Walk through these before you submit. The assignment is graded on a working product, the OpenAI and Great Expectations integration, and the write-up.

App, from a fresh start

Run scripts/setup.sh, then scripts/dev.sh, and open http://localhost:3000.
Confirm http://localhost:8000/api/health says the database is ok and the provider is openai.
Confirm the table list shows customers, orders, and products, with columns, empty-value notes, and sample rows.
On customers, confirm the report shows the bad email nope, the duplicate ada@example.com, and ages -3 and 240.
On orders, confirm customer 9999 and amount -20. On products, confirm duplicate SKU-1 and price -9.99.
Edit a check, pause one, and delete one. Reopen the table and confirm the last report is still there without running again.
Type country is required, add it, and run checks. That check should pass, and the email failures should remain.
Type something vague, such as make the data better, and confirm the page shows an error instead of saving a check.
Run scripts/test.sh with the API up. Every line should say PASS.
OpenAI

Replace the key in backend/.env. The current OPENAI_API_KEY was rejected by OpenAI as expired, so suggestions fall back to the built-in profiler. Health still says openai because a key is present; that does not mean the model call succeeded.
Click Suggest checks on a table and confirm the note says it was suggested by openai (gpt-5.6-luna), not by the profiler.
Add a new sentence, such as amount should be between 0 and 1000, and confirm the saved check shows a Great Expectations type and kwargs.
Do not commit a live key. backend/.env is gitignored. backend/.env.example currently contains the same expired key, so blank that line before you push and keep the real key only in backend/.env.
What the brief asked for

PostgreSQL is required, and the brief says to use Supabase. Local Postgres is enough to demo, but if the reviewer expects the cloud database, point DATABASE_URL at Supabase and set SEED_DEMO_DATA=false before using a real database.
Confirm a run goes through Great Expectations: the configuration block shows an expectation type, and the report shows pass, fail, or warning with example values.
Read README.md and confirm it covers architecture, how the model is prompted, what happens when the key is missing, future enhancements, and how Cursor was used. Those are the required write-up sections.
Push the repo with the Django backend, the TypeScript frontend, requirements.txt, and the scripts. Leave out .venv, node_modules, and backend/.env.