# Void — AI Pull Request Reviewer

Void reads every pull request the moment it opens, catches real bugs with an LLM, and posts inline
comments only when something's actually wrong. No noise, no rubber-stamping — silence means the
code passed.

## What it does

- **Reviews PRs automatically** — installs as a GitHub App, triggers on `opened`/`synchronize`
- **Only flags real issues** — bugs, security problems, correctness bugs; not style nitpicks
- **Stays quiet on purpose** — severity threshold + comment cap so it never walls-of-text a diff
- **Never repeats itself** — remembers what it already flagged, deduplicates across pushes to the
  same PR, and skips re-processing a commit it's already reviewed (safe against webhook redelivery)
- **Live activity feed** — a WebSocket channel (`/ws/activity`) broadcasts every step in real time;
  a native macOS floating overlay ([`overlay-macos/`](../overlay-macos)) subscribes to it
- **Controllable** — pause/resume the bot, or manually trigger a review for any `owner/repo#pr`,
  via local-only control endpoints

## How it works

```
GitHub PR opened/synchronize
        │  webhook (HMAC-signed)
        ▼
FastAPI /webhook  → verifies signature → dispatches background task
        │
        ▼
1. Auth as the GitHub App (JWT → installation access token)
2. Fetch the diff + full content of touched files
3. Send to Gemini with a structured-output schema (findings: file, line, severity, category)
4. Filter: drop low severity, dedupe against past reviews, cap comment count
5. Post the surviving findings as a GitHub review
6. Persist the review + findings to Postgres
7. Broadcast progress over WebSocket the whole way through
```

## Stack

FastAPI · SQLAlchemy + Alembic (Postgres) · Google Gemini (`google-genai`) · GitHub App auth (PyJWT)
· httpx

## Setup

1. **Create a GitHub App** — permissions: `Pull requests: Read & write`, `Contents: Read-only`
   (or `Read & write` if you want it to be able to commit); subscribe to the `Pull request` event;
   set the webhook URL to wherever this is deployed (or an `ngrok`/`smee.io` tunnel for local dev)
   and generate a webhook secret.
2. **Install the App** on the repo(s) you want reviewed.
3. **Get a Gemini API key** — free tier at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
4. **Copy `.env.example` → `.env`** and fill in:
   ```
   GITHUB_APP_ID=
   GITHUB_PRIVATE_KEY=       # full PEM contents from the App's downloaded private key
   GITHUB_WEBHOOK_SECRET=
   GEMINI_API_KEY=
   DATABASE_URL=             # postgresql://... (or sqlite:///./dev.db for local testing)
   ```
5. **Install deps and run migrations:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   alembic upgrade head
   ```
6. **Run the server:**
   ```bash
   uvicorn app.main:app --port 8123
   ```

## Project structure

```
app/
├── main.py              # FastAPI app: /webhook, /ws/activity, /control/*
├── config.py             # env-based settings
├── github_auth.py        # GitHub App JWT → installation token
├── github_client.py      # fetch diffs/files, post reviews, GitHub API calls
├── reviewer.py            # Gemini prompt + structured review call
├── review_pipeline.py     # orchestrates the whole flow
├── filters.py              # severity/cap/dedupe logic
├── persistence.py          # DB read/write helpers
├── models.py                # SQLAlchemy models
├── db.py                     # engine/session
├── activity.py                # WebSocket broadcaster
└── control.py                  # pause state
```

## Companion app

[`overlay-macos/`](../overlay-macos) is a small native Swift app — a floating, always-on-top panel
that connects to `/ws/activity` and shows live review activity, plus pause/resume and manual-trigger
controls.
