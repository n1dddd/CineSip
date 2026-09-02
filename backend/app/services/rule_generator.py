import os
import json
import re
import httpx

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Cheap-first: free Llama 4 Maverick, then free Gemma, then paid-but-pennies Gemini Flash.
OPENROUTER_MODELS = [
    m.strip()
    for m in os.getenv(
        "OPENROUTER_MODELS",
        "meta-llama/llama-4-maverick:free,google/gemma-3-27b-it:free,google/gemini-2.5-flash",
    ).split(",")
    if m.strip()
]

SYSTEM_PROMPT = """You write drinking-game rules for a movie night.

CRITICAL GROUNDING RULE: You are given the movie's REAL plot summary, genres and cast
from TMDB. Base every rule ONLY on what appears in that provided context, or on
things that are visually obvious for the stated genre. NEVER invent specific plot
points, character names, or quotes that are not present in the provided context.
If the context is thin, prefer genre-level observable triggers (e.g. "a car chase
starts", "someone pours a drink") over invented specifics. Do not guess at scenes.

CRITICAL PLAYABILITY RULE: Every rule must be a DISCRETE, COUNTABLE MOMENT that a
viewer can point at the screen and call out the instant it happens. A rule is only
valid if a room full of drunk people would instantly agree "yes, that just happened".

GOOD (countable, has a clear instant):
- "A sandworm appears on screen."
- "Paul has a vision of the future."
- "Someone says the word 'Fremen'."
BAD (a mood, a theme, or always-true — never write these):
- "When Paul is on his path of revenge."   <- ongoing state, not a moment
- "If there's an adventure in the sci-fi setting."  <- always true
- "If you see any character from the main cast."   <- constantly true
Never write a rule beginning with "When <character> is..." describing a state.
Never write a rule that is true for most of the runtime.

Output STRICT JSON only, no markdown fences, matching exactly:
{"rules": [{"team": 0, "description": "..."}]}

Requirements:
- Exactly 8 rules.
- Alternate team 0 and team 1 so each team gets 4.
- Each description is one short sentence, under 90 characters, phrased as an
  event that happens: "X appears", "someone says Y", "Z happens on screen".
- Mix these kinds: a spoken word/catchphrase, a recurring visual, a specific
  character action, a genre staple.
- Fun and social. No slurs, no dangerous instructions ("finish the bottle" etc)."""


def _build_user_msg(movie_title: str, genre: str, plot_summary: str) -> str:
    return (
        f"Movie: {movie_title}\n"
        f"Genres: {genre or 'unknown'}\n"
        f"TMDB plot summary and cast (this is your ONLY source of facts):\n"
        f"{plot_summary or '(no summary available — use genre-level triggers only)'}"
    )


def _extract_json(content: str) -> dict | None:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


# Phrasings that describe an ongoing state or are true most of the runtime.
# A rule matching these is unplayable — nobody can agree on when to drink.
_VAGUE_PATTERNS = [
    r"\bis on (a|his|her|their) path\b",
    r"\bthere('s| is) an? (adventure|journey|story|theme|atmosphere|vibe)\b",
    r"\bany character\b",
    r"\bthe (setting|tone|mood|genre)\b",
    r"\bthroughout\b",
    r"\bin general\b",
    r"\bis (present|shown|depicted|portrayed)\b",
    r"\bstruggles with\b",
    r"\bfeels\b",
]


def _is_playable(description: str) -> bool:
    """Reject rules describing a state/theme rather than a spottable moment."""
    d = description.lower()
    return not any(re.search(p, d) for p in _VAGUE_PATTERNS)


def _validate(payload: dict | list) -> list[dict] | None:
    """Coerce model output into [{team:int, description:str}] or reject it."""
    raw = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(raw, list) or not raw:
        return None

    cleaned: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description", "")).strip()
        if not desc or len(desc) > 200:
            continue
        if not _is_playable(desc):
            continue
        try:
            team = int(item.get("team", i % 2))
        except (TypeError, ValueError):
            team = i % 2
        cleaned.append({"team": 0 if team == 0 else 1, "description": desc})

    if len(cleaned) < 6:
        return None

    # Force balanced teams regardless of what the model returned.
    for i, rule in enumerate(cleaned):
        rule["team"] = i % 2
    return cleaned[:8]


async def generate_rules(
    movie_title: str, genre: str = "", plot_summary: str = ""
) -> list[dict]:
    """Generate grounded drinking-game rules from real TMDB context.

    Tries each configured model in order; falls back to generic rules only if
    every model fails. Never raises — a party app must always return something.
    """
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("your_"):
        return _fallback_rules(movie_title)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_msg(movie_title, genre, plot_summary)},
    ]

    async with httpx.AsyncClient(timeout=45.0) as client:
        for model in OPENROUTER_MODELS:
            try:
                resp = await client.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://cinesip.dseniv.cc",
                        "X-Title": "CineSip",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.85,
                        "max_tokens": 900,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = _extract_json(content)
                if parsed is None:
                    continue
                rules = _validate(parsed)
                if rules:
                    return rules
            except Exception:
                continue

    return _fallback_rules(movie_title)


def _fallback_rules(movie_title: str) -> list[dict]:
    """Generic but always-playable rules when the LLM is unavailable."""
    generic = [
        "Drink when the title character appears on screen.",
        "Drink whenever there's a dramatic pause.",
        "Drink every time someone enters a room.",
        "Drink whenever the music swells dramatically.",
        "Drink every time there's a close-up shot.",
        "Drink whenever a phone rings or buzzes.",
        "Drink when a character pours or holds a drink.",
        "Drink whenever the scene changes location.",
    ]
    return [{"team": i % 2, "description": d} for i, d in enumerate(generic)]
