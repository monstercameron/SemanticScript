"""The coverage map: every item of the language testing checklist, with its status and the cases that prove it.

`docs/test-suite.md` is generated from three sources and checked by tests/test_suite.py:

- CHECKLIST: the checklist items, in order (the owner's list).
- the evidence: `# covers:` rows of the program cases, the `covers` of each
  mutation, and GENERATED (the covers of the generated tests in test_suite.py).
- NOTES: a status and a reason for items the evidence alone does not settle
  (absent by design, a known gap, or not applicable), plus extra evidence.

Regenerate after changing cases or notes:

    python tests/suite/coverage_map.py --write
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs", "test-suite.md")

CHECKLIST = [
    (1, 'Variables & Constants', [
        'Variable declaration',
        'Variable initialization',
        'Variable reassignment',
        'Immutable variables',
        'Mutable variables',
        'Constants',
        'Variable shadowing',
        'Variable scope',
        'Global variables',
        'Local variables',
        'Uninitialized variables',
        'Type inference',
        'Type annotations',
        'Variable lifetime',
        'Multiple assignments',
        'Destructuring',
    ]),
    (2, 'Data Types', [
        'Signed integers (8/16/32/64-bit)',
        'Unsigned integers',
        'Floating-point numbers',
        'Boolean',
        'Characters',
        'Strings',
        'Byte arrays',
        'Arrays',
        'Lists',
        'Tuples',
        'Structures / Records',
        'Enumerations',
        'Unions',
        'Maps / Dictionaries',
        'Sets',
        'Optional / Nullable types',
        'Result types',
        'Generic types',
        'User-defined types',
        'Recursive types',
        'Function types',
        'Type aliases',
        'Type conversions',
        'Type compatibility',
    ]),
    (3, 'Operators & Expressions', [
        'Addition',
        'Subtraction',
        'Multiplication',
        'Division',
        'Modulo',
        'Exponentiation',
        'Equality',
        'Inequality',
        'Greater than / Less than',
        'Logical AND / OR / NOT',
        'Bitwise operators',
        'Bit shifting',
        'Unary operators',
        'Operator precedence',
        'Operator associativity',
        'Short-circuit evaluation',
        'Compound assignment',
        'Expression evaluation order',
        'Integer overflow',
        'Integer underflow',
        'Division by zero',
        'Floating-point precision',
        'NaN / Infinity handling',
    ]),
    (4, 'Control Flow', [
        'If / Else',
        'Else-if chains',
        'Nested conditionals',
        'Switch / Match',
        'Pattern matching',
        'While loops',
        'For loops',
        'Do-while loops',
        'Infinite loops',
        'Nested loops',
        'Break',
        'Continue',
        'Early return',
        'Conditional expressions',
        'Labels',
        'Goto / Branching',
        'Unreachable code',
        'Control-flow validation',
        'Loop termination',
    ]),
    (5, 'Functions & Operations', [
        'Function declaration',
        'Function invocation',
        'Function parameters',
        'Return values',
        'Multiple return values',
        'Default arguments',
        'Named arguments',
        'Variadic arguments',
        'Function overloading',
        'Nested functions',
        'Anonymous functions',
        'Lambdas',
        'Closures',
        'Higher-order functions',
        'Function references',
        'Pure functions',
        'Impure functions',
        'Tail calls',
        'Function composition',
        'Parameter passing by value',
        'Parameter passing by reference',
    ]),
    (6, 'Recursion', [
        'Direct recursion',
        'Indirect recursion',
        'Mutual recursion',
        'Tail recursion',
        'Nested recursion',
        'Recursive data structures',
        'Base-case termination',
        'Maximum recursion depth',
        'Stack overflow detection',
        'Recursion with local variables',
        'Recursion with mutable state',
        'Recursion with error propagation',
        'Recursive generic functions',
        'Recursive resource cleanup',
        'Recursive function reentrancy',
    ]),
    (7, 'Memory Management', [
        'Stack allocation',
        'Heap allocation',
        'Dynamic allocation',
        'Deallocation',
        'Ownership',
        'Ownership transfer',
        'Borrowing',
        'Mutable borrowing',
        'Immutable borrowing',
        'Reference counting',
        'Garbage collection (if supported)',
        'Memory lifetime tracking',
        'Memory leak detection',
        'Double-free prevention',
        'Use-after-free prevention',
        'Dangling references',
        'Null pointer handling',
        'Out-of-bounds memory access',
        'Buffer overflow protection',
        'Memory alignment',
        'Memory fragmentation',
        'Circular references',
        'Resource cleanup',
        'Deterministic destruction',
        'Memory exhaustion',
    ]),
    (8, 'Strings & Collections', [
        'String creation',
        'String concatenation',
        'String comparison',
        'String interpolation',
        'String slicing',
        'Unicode support',
        'UTF-8 handling',
        'String escaping',
        'Empty strings',
        'Array initialization',
        'Array indexing',
        'Array bounds checking',
        'Array resizing',
        'Multidimensional arrays',
        'Collection iteration',
        'Collection insertion',
        'Collection removal',
        'Collection sorting',
        'Collection searching',
        'Collection copying',
        'Collection equality',
        'Nested collections',
    ]),
    (9, 'Modules & Namespaces', [
        'Module declaration',
        'Module imports',
        'Module exports',
        'Module aliases',
        'Nested modules',
        'Circular imports',
        'Import resolution',
        'Namespace collisions',
        'Visibility / Access modifiers',
        'Public / Private symbols',
        'Dependency management',
        'Module initialization',
        'Module cleanup',
        'Cross-module function calls',
        'Cross-module type references',
    ]),
    (10, 'Error Handling', [
        'Error creation',
        'Error propagation',
        'Error catching',
        'Error recovery',
        'Multiple error types',
        'Custom error types',
        'Exception handling',
        'Result-based errors',
        'Panic / Fatal errors',
        'Assertion failures',
        'Nested error handling',
        'Error handling during recursion',
        'Cleanup after errors',
        'Error context preservation',
        'Stack traces',
        'Unhandled errors',
        'Errors during resource cleanup',
        'Exit codes',
    ]),
    (11, 'Concurrency & Parallelism', [
        'Thread creation',
        'Thread termination',
        'Async functions',
        'Await',
        'Futures / Promises',
        'Task scheduling',
        'Parallel execution',
        'Shared mutable state',
        'Mutexes',
        'Locks',
        'Atomic operations',
        'Channels',
        'Message passing',
        'Race-condition detection',
        'Deadlock detection',
        'Task cancellation',
        'Timeouts',
        'Thread-local storage',
        'Producer-consumer patterns',
        'Concurrent recursion',
        'Structured concurrency',
    ]),
    (12, 'Input / Output', [
        'Standard output',
        'Standard input',
        'Standard error',
        'File reading',
        'File writing',
        'File appending',
        'Binary file operations',
        'Directory operations',
        'File permissions',
        'File-not-found handling',
        'File locking',
        'Buffered I/O',
        'Stream operations',
        'Stream piping',
        'Network I/O',
        'Socket operations',
        'HTTP requests',
        'Process execution',
        'Environment variables',
        'Command-line arguments',
    ]),
    (13, 'Capabilities & Effect System', [
        'Capability declaration',
        'Capability granting',
        'Capability restriction',
        'Capability propagation',
        'Capability revocation',
        'Capability scoping',
        'Unauthorized capability access',
        'Effect declaration',
        'Effect validation',
        'Effect inference',
        'Pure operation enforcement',
        'Nested operation effects',
        'Cross-module effects',
        'Resource access permissions',
        'File-system capability enforcement',
        'Network capability enforcement',
        'Console capability enforcement',
        'Capability escalation prevention',
        'Effect polymorphism',
    ]),
    (14, 'Type System & Generics', [
        'Static type checking',
        'Type inference',
        'Type mismatch detection',
        'Implicit conversions',
        'Explicit conversions',
        'Generic functions',
        'Generic structures',
        'Generic constraints',
        'Type parameter inference',
        'Nested generics',
        'Recursive generics',
        'Trait / Interface implementation',
        'Trait bounds',
        'Polymorphism',
        'Subtyping',
        'Variance',
        'Exhaustive pattern matching',
        'Type-safe casting',
    ]),
    (15, 'Compiler & Parser', [
        'Lexical analysis',
        'Token recognition',
        'Syntax parsing',
        'Abstract syntax tree generation',
        'Intermediate representation generation',
        'Symbol resolution',
        'Name binding',
        'Semantic analysis',
        'Type checking',
        'Control-flow graph generation',
        'Dataflow analysis',
        'Constant folding',
        'Dead-code elimination',
        'Inlining',
        'Tail-call optimization',
        'Loop optimization',
        'Register allocation',
        'Code generation',
        'Linking',
        'Incremental compilation',
        'Compiler error diagnostics',
        'Source-location tracking',
        'Compiler determinism',
    ]),
    (16, 'Runtime & Execution', [
        'Program startup',
        'Entry-point discovery',
        'Program shutdown',
        'Runtime initialization',
        'Global initialization',
        'Stack management',
        'Heap management',
        'Function call stack',
        'Runtime error handling',
        'Signal handling',
        'Process termination',
        'Exit status reporting',
        'Runtime assertions',
        'Resource limits',
        'Execution time limits',
        'Deterministic execution',
        'Runtime performance',
        'Cross-platform execution',
    ]),
    (17, 'Security & Safety', [
        'Memory safety',
        'Type safety',
        'Bounds checking',
        'Stack overflow protection',
        'Integer overflow protection',
        'Resource exhaustion protection',
        'Sandboxing',
        'Capability isolation',
        'Privilege separation',
        'Input validation',
        'Injection resistance',
        'Unsafe operation restrictions',
        'Module isolation',
        'Secure error handling',
        'Sensitive data handling',
        'Denial-of-service resistance',
    ]),
    (18, 'Interoperability', [
        'Foreign function interface (FFI)',
        'C interoperability',
        'Native library loading',
        'Dynamic linking',
        'Static linking',
        'ABI compatibility',
        'Data structure marshaling',
        'Cross-language error handling',
        'Cross-language memory ownership',
        'Calling conventions',
        'Shared libraries',
        'WASM integration',
        'Native system APIs',
    ]),
    (19, 'Standard Library', [
        'Mathematical functions',
        'Comparison functions',
        'String utilities',
        'Collection utilities',
        'File-system utilities',
        'Date and time',
        'Random number generation',
        'Cryptographic primitives',
        'Serialization',
        'JSON parsing',
        'Regular expressions',
        'Logging',
        'Networking',
        'Process management',
        'Environment utilities',
    ]),
    (20, 'Testing & Debugging Infrastructure', [
        'Unit tests',
        'Integration tests',
        'End-to-end tests',
        'Regression tests',
        'Property-based tests',
        'Fuzz testing',
        'Differential testing',
        'Snapshot tests',
        'Golden-file tests',
        'Compiler self-tests',
        'Negative compilation tests',
        'Runtime failure tests',
        'Performance benchmarks',
        'Memory profiling',
        'CPU profiling',
        'Code coverage',
        'Debugger integration',
        'Breakpoints',
        'Variable inspection',
        'Stack inspection',
        'Execution tracing',
    ]),
    (21, 'Language-Specific Structural Validation', [
        'Every operation has a valid declaration',
        'Every call references an existing operation',
        'Every call belongs to a valid operation',
        'Every label exists',
        'Branch targets exist',
        'Every referenced variable is defined',
        'Variables are initialized before use',
        'Call argument types match parameters',
        'Return types match operation declarations',
        'Required outputs are assigned',
        'Unreachable labels are detected',
        'Duplicate declarations are rejected',
        'Duplicate symbols are rejected',
        'Ownership constraints are enforced',
        'Borrowing constraints are enforced',
        'Cleanup obligations are enforced',
        'Declared effects match actual effects',
        'Required capabilities are present',
        'Unnecessary capabilities are rejected or reported',
        'Recursion limits are enforced',
        'Heap restrictions are enforced',
        'Async restrictions are enforced',
        'Error handling matches declared error types',
        'Invariants are validated',
        'Module dependency cycles are handled',
        'Invalid operation graphs are rejected',
        'Execution order is deterministic where specified',
    ]),
    (22, 'Edge Cases & Stress Testing', [
        'Empty program',
        'Minimal valid program',
        'Large source files',
        'Thousands of variables',
        'Thousands of operations',
        'Deeply nested expressions',
        'Deeply nested control flow',
        'Deep recursion',
        'Very large collections',
        'Zero-length collections',
        'Maximum integer values',
        'Minimum integer values',
        'Floating-point extremes',
        'Extremely long strings',
        'Invalid Unicode',
        'Invalid source encoding',
        'Repeated allocation/deallocation',
        'Memory exhaustion',
        'Infinite loops',
        'Large dependency graphs',
        'Circular dependencies',
        'Concurrent resource contention',
        'Rapid process creation',
        'Interrupted I/O operations',
        'Unexpected program termination',
        'Malformed input',
        'Randomized program generation',
    ]),
    (23, 'Build, Tooling & Ecosystem', [
        'CLI compiler invocation',
        'Interpreter invocation',
        'REPL behavior',
        'Package management',
        'Dependency resolution',
        'Version constraints',
        'Reproducible builds',
        'Incremental builds',
        'Build caching',
        'Cross-compilation',
        'Formatter',
        'Linter',
        'Language Server Protocol (LSP)',
        'IDE integration',
        'Source maps',
        'Documentation generation',
        'Testing framework integration',
        'Standard library versioning',
        'Backward compatibility',
        'Language feature versioning',
    ]),
]

# Covers of the generated tests in tests/test_suite.py (test function name -> checklist items).
GENERATED: dict[str, list[str]] = {
    "test_stress_thousands_of_values": ["22 Thousands of variables", "22 Large source files", "15 Code generation"],
    "test_stress_thousands_of_operations": ["22 Thousands of operations", "16 Function call stack"],
    "test_stress_deeply_nested_control_flow": ["22 Deeply nested control flow", "22 Deeply nested expressions"],
    "test_stress_extremely_long_string": ["22 Extremely long strings"],
    "test_stress_deep_recursion": ["22 Deep recursion", "16 Stack management", "16 Function call stack"],
    "test_stress_stack_exhaustion_traps": ["6 Stack overflow detection", "17 Stack overflow protection",
                                           "16 Stack management", "22 Unexpected program termination"],
    "test_stress_very_large_collection": ["22 Very large collections", "22 Repeated allocation/deallocation",
                                          "16 Heap management"],
    "test_stress_large_dependency_graph": ["22 Large dependency graphs", "9 Dependency management",
                                           "20 Integration tests"],
    "test_fuzz_checker_never_crashes": ["20 Fuzz testing", "22 Malformed input", "22 Randomized program generation",
                                        "15 Compiler error diagnostics", "15 Source-location tracking"],
    "test_differential_integer_arithmetic": ["20 Differential testing", "20 Property-based tests",
                                             "3 Integer overflow", "19 Mathematical functions",
                                             "17 Denial-of-service resistance", "22 Randomized program generation"],
    "test_check_output_is_deterministic": ["15 Compiler determinism", "23 Reproducible builds"],
    "test_emitted_ir_is_deterministic": ["15 Compiler determinism", "15 Intermediate representation generation",
                                         "23 Reproducible builds"],
    "test_run_is_deterministic": ["16 Deterministic execution", "21 Execution order is deterministic where specified"],
    "test_diagnostics_point_at_real_lines": ["15 Source-location tracking", "23 Source maps"],
    "test_a_single_edit_is_reported_on_its_own_line": ["15 Source-location tracking", "15 Compiler error diagnostics"],
    "test_cli_check_json_shape": ["23 CLI compiler invocation", "23 IDE integration"],
    "test_cli_run_refuses_a_library": ["23 CLI compiler invocation", "16 Entry-point discovery"],
    "test_cli_run_refuses_a_module_file_without_project": ["23 CLI compiler invocation"],
    "test_cli_rejects_unknown_command": ["23 CLI compiler invocation"],
    "test_check_reports_unreadable_source_encoding": ["22 Invalid source encoding", "15 Lexical analysis"],
    "test_mutation": ["20 Negative compilation tests"],
    "test_formatter_repository_is_canonical": ["23 Formatter"],
    "test_formatter_undoes_added_spacing": ["23 Formatter"],
    "test_repl_checks_and_runs": ["23 REPL behavior"],
    "test_language_server": ["23 Language Server Protocol (LSP)", "23 IDE integration"],
    "test_build_cache_reuses_only_identical_projects": ["23 Build caching", "23 Incremental builds",
                                                        "15 Incremental compilation"],
    "test_bench_reports_timings": ["20 Performance benchmarks", "16 Runtime performance"],
    "test_trace_coverage_and_profile": ["20 Execution tracing", "20 Code coverage", "20 CPU profiling",
                                        "20 Memory profiling"],
    "test_debugger_breakpoints_values_and_stack": ["20 Debugger integration", "20 Breakpoints",
                                                   "20 Variable inspection", "20 Stack inspection"],
    "test_cross_compiles_to_other_targets": ["23 Cross-compilation", "15 Code generation"],
    "test_webassembly_runs_under_node": ["18 WASM integration"],
    "test_program_sees_an_interrupt": ["16 Signal handling"],
    "test_standalone_executables_match_the_jit": ["18 Static linking", "16 Program startup"],
    "test_symlink_out_of_scope_traps": ["13 Capability escalation prevention", "17 Sandboxing"],
    "test_every_operation_compiles": ["15 Code generation", "15 Intermediate representation generation"],
    "test_every_program_case_runs": ["20 End-to-end tests"],
    "test_program_case": ["20 End-to-end tests", "20 Golden-file tests", "20 Snapshot tests"],
}

BY_DESIGN, GAP, NA = "by design", "gap", "n/a"

# item -> (status or None to derive it from the evidence, note, extra evidence)
NOTES: dict[str, tuple[str | None, str, list[str]]] = {
    # 1
    "1 Variable shadowing": (None, "A name is declared once per operation, across labels, values, and owned "
                             "entities (R411). The same name in two operations is fine: each operation is its own "
                             "scope.", []),
    "1 Global variables": (None, "Modules hold no variables (R204); shared constant data lives in `table` "
                           "entities.", []),
    "1 Type inference": (None, "Every `let` states its type; leaving it out is a shape error.", []),
    "1 Variable lifetime": (None, "A value lives for the operation that declares it; a region-owned value lives "
                            "until its region is released (`released atReturn`).", ["07-memory/region-list"]),
    "1 Multiple assignments": (BY_DESIGN, "One `set` row assigns one name. Two results come back as a record "
                               "(see `Point` in the shapes case).", ["02-types/shapes"]),
    "1 Destructuring": (BY_DESIGN, "Fields are read one at a time with `<Record>.<field>` calls; an enum payload is "
                        "bound by `case ... bind`.", ["02-types/shapes"]),
    # 2
    "2 Boolean": (None, "`Bool` with `true` and `false`; printed by the operators and floats cases.",
                  ["03-operators/operators", "02-types/floats"]),
    "2 Tuples": (BY_DESIGN, "No anonymous tuples: a record names every field.", ["02-types/shapes"]),
    "2 Characters": (None, "There is no character type: text is UTF-8 `String`, read a `Byte` at a time.", []),
    "2 Unions": (None, "Enums with payloads are the tagged unions; untagged unions do not exist.", []),
    # 3
    "3 Short-circuit evaluation": (BY_DESIGN, "There are no nested expressions: each operand is a named value "
                                   "computed by an earlier step, so nothing is skipped implicitly. Conditional "
                                   "work is written as branches (control case).", ["04-control-flow/control"]),
    "3 Operator precedence": (BY_DESIGN, "No infix operators, so no precedence: every operation is a call with "
                              "named slots `left` and `right`.", []),
    "3 Operator associativity": (BY_DESIGN, "No infix operators: grouping is the order of the steps.", []),
    "3 Compound assignment": (BY_DESIGN, "No `+=`: compute with a call, then `set` (and only a mutable let).", []),
    # 4
    "4 Conditional expressions": (BY_DESIGN, "No ternary expression: `branch if` chooses a block.", []),
    # 5
    "5 Default arguments": (BY_DESIGN, "Every slot is passed on every call; leaving one out is R405.", []),
    "5 Variadic arguments": (BY_DESIGN, "A target has a fixed list of slots; pass a list for many values.", []),
    "5 Function overloading": (BY_DESIGN, "One name, one operation (R203). Generic operations cover one body for "
                               "many types.", []),
    "5 Nested functions": (BY_DESIGN, "Entities are flat: an `is` row always starts a new top-level entity, and a "
                           "call belongs to its operation by its `in` row.", []),
    "5 Anonymous functions": (BY_DESIGN, "Every operation is named; references point at named operations.", []),
    "5 Lambdas": (BY_DESIGN, "No lambdas: pass a named operation through an `operationType` value.", []),
    "5 Closures": (BY_DESIGN, "No captured environment: an operation sees only its inputs and lets.", []),
    "5 Tail calls": (None, "Tail recursion runs (fibonacci in the recursion case) but is not guaranteed to reuse "
                     "the frame; `maxRecursion` bounds the depth either way.", ["06-recursion/recursion"]),
    # 6
    # 7
    "7 Reference counting": (BY_DESIGN, "Single owners and regions: a value has one owner (`ownedBy`), and "
                             "region-owned values are freed with their region.", []),
    "7 Garbage collection (if supported)": (BY_DESIGN, "No garbage collector; release points are explicit "
                                            "(regions, cleanups, `give`).", []),
    "7 Memory alignment": (NA, "Handled by the backend's LLVM data layout and the host allocator; not observable in "
                           "the language.", []),
    "7 Memory fragmentation": (BY_DESIGN, "Region values are released all at once with their region, so programs "
                               "do not free individual values.", []),
    "7 Circular references": (None, "A type cannot contain itself by value (R403); single ownership leaves no "
                              "owner cycles; graphs refer to nodes by list index (LR-25 rule 5).", ["recursive-type-by-value"]),
    "7 Stack allocation": (None, "Plain values (integers, records of plain fields) live in the operation's frame; "
                           "`memoryHeap false` promises nothing else is allocated.", ["01-variables/variables"]),
    "7 Null pointer handling": (None, "No null: absence is `option.Option` with `absent`, matched explicitly.", []),
    # 9
    "9 Module initialization": (BY_DESIGN, "Modules run no code when loaded and hold no mutable state; tables are "
                                "constant data.", []),
    "9 Module cleanup": (BY_DESIGN, "Nothing to clean: modules own no resources. Operations clean up what they "
                         "own.", []),
    "9 Module aliases": (BY_DESIGN, "A module is always referred to by its last path segment; there is no `as`.",
                         []),
    # 10
    "10 Panic / Fatal errors": (None, "Run-time rule breaks (overflow, bounds of loops and recursion, region "
                                "capacity) trap: the program stops with exit code 70 and a message naming the "
                                "source line.", ["03-operators/trap-add-overflow", "04-control-flow/trap-loop-bound"]),
    "10 Exception handling": (None, "No exceptions: an operation `raises` one error enum, and every fallible call is "
                              "followed by `branch ifError` (R506).", []),
    # 11
    "11 Deadlock detection": (None, "The checker proves every task and group is joined or cancelled on every path "
                              "(R512). At run time, when every task waits on another with no deadline, the program "
                              "traps and names each wait (D-31).", []),
    "11 Thread-local storage": (BY_DESIGN, "No globals, so nothing to make thread-local: a task receives what it "
                                "needs as arguments.", []),
    "11 Concurrent recursion": (None, "Recursion runs inside tasks with its depth and stack checked per thread.",
                                ["11-concurrency/parallel"]),
    "11 Parallel execution": (None, "Each task runs on its own thread (D-31); the parallel case measures two pauses "
                              "overlapping and a group of two running four tasks in two waves.", []),
    "11 Mutexes": (BY_DESIGN, "No shared mutable state between tasks: values are copied, lent read-only, or given. "
                   "Coordination is by channels.", []),
    "11 Locks": (BY_DESIGN, "See mutexes: no shared mutable state, so no locks.", []),
    "11 Atomic operations": (BY_DESIGN, "See mutexes: no shared mutable state, so no atomics.", []),
    # 12
    "12 HTTP requests": ("tested", "The worked server example runs and answers real HTTP requests "
                         "(`test_server_example_answers_http` in tests/test_refined.py). There is no HTTP client.",
                         []),
    "12 File appending": (None, "`fs.openAppend` writes at the end of a file, creating it if missing.", []),
    "12 Directory operations": (None, "`fs.createDirectory`, `listDirectory`, `entryCount`, `entryName`, "
                                "`removeDirectory`.", []),
    "12 File permissions": (None, "Access is governed by capabilities with a path-prefix scope; the case proves a "
                            "path outside the scope is rejected. File-mode bits are not modelled.", []),
    # 15
    "15 Type checking": (None, "", ["operator-type-mismatch", "var-annotation-mismatch", "no-implicit-widening"]),
    "15 Control-flow graph generation": (None, "", ["unreachable-block", "cycle-without-header", "jump-into-loop"]),
    "15 Dataflow analysis": (None, "", ["var-uninitialized-path", "double-give", "owned-never-released"]),
    "15 Constant folding": (NA, "An optimisation inside LLVM; the language makes no promise about it.", []),
    "15 Dead-code elimination": (NA, "An optimisation inside LLVM. Unreachable blocks are a check error (R511), so "
                                 "source has no dead blocks.", ["unreachable-block"]),
    "15 Inlining": (NA, "An optimisation inside LLVM; the language makes no promise about it.", []),
    "15 Tail-call optimization": (NA, "Not promised; recursion depth is bounded by `maxRecursion` instead.", []),
    "15 Loop optimization": (NA, "An optimisation inside LLVM; loop bounds are still enforced.", []),
    "15 Register allocation": (NA, "Done by LLVM.", []),
    "15 Linking": (BY_DESIGN, "`run` and `test` JIT-compile in process; there is no separate link step or "
                   "executable yet.", []),
    "15 Abstract syntax tree generation": (None, "The model is rows grouped into entities; malformed rows are "
                                           "reported and dropped before later passes.", []),
    # 16
    "16 Cross-platform execution": (None, "CI runs this suite on Windows and Linux.", ["test_program_case"]),
    "16 Execution time limits": (None, "Every loop states `maxIterations` (or `unbounded` on a `forever` loop with "
                                 "a reason) and traps past it; there is no wall-clock limit.", []),
    # 17
    "17 Unsafe operation restrictions": (BY_DESIGN, "There are no unsafe operations: no pointers, casts, or "
                                         "unchecked arithmetic outside the `wrapping` targets.", []),
    "17 Denial-of-service resistance": (None, "Loops, recursion, and regions have stated bounds that trap; "
                                        "`powerInt64` takes at most 63 steps whatever the exponent.",
                                        ["04-control-flow/trap-loop-bound", "07-memory/trap-region-exhausted"]),
    # 18
    "18 Native system APIs": (None, "Reached only through the standard library (`fs`, `net`, `process`, "
                              "`environment`, `clock`) under capabilities.", ["12-io/file-read", "12-io/process-run"]),
    # 19
    "19 Comparison functions": (None, "", ["03-operators/operators"]),
    "19 Regular expressions": (BY_DESIGN, "No regex engine; `string.find`, `startsWith`, and byte classes cover "
                               "matching, written out explicitly.", []),
    "19 Mathematical functions": (None, "", ["03-operators/operators"]),
    # 20
    "20 Compiler self-tests": ("tested", "tests/test_refined.py tests the checker on the worked examples, including a "
                               "lexer written in SemanticScript (docs/refined-examples/selfhost).", []),
    "20 Runtime failure tests": (None, "", ["03-operators/trap-divide-by-zero", "06-recursion/trap-recursion-depth",
                                            "20-testing/tests-fail"]),
    # 22
    "22 Zero-length collections": (None, "Empty strings and a cleared list.", ["08-strings-collections/strings",
                                                                           "07-memory/region-list"]),
    "22 Concurrent resource contention": (None, "A task group's `limit` bounds how many tasks run at once; "
                                          "`awaitSlot` waits for room, and starting into a full group traps (A12).",
                                          []),
    "22 Unexpected program termination": (None, "A trap flushes what was written to stdout, writes the message to "
                                          "stderr, and exits with code 70.", ["03-operators/trap-shift-too-far"]),
    "22 Empty program": (None, "An empty module file is rejected: a module file declares one module entity.", []),
    # 23
    "23 Interpreter invocation": (BY_DESIGN, "There is no interpreter: `run` JIT-compiles the project.", []),
    "23 Linter": (BY_DESIGN, "The checker is the linter: every rule it enforces is an error, not a warning.", []),
    "23 Documentation generation": ("tested", "The grammar reference and the editor grammar are generated from the "
                                    "shape table; CI fails when they are stale.", []),
    "23 Backward compatibility": (BY_DESIGN, "Not promised: the owner chose no compatibility layer while the "
                                  "language settles (language-refinement.md, Part 5).", []),
    "6 Recursive resource cleanup": (None, "Each level of a recursion opens a file and releases it with a deferred cleanup.", []),
    "10 Stack traces": (None, "A trap prints the operations it passed through, innermost first, with repeated frames "
                        "collapsed into a count.", []),
    "12 File locking": (None, "`fs.lock` takes an exclusive advisory lock on an open file; `fs.unlock` releases it.", []),
    "12 Stream piping": (None, "`process.runCaptured` pipes bytes into a program and collects its standard output and "
                          "error.", []),
    "15 Incremental compilation": (None, "An unchanged project is neither checked nor compiled again (the build cache); a "
                                  "change rechecks the whole project, since checks span modules.", []),
    "16 Signal handling": (None, "`signal.interrupted` and `signal.waitForInterrupt`: the first interrupt goes to the "
                          "program, a second ends it. The delivery test runs on POSIX systems.", ["19-stdlib/signal"]),
    "16 Runtime performance": (None, "`refined bench` times repeated runs; the stress tests bound sizes.", []),
    "17 Sensitive data handling": (None, "`secret.Secret` has no conversion to text except `reveal`, which needs a capability "
                                  "for `read secret.values`; `matches` compares in constant time.", []),
    "18 Static linking": (None, "`refined build --kind executable` links the program and a C runtime into a "
                         "standalone executable; programs that call the host library trap there with "
                         "the target's name.", []),
    "18 WASM integration": (None, "`refined build --kind wasm` emits WebAssembly; tests/suite/wasm_host.mjs runs it in Node.", []),
    "19 Random number generation": (None, "`random.int64Between` from the operating system, and seeded generators.", []),
    "19 Cryptographic primitives": (None, "`crypto.sha256`, `hmacSha256`, `toHex`, and `constantTimeEquals`.", []),
    "19 Serialization": (None, "`json` builds values and writes them with `stringify`.", []),
    "19 JSON parsing": (None, "`json.parse` with typed access to fields and items, and error positions.", []),
    "19 Logging": (None, "`log.debug`, `info`, `warn`, and `error` write levelled lines to standard error.", []),
    "20 Performance benchmarks": (None, "`refined bench PATH --runs N`.", []),
    "20 Memory profiling": (None, "`refined run --profile` reports each region's peak use against its capacity.", []),
    "20 CPU profiling": (None, "`refined run --profile` reports calls and time per operation.", []),
    "20 Code coverage": (None, "`refined run --coverage` reports which blocks ran and lists the ones that never did.", []),
    "23 REPL behavior": (None, "`refined repl`: type rows, then `:check`, `:run`, `:undo`, `:show`.", []),
    "23 Package management": (None, "Local packages: `requires <name> \"<path>\" \"<constraint>\"` in build.sem; there is no "
                             "registry.", []),
    "23 Version constraints": (None, "Comparators such as `>=1.0.0 <2.0.0`, `^1.2.0`, `=1.2.3`, or `*`.", []),
    "23 Incremental builds": (None, "The build cache skips checking and code generation for an unchanged project.", []),
    "23 Build caching": (None, "`.refined-cache` entries keyed by the compiler, every source, and the options.", []),
    "23 Cross-compilation": (None, "`refined build --target <triple>` for any LLVM target.", []),
    "23 Formatter": (None, "`refined fmt [--check]`: one layout; comments kept exactly.", []),
    "23 Language Server Protocol (LSP)": (None, "`refined lsp`: diagnostics for unsaved text, hover, and formatting.", []),
    "23 Standard library versioning": (None, "build.sem states `standardLibrary 1`; a different version is refused.", []),
    "23 Language feature versioning": (None, "build.sem states `language refined 1`; anything else is refused.", []),
    "20 Debugger integration": (None, "`refined run --debug --break M.OP[:LABEL]`: stops, prints values and the call stack, steps; "
                   "`--trace` prints every block entered.", []),
    "20 Breakpoints": (None, "`refined run --debug --break M.OP[:LABEL]`: stops, prints values and the call stack, steps; "
                   "`--trace` prints every block entered.", []),
    "20 Variable inspection": (None, "`refined run --debug --break M.OP[:LABEL]`: stops, prints values and the call stack, steps; "
                   "`--trace` prints every block entered.", []),
    "20 Stack inspection": (None, "`refined run --debug --break M.OP[:LABEL]`: stops, prints values and the call stack, steps; "
                   "`--trace` prints every block entered.", []),
    "20 Execution tracing": (None, "`refined run --debug --break M.OP[:LABEL]`: stops, prints values and the call stack, steps; "
                   "`--trace` prints every block entered.", []),
    "18 Foreign function interface (FFI)": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 C interoperability": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Native library loading": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Dynamic linking": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 ABI compatibility": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Data structure marshaling": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Cross-language error handling": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Cross-language memory ownership": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Calling conventions": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
    "18 Shared libraries": (None, "`ffi.open` loads a shared library under a capability scoped to its name; "
                   "`ffi.Function.bind` gives a C symbol a declared operation type over numbers and `Bool`, "
                   "called with the C calling convention. No pointers cross, so no memory is shared; a "
                   "missing library or symbol is an error value.", []),
}

STATUS_ORDER = ["tested", "rejected", "static", BY_DESIGN, GAP, NA]
LEGEND = {
    "tested": "a program runs (or traps, or its tests run) and its output is checked",
    "rejected": "the language forbids it, and a negative case proves the checker reports it",
    "static": "the checker accepts and checks it, but the backend refuses to run it yet (R901); the case "
              "asserts that refusal, so it fails as soon as the backend learns the feature",
    BY_DESIGN: "absent on purpose; the note says what to write instead",
    GAP: "wanted, not there yet; the note says what is missing",
    NA: "does not apply to this language",
}


def _items() -> list[tuple[int, str, list[str]]]:
    return CHECKLIST


def _evidence(cases, mutations) -> dict[str, list[tuple[str, str]]]:
    """item -> [(kind, id)], kind one of run, check, reject, static, mutation, generated."""
    out: dict[str, list[tuple[str, str]]] = {}
    for c in cases:
        kind = {"run": "run", "trap": "run", "test": "run", "unsupported": "static"}.get(c.mode, "check")
        if c.mode == "check" and c.detail != "ok":
            kind = "reject"
        if c.mode == "test" and c.detail.startswith("fail"):
            kind = "run"
        for item in c.covers:
            out.setdefault(item, []).append((kind, c.name))
    for m in mutations:
        for item in m.covers:
            out.setdefault(item, []).append(("mutation", m.id))
    for test, items in GENERATED.items():
        for item in items:
            out.setdefault(item, []).append(("generated", test))
    return out


def _derive(found: list[tuple[str, str]]) -> str | None:
    kinds = {k for k, _ in found}
    if kinds & {"run", "generated"}:
        return "tested"
    if kinds & {"mutation", "reject"}:
        return "rejected"
    if "static" in kinds or "check" in kinds:
        return "static"
    return None


def _kind_of(ref: str, cases, mutations) -> str:
    if ref in {c.name for c in cases}:
        case = next(c for c in cases if c.name == ref)
        return {"run": "run", "trap": "run", "test": "run", "unsupported": "static"}.get(case.mode, "reject")
    if ref in {m.id for m in mutations}:
        return "mutation"
    if ref in GENERATED:
        return "generated"
    raise KeyError(ref)


def table(cases, mutations) -> list[tuple[int, str, list[tuple[str, str, list[tuple[str, str]], str]]]]:
    ev = _evidence(cases, mutations)
    rows = []
    for n, title, items in _items():
        section = []
        for item in items:
            key = f"{n} {item}"
            found = list(ev.get(key, []))
            status, note, extra = NOTES.get(key, (None, "", []))
            for ref in extra:
                found.append((_kind_of(ref, cases, mutations), ref))
            status = status or _derive(found) or "MISSING"
            section.append((item, status, found, note))
        rows.append((n, title, section))
    return rows


def problems(cases, mutations) -> list[str]:
    out = []
    known = {f"{n} {i}" for n, _t, items in _items() for i in items}
    for c in cases:
        out += [f"case {c.name} covers unknown item `{i}`" for i in c.covers if i not in known]
    for m in mutations:
        out += [f"mutation {m.id} covers unknown item `{i}`" for i in m.covers if i not in known]
    for t, items in GENERATED.items():
        out += [f"generated test {t} covers unknown item `{i}`" for i in items if i not in known]
    out += [f"note for unknown item `{k}`" for k in NOTES if k not in known]
    for k, (_s, _n, extra) in NOTES.items():
        for ref in extra:
            try:
                _kind_of(ref, cases, mutations)
            except KeyError:
                out.append(f"note for `{k}` names unknown evidence `{ref}`")
    for n, _title, section in table(cases, mutations):
        for item, status, found, note in section:
            if status == "MISSING":
                out.append(f"`{n} {item}` has no evidence and no note")
            elif status in (BY_DESIGN, GAP, NA) and not note:
                out.append(f"`{n} {item}` is `{status}` without a reason")
    return out


def _ref(kind: str, ref: str) -> str:
    if kind in ("run", "check", "reject", "static"):
        is_dir = os.path.isdir(os.path.join(HERE, "programs", *ref.split("/")))
        return f"[{ref.split('/')[-1]}](../tests/suite/programs/{ref}{'' if is_dir else '.sem'})"
    return f"`{ref}`"


def render(cases, mutations) -> str:
    rows = table(cases, mutations)
    counts: dict[str, int] = {s: 0 for s in STATUS_ORDER}
    for _n, _t, section in rows:
        for _item, status, _f, _note in section:
            counts[status] = counts.get(status, 0) + 1
    total = sum(counts.values())
    out = ["# Language test suite: coverage map", "",
           "Generated by `python tests/suite/coverage_map.py --write` from the checklist, the program cases in",
           "`tests/suite/programs`, the negative mutations in `tests/suite/mutations.py`, and the generated tests",
           "in `tests/test_suite.py`. Do not edit by hand: `tests/test_suite.py` fails when this file is stale or",
           "when an item has neither evidence nor a reason.", "",
           "Run the suite with `python -m pytest tests/test_suite.py`. How cases are written: "
           "[tests/suite/README.md](../tests/suite/README.md).", "",
           "## Status", "", "| Status | Meaning | Items |", "| --- | --- | --- |"]
    for s in STATUS_ORDER:
        out.append(f"| **{s}** | {LEGEND[s]} | {counts.get(s, 0)} |")
    out += [f"| | total | {total} |", ""]
    out += ["Evidence: a program case links to its file; a `mutation` id names an entry in "
            "`tests/suite/mutations.py`; a `test_...` name is a generated test in `tests/test_suite.py`.", ""]
    gaps = [(n, item, note) for n, _t, section in rows for item, status, _f, note in section if status == GAP]
    statics = [(n, item, note) for n, _t, section in rows for item, status, _f, note in section if status == "static"]
    for n, title, section in rows:
        out += [f"## {n}. {title}", "", "| Item | Status | Evidence | Note |", "| --- | --- | --- | --- |"]
        for item, status, found, note in section:
            seen, refs = set(), []
            for kind, ref in found:
                if ref not in seen:
                    seen.add(ref)
                    refs.append(_ref(kind, ref))
            out.append(f"| {item} | {status} | {', '.join(refs) or ' '} | {note or ' '} |")
        out.append("")
    out += ["## Open work", "", "Every `gap` and `static` item, in checklist order: the list to fill next.", ""]
    for n, item, note in statics + gaps:
        out.append(f"- **{n} {item}** ({'static' if (n, item, note) in statics else 'gap'}): {note}")
    out.append("")
    return "\n".join(out)


def main() -> int:
    sys.path.insert(0, HERE)
    import caselib
    from mutations import MUTATIONS
    text = render(caselib.discover(), MUTATIONS)
    issues = problems(caselib.discover(), MUTATIONS)
    if "--write" in sys.argv:
        with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    for p in issues:
        sys.stderr.write(p + "\n")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
