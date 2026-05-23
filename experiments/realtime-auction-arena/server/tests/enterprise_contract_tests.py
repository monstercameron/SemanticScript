from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / "experiments" / "realtime-auction-arena" / "server"


def read(relative):
    return (SERVER / relative).read_text(encoding="utf-8")


def assert_contains(text, needle, label):
    assert needle in text, f"missing {label}: {needle}"


def test_build_config_contract():
    build = read("build.sem")
    for needle in [
        "record BuildServerConfig",
        "field BuildPlan serverConfig BuildServerConfig",
        "AUCTION_ARENA_HOST",
        "AUCTION_ARENA_PORT",
        "AUCTION_ARENA_DB",
        "AUCTION_ARENA_JWT_SECRET",
        "AUCTION_ARENA_RATE_LIMIT_MODE",
        "record BuildGracefulShutdown",
        "graceMillis",
    ]:
        assert_contains(build, needle, "build config contract")


def test_api_contract_enterprise_sections():
    api = read("docs/api-contract.md")
    for needle in [
        "## Admin Audit Query Filter Contract",
        "`actorUserId`",
        "`fromUtcMillis`",
        "`toUtcMillis`",
        "## Pagination Contract",
        "data.page",
        "## Server Config And Shutdown Contract",
        "method_not_allowed",
    ]:
        assert_contains(api, needle, "API hardening contract")


def test_runtime_gap_shutdown_plan():
    gaps = read("docs/runtime-gaps.md")
    for needle in [
        "## Graceful Shutdown Plan",
        "Stop accepting new HTTP requests",
        "checkpoint/close SQLite",
        "process-signal accept-loop shutdown is executable",
    ]:
        assert_contains(gaps, needle, "shutdown plan")


def test_worker6_scripts_exist():
    for relative in ["scripts/load_smoke.py", "scripts/full_demo.py"]:
        path = SERVER / relative
        assert path.exists(), f"missing script: {relative}"
        text = path.read_text(encoding="utf-8")
        assert "argparse" in text
        assert "realtime_auction_arena_server.exe" in text


def main():
    test_build_config_contract()
    test_api_contract_enterprise_sections()
    test_runtime_gap_shutdown_plan()
    test_worker6_scripts_exist()
    print("Enterprise hardening contract tests passed")


if __name__ == "__main__":
    main()
