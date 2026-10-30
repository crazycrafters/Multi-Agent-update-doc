import os
import subprocess
from pathlib import Path


def test_migration_upgrade_downgrade_upgrade(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/migrations.db",
    }
    alembic = root / ".venv/bin/alembic"
    for command in [
        ("upgrade", "head"),
        ("check",),
        ("downgrade", "base"),
        ("upgrade", "head"),
    ]:
        result = subprocess.run(
            [str(alembic), *command],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
