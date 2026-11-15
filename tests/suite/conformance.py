"""Conformance suite: the language's safety guarantees, each stated as rules and proven by executable checks.

Every guarantee has:
- `rules`: what the language promises, in the words the checker and runtime implement;
- `checks`: programs derived from `conformance/warehouse` (a frozen copy of the warehouse example) by exact
  edits, each of which must be rejected with exactly the listed codes (`reject`), trap at run time with the
  listed text (`trap`), or run and print the listed line (`run`);
- `evidence`: other tests that also prove it (`mutation:<id>`, `case:<program case>`, `test:<test function>`).

`python tests/suite/conformance.py --write` regenerates docs/safety-guarantees.md from this table, and
tests/test_conformance.py fails when that file is stale, when a check fails, or when evidence names a test
that does not exist.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "semanticscript", "compiler"))
from sembuild import suppressed  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "conformance", "warehouse")
BASES = {"warehouse": BASE, "groups": os.path.join(HERE, "conformance", "groups"),
         "cleanups": os.path.join(HERE, "conformance", "cleanups"),
         "symbols": os.path.join(HERE, "conformance", "symbols"),
         "lists": os.path.join(HERE, "conformance", "lists"),
         "lexer": os.path.join(HERE, "..", "..", "docs", "refined-examples", "lexer")}
DOC = os.path.join(HERE, "..", "..", "docs", "safety-guarantees.md")

W, P, B, C, L = "warehouse.sem", "pricing.sem", "build.sem", "cleanups.sem", "lists.sem"
SM, SE = "symbols.sem", "expressions.sem"  # the symbols example (D-60 to D-62)


@dataclass(frozen=True)
class Check:
    id: str
    kind: str  # reject | trap | run
    says: str  # what the check shows, one line
    edits: tuple = ()  # (file, old, new); old "<append>" appends `new` to the file
    codes: tuple = ()  # reject: the exact set of codes
    detail: str = ""  # reject: text of the rule's own diagnostic; trap: text in stderr; run: a stdout line
    base: str = "warehouse"  # which program in tests/suite/conformance the edits apply to
    exit: int = 0  # run: the exit code
    lines: tuple | None = None  # run and trap: the exact stdout, line by line (`()` for nothing)
    args: tuple = ()  # run and trap: the program's command-line arguments (what follows `--`)


@dataclass(frozen=True)
class Guarantee:
    key: str
    title: str
    rules: tuple
    checks: tuple
    evidence: tuple = field(default_factory=tuple)


def _call(name, op, target, args, out="none", owned="none", catch="none", kind="call", rationale=None):
    rows = [f"{name} is {kind}"]
    if rationale:
        rows.append(f'{name} rationale "{rationale}"')
    rows += [f"{name} in {op}", f"{name} invokes {target}"]
    rows += [f"{name} argument {a}" for a in args] or [f"{name} argument none"]
    rows += [f"{name} result {out}", f"{name} ownedBy {owned}", f"{name} cleanedBy none", f"{name} borrows none",
             f"{name} catch {catch}"]
    rows += [f"{name} suppresses {v}" for v in suppressed(catch, rationale)]
    return "\n".join(rows)


CLEAR_LINES = _call("clearLines", "main", "pricing.Lines.clear", ("list pricing.Lines lines lendMutable",))
CLEANUP = ('closeReportCleanup is cleanup\ncloseReportCleanup rationale "A report that cannot be closed may not be '
           'fully written, so the program stops"\ncloseReportCleanup in main\ncloseReportCleanup runs closeReport\n'
           'closeReportCleanup cleans report\ncloseReportCleanup onError trap\n')
STAMP = '''
clockReader is capability
clockReader purpose "Authority to read the monotonic clock"
clockReader grants read clock.monotonic none

stamp is operation
stamp purpose "Read the monotonic clock"
stamp invariant notNegative "Returns a time of zero or more milliseconds"
stamp typeParameter none
stamp input none
stamp output Int64
stamp outputOwnedBy none
stamp raises none
stamp effect read clock.monotonic
stamp uses clockReader
stamp memoryHeap false
stamp async false
stamp maxRecursion none
stamp label begin loopKind none
stamp label begin within none
stamp let none
stamp at begin do readClock
stamp at begin return ok now

''' + _call("readClock", "stamp", "clock.monotonic", (), out="now Int64")
STAMP_TEST = '''
stampTest is test
stampTest purpose "The clock reads zero or more"
stampTest verifies stamp notNegative
stampTest typeParameter none
stampTest input none
stampTest output none
stampTest outputOwnedBy none
stampTest raises none
stampTest effect read clock.monotonic
stampTest uses clockReader
stampTest memoryHeap false
stampTest async false
stampTest maxRecursion none
stampTest label begin loopKind none
stampTest label begin within none
stampTest let zero Int64 0 immutable
stampTest at begin do runStamp
stampTest at begin do atLeastZero
stampTest at begin do expectAtLeastZero
stampTest at begin return ok none

''' + "\n\n".join([
    _call("runStamp", "stampTest", "stamp", (), out="now Int64"),
    _call("atLeastZero", "stampTest", "compare.greaterOrEqualInt64", ("left Int64 now copy", "right Int64 zero copy"),
          out="fine Bool"),
    _call("expectAtLeastZero", "stampTest", "test.assertTrue", ("value Bool fine copy",))])
FAILING = (("cleanups.sem", "closeSecond invokes closeNoting\ncloseSecond argument file fs.FileHandle second give\n"
                 "closeSecond argument note String secondNote lend",
                 "closeSecond invokes closeFailing\ncloseSecond argument file fs.FileHandle second give"),
                ("cleanups.sem", "closeSecond catch closeSecondError fs.FileError",
                 "closeSecond catch closeSecondError CloseError"),
                ("cleanups.sem", 'main let secondNote String "closing second" immutable\n', ""),
                ("cleanups.sem", "closeSecond suppresses fs.FileError.notFound\ncloseSecond suppresses fs.FileError.denied\ncloseSecond suppresses fs.FileError.exists\ncloseSecond suppresses fs.FileError.tooLarge\ncloseSecond suppresses fs.FileError.timedOut\ncloseSecond suppresses fs.FileError.cancelled\ncloseSecond suppresses fs.FileError.busy\ncloseSecond suppresses fs.FileError.failed", "closeSecond suppresses CloseError.refused"))
FAILING_TRAP = FAILING + (("cleanups.sem", "releaseSecond runs closeSecond\nreleaseSecond cleans second\n"
                                           "releaseSecond onError suppress",
                           "releaseSecond runs closeSecond\nreleaseSecond cleans second\nreleaseSecond onError trap"),
                          ("cleanups.sem", "closeSecond suppresses CloseError.refused", "closeSecond suppresses none"))
CALLEE_STACK = '''
fillGroups is operation
fillGroups purpose "Append a stack made in this operation's own region to the caller's list"
fillGroups invariant none
fillGroups typeParameter none
fillGroups input groups Groups borrowedMutable
fillGroups output none
fillGroups outputOwnedBy none
fillGroups raises none
fillGroups effect none
fillGroups uses none
fillGroups memoryHeap true
fillGroups async false
fillGroups maxRecursion none
fillGroups label begin loopKind none
fillGroups label begin within none
fillGroups let none
fillGroups at begin do makeLocal
fillGroups at begin do storeLocal
fillGroups at begin return ok none

local is region
local in fillGroups
local strategy arena
local maxBytes 1024
local released atReturn

''' + _call("makeLocal", "fillGroups", "Stack.new", ("region Region local lend",), out="localStack Stack", owned="local") \
    + "\n\n" + _call("storeLocal", "fillGroups", "Groups.append", ("list Groups groups lendMutable",
                                                                  "item Stack localStack give"))
GENERIC_STASH = '''
Pile is typeInstance
Pile purpose "Values of the stash's type, kept in the caller's list"
Pile in stash
Pile instantiates list.List T

stash is operation
stash purpose "Store any value in a list the caller lends"
stash invariant none
stash typeParameter T any
stash input into Pile borrowedMutable
stash input thing T owned
stash output none
stash outputOwnedBy none
stash raises none
stash effect none
stash uses none
stash memoryHeap false
stash async false
stash maxRecursion none
stash label begin loopKind none
stash label begin within none
stash let none
stash at begin do put
stash at begin return ok none

''' + _call("put", "stash", "Pile.append", ("list Pile into lendMutable", "item T thing give"))
LOCAL_STACK_RETURNED = '''
stackFor is operation
stackFor purpose "Make a stack in this operation's own region and return it in the caller's"
stackFor invariant none
stackFor typeParameter none
stackFor input into Region borrowed
stackFor output Stack
stackFor outputOwnedBy into
stackFor raises none
stackFor effect none
stackFor uses none
stackFor memoryHeap true
stackFor async false
stackFor maxRecursion none
stackFor label begin loopKind none
stackFor label begin within none
stackFor let none
stackFor at begin do makeLocal
stackFor at begin return ok localStack

local is region
local in stackFor
local strategy arena
local maxBytes 1024
local released atReturn

''' + _call("makeLocal", "stackFor", "Stack.new", ("region Region local lend",), out="localStack Stack", owned="local")
REGION_TEXT = '''
label is operation
label purpose "Return text built in this operation's own region"
label invariant none
label typeParameter none
label input none
label output String
label outputOwnedBy none
label raises none
label effect none
label uses none
label memoryHeap true
label async false
label maxRecursion none
label label begin loopKind none
label label begin within none
label let seven Int64 7 immutable
label at begin do digits
label at begin return ok text

scratch is region
scratch in label
scratch strategy arena
scratch maxBytes 64
scratch released atReturn

''' + _call("digits", "label", "string.fromInt64", ("value Int64 seven copy", "region Region scratch lend"),
            out="text String", owned="scratch")

GUARANTEES = (
    Guarantee("ownership", "Ownership and moves", (
        "A resource or region-owned value has exactly one owner: an operation, a region, or (for an output) the "
        "caller. `give` moves it; after a `give` on any path the name cannot be used again (R513).",
        "Every owned value is released exactly once on every path: given away, returned, or cleaned by a deferred "
        "cleanup (R513). A cleanup is deferred exactly once (R510).",
        "A `let` copies only plain values; a second name for a String, list, or record is rejected because it would "
        "outlive the loan it came from (R514).",
        "A resource cannot be stored in a collection, because a region releases collections without closing what "
        "they hold (R403).",
        "Two handles are independent values to the checker, so the runtime guards what they share: one file, under "
        "any name (links and `..` resolved), is open for writing by at most one handle of the program and never "
        "while another handle reads it; readers share it. A conflicting open, `readAll`, `writeAll`, or `remove` "
        "fails with `fs.FileError.busy` (D-52).",
    ), (
        Check("same-file-twice", "run", "opening `./cleanup-first.txt` while `cleanup-first.txt` is open for writing "
              "fails with `busy`; only the first file's cleanup runs",
              ((C, 'main let secondPath String "cleanup-second.txt" immutable',
                'main let secondPath String "./cleanup-first.txt" immutable'),),
              (), "closing first", base="cleanups", exit=1, lines=("closing first",)),
        Check("close-twice", "reject", "closing the report again after the failure path already closed it",
              ((W, "main at closeAfterFailure branch ifError closeFailedReport goto fileFailed else goto fileFailed",
                "main at closeAfterFailure branch ifError closeFailedReport goto closeWritten else goto closeWritten"),),
              ("R513",), "`report` may already have been given away"),
        Check("let-aliases-a-loan", "reject", "a `let` naming a borrowed list",
              ((P, "orderTotal let running Int64 0 mutable\n",
                "orderTotal let running Int64 0 mutable\norderTotal let alias Lines lines immutable\n"),),
              ("R514",), "a let copies only plain values"),
        Check("resource-in-collection", "reject", "a list of file handles",
              ((W, "warehouse imports pricing", "warehouse imports standard.list\nwarehouse imports pricing"),
               (W, "<append>", 'Handles is typeInstance\nHandles purpose "Open files kept in a list"\n'
                               'Handles in none\nHandles instantiates list.List fs.FileHandle')),
              ("R403",), "is a resource"),
    ), ("mutation:double-give", "mutation:give-borrowed", "mutation:use-after-give", "mutation:give-deferred",
        "mutation:owned-never-released", "mutation:leak-on-error-path", "mutation:return-owned-with-cleanup-none")),

    Guarantee("borrowing", "Loans and lifetimes", (
        "`lend` is a shared, read-only loan for the duration of the activation; `lendMutable` is exclusive. A value "
        "cannot be lent exclusively while any other loan of it is live, and a read loan cannot be turned into an "
        "exclusive one (R515).",
        "A loan to a task lasts from `start` to `join`, including after a `cancel` (D-39, D-44).",
        "A value borrowed from an input or a region cannot leave the operation that borrowed it, and an output "
        "allocated in a region names that region as its owner (R514, R409).",
    ), (
        Check("exclusive-while-lent-to-tasks", "reject", "clearing the list while two tasks read it",
              ((W, "main at price start discountTask into none\n", "main at price start discountTask into none\nmain at price do clearLines\n"),
               (W, "<append>", CLEAR_LINES)),
              ("R515",), "`lines` is lent to task `listTask`"),
        Check("loan-outlives-cancel", "reject", "clearing the list after cancelling, before joining",
              ((W, "main at stopDiscount cancel discountTask\n",
                "main at stopDiscount cancel discountTask\nmain at stopDiscount do clearLines\n"),
               (W, "<append>", CLEAR_LINES)),
              ("R515",), "`lines` is lent to task `discountTask`"),
        Check("region-output-unowned", "reject", "returning region text with `outputOwnedBy none`",
              ((P, "pricing imports standard.list", "pricing imports standard.list\npricing imports standard.string"),
               (P, "<append>", REGION_TEXT)),
              ("R409",), "names the `Region` input it is allocated in"),
    ), ("mutation:mutable-loan-of-read-loan", "mutation:change-through-read-loan", "mutation:give-while-lent-to-task",
        "mutation:return-borrowed-resource", "mutation:region-escape-none", "mutation:effect-laundering-ref",
        "mutation:by-reference-needs-mutable-loan")),

    Guarantee("concurrency", "Structured concurrency", (
        "Every task is started at most once per path and joined exactly once on every path to every return, "
        "whether or not it was cancelled; a task group is joined on every path (R510, R512). There is no detached "
        "task, so no task outlives the operation that started it, or anything it borrowed from it.",
        "`cancel` asks a task (and every task it started) to stop and returns at once; the task sees `cancelled` at "
        "its next wait. `join` waits for it to stop and delivers its outcome: its output, its error, or the "
        "`cancelled` variant of its error type (D-44).",
        "A task's failure is delivered only at its `join`, to the operation that started it, and must be branched "
        "on there (R506). One plain task failing does not cancel its siblings: the parent decides, and must still "
        "join each one. A trap in any task ends the program with the trap's stack trace.",
        "A task group states the one error type its tasks raise (`catch <name> <Type>`, or `catch none` when none "
        "can fail; R403). The first task to fail records its error in the group and cancels the group's other "
        "tasks; `join <group>` waits for all of them and delivers that error, followed directly by "
        "`branch ifError <group>` (R506, D-48). A grouped task's own output is never read (R510).",
        "A `join` or `cancel` needs its task live on EVERY path that reaches it: started, and not yet joined, on "
        "each incoming path, not just on one; a block reached both after a join and without one is rejected (R510, "
        "D-50).",
        "Cancellation is observed at waits (channel operations, sleeps, accepts, reads, child processes, file "
        "locks): the wait ends with the `cancelled` variant of its error. Computation between waits runs to its "
        "end, so a cancelled task always finishes in a defined state.",
    ), (
        Check("cancel-without-join", "reject", "cancelling a task and returning without joining it",
              ((W, "main at stopDiscount join discountTask\nmain at stopDiscount branch ifError discountTask goto "
                   "bothFailed else goto listFailed", "main at stopDiscount goto listFailed"),),
              ("R512", "R511"), "was cancelled but is not joined"),
        Check("join-on-a-merge", "reject", "a block joins the task, then flows into a block that joins it again",
              ((W, "main at price branch ifError listTask goto stopDiscount else goto joinDiscount",
                "main at price branch ifError listTask goto earlyJoin else goto joinDiscount\n"
                "main at earlyJoin join discountTask\n"
                "main at earlyJoin branch ifError discountTask goto joinDiscount else goto joinDiscount"),
               (W, "main label joinDiscount loopKind none",
                "main label earlyJoin loopKind none\nmain label earlyJoin within none\nmain label joinDiscount loopKind none")),
              ("R510", "R507", "R511", "R506"), "was never started or was already joined"),
        Check("no-detach", "reject", "`detach` is not a step",
              ((W, "main at price start discountTask into none", "main at price detach discountTask"),),
              ("R205", "R510"), "step row must be"),
        Check("runs", "run", "the program prices the order in two tasks and prints the report",
              (), (), "list=3750 discounted=3375"),
        Check("group-first-failure", "run", "a group's failing task cancels a ten-second sibling; `join` delivers "
              "its error at once (exit 3: stopped early)", (), (), "-3", base="groups", exit=3),
        Check("error-carries-text", "reject", "an error type whose payload is text",
              (("groups.sem", "CheckError variant negative Int64", "CheckError variant negative String"),),
              ("R403", "R406"), "an error carries only plain values", base="groups"),
        Check("group-catch-none", "reject", "a group that cannot receive its tasks' errors",
              (("groups.sem", "checks catch checkError CheckError", "checks catch none"),),
              ("R403", "R401", "R506"), "states `catch <name> groups.CheckError`", base="groups"),
        Check("group-wrong-error-type", "reject", "a group catching a different error type than its tasks raise",
              (("groups.sem", "checks catch checkError CheckError", "checks catch checkError console.WriteError"),),
              ("R403",), "a group's tasks raise its one error type", base="groups"),
        Check("group-join-unchecked", "reject", "joining a fallible group without branching on its error",
              (("groups.sem", "main at begin branch ifError checks goto failed else goto allPassed",
                "main at begin goto allPassed"),),
              ("R506", "R511"), "`checks` can fail", base="groups"),
    ), ("mutation:task-not-joined", "mutation:group-not-joined", "mutation:join-twice",
        "mutation:start-in-loop-join-after", "mutation:task-wrong-loan-mode", "case:11-concurrency/cancellation",
        "case:11-concurrency/parallel", "case:11-concurrency/trap-channel-deadlock")),

    Guarantee("effects", "Effects", (
        "An operation declares exactly the effects it performs: its own and those of everything it activates, "
        "including calls, tasks, cleanups, imported operations, and operations invoked through references, whose "
        "effects are those of their `operationType` (R407).",
        "An operation used as a value has no effects its `operationType` does not allow (R403).",
    ), (
        Check("effect-undeclared", "reject", "printing without declaring `write console.stdout`",
              ((W, "main effect write console.stdout\n", ""),), ("R407", "R408"), "does not declare"),
        Check("effect-through-reference", "reject", "a rule type that allows printing, invoked by an operation that "
              "does not declare it",
              ((P, "PriceRule effect none", "PriceRule effect write console.stdout"),),
              ("R407",), "`lineTotal` performs `write console.stdout`"),
        Check("effect-across-modules", "reject", "calling an imported operation that reads the clock",
              ((P, "pricing imports standard.list", "pricing imports standard.list\npricing imports standard.clock"),
               (P, "pricing exports discountTotal", "pricing exports discountTotal\npricing exports stamp"),
               (P, "<append>", STAMP),
               ("pricing.test.sem", "<append>", STAMP_TEST),
               (B, "warehouse allows write console.stdout none",
                "warehouse allows write console.stdout none\nwarehouse allows read clock.monotonic none"),
               (W, "main at finished return ok okCode", "main at finished do stampDone\nmain at finished return ok okCode"),
               (W, "<append>", _call("stampDone", "main", "pricing.stamp", (), out="doneAt Int64"))),
              ("R407",), "`main` performs `read clock.monotonic`"),
    ), ("mutation:effect-undeclared", "mutation:effect-declared-not-performed", "mutation:effect-laundering-ref",
        "mutation:reference-signature-mismatch")),

    Guarantee("capabilities", "Capabilities and authority", (
        "build.sem states the program's whole authority in `allows` rows. Every capability of every module, "
        "including required packages, grants only what an `allows` row covers, within its scope (R408, D-41).",
        "An effect is performed only through a capability the operation `uses`, declared in the same module. "
        "Capabilities cannot be exported or named from another module, so authority cannot be forged or passed "
        "between modules (R402, R205).",
        "A scoped argument written as a literal must lie inside the scope at check time (R408); a computed one is "
        "checked before the call at run time, after `..` and links are resolved, and traps outside it (D-38).",
        "Writing `allows` rows does not grant them: `refined run`, `test`, `bench`, and executable builds start only "
        "when every `allows` row of build.sem is listed in the project's `authority.approved`, written by "
        "`refined approve` after a person or a trusted pipeline reviews them; otherwise they stop with exit 3 and "
        "name what is missing (D-53).",
    ), (
        Check("authority-not-approved", "refused", "build.sem widened to read every file in the directory; nobody "
              "approved that", ((B, 'warehouse allows read fs.files "warehouse-*"', 'warehouse allows read fs.files "*"'),),
              (), 'allows read fs.files "*"', exit=3),
        Check("allows-missing", "reject", "build.sem no longer allows reading files",
              ((B, 'warehouse allows read fs.files "warehouse-*"\n', ""),), ("R408",), "which build.sem does not allow"),
        Check("capability-exported", "reject", "exporting a capability",
              ((W, "warehouse exports main", "warehouse exports main\nwarehouse exports reportFiles"),),
              ("R402",), "capabilities are never exported"),
        Check("capability-of-another-module", "reject", "using a capability declared in another module",
              ((P, "listTotal uses none", "listTotal uses warehouse.reportFiles"),), ("R205",), "`uses` row"),
        Check("path-outside-scope", "reject", "a report path outside the capability's scope",
              ((W, 'main let reportPath String "warehouse-report.txt" immutable',
                'main let reportPath String "report.txt" immutable'),), ("R408",), "outside the scope"),
        Check("scope-wider-than-allowed", "reject", "a capability scope wider than build.sem allows",
              ((W, 'reportFiles grants write fs.files "warehouse-*"', 'reportFiles grants write fs.files "ware*"'),),
              ("R408",),
              "which build.sem does not allow"),
    ), ("mutation:capability-missing", "mutation:capability-unused", "mutation:capability-scope-escape",
        "mutation:capability-scope-dotdot", "mutation:host-prefix", "mutation:fs-prefix-sibling",
        "mutation:allows-scope-narrower", "mutation:ffi-symbol-not-granted", "mutation:ffi-symbol-grant-missing",
        "case:17-security/trap-computed-path-escape", "case:17-security/trap-computed-program",
        "test:test_symlink_out_of_scope_traps")),

    Guarantee("errors", "Errors", (
        "A fallible activation is followed directly by `branch ifError`; its error has the declared type of the "
        "target, and an operation raises only its declared type (R506, R403).",
        "A `match` names every variant of the error exactly once (R509).",
        "Sending both outcomes to the same block discards the failure, which needs a `rationale` row saying why "
        "(filler text is rejected) and `suppresses` rows naming exactly the variants dropped: every variant of the "
        "error type, so a variant added later breaks the build instead of vanishing. An activation that handles its "
        "failure states `suppresses none`; a cleanup under `onError suppress` names its call's variants (R506, "
        "R304, D-54).",
    ), (
        Check("discard-without-reason", "reject", "both outcomes of a close go to the same block, with no reason",
              ((W, 'closeFailedReport rationale "The write already failed and exit 4 reports it; the close only '
                   'releases the file"\n', ""),), ("R506",), "needs a `rationale` row"),
        Check("discard-with-filler", "reject", "a rationale that says nothing",
              ((W, 'closeFailedReport rationale "The write already failed and exit 4 reports it; the close only '
                   'releases the file"', 'closeFailedReport rationale "ignored"'),), ("R304",), "filler"),
        Check("suppression-incomplete", "reject", "a discard that does not name `busy`",
              ((W, "closeFailedReport suppresses fs.FileError.busy\n", ""),), ("R506",),
              "add `closeFailedReport suppresses fs.FileError.busy`"),
        Check("suppression-on-handled", "reject", "naming a suppressed variant for a failure that is handled",
              ((W, "askRoom suppresses none", "askRoom suppresses arena.ArenaError.exhausted"),), ("R506",),
              "handles its failure, so it suppresses nothing"),
        Check("match-incomplete", "reject", "a match missing `emptyOrder`",
              ((W, "main at listFailed case pricing.PricingError.emptyOrder bind none none goto noLines\n", ""),),
              ("R509",), "has no case for `emptyOrder`"),
        Check("wrong-error-type", "reject", "catching an imported operation's error as the wrong type",
              ((W, "listTask catch listError pricing.PricingError", "listTask catch listError fs.FileError"),),
              ("R403",), "raises `pricing.PricingError`"),
    ), ("mutation:catch-missing", "mutation:catch-wrong-type", "mutation:raise-undeclared", "mutation:raise-wrong-type",
        "mutation:error-not-passed-up", "mutation:error-match-incomplete", "mutation:error-match-duplicate",
        "case:10-errors/errors")),

    Guarantee("text", "Text and source positions", (
        "Text is read a byte at a time with `string.byteAt`, and every index is checked: an index outside the text is "
        "a typed `outOfRange` error, never a read past its end.",
        "`string.slice` keeps characters whole: a slice that would start or end inside a UTF-8 sequence is "
        "`outOfRange` (D-70), so a slice of UTF-8 text is UTF-8 text.",
        "`string.advancePosition` steps over one whole character and keeps its line and column: a newline starts the "
        "next line at column 1 and any other character moves one column, so columns count characters, not bytes. "
        "Stepping from outside the text is `outOfRange` (D-71).",
        "A file path computed at run time (from the command line, say) is checked against the capability's scope "
        "when the file is opened; outside the scope the program stops before the file is touched (D-38).",
    ), (
        Check("position-step-unchecked", "reject", "stepping past a space without its error branch",
              (("lexer.sem", "tokenize at skipSpace branch ifError stepSpace goto finished else goto spaceDone\n",
                "tokenize at skipSpace goto spaceDone\n"),), ("R506", "R507"), "`stepSpace` can fail",
              base="lexer"),
        Check("position-is-a-record", "reject", "reporting a too-large integer at a byte offset, not a position",
              (("lexer.sem", "makeTooLarge argument payload string.Position position copy",
                "makeTooLarge argument payload Int64 offset copy"),), ("R403",), "is `string.Position`, not `Int64`",
              base="lexer"),
        Check("lexes-a-named-file", "run", "the lexer example tokenizes the file its argument names",
              (), (), "lexer-sample.txt: 31 tokens, end of input at 6:1, written to lexer-sample.txt.tokens",
              base="lexer", args=("lexer-sample.txt",)),
        Check("computed-path-outside-scope", "trap", "the lexer example given a path outside `lexer-*`",
              (), (), "which no capability this operation uses allows", base="lexer", args=("build.sem",)),
    ), ("case:08-strings-collections/positions", "case:08-strings-collections/bounds",
        "mutation:whole-character-slice-unchecked", "mutation:position-step-unchecked",
        "mutation:position-is-not-an-integer", "mutation:punctuation-takes-a-byte",
        "test:test_lexer_example_tokenizes_a_file_named_on_the_command_line",
        "test:test_lexer_example_reports_problems_with_their_exit_codes")),

    Guarantee("cleanup", "Deterministic cleanup", (
        "A cleanup is deferred after the value it cleans exists, and exactly once on a path (R507, R510); it runs at "
        "every later `return`, `ok` or `error`, newest first, and only once.",
        "A cleanup's call takes the value with `give`: the value is consumed even if releasing it fails. "
        "`onError trap` stops the program; `onError suppress` continues. Every cleanup states a `rationale` row saying why its policy is right (R302).",
        "A trap runs no more program code, so deferred cleanups are skipped (the state that trapped may be the "
        "state they act on). The runtime then releases what the program still holds outside it: files are flushed "
        "and closed, connections closed, child processes stopped; the trap message says how many (D-51).",
        "A cancelled task runs the cleanups of the operations it unwinds through, since cancellation reaches it as "
        "an error.",
    ), (
        Check("resource-in-record", "reject", "a record with a file handle field",
              ((C, "<append>", 'Holder is record\nHolder purpose "A file kept in a record"\nHolder typeParameter none\n'
                               'Holder field file fs.FileHandle'),), ("R403",), "a resource", base="cleanups"),
        Check("cleanup-deferred-twice", "reject", "deferring the first file's cleanup twice",
              ((C, "main at openedFirst defer releaseFirst\n",
                "main at openedFirst defer releaseFirst\nmain at openedFirst defer releaseFirst\n"),),
              ("R510",), "is deferred 2 times", base="cleanups"),
        Check("cleanup-before-acquire", "reject", "deferring the cleanup before the file is open",
              ((C, "main at begin do openFirst\n", "main at begin defer releaseFirst\nmain at begin do openFirst\n"),
               (C, "main at openedFirst defer releaseFirst\n", "")),
              ("R507", "R513"), "may not be set here", base="cleanups"),
        Check("trap-releases-handles", "trap", "a division by zero with both files open: no cleanup runs, and the "
              "runtime closes the two files",
              ((C, "cleanups imports standard.fs", "cleanups imports standard.fs\ncleanups imports standard.math"),
               (C, "main at openedSecond do printBody\n", "main at openedSecond do crash\nmain at openedSecond do printBody\n"),
               (C, "main let okCode ExitCode 0 immutable", "main let okCode ExitCode 0 immutable\n"
                                                          "main let one Int64 1 immutable\nmain let zero Int64 0 immutable"),
               (C, "<append>", _call("crash", "main", "math.divideInt64", ("left Int64 one copy", "right Int64 zero copy"),
                                     out="nothing Int64"))),
              (), "the runtime released 2 resources", base="cleanups", lines=()),
        Check("cleanup-order", "run", "two deferred cleanups run at the return, newest first", (), (), "body",
              base="cleanups", lines=("body", "closing second", "closing first")),
        Check("partial-initialization", "run", "the second file fails to open: only the first file's cleanup "
              "exists, and only it runs", (("cleanups.sem", 'main let secondPath String "cleanup-second.txt" immutable',
                                            'main let secondPath String "cleanup-missing/second.txt" immutable'),),
              (), "closing first", base="cleanups", exit=1, lines=("closing first",)),
        Check("cleanup-fails-trap", "trap", "a cleanup that fails under `onError trap` stops the program; the "
              "older cleanup does not run", FAILING_TRAP, (), "failed (onError trap)", base="cleanups",
              lines=("body",)),
        Check("cleanup-fails-suppress", "run", "a cleanup that fails under `onError suppress` is passed over; the "
              "handle is consumed and the older cleanup still runs", FAILING, (), "closing first",
              base="cleanups", lines=("body", "closing first")),
        Check("cleanup-missing", "reject", "never deferring the first file's cleanup",
              ((C, "main at openedFirst defer releaseFirst\n", ""),), ("R513", "R510"), "may still be owned",
              base="cleanups"),
    ), ("mutation:cleanup-not-deferred", "mutation:cleanup-wrong-value", "mutation:cleanup-suppress-without-reason",
        "mutation:cleanup-before-acquire", "case:07-memory/cleanup-on-error", "case:06-recursion/recursive-cleanup",
        "case:07-memory/resources")),

    Guarantee("regions", "Region memory", (
        "Every allocation names a region; a region's `capacity` is a hard limit. Allocating past it traps with the "
        "region's name before any memory is written, so exhaustion never corrupts memory (A10).",
        "A region is released at its operation's return, after every task that could use it has been joined; values "
        "it owns cannot be returned unless the output names the region as owner (R409, R512).",
        "Allocation a program can recover from: `arena.remaining(region)` says how many bytes are left, and "
        "`arena.ensure(region, bytes)` fails with `arena.ArenaError.exhausted` (carrying what is left) when that "
        "much is not free, so a program asks before a step that allocates and takes its own path (D-55).",
    ), (
        Check("recover-before-allocating", "run", "a 300-byte region: the totals fit, the report does not, and the "
              "program says so with exit 6 instead of trapping",
              ((W, "store maxBytes 65536", "store maxBytes 300"),), (), "3375", exit=6, lines=("3750", "3375")),
        Check("arena-exhausted", "trap", "a 64-byte region for the whole program: passing it unasked traps",
              ((W, "store maxBytes 65536", "store maxBytes 64"),), (), "exceeded its capacity of 64 bytes"),
    ), ("case:07-memory/trap-region-exhausted", "mutation:region-value-without-owner", "mutation:heap-undeclared",
        "mutation:region-escape-none")),

    Guarantee("interior-mutability", "Handles and interior mutability", (
        "A target that changes the state of the handle it is given (a file's position or lock, a connection's "
        "stream, a listener's queue) takes it `borrowedMutable`, so it is passed with `lendMutable` and no two "
        "activations can use one handle at once (R406, R515, D-43).",
        "A channel is the one shared mutable value: its operations are synchronized and it exists to be used by "
        "several tasks, so it is lent with `lend`.",
    ), (
        Check("shared-loan-to-write", "reject", "writing through a shared loan",
              ((W, "writeReport argument file fs.FileHandle report lendMutable", "writeReport argument file fs.FileHandle report lend"),),
              ("R406",), "passed as `lendMutable`"),
        Check("two-writers", "reject", "two tasks writing through one handle at once",
              ((W, "main at opened start writeReport into none\n", "main at opened start writeReport into none\nmain at opened start writeAgain into none\n"),
               (W, "main at opened branch ifError writeReport goto closeAfterFailure else goto closeWritten",
                "main at opened branch ifError writeReport goto stopAgain else goto joinAgain\n"
                "main at joinAgain join writeAgain\nmain at joinAgain branch ifError writeAgain goto closeAfterFailure "
                "else goto closeWritten\n"
                "main at stopAgain cancel writeAgain\nmain at stopAgain join writeAgain\n"
                "main at stopAgain branch ifError writeAgain goto closeAfterFailure else goto closeAfterFailure"),
               (W, "main label closeWritten loopKind none", "main label joinAgain loopKind none\nmain label joinAgain within none\n"
                "main label stopAgain loopKind none\nmain label stopAgain within none\nmain label closeWritten loopKind none"),
               (W, "<append>", _call("writeAgain", "main", "fs.write",
                                     ("file fs.FileHandle report lendMutable", "bytes Bytes reportBytes lend",
                                      "deadline time.Deadline deadline copy"),
                                     catch="writeAgainError fs.FileError", kind="task",
                                     rationale="The first write already failed, so the second one's result no longer matters"))),
              ("R515",), "is lent exclusively to task `writeReport`"),
    ), ("mutation:task-wrong-loan-mode", "case:19-stdlib/file-lock", "case:12-io/network-connect")),

    Guarantee("control-flow", "Control flow and definite assignment", (
        "Every jump names a declared block; every block is reachable and ends in exactly one terminator (R502, R511, "
        "R501). A loop is entered only through its header (R504).",
        "A value is read only where every path to the read has set it (R507); only `mutable` lets are set, with a "
        "value of their declared type (R403). Every name has one declared type, so the type is the same on every "
        "path into a block.",
    ), (
        Check("unknown-label", "reject", "branching to a misspelt block",
              ((W, "goto outputFailed else goto finished", "goto outputFailed else goto finishd"),),
              ("R502", "R511"), "no block is labelled `finishd`"),
        Check("maybe-unset", "reject", "reaching the totals after the list task failed",
              ((W, "main at stopDiscount branch ifError discountTask goto bothFailed else goto listFailed",
                "main at stopDiscount branch ifError discountTask goto bothFailed else goto printTotals"),),
              ("R507",), "`listCents` may not be set here"),
        Check("set-immutable", "reject", "setting an immutable let",
              ((W, "main at finished return ok okCode", "main at finished set okCode badLineCode\nmain at finished return ok okCode"),),
              ("R403",), "only a `mutable` let can be set"),
        Check("jump-into-loop", "reject", "jumping into a loop's body",
              ((W, "main at begin goto fill", "main at begin goto addRow"),), ("R504", "R507"),
              "into the middle of loop `fill`"),
    ), ("mutation:var-uninitialized-path", "mutation:var-unset-after-zero-pass-loop", "mutation:var-set-immutable",
        "mutation:var-set-wrong-type", "mutation:branch-unknown-label", "mutation:unreachable-block",
        "mutation:statement-after-return", "mutation:block-falls-through", "mutation:jump-into-loop",
        "mutation:cycle-without-header")),

    Guarantee("collections", "Collections and iteration", (
        "A table is constant data fixed when the program is checked; it is read only by `forEach` and has no step "
        "that changes it. A `forEach` over a table states a `maxIterations` at least its row count (R503).",
        "A `forEach` over a list reads it on every pass, so inside the loop the list cannot be changed, lent "
        "exclusively, or given away (R515). Passing the loop's `maxIterations` at run time traps (D-45).",
        "A loop's bound may be computed at run time (a list's length, say): any immutable `Int64` value set on "
        "every path into the loop before its first pass, back edges included (R503, R507, D-56).",
    ), (
        Check("table-rows-exceed-bound", "reject", "a three-row table read by a loop bounded at 2",
              ((W, "main label fill maxIterations 3", "main label fill maxIterations 2"),), ("R503",), "has 3 rows"),
        Check("list-exceeds-bound", "trap", "a three-line order priced by a loop bounded at 2",
              ((P, "orderTotal label sumLines maxIterations lineCount", "orderTotal label sumLines maxIterations 2"),), (),
              "more than maxIterations 2 times"),
        Check("bound-set-inside-loop", "reject", "a loop bounded by a value first set inside the loop",
              ((P, "orderTotal label sumLines maxIterations lineCount", "orderTotal label sumLines maxIterations newRunning"),),
              ("R507",), "may not be set when loop `sumLines` starts"),
    ), ("mutation:append-during-foreach", "mutation:list-index-unchecked", "mutation:table-missing-cell",
        "mutation:table-cell-wrong-type", "case:04-control-flow/trap-loop-bound")),

    Guarantee("trees", "Trees and symbol tables", (
        "A type never holds itself, by value or inside a collection (R403). A tree is a list of nodes that refer to "
        "each other by position: `<Alias> aliasOf Int64` with `<Alias> indexes <List>` makes the alias that list "
        "type's only position type, so `get` and `set` take it and a plain `Int64` is refused (R403, D-60).",
        "A position has no literal; it comes only from `<List>.appendIndexed`, and reading a position the list does "
        "not have is `list.IndexOutOfRange`, never a stray read. Recursion over a tree is bounded by "
        "`maxRecursion`; deeper traps.",
        "A map's key is a plain value or a `String` (R403). A `String` key is lent, compared by content, and copied "
        "into the map's region when first put, so keys read back live as long as the map (D-61).",
        "A `forEach` over a map reads its keys in first-put order. Inside the loop the map cannot be changed, lent "
        "exclusively, or given away (R515); passing the loop's bound, which may be the map's length read at run "
        "time, traps (D-62).",
    ), (
        Check("forged-position", "reject", "writing a node position as a literal",
              ((SM, "main let one Int64 1 immutable", "main let one Int64 1 immutable\n"
                "main let forged expressions.NodeId 0 immutable"),), ("R403",), "a position has no literal",
              base="symbols"),
        Check("integer-as-position", "reject", "evaluating the tree at a plain whole number",
              ((SM, "evaluateFirst argument at expressions.NodeId rootAt copy",
                "evaluateFirst argument at expressions.NodeId one copy"),), ("R403",), "but `one` is `Int64`",
              base="symbols"),
        Check("node-holds-its-children", "reject", "a node type that holds a list of itself",
              ((SE, "<append>", 'Branch is record\nBranch purpose "A tree node that holds its children directly"\n'
                "Branch typeParameter none\nBranch field value Int64\nBranch field children Branches\n\n"
                'Branches is typeInstance\nBranches purpose "The children of one branch"\n'
                "Branches in none\nBranches instantiates list.List Branch"),), ("R403",),
              "holds itself inside a collection",
              base="symbols"),
        Check("table-changed-while-listed", "reject", "redefining a name while the listing reads the table",
              ((SM, "main at printValue do printValueLine", "main at printValue do redefineAgain\n"
                "main at printValue do printValueLine"),
               (SM, "<append>", _call("redefineAgain", "main", "expressions.Symbols.put",
                                      ("map expressions.Symbols symbolTable lendMutable", "key String xName lend",
                                       "value Int64 five copy")))),
              ("R515",), "is being iterated by loop `showNames`", base="symbols"),
        Check("tree-deeper-than-bound", "trap", "a two-level tree evaluated with maxRecursion 1",
              ((SE, "evaluate maxRecursion 64", "evaluate maxRecursion 1"),), (),
              "called itself deeper than maxRecursion 1", base="symbols"),
        Check("listing-exceeds-bound", "trap", "a two-name table listed by a loop bounded at 1",
              ((SM, "main label showNames maxIterations nameCount", "main label showNames maxIterations one"),), (),
              "more than maxIterations one times", base="symbols"),
        Check("names-in-definition-order", "run", "the table lists x, then y, after x is redefined",
              (), (), "y", base="symbols", lines=("15", "30", "2", "x", "10", "y", "7")),
    ), ("mutation:recursive-type-by-value", "mutation:recursive-type-through-list", "mutation:index-literal",
        "mutation:index-from-integer", "mutation:index-alias-twice", "mutation:map-key-not-plain",
        "mutation:map-text-key-copied", "mutation:map-changed-while-listed", "case:08-strings-collections/trees",
        "test:test_symbols_example_runs_and_its_tests_pass")),

    Guarantee("positions", "Positions and stacks", (
        "A list that has an index alias is indexed: `appendIndexed` returns a position, and `get`, `set`, and "
        "`getOrTrap` take one. Every list has an identity, given when it is made, and a position carries the "
        "identity of the list it came from: used on any other list it is `list.IndexOutOfRange`, never a read of "
        "another item (D-100).",
        "An indexed list only grows: it has no `clear`, `removeLast`, or `truncate`, so a position never names a "
        "slot that was emptied and reused (R401, D-100). `<Alias>.toInt64` gives a position's number, for printing "
        "and as a key; there is no way back from a number to a position.",
        "`getOrTrap` (lists) and `string.byteAtOrTrap` are the trapping twins of `get` and `byteAt`: for an index "
        "the program has already proved in range, a bad index is a trap rather than an error to branch on (D-101).",
        "A list of plain items is also a stack: `removeLast` takes the last item off (an empty list is "
        "`list.IndexOutOfRange`), and `truncate` cuts the list to a length (D-102).",
        "An item of a list is read as a view; to change a list or record held in a list, `replace` puts a new item "
        "in and hands the old one back owned (for items that are not plain values, as a value of the list's region, "
        "which the call names and the runtime checks), so it can be changed and put back (D-105).",
        "A collection outlives what it stores only if what it stores lives in its region. Text, and text inside "
        "records and enum payloads, is copied into the collection's region when stored (lists, maps, sets, "
        "channels), so text made in a region that ends first stays readable. A value holding a list, map, set, or "
        "channel cannot be copied that way: it must come from a call whose `ownedBy` names the collection's own "
        "region, in the same operation (R514, D-107).",
        "A result is returned in the region its output names: text in it is copied there at the return, and a "
        "list, map, set, or channel in it must have been made there. An error carries only plain values, since no "
        "region is named for it. A type parameter that is not `plain` may stand for a container, so a generic "
        "operation stores its values under the same rule. A `set` takes no value from a view or a borrowed input. "
        "A resource is never a field or a payload (R403, R514, D-108).",
        "A table is a fixed array: `<table>.length` is its row count and `<table>.rowAt` reads a row by the number "
        "its `row` row gives it (1 to n); any other number is `list.IndexOutOfRange` (D-104).",
        "A `constant` is a named literal of a module (`type`, `value`), read by every operation of the module as an "
        "immutable value set on entry; its value is a literal of its type, it cannot be set, and no operation may "
        "reuse its name (R403, R411, D-103).",
    ), (
        Check("positions-and-stacks", "run", "a position read on its own list, refused on another; a stack pushed, "
              "popped, cut, and emptied", (), (), "foreign", base="lists",
              lines=("7", "0", "foreign", "3", "1", "empty", "7", "2", "10", "missing", "1", "name", "7")),
        Check("replace-in-another-region", "reject", "putting back an inner list made in another region",
              ((L, "store released atReturn", "store released atReturn\n\nelsewhere is region\n"
                          "elsewhere in main\nelsewhere strategy arena\nelsewhere maxBytes 1024\n"
                          "elsewhere released atReturn"),
               (L, "takeInner argument region Region store lend", "takeInner argument region Region elsewhere lend"),
               (L, "takeInner ownedBy store", "takeInner ownedBy elsewhere")),
              ("R514",), "its region is `elsewhere`, and `groups`'s is `store`", base="lists"),
        Check("generic-stash", "reject", "a generic operation storing a value of any type in a list the caller lends",
              ((L, "<append>", GENERIC_STASH),), ("R514",), "`thing` is stored in `into`", base="lists"),
        Check("returned-from-local-region", "reject", "returning a stack made in the operation's own region",
              ((L, "<append>", LOCAL_STACK_RETURNED),), ("R514",), "is returned in region `into`", base="lists"),
        Check("set-launders-a-view", "reject", "setting a mutable let from a view of a list's item",
              ((L, "main let eight Int64 8 immutable", "main let eight Int64 8 immutable\nmain let alias Stack unset mutable"),
               (L, "main at measured do innerSize\n", "main at measured set alias stored\nmain at measured do innerSize\n")),
              ("R514",), "a view of `groups`", base="lists"),
        Check("callee-region-stored", "reject", "an operation storing a list made in its own region in its caller's "
              "list", ((L, "<append>", CALLEE_STACK),), ("R514",), "its region is `local`", base="lists"),
        Check("foreign-position-traps", "trap", "the trapping read with a position from the other list",
              ((L, "trapOwn argument list Cells first lend", "trapOwn argument list Cells second lend"),), (),
              "read a position outside its list", base="lists",
              lines=("7", "0", "foreign", "3", "1", "empty")),
        Check("indexed-list-never-clears", "reject", "clearing an indexed list",
              ((L, "main at empty do trapOwn\n", "main at empty do clearFirst\nmain at empty do trapOwn\n"),
               (L, "<append>", _call("clearFirst", "main", "Cells.clear", ("list Cells first lendMutable",)))),
              ("R401",), "has no target `clear`", base="lists"),
        Check("indexed-list-never-shrinks", "reject", "taking the last item off an indexed list",
              ((L, "main at empty do trapOwn\n", "main at empty do dropLast\nmain at empty do trapOwn\n"),
               (L, "<append>", _call("dropLast", "main", "Cells.removeLast", ("list Cells first lendMutable",),
                                     out="dropped Int64"))),
              ("R401",), "has no target `removeLast`", base="lists"),
        Check("table-unknown-target", "reject", "asking a table for a target it does not have",
              ((L, "countPairs invokes pairs.length", "countPairs invokes pairs.size"),), ("R401",),
              "has the targets `rowAt`, `length`, and `find`", base="lists"),
        Check("constant-wrong-type", "reject", "a constant whose value is not of its type",
              ((L, "seven value 7", 'seven value "seven"'),), ("R403",), "constant `seven`", base="lists"),
        Check("constant-shadowed", "reject", "an operation's let with a constant's name",
              ((L, "main let eight Int64 8 immutable", "main let eight Int64 8 immutable\nmain let seven Int64 6 immutable"),),
              ("R411",), "already a module-level name", base="lists"),
        Check("constant-set", "reject", "setting a constant",
              ((L, "main at empty do trapOwn\n", "main at empty set seven eight\nmain at empty do trapOwn\n"),),
              ("R403",), "only a `mutable` let can be set", base="lists"),
    ), ("mutation:map-changed-while-listed", "case:08-strings-collections/trees")),

    Guarantee("modules", "Module contracts", (
        "A module uses another's operation, type, or variant only through `imports` and only if it is exported "
        "(R404). Calls across modules are checked against the callee's declared signature: argument types and loan "
        "modes, output owner, error type, effects, and generic constraints, exactly as within a module.",
        "The whole program, packages included, is checked from source as one unit; there is no separately compiled "
        "module that could skip a check.",
    ), (
        Check("cross-module-mode", "reject", "lending the list exclusively to an imported operation that reads it",
              ((W, "listTask argument lines pricing.Lines lines lend", "listTask argument lines pricing.Lines lines lendMutable"),),
              ("R406", "R515"), "passed as `lend`"),
        Check("cross-module-unexported", "reject", "calling an operation pricing does not export",
              ((W, "listTask invokes pricing.listTotal", "listTask invokes pricing.orderTotal"),),
              ("R404",), "is not exported"),
    ), ("mutation:module-private-symbol", "mutation:module-unexported-type", "mutation:module-missing-import",
        "mutation:generic-constraint-isolated", "mutation:capability-missing-isolated", "mutation:package-version-unmet",
        "case:09-modules/project", "case:09-modules/package")),
)


def render() -> str:
    out = ["# Safety guarantees", "",
           "Generated by `python tests/suite/conformance.py --write` from `tests/suite/conformance.py`; "
           "`tests/test_conformance.py` runs every check below and fails when this file is stale.", "",
           "Each guarantee states the rules the checker and runtime enforce, the conformance checks that prove them "
           "(edits of [a frozen copy of the warehouse example](../tests/suite/conformance/warehouse)), and other "
           "tests that prove them too.", ""]
    for g in GUARANTEES:
        out += [f"## {g.title}", ""]
        out += [f"- {r}" for r in g.rules]
        out += ["", "| Check | Expect | What it shows |", "| --- | --- | --- |"]
        for c in g.checks:
            expect = {"reject": "rejected: " + ", ".join(c.codes), "trap": "traps", "run": "runs",
                      "refused": f"refused to start (exit {c.exit})"}[c.kind]
            out.append(f"| `{c.id}` | {expect} | {c.says} |")
        if g.evidence:
            out += ["", "Also: " + ", ".join(f"`{e}`" for e in g.evidence) + "."]
        out.append("")
    out += ["## Not guaranteed", "",
            "- Deadlock freedom is checked at run time, not statically: a program in which every task waits on "
            "another traps with every wait listed (`case:11-concurrency/trap-channel-deadlock`).",
            "- Arithmetic overflow, division by zero, out-of-range conversions, and a list read past its end are run "
            "time traps or typed errors, not compile-time errors.",
            "- Capability scopes on computed arguments are enforced at run time only.",
            "- Foreign functions (`ffi`) are limited to numbers and `Bool` with no shared memory; what the C code "
            "does inside is outside the language's guarantees.",
            "- Standalone executables link the runtime in SemanticScript and no C library (Windows and x86_64 "
            "Linux, D-141); it implements the host library except `net`, `http`, `json`, `random`, and `signal`, "
            "and `ffi` on Linux, and programs calling those are refused (R901) rather than built (D-137, D-140). "
            "Tasks wait there as under `refined run`: a waiting task is cancelled by a sibling's failure (D-133).",
            "- Running out of a region is a safe trap (D-49), not a typed error: every allocation would otherwise be "
            "fallible. The trap happens before any memory is written and names the region; a program sizes its "
            "regions for what it allocates.",
            "- A grouped task's output is not delivered (`result none`); its failure is, through the group. Use a "
            "plain task when the output matters.",
            "- There is no detached task; work that must outlive its operation is not expressible.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    if "--write" in sys.argv:
        with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render())
        print("wrote", os.path.normpath(DOC))
    else:
        print(render())
