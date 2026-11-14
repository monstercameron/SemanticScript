"""Force UTF-8 on the process stdout/stderr streams.

SemanticScript diagnostics embed non-ASCII text (for example the `§3`
spec-section markers in `missingPurpose` advisories). On Windows the console
streams default to a legacy code page (cp1252), so those characters render as
mojibake. Reconfiguring the streams to UTF-8 at CLI entry keeps diagnostics
legible everywhere without per-message escaping.
"""

from __future__ import annotations

import sys


def force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 when the streams support it.

    No-op on streams that cannot be reconfigured (already-wrapped or redirected
    streams without ``reconfigure``), so it is always safe to call.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            # Stream is detached or otherwise not reconfigurable; leave it as-is.
            continue
