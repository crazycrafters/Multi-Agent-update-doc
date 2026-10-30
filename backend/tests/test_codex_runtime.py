import asyncio
import json
import pytest
from app.codex_runtime import CodexRuntime, CodexError
from app.config import Settings


class FakeProcess:
    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.stdin = self
        self.returncode = None
        self.sent = []
        self.destination = "https://auth.openai.com/codex/device"

    def write(self, line):
        msg = json.loads(line)
        self.sent.append(msg)
        if "id" not in msg or "method" not in msg:
            return
        result = {}
        if msg["method"] == "account/read":
            result = {
                "account": {
                    "type": "chatgpt",
                    "email": "private@example.com",
                    "planType": "plus",
                }
            }
        elif msg["method"] == "account/login/start":
            result = {
                "type": "chatgptDeviceCode",
                "verificationUrl": self.destination,
                "loginId": "login1",
                "userCode": "TEST-ONLY",
            }
        self.emit({"id": msg["id"], "result": result})

    def emit(self, message):
        self.stdout.feed_data((json.dumps(message) + "\n").encode())

    async def drain(self):
        pass

    def terminate(self):
        self.returncode = 0
        self.stdout.feed_eof()

    def kill(self):
        self.terminate()

    async def wait(self):
        return self.returncode


async def test_transport_isolates_credentials_denies_server_tools_and_redacts_account(
    tmp_path, monkeypatch
):
    proc = FakeProcess()
    captured = {}

    async def create(*args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return proc

    monkeypatch.setattr("app.codex_runtime.asyncio.create_subprocess_exec", create)
    monkeypatch.setattr("app.codex_runtime.shutil.which", lambda _: "/fake/codex")
    monkeypatch.setenv("GH_TOKEN", "private-github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "private-api-key")
    runtime = CodexRuntime(Settings(codex_home=str(tmp_path / "isolated")))
    try:
        await runtime.start()
        status = await runtime.status()
        assert status["signed_in"] and "private@example.com" not in json.dumps(status)
        assert (
            "GH_TOKEN" not in captured["env"]
            and "OPENAI_API_KEY" not in captured["env"]
        )
        assert captured["env"]["CODEX_HOME"] == str(tmp_path / "isolated")
        assert "features.shell_tool=false" in captured["args"]
        proc.emit(
            {
                "id": 99,
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "untrusted"},
            }
        )
        await asyncio.sleep(0)
        assert any(
            x.get("id") == 99 and x.get("error", {}).get("code") == -32601
            for x in proc.sent
        )
        login = await runtime.begin_login()
        assert login["userCode"] == "TEST-ONLY"
        proc.emit(
            {
                "method": "account/login/completed",
                "params": {"loginId": "login1", "success": True},
            }
        )
        await asyncio.sleep(0)
        assert runtime.login is None
    finally:
        await runtime.close()


async def test_login_rejects_non_openai_authorization_url(tmp_path, monkeypatch):
    proc = FakeProcess()
    proc.destination = "https://evil.example/collect"

    async def create(*args, **kwargs):
        return proc

    monkeypatch.setattr("app.codex_runtime.asyncio.create_subprocess_exec", create)
    monkeypatch.setattr("app.codex_runtime.shutil.which", lambda _: "/fake/codex")
    runtime = CodexRuntime(Settings(codex_home=str(tmp_path / "isolated")))
    try:
        with pytest.raises(CodexError):
            await runtime.begin_login()
        assert runtime.login is None
        assert any(m.get("method") == "account/login/cancel" for m in proc.sent)
    finally:
        await runtime.close()
