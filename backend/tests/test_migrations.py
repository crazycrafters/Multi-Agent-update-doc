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


def test_legacy_resume_backfills_separate_profile_without_losing_original(tmp_path):
    import sqlite3

    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "legacy.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    for target in ["c21a98b7d004"]:
        subprocess.run(
            [str(root / ".venv/bin/alembic"), "upgrade", target],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
        )
    with sqlite3.connect(path) as db:
        stamp = "2026-01-01 00:00:00"
        db.execute(
            "INSERT INTO users (id,created_at,name) VALUES (?,?,?)",
            ("u", stamp, "Candidate"),
        )
        db.execute(
            "INSERT INTO resumes (id,created_at,user_id,title,original_text,target_role,job_description,current_version_id) VALUES (?,?,?,?,?,?,?,?)",
            (
                "r",
                stamp,
                "u",
                "Legacy",
                "Original immutable resume",
                "Engineer",
                "Historical target",
                None,
            ),
        )
        db.commit()
    result = subprocess.run(
        [str(root / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT r.original_text,p.target_role FROM resumes r JOIN profiles p ON p.id=r.profile_id WHERE r.id=?",
            ("r",),
        ).fetchone()
        assert row == ("Original immutable resume", "Engineer")
