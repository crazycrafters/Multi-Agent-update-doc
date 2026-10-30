import os
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import Base
from app import main
from app.workflow import Workflow
from app.config import Settings
from httpx import AsyncClient, ASGITransport
from tests.provider import TestProvider


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    if url.startswith("postgresql"):
        assert url.endswith("/resume_test"), (
            "Tests require a dedicated resume_test database"
        )
    engine = create_async_engine(url)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = TestProvider()
    runner = Workflow(factory, provider, Settings(max_iteration_tokens=1000000))
    monkeypatch.setattr(main, "workflow", runner)
    monkeypatch.setattr(main, "Session", factory)
    main.rate.clear()
    main.locks.clear()

    async def get_db():
        async with factory() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = get_db
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        yield client, factory, runner, provider
    await runner.shutdown()
    main.app.dependency_overrides.clear()
    await engine.dispose()
