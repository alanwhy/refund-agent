from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from refund_agent.infrastructure import migrations
from refund_agent.infrastructure.database import engine


class FakeInspector:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables

    def get_table_names(self) -> list[str]:
        return sorted(self.tables)


def test_empty_database_upgrades_without_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(migrations, "inspect", lambda engine: FakeInspector(set()))
    monkeypatch.setattr(
        migrations,
        "command",
        SimpleNamespace(
            stamp=lambda config, revision: calls.append(("stamp", revision)),
            upgrade=lambda config, revision: calls.append(("upgrade", revision)),
        ),
    )

    migrations.migrate_database()

    assert calls == [("upgrade", "head")]


def test_complete_legacy_schema_is_stamped_then_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migrations,
        "inspect",
        lambda engine: FakeInspector(set(migrations.V1_TABLES)),
    )
    monkeypatch.setattr(
        migrations,
        "command",
        SimpleNamespace(
            stamp=lambda config, revision: calls.append(("stamp", revision)),
            upgrade=lambda config, revision: calls.append(("upgrade", revision)),
        ),
    )

    migrations.migrate_database()

    assert calls == [("stamp", "0001"), ("upgrade", "head")]


def test_partial_legacy_schema_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        migrations,
        "inspect",
        lambda engine: FakeInspector({"users", "tickets"}),
    )

    with pytest.raises(RuntimeError, match="missing v1 tables"):
        migrations.migrate_database()


def test_demo_order_creation_schema_has_constraints_and_foreign_keys() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("demo_order_creations")}
    indexes = {index["name"]: index for index in inspector.get_indexes("demo_order_creations")}
    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): (
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("demo_order_creations")
    }

    assert columns == {
        "id",
        "request_id",
        "order_id",
        "created_by",
        "scenario",
        "created_at",
    }
    assert indexes["ix_demo_order_creations_request_id"]["unique"] is True
    assert indexes["ix_demo_order_creations_order_id"]["unique"] is True
    assert "ix_demo_order_creations_created_by" in indexes
    assert "ix_demo_order_creations_created_at" in indexes
    assert foreign_keys[("order_id",)] == ("orders", ("id",))
    assert foreign_keys[("created_by",)] == ("users", ("id",))
