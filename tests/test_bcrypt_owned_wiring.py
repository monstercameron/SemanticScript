#!/usr/bin/env python3
"""R-202 (step 1): the owned-output bcrypt ops are wired to the SS surface.

The owned-output helpers (ss_bcrypt_hash_owned / ss_bcrypt_session_token_owned /
ss_bcrypt_free_string) allocate their own exact-sized output, so there is no
caller buffer/capacity to mis-size — overflow is structurally impossible. This
asserts they lower to the right native symbols and that a `catch` on the
allocating ops wires the 0 failure sentinel (so a hash/entropy failure takes the
error path). This is the enablement step; migrating taskforge-web's auth flow off
the caller-counted buffer ops onto these is the closure step.
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _ir(src):
    return str(semanticscript.lower_to_llvm(semanticscript.parse(src)))


_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "HashError is error\n"
    "bcryptHashCompute is capability\nbcryptHashCompute grants compute bcryptHash\n"
    'bcryptHashCompute purpose "run bcrypt"\n'
)


def test_hash_password_owned_wires_symbol_and_catch():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main effect compute bcryptHash\nmain uses bcryptHashCompute\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main let pw immutable String "secret-pw"\n'
        "main let cost immutable Int32 12\n"
        "main let okCode immutable ExitCode 0\nmain let failCode immutable ExitCode 7\n"
        "main do hashIt\nmain branch ifError hashIt goto failed\n"
        "main do freeIt\nmain return okCode\n"
        "main at failed return failCode\n"
        "hashIt is call\nhashIt in main\nhashIt invokes bcrypt.hashPasswordOwned\n"
        "hashIt arg plaintext String pw\nhashIt arg cost Int32 cost\n"
        "hashIt out hashHandle OpaquePointer\nhashIt catch hashErr HashError\n"
        "freeIt is call\nfreeIt in main\nfreeIt invokes bcrypt.freeString\n"
        "freeIt arg handle OpaquePointer hashHandle\nfreeIt discards \"freed\"\n"
    )
    ir = _ir(src)
    assert "ss_bcrypt_hash_owned" in ir
    assert "ss_bcrypt_free_string" in ir
    assert "icmp eq i64" in ir            # the 0 failure sentinel feeds the catch
    assert "br i1 false" not in ir        # not constant-false


def test_session_token_owned_lowers():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main effect compute bcryptHash\nmain uses bcryptHashCompute\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\nmain let failCode immutable ExitCode 7\n"
        "main do mintIt\nmain branch ifError mintIt goto failed\n"
        "main do freeIt\nmain return okCode\n"
        "main at failed return failCode\n"
        "mintIt is call\nmintIt in main\nmintIt invokes bcrypt.sessionTokenOwned\n"
        "mintIt out tokenHandle OpaquePointer\nmintIt catch tokErr HashError\n"
        "freeIt is call\nfreeIt in main\nfreeIt invokes bcrypt.freeString\n"
        "freeIt arg handle OpaquePointer tokenHandle\nfreeIt discards \"freed\"\n"
    )
    ir = _ir(src)
    assert "ss_bcrypt_session_token_owned" in ir
