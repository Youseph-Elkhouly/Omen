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

## Notes workspace

The home page (`http://localhost:3000/`) is a notes workspace backed by a folder of Markdown files, `OMEN_VAULT_PATH` (default `./vault/`, which is git-ignored). Open the same folder in desktop Obsidian and the notes, `[[wikilinks]]` and graph line up.

- `Goals.md` is the single source of truth for goals. Each `## heading` is one goal, and scoring, `/profile` and `/today` all read this file. On first run it's seeded from `opportunity_engine/profile/goals.md`. Link to a goal from any note with `[[Goals#Heading]]`.
- `Opportunities/` and `People/` notes are created the first time you open one and are named by their title, e.g. `People/Jane Doe.md`, so `[[Jane Doe]]` just works. When two different entities would get the same name, Omen adds ` (Org)`, or ` YYYY-MM-DD` when the same org repeats an event. Stubs start with `## Notes`, `## Prep` and `## Retro` (people get `## Why`, `## Notes` and `## Follow-ups`). Whatever you write under `## Notes` is copied into the database, including edits made in Obsidian. Renaming a note in Obsidian is fine, because Omen finds it again by its `omen_id`.
- `Orgs/` and any other folders hold free-form notes.
- Links resolve the way Obsidian resolves them: an exact path first, then a unique file name, ignoring case. A link that doesn't resolve is shown as unresolved, and clicking it creates the note.

The page has three panes: a file tree with search, the Focus panel above the graph, and the open note (Edit/Preview, properties and backlinks). On a phone they become tabs. The graph shows goals, people, orgs, every opportunity that has a note or is being tracked, and your own notes, not the whole opportunities table. The API behind it is `/notes/tree`, `/notes`, `/notes/search`, `/notes/rename`, `/notes/for/{entity}/{id}` and `/graph`.

## Focus

The Focus panel at the top of the home page shows what needs attention. It's computed on each request from the vault and the database; there is no separate task store.

Tasks are ordinary Markdown checkboxes anywhere in the vault. Due dates use either the Obsidian Tasks plugin form or a dataview-style field:

```md
- [ ] Email Priya about judging 📅 2026-11-24
- [ ] Draft the retro due:: 2026-11-25 [[Goals#Build in public]]
- [x] Register
```

- **Overdue** and **Due this week**: open tasks by due date. Ticking the checkbox rewrites only that line of the file (`PATCH /tasks`; `GET /tasks?status=open&due_before=YYYY-MM-DD` lists them).
- **Deadlines**: saved opportunities whose deadline is within 7 days and that haven't been applied to.
- **Follow up with**: people with an open task under `## Follow-ups` that is due, or people marked met whose note has no open follow-up and hasn't been edited since their event ended (after a 3-day grace period).
- **Write a retro**: opportunities at stage `going` or `attended` whose date has passed and whose `## Retro` is empty.
- **Goals**: per `## Goal`, the opportunities (by stage), people met and tasks that link to `[[Goals#Goal]]`, plus last activity. A goal is flagged *stale* after 14 quiet days and *empty* when nothing links to it. The Today page shows the same Goals section.

Opportunity stages are `saved → applied → going → attended`, plus `skipped`. On the graph, stale goals are faded and notes that need attention get a red ring. New person stubs come with a follow-up task due 3 days after their event, and new opportunity stubs with a deadline get `- [ ] Apply 📅 <deadline>`. `GET /focus` returns all of this in one call.

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
