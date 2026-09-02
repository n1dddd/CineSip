import os
import httpx
import json

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

RULE_PROMPT = """You are a fun drinking-game rule generator. Given a movie title, genre, and plot summary, generate 5-7 creative drinking-game rules for watching this movie.

Each rule should be a single sentence. Alternate rules between "Team 0" and "Team 1" so each team gets roughly equal rules.

Return ONLY a JSON array of objects with "team" (0 or 1) and "description" (string). No other text.
Example:
[{"team": 0, "description": "Drink every time someone says the main character's name."},
 {"team": 1, "description": "Drink whenever there's an explosion."}]

Movie: {movie_title}
Genre: {genre}
Plot: {plot_summary}
"""


async def generate_rules(
    movie_title: str, genre: str = "", plot_summary: str = ""
) -> list[dict]:
    """Use OpenRouter LLM to generate drinking game rules for a movie."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("your_"):
        return _fallback_rules(movie_title)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": RULE_PROMPT.format(
                                movie_title=movie_title,
                                genre=genre,
                                plot_summary=plot_summary,
                            ),
                        }
                    ],
                    "temperature": 0.9,
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3].strip()
            return json.loads(content)
        except Exception:
            return _fallback_rules(movie_title)


def _fallback_rules(movie_title: str) -> list[dict]:
    """Generate simple fallback rules when LLM is unavailable."""
    return [
        {"team": 0, "description": f"Drink every time a character says '{movie_title[:5]}'."},
        {"team": 1, "description": "Drink whenever there's a dramatic pause."},
        {"team": 0, "description": "Drink every time someone enters a room."},
        {"team": 1, "description": "Drink whenever music swells dramatically."},
        {"team": 0, "description": "Drink every time there's a close-up shot."},
        {"team": 1, "description": "Drink whenever a phone rings or buzzes."},
    ]