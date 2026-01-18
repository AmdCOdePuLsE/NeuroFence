from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class NeuroFenceClient:
    """HTTP client for the NeuroFence API."""

    base_url: str = "http://localhost:8000"
    timeout_seconds: float = 20.0

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def health(self) -> Dict[str, Any]:
        resp = requests.get(self._url("/health"), timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def intercept(self, sender: str, recipient: Optional[str], content: str) -> Dict[str, Any]:
        resp = requests.post(
            self._url("/intercept"),
            json={"sender": sender, "recipient": recipient, "content": content},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def isolate(self, agent_name: str, reason: str) -> Dict[str, Any]:
        resp = requests.post(
            self._url(f"/isolate/{agent_name}"),
            json={"reason": reason},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def release(self, agent_name: str) -> Dict[str, Any]:
        resp = requests.post(self._url(f"/release/{agent_name}"), timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def stats(self) -> Dict[str, Any]:
        resp = requests.get(self._url("/stats"), timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def forensics(self, agent_name: str) -> Dict[str, Any]:
        resp = requests.get(self._url(f"/forensics/{agent_name}"), timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()
