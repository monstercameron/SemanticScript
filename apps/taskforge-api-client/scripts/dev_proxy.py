from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

STATIC_CONTENT_TYPES = {
    ".css": "text/css",
    ".html": "text/html",
    ".ico": "image/x-icon",
    ".js": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}

STATIC_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]+$")
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


@dataclass(frozen=True)
class ApiOrigin:
    scheme: str
    host: str
    port: int
    base_path: str
    display_url: str


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def _is_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validated_api_origin(value: str) -> ApiOrigin:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("--api-origin must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("--api-origin must be an origin URL without credentials, query, or fragment")
    if not _is_loopback_host(parsed.hostname):
        raise ValueError("--api-origin must point at localhost or a loopback IP address")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("--api-origin port is invalid") from exc
    if not 1 <= port <= 65535:
        raise ValueError("--api-origin port is out of range")

    raw_base_path = parsed.path or "/"
    if any(char in raw_base_path for char in "\\\r\n\0"):
        raise ValueError("--api-origin path contains invalid characters")
    raw_base_segments = [segment for segment in raw_base_path.split("/") if segment]
    if any(segment in {".", ".."} for segment in raw_base_segments):
        raise ValueError("--api-origin path must not contain relative segments")
    normalized_base_path = posixpath.normpath(raw_base_path)
    if normalized_base_path in {".", "/"}:
        normalized_base_path = ""
    if normalized_base_path.startswith("../") or normalized_base_path == "..":
        raise ValueError("--api-origin path must stay under the origin root")
    if normalized_base_path and not normalized_base_path.startswith("/"):
        normalized_base_path = "/" + normalized_base_path
    for segment in normalized_base_path.split("/"):
        if segment and not STATIC_PATH_SEGMENT_RE.fullmatch(segment):
            raise ValueError("--api-origin path contains an unsafe segment")

    display_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    display_url = f"{parsed.scheme}://{display_host}:{port}{normalized_base_path}"
    return ApiOrigin(parsed.scheme, parsed.hostname, port, normalized_base_path, display_url)


def _safe_static_path(static_root: Path, request_path: str) -> Path | None:
    parsed_path = urlsplit(request_path).path
    if any(char in parsed_path for char in "\\\r\n\0"):
        return None
    raw_segments = [segment for segment in parsed_path.split("/") if segment]
    if any(segment in {".", ".."} for segment in raw_segments):
        return None
    normalized = posixpath.normpath(parsed_path)
    if normalized in {".", "/"}:
        normalized = "/index.html"

    path_segments = [segment for segment in normalized.split("/") if segment]
    if any(segment in {".", ".."} or not STATIC_PATH_SEGMENT_RE.fullmatch(segment) for segment in path_segments):
        return None

    static_root_text = os.path.realpath(str(static_root))
    local_text = os.path.realpath(os.path.join(static_root_text, *path_segments))
    try:
        if os.path.commonpath([static_root_text, local_text]) != static_root_text:
            return None
    except ValueError:
        return None
    return Path(local_text)


def _static_content_type(path: Path) -> str:
    return STATIC_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _safe_header_value(value: str) -> str | None:
    if any(char in value for char in "\r\n\0"):
        return None
    return value


def _safe_header_pair(name: str, value: str) -> tuple[str, str] | None:
    if not HEADER_NAME_RE.fullmatch(name):
        return None
    safe_value = _safe_header_value(value)
    if safe_value is None:
        return None
    return name, safe_value


def _api_request_target(api_origin: ApiOrigin, request_path: str) -> str | None:
    if any(char in request_path for char in "\r\n\0"):
        return None
    parsed = urlsplit(request_path)
    if parsed.scheme or parsed.netloc:
        return None
    api_path = parsed.path or "/"
    if "\\" in api_path or not api_path.startswith("/api/"):
        return None
    if any(segment == ".." for segment in api_path.split("/")):
        return None

    if api_origin.base_path:
        upstream_path = api_origin.base_path.rstrip("/") + "/" + api_path.lstrip("/")
    else:
        upstream_path = api_path
    if parsed.query:
        return upstream_path + "?" + parsed.query
    return upstream_path


def _forwardable_request_headers(headers) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "host":
            continue
        safe_header = _safe_header_pair(name, value)
        if safe_header is not None:
            forwarded[safe_header[0]] = safe_header[1]
    return forwarded


def _forwardable_response_headers(headers) -> Iterable[tuple[str, str]]:
    for name, value in headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-length", "server", "date"}:
            continue
        safe_header = _safe_header_pair(name, value)
        if safe_header is not None:
            yield safe_header


def make_handler(static_root: Path, api_origin: str):
    static_root = static_root.resolve()
    api_origin = _validated_api_origin(api_origin)

    class TaskForgeApiClientHandler(BaseHTTPRequestHandler):
        server_version = "TaskForgeApiClient/0.1"

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

        def do_GET(self) -> None:
            if self.path == "/__client_health":
                self._send_json(200, {"ok": True, "apiOrigin": api_origin.display_url})
                return
            if urlsplit(self.path).path.startswith("/api/"):
                self._proxy_api()
                return
            self._serve_static()

        def do_POST(self) -> None:
            if urlsplit(self.path).path.startswith("/api/"):
                self._proxy_api()
                return
            self._send_json(405, {"error": {"code": "methodNotAllowed", "message": "method not allowed"}})

        def do_DELETE(self) -> None:
            if urlsplit(self.path).path.startswith("/api/"):
                self._proxy_api()
                return
            self._send_json(405, {"error": {"code": "methodNotAllowed", "message": "method not allowed"}})

        def do_OPTIONS(self) -> None:
            if urlsplit(self.path).path.startswith("/api/"):
                self._proxy_api()
                return
            self.send_response(204)
            self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
            self.end_headers()

        def _send_json(self, status: int, payload: dict) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self) -> None:
            path = _safe_static_path(static_root, self.path)
            if path is None or not path.is_file():
                self._send_json(404, {"error": {"code": "notFound", "message": "asset not found"}})
                return

            content = path.read_bytes()
            content_type = _static_content_type(path)

            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _proxy_api(self) -> None:
            upstream_target = _api_request_target(api_origin, self.path)
            if upstream_target is None:
                self._send_json(400, {"error": {"code": "badRequest", "message": "invalid API request path"}})
                return
            try:
                content_length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._send_json(400, {"error": {"code": "badRequest", "message": "invalid content length"}})
                return
            if content_length < 0:
                self._send_json(400, {"error": {"code": "badRequest", "message": "invalid content length"}})
                return
            body = self.rfile.read(content_length) if content_length else None
            connection_cls = http.client.HTTPSConnection if api_origin.scheme == "https" else http.client.HTTPConnection
            connection = connection_cls(api_origin.host, api_origin.port, timeout=20)

            try:
                connection.request(
                    self.command,
                    upstream_target,
                    body=body,
                    headers=_forwardable_request_headers(self.headers),
                )
                response = connection.getresponse()
                response_body = response.read()
                self.send_response(response.status)
                self._copy_response_headers(response.headers, response_body)
                self.end_headers()
                self.wfile.write(response_body)
            except (OSError, http.client.HTTPException) as error:
                self._send_json(
                    502,
                    {
                        "error": {
                            "code": "apiUnavailable",
                            "message": "could not reach TaskForge API",
                            "detail": str(error),
                        }
                    },
                )
            finally:
                connection.close()

        def _copy_response_headers(self, headers, response_body: bytes) -> None:
            set_cookies = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else []
            for name, value in _forwardable_response_headers(headers):
                if name.lower() == "set-cookie":
                    continue
                self.send_header(name, value)
            for cookie in set_cookies or []:
                safe_cookie = _safe_header_value(cookie)
                if safe_cookie is not None:
                    self.send_header("Set-Cookie", safe_cookie)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Cache-Control", "no-store")

    return TaskForgeApiClientHandler


def create_server(host: str, port: int, api_origin: str, static_root: Path) -> ThreadingHTTPServer:
    handler = make_handler(static_root=static_root, api_origin=api_origin)
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the TaskForge API todo client.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18120, type=int)
    parser.add_argument("--api-origin", default="http://127.0.0.1:18090")
    parser.add_argument("--static-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)

    server = create_server(
        host=args.host,
        port=args.port,
        api_origin=args.api_origin,
        static_root=Path(args.static_root),
    )
    print(f"TaskForge API client: http://{args.host}:{args.port}")
    print(f"Proxying /api/* to {args.api_origin.rstrip('/')}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
