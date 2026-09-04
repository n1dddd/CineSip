"""Generate film-specific drinking-game rules from real fetched film data.

Pipeline: entity-anchored prompt -> LLM pass 1 -> deterministic validation ->
targeted repair pass (only the rejected rules) -> entity-templated backfill.

The model never supplies film facts; it only phrases events using the ENTITY
LIST that `film_context` derived from TMDB and Wikipedia.
"""

import asyncio
import json
import logging
import os
import re

import httpx

from app.services.rule_quality import backfill, balance_teams, validate_rules

log = logging.getLogger("cinesip.rules")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_DEFAULT_MODELS = (
    "z-ai/glm-5.2:free,"
    "minimax/minimax-m3:free,"
    "google/gemma-4-31b-it:free,"
    "google/gemini-2.5-flash"
)


def _api_key() -> str:
    """Read lazily so .env load order cannot silently disable the LLM path."""
    return os.getenv("OPENROUTER_API_KEY", "")


def _models() -> list[str]:
    return [
        m.strip()
        for m in os.getenv("OPENROUTER_MODELS", _DEFAULT_MODELS).split(",")
        if m.strip()
    ]


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
Every capitalised name you write MUST appear in the CHARACTERS list, the ENTITY LIST, or the
plot summary. If you remember a character from an earlier film in the series who is not
listed, do NOT use them — a rule naming anyone not listed is thrown away.

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
- Each description is ONE short sentence UNDER 90 CHARACTERS, phrased as an event that
  happens: "X appears", "someone says 'Y'", "X does Z". Aim for 5-10 words.
- ONE event per rule. Never chain two events with "and", "then", "while", "after" or
  "before" — "Paul rides a worm and the Fremen cheer" is two moments and is rejected.
- Never write a rule that can only happen ONCE ("for the first time", "in the final
  scene"). A good rule can fire several times across the film.
- Use at least 6 DIFFERENT items from the ENTITY LIST across the 8 rules. Do not build
  every rule around the same character.
- Mix these kinds, all still entity-anchored: a named character's signature action; a named
  object or place appearing; a specific word or name being spoken aloud; a recurring visual
  motif from the keywords.
- Fun and social. No slurs. No dangerous instructions ("finish the bottle", "down it").
"""

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


def build_user_msg(ctx: dict) -> str:
    """Render the film context into the entity-anchored user message."""
    lines = [f"FILM: {ctx.get('title', '')} ({ctx.get('year', '')})"]
    if ctx.get("tagline"):
        lines.append(f"TAGLINE: {ctx['tagline']}")
    if ctx.get("runtime"):
        lines.append(f"RUNTIME: {ctx['runtime']} minutes")
    if ctx.get("director"):
        lines.append(f"DIRECTOR: {ctx['director']}")
    if ctx.get("collection"):
        lines.append(f"FRANCHISE: {ctx['collection']}")
    if ctx.get("genres"):
        lines.append(f"GENRES: {', '.join(ctx['genres'])}")
    if ctx.get("keywords"):
        lines.append(
            "TMDB KEYWORDS (real motifs in this film): "
            f"{', '.join(ctx['keywords'][:20])}"
        )

    if ctx.get("characters"):
        lines.append("\nCHARACTERS (use these NAMES, not the actors'):")
        for c in ctx["characters"]:
            actor = f"  [played by {c['actor']}]" if c.get("actor") else ""
            lines.append(f"  - {c['character']}{actor}")

    if ctx.get("plot"):
        lines.append(
            f"\nPLOT SUMMARY (source: {ctx.get('plot_source', 'TMDB')} "
            "— this and the lists above are your ONLY source of facts):"
        )
        lines.append(ctx["plot"])

    lines.append(
        "\n=== ENTITY LIST — every rule MUST contain at least one of these, "
        "spelled exactly as written ==="
    )
    lines.append(" | ".join(ctx.get("entity_list", [])))
    lines.append(
        f"\nNow write exactly 8 rules for {ctx.get('title', 'this film')}. "
        "Use at least 6 different items from the ENTITY LIST. Return JSON only."
    )
    return "\n".join(lines)


def _extract_json(content: str) -> dict | list | None:
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Non-greedy so trailing model chatter after the object does not break it.
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
    return None


async def _call_model(
    client: httpx.AsyncClient, model: str, messages: list[dict], temperature: float
) -> dict | list | None:
    """One OpenRouter call. Returns parsed JSON or None; logs every failure mode.

    Retries on 429/5xx — free-tier endpoints rate-limit aggressively, and a
    single 429 previously meant silently serving generic rules.
    """
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(2 * (2 ** (attempt - 1)))  # 2s, 4s
        try:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cinesip.dseniv.cc",
                    "X-Title": "CineSip",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "top_p": 0.9,
                    "presence_penalty": 0.3,
                    "max_tokens": 1400,
                },
            )
        except httpx.HTTPError as exc:
            log.warning(
                "rulegen: %s transport error (attempt %d): %s: %s",
                model, attempt + 1, type(exc).__name__, exc,
            )
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            log.warning(
                "rulegen: %s HTTP %s (attempt %d), retrying: %s",
                model, resp.status_code, attempt + 1, resp.text[:200],
            )
            continue
        if resp.status_code != 200:
            log.warning("rulegen: %s HTTP %s: %s", model, resp.status_code, resp.text[:300])
            return None

        try:
            body = resp.json()
        except ValueError:
            log.warning("rulegen: %s returned non-JSON body: %s", model, resp.text[:300])
            return None

        # OpenRouter can return HTTP 200 with an error body instead of choices.
        if "error" in body and "choices" not in body:
            log.warning("rulegen: %s error body: %s", model, str(body["error"])[:300])
            return None
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            log.warning("rulegen: %s malformed response: %s", model, str(body)[:300])
            return None

        # Reasoning models sometimes put everything in `reasoning` and leave
        # `content` null; the JSON is usually still in there.
        content = message.get("content") or message.get("reasoning") or ""
        parsed = _extract_json(content)
        if parsed is None:
            log.warning("rulegen: %s unparseable content: %s", model, str(content)[:300])
        return parsed

    log.warning("rulegen: %s exhausted retries", model)
    return None


async def _repair(
    client: httpx.AsyncClient,
    model: str,
    base_messages: list[dict],
    accepted: list[dict],
    rejections: list[tuple[str, str]],
    entities: list[str],
    plot: str = "",
) -> list[dict]:
    """One targeted repair pass replacing only the rejected rules."""
    from app.services.rule_quality import build_entity_index, mentions_entity

    n_needed = 8 - len(accepted)
    if n_needed <= 0:
        return accepted

    kept_index = build_entity_index([r["description"] for r in accepted])
    unused = [e for e in entities if not mentions_entity(e, kept_index)][:20]
    rejected_block = "\n".join(
        f"  - {desc}   [reason: {reason}]" for reason, desc in rejections[:8]
    ) or "  (none)"
    kept_block = "\n".join(f"  - {r['description']}" for r in accepted) or "  (none)"

    messages = base_messages + [
        {"role": "assistant", "content": json.dumps({"rules": accepted})},
        {
            "role": "user",
            "content": REPAIR_TEMPLATE.format(
                n_bad=len(rejections),
                rejected_block=rejected_block,
                kept_block=kept_block,
                unused_entities=", ".join(unused) or "(none left)",
                n_needed=n_needed,
            ),
        },
    ]

    parsed = await _call_model(client, model, messages, temperature=0.2)
    if parsed is None:
        return accepted

    extra, extra_rejects = validate_rules(parsed, entities, plot=plot)
    log.info(
        "rulegen: repair on %s produced %d/%d usable (%d rejected)",
        model, len(extra), n_needed, len(extra_rejects),
    )
    seen = {r["description"].lower() for r in accepted}
    for r in extra:
        if len(accepted) >= 8:
            break
        if r["description"].lower() not in seen:
            accepted.append(r)
            seen.add(r["description"].lower())
    return accepted


async def generate_rules(ctx: dict) -> list[dict]:
    """Generate 8 grounded, film-specific rules. Never raises.

    `ctx` is the dict produced by film_context.build_film_context().
    Always returns exactly 8 balanced rules — entity-templated at worst.
    """
    entities = ctx.get("entity_list", [])
    plot = ctx.get("plot", "")
    title = ctx.get("title", "the film")

    if not _api_key() or _api_key().startswith("your_"):
        log.error("rulegen: OPENROUTER_API_KEY missing — serving backfill rules")
        return _last_resort(ctx)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_msg(ctx)},
    ]

    log.info(
        "rulegen: start title=%r entities=%d plot=%s(%d chars) chars=%d keywords=%d",
        title, len(entities), ctx.get("plot_source"), len(ctx.get("plot", "")),
        len(ctx.get("characters", [])), len(ctx.get("keywords", [])),
    )

    best: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in _models():
            parsed = await _call_model(client, model, messages, temperature=0.5)
            if parsed is None:
                continue

            accepted, rejections = validate_rules(parsed, entities, plot=plot)
            log.info(
                "rulegen: %s pass1 accepted=%d rejected=%d reasons=%s",
                model, len(accepted), len(rejections),
                [r for r, _ in rejections][:8],
            )

            if len(accepted) < 8 and accepted:
                accepted = await _repair(
                    client, model, messages, accepted, rejections, entities, plot
                )

            if len(accepted) > len(best):
                best = accepted
            if len(best) >= 8:
                break

    if len(best) >= 8:
        log.info("rulegen: done title=%r 8 model-written rules", title)
        return balance_teams(best[:8])

    filled = backfill(best, entities, target=8)
    log.warning(
        "rulegen: title=%r only %d model rules usable — backfilled to %d",
        title, len(best), len(filled),
    )
    return filled if len(filled) == 8 else _last_resort(ctx)


def _last_resort(ctx: dict) -> list[dict]:
    """Absolute floor: entity-templated if any entity exists, else generic."""
    entities = ctx.get("entity_list", [])
    if entities:
        filled = backfill([], entities, target=8)
        if len(filled) == 8:
            return filled
    title = ctx.get("title") or "the film"
    generic = [
        f"A character from {title} is named out loud.",
        "Someone pours or holds a drink.",
        "Two characters argue with each other.",
        "Someone laughs out loud on screen.",
        "A character shouts another character's name.",
        "Someone eats or drinks on screen.",
        "A character lies to another character.",
        "Someone leaves without saying goodbye.",
    ]
    return balance_teams([{"team": 0, "description": d} for d in generic])
