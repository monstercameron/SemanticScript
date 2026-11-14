"""R-068: human-authoring validation must have a concrete protocol."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_human_authoring_protocol_defines_metrics_thresholds_and_blocker() -> None:
    protocol = (ROOT / "docs" / "human-authoring-validation.md").read_text(encoding="utf-8")

    for section in [
        "## Participant Profile",
        "## Materials",
        "## Tasks",
        "## Metrics",
        "## Friction Taxonomy",
        "## Decision Thresholds",
        "## Session Report Template",
        "## Session Reports",
    ]:
        assert section in protocol

    for required in [
        "one non-maintainer session",
        "Time to first correct mental model",
        "Time to successful edit",
        "Review misses",
        "No completed human-authoring session recorded yet.",
    ]:
        assert required in protocol


def test_roadmap_and_language_point_at_human_authoring_protocol() -> None:
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    language = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")

    assert "protocol ready; participant session pending" in roadmap
    assert "docs/human-authoring-validation.md" in roadmap
    assert "Protocol ready; session pending" in language
    assert "docs/human-authoring-validation.md" in language
