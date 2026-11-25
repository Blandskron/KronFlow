#!/bin/sh
set -eu

if [ -n "${DATABASE_URL_FILE:-}" ]; then
  DATABASE_URL="$(cat "$DATABASE_URL_FILE")"
  export DATABASE_URL
fi

run_bool() {
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [ "$value" = "1" ] || [ "$value" = "true" ] || [ "$value" = "yes" ]
}

wait_for_database() {
  if [ -z "${DATABASE_URL:-}" ]; then
    return 0
  fi

  python - <<'PY'
import os
from urllib.parse import urlparse

url = urlparse(os.environ["DATABASE_URL"])
host = url.hostname or ""
port = url.port or 5432
print(f"{host}:{port}")
PY
}

db_target="$(wait_for_database)"
if [ -n "$db_target" ]; then
  db_host="${db_target%:*}"
  db_port="${db_target##*:}"
  echo "Waiting for database ${db_host}:${db_port}..."
  attempts=0
  until nc -z "$db_host" "$db_port"; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      echo "Database did not become reachable within 60 seconds." >&2
      exit 1
    fi
    sleep 1
  done
fi

if [ -n "${DATABASE_URL:-}" ]; then
  python - <<'PY'
import os
import re

import django
from django.conf import settings
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

schema = getattr(settings, "AUTH_DATABASE_SCHEMA", os.environ.get("AUTH_DATABASE_SCHEMA", "auth_"))
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
    raise SystemExit("AUTH_DATABASE_SCHEMA must be a valid PostgreSQL identifier.")

if connection.vendor == "postgresql":
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
PY
fi

if run_bool "${GENERATE_JWT_KEYS:-true}"; then
  if [ -z "${JWT_PRIVATE_KEY:-}" ] && [ -z "${JWT_PUBLIC_KEY:-}" ]; then
    private_path="${JWT_PRIVATE_KEY_PATH:-keys/jwt_private.pem}"
    public_path="${JWT_PUBLIC_KEY_PATH:-keys/jwt_public.pem}"
    if [ ! -f "$private_path" ] || [ ! -f "$public_path" ]; then
      python scripts/generate_jwt_keys.py
    fi
  fi
fi

if run_bool "${RUN_MIGRATIONS:-true}"; then
  python manage.py migrate --noinput
fi

if run_bool "${RUN_SEEDS:-true}"; then
  python manage.py seed_iam
  python manage.py seed_iam_advanced
fi

if run_bool "${RUN_COLLECTSTATIC:-true}"; then
  echo "Collecting static files for WhiteNoise..."
  python manage.py collectstatic --noinput
fi

if run_bool "${CREATE_SUPERUSER:-false}"; then
  python manage.py bootstrap_local_workspace --explicit
elif run_bool "${FLOWKRON_BOOTSTRAP_ADMIN:-false}" && run_bool "${DJANGO_DEBUG:-false}"; then
  case "${FLOWKRON_BIND_HOST:-127.0.0.1}" in
    127.0.0.1) python manage.py bootstrap_local_workspace ;;
  esac
fi

if run_bool "${FLOWKRON_PROVISION_WORKSPACES:-false}"; then
  python manage.py provision_open_workspaces
fi

exec "$@"
