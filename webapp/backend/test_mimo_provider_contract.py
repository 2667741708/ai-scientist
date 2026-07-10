from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_mimo_provider_contract_and_health(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        monkeypatch.setenv("XIAOMI_MIMO_API_KEY", "test-mimo-key")
        studio = load_studio(tmp)

        provider = studio.provider_for_model("openai/mimo-v2.5-pro")
        assert provider["provider"] == "mimo"
        assert "MIMO_API_KEY" in provider["env_vars"]
        assert studio.has_model_provider_key("openai/mimo-v2.5-pro")

        client = TestClient(studio.app)
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["has_mimo_key"] is True
        assert payload["providers"]["mimo"]["usable"] is True
