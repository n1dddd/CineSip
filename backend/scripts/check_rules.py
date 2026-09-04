"""Manual end-to-end check of the rule pipeline against live TMDB/Wikipedia/OpenRouter."""
import asyncio
import logging
import sys

from pathlib import Path

from dotenv import load_dotenv

# backend/.env holds placeholder keys; the real ones live in the repo-root .env
# (which docker-compose passes through as environment vars in production).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

from app.services import film_context, movie_search, rule_generator, wiki_plot  # noqa: E402

FILMS = [
    (693134, "Dune: Part Two"),
    (1233413, "Sinners"),
    (152601, "Her"),
]


async def one(movie_id: int, title: str) -> None:
    print(f"\n{'=' * 70}\n{title}  (tmdb {movie_id})\n{'=' * 70}")
    details = await movie_search.get_movie_details(movie_id)
    if "error" in details:
        print("TMDB ERROR:", details["error"])
        return
    plot = await wiki_plot.get_plot(movie_id)
    ctx = film_context.build_film_context(details, plot)
    print(f"tagline={ctx['tagline']!r} runtime={ctx['runtime']} director={ctx['director']!r}")
    print(f"plot_source={ctx['plot_source']} plot_chars={len(ctx['plot'])}")
    print(f"characters({len(ctx['characters'])}): "
          f"{', '.join(c['character'] for c in ctx['characters'])}")
    print(f"keywords({len(ctx['keywords'])}): {', '.join(ctx['keywords'][:15])}")
    print(f"ENTITY LIST ({len(ctx['entity_list'])}): {' | '.join(ctx['entity_list'])}")
    rules = await rule_generator.generate_rules(ctx)
    print(f"\n--- {len(rules)} RULES ---")
    for r in rules:
        print(f"  team{r['team']} | {r['description']}")


async def main() -> None:
    for mid, title in FILMS:
        await one(mid, title)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
