import asyncio
from app import main


async def test_connect_status_disconnect_keeps_key_out_of_responses_and_database(
    env, monkeypatch
):
    c, factory, runner, p = env
    monkeypatch.setattr(main.settings(), "openai_api_key", "")
    secret = "sk-test-sensitive-session-key"
    assert (await c.get("/provider")).json()["configured"] is False
    r = await c.post(
        "/provider/connection",
        json={"api_key": secret},
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200 and {
        k: r.json()[k] for k in ["configured", "source", "verified"]
    } == {
        "configured": True,
        "source": "session",
        "verified": False,
    }
    assert secret not in r.text and runner.config.openai_api_key == secret
    assert (await c.get("/health")).json()["provider_configured"] is True
    assert secret not in (await c.get("/provider")).text
    r = await c.post("/provider/disconnect")
    assert (
        r.status_code == 200
        and not r.json()["configured"]
        and not runner.config.openai_api_key
    )
    await runner.provider.client.close()


async def test_credential_changes_reject_untrusted_origin_active_work_and_missing_auth(
    env, monkeypatch
):
    c, factory, runner, p = env
    r = await c.post(
        "/provider/connection",
        json={"api_key": "sk-test"},
        headers={"Origin": "https://untrusted.example"},
    )
    assert r.status_code == 403 and runner.provider is p
    blocker = asyncio.create_task(asyncio.sleep(60))
    runner.tasks["blocker"] = blocker
    r = await c.post("/provider/connection", json={"api_key": "sk-test"})
    assert r.status_code == 409 and runner.provider is p
    blocker.cancel()
    await asyncio.gather(blocker, return_exceptions=True)
    monkeypatch.setattr(main.settings(), "api_access_token", "test-access")
    assert (
        await c.post("/provider/connection", json={"api_key": "sk-test"})
    ).status_code == 401
    r = await c.post(
        "/provider/connection",
        json={"api_key": ""},
        headers={"Authorization": "Bearer test-access"},
    )
    assert r.status_code == 422 and "api_key" not in r.json().get("error", {}).get(
        "message", ""
    )
