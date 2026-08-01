from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from refund_agent.config import get_settings
from refund_agent.infrastructure.checkpoint import setup_checkpointer
from refund_agent.infrastructure.database import SessionLocal, engine
from refund_agent.seed import seed_demo_data

V1_TABLES = {
    "approval_tasks",
    "audit_events",
    "conversations",
    "knowledge_documents",
    "messages",
    "orders",
    "refund_requests",
    "tickets",
    "users",
    "workflow_checkpoints",
}


def _alembic_config() -> Config:
    project_dir = Path(__file__).resolve().parents[3]
    config = Config(str(project_dir / "alembic.ini"))
    config.set_main_option("script_location", str(project_dir / "migrations"))
    return config


def migrate_database() -> None:
    config = _alembic_config()
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        if not V1_TABLES.issubset(tables):
            missing = ", ".join(sorted(V1_TABLES - tables))
            raise RuntimeError(f"Cannot adopt unknown database; missing v1 tables: {missing}")
        command.stamp(config, "0001")
    command.upgrade(config, "head")


def main() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        raise RuntimeError("The migration service requires PostgreSQL")
    migrate_database()
    setup_checkpointer(settings)
    with SessionLocal() as db:
        seed_demo_data(db)


if __name__ == "__main__":
    main()
