"""R-056: guard the integrated VS Code editor surface."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "vscode-semanticscript"


def test_vscode_extension_registers_r056_editor_surface() -> None:
    extension = (EXTENSION_DIR / "extension.js").read_text(encoding="utf-8")
    package = json.loads((EXTENSION_DIR / "package.json").read_text(encoding="utf-8"))

    for provider in [
        "registerDocumentSemanticTokensProvider",
        "registerHoverProvider",
        "registerDefinitionProvider",
        "registerDocumentSymbolProvider",
        "registerCompletionItemProvider",
        "registerRenameProvider",
        "registerInlayHintsProvider",
        "registerCodeActionsProvider",
    ]:
        assert provider in extension

    assert "provideRenameEdits" in extension
    assert "prepareRename" in extension
    assert "provideInlayHints" in extension
    assert "semanticscript.runFixPlan" in extension
    assert "'check', '--json'" in extension
    assert "semanticscript.py build" in (EXTENSION_DIR / "README.md").read_text(encoding="utf-8")

    commands = {entry["command"] for entry in package["contributes"]["commands"]}
    activation_events = set(package["activationEvents"])
    assert "semanticscript.runFixPlan" in commands
    assert "onCommand:semanticscript.runFixPlan" in activation_events


def test_vscode_readme_matches_current_compiler_surface() -> None:
    readme = (EXTENSION_DIR / "README.md").read_text(encoding="utf-8")

    assert "same-file rename" in readme
    assert "Inlay hints" in readme
    assert "semanticscript.py check --json" in readme
    assert "semanticscript.py fix --plan" in readme
    assert "semlint.py" not in readme
    assert "semsc.py" not in readme
