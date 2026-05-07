"""Daily SQLite backup job.

Uses ``sqlite3 .backup`` via subprocess to create a consistent snapshot
even when the app is mid-write. Backups land in
``DATA_DIR / "backups" / "YYYY-MM-DD.db"``. Older backups beyond
``RETENTION_DAYS`` are deleted on each run.
"""

from datetime import datetime
from pathlib import Path

import anyio

from app.config import DATA_DIR
from app.services.cron_log import cron_run

RETENTION_DAYS: int = 14


def _resolve_db_path() -> Path:
    """Pull the SQLite file path from the configured database_url."""
    from app.config import get_settings

    url = get_settings().database_url
    # 'sqlite+aiosqlite:///./data/app.db' or 'sqlite:///...'
    _, _, path_part = url.partition(":///")
    return Path(path_part).resolve()


async def run_backup() -> None:
    async with cron_run("backup") as meta:
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_path = _resolve_db_path()
        if not db_path.exists():
            meta["skipped"] = "db_not_found"
            return
        target = backup_dir / f"{datetime.utcnow().strftime('%Y-%m-%d')}.db"

        # `sqlite3 source ".backup target"` — atomic snapshot.
        proc = await anyio.run_process(
            ["sqlite3", str(db_path), f".backup '{target}'"],
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"sqlite3 backup exited {proc.returncode}: {proc.stderr.decode()[:200]}"
            )
        meta["target"] = str(target)

        removed = 0
        cutoff = datetime.utcnow().timestamp() - RETENTION_DAYS * 86400
        for entry in backup_dir.iterdir():
            if not entry.is_file() or entry.suffix != ".db":
                continue
            if entry.stat().st_mtime < cutoff:
                entry.unlink(missing_ok=True)
                removed += 1
        meta["pruned"] = removed
