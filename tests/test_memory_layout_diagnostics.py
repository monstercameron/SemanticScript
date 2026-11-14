#!/usr/bin/env python3
"""R-243: the _lint_memory_layout family (SS0820-SS0829, incl. T1 safety checks)
gets real negative coverage instead of `assert True` placeholders.

Each test builds a minimal program that triggers exactly one memory-layout
diagnostic and asserts its code is emitted by lint().
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


_OP_HEAD = (
    "ExitCode is alias\nExitCode for Int32\n"
    "demo is operation\ndemo out ExitCode\ndemo async no\n"
    'demo purpose "p"\ndemo invariant "i"\n'
)


def test_ss0820_literal_source_without_digest():
    src = (
        "banner is storage\nbanner scope module\nbanner type String\n"
        "banner mutability immutable\nbanner literalSource \"a/b.txt\"\n"
        "banner literalEncoding utf8\nbanner purpose \"p\"\n")
    assert "SS0820" in _codes(src)


def test_ss0825_literal_source_without_encoding():
    src = (
        "banner is storage\nbanner scope module\nbanner type String\n"
        "banner mutability immutable\nbanner literalSource \"a/b.txt\"\n"
        "banner literalDigest sha256 deadbeef\nbanner purpose \"p\"\n")
    assert "SS0825" in _codes(src)


def test_ss0822_record_align_not_power_of_two():
    src = "Rec is record\nRec field x Int32\nRec align 3\n"
    assert "SS0822" in _codes(src)


def test_ss0823_array_alias_zero_length():
    src = "Arr is alias\nArr for Int32\nArr arrayLength 0\n"
    assert "SS0823" in _codes(src)


def test_ss0824_inline_capacity_overrun():
    # Int64 needs 8 bytes but inlineCapacity is 4; allocator present (so not SS0828).
    src = ("Inl is alias\nInl for Int64\nInl memory inline\n"
           "Inl inlineCapacity 4\nInl allocator c.heap\n")
    assert "SS0824" in _codes(src)


def test_ss0828_inline_capacity_without_spill_allocator():
    # Int8 fits in 4 (so not SS0824); no allocator row -> SS0828.
    src = "Inl is alias\nInl for Int8\nInl memory inline\nInl inlineCapacity 4\n"
    assert "SS0828" in _codes(src)


def test_ss0821_heap_alloc_under_memory_heap_no():
    src = _OP_HEAD + (
        "demo memory heap no\n"
        "demo let okCode immutable ExitCode 0\ndemo let sz immutable Int64 16\n"
        "demo do allocCall\ndemo return okCode\n"
        "allocCall is call\nallocCall in demo\nallocCall invokes c.malloc\n"
        "allocCall arg size Int64 sz\nallocCall out ptr OpaquePointer\n")
    assert "SS0821" in _codes(src)


def test_ss0826_large_local_string_literal():
    big = "x" * 300  # > _LARGE_LITERAL_BYTES (256)
    src = _OP_HEAD + (
        "demo let okCode immutable ExitCode 0\n"
        'demo let blob immutable String "%s"\n'
        "demo return okCode\n" % big)
    assert "SS0826" in _codes(src)


def test_ss0827_magic_printable_ascii_byte():
    src = _OP_HEAD + (
        "demo let okCode immutable ExitCode 0\n"
        "demo let ch immutable Byte 65\n"  # 'A'
        "demo return okCode\n")
    assert "SS0827" in _codes(src)


def test_ss0829_stack_budget_overrun():
    # memory stack 4, but two Int64 locals (+ ExitCode) need far more.
    src = _OP_HEAD + (
        "demo memory stack 4\n"
        "demo let okCode immutable ExitCode 0\n"
        "demo let a immutable Int64 1\ndemo let b immutable Int64 2\n"
        "demo return okCode\n")
    assert "SS0829" in _codes(src)
