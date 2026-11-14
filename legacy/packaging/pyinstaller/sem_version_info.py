"""Generate the Windows VERSIONINFO resource for the frozen sem.exe."""

from __future__ import annotations

import json
from pathlib import Path


MCP_COMMAND = "sem.exe mcp"
MCP_TRANSPORT = "stdio"
MCP_CLIENT_CONFIG = '{"command":"sem.exe","args":["mcp"],"cwd":"<project-root>"}'
MCP_COMMENTS = (
    'MCP stdio server: run sem.exe mcp. '
    'MCP client config: command sem.exe; args ["mcp"]; cwd project root. '
    'Load project docs: agent_docs path dot. '
    'Then load versioned skills: skills_get names sem-start sem sem-agent sem-syntax. '
    'Then call help path . and docs_search for API/capability/type/syntax/runtime discovery.'
)


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if not 1 <= len(parts) <= 4:
        raise ValueError(f"version must have 1 to 4 numeric parts: {version!r}")

    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"version part is not numeric: {version!r}")
        numbers.append(int(part))

    padded = [*numbers, *([0] * (4 - len(numbers)))]
    return (padded[0], padded[1], padded[2], padded[3])


def _resource_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("'", "\\'")


def _string_struct(key: str, value: str) -> str:
    return f"      StringStruct('{_resource_string(key)}', '{_resource_string(value)}'),"


def render_version_info(version: str) -> str:
    file_version = _version_tuple(version)
    string_entries = [
        ("CompanyName", "Earl Cameron"),
        ("FileDescription", "SemanticScript CLI and MCP server"),
        ("FileVersion", version),
        ("InternalName", "sem"),
        ("OriginalFilename", "sem.exe"),
        ("ProductName", "SemanticScript"),
        ("ProductVersion", version),
        ("LegalCopyright", "MIT License"),
        ("Comments", MCP_COMMENTS),
        ("McpServerCommand", MCP_COMMAND),
        ("McpServerTransport", MCP_TRANSPORT),
        ("McpClientConfig", MCP_CLIENT_CONFIG),
    ]
    rendered_entries = "\n".join(_string_struct(key, value) for key, value in string_entries)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
{rendered_entries}
        ],
      ),
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def write_sem_version_info(repo_root: Path, output_path: Path) -> Path:
    version_payload = json.loads((repo_root / "version.json").read_text(encoding="utf-8"))
    version_text = version_payload["version"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_version_info(version_text), encoding="utf-8")
    return output_path
