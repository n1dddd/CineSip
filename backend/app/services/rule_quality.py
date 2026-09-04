"""Deterministic rule validation. Rejects generic, duplicate and unanchored rules.

The model is *told* to anchor every rule to a real entity from the film; this
module is what makes that instruction real. Free/small models comply with
prompt constraints unreliably, so the objective check lives in code.
"""

import re
import unicodedata

_BANNED_PATTERNS = [
    # --- ongoing states / always-true (a rule must be a countable instant) ---
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
    # --- generic filler: the actual reported problem ---
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
    # --- unrepeatable / narrated-plot-beat phrasings ---
    # A rule that can only ever fire once is not a drinking-game rule, and
    # "X does A and then Y does B" is a plot summary, not a callable moment.
    r"\bfor the first time\b",
    r"\bat the (end|start|beginning) of the (film|movie)\b",
    r"\bin the (final|opening|last|first) (scene|act|sequence)\b",
]
_BANNED_RE = [re.compile(p) for p in _BANNED_PATTERNS]

# Safety: the prompt bans these, but nothing previously validated them.
_UNSAFE_PATTERNS = [
    r"\bfinish (the|your) (bottle|drink|glass)\b",
    r"\bdown (it|the|your)\b",
    r"\bchug\b",
    r"\bshotgun\b",
    r"\bshots?\s+each\b",
    r"\bdrive\b",
    r"\bwhole bottle\b",
]
_UNSAFE_RE = [re.compile(p) for p in _UNSAFE_PATTERNS]

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
    index: list[tuple[str, set[str]]] = []
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


# Capitalised words that are ordinary English, not film-specific proper nouns.
_COMMON_CAPS = {
    "a", "an", "the", "drink", "sip", "someone", "somebody", "anyone", "when",
    "whenever", "every", "each", "if", "after", "before", "during", "while",
    "any", "two", "three", "his", "her", "their", "he", "she", "they", "it",
    "one", "another", "both", "there", "this", "that", "these", "those",
    "no", "not", "and", "or", "but", "for", "with", "on", "in", "at", "to",
}


def unknown_proper_nouns(description: str, index, plot: str = "") -> list[str]:
    """Capitalised words in a rule that appear nowhere in the film's real data.

    This is the anti-hallucination gate. The entity check alone is not enough:
    "Paul Atreides defeats Jamis in a duel" contains a real entity (Paul) but
    invents Jamis, who is absent from this film's data entirely. Any capitalised
    word must be traceable to the entity list or the fetched plot text.
    """
    plot_norm = f" {_norm(plot)} " if plot else ""
    unknown = []
    # Skip the first word — sentence-initial capitalisation carries no signal.
    for word in re.findall(r"(?<!^)\b([A-Z][a-zA-Z'\u2019-]{2,})", description):
        n = _norm(word)
        if not n or n in _COMMON_CAPS or n in _STOPWORDS:
            continue
        if mentions_entity(word, index):
            continue
        if plot_norm and f" {n} " in plot_norm:
            continue
        unknown.append(word)
    return unknown


# Two independent clauses joined by "and"/"then"/"while" describe a sequence,
# not one instant a room can call out together.
_COMPOUND_RE = re.compile(
    r"\b(?:and then|, and\b|,? then\b|\bwhile\b|\bafter\b|\bbefore\b)"
    # "and" + a new subject = a second clause ("...and the Fremen cheer"),
    # unlike a bare list ("Delta Slim and Pearline sing").
    r"|\band (?:the|a|an|his|her|their|they|someone|everyone|it)\b"
)


def _is_compound(description: str) -> bool:
    """True if the rule chains multiple events instead of naming one moment."""
    d = description.lower()
    if _COMPOUND_RE.search(d):
        return True
    # More than one "and" almost always means a narrated sequence.
    return d.count(" and ") > 1


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


def validate_rules(
    payload,
    entities: list[str],
    require_entity: bool = True,
    plot: str = "",
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Return (accepted_rules, rejections) where rejections is [(reason, desc)].

    Unlike the old validator this does NOT throw away a partial set: callers
    keep whatever passed and top it up via the repair pass or backfill. Five
    good film-specific rules are worth more than eight generic ones.
    """
    raw = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return [], [("not-a-list", str(payload)[:80])]

    index = build_entity_index(entities)
    accepted: list[dict] = []
    kept_descs: list[str] = []
    rejections: list[tuple[str, str]] = []

    for item in raw:
        if not isinstance(item, dict):
            rejections.append(("not-an-object", str(item)[:80]))
            continue
        desc = re.sub(r"\s+", " ", str(item.get("description", ""))).strip()

        # 90 chars is the prompt's own limit and roughly what fits on one
        # phone line in a dark room. The old 200 allowed narrated plot beats.
        if not desc or len(desc) > 90:
            rejections.append(("length", desc[:80]))
            continue
        if _is_compound(desc):
            rejections.append(("compound-event", desc))
            continue
        low = desc.lower()
        unsafe = next((p.pattern for p in _UNSAFE_RE if p.search(low)), None)
        if unsafe:
            rejections.append((f"unsafe:{unsafe}", desc))
            continue
        hit = next((p.pattern for p in _BANNED_RE if p.search(low)), None)
        if hit:
            rejections.append((f"banned:{hit}", desc))
            continue
        if require_entity and index and not mentions_entity(desc, index):
            rejections.append(("no-entity", desc))
            continue
        invented = unknown_proper_nouns(desc, index, plot)
        if invented:
            rejections.append((f"invented-name:{','.join(invented)}", desc))
            continue
        if is_near_duplicate(desc, kept_descs):
            rejections.append(("near-duplicate", desc))
            continue

        accepted.append({"team": 0, "description": desc})
        kept_descs.append(desc)

    return accepted[:8], rejections


_BACKFILL_TEMPLATES = [
    "{e} appears on screen.",
    'Someone says "{e}".',
    "{e} is mentioned by name.",
    "{e} is shown in a wide shot.",
]


def backfill(accepted: list[dict], entities: list[str], target: int = 8) -> list[dict]:
    """Top up to `target` rules with entity-templated rules — never generic ones.

    Worst case stays film-specific: "Paul Atreides appears on screen." beats
    "Drink whenever the music swells dramatically."
    """
    kept = [r["description"] for r in accepted]
    out = [dict(r) for r in accepted]
    for tpl in _BACKFILL_TEMPLATES:
        for e in entities:
            if len(out) >= target:
                break
            if mentions_entity(e, build_entity_index(kept)):
                continue  # entity already used by a kept rule
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
    return balance_teams(out)


def balance_teams(rules: list[dict]) -> list[dict]:
    """Force an even 4/4 split. An odd count would render as '3.5 per team'."""
    if len(rules) % 2:
        rules = rules[:-1]
    half = len(rules) // 2
    for i, r in enumerate(rules):
        r["team"] = 0 if i < half else 1
    return rules
