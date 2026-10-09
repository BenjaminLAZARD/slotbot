# slotbot

**Books public sports courts the second their booking window opens, driven by your Google Calendar.**
You drop an event called *Candidate Tennis* in your calendar at the time you want to play; slotbot
finds courts within biking distance, wakes up 5 minutes before the city opens bookings for that day,
polls every second, books the best free slot, and writes the outcome back into the event.

First supported booking system: **Madrid municipal sports centres** (the system behind the
*Madrid Móvil* app and [deportesweb.madrid.es](https://deportesweb.madrid.es)). Built so that other
cities or booking sites plug in as one module.

> **Status (2026-10-08):** the whole Madrid chain is implemented: planning, venues (the booking
> site's own 33 tennis centres), login, opening detection, availability, reservation and payment
> **from the Madrid wallet** (top it up yourself; card/Bizum/Google Pay need your bank's approval and
> can't be automated). The flow was captured from a real booking; the bot's own first end-to-end run
> is still to come. See [docs/madrid-api.md](docs/madrid-api.md) and [HISTORY.md](HISTORY.md).

## How it works

```
Your calendar                         slotbot                                    Madrid booking site
─────────────                         ───────                                    ───────────────────
"Candidate Tennis"  ── daily sync ──► plan: where from (event location),
Sat 17 Oct 19:00                      courts ≤ 30 min by bike, acceptable times,
                                      booking opens Sun 11 Oct 00:00
"Pending Tennis"    ◄── rename + list courts in description
                                      schedule trigger at 23:55 ───┐
                                                                    ▼
                                      23:55 log in · 23:59 poll every 1 s ─────► availability
                                      00:00 slots appear → book best one ──────► booking (wallet)
"Success - Tennis"  ◄── title, court, time, every attempt logged
  (or "Failure - Tennis")             then plan the next candidate event
```

- **Which event:** the earliest upcoming event whose title contains the *candidate* marker
  (default `Candidate Tennis`). Only the next one is marked *Pending*; the following one is planned
  right after each race.
- **Where from:** the event's location (an address, a neighbourhood, or `lat, lon`), falling back to
  the profile's home. Geocoded with OpenStreetMap's Nominatim.
- **Which courts:** the provider's venue list, ranked by estimated bike time (straight-line distance
  × 1.3 at 15 km/h by default), kept if ≤ 30 min. Cached for 24 h; refreshed after every race and
  from the UI.
- **Which times:** weekdays accept the requested time *or any later slot*; weekends accept ±2 h
  (both configurable). Order of attempts: requested time first, then the nearest times (later wins
  a tie); within one time, the closest court first.
- **When:** Madrid opens one-off tennis rentals 7 days ahead *counting the day of play* (D−6). The
  hour is not published; it defaults to 00:00 (`SLOTBOT_MADRID_OPENS_AT`) until verified.
- **Race:** the trigger fires 5 min before opening (log in), polls availability every 1 s from 60 s
  before, tries every acceptable free slot in order, and keeps retrying for 2 min after opening.

### Narrowing a single event

Optional `key: value` lines in the event description (everything above the bot's
`──── slotbot ────` section stays yours):

```
earliest: 18:00        # overrides the weekday/weekend window
latest: 21:30
only: Chopera, Gallur  # venue name contains one of these (accents/case ignored)
avoid: Casa de Campo
max_bike: 20           # minutes, this event only
```

Lines the bot can't read are reported as ⚠ warnings in the event description.

## Quick start (local, OrbStack or any Docker engine)

```bash
cp .env.example .env    # then set SLOTBOT_SECRET_KEY (command in the file) and SLOTBOT_CONTACT_EMAIL
docker compose up --build
```

- UI: <http://localhost:5173> · API docs: <http://localhost:8000/docs>
- Without Google configured you can still create profiles and preview courts; syncing needs step 2.

### Connect Google Calendar (service account)

A *service account* is a robot Google identity owned by your Google Cloud project. You share your
tennis calendar with its email, and it reads/edits only that calendar.

1. In [Google Cloud console](https://console.cloud.google.com): create (or pick) a project →
   *APIs & Services* → enable **Google Calendar API**.
2. *IAM & Admin → Service accounts* → create `slotbot` → *Keys* → add a JSON key → save it as
   `secrets/google-service-account.json` (the `secrets/` folder is gitignored).
3. In Google Calendar → your tennis calendar → *Settings and sharing* → *Share with specific people*
   → add the service account's email with **Make changes to events**. Copy the *Calendar ID* from
   *Integrate calendar*.
4. In the UI: create a profile with that Calendar ID, your home area, and the booking site; store the
   booking-site credentials (encrypted at rest, write-only from the UI).

### Debugging & hot reload

Both services hot-reload inside the containers (polling-based, so edits on the host are always seen):

| What | How |
|---|---|
| Backend code | edit `backend/src/**` → uvicorn restarts the worker (within ~5 s) |
| Frontend code | edit `frontend/src/**` → Vite hot-module replacement, no page reload |
| Python breakpoints | debugpy listens on `localhost:5678`; in VS Code/Cursor run **Attach to API (docker)** (`.vscode/launch.json`) |
| Run the API outside Docker | `docker compose up db`, then **API (local, no docker)** launch config, or `cd backend && uv run uvicorn slotbot.main:create_app --factory --reload` |
| Frontend data | React Query devtools (bottom-left flower icon, dev only) |
| Tests | `cd backend && uv run pytest` |

After changing API models, regenerate the frontend's types: `cd frontend && npm run gen:api`.

### Email notifications

The bot emails you when it books (court, time, price), when it fails (reason + attempts), and flags
when the wallet balance left is below the price just paid. It sends through [Resend](https://resend.com)
(free: 100 emails/day):

1. Sign up at resend.com **with the address you want the emails at**. Without your own domain,
   Resend only delivers to that address (from `onboarding@resend.dev`), which is all a personal
   setup needs.
2. *API Keys* → create a key with **Sending access** (it can send email and nothing else).
3. In `.env`: `SLOTBOT_RESEND_API_KEY=re_…`, then `docker compose up -d api`.
4. In the UI → Settings: put that same address in **Email me results**, save, press **Send test email**.

SMTP (`SLOTBOT_SMTP_USER` / `SLOTBOT_SMTP_PASSWORD`) also works, but with Gmail it needs an app
password, which grants access to your whole mailbox; prefer Resend.

## Running it so it books for you

The UI and the bot are one program: the API process holds the booking timers. It books only while it
runs, at the daily sync and at each trigger (5 min before a booking window opens).

- **On your Mac:** `docker compose up -d`, keep the Mac plugged in and awake (System Settings → Battery
  → Options → prevent automatic sleeping on power adapter). Optional wake-up safety net:
  `sudo pmset repeat wakeorpoweron MTWRFSU 23:45:00`.
- **In the cloud:** see below; nothing needs to run on your machine.

## Deploying (scale-to-zero on Google Cloud)

Nothing runs 24/7: Cloud Run hosts the container and scales to zero, **Cloud Tasks** calls
`/jobs/race/{id}` at the exact trigger time, **Cloud Scheduler** calls `/jobs/sync` hourly, and the
database is **Neon** Postgres (also scales to zero). A €10 budget alerts by email and, through
Pub/Sub → `/jobs/budget`, detaches billing when reached. Step-by-step: [deploy/gcp.md](deploy/gcp.md).

## Sign-in and several people

The site's front page explains slotbot to visitors; the app behind it needs **Sign in with Google**.
Only accounts on the invite list (`SLOTBOT_ALLOWED_EMAILS`) get in, and each person sees only their
own profiles. The browser receives a Google-signed ID token, the API verifies it against Google's
public keys and keeps the user's id in a signed session cookie. On localhost without
`SLOTBOT_GOOGLE_CLIENT_ID`, sign-in is off and everything belongs to one local user. `/jobs/*` (the
machines) never use the cookie: job token, plus Google's OIDC token once the service is public.

## Project layout

```
backend/src/slotbot/
  domain/        pure rules: constraints parsing, ranking & time windows, description rendering
  ports.py       interfaces: Calendar, Provider(+Session), Geocoder, Triggers, Clock
  services/      sync (plan next event), race (the booking loop), planner, venue cache, local loop
  adapters/      Google Calendar, Google auth, Nominatim, Cloud Tasks / local triggers, vault, clock
  providers/     madrid.py (Madrid municipal tennis), demo.py (simulated), registry
  api/           FastAPI routers: profiles, bookings, jobs (scheduler callbacks), meta
  container.py   composition root: the only place wiring concrete adapters to ports
frontend/src/    React + Vite + Tailwind + shadcn/ui; typed client generated from the API schema
deploy/gcp.md    Cloud Run + Cloud Tasks + Cloud Scheduler + Neon
docs/            provider notes (Madrid API capture procedure)
HISTORY.md       dated change log and decisions (read this first when resuming work)
```

### Adding a city or booking site

Implement `ports.Provider` (venues, opening rule, credential fields) and `ports.ProviderSession`
(`free_slots`, `book`) in `backend/src/slotbot/providers/<name>.py`, register it in
`providers/__init__.py`. Everything else (calendar, planning, race, UI) is shared.

## Things to know before using it

- **Pay from the wallet.** Madrid lets you pay with the app's prepaid wallet (*monedero*); keep it
  topped up. slotbot never handles card payments (3-D Secure can't be automated, and shouldn't be).
- **No-shows cost you.** Madrid allows free cancellation until 24 h before; a second no-show suspends
  advance booking for 48 h. Any booking can be cancelled within 10 minutes of confirmation.
- **Be a good citizen.** One request per second for a couple of minutes per booking is modest; don't
  lower `SLOTBOT_POLL_SECONDS`. Automated booking may conflict with the site's terms of use; you are
  responsible for how you use it.
- **Secrets** live in `.env` and `secrets/` (both gitignored) locally, and in Secret Manager in the
  cloud. Booking-site credentials are encrypted in the database with `SLOTBOT_SECRET_KEY`.
