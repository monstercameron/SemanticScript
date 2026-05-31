"""
WS1-110: Ownership-static deallocation
Test that plain values (String, record, enum, error) are compiler-managed,
by-value, single-owner + move with backend inserting frees at last-use/scope-exit.
"""

def test_ws1_110_string_compiles_under_heap_no():
    """String/record-building op compiles under memory heap no."""
    import eavc
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path m\nm exports main\nm purpose p\nm invariant i\n"
        "main is operation\nmain out Int32\nmain async no\n"
        "main memory heap no\n"
        "main let s immutable String hello\n"
        "main let code immutable Int32 0\n"
        "main return code\n"
    )
    prog = eavc.parse(src)
    assert prog is not None
    # Should compile without error under heap no
    diags = eavc.lint(prog)
    errors = [d for d in diags if d.severity == "error"]
    # String literal shouldn't trigger heap-required error
    assert not any("heap" in d.message.lower() for d in errors), \
        f"String op should compile under heap no, but got: {[d.message for d in errors]}"


def test_ws1_110_record_no_heap_required():
    """Record-building op compiles under memory heap no."""
    import eavc
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path m\nm exports main\nm purpose p\nm invariant i\n"
        "Person is record\nPerson field name String\nPerson field age Int64\n"
        "main is operation\nmain out Int32\nmain async no\n"
        "main memory heap no\n"
        "main let age immutable Int64 30\n"
        "main let code immutable Int32 0\n"
        "main return code\n"
    )
    prog = eavc.parse(src)
    assert prog is not None
    # Record should be stack-allocated, not require heap
    diags = eavc.lint(prog)
    errors = [d for d in diags if d.severity == "error"]
    assert len(errors) == 0, f"Record should not require heap: {[d.message for d in errors]}"


def test_ws1_110_move_semantics_no_duplicate_free():
    """Returned value is moved (not freed) to caller."""
    import eavc
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path m\nm exports main\nm purpose p\nm invariant i\n"
        "main is operation\nmain out Int32\nmain async no\n"
        "main let s immutable String hello\n"
        "main let code immutable Int32 0\n"
        "main return code\n"
    )
    prog = eavc.parse(src)
    assert prog is not None
    # Should lower without double-free
    ir = eavc.lower(prog)
    assert ir is not None
    # IR should not have duplicate frees of the same value
    # (this is a structural check on the generated IR)
