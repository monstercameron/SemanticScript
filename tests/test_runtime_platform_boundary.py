from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "semanticscript" / "runtime"

FORBIDDEN_OS_HEADERS = re.compile(
    r"#\s*include\s*<("
    r"windows\.h|winsock2\.h|ws2tcpip\.h|"
    r"sys/socket\.h|pthread\.h|mach-o/dyld\.h|"
    r"signal\.h|time\.h|unistd\.h|fcntl\.h|sys/stat\.h|"
    r"termios\.h|sys/ioctl\.h|sys/select\.h|netdb\.h|"
    r"arpa/inet\.h|netinet/in\.h|poll\.h|io\.h|conio\.h|direct\.h"
    r")>"
)


def _allowed_platform_header_owner(path: Path) -> bool:
    rel = path.relative_to(RUNTIME).as_posix()
    return (
        rel.startswith("native_platform/")
        or rel.startswith("native_win32_gui/")
    )


def test_runtime_os_headers_are_confined_to_native_platform_boundary():
    offenders = []
    for path in RUNTIME.rglob("*"):
        if path.suffix not in {".c", ".h"}:
            continue
        if _allowed_platform_header_owner(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if FORBIDDEN_OS_HEADERS.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
