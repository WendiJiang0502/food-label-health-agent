from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from food_label_agent.persistence.backup import create_backup, verify_backup


def test_sqlite_backup_is_atomic_private_and_verified(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    output = tmp_path / "backups" / "snapshot.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE records (id TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO records VALUES ('one', '已确认')")
        connection.commit()

    report = create_backup(source, output)

    assert report["status"] == "verified"
    assert report["tables"] == ["records"]
    assert output.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "已确认"
    assert not list(output.parent.glob("*.tmp"))


def test_backup_refuses_to_overwrite_live_database(tmp_path: Path) -> None:
    database = tmp_path / "source.sqlite3"
    database.touch()

    with pytest.raises(ValueError, match="must differ"):
        create_backup(database, database)


def test_verify_rejects_missing_backup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify_backup(tmp_path / "missing.sqlite3")
