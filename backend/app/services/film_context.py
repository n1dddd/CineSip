"""Build a rich, entity-dense film context from TMDB (+ optional Wikipedia plot).

No LLM involved. This module turns raw TMDB JSON into the exact vocabulary the
rule generator is allowed to draw on: real CHARACTER names, real proper nouns
lifted from the plot, and concrete TMDB keywords.

Why this exists: the model was previously handed the 1-sentence TMDB `overview`
plus a list of ACTOR names, which contains almost nothing it can build a
film-specific rule out of. Given "Timothée Chalamet" it cannot write "Paul
Atreides has a vision" — so it fell back on training priors ("the music swells").
"""

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

# TMDB keywords that are abstract/meta and make BAD rule anchors. A rule built
# on "revenge" or "dystopia" is exactly the generic filler we are eliminating.
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

# Sentence-initial words that get swept into a capitalised-phrase match.
_NOISE_PREFIX = re.compile(
    r"^(Some|Many|Most|Several|Both|Other|After|Before|When|While|Following|"
    r"During|Meanwhile|However|Although|Later|Then|But|And|The|More)\b"
)


def character_entities(cast: list[dict], limit: int = 12) -> list[dict]:
    """Extract real CHARACTER names (NOT actor names) usable as rule anchors."""
    out: list[dict] = []
    for c in sorted(cast, key=lambda x: x.get("order", 999)):
        char = (c.get("character") or "").strip()
        if not char or _GENERIC_ROLE.match(char):
            continue
        char = re.split(r"\s*/\s*|\s*\(", char)[0].strip()  # "X / Y" -> "X"
        if len(char) < 2 or char.lower() in {"himself", "herself"}:
            continue
        out.append({"character": char, "actor": (c.get("name") or "").strip()})
        if len(out) >= limit:
            break
    return out


def plot_proper_nouns(plot: str, known: set[str], limit: int = 14) -> list[str]:
    """Capitalised terms from the plot text, minus already-known entities."""
    if not plot:
        return []
    cands = re.findall(
        r"\b(?:[A-Z][\w'\u2019-]+)(?:[ -](?:al-|of |the )?[A-Z][\w'\u2019-]+)*", plot
    )
    counts: Counter[str] = Counter()
    for raw in cands:
        # Strip possessive ONLY. Do not use rstrip("'s") — it treats its
        # argument as a CHARACTER SET and turns "Arrakis" into "Arraki".
        c = re.sub(r"['\u2019]s?$", "", raw.strip())
        c = _NOISE_PREFIX.sub("", c).strip()  # "Some Fremen" -> "Fremen"
        if len(c) < 4 or c in _STOP_TITLES:
            continue
        low = c.lower()
        if any(k in low or low in k for k in known):
            continue
        counts[c] += 1
    # Single words need 2+ mentions to count as a real proper noun (guards
    # against sentence-initial capitalisation); multiword always counts.
    return [
        w for w, n in counts.most_common() if n >= 2 or " " in w or "-" in w
    ][:limit]


def build_film_context(details: dict, plot: str = "", plot_source: str = "Wikipedia") -> dict:
    """Assemble the context dict consumed by the rule generator's user message."""
    cast = details.get("credits", {}).get("cast", []) or []
    chars = character_entities(cast)
    kws = [k.get("name", "") for k in (details.get("keywords", {}) or {}).get("keywords", [])]

    known = {c["character"].lower() for c in chars}
    known |= {w for c in chars for w in c["character"].lower().split()}
    nouns = plot_proper_nouns(plot, known)

    coll = (details.get("belongs_to_collection") or {}).get("name")
    good_kws = [
        k for k in kws if k and k.lower() not in _ABSTRACT_KW and len(k.split()) <= 2
    ]

    director = next(
        (
            c.get("name", "")
            for c in (details.get("credits", {}).get("crew", []) or [])
            if c.get("job") == "Director"
        ),
        "",
    )

    flat = [c["character"] for c in chars] + nouns + good_kws
    if coll:
        flat.append(coll.replace(" Collection", "").strip())

    seen: set[str] = set()
    entity_list: list[str] = []
    for e in flat:
        if e and e.lower() not in seen:
            seen.add(e.lower())
            entity_list.append(e)

    return {
        "title": details.get("title") or "",
        "year": (details.get("release_date") or "")[:4],
        "tagline": details.get("tagline") or "",
        "runtime": details.get("runtime") or 0,
        "collection": coll,
        "director": director,
        "genres": [g.get("name", "") for g in details.get("genres", []) or []],
        "keywords": good_kws,
        "characters": chars,
        "plot": (plot or details.get("overview") or "")[:2500],
        "plot_source": plot_source if plot else "TMDB overview",
        "entity_list": entity_list,
    }
