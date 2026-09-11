"""Safe SQLite backup and recovery-drill verification."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path


def create_backup(source: str | Path, output: str | Path) -> dict[str, object]:
    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if source_path == output_path:
        raise ValueError("Backup output must differ from source database")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with (
            sqlite3.connect(source_path) as source_connection,
            sqlite3.connect(temporary_path) as backup_connection,
        ):
            source_connection.backup(backup_connection)
            integrity = backup_connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError("Backup integrity check failed")
        temporary_path.chmod(0o600)
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return verify_backup(output_path)


def verify_backup(path: str | Path) -> dict[str, object]:
    backup_path = Path(path).expanduser().resolve()
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    uri = f"file:{backup_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = sorted(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
    return {
        "status": "verified" if integrity == "ok" else "invalid",
        "integrity": integrity,
        "path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "table_count": len(tables),
        "tables": tables,
        "verified_at": datetime.now().astimezone().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up and verify the platform SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--source", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()
    result = (
        create_backup(args.source, args.output)
        if args.command == "backup"
        else verify_backup(args.path)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "verified" else 1)


if __name__ == "__main__":
    main()
