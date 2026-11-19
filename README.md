# Omen

Python 3.12 personal opportunity discovery pipeline: collect, normalize, deduplicate, score and render a daily digest. SQLite keeps source identity separate from the profile so the data model can support multiple profiles later.

## Setup

```sh
uv sync
uv run oe collect
uv run oe score
uv run oe digest
# or run all stages and both sources
uv run oe run
```

The initial profile is under `opportunity_engine/profile/`. Replace the resume placeholder with structured JSON and replace the goals placeholder with your goals verbatim. No login-only sources are used.

## Environment

- `LLM_API_KEY`: optional OpenAI-compatible API key; without it, scoring uses a transparent keyword fallback.
- `LLM_BASE_URL`, `LLM_MODEL`: optional API endpoint and model (defaults to OpenAI API and `gpt-4o-mini`).
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`: optional digest delivery. Without `SMTP_HOST`, writes `digests/YYYY-MM-DD.html`.

## Adding a collector

Implement `fetch() -> list[RawItem]` in `opportunity_engine/collectors/`, retain a stable `source_id`, add its fixture and parser test, then include the collector in `collect_sources()` in `cli.py`. The collector should set a descriptive User-Agent, use retries, and respect the source's request limits.

## API and web app

```sh
uv run python -m api.seed        # collect live events from configured public sources
uv run api                        # FastAPI at localhost:8000
cd web && pnpm install && pnpm dev
```

Open `http://localhost:3000/events`. The API uses the existing SQLite file and adds `stage`/`notes` columns plus people and X post tables on first request. Configure `NEXT_PUBLIC_API_URL` in `web/.env.local` to match the API address. Set `WEB_ORIGINS` to the web app origins allowed to call the API. Live collection filters are set with `LUMA_QUERIES`; no location is assumed.

The web app includes Today, Events, Hackathons, X posts, People, Tracker, and Calendar. Running `uv run python -m api.seed` collects live Luma events using the configured query filters.

### Social sources

- `X_PUBLIC_TIMELINES`: comma-separated public X profile or list URLs. The X page renders X's official embedded timeline widgets and provides a direct link to X. The collector does not scrape X; automatic search/import requires X API access.
- LinkedIn post retrieval is disabled until an approved LinkedIn API integration is configured. Do not scrape LinkedIn. Public LinkedIn content can be opened in LinkedIn; LinkedIn records appear only after an approved API integration or explicit manual import.
- The **Refresh** action runs the Luma public discover collector and scoring pipeline for events and programs, excluding internship/job collection.
