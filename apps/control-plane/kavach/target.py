"""The only module that talks HTTP to the system under management.

Detection, verification and the executor all need the target's health, config
and query endpoints. Without one client they would each grow their own urllib
calls, and the set of things Kavach can do to the target would stop being
reviewable in one place.

Deliberately narrow. There is no generic request method, no way to pass an
arbitrary path, and no way to run a command. Every operation is a named method
corresponding to one endpoint the manifest declares.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class TargetError(RuntimeError):
    """The target could not be reached, or refused the request."""


@dataclass(frozen=True)
class TargetEndpoints:
    health: str = "http://localhost:8000/healthz"
    chat: str = "http://localhost:8000/v1/chat"
    config: str = "http://localhost:8000/v1/admin/config"
    admin_token: str = ""


class TargetClient:
    def __init__(self, endpoints: TargetEndpoints | None = None) -> None:
        self.e = endpoints or TargetEndpoints()

    # --- internals ----------------------------------------------------------

    def _call(
        self, url: str, method: str = "GET",
        body: dict[str, Any] | None = None, timeout: float = 30.0,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.e.admin_token:
            headers["X-Admin-Token"] = self.e.admin_token
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            raise TargetError(f"{method} {url} -> HTTP {exc.code}") from exc
        except Exception as exc:
            raise TargetError(f"{method} {url} -> {exc}") from exc

    # --- read ---------------------------------------------------------------

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return dict(self._call(self.e.health, timeout=timeout))

    def is_healthy(self, timeout: float = 10.0) -> bool:
        try:
            return self.health(timeout).get("status") == "ok"
        except TargetError:
            return False

    def config(self, timeout: float = 15.0) -> dict[str, Any]:
        """Settings, config_hash and prompt_version. The pre-state witness."""
        return dict(self._call(self.e.config, timeout=timeout))

    def settings(self) -> dict[str, Any]:
        return dict(self.config().get("settings", {}))

    def config_hash(self) -> str:
        return str(self.config().get("config_hash", ""))

    def ask(self, question: str, timeout: float = 240.0) -> str:
        return str(self._call(self.e.chat, "POST", {"question": question},
                              timeout=timeout)["answer"])

    # --- write --------------------------------------------------------------

    def apply_settings(self, settings: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        """The ONLY write path to the target.

        The target validates and refuses the whole request if any key is
        denied, unknown or out of range, so this cannot be used to reach
        `embed_model` or the database settings.
        """
        return dict(self._call(self.e.config, "PUT", {"settings": settings},
                               timeout=timeout))
