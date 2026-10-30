"""Pinned Codex app-server JSON-RPC transport. No browser cookies or token extraction."""

import asyncio
import contextlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit


class CodexError(RuntimeError):
    pass


class CodexRuntime:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.reader = None
        self.pending = {}
        self.queues = {}
        self.next_id = 0
        self.start_lock = asyncio.Lock()
        self.turn_lock = asyncio.Lock()
        self.login = None
        self.login_error = None
        self.generation = 0
        self.workspace = str(Path(config.codex_home).resolve() / "workspace")

    @property
    def available(self):
        return shutil.which(self.config.codex_binary) is not None

    async def start(self):
        async with self.start_lock:
            if self.process and self.process.returncode is None:
                return
            if not self.available:
                raise CodexError("Codex CLI is not installed")
            home = Path(self.config.codex_home).resolve()
            home.mkdir(parents=True, exist_ok=True, mode=0o700)
            Path(self.workspace).mkdir(exist_ok=True, mode=0o700)
            # A dedicated auth/config directory; never read or share the host user's Codex credentials.
            keep = {
                "PATH",
                "HOME",
                "LANG",
                "TMPDIR",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "no_proxy",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
                "NODE_EXTRA_CA_CERTS",
            }
            child_env = {k: v for k, v in os.environ.items() if k in keep}
            child_env["CODEX_HOME"] = str(home)
            config = {
                "forced_login_method": "chatgpt",
                "cli_auth_credentials_store": "file",
                "project_doc_max_bytes": 0,
                "web_search": "disabled",
                "features.shell_tool": False,
                "features.unified_exec": False,
                "features.apply_patch_freeform": False,
                "features.code_mode": False,
                "features.multi_agent": False,
                "features.apps": False,
                "features.connectors": False,
                "features.plugins": False,
                "features.memories": False,
                "mcp_servers": {},
            }
            args = [self.config.codex_binary, "app-server", "--listen", "stdio://"]
            for key, value in config.items():
                # These overrides are TOML, not JSON. An empty table uses TOML inline-table syntax.
                args += ["-c", f"{key}=" + ("{}" if value == {} else json.dumps(value))]
            self.process = await asyncio.create_subprocess_exec(
                *args,
                cwd=self.workspace,
                env=child_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=8 * 1024 * 1024,
            )
            self.reader = asyncio.create_task(self.read_messages())
            self.generation += 1
            try:
                await self.rpc(
                    "initialize",
                    {"clientInfo": {"name": "resume_evolution", "version": "0.1.0"}},
                    start=False,
                )
                await self.send({"method": "initialized", "params": {}})
            except BaseException:
                await self.close()
                raise

    async def send(self, message):
        if not self.process or self.process.returncode is not None:
            raise CodexError("Codex process unavailable")
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def rpc(self, method, params=None, start=True):
        if start:
            await self.start()
        self.next_id += 1
        identifier = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        try:
            await self.send(
                {"id": identifier, "method": method, "params": params or {}}
            )
            try:
                return await asyncio.wait_for(future, 30)
            except asyncio.TimeoutError:
                raise CodexError("Codex request timed out") from None
        finally:
            self.pending.pop(identifier, None)

    async def read_messages(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message:
                    if "id" in message:
                        # No shell, file changes, approvals, MCP calls or prompts can escape the adapter.
                        await self.send(
                            {
                                "id": message["id"],
                                "error": {
                                    "code": -32601,
                                    "message": "Tool execution is not permitted by this application",
                                },
                            }
                        )
                        continue
                    params = message.get("params") or {}
                    if message["method"] == "account/login/completed":
                        if self.login and params.get("loginId") == self.login.get(
                            "loginId"
                        ):
                            self.login = None
                            self.login_error = (
                                None
                                if params.get("success")
                                else "Sign-in failed or expired. Start again."
                            )
                    queue = self.queues.get(params.get("threadId"))
                    if queue:
                        await queue.put(message)
                else:
                    future = self.pending.get(message.get("id"))
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                CodexError(
                                    "Codex request failed; check login, model availability and account limits"
                                )
                            )
                        else:
                            future.set_result(message.get("result", {}))
            raise CodexError("Codex process disconnected")
        except asyncio.CancelledError:
            raise
        except Exception:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(CodexError("Codex transport disconnected"))
            for queue in self.queues.values():
                await queue.put({"method": "transport_error"})

    async def status(self):
        if not self.process or self.process.returncode is not None:
            return {
                "available": self.available,
                "signed_in": False,
                "pending_login": None,
                "error": None,
            }
        result = await self.rpc("account/read", {"refreshToken": False})
        account = result.get("account") or {}
        return {
            "available": True,
            "signed_in": account.get("type") == "chatgpt",
            "pending_login": self.login,
            "error": self.login_error,
        }

    async def begin_login(self):
        if self.login:
            return self.login
        result = await self.rpc("account/login/start", {"type": "chatgptDeviceCode"})
        url = result.get("verificationUrl", "")
        if (
            result.get("type") != "chatgptDeviceCode"
            or urlsplit(url).scheme != "https"
            or urlsplit(url).hostname != "auth.openai.com"
        ):
            if result.get("loginId"):
                await self.rpc("account/login/cancel", {"loginId": result["loginId"]})
            raise CodexError("Codex returned an unsupported sign-in destination")
        self.login = {k: result[k] for k in ["loginId", "userCode", "verificationUrl"]}
        self.login_error = None
        return self.login

    async def logout(self):
        if self.login:
            await self.rpc("account/login/cancel", {"loginId": self.login["loginId"]})
        await self.rpc("account/logout")
        self.login = None
        self.login_error = None
        await self.close()

    async def close(self):
        process = self.process
        self.process = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self.reader and self.reader is not asyncio.current_task():
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader
        self.reader = None
        self.queues.clear()
