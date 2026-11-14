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

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "conformance", "warehouse")
BASES = {"warehouse": BASE, "groups": os.path.join(HERE, "conformance", "groups"),
         "cleanups": os.path.join(HERE, "conformance", "cleanups")}
DOC = os.path.join(HERE, "..", "..", "docs", "safety-guarantees.md")

W, P, B = "warehouse.sem", "pricing.sem", "build.sem"


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
    lines: tuple = ()  # run and trap: the exact stdout, line by line, when the order matters


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
    return "\n".join(rows)


CLEAR_LINES = _call("clearLines", "main", "pricing.Lines.clear", ("list pricing.Lines lines lendMutable",))
CLEANUP = ('closeReportCleanup is cleanup\ncloseReportCleanup rationale "A report that cannot be closed may not be '
           'fully written, so the program stops"\ncloseReportCleanup in main\ncloseReportCleanup runs closeReport\n'
           'closeReportCleanup cleans report\ncloseReportCleanup onError trap\n')
ANNOUNCE = '''
announceWriter is capability
announceWriter purpose "Authority to write notices to standard error"
announceWriter grants write console.stderr none

announce is operation
announce purpose "Write a notice line to standard error"
announce invariant writesNotice "Writes the text as one line on standard error"
announce typeParameter none
announce input text String borrowed
announce output none
announce outputOwnedBy none
announce raises console.WriteError
announce effect write console.stderr
announce uses announceWriter
announce memoryHeap false
announce async false
announce maxRecursion none
announce label begin loopKind none
announce label begin within none
announce label failed loopKind none
announce label failed within none
announce label done loopKind none
announce label done within none
announce let none
announce at begin do say
announce at begin branch ifError say goto failed else goto done
announce at failed return error sayError
announce at done return ok none

say is call
say in announce
say invokes console.writeError
say argument text String text lend
say result none
say ownedBy none
say cleanedBy none
say borrows none
say catch sayError console.WriteError'''
ANNOUNCE_TEST = '''
announceTest is test
announceTest purpose "announce writes a notice without failing"
announceTest verifies announce writesNotice
announceTest typeParameter none
announceTest input none
announceTest output none
announceTest outputOwnedBy none
announceTest raises none
announceTest effect write console.stderr
announceTest uses announceWriter
announceTest memoryHeap false
announceTest async false
announceTest maxRecursion none
announceTest label begin loopKind none
announceTest label begin within none
announceTest label wrote loopKind none
announceTest label wrote within none
announceTest label failed loopKind none
announceTest label failed within none
announceTest let notice String "pricing test notice" immutable
announceTest let failedText String "writing a notice to standard error failed" immutable
announceTest at begin do runAnnounce
announceTest at begin branch ifError runAnnounce goto failed else goto wrote
announceTest at wrote return ok none
announceTest at failed do failWrite
announceTest at failed return ok none

''' + _call("runAnnounce", "announceTest", "announce", ("text String notice lend",),
             catch="announceError console.WriteError") + "\n\n" + _call(
    "failWrite", "announceTest", "test.fail", ("message String failedText lend",))
FAILING = (("cleanups.sem", "closeSecond invokes closeNoting\ncloseSecond argument file fs.FileHandle second give\n"
                 "closeSecond argument note String secondNote lend",
                 "closeSecond invokes closeFailing\ncloseSecond argument file fs.FileHandle second give"),
                ("cleanups.sem", "closeSecond catch closeSecondError fs.FileError",
                 "closeSecond catch closeSecondError CloseError"),
                ("cleanups.sem", 'main let secondNote String "closing second" immutable\n', ""))
FAILING_TRAP = FAILING + (("cleanups.sem", "releaseSecond runs closeSecond\nreleaseSecond cleans second\n"
                                           "releaseSecond onError suppress",
                           "releaseSecond runs closeSecond\nreleaseSecond cleans second\nreleaseSecond onError trap"),)
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
    ), (
        Check("use-after-close", "reject", "writing a report after closing it",
              ((W, "main at opened defer closeReportCleanup\n", "main at opened do closeReport\n"),
               (W, "openReport cleanedBy closeReportCleanup", "openReport cleanedBy none"), (W, CLEANUP, "")),
              ("R513", "R506"), "`report` may already have been given away"),
        Check("let-aliases-a-loan", "reject", "a `let` naming a borrowed list",
              ((P, "orderTotal let running Int64 0 mutable\n",
                "orderTotal let running Int64 0 mutable\norderTotal let alias Lines lines immutable\n"),),
              ("R514",), "a let copies only plain values"),
        Check("resource-in-collection", "reject", "a list of file handles",
              ((W, "warehouse imports pricing", "warehouse imports standard.list\nwarehouse imports pricing"),
               (W, "<append>", 'Handles is typeInstance\nHandles purpose "Open files kept in a list"\n'
                               'Handles instantiates list.List fs.FileHandle')),
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
        "Cancellation is observed at waits (channel operations, sleeps, accepts, reads, child processes, file "
        "locks): the wait ends with the `cancelled` variant of its error. Computation between waits runs to its "
        "end, so a cancelled task always finishes in a defined state.",
    ), (
        Check("cancel-without-join", "reject", "cancelling a task and returning without joining it",
              ((W, "main at stopDiscount join discountTask\nmain at stopDiscount branch ifError discountTask goto "
                   "listFailed else goto listFailed", "main at stopDiscount goto listFailed"),),
              ("R512",), "was cancelled but is not joined"),
        Check("no-detach", "reject", "`detach` is not a step",
              ((W, "main at price start discountTask into none", "main at price detach discountTask"),),
              ("R205", "R510"), "step row must be"),
        Check("runs", "run", "the program prices the order in two tasks and prints the report",
              (), (), "list=3750 discounted=3375"),
        Check("group-first-failure", "run", "a group's failing task cancels a ten-second sibling; `join` delivers "
              "its error at once (exit 3: stopped early)", (), (), "-3", base="groups", exit=3),
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
        Check("effect-across-modules", "reject", "calling an imported operation that writes to standard error",
              ((P, "pricing imports standard.list", "pricing imports standard.list\npricing imports standard.console"),
               (P, "pricing exports discountTotal", "pricing exports discountTotal\npricing exports announce"),
               (P, "<append>", ANNOUNCE),
               ("pricing.test.sem", "<append>", ANNOUNCE_TEST),
               (B, "warehouse allows write console.stdout none",
                "warehouse allows write console.stdout none\nwarehouse allows write console.stderr none"),
               (W, "main at finished return ok okCode",
                "main at finished do announceDone\nmain at finished branch ifError announceDone goto outputFailed "
                "else goto exit\nmain at exit return ok okCode"),
               (W, "main label listFailed loopKind none", "main label exit loopKind none\nmain label exit within none\n"
                                                         "main label listFailed loopKind none"),
               (W, "main let okCode ExitCode 0 immutable", 'main let okCode ExitCode 0 immutable\n'
                                                          'main let doneText String "warehouse done" immutable'),
               (W, "<append>", _call("announceDone", "main", "pricing.announce", ("text String doneText lend",),
                                     catch="announceError console.WriteError"))),
              ("R407",), "`main` performs `write console.stderr`"),
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
    ), (
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
        "Sending both outcomes to the same block discards the failure, which needs a `rationale` row saying why; "
        "filler text is rejected (R506, R304).",
    ), (
        Check("discard-without-reason", "reject", "both outcomes of a join go to the same block, with no reason",
              ((W, 'discountTask rationale "Once the list total has failed, the discount total is cancelled and its '
                   'outcome no longer matters"\n', ""),), ("R506",), "needs a `rationale` row"),
        Check("discard-with-filler", "reject", "a rationale that says nothing",
              ((W, 'discountTask rationale "Once the list total has failed, the discount total is cancelled and its '
                   'outcome no longer matters"', 'discountTask rationale "ignored"'),), ("R304",), "filler"),
        Check("match-incomplete", "reject", "a match missing `emptyOrder`",
              ((W, "main at listFailed case pricing.PricingError.emptyOrder bind none none goto noLines\n", ""),),
              ("R509",), "has no case for `emptyOrder`"),
        Check("wrong-error-type", "reject", "catching an imported operation's error as the wrong type",
              ((W, "listTask catch listError pricing.PricingError", "listTask catch listError fs.FileError"),),
              ("R403",), "raises `pricing.PricingError`"),
    ), ("mutation:catch-missing", "mutation:catch-wrong-type", "mutation:raise-undeclared", "mutation:raise-wrong-type",
        "mutation:error-not-passed-up", "mutation:error-match-incomplete", "mutation:error-match-duplicate",
        "case:10-errors/errors")),

    Guarantee("cleanup", "Deterministic cleanup", (
        "A cleanup is deferred after the value it cleans exists, and exactly once on a path (R507, R510); it runs at "
        "every later `return`, `ok` or `error`, newest first, and only once.",
        "A cleanup's call takes the value with `give`: the value is consumed even if releasing it fails. "
        "`onError trap` stops the program; `onError suppress` continues. Every cleanup states a `rationale` row saying why its policy is right (R302).",
        "A trap does not run cleanups: the process ends and the operating system releases what it held.",
        "A cancelled task runs the cleanups of the operations it unwinds through, since cancellation reaches it as "
        "an error.",
    ), (
        Check("cleanup-deferred-twice", "reject", "deferring the report's cleanup twice",
              ((W, "main at opened defer closeReportCleanup\n",
                "main at opened defer closeReportCleanup\nmain at opened defer closeReportCleanup\n"),),
              ("R510",), "is deferred 2 times"),
        Check("cleanup-before-acquire", "reject", "deferring the cleanup before the file is open",
              ((W, "main at createNew do openReport\n", "main at createNew defer closeReportCleanup\n"
                                                        "main at createNew do openReport\n"),
               (W, "main at opened defer closeReportCleanup\n", "")),
              ("R507", "R513"), "may not be set here"),
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
        Check("cleanup-missing", "reject", "never deferring the report's cleanup",
              ((W, "main at opened defer closeReportCleanup\n", ""),), ("R513", "R510"), "may still be owned"),
    ), ("mutation:cleanup-not-deferred", "mutation:cleanup-wrong-value", "mutation:cleanup-suppress-without-reason",
        "mutation:cleanup-before-acquire", "case:07-memory/cleanup-on-error", "case:06-recursion/recursive-cleanup",
        "case:07-memory/resources")),

    Guarantee("regions", "Region memory", (
        "Every allocation names a region; a region's `capacity` is a hard limit. Allocating past it traps with the "
        "region's name before any memory is written, so exhaustion never corrupts memory (A10).",
        "A region is released at its operation's return, after every task that could use it has been joined; values "
        "it owns cannot be returned unless the output names the region as owner (R409, R512).",
    ), (
        Check("arena-exhausted", "trap", "a 64-byte region for the whole program",
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
               (W, "main at opened branch ifError writeReport goto fileFailed else goto readBack",
                "main at opened branch ifError writeReport goto stopAgain else goto joinAgain\n"
                "main at joinAgain join writeAgain\nmain at joinAgain branch ifError writeAgain goto fileFailed else goto readBack\n"
                "main at stopAgain cancel writeAgain\nmain at stopAgain join writeAgain\n"
                "main at stopAgain branch ifError writeAgain goto fileFailed else goto fileFailed"),
               (W, "main label readBack loopKind none", "main label joinAgain loopKind none\nmain label joinAgain within none\n"
                "main label stopAgain loopKind none\nmain label stopAgain within none\nmain label readBack loopKind none"),
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
              ((W, "main at stopDiscount branch ifError discountTask goto listFailed else goto listFailed",
                "main at stopDiscount branch ifError discountTask goto listFailed else goto printTotals"),),
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
    ), (
        Check("table-rows-exceed-bound", "reject", "a three-row table read by a loop bounded at 2",
              ((W, "main label fill maxIterations 3", "main label fill maxIterations 2"),), ("R503",), "has 3 rows"),
        Check("list-exceeds-bound", "trap", "a three-line order priced by a loop bounded at 2",
              ((P, "orderTotal label sumLines maxIterations 1000", "orderTotal label sumLines maxIterations 2"),), (),
              "more than maxIterations 2 times"),
    ), ("mutation:append-during-foreach", "mutation:list-index-unchecked", "mutation:table-missing-cell",
        "mutation:table-cell-wrong-type", "case:04-control-flow/trap-loop-bound")),

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
            expect = {"reject": "rejected: " + ", ".join(c.codes), "trap": "traps", "run": "runs"}[c.kind]
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
            "- Standalone executables include only the core runtime; programs calling host-library targets are "
            "refused (R901) rather than built.",
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
