"""HTTP client used by the MCP tool surface."""

import threading
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import DEFAULT_CONFIG_NAME, find_config, load_config
from .project_server import SharedProjectServer


class ProjectSetupError(RuntimeError):
    def __init__(self, config_path: Path, error: Exception):
        super().__init__(f"{config_path}: {error}")
        self.config_path = config_path


class ProjectClient:
    def __init__(self, shared: SharedProjectServer):
        self.shared = shared

    async def request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        response = await self._request(method, path, body, timeout=timeout)
        return response.json() if response.content else None

    async def get_bytes(self, path: str, timeout: float) -> bytes:
        return (await self._request("GET", path, None, timeout=timeout)).content

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> httpx.Response:
        try:
            self.shared.ensure()
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    f"http://127.0.0.1:{self.shared.port}{path}",
                    json=body,
                )
        except (httpx.HTTPError, RuntimeError) as error:
            raise RuntimeError(f"project server request failed: {error}") from error
        if response.status_code >= 400:
            raise RuntimeError(f"project server request failed ({response.status_code}): {response.text}")
        return response


class ProjectBinding:
    """Bind one MCP process to the project discovered from its startup directory."""

    def __init__(self, start_dir: Path):
        self.start_dir = start_dir.resolve()
        self._lock = threading.Lock()
        self._shared: SharedProjectServer | None = None
        self._client: ProjectClient | None = None

    def connect(self) -> ProjectClient | None:
        with self._lock:
            if self._client is not None:
                return self._client
            config_path = find_config(self.start_dir)
            if config_path is None:
                return None
            try:
                config = load_config(config_path)
                shared = SharedProjectServer(config)
                shared.ensure()
            except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as error:
                raise ProjectSetupError(config_path, error) from error
            self._shared = shared
            self._client = ProjectClient(shared)
            return self._client

    def require_client(self) -> ProjectClient:
        client = self.connect()
        if client is None:
            raise RuntimeError(
                f"{DEFAULT_CONFIG_NAME} was not found from {self.start_dir}; "
                "call inspect() for project setup instructions"
            )
        return client

    def setup_state(self) -> dict[str, Any]:
        return {
            "setup_required": {
                "project_dir": str(self.start_dir),
                "config_path": str(self.start_dir / DEFAULT_CONFIG_NAME),
                "next_action": (
                    "Run html-mcp-web init in project_dir with the requested layout, main file, and port "
                    "(add --template and --content for a templated deck), then call inspect() again."
                ),
            }
        }

    def setup_error_state(self, error: ProjectSetupError) -> dict[str, Any]:
        return {
            "setup_error": {
                "config_path": str(error.config_path),
                "message": str(error),
                "next_action": "Correct the project configuration, then call inspect() again.",
            }
        }

    def stop(self) -> None:
        with self._lock:
            if self._shared is not None:
                self._shared.stop()
            self._shared = None
            self._client = None
