from types import SimpleNamespace

import pytest

from refund_agent.infrastructure import migrations


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
