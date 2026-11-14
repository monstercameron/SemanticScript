"""The refined SemanticScript compiler (docs/language-refinement.md).

A table-driven checker for the refined syntax and an LLVM backend that compiles
the checked model directly. It does not depend on the earlier compiler
(semanticscript.py) and keeps no compatibility with the earlier syntax.
"""
from .check import Result, check_modules, check_path, check_project  # noqa: F401
