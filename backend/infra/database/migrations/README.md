# Database migrations (backend)

This folder holds **optional** SQL migrations for production when you prefer not to rely on `init_db()` (which uses SQLAlchemy `create_all`).

## Default: use init_db()

On first run, the CLI and services call `init_db()`, which creates all tables (including `orchestrator_rules`) from the ORM models. No separate migration step is required for development.

## Production: run SQL manually

If you manage schema with SQL (e.g. separate DBA, or Alembic in another repo), you can apply:

- `001_orchestrator_rules.sql` — creates the `orchestrator_rules` table and indexes.

Example:

```bash
psql "$DATABASE_URL" -f backend/infra/database/migrations/001_orchestrator_rules.sql
```

## Adding new migrations

When adding new tables or columns:

1. Update the ORM model under `backend/infra/database/models/`.
2. Add a new `NNN_description.sql` here with `CREATE TABLE ...` or `ALTER TABLE ...` so production can apply it without Python.
