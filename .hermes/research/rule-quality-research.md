# CineSip — Rule Quality Research & Implementation Spec

**Goal:** make LLM-generated rules name *real* things from the chosen film (characters, places, objects, motifs) instead of genre filler like "Drink when the music swells."

**Status:** research only. No source files modified. All TMDB / Wikipedia / Wikidata calls below were executed live against the real `TMDB_API_KEY` in `~/cinesip/.env`; all Python in §5 was executed and its output is pasted verbatim.

---

## 1. Root cause (confirmed by reading the code)

The prompt is not the primary problem. **The context is starved.** Three concrete defects:

### 1.1 `game.py` passes actor names, not character names

`backend/app/routes/game.py:32-34`:

```python
cast = ", ".join(
    c["name"] for c in (details.get("credits", {}).get("cast", [])[:8])
)
```

`c["name"]` is the **actor**. The model receives `Timothée Chalamet, Zendaya, Rebecca Ferguson` — useless for a rule. `c["character"]` is right there in the same dict and holds `Paul Atreides, Chani, Jessica`. **This single field is the highest-value fix in the whole report.**

### 1.2 The only plot text is the 1-sentence TMDB `overview`

For *Dune: Part Two*, `overview` is **305 characters**. The English Wikipedia "Plot" section is **4,002 characters** — 13× more, and it is where the film-specific nouns actually live (`Sietch Tabr`, `Water of Life`, `Sardaukar`, `Kwisatz Haderach`). None of those appear in the overview.

### 1.3 `movie_search.py` requests only `append_to_response=credits`

`keywords` is free, in the same HTTP round-trip, and yields 22 concrete motif terms for Dune 2 (`sandworm`-adjacent: `giant worm`, `sand dune`, `sandstorm`, `stillsuit`-adjacent motifs, `messiah`, `desert`). `tagline`, `runtime`, and `belongs_to_collection` are already in the base response and are currently discarded.

### 1.4 The system prompt actively *invites* filler

`rule_generator.py:25-26` says:

> *"If the context is thin, prefer genre-level observable triggers (e.g. "a car chase starts", "someone pours a drink")"*

and line 52 requires a **"genre staple"** as one of the four rule kinds. The model is doing exactly what it is told. Meanwhile `_fallback_rules()` is a hardcoded list of precisely the bland rules being complained about — and it fires whenever validation returns `None`, which is often, because `_validate` demands ≥6 rules and rejects nothing entity-related. **The escape hatch is wider than the main path.**

### 1.5 `_validate` has no specificity check at all

`_VAGUE_PATTERNS` catches ongoing *states* ("is on his path"). It does not catch generic *events*. `"Drink when the music swells dramatically."` passes every current check.

---

## 2. Free, no-extra-key data sources (all verified live)

### 2.1 TMDB — one request, everything

Replace the current details call with a single request. `api_key` as a query param (the existing auth style) works fine; no Bearer token needed.

```
GET https://api.themoviedb.org/3/movie/{movie_id}
    ?api_key={TMDB_API_KEY}
    &language=en-US
    &append_to_response=keywords,credits,alternative_titles,release_dates
```

Verified against `movie_id=693134` (*Dune: Part Two*). Response top-level keys confirmed present:

```
adult, alternative_titles, backdrop_path, belongs_to_collection, budget,
credits, genres, homepage, id, imdb_id, keywords, origin_country,
original_language, original_title, overview, popularity, poster_path,
production_companies, production_countries, release_date, release_dates,
revenue, runtime, spoken_languages, status, tagline, title, video,
vote_average, vote_count
```

Exact JSON paths, with real observed values:

| What | Exact JSON path | Verified value (Dune 2) |
|---|---|---|
| Title | `$.title` | `Dune: Part Two` |
| Year | `$.release_date[:4]` | `2024` |
| **Tagline** | `$.tagline` | `Long live the fighters.` |
| Runtime (min) | `$.runtime` | `167` |
| Genres | `$.genres[*].name` | `Science Fiction`, `Adventure` |
| **Keywords** | `$.keywords.keywords[*].name` | 22 items: `sandstorm`, `chosen one`, `giant worm`, `desert`, `sand dune`, `messiah`, `space opera`, `distant future`, … |
| **Character names** | `$.credits.cast[*].character` | `Paul Atreides`, `Chani`, `Jessica`, `Stilgar`, `Gurney Halleck`, `Feyd-Rautha`, `Princess Irulan`, `Beast Rabban`, `Baron Harkonnen`, `Reverend Mother Mohiam` |
| Actor for each | `$.credits.cast[*].name` | `Timothée Chalamet`, `Zendaya`, … |
| Billing order | `$.credits.cast[*].order` | `0,1,2,…` — sort ascending, take top 10–12 |
| Director | `$.credits.crew[?(@.job=='Director')].name` | `Denis Villeneuve` |
| Franchise | `$.belongs_to_collection.name` | `Dune Collection` |
| Countries | `$.production_countries[*].name` | `United States of America` |
| Certification | `$.release_dates.results[?(@.iso_3166_1=='US')].release_dates[*].certification` | US rating |

**Critical note on `keywords`:** for the *movie* namespace the nesting is `keywords.keywords[]` (double). It is **not** `keywords.results[]` — that shape is the *TV* namespace. Getting this wrong silently yields an empty list.

**Rate limits.** TMDB's official rate-limiting page states the legacy 40-req/10-s limit was **disabled on 2019-12-16**; the current soft ceiling is *"somewhere in the 40 requests per second range"* and callers must respect a `429`. CineSip issues **one** TMDB request per movie selection, so this is a non-issue — but the `append_to_response` consolidation matters anyway because it turns what would be 4 requests into 1.

**`alternative_titles` — recommend AGAINST including.** Verified: 35 entries for Dune 2, almost all non-English transliterations (`デューン 砂の惑星PART2` etc.). It is context bloat that will pull a free model toward non-English output. Skip it. (It is listed here because it was asked about; the finding is negative.)

**`videos` — recommend AGAINST.** Returns trailer metadata (`name`, `key`, `site`), not film content. Titles like "Official Trailer" contribute zero film specifics. Skip.

### 2.2 Wikipedia — the plot section (free, no key)

This is the biggest quality unlock after `cast[].character`.

**Step 1 — resolve TMDB id → Wikipedia title via Wikidata property P4947.** Robust; avoids title-guessing and disambiguation collisions (`Dune (1984)` vs `Dune (2021)`).

```
GET https://query.wikidata.org/sparql?format=json&query=<urlencoded>
```

Query:

```sparql
SELECT ?item ?enwiki WHERE {
  ?item wdt:P4947 "693134".
  ?enwiki schema:about ?item;
          schema:isPartOf <https://en.wikipedia.org/>.
}
```

Verified live response:

```json
[{"item":  {"value": "http://www.wikidata.org/entity/Q109228991"},
  "enwiki":{"value": "https://en.wikipedia.org/wiki/Dune:_Part_Two"}}]
```

Path: `$.results.bindings[0].enwiki.value` → take the last URL path segment, URL-decode → `Dune:_Part_Two`.

**Step 2 — fetch the article as plaintext and slice out the Plot section.**

```
GET https://en.wikipedia.org/w/api.php
    ?action=query&format=json&prop=extracts&explaintext=1&redirects=1
    &titles=Dune%3A%20Part%20Two
```

Verified: `pageid 63790171`, extract length **37,896 chars**. Path: `$.query.pages.<pageid>.extract` (the page key is a dynamic numeric id — take `list(pages.values())[0]`).

Slice the Plot section with:

```python
m = re.search(r"\n== (?:Plot|Synopsis|Premise|Plot summary) ==\n(.*?)(?=\n== )",
              text, re.S | re.I)
```

Verified: yields **4,002 chars** of real plot beginning *"Following the defeat of House Atreides by House Harkonnen, Princess Irulan—daughter of the Padishah Emperor, Shaddam Corrino IV—records in her journal…"*

`prop=extracts&explaintext=1` is strongly preferred over `action=parse&prop=wikitext`, which returns raw wikitext full of `{{templates}}` and `[[links]]` that you would have to strip yourself. A section-index route (`action=parse&prop=sections` → find index of "Plot" → refetch that section) also works and was verified (`[('1','Plot'),('2','Cast'),('3','Production'),…]`) but costs a second round-trip for no gain over regex-slicing the plaintext.

**Rate limits & etiquette.** Wikimedia asks for ≤200 req/s on the REST API and — importantly — a **unique identifying `User-Agent`**. Requests with a generic or absent UA are subject to blocking. Send:

```
User-Agent: CineSip/1.0 (https://cinesip.dseniv.cc; contact@dseniv.cc)
```

No key, no signup, commercial use permitted. Content is CC BY-SA — CineSip derives entity nouns rather than republishing prose, but a small "plot data from Wikipedia" credit in the UI is the polite call.

**Truncate to ~2,500 chars** before sending to the model. Free-tier context is limited and the first half of a plot section carries most of the distinctive nouns.

### 2.3 Degradation ladder (brand-new releases)

Honors the AGENTS.md rule "the LLM never invents film facts" — every tier is fetched, none is model memory.

| Tier | Available | Action |
|---|---|---|
| A | Wikipedia plot found | Full entity list: characters + plot proper nouns + keywords |
| B | No Wikipedia article (just-released) | Characters + keywords + overview. **Verified sufficient** — see below |
| C | No cast, no keywords | Only then fall back — and use *entity-templated* fallbacks (§5.4), never the current generic list |

Tier B verified live on two films with `plot=''` (no Wikipedia input at all):

- **Sinners (2025)** → 41 entities: `Smoke | Mary | Sammie Moore | Remmick | Annie | Pearline | Cornbread | Delta Slim | Grace Chow | Bo Chow | … | blues music | klansmen | twins | church | vampire | train station | southern gothic`
- **Kung Fu Panda 4** → 26 entities: `Po | Zhen | The Chameleon | Shifu | Li | Mr. Ping | Tai Lung | Han | Granny Boar | Mantis | … | kung fu | wuxia | chameleon | panda`

Those are richly film-specific with zero Wikipedia dependency. A brand-new release still gets good rules.

---

## 3. Prompt engineering for free/small instruct models

Sources consulted: Madaan et al., *Self-Refine: Iterative Refinement with Self-Feedback* (arXiv:2303.17651); Geng et al., *Generating Structured Outputs from Language Models: Benchmark and Studies* (arXiv:2501.10868); Tam et al., *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of LLMs* (arXiv:2408.02442); *Navigating the Impact of Structured Output Format on LLM Performance* (arXiv:2509.21791); OpenRouter Structured Outputs docs; TMDB rate-limiting docs; Wikimedia API etiquette docs.

### 3.1 Entity anchoring — the core technique

Give the model a closed, explicit `ENTITY LIST` and make naming an item from it a hard requirement, *enforced in code*. This converts an open-ended creative task (where a small model falls back on high-frequency training priors — "music swells") into **slot filling** over a supplied vocabulary. This is the same grounding mechanism that makes RAG work, and it is the technique the deterministic validator in §5 is built to enforce. Prompt-level instruction alone is not enough on free models; the validator is what makes it real.

### 3.2 Few-shot exemplars — with a *different* film

arXiv:2509.21791 finds few-shot prompting measurably improves format compliance; arXiv:2603.03305 uses k=3 in-context examples as the standard "Constrained Few-Shot" baseline. Two design rules specific to this task:

- **Draw exemplars from a film that is NOT the target.** Using Dune examples (as the current prompt does, lines 33-35) causes small models to copy the Dune nouns verbatim into rules for unrelated films. Use a fixed neutral exemplar (below: *Jaws*) and never a film a user might pick.
- **Show a paired BAD → GOOD rewrite**, not just good examples. Contrastive pairs teach the boundary. The current prompt does this well for playability; extend it to specificity.

### 3.3 Ban list in the prompt *and* in code

State the banned phrasings explicitly in the prompt (cheap, catches most), and enforce with regex (§5.2). Negative instructions alone are unreliable on small models — a known failure mode where mentioning a concept raises its salience. Prompt-ban + code-reject is the belt-and-braces that actually works.

### 3.4 Temperature

Current `0.85` is too high. High temperature is *not* what produces specificity here — specificity comes from context, and high temperature increases both format violations and drift toward generic training priors. **Recommend `0.5`** for pass 1 and `0.2` for the repair pass. Also set `top_p: 0.9` and `presence_penalty: 0.3` (the latter discourages repeating the same noun across all 8 rules).

### 3.5 JSON: keep `json_object`, add schema *in the prompt*

Per OpenRouter docs, `json_schema` support is **per-endpoint, not per-model**, and free endpoints for `llama-4-maverick:free` / `gemma-3-27b-it:free` frequently do not advertise `structured_outputs`. Requesting `json_schema` with `provider.require_parameters: true` would shrink routing to endpoints that may not include the free tier — i.e. it can break the free path entirely.

**Recommendation:** keep `response_format: {"type": "json_object"}` (syntax guarantee only), restate the schema in the prompt, and rely on the existing `_extract_json` + the §5 validator for field-level conformance. arXiv:2501.10868 finds constrained decoding helps downstream tasks up to 4% — worth having where available, not worth losing free routing over. Optionally send `json_schema` *only* for the paid `google/gemini-2.5-flash` tier.

Note also arXiv:2408.02442's finding that format restriction can *degrade* reasoning quality; since the reasoning here is trivial (pick an entity, phrase an event), the tradeoff favors keeping the format simple — a flat array of short strings, which is what the schema below is.

### 3.6 Two-pass generate-then-critique — targeted, not blanket

Self-Refine (arXiv:2303.17651) improves outputs via generate → feedback → refine. But per the practitioner consensus, self-critique **helps on objectively checkable criteria (format fidelity, instruction adherence, fact-matching-source) and fails on subjective quality**, where it collapses output toward generic polish — exactly the failure CineSip is trying to escape.

So do **not** run a blanket "make these better" pass. Instead:

- **Pass 1:** generate 8 rules.
- **Deterministic validation** (§5) — code, not the model, produces the critique.
- **Pass 2 (only if rules were rejected):** send back the *specific* machine-generated critique — "these 3 rules named no entity from the ENTITY LIST: […]. Replace them. Unused entities you may use: […]" — and ask only for replacements at `temperature=0.2`.

This is Reflexion-shaped rather than Self-Refine-shaped: the feedback signal is external and objective (the validator), which the sources identify as strictly stronger than model self-judgment. Cap at **one** repair pass; k>2 drifts without improving. Cost is ~1.3 calls average, not 3–5×.

---

## 4. Recommended prompts (copy-pasteable)

### 4.1 New `SYSTEM_PROMPT`

```python
SYSTEM_PROMPT = """You write drinking-game rules for a movie night. Your rules must be
SPECIFIC to the one film described in the user message — a player who knows the film should
read them and think "yes, that's this movie".

=== RULE 1: EVERY RULE MUST NAME A REAL THING FROM THIS FILM ===
The user message ends with an ENTITY LIST: real character names, places, objects and motifs
taken from this film's actual data. Every single rule you write MUST contain at least one
item from that ENTITY LIST, spelled the same way. A rule that names nothing from the ENTITY
LIST will be thrown away.
Prefer character names, named places, and named objects over abstract words.

=== RULE 2: NEVER INVENT FACTS ===
Use ONLY the title, tagline, genres, keywords, characters, plot summary and ENTITY LIST given
to you. Do not add plot points, character names, or quotes from your own memory — you may be
shown a film released after your training. If you are unsure whether something happens, write
a rule about a thing that simply APPEARS or is SAID BY NAME instead.

=== RULE 3: EVERY RULE IS A COUNTABLE MOMENT ===
A rule is valid only if a room of drunk people can point at the screen and instantly agree
"that just happened". One clear instant, not a mood or an ongoing state.
Never write a rule that is true for most of the runtime.
Never begin a rule with "When <character> is ..." describing a state.

=== RULE 4: BANNED — these are auto-rejected ===
Do not write rules about: the music, the score, swelling music, dramatic pauses, close-ups,
slow motion, scene changes, changing locations, camera pans or zooms, establishing shots,
the lighting, the weather, "a car chase starts", "someone enters a room", "a phone rings",
"an explosion happens", "the main character", "the hero", "the villain", "the protagonist",
"a new character appears", or any rule that would work for a different film.
If a rule you drafted would still make sense for a completely different movie, delete it and
write one that names an ENTITY instead.

=== EXAMPLE (a different film — copy the STYLE, never these nouns) ===
For a film whose ENTITY LIST was: Brody, Quint, Hooper, Amity Island, the Orca, the shark,
the yellow barrels, the beach, the mayor

BAD -> GOOD rewrites:
  BAD  "Drink when the music swells."        GOOD "The shark's fin breaks the surface."
  BAD  "Drink when someone is scared."       GOOD "Brody tells someone to get out of the water."
  BAD  "Drink when a boat appears."          GOOD "A yellow barrel goes under."
  BAD  "Drink at a close-up."                GOOD "Quint drinks or sings on the Orca."
  BAD  "Drink when the mood is tense."       GOOD "Someone says 'Amity'."

=== OUTPUT ===
Output STRICT JSON only. No markdown fences, no commentary, matching exactly:
{"rules": [{"team": 0, "description": "..."}, {"team": 1, "description": "..."}]}

Requirements:
- Exactly 8 rules.
- Alternate team 0 and team 1, starting at 0, so each team gets exactly 4.
- Each description is ONE short sentence under 90 characters, phrased as an event that
  happens: "X appears", "someone says 'Y'", "X does Z".
- Use at least 6 DIFFERENT items from the ENTITY LIST across the 8 rules. Do not build
  every rule around the same character.
- Mix these kinds, all still entity-anchored: a named character's signature action; a named
  object or place appearing; a specific word or name being spoken aloud; a recurring visual
  motif from the keywords.
- Fun and social. No slurs. No dangerous instructions ("finish the bottle", "down it").
"""
```

### 4.2 New user-message template

```python
def _build_user_msg(ctx: dict) -> str:
    """ctx keys: title, year, tagline, runtime, genres, keywords,
    characters [{character, actor}], plot, entity_list, plot_source"""
    lines = [
        f"FILM: {ctx['title']} ({ctx['year']})",
    ]
    if ctx.get("tagline"):
        lines.append(f"TAGLINE: {ctx['tagline']}")
    if ctx.get("runtime"):
        lines.append(f"RUNTIME: {ctx['runtime']} minutes")
    if ctx.get("collection"):
        lines.append(f"FRANCHISE: {ctx['collection']}")
    if ctx.get("genres"):
        lines.append(f"GENRES: {', '.join(ctx['genres'])}")
    if ctx.get("keywords"):
        lines.append(f"TMDB KEYWORDS (real motifs in this film): "
                     f"{', '.join(ctx['keywords'][:20])}")

    if ctx.get("characters"):
        lines.append("\nCHARACTERS (use these NAMES, not the actors'):")
        for c in ctx["characters"]:
            actor = f"  [played by {c['actor']}]" if c.get("actor") else ""
            lines.append(f"  - {c['character']}{actor}")

    if ctx.get("plot"):
        lines.append(f"\nPLOT SUMMARY (source: {ctx.get('plot_source', 'TMDB')} "
                     f"— this and the lists above are your ONLY source of facts):")
        lines.append(ctx["plot"])

    lines.append(
        "\n=== ENTITY LIST — every rule MUST contain at least one of these, "
        "spelled exactly as written ==="
    )
    lines.append(" | ".join(ctx["entity_list"]))
    lines.append(
        f"\nNow write exactly 8 rules for {ctx['title']}. "
        f"Use at least 6 different items from the ENTITY LIST. "
        f"Return JSON only."
    )
    return "\n".join(lines)
```

A real rendered ENTITY LIST for Dune 2, produced by the §5.1 code:

```
Paul Atreides | Chani | Jessica | Stilgar | Gurney Halleck | Feyd-Rautha |
Princess Irulan | Beast Rabban | Emperor | Lady Margot Fenring | Baron Harkonnen |
Reverend Mother Mohiam | Fremen | Arrakis | Bene Gesserit | Sietch Tabr |
Water of Life | Alia | Sardaukar | Shaddam | Shishakli | Kwisatz Haderach |
Shaddam Corrino IV | sandstorm | chosen one | creature | planet | desert |
giant worm | space opera | sand dune | messiah | giant creature | Dune
```

### 4.3 Repair-pass user message (only when validation rejects)

```python
REPAIR_TEMPLATE = """Your previous answer had {n_bad} unusable rules.

REJECTED (with reason):
{rejected_block}

KEPT (do not repeat these, and do not reuse their entities):
{kept_block}

ENTITY LIST items you have NOT used yet:
{unused_entities}

Write exactly {n_needed} REPLACEMENT rules. Each must contain at least one unused
ENTITY LIST item spelled exactly as written, and must be a single countable on-screen
moment. Return JSON only: {{"rules": [{{"team": 0, "description": "..."}}]}}
"""
```

Send at `temperature=0.2`, one attempt only.

### 4.4 Request-body changes in `generate_rules`

```python
json={
    "model": model,
    "messages": messages,
    "temperature": 0.5,          # was 0.85 — high temp drifts to generic priors
    "top_p": 0.9,
    "presence_penalty": 0.3,     # discourages reusing one noun in all 8 rules
    "max_tokens": 900,
    "response_format": {"type": "json_object"},
}
```

Do **not** add `provider.require_parameters: true` — it can exclude the free endpoints.

---

## 5. Deterministic post-validation (real, executed code)

### 5.1 Entity extraction — `backend/app/services/film_context.py` (new)

```python
"""Build a rich, entity-dense film context from TMDB + Wikipedia. No LLM."""
import re
from collections import Counter

_STOP_TITLES = {"Mr", "Mrs", "Ms", "Dr", "Sir", "Lady", "Lord", "Uncle", "Aunt"}

# Roles that are not usable rule anchors ("Guard #2", "Young Woman").
_GENERIC_ROLE = re.compile(
    r"^(uncredited|voice|self|additional|various|young |older |"
    r"(the )?(man|woman|boy|girl|guard|soldier|cop|nurse|doctor|waiter|"
    r"bartender|reporter|pilot|driver|student|villager|party ?goer)\b)",
    re.I,
)

# TMDB keywords that are abstract/meta and make BAD rule anchors.
_ABSTRACT_KW = {
    "sequel", "prequel", "remake", "reboot", "based on novel or book",
    "based on comic", "based on true story", "duringcreditsstinger",
    "aftercreditsstinger", "woman director", "allegorical", "melodramatic",
    "ambiguous", "antagonistic", "power", "destiny", "revenge", "vengeance",
    "distant future", "dystopia", "coming of age", "friendship", "love",
    "betrayal", "survival", "good versus evil", "self-discovery", "redemption",
    "family", "tragedy", "suspense", "cult film", "independent film",
    # mood tags TMDB attaches; observed on Sinners / Kung Fu Panda 4
    "playful", "joyous", "joyful", "enthusiastic", "frightened", "sentimental",
}

_NOISE_PREFIX = re.compile(
    r"^(Some|Many|Most|Several|Both|Other|After|Before|When|While|Following|"
    r"During|Meanwhile|However|Although|Later|Then|But|And|The)\b"
)


def character_entities(cast: list[dict], limit: int = 12) -> list[dict]:
    """Extract real CHARACTER names (NOT actor names) usable as rule anchors."""
    out = []
    for c in sorted(cast, key=lambda x: x.get("order", 999)):
        char = (c.get("character") or "").strip()
        if not char or _GENERIC_ROLE.match(char):
            continue
        char = re.split(r"\s*/\s*|\s*\(", char)[0].strip()   # "X / Y" -> "X"
        if len(char) < 2 or char.lower() in {"himself", "herself"}:
            continue
        out.append({"character": char, "actor": (c.get("name") or "").strip()})
        if len(out) >= limit:
            break
    return out


def plot_proper_nouns(plot: str, known: set[str], limit: int = 14) -> list[str]:
    """Capitalised terms from the Wikipedia plot, minus already-known entities."""
    if not plot:
        return []
    cands = re.findall(
        r"\b(?:[A-Z][\w'\u2019-]+)(?:[ -](?:al-|of |the )?[A-Z][\w'\u2019-]+)*", plot
    )
    counts = Counter()
    for c in cands:
        # Strip possessive ONLY. Do not use rstrip("'s") — it eats plain
        # trailing 's' and turns "Arrakis" into "Arraki".
        c = re.sub(r"['\u2019]s?$", "", c.strip())
        c = _NOISE_PREFIX.sub("", c).strip()      # "Some Fremen" -> "Fremen"
        if len(c) < 4 or c in _STOP_TITLES:
            continue
        low = c.lower()
        if any(k in low or low in k for k in known):
            continue
        counts[c] += 1
    # Single words need 2+ mentions to count as a real proper noun (guards
    # against sentence-initial capitalisation); multiword always counts.
    return [w for w, n in counts.most_common()
            if n >= 2 or " " in w or "-" in w][:limit]


def build_film_context(details: dict, plot: str = "", plot_source: str = "TMDB") -> dict:
    """Assemble the full context dict consumed by _build_user_msg()."""
    cast = details.get("credits", {}).get("cast", [])
    chars = character_entities(cast)
    kws = [k["name"] for k in details.get("keywords", {}).get("keywords", [])]

    known = {c["character"].lower() for c in chars}
    known |= {w for c in chars for w in c["character"].lower().split()}
    nouns = plot_proper_nouns(plot, known)

    coll = (details.get("belongs_to_collection") or {}).get("name")
    good_kws = [k for k in kws if k.lower() not in _ABSTRACT_KW and len(k.split()) <= 2]

    flat = [c["character"] for c in chars] + nouns + good_kws
    if coll:
        flat.append(coll.replace(" Collection", "").strip())

    seen, entity_list = set(), []
    for e in flat:
        if e.lower() not in seen:
            seen.add(e.lower())
            entity_list.append(e)

    return {
        "title": details.get("title") or "",
        "year": (details.get("release_date") or "")[:4],
        "tagline": details.get("tagline") or "",
        "runtime": details.get("runtime") or 0,
        "collection": coll,
        "genres": [g["name"] for g in details.get("genres", [])],
        "keywords": good_kws,
        "characters": chars,
        "plot": (plot or details.get("overview") or "")[:2500],
        "plot_source": plot_source if plot else "TMDB overview",
        "entity_list": entity_list,
    }
```

**Executed output** (real TMDB + real Wikipedia, `movie_id=693134`):

```
CHARACTERS (12):
   Paul Atreides  (played by Timothée Chalamet)
   Chani  (played by Zendaya)
   Jessica  (played by Rebecca Ferguson)
   Stilgar  (played by Javier Bardem)
   Gurney Halleck  (played by Josh Brolin)
   Feyd-Rautha  (played by Austin Butler)
   Princess Irulan  (played by Florence Pugh)
   Beast Rabban  (played by Dave Bautista)
   Emperor  (played by Christopher Walken)
   Lady Margot Fenring  (played by Léa Seydoux)
   Baron Harkonnen  (played by Stellan Skarsgård)
   Reverend Mother Mohiam  (played by Charlotte Rampling)

PLOT PROPER NOUNS (13): ['Fremen', 'Arrakis', 'Bene Gesserit', 'Sietch Tabr',
 'Water of Life', 'Alia', 'Sardaukar', 'Shaddam', 'Shishakli',
 'Kwisatz Haderach', 'Shaddam Corrino IV', 'Outer World', 'More Great Houses']

FLAT ENTITY LIST: 37 items
plot chars=4002  tagline='Long live the fighters.'  runtime=167
```

Two bugs were found and fixed during this run and are already reflected in the code above — worth flagging so they are not reintroduced:

1. `rstrip("'’s")` mangled `Arrakis` → `Arraki`. `rstrip` treats its argument as a *character set*. Use the anchored regex `re.sub(r"['’]s?$", "", c)`.
2. Without `_NOISE_PREFIX` / `_ABSTRACT_KW`, the list contained `Some Fremen`, `Sietch Tabr's`, `melodramatic`, `ambiguous`, `antagonistic`, `power`. `More Great Houses` still slips through — harmless, but a future stoplist entry.

### 5.2 Validator — `backend/app/services/rule_quality.py` (new)

```python
"""Deterministic rule validation. Rejects generic, duplicate and unanchored rules."""
import re
import unicodedata

_BANNED_PATTERNS = [
    # --- kept from the existing _VAGUE_PATTERNS (ongoing states) ---
    r"\bis on (a|his|her|their) path\b",
    r"\bthere('s| is) an? (adventure|journey|story|theme|atmosphere|vibe)\b",
    r"\bany character\b",
    r"\bthe (setting|tone|mood|genre)\b",
    r"\bthroughout\b",
    r"\bin general\b",
    # NOTE: the original r"\bis (present|shown|depicted|portrayed)\b" was too
    # broad — it rejected the perfectly good "A stillsuit is shown in close
    # detail." Narrowed to genuinely always-true state verbs:
    r"\b(is|are) (present|depicted|portrayed|visible)\b",
    r"\bstruggles with\b",
    r"\bfeels\b",
    # --- NEW: generic-filler bans (the actual reported problem) ---
    r"\bmusic (swells|builds|starts|plays)\b",
    r"\bthe (music|score|soundtrack)\b",
    r"\bdramatic pause\b",
    r"\bclose-?up\b",
    r"\bslow[- ]?mo(tion)?\b",
    r"\bscene chang(es|e)\b",
    r"\bchanges? (location|scenes?)\b",
    r"\bcamera (pans|zooms|cuts)\b",
    r"\bestablishing shot\b",
    r"\ba (car|chase) (chase|scene) (starts|begins|happens)\b",
    r"\bsomeone (enters|leaves) (a|the) room\b",
    r"\ba (phone|telephone) (rings|buzzes)\b",
    r"\ba (fight|explosion|gunshot|shootout) (breaks out|happens|occurs)\b",
    r"\b(the )?(main|title|lead) character\b",
    r"\bthe (hero|villain|protagonist|antagonist|bad guy)\b",
    r"\bthe (weather|sky|sun|moon)\b",
    r"\bnew (character|location) (appears|is introduced)\b",
    r"\bsomething (explodes|breaks)\b",
]
_BANNED_RE = [re.compile(p) for p in _BANNED_PATTERNS]

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "drink", "drinks", "sip", "sips", "when", "whenever", "someone", "somebody",
    "anyone", "says", "say", "said", "appears", "appear", "happens", "screen",
    "every", "time", "each", "is", "are", "was", "were", "his", "her", "their",
    "it", "its", "they", "he", "she", "you", "any", "one", "two", "shows", "show",
}


def _norm(s: str) -> str:
    """Lowercase, strip accents, collapse non-alphanumerics to single spaces."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def build_entity_index(entities: list[str]) -> list[tuple[str, set[str]]]:
    """[(normalised_entity, {significant_tokens})].

    A multi-word entity like "Paul Atreides" also matches on "Atreides" alone,
    because the model will often use only one part of the name.
    """
    index = []
    for raw in entities:
        n = _norm(raw)
        if not n:
            continue
        toks = {t for t in n.split() if len(t) >= 4 and t not in _STOPWORDS}
        index.append((n, toks))
    return index


def mentions_entity(description: str, index) -> str | None:
    """Return the matched entity, or None if the rule names nothing real."""
    d_padded = f" {_norm(description)} "
    for full, toks in index:
        if full and f" {full} " in d_padded:
            return full
        for t in toks:
            if f" {t} " in d_padded:
                return t
    return None


def _shingles(text: str, n: int = 3) -> set[str]:
    toks = [t for t in _norm(text).split() if t not in _STOPWORDS]
    if len(toks) < n:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_near_duplicate(desc: str, kept: list[str], threshold: float = 0.5) -> bool:
    s = _shingles(desc)
    return any(_jaccard(s, _shingles(k)) >= threshold for k in kept)


def validate_rules(payload, entities: list[str], min_rules: int = 8,
                   require_entity: bool = True):
    """Return (accepted_rules, rejections) where rejections is [(reason, desc)]."""
    raw = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return [], [("not-a-list", str(payload)[:80])]

    index = build_entity_index(entities)
    accepted, kept_descs, rejections = [], [], []

    for item in raw:
        if not isinstance(item, dict):
            rejections.append(("not-an-object", str(item)[:80]))
            continue
        desc = re.sub(r"\s+", " ", str(item.get("description", ""))).strip()

        if not desc or len(desc) > 110:
            rejections.append(("length", desc[:80]))
            continue
        low = desc.lower()
        hit = next((p.pattern for p in _BANNED_RE if p.search(low)), None)
        if hit:
            rejections.append((f"banned:{hit}", desc))
            continue
        if require_entity and not mentions_entity(desc, index):
            rejections.append(("no-entity", desc))
            continue
        if is_near_duplicate(desc, kept_descs):
            rejections.append(("near-duplicate", desc))
            continue

        accepted.append({"team": 0, "description": desc})
        kept_descs.append(desc)

    if len(accepted) < min_rules:
        return accepted, rejections + [("too-few", f"{len(accepted)}/{min_rules}")]

    accepted = accepted[:8]
    for i, r in enumerate(accepted):
        r["team"] = i % 2          # enforce 4/4 balance regardless of model output
    return accepted, rejections
```

### 5.3 Entity-templated backfill (replaces the generic fallback)

```python
_BACKFILL_TEMPLATES = [
    "{e} appears on screen.",
    'Someone says "{e}".',
    "{e} is mentioned by name.",
    "{e} is shown in a close shot.",
]


def backfill(accepted: list[dict], entities: list[str], target: int = 8) -> list[dict]:
    """Top up to `target` rules with entity-templated rules — never generic ones."""
    kept = [r["description"] for r in accepted]
    out = list(accepted)
    for tpl in _BACKFILL_TEMPLATES:
        for e in entities:
            if len(out) >= target:
                break
            if mentions_entity(e, build_entity_index(kept)):
                continue                     # entity already used by a kept rule
            desc = tpl.format(e=e)
            if len(desc) > 110 or is_near_duplicate(desc, kept):
                continue
            if any(p.search(desc.lower()) for p in _BANNED_RE):
                continue
            out.append({"team": 0, "description": desc})
            kept.append(desc)
        if len(out) >= target:
            break
    out = out[:target]
    for i, r in enumerate(out):
        r["team"] = i % 2
    return out
```

This makes the worst case *still film-specific*: `"Paul Atreides appears on screen."` beats `"Drink whenever the music swells dramatically."` The current `_fallback_rules()` should be deleted, or reduced to a last-resort used only when `entity_list` is empty.

### 5.4 Verified test run

Executed against a GOOD set and a deliberately BAD set with the real 24-entity Dune list:

```
--- GOOD: accepted=8 ---
   team0 | A sandworm appears on screen.
   team1 | Someone calls Paul 'Lisan al-Gaib'.
   team0 | Chani rolls her eyes at the prophecy.
   team1 | Stilgar declares something a sign of the prophecy.
   team0 | Feyd-Rautha kills someone with a blade.
   team1 | A stillsuit is shown in close detail.
   team0 | Jessica speaks in the Bene Gesserit Voice.
   team1 | Someone says the word 'spice'.
   after backfill: 8 rules, teams=[0, 0, 0, 0, 1, 1, 1, 1]

--- BAD: accepted=2 ---
   team0 | A sandworm appears on screen.
   team1 | Someone says the word 'spice'.
   REJECT [banned:\bmusic (swells|builds|starts|plays)\b] Drink when the music swells dramatically.
   REJECT [banned:\bdramatic pause\b] Drink whenever there's a dramatic pause.
   REJECT [banned:\bclose-?up\b] Drink every time there's a close-up shot.
   REJECT [banned:\ba (car|chase) (chase|scene) (starts|begins|happens)\b] Drink when a car chase starts.
   REJECT [banned:\bscene chang(es|e)\b] Drink whenever the scene changes location.
   REJECT [banned:\b(the )?(main|title|lead) character\b] Drink when the main character appears.
   REJECT [near-duplicate] A sandworm appears on the screen!
   REJECT [banned:\bis on (a|his|her|their) path\b] Paul is on his path of revenge.
   after backfill: 8 rules, teams=[0, 0, 0, 0, 1, 1, 1, 1]
      +team0 | Paul Atreides appears on screen.
      +team1 | Chani appears on screen.
      ...
```

All 8 good rules pass; **all 6 of the exact generic rules from the current `_fallback_rules()` list are rejected**; the near-duplicate (`"A sandworm appears on the screen!"` vs `"A sandworm appears on screen."`) is caught; both paths end at exactly 8 rules split 4/4.

---

## 6. Recommended pipeline

```
select_movie(movie_id)
  │
  ├─ TMDB: /movie/{id}?append_to_response=keywords,credits          [1 request]
  ├─ Wikidata SPARQL: P4947 == movie_id  → enwiki title             [1 request, optional]
  ├─ Wikipedia: prop=extracts&explaintext → slice "== Plot ==="     [1 request, optional]
  │     (wrap both wiki calls in try/except + short timeout; on any
  │      failure fall through to Tier B with TMDB overview only)
  │
  ├─ build_film_context(details, plot)  →  entity_list              [no network]
  ├─ LLM pass 1  (temp 0.5, json_object)
  ├─ validate_rules(payload, entity_list)
  │     ├─ 8 accepted → done
  │     └─ <8 → LLM repair pass (temp 0.2, one attempt) → re-validate
  └─ backfill(accepted, entity_list, target=8)                      [always 8, always specific]
```

### Implementation order (highest value first)

1. **`c["name"]` → `c["character"]` in `game.py`.** One-line change, largest single gain. Include the actor name alongside.
2. **Add `keywords` to `append_to_response`** and stop discarding `tagline` / `runtime` / `belongs_to_collection`.
3. **Drop `temperature` 0.85 → 0.5**; add `presence_penalty: 0.3`.
4. **New system prompt** (§4.1) — critically, delete the "prefer genre-level triggers" instruction and the "genre staple" requirement that currently *cause* the filler.
5. **`rule_quality.py` validator + entity backfill**; retire `_fallback_rules()`.
6. **Wikipedia plot enrichment** (Wikidata → extracts). Biggest quality jump for catalogue films; must be fully optional and non-blocking so brand-new releases still work.
7. **Repair pass** — add last; steps 1–5 may make it unnecessary.

### Caching note

Wikidata SPARQL and the 38 KB Wikipedia extract are the two slow calls. Cache the derived context (not the raw article) keyed on `tmdb_id`; it never changes for a released film. This also keeps CineSip well clear of Wikimedia etiquette limits.

---

## 7. Sources

- TMDB — Append To Response: https://developer.themoviedb.org/docs/append-to-response
- TMDB — Rate Limiting (legacy limits disabled 2019-12-16; ~40 req/s soft ceiling): https://developer.themoviedb.org/docs/rate-limiting
- TMDB — Movie Keywords: https://developer.themoviedb.org/reference/movie-keywords
- Wikidata — Property P4947 (TMDB movie ID): https://www.wikidata.org/wiki/Property:P4947
- MediaWiki Action API — `action=parse` / `prop=extracts`: https://www.mediawiki.org/wiki/API:Parse
- Wikimedia APIs — etiquette, ≤200 req/s, unique User-Agent required: https://api.wikimedia.org/wiki/Core_REST_API
- OpenRouter — Structured Outputs (per-endpoint support, `require_parameters`): https://openrouter.ai/docs/features/structured-outputs
- Madaan et al., *Self-Refine: Iterative Refinement with Self-Feedback*: https://arxiv.org/abs/2303.17651
- Geng et al., *Generating Structured Outputs from LMs: Benchmark and Studies*: https://arxiv.org/html/2501.10868v1
- Tam et al., *Let Me Speak Freely? Impact of Format Restrictions on LLM Performance*: https://arxiv.org/html/2408.02442v1
- *Navigating the Impact of Structured Output Format on LLM Performance*: https://arxiv.org/html/2509.21791v1
