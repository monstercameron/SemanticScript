"""Browser/DOM integration tests for the standard.document wasm target.

Each test builds a SemanticScript program to wasm via emscripten, then runs it
under Node against a real jsdom DOM (the run_dom_harness.js driver) and asserts
on the resulting document. Sync DOM mutation and Asyncify-suspended DOM events
are both covered.

Skipped automatically when the emscripten toolchain (third_party/emsdk) or the
jsdom dev dependency (SemanticScript/tests/wasm_dom/node_modules) is absent, so
the suite stays green without the heavy toolchain.

Install prerequisites (emsdk is an opt-in `update = none` submodule):
    git submodule update --init --checkout third_party/emsdk
    python third_party/emsdk/emsdk.py install latest
    python third_party/emsdk/emsdk.py activate latest
    (cd SemanticScript/tests/wasm_dom && npm install)

Run from repo root:
    python -m unittest SemanticScript/tests/test_wasm_dom.py -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "SemanticScript" / "tools"))

import build_wasm  # noqa: E402

DOM_DIR = REPO_ROOT / "SemanticScript" / "tests" / "wasm_dom"
FIXTURES = DOM_DIR / "fixtures"
HARNESS = DOM_DIR / "run_dom_harness.js"
JSDOM_INSTALLED = (DOM_DIR / "node_modules" / "jsdom").is_dir()

# MODULARIZE so the harness controls instantiation; EXIT_RUNTIME=1 so a
# returning main fires Module.onExit, the harness's completion signal (the
# factory promise is unreliable under Asyncify -- it resolves at suspend, not
# at main's return).
MODULARIZE_ARGS = ["-sMODULARIZE", "-sEXPORT_NAME=createSemModule", "-sEXIT_RUNTIME=1"]

REQS_MET = build_wasm.toolchain_ready() and JSDOM_INSTALLED and HARNESS.is_file()


def _build(name: str, out_dir: Path) -> Path:
    out_js = out_dir / f"{name}.js"
    build_wasm.build_wasm(FIXTURES / f"{name}.sem", out_js, extra_args=MODULARIZE_ARGS)
    return out_js


def _run_harness(config: dict) -> dict:
    result = subprocess.run(
        ["node", str(HARNESS), json.dumps(config)],
        cwd=DOM_DIR,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"harness produced no output:\n{result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])


@unittest.skipUnless(
    REQS_MET,
    "requires emscripten toolchain (third_party/emsdk) and jsdom "
    "(SemanticScript/tests/wasm_dom npm install)",
)
class WasmDomTest(unittest.TestCase):
    def test_sync_dom_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_mutation", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": "<!DOCTYPE html><html><body></body></html>",
            })
        self.assertTrue(res.get("ok"), res)
        # The wasm program created and appended the greeting div.
        self.assertIn('id="greeting"', res["bodyHtml"])
        self.assertIn('class="banner"', res["bodyHtml"])
        self.assertIn("hello-from-wasm", res["bodyHtml"])

    def test_dom_event_resumes_on_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_event", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": '<!DOCTYPE html><html><body><button id="btn">go</button></body></html>',
                "actions": [{"selector": "#btn", "type": "click", "delayMs": 40}],
                "timeoutMs": 8000,
            })
        self.assertTrue(res.get("ok"), res)
        # main suspended on nextEvent and only set the marker after the click.
        self.assertEqual(res["bodyHtml"], "clicked")

    def test_event_target_identifies_element(self):
        # After a click, eventTarget must return the clicked node; the program
        # mutates that exact node, proving the event payload is usable.
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_event_target", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": '<!DOCTYPE html><html><body><button id="btn">go</button></body></html>',
                "actions": [{"selector": "#btn", "type": "click", "delayMs": 40}],
                "timeoutMs": 8000,
            })
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["bodyHtml"], '<button id="btn">hit</button>')

    def test_multiple_events_redeliver(self):
        # Two clicks: the stream re-parks between awaits and delivers both.
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_multi_event", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": '<!DOCTYPE html><html><body><button id="btn">go</button></body></html>',
                "actions": [
                    {"selector": "#btn", "type": "click", "delayMs": 40},
                    {"selector": "#btn", "type": "click", "delayMs": 120},
                ],
                "timeoutMs": 8000,
            })
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["bodyHtml"], '<button id="btn">second</button>')

    def test_eval_script_escape_hatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_eval", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": "<!DOCTYPE html><html><body></body></html>",
            })
        self.assertTrue(res.get("ok"), res)
        self.assertIn('id="evaled"', res["bodyHtml"])

    def test_negative_status_drives_control_flow(self):
        # appendChild against a not-found (querySelector miss) handle returns
        # domStatusDetached (-4); the program branches on it via math.equalInt32.
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_negative", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": "<!DOCTYPE html><html><body></body></html>",
            })
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["exitCode"], 0)
        self.assertEqual(res["bodyHtml"], "detached-rejected")

    def test_dom_event_blocks_without_dispatch(self):
        # No dispatched event: nextEvent must keep main suspended until the hard
        # timeout, proving the await genuinely blocks rather than returning eagerly.
        with tempfile.TemporaryDirectory() as tmp:
            out_js = _build("dom_event", Path(tmp))
            res = _run_harness({
                "module": str(out_js),
                "html": '<!DOCTYPE html><html><body><button id="btn">go</button></body></html>',
                "actions": [],
                "timeoutMs": 1200,
            })
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "timeout")
        # body was never marked, because main never resumed.
        self.assertNotEqual(res.get("bodyHtml"), "clicked")


if __name__ == "__main__":
    unittest.main()
