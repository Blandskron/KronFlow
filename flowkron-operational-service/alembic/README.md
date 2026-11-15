Alembic is reserved for public schema migrations.

Tenant schema tables are declared as SQLAlchemy 2.0 ORM models under `app/tenant_models` with `__table_args__ = {"schema": "tenant"}` and applied per schema using `schema_translate_map`.

`alembic/env.py` excludes tenant models from public autogeneration. Tenant migrations are executed for every active runtime through `scripts/migrate_all_tenants.py`.
