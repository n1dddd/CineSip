> Cursor / Claude / agent rules for this repo. Read before writing code.

# CineSip

Team drinking game. Friends split into two teams, pick a film, and each team
gets rules generated from that film's **real** plot — tap a rule when it
happens on screen.

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + aiosqlite (WAL), Python 3.12 |
| Frontend | React 19 + Vite + Tailwind v4 + Zustand |
| Data | TMDB (film facts) + OpenRouter (rule wording) |
| Deploy | Docker Compose on OVH VPS, nginx fronts everything |

## Architecture rules

**The LLM never invents film facts.** `POST /api/games/{id}/movie` fetches real
TMDB plot/cast/genres first and passes them as the *only* permitted source. This
is why brand-new releases work. Never "simplify" this into asking the model what
it remembers about a film.

**Server is the single source of truth for scores.** Drink totals are derived
from `drink_logs` at render time, never cached in client state — otherwise two
phones disagree. Don't reintroduce local counters.

**Same-origin API.** `API_BASE` is `''`; nginx proxies `/api/` to the backend.
Never hardcode `localhost:8000` — it breaks every phone on the network.

**Backend is not publicly exposed.** Compose uses `expose`, not `ports`. nginx
is the only entrance.

## Design rules

The app is used **in a dark room, mid-film, by people drinking.** That drives
every visual decision:

- Use semantic tokens from `app.css` (`--color-surface`, `--color-content`,
  `--color-team-a`). Never raw hex in components.
- **No gradients, no glow shadows.** They light up the room and wreck night
  vision. Shadows convey elevation only.
- Cream text (`--color-cream-100`), never pure white — less glare.
- Teams are **Amber vs Teal**: the cinema colour grade, and colourblind-safe
  (differ in hue *and* temperature). Never rely on colour alone — always pair
  with the team name.
- **One loud element per screen**: the Sip button. Everything else recedes.
- Touch targets ≥ 46px. Inputs ≥ 16px font or iOS zooms on focus.
- Emoji is not UI. Use type and colour.

## Commit convention

Conventional Commits — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`,
`chore:`, `perf:`. Body explains *why*, not what.

## Never commit

`.env`, `*.db`, `dist/`, `node_modules/`. Secrets live in `.env` (gitignored);
`.env.example` documents the shape.

## Local development

```bash
# backend
cd backend && uv run uvicorn app.main:app --reload --port 8000

# frontend (proxies /api to :8000)
cd frontend && npm run dev
```

## Deploy

```bash
# copy changed files, then:
ssh cinesip 'bash ~/cinesip/deploy.sh'
```

`deploy.sh` stops host nginx (it fights the container for :80), rebuilds, and
health-checks.

## Known constraints

- State syncs by **polling every 2.5s**, not WebSockets. Fine for a movie night;
  a sip may land ~2s late on other screens.
- Two teams only. The schema has `CHECK(team IN (0,1))` — adding a third team
  means a migration.
