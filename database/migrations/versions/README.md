# Alembic Migrations

## Current State

This directory is intentionally empty. The database schema for this project is
currently managed via SQLAlchemy's `Base.metadata.create_all()` (see
`database/connection.py`), not via Alembic migrations.

All ORM models are defined in `database/models.py` and the schema is created
on application startup. This is acceptable for the current single-deployment,
single-developer phase of the project.

## When to Switch to Real Migrations

Once any of the following becomes true, a proper Alembic baseline should be
generated and this README replaced with versioned migration files:

- Multiple environments (staging/prod) need to stay in sync
- Schema changes must be applied to a database with existing production data
  that cannot be dropped/recreated
- More than one developer is making concurrent schema changes

## How to Bootstrap (when ready)

1. Ensure the live database matches `database/models.py` exactly.
2. Run from the project root:

   ```
   alembic revision --autogenerate -m "baseline"
   ```

3. Inspect the generated file in this directory carefully — autogenerate is
   not perfect (it misses some constraint/index changes, server defaults,
   etc.).
4. Stamp the existing database as being at this baseline:

   ```
   alembic stamp head
   ```

5. From this point onward, every schema change in `models.py` should be
   accompanied by a new `alembic revision --autogenerate` migration in this
   directory, reviewed, and committed alongside the model change.

## Notes

- Do **not** mix `Base.metadata.create_all()` and Alembic migrations once
  Alembic is in use — pick one source of truth.
- The `alembic.ini` and `env.py` config (under `database/migrations/`) should
  already be wired up to import `Base` from `database.models`.
