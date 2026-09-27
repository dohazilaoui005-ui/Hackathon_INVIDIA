# CivicPilot — Backend & API (Person 4's part)

This is the backend/integration layer for CivicPilot. Per the team workflow:
my job is the API, the shared schemas, wiring the frontend to AI/retrieval/
rules/database, error handling, logging, caching, deployment, and a
fallback demo dataset — **not** the AI extraction logic, the RAG pipeline,
or the eligibility rules themselves. Those belong to Persons 2 and 3.

One reliable endpoint: **`POST /analyze-case`**.

## How the five roles connect (from the team doc)

| Field                | Owner            | Purpose                                          |
|----------------------|------------------|---------------------------------------------------|
| `user_profile`       | AI workflow (P2) | Structured facts from the conversation             |
| programs + evidence  | RAG/data (P3)    | Relevant official passages and source links        |
| eligibility result   | Rules/data (P3)  | Matched, missing, and failed requirements          |
| `final_response`     | AI workflow (P2) | Safe explanation + prioritized action plan         |
| `display_model`      | Backend (P4, me) | Stable format for cards, citations, checklist      |

See **`contracts.py`** for the exact shape of every one of these — that
file is what Persons 2 and 3 should build against.

## Architecture

```
Frontend (Person 5)
   |
   v
POST /analyze-case   (app.py — orchestration only)
   |
   |-- 1. modules/ai_workflow.py :: extract_profile(text, language)
   |        PERSON 2 owns this. Fallback inside: calls Claude, degrades to
   |        keyword extraction (modules/_fallback_extract_impl.py) if that fails.
   |
   |-- 2. merge with any partial profile the frontend already collected
   |        (schemas.py :: merge_case — explicit frontend values always win)
   |
   |-- 3. modules/rag_engine.py :: find_programs(profile)
   |        PERSON 3 owns this. Fallback inside: queries the bundled demo
   |        dataset (data/programs_demo.json) with deterministic eligibility
   |        scoring. This IS the guaranteed fallback if the real vector-DB /
   |        live-source pipeline is down — same function, same return shape.
   |
   |-- 4. modules/ai_workflow.py :: generate_final_response(profile, rag_result)
   |        PERSON 2 owns this. Must use "appears to match" / "may be
   |        eligible" — never "approved". Fallback: simple templating.
   |
   |-- 5. modules/display.py :: build_display_model(...)
   |        BACKEND owns this. Combines the above into the exact shape
   |        Person 5 renders as cards / citations / checklist.
   |
   |-- 6. db.py :: save_case(...) — logged but non-fatal on failure
   |
   v
JSON response: { case_id, user_profile, rag_result, final_response, display_model, meta }
```

Every external step (the AI call, retrieval) is wrapped in try/except. If
it fails, the request still returns 200 with partial results and a
human-readable note in `meta.warnings` — one failing component never takes
down the demo.

## Handoff for Persons 2 and 3

You only need to edit **one function each**, matching the signature already
wired into `app.py`:

- **Person 2** — `modules/ai_workflow.py`:
  - `extract_profile(text, language) -> user_profile dict`
  - `generate_final_response(profile, rag_result, language) -> final_response dict`
- **Person 3** — `modules/rag_engine.py`:
  - `find_programs(profile) -> {"programs", "evidence", "matches", "warnings", "sources"}`

Replace the function *bodies* only. Don't change the signatures or return
shapes — `app.py`, `modules/display.py`, and the frontend are all built
against them and won't need to change when you swap in the real
implementation.

## Running locally

```bash
cd case_analyzer_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # ANTHROPIC_API_KEY is optional — see below
python app.py
```

Runs at `http://localhost:5000`.

### Without any API key
Leave `ANTHROPIC_API_KEY` blank. `extract_profile` falls back to keyword
matching and `find_programs` uses the bundled demo dataset — the full
pipeline still runs and returns real (if simpler) results. This is what
makes the prototype demoable even if the AI or a live data source is down
during judging.

## API

### `POST /analyze-case`
```json
{
  "text": "I'm a 24-year-old student in Casablanca, Morocco. I want to start a small tech tutoring business but can't take on debt. I need about 15000 MAD.",
  "language": "en",
  "case": {}
}
```
Returns `{ case_id, user_profile, rag_result, final_response, display_model, meta }`
— see `contracts.py` for the full shape of each.

### `GET /case/<case_id>` — retrieve a previously analyzed case
### `GET /programs` — inspect the current fallback dataset
### `GET /health` — `{"status", "demo_programs_loaded", "ai_configured"}`

## Extending the demo dataset
Add entries to `data/programs_demo.json`. Each program can declare:
`countries`, `sector`, `type` (`grant`/`loan`/`equity`), `max_amount`,
`currency`, `requires` (eligibility flags), `required_documents`,
`deadline`, `official_contact`, `verification_date`. Person 3's real RAG
pipeline should populate the same fields from actual scraped/official
sources.

## Deployment (Render; similar on Railway/Fly.io)
1. Push this folder to a GitHub repo.
2. New **Web Service** on Render, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT` (the `Procfile` covers this automatically)
5. Add env vars from `.env.example` (`ANTHROPIC_API_KEY` optional).
6. Deploy — you get a URL like `https://your-service.onrender.com`.

Note: free tiers usually have an ephemeral filesystem, so SQLite resets on
redeploy — fine for a hackathon demo. Swap `DATABASE_PATH` for a managed
Postgres URL later; only `db.py` would need to change.

## Quick test once deployed
```bash
curl -X POST https://your-service.onrender.com/analyze-case \
  -H "Content-Type: application/json" \
  -d '{"text": "Je suis réfugié dans une zone rurale, je veux démarrer une petite ferme, j ai besoin de 3000 USD.", "language": "fr"}'
```
