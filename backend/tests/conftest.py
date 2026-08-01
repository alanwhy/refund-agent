import os

import pytest

os.environ["LLM_BASE_URL"] = "http://model.invalid/v1"
os.environ["LLM_API_KEY"] = "test-only-key"
os.environ["LLM_MODEL"] = "scripted-test-model"
os.environ["SERVICE_ROLE"] = "test"

from refund_agent.infrastructure.database import SessionLocal, create_schema
from refund_agent.seed import seed_demo_data


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> None:
    create_schema()
    with SessionLocal() as db:
        seed_demo_data(db)
