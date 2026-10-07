# History

Dated log of what changed and **why**, newest first. Written for whoever (human or Claude) picks the
project up next: read the latest entry and its *Open items* before changing anything. Append a new
entry at the end of each working session.

---

## 2026-10-07 · v0.1: first end-to-end skeleton

### Goal (from Benjamin)
Automatically book Madrid municipal tennis courts from Google Calendar events:
1. Daily: find the next future event whose title contains *Candidate Tennis*; rename it
   *Pending Tennis*; list in its description the public courts within 30 min by bike of the event's
   location; schedule a trigger 5 min before the **booking window opens** (not before the event).
2. At the trigger: log in with the user's credentials and hit the booking API every 1 s until booked
   or rejected. Weekday: requested time or any later slot. Weekend: ±2 h. Constraints written in the
   description are honoured. Order: closest court first, then other courts, then other times.
3. Write every attempt into the event; retitle *Success - Tennis* / *Failure - Tennis*.
4. Configurable through a website so anyone could use it (other cities, other booking APIs).
   Long-term: a hosted multi-user product.

### Research findings
- Madrid rules (official PDF, Área Delegada de Deporte): one-off tennis rentals open **7 days ahead
  including the day of play → D−6**; free cancellation until 24 h before; any booking cancellable
  within 10 min; no-shows → 48 h suspension of advance booking. Payment: card, Bizum or in-app
  wallet (*monedero*). **Opening hour is not published** → setting, default 00:00, to verify.
- Madrid Móvil and deportesweb.madrid.es share the account. DeportesWeb is ASP.NET WebForms +
  AngularJS; its booking endpoints are behind login and undocumented → capture needed.
- City open data `200186-0-polideportivos` lists 82 sports centres with coordinates; 32 mention tennis
  courts (the JSON URL now 302-redirects; the HTTP client must follow redirects).
- Claude routines (cloud scheduled agents) were evaluated and **rejected** for the booking: 1 h
  minimum interval, network allowlist, env vars visible to environment users, consume Claude usage,
  undocumented max runtime, LLM in a 1 s polling loop.

### Decisions (asked to Benjamin unless noted)
| Topic | Decision | Why |
|---|---|---|
| Trigger timing | opening − 5 min (user correction) | the race is at window opening, not at play time |
| Time windows | weekday: start → any later; weekend: ±2 h | user choice; description `earliest/latest` override |
| Constraints syntax | `key: value` lines | deterministic, no AI needed; user prefers small OSS models if AI is ever added |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, httpx | user asked for FastAPI |
| Frontend | React + Vite + TS, Tailwind v4 + shadcn/ui (radix-nova), TanStack Query, openapi-fetch | user choice |
| Local dev | docker compose on OrbStack | user asked |
| Hosting | GCP Cloud Run + Cloud Tasks + Cloud Scheduler, scale to zero | user rejected always-on containers; Cloud Tasks gives exact-time one-off triggers |
| Database | Neon Postgres (prod), Postgres container (dev) | user asked Neon vs Supabase; FastAPI is the backend so Supabase's extras overlap; Neon scales to zero |
| Google auth | service account (calendar shared with it) | headless, no token expiry; per-user OAuth later for the hosted product |
| Product | hosted multi-user later | user choice despite challenge (credential custody, Google verification, rate limits, fairness) |
| Venues | from the booking app ideally; open data until the API is captured | user request; refresh after each booking + on demand |
| Scheduling model (Claude) | calendar is the source of truth; `bookings` table tracks state; one trigger per pending booking, rescheduled when opening time moves | restart-safe, idempotent, multi-profile |

### What was built
- `backend/`: domain rules (constraints, ranking, windows, description), ports, services (sync,
  race, planner, venue cache, local loop), adapters (Google Calendar REST, service-account tokens,
  Nominatim, Cloud Tasks + local triggers, Fernet vault), providers (`madrid-tennis` with open-data
  venues and **stubbed booking session**, `demo`), API (profiles, credentials, venues, sync,
  bookings, retry, jobs, meta), Alembic initial migration. 12 tests (domain, race loop, sync + race
  flow on SQLite with fakes).
- `frontend/`: profiles list; Bookings (next booking, history with attempts, retry), Courts (ranked,
  refresh), Settings (config form, write-only credentials, constraints cheat sheet).
- Dev: compose (db, api with debugpy :5678 + uvicorn reload via polling, web with Vite HMR via
  polling), `.vscode/launch.json` attach/launch configs, React Query devtools.
- Docs: README, `docs/madrid-api.md` (capture procedure), `deploy/gcp.md` (untested), CI workflow.

### Verified
- `pytest` 12/12; frontend `tsc` + build OK; ruff clean.
- In OrbStack: migrations apply; UI creates a profile; Courts tab ranks live Madrid open-data venues
  (15 within 30 min of Puerta del Sol); sync without Google key returns a clear 503.
- Hot reload: backend file edit → "WatchFiles detected changes… Reloading"; frontend edit → Vite
  "hmr update". debugpy port open (IDE attach itself not exercised).

### Gotchas met
- YAML folded scalar (`>`) keeps newlines on more-indented lines → split the compose command and
  uvicorn started on 127.0.0.1 without `--reload`. Use a list `command:` with `>-`.
- Bind-mounted files in containers didn't trigger reloads → `WATCHFILES_FORCE_POLLING`,
  `VITE_USE_POLLING`.
- `openapi-typescript` peers TypeScript 5 while Vite's template ships TS 6 → run it via `npx` in
  `npm run gen:api` instead of a dev dependency.
- `UTCDateTime` type decorator must be rendered as `sa.DateTime(timezone=True)` in migrations
  (`render_item` in `migrations/env.py`).

### Open items (next session)
1. **Capture the DeportesWeb API** with Benjamin signed in (docs/madrid-api.md); implement
   `DeportesWebSession` (login, availability, book with wallet) and source venues from it.
2. **Verify the opening hour** of D−6 slots; set `SLOTBOT_MADRID_OPENS_AT`.
3. Benjamin: create the Google service account + share the tennis calendar; first real sync.
4. First deploy to GCP following deploy/gcp.md; fix what breaks; Neon project.
5. Product track: user accounts (Google sign-in with calendar scope, per-user OAuth tokens), auth on
   the UI, per-provider rate limiting, Google app verification.
6. Nice to have: notify on success/failure (calendar already shows it), real bike routing (OSRM)
   instead of straight-line estimate, Spanish public holidays as "weekend".
