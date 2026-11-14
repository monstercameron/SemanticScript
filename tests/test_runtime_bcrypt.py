import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _runtime_library(name: str) -> dict:
    manifest = json.loads((ROOT / "semanticscript" / "runtime" / "manifest.json").read_text(encoding="utf-8"))
    for library in manifest["libraries"]:
        if library.get("name") == name:
            return library
    raise AssertionError(f"runtime library {name!r} not found")


def test_bcrypt_contract_is_runtime_backed_not_deferred():
    semsig = (ROOT / "semanticscript" / "sigs" / "standard.bcrypt.semsig").read_text(encoding="utf-8")
    lowered = semsig.lower()
    assert "deferred runtime" not in lowered
    assert "not lowered" not in lowered
    assert "native bindings" in semsig
    assert "platform CSPRNG" in semsig

    library = _runtime_library("ss_bcrypt")
    assert library["provides"] == ["ss_bcrypt_", "ss_random_", "ss_base64url_"]
    assert "native_bcrypt/sem_bcrypt_runtime.c" in library["sources"]
    assert "native_platform/ss_platform_entropy.c" in library["sources"]
    assert "../../third_party/bcrypt/crypt_blowfish.c" in library["sources"]
    assert "../../third_party/bcrypt/crypt_gensalt.c" in library["sources"]
    assert "bcrypt" in library["platforms"]["windows"]["libs"]


def test_bcrypt_runtime_keeps_cost_entropy_and_constant_time_guards():
    source = (ROOT / "semanticscript" / "runtime" / "native_bcrypt" / "sem_bcrypt_runtime.c").read_text(
        encoding="utf-8"
    )
    header = (ROOT / "semanticscript" / "runtime" / "native_bcrypt" / "sem_bcrypt_runtime.h").read_text(
        encoding="utf-8"
    )

    assert "#define SS_BCRYPT_MIN_COST 4" in header
    assert "#define SS_BCRYPT_MAX_COST 31" in header
    assert "#define SS_BCRYPT_HASH_OUTPUT_SIZE 61" in header
    assert "byte_count > SS_RANDOM_MAX_BYTES" in source
    assert "ss_platform_random_bytes(out_buffer, (size_t)byte_count)" in source
    assert "static int constant_time_equals" in source
    assert "accumulator |= (unsigned char)(a[i] ^ b[i]);" in source
    assert "ss_bcrypt_hash_owned" in source
    assert "ss_bcrypt_session_token_owned" in source
