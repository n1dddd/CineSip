# CineSip — Rule-Generation Pipeline Code Review

Scope: `backend/app/services/rule_generator.py`, `services/movie_search.py`,
`routes/game.py`, `services/game_manager.py`, `models.py`, judged against `AGENTS.md`.
Review only — **no source files were modified**.

Supporting files also inspected (they change some conclusions): `backend/app/database.py`,
`backend/app/main.py`, `frontend/nginx.conf`, `frontend/src/services/api.js`.

---

## Executive summary

The owner's complaint ("rules are too generic") has **three independent root causes**, and
they compound:

1. **Starvation of context.** Of ~25 usable fields TMDB returns for a movie, exactly
   **three** reach the model: `overview`, `genres[].name`, and `credits.cast[:8].name`.
   Character names, tagline, release year, runtime, director, keywords, collection and
   `vote_average` are all discarded or never requested. The model is given ~60 words of plot
   and eight actor names, so it cannot write anything film-specific.
2. **The prompt explicitly authorises generic output.** `rule_generator.py:25-26` tells the
   model that if context is thin it may fall back to genre-level triggers, and `:51-52`
   *mandates* "a genre staple" as one of the four rule kinds. The system prompt itself is
   requesting the behaviour being complained about.
3. **Silent total failure.** With `except Exception: continue` (`:176-177`) and zero logging,
   a 400 on `response_format`, a free-tier 429, or an OpenRouter `{"error": ...}` 200-body all
   look identical to "worked fine": the caller gets `_fallback_rules()` — eight hardcoded,
   maximally generic rules — with no signal anywhere. **The most likely explanation for the
   owner's complaint is that the LLM path is failing in production and nobody can see it.**

Two further **high-severity** defects unrelated to quality were found:

- **`nginx` will 504 before the backend finishes.** `frontend/nginx.conf:17-22` sets no
  `proxy_read_timeout`, so the default 60s applies; the worst case in `rule_generator.py:149`
  (3 models × 45s) is 135s. Slow generations return a 504 to the phone while the backend keeps
  going and *does* eventually write rules — the host sees an error and retries, producing
  duplicate rule sets.
- **Re-picking a movie silently destroys all scores.** `game.py:46` calls `clear_rules`, which
  `DELETE`s from `rules`; `drink_logs.rule_id` is `ON DELETE CASCADE` and `PRAGMA foreign_keys=ON`
  (`database.py:25`, `:66-67`), so every logged sip in the game is wiped. Nothing in the route
  prevents this mid-game. This directly violates AGENTS.md's "Server is the single source of
  truth for scores."

---

## 1. Context starvation — why output is generic

### 1.1 [HIGH] Only 3 of ~25 TMDB fields reach the model — `routes/game.py:30-37`

```python
overview = details.get("overview") or ""
genres = ", ".join(g["name"] for g in details.get("genres", []))
cast = ", ".join(c["name"] for c in (details.get("credits", {}).get("cast", [])[:8]))
plot_context = overview
if cast:
    plot_context += f"\n\nMain cast: {cast}"
```

Fields present in the response but **dropped**:

| Field | Why it matters for rule quality |
|---|---|
| `credits.cast[].character` | The single highest-value field. "Drink when **Furiosa** loses her arm" vs "Drink when Charlize Theron appears." Actor names are useless as on-screen triggers; character names are exactly what players shout. |
| `tagline` | Often the film's catchphrase — instant "someone says X" rule. |
| `release_date` | Year drives period-appropriate visual triggers (rotary phones, VHS, flip phones). Also disambiguates remakes (*Dune* 1984 vs 2021). |
| `runtime` | Needed to calibrate rule frequency (a 3h epic tolerates rarer triggers). |
| `credits.crew` → director | Director-signature visuals are prime drinking-game material (Wes Anderson centred symmetry, Nolan clocks). |
| `belongs_to_collection` | Franchise running gags. |
| `original_language` / `spoken_languages` | "Someone speaks Fremen/Klingon/German" rules. |
| `production_companies` | Studio idents, opening-logo rules. |
| `vote_average`, `popularity` | Weak, but signals how well-known the film is → how obscure a trigger can be. |

Fields **not even requested** — `movie_search.py:31`:

```python
params={"api_key": TMDB_API_KEY, "query": ..., "append_to_response": "credits"}
```

`append_to_response` should include `keywords,release_dates,videos`. **`keywords` is the biggest
miss**: TMDB keywords for *Mad Max: Fury Road* include `desert`, `car chase`, `dystopia`,
`post-apocalyptic`, `sandstorm` — each is a directly playable, countable, film-specific trigger,
and it is one extra query parameter away.

**Fix — `movie_search.py:28-34`:**
```python
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.get(
        f"{TMDB_BASE}/movie/{movie_id}",
        params={
            "api_key": TMDB_API_KEY,
            "append_to_response": "credits,keywords,release_dates",
        },
    )
```

**Fix — `routes/game.py:30-37`,** build a structured context block instead of a paragraph:
```python
d = details
year = (d.get("release_date") or "")[:4]
cast = [
    f'{c["name"]} as {c.get("character") or "?"}'
    for c in d.get("credits", {}).get("cast", [])[:10]
    if c.get("character")
]
crew = d.get("credits", {}).get("crew", [])
director = next((c["name"] for c in crew if c.get("job") == "Director"), None)
keywords = [k["name"] for k in d.get("keywords", {}).get("keywords", [])][:20]

parts = [
    f"TITLE: {req.movie_title} ({year})" if year else f"TITLE: {req.movie_title}",
    f"TAGLINE: {d['tagline']}" if d.get("tagline") else None,
    f"DIRECTOR: {director}" if director else None,
    f"RUNTIME: {d['runtime']} min" if d.get("runtime") else None,
    f"GENRES: {genres}",
    f"KEYWORDS (concrete on-screen elements): {', '.join(keywords)}" if keywords else None,
    "CHARACTERS (use these names, not actor names):\n  " + "\n  ".join(cast) if cast else None,
    f"PLOT:\n{overview}" if overview else None,
]
plot_context = "\n\n".join(p for p in parts if p)
```

### 1.2 [HIGH] The prompt licenses genericity — `rule_generator.py:25-26, 51-52`

```
If the context is thin, prefer genre-level observable triggers (e.g. "a car chase
starts", "someone pours a drink") over invented specifics. Do not guess at scenes.
...
- Mix these kinds: a spoken word/catchphrase, a recurring visual, a specific
  character action, a genre staple.
```

Two problems: the "thin context" escape hatch is a free pass the model will always take
(context *is* thin — see 1.1), and "a genre staple" makes 1-in-4 rules generic **by
instruction**. The two in-prompt GOOD examples are *Dune*-specific, which biases every
generation toward sci-fi phrasing regardless of the actual film.

**Fix:** make grounding auditable and quota-bound. Require the model to name its source
fragment per rule, then enforce it in `_validate`:

```python
SYSTEM_PROMPT = """...
Output STRICT JSON only:
{"rules": [{"team": 0, "description": "...", "source": "<exact phrase copied from the
provided context that this rule is grounded in>"}]}

Requirements:
- Exactly 8 rules.
- At least 6 of the 8 must name a CHARACTER, a KEYWORD, or a PLOT noun from the context
  verbatim. At most 2 may be genre staples.
- Every "source" must be a substring of the context you were given. A rule whose source
  you cannot copy verbatim is invalid — replace it.
- Under 90 characters each.
"""
```

and in `_validate`, drop rules whose `source` is not actually in the context, and reject the
whole payload if fewer than 6 grounded rules survive so the next model gets a turn.

### 1.3 [MED] Movie title and year are not in the user message consistently — `rule_generator.py:56-62`

`_build_user_msg` passes the title but never a year, so for any remake or franchise entry the
model has no way to know which film it is even by title. Fold the year in (see 1.1 fix).

### 1.4 [LOW] `temperature=0.85` with no `seed` — `rule_generator.py:163`

High temperature does not create specificity when context is absent; it creates *variance in
genericity*. With a proper context block, drop to ~0.7 and add `"seed"` for reproducibility
when debugging quality complaints.

---

## 2. `_VAGUE_PATTERNS` / `_is_playable`

`rule_generator.py:84-100`

### 2.1 [MED] False positives — the filter rejects perfectly good rules

| Pattern (`:88`, `:91`, `:87`, `:93`) | Legitimate rule it kills |
|---|---|
| `\bthe (setting\|tone\|mood\|genre)\b` | "Drink when **the setting** sun fills the frame." — `the setting` matches as a noun-phrase prefix. |
| `\bis (present\|shown\|depicted\|portrayed)\b` | "Drink when the ring **is shown** in close-up." — countable and fine. |
| `\bany character\b` | "Drink when **any character** says 'Fremen'." — perfectly countable. |
| `\bfeels\b` | "Drink when someone **feels** the wall for a switch." — a discrete physical action. |

These matter because every false positive brings `cleaned` closer to the `< 6` cliff (see 2.3).

### 2.2 [MED] False negatives — real bad output it does not catch

None of the following are matched:

- "Drink whenever the tension rises." (state)
- "Drink every time you notice good cinematography." (subjective, uncountable)
- "Drink when a character talks." / "Drink whenever there is dialogue." (true ~90% of runtime)
- "Drink when the movie gets dark." (ambiguous — lighting or tone?)
- "Take a shot for the vibes." (dangerous-ish, no trigger)
- "Drink whenever the protagonist is emotional." (state, not caught — `is (present|shown|...)`
  doesn't cover `is <adjective>`)
- "Finish your drink if the villain wins." — the prompt bans dangerous instructions (`:53`)
  but **nothing validates it**. `_is_playable` has no safety patterns at all.
- Any rule that is a **question** or **not a rule at all** ("Have fun!").

The filter is a denylist of nine phrasings against an open-ended failure space. A denylist
cannot win here.

**Fix:** invert it. Require a positive structural signal, and add a real safety denylist:

```python
_UNSAFE = re.compile(
    r"\b(finish (the|your) (bottle|drink|glass)|chug|shot(gun)?s? of|down it|"
    r"skull|neck it|drink until|keep drinking)\b", re.I
)

# A playable rule must reference a concrete on-screen event verb.
_EVENT_VERBS = re.compile(
    r"\b(appears?|says?|shouts?|screams?|shoots?|kisses|dies|explodes?|crashes|"
    r"enters?|leaves?|drinks?|smokes?|cries|laughs?|punches|falls?|opens?|"
    r"pulls?|draws?|reveals?|arrives?|starts?|cuts to|zooms?|is destroyed|"
    r"is killed|is named|is mentioned)\b"
)

def _is_playable(description: str) -> bool:
    d = description.lower().strip()
    if _UNSAFE.search(d):
        return False
    if any(re.search(p, d) for p in _VAGUE_PATTERNS):
        return False
    if not _EVENT_VERBS.search(d):        # NEW: must describe an event
        return False
    if d.endswith("?"):
        return False
    return True
```

and delete the over-broad `\bfeels\b`, `\bany character\b`, `\bthe (setting|...)\b` entries,
tightening the remaining ones (`\bis (present|shown) throughout\b`, `\bstruggles with\b` is fine).

### 2.3 [HIGH] Rejection can silently drop below 6 and fall through to fully generic rules

`rule_generator.py:124-125`:
```python
if len(cleaned) < 6:
    return None
```

The model returns 8. Two false positives (2.1) plus one malformed item and `cleaned` is 5 →
`_validate` returns `None` → `generate_rules` (`:174`) doesn't return → loop advances to the
next model → all three exhaust → **`_fallback_rules()`**, the eight hardcoded generic rules at
`:184-193`. The owner then sees "Drink whenever there's a dramatic pause" and concludes the AI
is bad. Worse: five *good, film-specific* rules were thrown away to reach that outcome.

**Fix:** accumulate across models instead of all-or-nothing, and only fall back on a true empty.

```python
async def generate_rules(...):
    ...
    pool: list[dict] = []
    for model in OPENROUTER_MODELS:
        ...
        rules = _validate(parsed, min_rules=1)   # relaxed: keep whatever is good
        if rules:
            pool.extend(rules)
            pool = _dedupe(pool)
            if len(pool) >= 8:
                break
    if len(pool) >= 6:
        return _balance(pool[:8])
    if pool:                                     # top up rather than discard
        return _balance((pool + _fallback_rules("")[: 8 - len(pool)])[:8])
    return _fallback_rules(movie_title)
```

### 2.4 [MED] 6 or 7 accepted rules produce unbalanced teams and a broken UI string

`:128-130` reassigns `team = i % 2` over a list that may be 6 or 7 long. With 7, Amber gets 4
and Teal gets 3. `frontend/src/pages/Lobby.jsx` renders ``${rules.length/2} per team``, which
displays **"3.5 per team"**. And an odd count means one team has a structurally lower chance of
drinking — unfair in a competitive game.

**Fix:** force an even count before balancing.
```python
cleaned = cleaned[: (len(cleaned) // 2) * 2][:8]   # always even, max 8
for i, rule in enumerate(cleaned):
    rule["team"] = i % 2
```

### 2.5 [LOW] `_fallback_rules` is never filtered by `_is_playable`

"Drink whenever there's a dramatic pause" (`:186`) and "Drink every time there's a close-up
shot" (`:188`) are precisely the uncountable, always-true rules the prompt at `:36-41`
forbids. The fallback set violates the pipeline's own playability contract. Replace the worst
offenders with genuinely discrete triggers (phone rings, door slams, someone lights a cigarette,
a gun is drawn, the title is spoken aloud).

---

## 3. Silent exception swallowing

### 3.1 [HIGH] `except Exception: continue` with zero logging — `rule_generator.py:176-177`

```python
except Exception:
    continue
```

This one clause hides, indistinguishably:

- HTTP 400 — model rejected `response_format` (§4.1)
- HTTP 401/402 — bad key / out of credits
- HTTP 429 — free-tier rate limit (the **most common** production failure)
- HTTP 5xx / upstream provider down
- `httpx.ReadTimeout` at 45s
- `KeyError: 'choices'` — OpenRouter returns HTTP 200 with `{"error": {...}}` for some
  provider errors, so `resp.json()["choices"][0]` (`:169`) raises inside the `try`
- `TypeError` when `content` is `None`
- `json.JSONDecodeError` variants not handled by `_extract_json`

There is no logger anywhere in the backend (`grep` finds no `logging` import in `app/`). In
production the owner cannot answer "did the LLM even run?" — which is exactly the question
raised by the complaint.

**Fix:**
```python
import logging, time
log = logging.getLogger(__name__)

for model in OPENROUTER_MODELS:
    t0 = time.monotonic()
    try:
        resp = await client.post(...)
        if resp.status_code != 200:
            log.warning(
                "rulegen model=%s http=%s body=%s elapsed=%.1fs",
                model, resp.status_code, resp.text[:400], time.monotonic() - t0,
            )
            continue
        data = resp.json()
        if "choices" not in data:
            log.warning("rulegen model=%s non-choices body=%s", model, str(data)[:400])
            continue
        content = (data["choices"][0]["message"].get("content") or "")
        usage = data.get("usage", {})
        parsed = _extract_json(content)
        if parsed is None:
            log.warning("rulegen model=%s unparseable content=%r", model, content[:400])
            continue
        rules, rejected = _validate(parsed)
        if rejected:
            log.info("rulegen model=%s rejected=%s", model, rejected)  # the exact strings
        if rules:
            log.info(
                "rulegen ok model=%s n=%d tokens=%s elapsed=%.1fs",
                model, len(rules), usage.get("total_tokens"), time.monotonic() - t0,
            )
            return rules
    except httpx.TimeoutException:
        log.warning("rulegen timeout model=%s after %.1fs", model, time.monotonic() - t0)
    except Exception:
        log.exception("rulegen unexpected failure model=%s", model)

log.error("rulegen ALL MODELS FAILED movie=%r — serving generic fallback", movie_title)
return _fallback_rules(movie_title)
```

**What must be logged, minimally:** model name, HTTP status, response body snippet on
non-200, elapsed seconds, token usage, the **rejected rule strings with the pattern that
rejected them** (this is how you tune `_VAGUE_PATTERNS` against real data), and an
`ERROR`-level line whenever the generic fallback is served. Add `logging.basicConfig` in
`main.py` so it reaches `docker compose logs`.

### 3.2 [MED] Frontend swallows the same failure — `frontend/src/pages/Lobby.jsx`

```js
catch { setErr('Could not write rules for that title. Try another.') }
```
Combined with §3.1, a 504 (§4.4) shows "try another title" for a film that was perfectly fine.

### 3.3 [MED] `get_movie_details` failures become HTTP 500, not 503 — `movie_search.py:33` / `game.py:27-28`

`resp.raise_for_status()` raises `httpx.HTTPStatusError` on a TMDB 404/429/5xx. `game.py:27`
only checks `if "error" in details`, which catches the missing-key case but never the raised
exception, so the request 500s with a stack trace.

```python
# movie_search.py
try:
    resp = await client.get(...)
    resp.raise_for_status()
    return resp.json()
except httpx.HTTPStatusError as e:
    log.warning("tmdb detail %s -> %s", movie_id, e.response.status_code)
    return {"error": f"TMDB returned {e.response.status_code}"}
except httpx.RequestError as e:
    log.warning("tmdb detail %s unreachable: %s", movie_id, e)
    return {"error": "TMDB unreachable"}
```

### 3.4 [LOW] No timeouts on TMDB clients — `movie_search.py:14, 28, 42`

`httpx.AsyncClient()` with no `timeout=` uses the 5s default; that's acceptable but should be
explicit (`timeout=10.0`) so it can't silently change with an httpx upgrade, and so TMDB
latency is bounded independently of the LLM budget.

---

## 4. Robustness

### 4.1 [HIGH] `response_format: json_object` can 400 the entire request — `rule_generator.py:165`

OpenRouter forwards `response_format` to the upstream provider. Free-tier endpoints
(including several `:free` Gemma and Llama routes) do not all support structured outputs and
return **400 Bad Request** for the whole call — not a degraded response. Combined with §3.1
this is invisible. Note the code already has a full markdown-fence-and-regex JSON extractor
(`_extract_json`, `:65-79`), so the parameter buys almost nothing while risking everything.

**Fix — send it only where supported, and retry without it on 400:**
```python
def _payload(model, messages, structured=True):
    body = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 1200}
    if structured:
        body["response_format"] = {"type": "json_object"}
    return body

for model in OPENROUTER_MODELS:
    for structured in (True, False):
        resp = await client.post(url, headers=H, json=_payload(model, messages, structured))
        if resp.status_code == 400 and structured:
            log.info("rulegen model=%s rejected response_format, retrying plain", model)
            continue          # retry same model without response_format
        break
```

### 4.2 [HIGH] No retry/backoff on 429 — `rule_generator.py:150-177`

Free OpenRouter models rate-limit aggressively and per-day. A single 429 burns the model for
that request; three 429s in a row = generic fallback. There is no `Retry-After` handling and
no jitter.

```python
async def _post_with_retry(client, model, messages, attempts=3):
    for a in range(attempts):
        resp = await client.post(...)
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 0)) or (2 ** a) + random.random()
            if a < attempts - 1 and wait <= 8:
                log.info("rulegen 429 model=%s backoff=%.1fs", model, wait)
                await asyncio.sleep(wait)
                continue
        return resp
    return resp
```

### 4.3 [HIGH] 135s worst case blocks a request the phone is awaiting — `rule_generator.py:149`

`timeout=45.0` × 3 models = 135s of a single blocking `POST /api/games/{id}/movie`
(`game.py:39-43`). Meanwhile the host's phone is sitting on a spinner and the lobby is polling
every 2s.

### 4.4 [HIGH] nginx will 504 first — `frontend/nginx.conf:17-22`

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    ...
}
```

No `proxy_read_timeout` → nginx's default **60s**. Any generation past 60s returns 504 to the
phone. The backend does **not** stop; it finishes and writes rules. So the host sees "Could not
write rules for that title" (§3.2), taps a different film or the same one again, and the
pipeline runs a second time — producing the duplicate / churned rule sets that also destroy
drink logs (§5.1). This is a genuine production bug independent of rule quality.

Minimum fix (`nginx.conf`):
```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 4.5 [HIGH] **Verdict: yes, rule generation should be backgrounded**

The app already has everything needed to make this trivial — the lobby polls
`GET /api/games/{code}` every 2s and already renders a "Writing rules…" state with a pulse dot
when `rules.length === 0`. Returning 202 immediately and filling rules in a background task
costs almost no frontend work and removes the 504, the double-submit, and the timeout budget
problem in one move.

```python
# game.py
@router.post("/{game_id}/movie", status_code=202)
async def select_movie(game_id: int, req: SelectMovieRequest, bg: BackgroundTasks):
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(404, "Game not found")
    if game.status != "lobby":
        raise HTTPException(409, "Cannot change the film once the game has started")

    details = await movie_search.get_movie_details(req.movie_id)
    if "error" in details:
        raise HTTPException(503, details["error"])

    await game_manager.set_movie(game_id, req.movie_title, req.movie_id)
    await game_manager.clear_rules(game_id)
    bg.add_task(_generate_and_store, game_id, req.movie_title, details)
    return {"movie_title": req.movie_title, "rules": [], "status": "generating"}


async def _generate_and_store(game_id: int, title: str, details: dict):
    try:
        rules = await rule_generator.generate_rules(**_build_context(title, details))
        await game_manager.replace_rules(game_id, rules)
    except Exception:
        log.exception("rulegen background task failed game=%s", game_id)
        await game_manager.replace_rules(game_id, rule_generator._fallback_rules(title))
```

Add a `games.rules_status` column (`pending`/`ready`/`fallback`) so the lobby can distinguish
"still writing" from "done, and they're generic because the LLM failed" — and so the **host**
gets told when fallback rules were served, which is currently impossible.

With generation backgrounded, the 45s-per-model budget stops mattering and you can afford
retries (§4.2) and a 4th model.

### 4.6 [MED] Module-level env reads defeat `.env` load order — `rule_generator.py:8-17`, `movie_search.py:6`

`OPENROUTER_API_KEY` / `TMDB_API_KEY` / `OPENROUTER_MODELS` are captured at **import time**.
`database.py:10-16` explicitly documents that this is wrong and reads `DB_PATH` lazily for
exactly that reason — the services are inconsistent with the established pattern. If `.env`
loading ever moves after router import, the app silently runs key-less and serves fallback
rules forever.

```python
def _api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")

def _models() -> list[str]:
    return [m.strip() for m in os.getenv("OPENROUTER_MODELS", _DEFAULT_MODELS).split(",") if m.strip()]
```

### 4.7 [LOW] `startswith("your_")` placeholder detection is fragile — `rule_generator.py:141`, `movie_search.py:11`

A placeholder like `sk-REPLACE_ME` or an empty-string-with-whitespace passes. Prefer a length
sanity check (`len(key) < 20`) plus the prefix test.

### 4.8 [LOW] `_extract_json` greedy match — `rule_generator.py:73`

`re.search(r"\{.*\}", content, re.DOTALL)` is greedy and will span from the first `{` to the
last `}` across unrelated prose. Prefer a brace-balance scan, or at minimum try both greedy
and non-greedy.

### 4.9 [LOW] No `max_tokens` headroom for reasoning models — `rule_generator.py:164`

`max_tokens: 900`. If someone puts a reasoning model in `OPENROUTER_MODELS`, thinking tokens
consume the budget and the response truncates mid-JSON → `_extract_json` returns `None` →
silent skip. Raise to 1200-1500 and log `finish_reason == "length"`.

---

## 5. Duplicates, cross-team collisions, and length

### 5.1 [HIGH] Regenerating rules cascade-deletes every drink log — `game.py:45-50`, `game_manager.py:120-124`, `database.py:66-67`

```python
await game_manager.clear_rules(game_id)      # DELETE FROM rules WHERE game_id = ?
```
`drink_logs.rule_id REFERENCES rules(id) ON DELETE CASCADE` and `PRAGMA foreign_keys=ON`.
There is **no status guard** on the route, so a host who taps "Change the film" mid-movie
silently zeroes both teams' scores. AGENTS.md: *"Server is the single source of truth for
scores."* This breaks that guarantee.

**Fix:** reject the change once the game is active (see §4.5 route above), and/or soft-delete:
```sql
ALTER TABLE rules ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
-- clear_rules: UPDATE rules SET active = 0 WHERE game_id = ?
```

### 5.2 [MED] No deduplication anywhere — `rule_generator.py:109-130`

`_validate` never checks for repeats. Real free-model output routinely contains near-duplicates
("Someone says 'spice'." / "A character mentions spice."). Two teams then get the same rule and
the game becomes a coin flip — and because `team = i % 2` is assigned by index (`:128-129`),
adjacent duplicates land on *opposite* teams, which is the worst case.

```python
def _norm(d: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", d.lower()).replace("drink when ", "").replace("drink whenever ", "").strip()

seen: set[str] = set()
for ...:
    key = _norm(desc)
    if key in seen:
        log.info("rulegen dropped duplicate: %r", desc)
        continue
    # also catch near-duplicates
    if any(difflib.SequenceMatcher(None, key, s).ratio() > 0.82 for s in seen):
        log.info("rulegen dropped near-duplicate: %r", desc)
        continue
    seen.add(key)
    cleaned.append(...)
```

### 5.3 [MED] Prompt says <90 chars, validator allows 200 — `rule_generator.py:49` vs `:114`, `models.py:19`

```python
- Each description is one short sentence, under 90 characters   # :49
...
if not desc or len(desc) > 200: continue                        # :114
description: str = Field(min_length=1, max_length=200)          # models.py:19
```

Nothing enforces the 90-char guidance, so 150-char rules ship. In a dark room, on a phone, in a
single-line `.rule-text` row, those truncate or wrap and become unreadable — directly against
AGENTS.md's design constraints. Note the mismatch is intentional-looking (200 also matches
`AddRuleRequest` for human-written rules) but the *generated* path should be tighter.

```python
_MAX_GENERATED = 100          # 90 guidance + slack
if not desc or len(desc) > _MAX_GENERATED:
    log.info("rulegen dropped over-length (%d chars): %r", len(desc), desc)
    continue
```
Keep `models.py:19` at 200 for manually added rules; that's a different contract.

### 5.4 [MED] Concurrent/double taps produce duplicate rule sets — `game.py:39-50`

No idempotency key, no lock, no `status` guard. Two hosts (or one impatient host after a 504,
§4.4) hitting the endpoint concurrently interleave `clear_rules` and `add_rule` and can leave
16 rules, or 8 rules from two different films. Add a per-game `asyncio.Lock` or an
`UPDATE ... WHERE movie_id IS DISTINCT FROM ?` guard.

### 5.5 [LOW] Non-atomic, N-commit rule write — `game.py:47-50`, `game_manager.py:127-136`

```python
created = [await game_manager.add_rule(game_id, r["team"], r["description"]) for r in rules]
```
Eight separate `INSERT` + `COMMIT` round-trips. A crash mid-loop leaves a partial rule set that
the lobby will happily start a game with. Add `game_manager.replace_rules(game_id, rules)` that
does the delete and all inserts in one transaction with `executemany`.

---

## 6. Other defects found in scope

| Sev | Location | Issue |
|---|---|---|
| MED | `main.py:14-20` | `allow_origins=["*"]` **with** `allow_credentials=True` is an invalid CORS combination (browsers reject it) and contradicts AGENTS.md's same-origin rule. CORS middleware is not needed at all behind nginx — remove it, or restrict to the known origin. |
| MED | `game.py:10-12` | `SelectMovieRequest` has no field constraints: `movie_title` is unbounded (arbitrary-length string straight into the DB and into the LLM prompt — a prompt-injection vector) and `movie_id` is unvalidated. Use `movie_title: str = Field(min_length=1, max_length=200)` and `movie_id: int = Field(gt=0)`. |
| MED | `game.py:63-69` | `log_drink` never verifies `rule_id` belongs to `game_id`, or that `player_id` is in that game. Any client can inflate another game's score. |
| LOW | `models.py:16-19` | `AddRuleRequest.game_id` is dead — `add_rule` (`game.py:55`) takes `game_id` from the path and ignores the body field. Mismatched values silently do the wrong-looking thing. Remove the field. |
| LOW | `game_manager.py:8-22` | `_generate_code()` uses `random`, not `secrets`, and loops with a TOCTOU race between the `SELECT` and `INSERT`. The `UNIQUE` constraint saves correctness but the insert can raise. Use `secrets.choice` and catch `IntegrityError` to retry. |
| LOW | `game_manager.py:96, 106, 117` | Return type is `GameOut` but `get_game_by_id` can return `None`; annotations on `start_game`/`finish_game` claim non-optional. |
| LOW | `game_manager.py:139-152` | `log_drink` overwrites `cursor` before reading `lastrowid`... it happens to read `lastrowid` from the correct cursor, but the shadowing is a latent bug one edit away from breaking. |
| LOW | `database.py:19-26` | A single module-global connection with no lock; `get_db()` is racy on first concurrent call (two coroutines can both see `_db is None`). |

---

## 7. AGENTS.md compliance verdict

| Rule | Verdict |
|---|---|
| "The LLM never invents film facts" | **Partially met, poorly.** The mechanism is right (TMDB first, prompt-constrained), but the context is so thin (§1.1) that the prompt's own escape hatch (§1.2) turns it into genre boilerplate. The letter of the rule is honoured; the intent — *rules from that film's real plot* — is not. |
| "Rules generated from that film's **real** plot" | **Violated in practice** whenever the fallback fires (§2.3, §3.1, §4.1-4.4), which is likely often and is completely invisible. |
| "Server is the single source of truth for scores" | **Violated** — §5.1 cascade-deletes `drink_logs`. |
| "Same-origin API" | Met in `api.js`; undermined by wildcard CORS in `main.py:14-20`. |
| "Backend is not publicly exposed" | Met (compose uses `expose`). |
| Design: readable in a dark room | **At risk** — §5.3 lets 200-char rules through into a single-line row. |

---

## 8. Recommended fix order

1. `nginx proxy_read_timeout` + background the generation (§4.4, §4.5) — stops the 504 →
   retry → score-wipe chain.
2. Status guard on `POST /{id}/movie` + soft-delete rules (§5.1).
3. Add logging everywhere (§3.1) — **do this before tuning quality**, because without it you
   are guessing whether the LLM ran at all.
4. Drop / conditionally send `response_format`, add 429 backoff (§4.1, §4.2).
5. Enrich the TMDB context: `keywords`, `cast[].character`, tagline, year, director (§1.1).
6. Rewrite the prompt to require verbatim grounding and cap genre staples at 2 (§1.2).
7. Replace the `_VAGUE_PATTERNS` denylist with denylist + positive event-verb requirement +
   safety patterns; accumulate rules across models instead of all-or-nothing (§2.1-2.3).
8. Dedupe, enforce even count, enforce 100-char cap (§5.2, §2.4, §5.3).
