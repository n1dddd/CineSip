"""Fetch a film's real Plot section from Wikipedia. Free, no API key.

TMDB's `overview` is one sentence (~300 chars). Wikipedia's Plot section is
~4000 chars of the actual events, which is where the film-specific nouns that
make a rule feel like *this* movie actually live.

Strictly optional and non-blocking: any failure (brand-new release with no
article, network hiccup, Wikimedia rate-limit) falls through to an empty string
and the caller degrades to the TMDB overview. Never raises.
"""

import logging
import re
from urllib.parse import unquote

import httpx

log = logging.getLogger("cinesip.wiki")

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Wikimedia require a unique identifying User-Agent; generic/absent UAs get blocked.
_UA = "CineSip/1.0 (https://cinesip.dseniv.cc; rules-generator)"

# P4947 is the Wikidata property for "TMDB movie ID" — resolving through it
# avoids title-guessing collisions like Dune (1984) vs Dune (2021).
_SPARQL_TMPL = """SELECT ?enwiki WHERE {
  ?item wdt:P4947 "%s".
  ?enwiki schema:about ?item;
          schema:isPartOf <https://en.wikipedia.org/>.
} LIMIT 1"""

_PLOT_RE = re.compile(
    r"\n== (?:Plot|Synopsis|Premise|Plot summary) ==\n(.*?)(?=\n== )",
    re.S | re.I,
)

# Simple in-process cache. A released film's plot never changes, and this keeps
# CineSip comfortably clear of Wikimedia etiquette limits.
_cache: dict[int, str] = {}


async def _resolve_title(client: httpx.AsyncClient, tmdb_id: int) -> str:
    resp = await client.get(
        WIKIDATA_SPARQL,
        params={"format": "json", "query": _SPARQL_TMPL % tmdb_id},
        headers={"User-Agent": _UA, "Accept": "application/sparql-results+json"},
    )
    resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    if not bindings:
        return ""
    url = bindings[0].get("enwiki", {}).get("value", "")
    return unquote(url.rsplit("/", 1)[-1]).replace("_", " ") if url else ""


async def _fetch_plot(client: httpx.AsyncClient, title: str) -> str:
    resp = await client.get(
        WIKIPEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "titles": title,
        },
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return ""
    extract = next(iter(pages.values()), {}).get("extract", "")
    if not extract:
        return ""
    match = _PLOT_RE.search(extract)
    return match.group(1).strip() if match else ""


async def get_plot(tmdb_id: int, http_timeout: float = 8.0) -> str:  # noqa: ASYNC109
    """Return the Wikipedia Plot section for a TMDB movie id, or '' on any failure."""
    if tmdb_id in _cache:
        return _cache[tmdb_id]
    try:
        async with httpx.AsyncClient(timeout=http_timeout, follow_redirects=True) as client:
            title = await _resolve_title(client, tmdb_id)
            if not title:
                log.info("wiki: no enwiki article for tmdb_id=%s", tmdb_id)
                _cache[tmdb_id] = ""
                return ""
            plot = await _fetch_plot(client, title)
            log.info("wiki: tmdb_id=%s title=%r plot_chars=%d", tmdb_id, title, len(plot))
            _cache[tmdb_id] = plot
            return plot
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("wiki: lookup failed for tmdb_id=%s: %s: %s",
                    tmdb_id, type(exc).__name__, exc)
        return ""
    except Exception:
        log.exception("wiki: unexpected failure for tmdb_id=%s", tmdb_id)
        return ""
