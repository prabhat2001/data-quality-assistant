# Data Quality Assistant

A small product for domain experts who need data-quality checks on PostgreSQL without learning Great Expectations first. They pick a table, review suggested checks in plain language, describe their own, and run them. The technical expectation config stays available, but it is not the starting point.

## What you need

- Python 3.12 (3.10–3.13 also works)
- Node.js 20 or newer
- PostgreSQL. Local Homebrew Postgres is enough for development. Point `DATABASE_URL` at Supabase when you want the cloud database from the case study.

## Setup

```bash
scripts/setup.sh
createdb data_quality   # skip if the database already exists
```

Edit `backend/.env`:

- `DATABASE_URL` — local Postgres, or a Supabase connection string with `?sslmode=require`
- `SEED_DEMO_DATA=true` loads three imperfect demo tables (`customers`, `orders`, `products`) only when `customers` is missing. Set this to `false` before pointing at a real warehouse.
- `GEMINI_API_KEY` — a free key from [Google AI Studio](https://aistudio.google.com/apikey). Leave it blank and the app still suggests checks from the table profile.
- Later, switch to a paid model with no code change:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

`LLM_PROVIDER=groq` is the other free-tier option.

## Run

```bash
scripts/dev.sh
```

Open [http://localhost:3000](http://localhost:3000). API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

The first check run is slower because Great Expectations loads its runtime. Later runs in the same process are quicker. Results are stored, so reopening a table shows the last run without executing it again.

## How to use it

1. Pick a table. The page shows columns, empty values, and a sample.
2. Choose **Suggest checks**. Each suggestion is a Great Expectations expectation with a plain-language title.
3. Edit, pause, or remove any check. The configuration block shows the expectation type and kwargs.
4. Describe another check, for example: `amount should be between 0 and 1000`.
5. **Run checks**. Failures and warnings list example values. **Run checks** again to refresh the saved result.

## Architecture

- **Next.js** is the interface. It proxies `/api` to the backend.
- **FastAPI** lists tables, profiles them, stores checks, and returns saved runs.
- **PostgreSQL** holds the data under test. Application state (checks and runs) lives in a separate `dq` schema in the same database, so switching `DATABASE_URL` to Supabase moves both.
- **Great Expectations 1.x** runs each check through an ephemeral context and a whole-table batch. Expectations are a fixed catalog (not arbitrary code), then executed one at a time so one bad check does not hide the rest.
- A run writes `dq.runs` and `dq.run_results`. The dashboard reads that cache until the user runs again.

## AI integration

The development provider is Gemini’s free tier (`gemini-3.5-flash-lite` by default). The model receives the table profile: types, null rates, ranges, frequent values, and a few sample rows. It must return JSON using only the expectation types the engine knows how to run. Unknown columns and unknown types are dropped.

When `GEMINI_API_KEY` is empty, or the model call fails, the same profile produces checks with deterministic rules (required identifiers, email shape, non-negative amounts, allowed status values, foreign-key style id sets). A short phrase parser covers the same path for typed requests. The API tells the UI which path was used.

Prompts live in `backend/app/services/llm.py`. The allowed expectation catalog lives in `backend/app/services/catalog.py`.

## How AI tools were used

Cursor was used to scaffold this MVP: the FastAPI service, the Great Expectations runner, the Next.js screens, and this write-up. The expectation catalog and the profile-based fallback were kept explicit so a model response cannot invent an executable check the runner does not understand.

## Future enhancements

- Sample large tables instead of aggregating the full relation.
- Show the primary key of each failing row, not only the bad value.
- Schedule runs and send a short summary when critical checks fail.
- Expectation version history and a review step before a check becomes active.
- Authentication in front of both the UI and the API.
- Cross-table checks that are heavier than an in-set comparison against a small parent id list.

## Repository layout

```
backend/app          FastAPI app, profiler, LLM client, GX runner
backend/.env.example environment template (no secrets)
frontend/src         Next.js UI
scripts/setup.sh     install dependencies
scripts/dev.sh       run API and UI together
```

Do not commit `backend/.env`. It is listed in `.gitignore`.
