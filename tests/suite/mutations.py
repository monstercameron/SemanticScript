"""Negative cases: one deliberate mistake in a program case that passes.

Each entry copies a case from `programs/`, replaces `old` (which must occur
exactly once) with `new` in one file, and asserts the checker reports exactly
the listed codes (as a set) and nothing else. That makes every entry a proof
that the rule fires on its own, and that the mistake is not also tripping
unrelated rules.

Fields: id, the checklist items it covers (`<section> <item>`), the case, old,
new, the expected codes, and the file inside the case (`None` for the module
file of a single-file case). `old` and `new` may be tuples of the same length
for a mistake that needs more than one edit; each `old` must occur exactly once.

Some mistakes also break what depends on them (removing a branch makes a block
unreachable, say). Those follow-on codes are listed too, so the exact set of
diagnostics is pinned.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mutation:
    id: str
    covers: tuple[str, ...]
    case: str
    old: str | tuple[str, ...]
    new: str | tuple[str, ...]
    codes: tuple[str, ...]
    file: str | None = None

    def edits(self) -> list[tuple[str, str]]:
        olds = self.old if isinstance(self.old, tuple) else (self.old,)
        news = self.new if isinstance(self.new, tuple) else (self.new,)
        assert len(olds) == len(news), self.id
        return list(zip(olds, news))


V = "01-variables/variables"
INTS = "02-types/integers"
SHAPES = "02-types/shapes"
OPS = "03-operators/operators"
CTRL = "04-control-flow/control"
FUNCS = "05-functions/functions"
REC = "06-recursion/recursion"
MEM = "07-memory/region-list"
RES = "07-memory/resources"
STR = "08-strings-collections/strings"
SORT = "08-strings-collections/sorting"
TABLE = "08-strings-collections/table"
MODS = "09-modules/project"
PKG = "09-modules/package"
ERR = "10-errors/errors"
CONC = "11-concurrency/tasks-and-channels"
CONS = "12-io/console"
FREAD = "12-io/file-read"
NET = "12-io/network-connect"
PROC = "12-io/process-run"
EFF = "13-capabilities/effects"
GEN = "14-types-generics/generics"
MIN = "22-edge/minimal"
TESTS = "20-testing/tests-pass"

M = Mutation
MUTATIONS: list[Mutation] = [
    # ---------------------------------------------------------------- 1 variables
    M("var-shadowing", ("1 Variable shadowing", "21 Duplicate declarations are rejected"), V,
      "main let one immutable Int64 1\n", "main let one immutable Int64 1\nmain let one immutable Int64 2\n", ("R411",)),
    M("var-shadow-label", ("1 Variable scope", "21 Duplicate symbols are rejected"), V,
      "main let one immutable Int64 1\n", "main let one immutable Int64 1\nmain let merged immutable Int64 2\n", ("R411",)),
    M("var-uninitialized-path", ("1 Uninitialized variables", "21 Variables are initialized before use"), V,
      "main at seven set chosen sevenValue\n", "", ("R507",)),
    M("var-set-immutable", ("1 Immutable variables", "1 Constants"), V,
      "main at begin set counter bumped", "main at begin set ten bumped", ("R403",)),
    M("var-undefined", ("21 Every referenced variable is defined",), V,
      "showStart arg value Int64 counter copy", "showStart arg value Int64 countr copy", ("R401",)),
    M("var-global", ("1 Global variables",), V,
      "variables exports main\n", "variables exports main\nvariables let shared mutable Int64 0\n", ("R204",)),
    M("var-annotation-mismatch", ("1 Type annotations", "14 Type mismatch detection"), V,
      "main let ten immutable Int64 10", 'main let ten immutable Int64 "ten"', ("R403",)),
    M("var-no-inference", ("1 Type inference", "14 Type inference"), V,
      "main let ten immutable Int64 10", "main let ten immutable 10", ("R205", "R401")),
    M("var-set-wrong-type", ("1 Variable reassignment", "17 Type safety"), V,
      "main at seven set chosen sevenValue", "main at seven set chosen pickSeven", ("R403",)),
    # ---------------------------------------------------------------- 2 data types
    M("int8-literal-too-large", ("2 Signed integers (8/16/32/64-bit)", "22 Maximum integer values"), INTS,
      "main let max8 immutable Int8 127", "main let max8 immutable Int8 128", ("R403",)),
    M("int16-literal-too-small", ("2 Signed integers (8/16/32/64-bit)", "22 Minimum integer values"), INTS,
      "main let min16 immutable Int16 -32768", "main let min16 immutable Int16 -32769", ("R403",)),
    M("uint-negative", ("2 Unsigned integers",), INTS,
      "main let maxU8 immutable UInt8 255", "main let maxU8 immutable UInt8 -1", ("R403",)),
    M("uint64-too-large", ("2 Unsigned integers", "22 Maximum integer values"), INTS,
      "main let maxU64 immutable UInt64 18446744073709551615", "main let maxU64 immutable UInt64 18446744073709551616",
      ("R403",)),
    M("int64-too-large", ("22 Maximum integer values",), INTS,
      "main let maxValue immutable Int64 9223372036854775807", "main let maxValue immutable Int64 9223372036854775808",
      ("R403",)),
    M("no-implicit-widening", ("14 Implicit conversions", "2 Type compatibility"), INTS,
      "show32 arg value Int64 wide32 copy", "show32 arg value Int64 max32 copy", ("R403",)),
    M("float-into-integer", ("2 Floating-point numbers", "14 Implicit conversions"), INTS,
      "main let small immutable Int64 -128", "main let small immutable Int64 -128.0", ("R403",)),
    M("record-missing-field", ("2 Structures / Records", "5 Default arguments"), SHAPES,
      "makePoint arg y Int64 four copy\n", "", ("R405",)),
    M("record-unknown-field", ("2 Structures / Records",), SHAPES,
      "readX invokes Point.x", "readX invokes Point.z", ("R401",)),
    M("recursive-type-by-value", ("2 Recursive types", "6 Recursive data structures"), SHAPES,
      "Point field y Int64\n", "Point field y Int64\nPoint field next Point\n", ("R403", "R405")),
    M("enum-unknown-variant", ("2 Enumerations", "2 Unions"), SHAPES,
      "makeSquare invokes Shape.square", "makeSquare invokes Shape.circle", ("R401",)),
    M("enum-payload-type", ("2 Unions", "17 Type safety"), SHAPES,
      "makeSquare arg payload Int64 five copy", "makeSquare arg payload Meters distance copy", ("R403",)),
    M("alias-is-distinct", ("2 Type aliases", "14 Subtyping"), SHAPES,
      "makeSquare arg payload Int64 five copy", "makeSquare arg payload Int64 distance copy", ("R403",)),
    M("option-wrong-payload", ("2 Optional / Nullable types", "7 Null pointer handling"), SHAPES,
      "inspectAbsent case MaybeCount.present bind found Int64", "inspectAbsent case MaybeCount.present bind found Bool",
      ("R403",)),
    M("generic-instance-arity", ("2 Generic types", "14 Generic structures"), SHAPES,
      "IntHolder instantiates Holder Int64", "IntHolder instantiates Holder Int64 Int64", ("R403",)),
    M("type-wrong-case", ("2 User-defined types",), SHAPES,
      "Meters is alias\n", "meters is alias\nmeters purpose \"A type named like a value\"\nmeters for Int64\n"
      "meters indexes none\n\nMeters is alias\n", ("R207",)),
    # ---------------------------------------------------------------- 3 operators
    M("operator-type-mismatch", ("3 Equality", "14 Static type checking"), OPS,
      "eq invokes compare.equalInt64", "eq invokes compare.equalFloat64", ("R403",)),
    M("logic-on-integers", ("3 Logical AND / OR / NOT",), OPS,
      "both invokes logic.and", "both invokes bits.andInt64", ("R403",)),
    M("operator-missing-operand", ("3 Operator precedence", "5 Named arguments"), OPS,
      "add arg right Int64 three copy\n", "", ("R405",)),
    M("operator-extra-operand", ("5 Variadic arguments",), OPS,
      "add arg right Int64 three copy\n", "add arg right Int64 three copy\nadd arg third Int64 three copy\n", ("R405",)),
    M("operator-wrong-slot", ("5 Named arguments", "3 Operator associativity"), OPS,
      "add arg left Int64 seven copy", "add arg first Int64 seven copy", ("R405",)),
    M("operator-wrong-mode", ("5 Parameter passing by value", "21 Call argument types match parameters"), OPS,
      "add arg left Int64 seven copy", "add arg left Int64 seven lend", ("R406",)),
    M("compound-assignment", ("3 Compound assignment",), OPS,
      "main at begin do add\n", "main at begin set seven sum\nmain at begin do add\n", ("R403", "R507")),
    # ---------------------------------------------------------------- 4 control flow
    M("branch-unknown-label", ("4 Goto / Branching", "21 Branch targets exist", "21 Every label exists"), CTRL,
      "grade at begin branch if isBelowTen goto low else goto notLow",
      "grade at begin branch if isBelowTen goto lowest else goto notLow", ("R502", "R511")),
    M("unreachable-block", ("4 Unreachable code", "21 Unreachable labels are detected"), CTRL,
      "grade at high return ok three\n",
      "grade at high return ok three\ngrade at orphan return ok one\n", ("R305", "R511")),
    M("statement-after-return", ("4 Early return", "4 Control-flow validation"), CTRL,
      "grade at low return ok one\n", "grade at low return ok one\ngrade at low goto high\n", ("R501",)),
    M("block-falls-through", ("4 Control-flow validation", "21 Invalid operation graphs are rejected"), V,
      "main at merged return ok okCode\n", "", ("R501",)),
    M("branch-on-integer", ("4 If / Else", "4 Conditional expressions"), CTRL,
      "grade at begin branch if isBelowTen goto low else goto notLow",
      "grade at begin branch if score goto low else goto notLow", ("R403",)),
    M("loop-without-bound", ("4 While loops", "4 Loop termination"), CTRL,
      "oddSum label scan maxIterations 20\n", "", ("R503",)),
    M("cycle-without-header", ("4 Labels", "4 Infinite loops", "22 Infinite loops"), CTRL,
      "oddSum label scan loopKind while", "oddSum label scan loopKind none", ("R503", "R504")),
    M("jump-into-loop", ("4 Nested loops", "4 Control-flow validation"), CTRL,
      "gridCells at begin goto rows", "gridCells at begin goto countCell", ("R504",)),
    M("counted-not-advancing", ("4 For loops", "4 Loop termination"), CTRL,
      "sumToFive at addStep set index nextIndex\n", "", ("R505",)),
    M("counted-wrong-direction", ("4 For loops", "22 Infinite loops"), CTRL,
      "advance invokes math.addInt64\nadvance arg left Int64 index copy",
      "advance invokes math.subtractInt64\nadvance arg left Int64 index copy", ("R505",)),
    M("counted-wrong-bound", ("4 Loop termination",), CTRL,
      "sumToFive label sumLoop maxIterations 5", "sumToFive label sumLoop maxIterations 6", ("R505",)),
    M("forever-with-bound", ("4 Infinite loops",), CTRL,
      "halvings label halve maxIterations unbounded", "halvings label halve maxIterations 20", ("R503",)),
    M("unbounded-while", ("4 While loops",), CTRL,
      "oddSum label scan maxIterations 20", "oddSum label scan maxIterations unbounded", ("R503",)),
    M("break-without-within", ("4 Break", "4 Continue"), CTRL,
      "oddSum label keep within scan", "oddSum label keep within none", ("R504",)),
    M("label-missing-declaration", ("4 Labels", "15 Syntax parsing"), CTRL,
      "grade label middle within none\n", "", ("R305",)),
    M("first-block-not-begin", ("16 Entry-point discovery", "4 Labels"), MIN,
      "main label begin loopKind none\nmain label begin within none\nmain let zero immutable ExitCode 0\n"
      "main at begin return ok zero",
      "main label start loopKind none\nmain label start within none\nmain let zero immutable ExitCode 0\n"
      "main at start return ok zero", ("R501", "R511")),
    # ---------------------------------------------------------------- 5 functions
    M("call-unknown-operation", ("21 Every call references an existing operation", "5 Function invocation"), FUNCS,
      "twiceDoubled invokes applyTwice", "twiceDoubled invokes applyThrice", ("R401",)),
    M("call-in-unknown-operation", ("21 Every call belongs to a valid operation",), FUNCS,
      "twiceDoubled in main", "twiceDoubled in mane", ("R401",)),
    M("call-never-activated", ("5 Function invocation", "21 Invalid operation graphs are rejected"), FUNCS,
      "main at begin do showComposed\n", "", ("R510",)),
    M("call-activated-twice", ("21 Execution order is deterministic where specified",), FUNCS,
      "main at begin do showComposed\n", "main at begin do showComposed\nmain at begin do showComposed\n", ("R510",)),
    M("overloading", ("5 Function overloading", "21 Duplicate declarations are rejected",
                      "21 Duplicate symbols are rejected", "15 Symbol resolution"), MIN,
      "main at begin return ok zero", 'main at begin return ok zero\n\nmain is operation\nmain purpose "A second main: operations are not overloaded"\nmain invariant none\nmain typeParam none\nmain input none\nmain output ExitCode\nmain outputOwner none\nmain raises none\nmain effect none\nmain uses none\nmain memory heap false\nmain async false\nmain maxRecursion none\nmain label begin loopKind none\nmain label begin within none\nmain let zero immutable ExitCode 0\nmain at begin return ok zero', ("R203",)),
    M("default-argument", ("5 Default arguments", "5 Function parameters"), FUNCS,
      "twiceDoubled arg value Int64 three copy\n", "", ("R405",)),
    M("return-wrong-type", ("5 Return values", "21 Return types match operation declarations"), FUNCS,
      "main at begin return ok okCode", "main at begin return ok three", ("R403",)),
    M("missing-output", ("21 Required outputs are assigned",), FUNCS,
      "double at begin return ok scaled", "double at begin return ok none", ("R508",)),
    M("change-through-read-loan", ("7 Immutable borrowing", "5 Parameter passing by reference",
                                   "21 Borrowing constraints are enforced"), FUNCS,
      "appendThree input numbers Numbers borrowedMutable", "appendThree input numbers Numbers borrowed",
      ("R515", "R406")),
    M("reference-signature-mismatch", ("2 Function types", "14 Variance", "5 Function references"), FUNCS,
      "main let doubleStep immutable IntStep double", "main let doubleStep immutable IntStep appendThree", ("R403",)),
    M("reference-not-an-operation", ("5 Higher-order functions", "5 Lambdas", "5 Anonymous functions", "5 Closures"),
      FUNCS, "main let doubleStep immutable IntStep double", "main let doubleStep immutable IntStep three", ("R403",)),
    M("by-reference-needs-mutable-loan", ("5 Parameter passing by reference", "7 Mutable borrowing"), FUNCS,
      "fill arg numbers Numbers numbers lendMutable", "fill arg numbers Numbers numbers lend", ("R406",)),
    # ---------------------------------------------------------------- 6 recursion
    M("recursion-undeclared", ("6 Maximum recursion depth", "21 Recursion limits are enforced"), REC,
      "factorial maxRecursion 25", "factorial maxRecursion none", ("R410",)),
    M("mutual-recursion-undeclared", ("6 Mutual recursion", "6 Indirect recursion"), REC,
      "isOdd maxRecursion 50", "isOdd maxRecursion none", ("R410",)),
    M("recursion-declared-not-recursive", ("21 Recursion limits are enforced",), REC,
      "main maxRecursion none", "main maxRecursion 3", ("R410",)),
    M("error-not-passed-up", ("6 Recursion with error propagation", "10 Unhandled errors"), REC,
      "countdown at step branch ifError recurse goto passUp else goto ok\n", "", ("R501", "R506", "R511")),
    # ---------------------------------------------------------------- 7 memory
    M("region-value-without-owner", ("7 Ownership", "21 Ownership constraints are enforced"), MEM,
      "makeNumbers ownedBy scratch", "makeNumbers ownedBy none", ("R409",)),
    M("heap-undeclared", ("7 Stack allocation", "7 Heap allocation", "21 Heap restrictions are enforced"), MEM,
      "main memory heap true", "main memory heap false", ("R410",)),
    M("mutable-loan-of-read-loan", ("7 Immutable borrowing", "21 Borrowing constraints are enforced"), MEM,
      "appendIndex arg list Numbers numbers lendMutable", "appendIndex arg list Numbers numbers lend", ("R406",)),
    M("double-give", ("7 Double-free prevention", "7 Ownership transfer", "7 Use-after-free prevention",
                      "7 Dangling references"), RES,
      ("main at handOff do giveSecond\n", "giveSecond is call\n"),
      ("main at handOff do giveSecond\nmain at handOff do giveAgain\n",
       "giveAgain is call\ngiveAgain in main\ngiveAgain invokes closeFor\ngiveAgain arg file fs.FileHandle second give\n"
       "giveAgain out closedAgain Bool\ngiveAgain ownedBy none\ngiveAgain cleanedBy none\ngiveAgain borrows none\n"
       "giveAgain catch none\n\ngiveSecond is call\n"), ("R513",)),
    M("owned-never-released", ("7 Memory leak detection", "21 Cleanup obligations are enforced"), RES,
      "main at handOff do giveSecond\n", "", ("R507", "R510", "R513")),
    M("cleanup-not-deferred", ("7 Resource cleanup", "7 Deterministic destruction", "10 Cleanup after errors"), RES,
      "main at opened defer closeFirstCleanup\n", "", ("R510", "R513")),
    M("cleanup-wrong-value", ("7 Resource cleanup",), RES,
      "closeFirst arg file fs.FileHandle first give", "closeFirst arg file fs.FileHandle second give", ("R409", "R507")),
    M("give-borrowed", ("7 Borrowing", "17 Memory safety"), RES,
      "closeFor input file fs.FileHandle owned", "closeFor input file fs.FileHandle borrowed", ("R406", "R514")),
    M("cleanup-suppress-without-reason", ("10 Errors during resource cleanup",), RES,
      'closeFirstCleanup because "A failed close at exit has nobody to report to"\n', "", ("R302",)),
    # ---------------------------------------------------------------- 8 strings and collections
    M("string-slice-unchecked", ("8 String slicing", "21 Error handling matches declared error types"), STR,
      "main at begin branch ifError cut goto broken else goto showCut\n", "main at begin goto showCut\n", ("R506", "R507")),
    M("string-borrow-undeclared", ("8 String slicing", "7 Memory lifetime tracking"), STR,
      "cut borrows joined", "cut borrows none", ("R409",)),
    M("string-owner-undeclared", ("8 String concatenation", "7 Dynamic allocation"), STR,
      "join ownedBy text", "join ownedBy none", ("R409",)),
    M("string-is-not-integer", ("8 String comparison", "14 Type mismatch detection"), STR,
      "sameText arg right String helloWorld lend", "sameText arg right String seven lend", ("R403",)),
    M("list-index-unchecked", ("8 Array bounds checking", "17 Bounds checking"), SORT,
      "sortInPlace at readPair branch ifError readLeft goto brokenLeft else goto readRightStep\n",
      "sortInPlace at readPair goto readRightStep\n", ("R506", "R507", "R511")),
    M("table-position-gap", ("8 Array initialization", "8 Array indexing"), TABLE,
      "catalog row cheese 3", "catalog row cheese 4", ("R306",)),
    M("table-missing-cell", ("8 Array initialization", "2 Structures / Records"), TABLE,
      "catalog cell bread price 20\n", "", ("R306",)),
    M("table-cell-wrong-type", ("2 Type compatibility",), TABLE,
      "catalog cell bread price 20", 'catalog cell bread price "twenty"', ("R403",)),
    M("list-wrong-item-type", ("2 Lists", "8 Collection insertion"), SORT,
      "appendFive arg item Int64 five copy", "appendFive arg item Bool five copy", ("R403",)),
    # ---------------------------------------------------------------- 9 modules
    M("module-private-symbol", ("9 Visibility / Access modifiers", "9 Public / Private symbols", "17 Module isolation"),
      MODS, "readWidth invokes shapes.width", "readWidth invokes shapes.hidden", ("R404",), file="app.sem"),
    M("module-missing-import", ("9 Import resolution", "9 Module imports"), MODS,
      "app imports geometry.area\n", "", ("R404",), file="app.sem"),
    M("module-unused-import", ("9 Dependency management", "23 Dependency resolution"), MODS,
      "app imports geometry.area\n", "app imports geometry.area\napp imports standard.math\n", ("R404",), file="app.sem"),
    M("module-cycle", ("9 Circular imports", "22 Circular dependencies", "21 Module dependency cycles are handled"),
      MODS, "shapes imports standard.test\n", "shapes imports standard.test\nshapes imports geometry.area\n",
      ("R603", "R404"), file="geometry/shapes.sem"),
    M("module-path-mismatch", ("9 Nested modules", "9 Module declaration"), MODS,
      "area path geometry.area", "area path geometry.areas", ("R602", "R404"), file="geometry/area.sem"),
    M("module-file-missing", ("9 Import resolution",), MODS,
      "modulesDemo module geometry.area", "modulesDemo module geometry.volume", ("R602", "R404", "R401"),
      file="build.sem"),
    M("module-unexported-type", ("9 Cross-module type references",), MODS,
      "shapes exports Rectangle\n", "", ("R404",), file="geometry/shapes.sem"),
    M("module-unknown-standard", ("9 Module aliases",), MODS,
      "app imports standard.console", "app imports standard.konsole", ("R404", "R407"), file="app.sem"),
    M("entry-not-exported", ("16 Entry-point discovery",), MODS,
      "app exports main", "app exports none", ("R601",), file="app.sem"),
    M("entry-missing", ("16 Entry-point discovery", "23 CLI compiler invocation"), MODS,
      "modulesDemo entry app.main", "modulesDemo entry app.start", ("R601", "R304"), file="build.sem"),
    M("package-version-unmet", ("23 Version constraints", "23 Dependency resolution"), PKG,
      'packageDemo requires geometryKit "packages/geometryKit" ">=1.0.0 <2.0.0"',
      'packageDemo requires geometryKit "packages/geometryKit" ">=2.0.0"', ("R601",), file="build.sem"),
    M("package-bad-constraint", ("23 Version constraints",), PKG,
      'packageDemo requires geometryKit "packages/geometryKit" ">=1.0.0 <2.0.0"',
      'packageDemo requires geometryKit "packages/geometryKit" "about one"', ("R601", "R404", "R401"),
      file="build.sem"),
    M("package-missing", ("23 Package management",), PKG,
      'packageDemo requires geometryKit "packages/geometryKit" ">=1.0.0 <2.0.0"',
      'packageDemo requires geometryKit "packages/elsewhere" ">=1.0.0 <2.0.0"', ("R601", "R404", "R401"),
      file="build.sem"),
    M("package-cycle", ("22 Circular dependencies", "23 Dependency resolution"), PKG,
      "geometryKit requires none", 'geometryKit requires packageDemo "../.." "*"', ("R603",),
      file="packages/geometryKit/build.sem"),
    M("package-not-a-library", ("23 Package management",), PKG,
      "geometryKit target library", "geometryKit target console", ("R601",),
      file="packages/geometryKit/build.sem"),
    M("standard-library-version", ("23 Standard library versioning",), PKG,
      "packageDemo standardLibrary 1", "packageDemo standardLibrary 2", ("R601",), file="build.sem"),
    M("language-version", ("23 Language feature versioning", "23 Backward compatibility"), PKG,
      "packageDemo language refined-1", "packageDemo language refined-2", ("R205", "R302"), file="build.sem"),
    M("project-version-format", ("23 Package management",), PKG,
      'packageDemo version "0.1.0"', 'packageDemo version "one"', ("R601",), file="build.sem"),
    M("library-with-entry", ("23 Package management",), MODS,
      "modulesDemo target console", "modulesDemo target library", ("R601",), file="build.sem"),
    # ---------------------------------------------------------------- 10 errors
    M("raise-undeclared", ("10 Custom error types", "21 Error handling matches declared error types"), ERR,
      "loadPort raises ConfigError", "loadPort raises none", ("R508", "R403")),
    M("raise-wrong-type", ("10 Multiple error types",), ERR,
      "parsePort at badText return error notNumber", "parsePort at badText return error parseError", ("R403",)),
    M("catch-wrong-type", ("10 Error catching",), ERR,
      "parseIt catch innerError ConfigError", "parseIt catch innerError string.ParseError", ("R403",)),
    M("catch-missing", ("10 Unhandled errors", "10 Exception handling"), ERR,
      "loadGood catch goodError ConfigError", "loadGood catch none", ("R403", "R506")),
    M("error-match-incomplete", ("14 Exhaustive pattern matching", "4 Switch / Match"), ERR,
      "main at inspect case ConfigError.notANumber bind none none goto broken\n", "", ("R509",)),
    M("error-match-duplicate", ("4 Pattern matching",), ERR,
      "main at inspect case ConfigError.notANumber bind none none goto broken\n",
      "main at inspect case ConfigError.notANumber bind none none goto broken\n"
      "main at inspect case ConfigError.notANumber bind none none goto broken\n", ("R509",)),
    # ---------------------------------------------------------------- 11 concurrency
    M("task-not-joined", ("11 Structured concurrency", "11 Thread termination", "21 Async restrictions are enforced"),
      CONC, "main at begin join squareThree\n", "", ("R512", "R507", "R510")),
    M("group-not-joined", ("11 Task scheduling", "11 Structured concurrency"), CONC,
      "main at begin join workers\n", "", ("R512",)),
    M("async-undeclared", ("11 Async functions", "11 Await"), CONC,
      "main async true", "main async false", ("R410",)),
    M("wait-without-task", ("11 Futures / Promises", "11 Timeouts"), CONC,
      "main at begin start nap\nmain at begin cancel nap\nmain at begin join nap\n", "main at begin do nap\n",
      ("R402", "R510")),
    M("shared-mutable-to-task", ("11 Shared mutable state", "11 Race-condition detection", "11 Mutexes", "11 Locks",
                                 "11 Atomic operations"), CONC,
      "produce arg channel Mailbox mailbox lend", "produce arg channel Mailbox mailbox lendMutable", ("R406",)),
    # ---------------------------------------------------------------- 12/13 I/O, capabilities, effects
    M("capability-missing", ("13 Unauthorized capability access", "13 Console capability enforcement",
                             "21 Required capabilities are present"), CONS,
      "main uses stderrWriter\n", "", ("R408",)),
    M("capability-unused", ("13 Capability restriction", "21 Unnecessary capabilities are rejected or reported"), EFF,
      "square uses none", "square uses stdoutWriter", ("R408",)),
    M("effect-undeclared", ("13 Effect validation", "13 Nested operation effects",
                            "21 Declared effects match actual effects"), EFF,
      "report effect write console.stdout", "report effect none", ("R407", "R408")),
    M("effect-declared-not-performed", ("13 Effect declaration", "13 Pure operation enforcement"), EFF,
      "square effect none", "square effect write console.stdout", ("R407", "R408")),
    M("capability-scope-escape", ("13 File-system capability enforcement", "13 Capability escalation prevention",
                                  "17 Sandboxing", "17 Injection resistance"), FREAD,
      'main let path immutable String "suite-input.txt"', 'main let path immutable String "/etc/passwd"', ("R408",)),
    M("capability-scope-host", ("13 Network capability enforcement",), NET,
      'main let address immutable String "127.0.0.1:47811"', 'main let address immutable String "192.0.2.1:47811"',
      ("R408",)),
    M("capability-scope-program", ("13 Resource access permissions", "17 Privilege separation"), PROC,
      'main let git immutable String "git"', 'main let git immutable String "rm"', ("R408",)),
    M("capability-wrong-grant", ("13 Capability granting", "13 Capability declaration"), CONS,
      "stderrWriter grants write console.stderr", "stderrWriter grants read console.stderr", ("R408",)),
    # ---------------------------------------------------------------- 14 generics
    M("generic-called-directly", ("14 Generic functions", "14 Type parameter inference"), GEN,
      "chooseInt invokes pickInt", "chooseInt invokes pick", ("R402",)),
    M("generic-wrong-argument", ("14 Generic constraints", "14 Trait bounds"), GEN,
      "pickBool instantiates pick Bool", "pickBool instantiates pick String", ("R403",)),
    # ---------------------------------------------------------------- 15 lexical and structural
    M("lex-other-whitespace", ("15 Lexical analysis", "22 Invalid source encoding"), MIN,
      "main at begin return ok zero", "main at begin return ok\u00a0zero", ("R101", "R205", "R501")),
    M("lex-control-character", ("15 Token recognition",), MIN,
      'main purpose "Return exit status 0"', 'main purpose "Return exit\x01 status 0"', ("R102",)),
    M("lex-misplaced-quote", ("15 Token recognition",), MIN,
      "main at begin return ok zero", 'main at begin return ok ze"ro', ("R104", "R205", "R501")),
    M("lex-bad-escape", ("8 String escaping",), MIN,
      'main purpose "Return exit status 0"', 'main purpose "Return exit\\q status 0"', ("R105",)),
    M("lex-unterminated-string", ("15 Token recognition",), MIN,
      'main purpose "Return exit status 0"', 'main purpose "Return exit status 0', ("R106",)),
    M("row-outside-entity", ("15 Syntax parsing", "15 Abstract syntax tree generation"), MIN,
      "minimal exports main\n", "minimal exports main\nstray at begin return ok zero\n", ("R201",)),
    M("unknown-kind", ("15 Syntax parsing",), MIN, "main is operation", "main is function", ("R202", "R401", "R601")),
    M("predicate-not-allowed", ("15 Semantic analysis",), MIN,
      "main memory heap false", "main memory heap false\nmain field x Int64", ("R204",)),
    M("row-shape", ("15 Syntax parsing", "21 Every operation has a valid declaration"), MIN,
      "main async false", "main async maybe", ("R205", "R302")),
    M("reserved-word-name", ("15 Name binding",), MIN,
      "main let zero immutable ExitCode 0\n", "main let zero immutable ExitCode 0\nmain let true immutable Int64 1\n",
      ("R206",)),
    M("wrong-case-name", ("15 Name binding",), MIN,
      "main let zero immutable ExitCode 0\n", "main let zero immutable ExitCode 0\nmain let One immutable Int64 1\n",
      ("R207",)),
    M("skeleton-order", ("15 Syntax parsing",), MIN,
      "main async false\nmain maxRecursion none", "main maxRecursion none\nmain async false", ("R301",)),
    M("missing-skeleton-row", ("21 Every operation has a valid declaration", "1 Variable declaration"), MIN,
      "main raises none\n", "", ("R302",)),
    M("none-beside-rows", ("15 Syntax parsing",), MIN,
      "main effect none\n", "main effect none\nmain effect write console.stdout\n", ("R303", "R407", "R408")),
    M("purpose-missing", ("21 Every operation has a valid declaration",), MIN,
      'main purpose "Return exit status 0"\n', "", ("R304",)),
    # ---------------------------------------------------------------- 20 tests
    M("test-verifies-unknown", ("20 Unit tests", "21 Invariants are validated"), TESTS,
      "tripleTest verifies triple timesThree", "tripleTest verifies triple timesFour", ("R604",),
      file="testsPass.test.sem"),
    M("invariant-unverified", ("21 Invariants are validated", "20 Regression tests"), TESTS,
      "tripleTest verifies triple timesThree\n", "", ("R604",), file="testsPass.test.sem"),
    M("test-invoked", ("20 Integration tests",), TESTS,
      "runTriple invokes triple", "runTriple invokes tripleTest", ("R402",), file="testsPass.test.sem"),
]
