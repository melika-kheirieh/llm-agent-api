# Database

Local development uses SQLite. Production-like runs use PostgreSQL. Schema changes go through Alembic, not `create_all`.

## URLs

`DATABASE_URL` is the only database setting. Async drivers are added when the URL is a plain SQLite or PostgreSQL scheme:

| Input | Engine URL |
| --- | --- |
| `sqlite:///./app.db` | `sqlite+aiosqlite:///./app.db` |
| `sqlite+aiosqlite:///./app.db` | unchanged |
| `postgresql://user:pass@host:5432/db` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `postgres://...` | `postgresql+asyncpg://...` |
| `postgresql+asyncpg://...` | unchanged |

Other schemes pass through unchanged. A blank `DATABASE_URL` fails startup.

Default (`.env.example`): `sqlite+aiosqlite:///./app.db`.

## Migrations

Startup (`init_db`) runs `alembic upgrade head` against the configured database before the runtime accepts traffic. CLI from the repo root:

```bash
alembic upgrade head
alembic revision -m "describe the change"
```

The first revision (`001_initial`) creates `chat_messages`, `agent_runs`, and `agent_run_events`. Event metadata stays sanitized; this is not a replay log.

If a local `app.db` was created before Alembic existed, delete it (or stamp `001_initial` only when the tables already match). Alembic will not merge a pre-migration SQLite file automatically.

A single API process may migrate on boot (local Compose). Multi-replica production should run `alembic upgrade head` as a separate job before starting replicas, so concurrent boot migrations do not race.

## Local vs production

- **Local / tests:** SQLite. `pytest` sets `DATABASE_URL` to a disposable `.pytest-app.db` so it does not touch `./app.db`. Postgres tests run only when `TEST_POSTGRES_URL` is set.
- **Compose / local Postgres:** PostgreSQL. `docker compose up --build` starts `db` (healthy) then `api`, which migrates on boot. Data lives in the `pgdata` volume. Compose user/password/database (`agent` / `agent` / `agent`) are **local development only**; do not use them in a real deployment.
- **CI:** SQLite tests always run. Postgres tests run when `TEST_POSTGRES_URL` is set (GitHub Actions provides a Postgres service).
- **Multi-replica production:** run `alembic upgrade head` once (or as a migrate job) before starting API replicas. Do not rely on every replica migrating on boot.
