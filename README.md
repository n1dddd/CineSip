# CineSip

Team drinking game for movie nights. Split into two teams, pick a film, and each
team gets rules drawn from that film's **actual** plot — tap a rule when it
happens on screen.

Live: [cinesip.dseniv.cc](https://cinesip.dseniv.cc)

## How it works

```
TMDB (real plot, cast, genres)  →  LLM (wording only)  →  team rule sets
```

The LLM is never asked what it *remembers* about a film. Real TMDB data is
fetched first and passed as the only permitted source of facts, so brand-new
releases work and rules can't be hallucinated. A validator then rejects rules
that aren't discrete, countable moments — no "when the hero is on a journey".

Example, generated live for *Blade Runner 2049*:

```
[Amber]  Officer K uses his LAPD spinner car.
[Teal]   Someone says the term 'blade runner'.
[Amber]  Rick Deckard appears on screen.
```

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + SQLite (WAL) | Zero ops; a party game does not need Postgres |
| Frontend | React 19 + Vite + Tailwind v4 | Mobile-first SPA |
| State | Zustand + server polling | Server is the source of truth for scores |
| Films | TMDB API v3 | Free, current, well documented |
| Rules | OpenRouter (free-model chain) | Costs ~nothing per game |
| Deploy | Docker Compose + nginx | Single box, one command |

## Local development

```bash
git clone <repo> && cd cinesip
cp .env.example .env        # add TMDB_API_KEY and OPENROUTER_API_KEY

# backend — http://localhost:8000
cd backend && uv run uvicorn app.main:app --reload

# frontend — http://localhost:5173 (proxies /api to :8000)
cd frontend && npm install && npm run dev
```

## Deploy

```bash
docker compose up -d --build
```

On the VPS, `deploy.sh` also stops the host nginx (it competes with the
container for port 80) and health-checks afterwards.

## Design constraints

This app is used **in a dark room, mid-film, by people who are drinking.** That
is the whole design brief:

- No gradients or glow effects — they light the room and wreck night vision
- Warm near-black surfaces, cream text (never pure white) to cut glare
- Teams are **Amber vs Teal** — the cinema colour grade, and colourblind-safe
  (they differ in hue *and* temperature), always paired with the team name
- One loud element per screen: the Sip button
- Touch targets ≥ 46px

## Known constraints

- State polls every 2.5s rather than using WebSockets, so a sip can appear ~2s
  late on other screens. Fine for a movie night.
- Two teams only — the schema enforces `CHECK(team IN (0,1))`.

## Roadmap

- [ ] Chaos slider — sipping vs pounding, feeding rule aggressiveness
- [ ] Archive tab — past films and results per player
- [ ] WebSockets to replace polling
