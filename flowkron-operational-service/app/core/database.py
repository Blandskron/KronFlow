from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.schema import CreateSchema
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_options = {"pool_pre_ping": True, "future": True}
if settings.database_url.startswith("postgresql"):
    engine_options["connect_args"] = {
        "options": f"-c search_path={settings.database_schema},public",
    }
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_public_tables() -> None:
    from app import public_models  # noqa: F401

    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(CreateSchema(settings.database_schema, if_not_exists=True))
    public_tables = [table for table in Base.metadata.sorted_tables if table.schema in (None, "public")]
    Base.metadata.create_all(bind=engine, tables=public_tables)


def check_database() -> bool:
    with engine.connect() as connection:
        return connection.execute(select(1)).scalar_one() == 1
