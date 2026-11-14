"""Pytest fixture-discovery hook for the SemanticScript test suite.

Puts the compiler package dir (semanticscript/compiler/) on sys.path so every
test under tests/ can `import semanticscript` regardless of pytest's import mode
or the directory the suite is launched from.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "semanticscript", "compiler"))
