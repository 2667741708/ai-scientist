from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def test_research_skills_api_lists_phase_filtered_rubrics() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")
        client = TestClient(studio.app)

        listed = client.get("/api/research-skills", params={"phase": "review"})
        assert listed.status_code == 200
        skill_ids = {item["skill_id"] for item in listed.json()["skills"]}
        assert "falsifiability-review" in skill_ids
        assert "citation-provenance-qa" in skill_ids

        detail = client.get("/api/research-skills/evidence-grounding-rubric")
        assert detail.status_code == 200
        assert "source_reliability" in " ".join(detail.json()["skill"]["checklist"])

        missing = client.get("/api/research-skills/missing")
        assert missing.status_code == 404


if __name__ == "__main__":
    test_research_skills_api_lists_phase_filtered_rubrics()
    print("research skills API tests passed")
