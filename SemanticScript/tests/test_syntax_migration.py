import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import syntax_migration  # noqa: E402


def check(label, predicate, message=""):
    if not predicate:
        raise AssertionError(f"{label}: {message}")


def test_golden_old_rows_convert_to_new_rows():
    source = """module example.migrate
importModule math standard.math
type SearchResult Result I64 SearchError
modulePurpose example.migrate "Search values."
moduleInvariant example.migrate "Only counter mutates."
htmlTemplate CardTemplate
htmlArg CardTemplate titleText HtmlText
htmlBody CardTemplate
  <h1>{htmlArg.titleText}</h1>
purpose helper "Compute a candidate."
invariant helper "Inputs are stable."
operation helper
input helper left I64
input helper right I64
output helper I64
returnValue left
operation main
input main needle I64
output main Result ExitCode MainError
const target I64 42
let low I64 0
var high I64 9
memoryHeap main no
effect main write storage.searchAttempts
authority main storage.searchAttempts write
set local high nextHigh
set module searchAttempts nextAttempts
call helperCall helper
arg helperCall left low
arg helperCall right target
run helperCall
bind mid I64 helperCall
bindOk foundIndex I64 searchCall
bindError searchError SearchError searchCall
branchIf isMatch found checkBelow
branchIfError searchCall reportFailure
branch reportSuccess
branch searchLoop
label found
returnOk foundIndex
label reportFailure
returnError searchError
label reportSuccess
ignoreValue printCall I32
ignoreOk writeCall I32
ignoreOk flushOkCall Void
ignoreError stopServerCall
ignoreValue flushCall Void
returnVoid
"""
    expected = """module example.migrate
import math standard.math
type SearchResult result ok I64 error SearchError
purpose module example.migrate "Search values."
invariant module example.migrate "Only counter mutates."
html template CardTemplate
html body template CardTemplate
  <h1>{titleText}</h1>
purpose operation helper "Compute a candidate."
invariant operation helper "Inputs are stable."
operation helper
input operation helper left I64
input operation helper right I64
output operation helper I64
return value left
operation main
input operation main needle I64
output operation main Result ExitCode MainError
storage module immutable target I64 42
memory main mutable low I64 0
memory main mutable high I64 9
memory main heap no
effect main write storage.searchAttempts
authority main write storage.searchAttempts
set memory high nextHigh
set storage searchAttempts nextAttempts
call helperCall helper
argument helperCall left I64 low
argument helperCall right I64 target
run helperCall
bind value mid I64 helperCall
bind ok foundIndex I64 searchCall
bind error searchError SearchError searchCall
branch if condition isMatch target found
branch else target checkBelow
branch error source searchCall target reportFailure
branch else target reportSuccess
jump target searchLoop
label found
return ok foundIndex
label reportFailure
return error searchError
label reportSuccess
ignore value source printCall type I32
ignore ok source writeCall type I32
ignore void source flushOkCall
ignore error source stopServerCall
ignore void source flushCall
return void
"""
    result = syntax_migration.migrate_text(source)
    check("golden conversion has no issues", result.ok, result.issues)
    check("golden conversion", result.text == expected, result.text)


def test_preserves_comments_without_splitting_branch_pair():
    source = """operation main
branchIf ready found
# comment that used to sit between branch legs
branch fallback
label found
returnValue ok
"""
    result = syntax_migration.migrate_text(source)
    expected = """operation main
branch if condition ready target found
branch else target fallback
# comment that used to sit between branch legs
label found
return value ok
"""
    check("comment moved after branch pair", result.text == expected, result.text)


def test_idempotent_on_new_syntax():
    source = """module example.current
import math standard.math
type SearchResult result ok I64 error SearchError
purpose module example.current "Already current."
html template CardTemplate
html body template CardTemplate
  <h1>{titleText}</h1>
operation main
input operation main needle I64
output operation main SearchResult
memory main mutable low I64 0
call helperCall helper
argument helperCall needle I64 needle
bind value value I64 helperCall
branch if condition ready target found
branch else target missing
jump target done
return ok value
ignore void source flushCall
"""
    result = syntax_migration.migrate_text(source)
    check("new syntax unchanged", result.text == source, result.text)
    check("new syntax has no issues", result.ok, result.issues)


def test_ambiguous_argument_reports_issue_without_guessing():
    source = """operation main
call externalCall external.moduleFunction
arg externalCall payload unknownValue
"""
    result = syntax_migration.migrate_text(source)
    check("ambiguous arg remains unchanged", "arg externalCall payload unknownValue" in result.text, result.text)
    check("ambiguous arg issue", len(result.issues) == 1, result.issues)
    check("issue line", result.issues[0].line == 3, result.issues[0])


def test_cli_diff_and_json_dry_run_do_not_write():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sample.sem"
        before = "module example.cli\nimportModule math standard.math\n"
        path.write_text(before, encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "syntax_migration.py"),
                "--diff",
                "--json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        check("cli dry run succeeds", proc.returncode == 0, proc.stderr)
        check("cli prints diff", "-importModule math standard.math" in proc.stdout, proc.stdout)
        payload = json.loads(proc.stdout[proc.stdout.index("{"):])
        check("cli json changed", payload["files"][0]["changed"] is True, payload)
        check("cli dry run did not write", path.read_text(encoding="utf-8") == before)


def main():
    tests = [
        test_golden_old_rows_convert_to_new_rows,
        test_preserves_comments_without_splitting_branch_pair,
        test_idempotent_on_new_syntax,
        test_ambiguous_argument_reports_issue_without_guessing,
        test_cli_diff_and_json_dry_run_do_not_write,
    ]
    for test in tests:
        test()
        print(f"[OK  ] {test.__name__}")


if __name__ == "__main__":
    main()
