import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_event_contract_is_runtime_backed_not_deferred():
    semsig = (ROOT / "semanticscript" / "sigs" / "standard.event.semsig").read_text(encoding="utf-8")
    assert "deferred runtime" not in semsig.lower()
    assert "ss_event_* native runtime" in semsig

    manifest = json.loads((ROOT / "semanticscript" / "runtime" / "manifest.json").read_text(encoding="utf-8"))
    event_libs = [library for library in manifest["libraries"] if library.get("name") == "ss_event"]
    assert event_libs == [{
        "name": "ss_event",
        "comment": "APP-RUN-3 in-process event pub/sub (event.*): a stream queue + per-subscription cursor, no external deps.",
        "provides": ["ss_event_"],
        "sources": ["ss_event.c"],
    }]
