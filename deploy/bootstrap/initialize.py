import os
import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote


def write(path: Path, value: str) -> str:
    if path.is_file() and path.read_text(encoding="utf-8") == value:
        return value
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(value.encode())
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o444)
    temporary_path.replace(path)
    return value


def credential(path: Path, variable: str = "") -> str:
    value = os.environ.get(variable) if variable else None
    if not value:
        value = path.read_text(encoding="utf-8") if path.is_file() else secrets.token_urlsafe(36)
    return write(path, value)


def initialize():
    postgres = Path("/bootstrap/postgres")
    iam = Path("/bootstrap/iam")
    operational = Path("/bootstrap/operational")
    agent = Path("/bootstrap/agent")
    channel = Path("/bootstrap/channel")

    password = credential(postgres / "password", "POSTGRES_PASSWORD")
    user = quote(os.environ["POSTGRES_USER"], safe="")
    database = quote(os.environ["POSTGRES_DB"], safe="")
    target = f"{user}:{quote(password, safe='')}@postgres:5432/{database}"
    write(iam / "database_url", os.environ.get("DATABASE_URL") or f"postgresql://{target}")
    write(
        operational / "database_url",
        os.environ.get("OPERATIONAL_DATABASE_URL") or f"postgresql+psycopg://{target}",
    )
    credential(iam / "django_secret_key", "DJANGO_SECRET_KEY")
    credential(iam / "signing_key_encryption_key", "SIGNING_KEY_ENCRYPTION_KEY")
    credential(iam / "bootstrap_admin_password")
    token = credential(iam / "operational_internal_token", "OPERATIONAL_INTERNAL_TOKEN")
    write(operational / "internal_token", token)
    write(agent / "internal_token", token)
    baileys_token = credential(channel / "internal_token", "BAILEYS_INTERNAL_TOKEN")
    for service in (iam, operational, agent):
        write(service / "baileys_internal_token", baileys_token)


if __name__ == "__main__":
    initialize()
