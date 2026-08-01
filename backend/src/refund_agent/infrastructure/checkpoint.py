from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from refund_agent.config import Settings, get_settings


def create_checkpoint_pool(settings: Settings | None = None) -> Any:
    current = settings or get_settings()
    if current.database_url.startswith("sqlite"):
        raise RuntimeError("PostgresSaver requires PostgreSQL")
    return ConnectionPool(
        conninfo=current.checkpoint_database_url,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )


def setup_checkpointer(settings: Settings | None = None) -> None:
    current = settings or get_settings()
    with PostgresSaver.from_conn_string(current.checkpoint_database_url) as saver:
        saver.setup()
