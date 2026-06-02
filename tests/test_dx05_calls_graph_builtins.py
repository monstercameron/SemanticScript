#!/usr/bin/env python3
"""DX-05: `graph --kind calls` includes built-in / cross-module call targets.

The calls-graph dropped any invoke target containing a dot (`"." not in …`), so a
program whose calls are all built-ins (console.*, math.*) produced an empty
`digraph calls {}` — useless — and cross-module user calls were silently missing.
The graph now includes every activated call target: a resolved user op by its
name, a built-in / cross-module target verbatim.
"""
import importlib

ss = importlib.import_module("semanticscript")

_BUILTINS_ONLY = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let g immutable String "hi"\nmain let okc immutable ExitCode 0\n'
    "main do w\nmain return okc\n"
    "w is call\nw in main\nw invokes console.writeLine\nw arg text String g\n"
)


def test_builtin_only_calls_graph_is_not_empty():
    dot = ss.graph(ss.parse(_BUILTINS_ONLY), "calls", "dot")
    assert '"main" -> "console.writeLine";' in dot


def test_user_and_builtin_edges_both_present():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okc immutable ExitCode 0\n'
        "main do callHelper\nmain do w\nmain return okc\n"
        "callHelper is call\ncallHelper in main\ncallHelper invokes helper\ncallHelper out r Int32\n"
        'w is call\nw in main\nw invokes console.writeLine\nw arg text String lit\n'
        'main let lit immutable String "x"\n'
        "helper is operation\nhelper out Int32\nhelper async no\n"
        'helper purpose "p"\nhelper invariant "i"\nhelper let h immutable Int32 0\nhelper return h\n'
    )
    dot = ss.graph(ss.parse(src), "calls", "dot")
    assert '"main" -> "helper";' in dot               # resolved user op by name
    assert '"main" -> "console.writeLine";' in dot     # built-in verbatim
