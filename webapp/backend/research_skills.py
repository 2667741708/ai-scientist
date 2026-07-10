from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ResearchSkill:
    skill_id: str
    title: str
    purpose: str
    phases: tuple[str, ...]
    checklist: tuple[str, ...]
    expected_outputs: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "title": self.title,
            "purpose": self.purpose,
            "phases": list(self.phases),
            "checklist": list(self.checklist),
            "expected_outputs": list(self.expected_outputs),
        }


RESEARCH_SKILLS: tuple[ResearchSkill, ...] = (
    ResearchSkill(
        skill_id="evidence-grounding-rubric",
        title="Evidence Grounding Rubric",
        purpose="Score whether a hypothesis is supported by parsed fulltext, metadata, experiments, or weak public evidence.",
        phases=("literature_review", "hypothesis_generation", "review_critique", "writing"),
        checklist=(
            "Separate fulltext support from abstract-only or metadata-only support.",
            "Record source_reliability, support_level, retrieval query, and evidence_id.",
            "Flag ungrounded claims when no knowledge base or MCP evidence is available.",
            "Prefer parsed_fulltext and experimental_data support for technical claims.",
        ),
        expected_outputs=(
            "grounding_status",
            "hypothesis_evidence_links",
            "evidence_retrievals",
            "grounding_limitation",
        ),
    ),
    ResearchSkill(
        skill_id="falsifiability-review",
        title="Falsifiability Review",
        purpose="Convert optimistic hypotheses into claims with testable failure conditions and negative-result interpretations.",
        phases=("review_critique", "experiment_design", "meta_review"),
        checklist=(
            "State the primary measurable outcome and decision threshold.",
            "Define at least one negative control or failure condition.",
            "Explain what result would falsify or weaken the hypothesis.",
            "Check feasibility, novelty, scientific soundness, and safety concerns.",
        ),
        expected_outputs=(
            "validation_plan",
            "failure_conditions",
            "negative_result_interpretation",
            "review_feedback",
        ),
    ),
    ResearchSkill(
        skill_id="experiment-design-checklist",
        title="Experiment Design Checklist",
        purpose="Turn a hypothesis into a reproducible experiment plan with datasets, baselines, metrics, and analysis steps.",
        phases=("experiment_design", "experiment_analysis"),
        checklist=(
            "Name datasets, splits, baselines, metrics, and statistical tests.",
            "Separate data preprocessing from model or method changes.",
            "Specify compute/runtime assumptions and reproducibility artifacts.",
            "Link any calculated result back to code.execute_analysis or an experiment background job result_ref.",
        ),
        expected_outputs=(
            "dataset_plan",
            "baseline_plan",
            "metric_plan",
            "analysis_result_ref",
        ),
    ),
    ResearchSkill(
        skill_id="citation-provenance-qa",
        title="Citation Provenance QA",
        purpose="Audit whether citations and source claims are traceable to stored evidence rather than latent model memory.",
        phases=("evidence_audit", "review_critique", "writing"),
        checklist=(
            "Verify each citation has a source id, URL/DOI/path, and source reliability.",
            "Check that citation text supports the specific claim being made.",
            "Flag public HTML or metadata-only sources as weak support when fulltext is unavailable.",
            "Ensure tool results and retrievals are stored before using them in final writing.",
        ),
        expected_outputs=(
            "citation_map",
            "provenance_qa_status",
            "weak_support_warnings",
            "missing_evidence_tasks",
        ),
    ),
)


def list_research_skills(phase: Optional[str] = None) -> List[Dict[str, Any]]:
    skills = RESEARCH_SKILLS
    if phase:
        skills = tuple(skill for skill in skills if phase in skill.phases)
    return [skill.to_dict() for skill in skills]


def get_research_skill(skill_id: str) -> Optional[Dict[str, Any]]:
    for skill in RESEARCH_SKILLS:
        if skill.skill_id == skill_id:
            return skill.to_dict()
    return None
