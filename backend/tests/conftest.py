import pytest

from refund_agent.infrastructure.database import SessionLocal, create_schema
from refund_agent.seed import seed_demo_data


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> None:
    create_schema()
    with SessionLocal() as db:
        seed_demo_data(db)
