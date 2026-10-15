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

Edit `backend/.env` (created from `backend/.env.example` on first setup):

- `DATABASE_URL` — local Postgres, or a Supabase connection string with `?sslmode=require`
- `SEED_DEMO_DATA=true` loads three imperfect demo tables (`customers`, `orders`, `products`) only when `customers` is missing. Set this to `false` before pointing at a real warehouse.
- `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` — the model that suggests checks and translates plain-language requests. The example file already sets these. Leave the key blank and the app still suggests checks from the table profile.
- Optional switches, with no other code change: `LLM_PROVIDER=gemini` plus `GEMINI_API_KEY`, or `LLM_PROVIDER=groq` plus `GROQ_API_KEY`.

## Run

```bash
scripts/dev.sh
```

Open [http://localhost:3000](http://localhost:3000). The API health check is at [http://localhost:8000/api/health](http://localhost:8000/api/health).

The first check run is slower because Great Expectations loads its runtime. Later runs in the same process are quicker. Results are stored, so reopening a table shows the last run without executing it again.

## How to use it

1. Pick a table. The page shows columns, empty values, and a sample.
2. Checks appear on their own the first time a table has none. **Suggest checks** adds more. Each one is a Great Expectations expectation with a plain-language title.
3. Edit, pause, or remove any check. The configuration block shows the expectation type and kwargs.
4. Describe another check, for example: `amount should be between 0 and 1000`.
5. **Run checks**. The quality report lists failures and warnings with example values, and that report is what you see the next time you open the table.

## Test

With the API running:

```bash
scripts/test.sh
```

That checks the demo tables, the saved reports, a plain-language check, and one live re-run. It finishes in a few seconds and prints `PASS` or `FAIL` for each step.

In the browser, open http://localhost:3000 and confirm:

1. `customers` is selected and the quality report shows the bad email, the duplicate email, and ages `-3` and `240`.
2. `orders` shows customer `9999` and amount `-20`.
3. `products` shows duplicate `SKU-1` and price `-9.99`.
4. On `customers`, type `country is required`, choose **Add this check**, then **Run checks**. That new check passes, and the email failures stay in the report.

## Architecture

- **Next.js** (TypeScript and React) is the interface. It proxies `/api` to the backend.
- **Django** lists tables, profiles them, stores checks, and returns saved runs. The same JSON paths the UI already used are unchanged.
- **PostgreSQL** holds the data under test. Application state (checks and runs) lives in a separate `dq` schema in the same database, so switching `DATABASE_URL` to Supabase moves both.
- **Great Expectations 1.x** runs each check through an ephemeral context and a whole-table batch. Expectations are a fixed catalog (not arbitrary code), then executed one at a time so one bad check does not hide the rest.
- A run writes `dq.runs` and `dq.run_results`. The dashboard reads that cache until the user runs again.

## AI integration

The configured provider is OpenAI (`OPENAI_MODEL` in `backend/.env`, `gpt-5.6-luna` in the example). The model receives the table profile: types, null rates, ranges, frequent values, and a few sample rows. It must return JSON using only the expectation types the engine knows how to run. Unknown columns and unknown types are dropped.

When `OPENAI_API_KEY` is empty, or the model call fails, the same profile produces checks with deterministic rules (required identifiers, email shape, non-negative amounts, allowed status values, foreign-key style id sets). A short phrase parser covers the same path for typed requests. The API tells the UI which path was used.

Prompts live in `backend/quality/services/llm.py`. The allowed expectation catalog lives in `backend/quality/services/catalog.py`.

## How AI tools were used

Cursor was used to scaffold this MVP: the Django API, the Great Expectations runner, the Next.js screens, and this write-up. The expectation catalog and the profile-based fallback were kept explicit so a model response cannot invent an executable check the runner does not understand.

## Future enhancements

- Sample large tables instead of aggregating the full relation.
- Show the primary key of each failing row, not only the bad value.
- Schedule runs and send a short summary when critical checks fail.
- Expectation version history and a review step before a check becomes active.
- Authentication in front of both the UI and the API.
- Cross-table checks that are heavier than an in-set comparison against a small parent id list.

## Repository layout

```
backend/config       Django project settings and root URLs
backend/quality      API, models, profiler, OpenAI client, GX runner
backend/.env.example environment template, including the OpenAI model settings
frontend/src         Next.js UI (TypeScript)
scripts/setup.sh     install dependencies
scripts/dev.sh       run API and UI together
```

Do not commit `backend/.env`. It is listed in `.gitignore`.
