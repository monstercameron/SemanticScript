"""SemanticScript external dependency resolution: fetch, integrity, cache, lock.

Fetching package source is build-time authority, not program behavior. It is an
explicit, auditable step driven by `build.sem` dependency rows, never an implicit
side effect of import resolution. Two phases keep that boundary visible:

  * ``sync`` resolves declared dependencies, fetches source, verifies integrity,
    populates the ``.semcache`` build-input cache, and writes ``sem.lock``. This
    is the only phase allowed to touch the network.
  * ``verify`` and ``dependency_module_registry`` are offline and deterministic.
    Import resolution reads the materialized cache only; a declared-but-unsynced
    dependency is an actionable error, never a silent network call.

The row contract (see docs/language/project-layout-build-sem.md):

    dependency        PROJECT ALIAS MODULE_PATH VERSION_OR_REF
    dependencyFetch   PROJECT ALIAS github OWNER/REPO REF
    dependencyFetch   PROJECT ALIAS http "https://.../archive.tar.gz"
    dependencySource  PROJECT ALIAS path "../local/package"     # path|local|github|http
    dependencyIntegrity PROJECT ALIAS sha256:<64hex> | commit:<7-40hex>
    dependencyCache   PROJECT ".semcache"
    dependencyLock    PROJECT "sem.lock"
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import os
import shutil
import re
import socket
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

LOCK_SCHEMA_VERSION = "sem.lock.v1"
DEFAULT_CACHE_DIR = ".semcache"
DEFAULT_LOCK_FILE = "sem.lock"
SHARED_CACHE_ENV_VARS = ("SEMANTICSCRIPT_CACHE", "SEMSC_CACHE")
_NETWORK_TIMEOUT_SECONDS = 60
_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024
_FETCHED_KINDS = frozenset({"github", "http"})
_WINDOWS_RESERVED_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})


class DependencyError(Exception):
    """Raised for malformed dependency rows, integrity failures, or an
    unmaterialized dependency. The message is user-facing and should always
    name the offending alias and the corrective command."""


class NetworkError(DependencyError):
    """A transport/connectivity failure (DNS resolution, TLS, HTTP, timeout) —
    distinct from integrity, extraction, or policy failures. Callers (and live
    tests) can treat this as "the network is unavailable" rather than "the
    dependency is bad", without masking real integrity/extract regressions."""


# --------------------------------------------------------------------------
# Build-tape tokenization (standalone so the compiler can import this module
# without a cycle). Mirrors semsc.tokenize_line for quoted-string handling.
# --------------------------------------------------------------------------

def _tokenize(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []
    tokens = []
    i = 0
    n = len(stripped)
    while i < n:
        c = stripped[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and stripped[j] != '"':
                if stripped[j] == "\\" and j + 1 < n:
                    nxt = stripped[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r",
                                "\\": "\\", '"': '"', "0": "\0"}.get(nxt, nxt))
                    j += 2
                else:
                    buf.append(stripped[j])
                    j += 1
            if j >= n:
                raise DependencyError(f"unterminated string in build.sem row: {stripped!r}")
            tokens.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not stripped[j].isspace():
                j += 1
            tokens.append(stripped[i:j])
            i = j
    return tokens


def _unwrap(token) -> str:
    if isinstance(token, tuple) and token and token[0] == "str":
        return token[1]
    return str(token)


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class DependencySpec:
    alias: str
    module_path: str = ""
    version: str = ""
    source_kind: str = ""          # path | local | github | http
    source_payload: tuple = ()     # path: (dir,); github: (owner/repo, ref); http: (url,)
    integrity_kind: str = ""       # sha256 | commit
    integrity_value: str = ""
    line: int = 0


@dataclass
class DependencyConfig:
    project_name: str
    build_sem_path: str
    cache_dir: str               # project-local cache (.semcache), for path deps + fallback
    lock_path: str
    specs: list = field(default_factory=list)
    shared_cache_dir: str = ""   # machine-wide cache for fetched deps (SEMANTICSCRIPT_CACHE)
    cache_dir_explicit: bool = False  # dependencyCache row present -> keep everything project-local

    def spec_for(self, alias: str) -> Optional[DependencySpec]:
        for spec in self.specs:
            if spec.alias == alias:
                return spec
        return None


@dataclass
class LockEntry:
    alias: str
    module_path: str
    version: str
    source_kind: str
    resolved: str          # commit / archive sha256 / path tree hash
    integrity: str         # the verified integrity string (sha256:.. / commit:..)
    content_hash: str = ""  # tree hash of the materialized cache dir (offline verify + idempotency)


@dataclass
class ResolvedDependency:
    spec: DependencySpec
    cache_dir: str         # absolute directory holding the package source
    lock_entry: LockEntry
    warnings: list = field(default_factory=list)
    from_cache: bool = False  # True when an idempotent sync reused the existing cache


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _strong_integrity(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith("sha256:"):
        digest = lowered[len("sha256:"):]
        return len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    if lowered.startswith("commit:"):
        digest = lowered[len("commit:"):]
        return 7 <= len(digest) <= 40 and all(c in "0123456789abcdef" for c in digest)
    return False


def parse_build_sem(text: str, build_sem_path: str) -> DependencyConfig:
    """Read dependency rows from a flat-row build tape into a structured config.

    Validation here is intentionally strict and local: a row that names an alias
    with no `dependency` declaration, an invalid source/fetch shape, or a weak
    integrity pin is rejected with an actionable message before any network or
    filesystem work happens."""
    project_root = os.path.dirname(os.path.abspath(build_sem_path))
    project_name = ""
    cache_dir = os.path.join(project_root, DEFAULT_CACHE_DIR)
    lock_path = os.path.join(project_root, DEFAULT_LOCK_FILE)
    cache_dir_explicit = False
    specs: dict = {}
    order: list = []

    def spec(alias: str, lineno: int) -> DependencySpec:
        if not alias:
            raise DependencyError(f"line {lineno}: dependency alias must not be empty")
        if alias not in specs:
            specs[alias] = DependencySpec(alias=alias)
            order.append(alias)
        return specs[alias]

    def set_source(current: DependencySpec, kind: str, payload: tuple, lineno: int):
        if current.source_kind and (current.source_kind != kind
                                    or tuple(current.source_payload) != tuple(payload)):
            raise DependencyError(
                f"line {lineno}: dependency `{current.alias}` already has a "
                f"`{current.source_kind}` source; a single alias may not declare "
                "conflicting source/fetch rows")
        current.source_kind = kind
        current.source_payload = tuple(payload)

    for lineno, raw in enumerate(text.splitlines(), start=1):
        toks = _tokenize(raw)
        if not toks:
            continue
        verb = toks[0]
        args = toks[1:]
        if verb == "buildProject" and args and not project_name:
            project_name = _unwrap(args[0])
            continue
        if verb == "dependency" and len(args) >= 4:
            current = spec(_unwrap(args[1]), lineno)
            current.module_path = _unwrap(args[2])
            current.version = _unwrap(args[3])
            current.line = lineno
        elif verb == "dependencyFetch" and len(args) >= 4:
            current = spec(_unwrap(args[1]), lineno)
            kind = _unwrap(args[2])
            if kind == "github":
                if len(args) < 5:
                    raise DependencyError(
                        f"line {lineno}: dependencyFetch github requires OWNER/REPO REF")
                owner_repo = _validate_github_owner_repo(_unwrap(args[3]))
                ref = _validate_github_ref(_unwrap(args[4]))
                set_source(current, "github", (owner_repo, ref), lineno)
            elif kind == "http":
                url = _unwrap(args[3])
                if not _is_https(url):
                    raise DependencyError(
                        f"line {lineno}: dependencyFetch http requires an https URL")
                set_source(current, "http", (url,), lineno)
            else:
                raise DependencyError(
                    f"line {lineno}: dependencyFetch kind `{kind}` is invalid; "
                    "expected github or http")
        elif verb == "dependencySource" and len(args) >= 3:
            current = spec(_unwrap(args[1]), lineno)
            kind, payload = _source_kind(args)
            values = tuple(_unwrap(p) for p in payload)
            if kind == "http" and not _is_https(values[0] if values else ""):
                raise DependencyError(
                    f"line {lineno}: dependencySource http requires an https URL")
            if kind == "github":
                if len(values) < 2:
                    raise DependencyError(
                        f"line {lineno}: github dependencySource requires "
                        "`github OWNER/REPO REF`; prefer dependencyFetch")
                values = (_validate_github_owner_repo(values[0]),
                          _validate_github_ref(values[1]))
            set_source(current, kind, values, lineno)
        elif verb == "dependencyIntegrity" and len(args) >= 3:
            value = _unwrap(args[2])
            if not _strong_integrity(value):
                raise DependencyError(
                    f"line {lineno}: dependencyIntegrity must be sha256:<64 hex> "
                    "or commit:<7-40 hex>")
            current = spec(_unwrap(args[1]), lineno)
            current.integrity_kind, _, current.integrity_value = value.partition(":")
            current.integrity_kind = current.integrity_kind.lower()
        elif verb == "dependencyCache" and len(args) >= 2:
            cache_dir = _project_relative(project_root, _unwrap(args[1]))
            cache_dir_explicit = True
        elif verb == "dependencyLock" and len(args) >= 2:
            lock_path = _project_relative(project_root, _unwrap(args[1]))

    ordered_specs = [specs[alias] for alias in order]
    for current in ordered_specs:
        if not current.module_path:
            raise DependencyError(
                f"dependency alias `{current.alias}` has source/integrity rows "
                "but no `dependency PROJECT ALIAS MODULE_PATH VERSION` declaration")
        if not current.source_kind:
            raise DependencyError(
                f"dependency `{current.alias}` has no source; add a "
                "`dependencyFetch` or `dependencySource` row")
    return DependencyConfig(
        project_name=project_name,
        build_sem_path=os.path.abspath(build_sem_path),
        cache_dir=cache_dir,
        lock_path=lock_path,
        specs=ordered_specs,
        shared_cache_dir=_shared_cache_root(),
        cache_dir_explicit=cache_dir_explicit,
    )


def _shared_cache_root() -> str:
    """Machine-wide cache root for fetched dependencies, so multiple projects
    share a single download per pinned version. Falls back to a per-user
    location when no environment override is set."""
    for env_name in SHARED_CACHE_ENV_VARS:
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return os.path.abspath(os.path.expandvars(os.path.expanduser(raw)))
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.join(os.path.expanduser("~"), ".cache"))
    return os.path.join(os.path.abspath(base), "semanticscript", "deps")


def cache_dir_for(config: DependencyConfig, spec: DependencySpec) -> str:
    """Resolve the absolute cache directory for one dependency.

    Fetched (github/http) dependencies use the shared, version-keyed cache so
    repos share downloads and versions coexist. Path/local dependencies — and
    everything when the build tape sets an explicit `dependencyCache` — stay in
    the project-local cache because local source is not a shareable artifact."""
    if spec.source_kind in _FETCHED_KINDS and not config.cache_dir_explicit and config.shared_cache_dir:
        root = config.shared_cache_dir
    else:
        root = config.cache_dir
    return os.path.join(root, cache_subdir(spec))


def _source_kind(args):
    if len(args) >= 4:
        return _unwrap(args[2]), args[3:]
    source_text = _unwrap(args[2])
    if source_text.startswith(("https://", "http://")):
        return "http", args[2:3]
    if _has_github_host_prefix(source_text):
        return "github", args[2:3]
    return "local", args[2:3]


def _is_https(value: str) -> bool:
    return value.startswith("https://") and " " not in value and len(value) > len("https://")


_GITHUB_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Refs may contain slashes (refs/tags/v1) but nothing that could re-target the
# codeload URL: no scheme/host (`:`, `//`), query/fragment (`?`, `#`), or
# whitespace, and no `..` path segment.
_GITHUB_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _has_github_host_prefix(value: str) -> bool:
    first_segment, separator, _ = value.partition("/")
    return bool(separator) and first_segment.lower() == "github.com"


def _validate_github_owner_repo(owner_repo: str) -> str:
    parsed = urllib.parse.urlsplit(owner_repo)
    if parsed.scheme or parsed.netloc:
        raise DependencyError(
            f"github source `{owner_repo}` must be OWNER/REPO or "
            "github.com/OWNER/REPO, not a URL")

    parts = owner_repo.split("/")
    if parts and parts[0].lower() == "github.com":
        parts = parts[1:]

    valid = (len(parts) == 2
             and all(_GITHUB_SEGMENT_RE.match(part) and part not in (".", "..")
                     for part in parts))
    if not valid:
        raise DependencyError(
            f"github source `{owner_repo}` must be OWNER/REPO or "
            "github.com/OWNER/REPO using only letters, digits, '.', '_', or "
            "'-' (no '.' or '..' segment)")
    return f"{parts[0]}/{parts[1]}"


def _validate_github_ref(ref: str) -> str:
    if not ref or not _GITHUB_REF_RE.match(ref) or any(seg == ".." for seg in ref.split("/")):
        raise DependencyError(
            f"github ref `{ref}` is invalid; refs may contain only letters, "
            "digits, '.', '_', '-', '/' and no '..' segment")
    return ref


def _project_relative(project_root: str, value: str) -> str:
    if os.path.isabs(value):
        return os.path.abspath(value)
    return os.path.abspath(os.path.join(project_root, value))


# --------------------------------------------------------------------------
# Cache keys
# --------------------------------------------------------------------------

def cache_subdir(spec: DependencySpec) -> str:
    """Stable, filesystem-safe cache key for a dependency. Keys are derived
    from package identity (module path + ref) so the same pin always maps to
    the same cache directory across machines."""
    if spec.source_kind == "github":
        owner_repo, ref = spec.source_payload
        owner_repo = _validate_github_owner_repo(owner_repo)
        owner, repo = owner_repo.split("/")
        return _safe_join("github.com", owner, repo, _safe_ref(ref))
    if spec.source_kind == "http":
        (url,) = spec.source_payload
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return _safe_join("http", digest)
    # path / local: key by module path so collisions are deterministic.
    return _safe_join("path", *spec.module_path.split("/"))


def _safe_ref(ref: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in ref) or "ref"


def _safe_join(*parts: str) -> str:
    safe = []
    for part in parts:
        cleaned = "".join(c if (c.isalnum() or c in "._-") else "_" for c in part)
        if cleaned in ("", ".", ".."):
            cleaned = "_"
        safe.append(cleaned)
    return os.path.join(*safe)


# --------------------------------------------------------------------------
# Integrity + tree hashing
# --------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_hash(root: str) -> str:
    """Deterministic content hash of a directory tree: sorted relative paths
    plus file bytes. Used to pin/verify `path` dependencies that have no archive
    checksum or commit of their own."""
    digest = hashlib.sha256()
    for rel in _sorted_relative_files(root):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        with open(os.path.join(root, rel), "rb") as handle:
            digest.update(handle.read())
        digest.update(b"\0")
    return digest.hexdigest()


def _sorted_relative_files(root: str):
    collected = []
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            abs_path = os.path.join(current, name)
            rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
            collected.append(rel)
    collected.sort()
    return collected


# --------------------------------------------------------------------------
# Network + archive extraction
# --------------------------------------------------------------------------

def _assert_public_url(url: str) -> None:
    """Reject URLs whose host resolves to a non-public address (loopback,
    private, link-local, reserved, multicast). Without this, an https URL such
    as `https://169.254.169.254/...` or `https://localhost/...` would pass the
    https-only check and turn the fetcher into an SSRF primitive against the
    host's own metadata/internal services. Applied to the initial URL and every
    redirect target. (This pre-resolve check cannot fully defeat DNS rebinding,
    but blocks the direct internal-host cases.)"""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise DependencyError(f"dependency fetch URL has no host: {url!r}")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as resolve_error:
        raise NetworkError(f"cannot resolve dependency host {host!r}: {resolve_error}")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast or address.is_unspecified):
            raise DependencyError(
                f"refusing to fetch from non-public address {address} for host {host!r}")


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when they stay on https AND target a public host. A
    fetch must never be redirected down to http://, file://, another scheme, or
    an internal address — that would defeat the https-only guarantee and open an
    SSRF/downgrade path."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_https(newurl):
            raise DependencyError(
                f"dependency fetch refused a non-https redirect to {newurl!r}")
        _assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_download(url: str) -> bytes:
    if not _is_https(url):
        raise DependencyError(f"refusing to fetch non-https URL: {url!r}")
    _assert_public_url(url)
    opener = urllib.request.build_opener(_HttpsOnlyRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "semanticscript-deps"})
    try:
        with opener.open(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:  # noqa: S310 (https enforced above)
            if not _is_https(response.geturl()):
                raise DependencyError(f"dependency fetch resolved to a non-https URL: {response.geturl()!r}")
            data = response.read(_MAX_ARCHIVE_BYTES + 1)
    except urllib.error.URLError as transport_error:
        # A non-https redirect raises DependencyError from the handler, which
        # URLError would otherwise wrap — keep that as a policy failure.
        if isinstance(transport_error.reason, DependencyError):
            raise transport_error.reason
        raise NetworkError(f"failed to fetch {url!r}: {transport_error}")
    except (TimeoutError, ConnectionError, socket.timeout) as transport_error:
        raise NetworkError(f"failed to fetch {url!r}: {transport_error}")
    if len(data) > _MAX_ARCHIVE_BYTES:
        raise DependencyError(
            f"dependency archive at {url!r} exceeds {_MAX_ARCHIVE_BYTES} bytes")
    return data


def _github_tarball_url(owner_repo: str, ref: str) -> str:
    owner_repo = _validate_github_owner_repo(owner_repo)
    ref = _validate_github_ref(ref)
    # Defense in depth: the ref is already validated, but encode it so it can
    # only ever be a path segment of the codeload URL — never a host, query, or
    # fragment.
    encoded_ref = urllib.parse.quote(ref, safe="/")
    return f"https://codeload.github.com/{owner_repo}/tar.gz/{encoded_ref}"


def _is_within(base: str, target: str) -> bool:
    base_abs = os.path.abspath(base)
    target_abs = os.path.abspath(target)
    try:
        return os.path.commonpath([base_abs, target_abs]) == base_abs
    except ValueError:
        return False


def _extract_archive(data: bytes, dest: str, *, strip_top_level: bool) -> None:
    """Extract a .tar.gz or .zip archive into ``dest`` with path-traversal and
    symlink guards. Archive entries that escape ``dest`` abort the whole
    extraction — a hostile package must never write outside its cache dir."""
    os.makedirs(dest, exist_ok=True)
    if _looks_like_zip(data):
        _extract_zip(data, dest, strip_top_level=strip_top_level)
    else:
        _extract_tar(data, dest, strip_top_level=strip_top_level)


def _looks_like_zip(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _strip(member_name: str, strip_top_level: bool) -> Optional[str]:
    normalized = member_name.replace("\\", "/").lstrip("/")
    if strip_top_level:
        parts = normalized.split("/", 1)
        normalized = parts[1] if len(parts) == 2 else ""
    if not normalized or normalized in (".", ".."):
        return None
    for part in normalized.split("/"):
        if part == "..":
            raise DependencyError(f"archive entry escapes cache directory: {member_name!r}")
        stem = part.split(".", 1)[0].strip().lower()
        if stem in _WINDOWS_RESERVED_NAMES or part != part.strip(" ."):
            raise DependencyError(
                f"archive entry uses a reserved or unsafe name: {member_name!r}")
    return normalized


def _extract_tar(data: bytes, dest: str, *, strip_top_level: bool) -> None:
    written = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise DependencyError(
                    f"archive contains a link member, refused: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                continue
            rel = _strip(member.name, strip_top_level)
            if rel is None:
                continue
            target = os.path.join(dest, rel)
            if not _is_within(dest, target):
                raise DependencyError(f"archive entry escapes cache directory: {member.name!r}")
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            written = _guard_extracted_size(written, member.size, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            with open(target, "wb") as handle:
                handle.write(extracted.read())


def _extract_zip(data: bytes, dest: str, *, strip_top_level: bool) -> None:
    written = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            rel = _strip(member.filename, strip_top_level)
            if rel is None:
                continue
            target = os.path.join(dest, rel)
            if not _is_within(dest, target):
                raise DependencyError(f"archive entry escapes cache directory: {member.filename!r}")
            if member.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            written = _guard_extracted_size(written, member.file_size, member.filename)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as handle:
                handle.write(source.read())


def _guard_extracted_size(written: int, member_size: int, name: str) -> int:
    total = written + max(int(member_size), 0)
    if total > _MAX_EXTRACTED_BYTES:
        raise DependencyError(
            f"dependency archive expands past {_MAX_EXTRACTED_BYTES} bytes "
            f"(decompression bomb guard) at {name!r}")
    return total


# --------------------------------------------------------------------------
# Materialization
# --------------------------------------------------------------------------

def _atomic_populate(final_dir: str, populate: Callable[[str], None]) -> None:
    """Fill a sibling temp directory via ``populate`` then move it into place.

    Writing to the final cache dir directly leaves a half-populated directory if
    two `sem deps sync` runs race or one crashes mid-extract — and the shared
    cache is machine-wide. Building in a temp dir and swapping it in makes a
    populated cache dir always complete. When replacing an existing dir, the old
    one is renamed aside first (a fast rename, not a slow rmtree) so the final
    path is only briefly absent — never half-populated — before the new content
    is swapped in. If another run wins the race, its result is kept."""
    parent = os.path.dirname(final_dir)
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".semdeps-tmp-", dir=parent)
    trash = None
    try:
        populate(tmp)
        if os.path.isdir(final_dir):
            trash = f"{final_dir}.semdeps-old-{os.urandom(4).hex()}"
            os.replace(final_dir, trash)  # atomic rename of the existing dir aside
        os.replace(tmp, final_dir)        # atomic rename into the now-absent path
        tmp = None
    finally:
        if tmp is not None and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        if trash is not None and os.path.isdir(trash):
            shutil.rmtree(trash, ignore_errors=True)


def _copy_into(src: str, dest: str) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest, symlinks=False, ignore=shutil.ignore_patterns(
        ".semcache", "build", "__pycache__", ".git"))


def materialize(spec: DependencySpec, config: DependencyConfig, *,
                allow_network: bool,
                downloader: Optional[Callable[[str], bytes]] = None,
                locked_entry: Optional[LockEntry] = None,
                force: bool = False) -> ResolvedDependency:
    """Populate the cache for one dependency and return its lock entry.

    Integrity precedence: an explicit `sha256:` pin wins; otherwise a prior lock
    entry pins the bytes (reproducible builds); otherwise the first fetch is
    trust-on-first-use and recorded with a warning. Fetched dependencies are
    idempotent — an existing cache dir whose content hash matches the lock is
    reused without touching the network. Cache writes are atomic. Network access
    is gated behind ``allow_network`` so offline phases never reach out."""
    download = downloader or _default_download
    cache_dir = cache_dir_for(config, spec)
    warnings: list = []
    expected_sha = spec.integrity_value.lower() if spec.integrity_kind == "sha256" else ""
    locked_sha = ""
    if locked_entry and locked_entry.integrity.startswith("sha256:"):
        locked_sha = locked_entry.integrity[len("sha256:"):]

    if spec.source_kind in ("path", "local"):
        (raw_path,) = spec.source_payload or ("",)
        if not raw_path:
            raise DependencyError(f"dependency `{spec.alias}` path source is empty")
        src = _project_relative(os.path.dirname(config.build_sem_path), raw_path)
        if not os.path.isdir(src):
            raise DependencyError(
                f"dependency `{spec.alias}` path source `{raw_path}` is not a directory")
        _atomic_populate(cache_dir, lambda tmp: _copy_into(src, tmp))
        content = tree_hash(cache_dir)
        if expected_sha and content != expected_sha:
            raise DependencyError(
                f"dependency `{spec.alias}` tree hash {content} does not match "
                f"declared sha256:{spec.integrity_value}")
        if locked_sha and content != locked_sha and not expected_sha:
            warnings.append(
                f"path dependency `{spec.alias}` changed since sem.lock "
                f"({locked_sha[:12]} -> {content[:12]}); lock updated")
        resolved = content
        integrity = f"sha256:{content}"
        content_hash = content
        from_cache = False
    elif spec.source_kind in ("github", "http"):
        if spec.integrity_kind == "commit":
            warnings.append(
                f"dependency `{spec.alias}` uses a `commit:` pin, which selects a "
                "ref but is not cryptographically verified; add a `sha256:` "
                "integrity row for tamper-proof reproducibility")
        locked_content = locked_entry.content_hash if locked_entry else ""
        pin_agrees_with_lock = (not expected_sha) or (locked_sha == expected_sha)
        if (not force and os.path.isdir(cache_dir) and locked_content and pin_agrees_with_lock
                and tree_hash(cache_dir) == locked_content):
            # Idempotent reuse: the cache already holds exactly the locked
            # content and any explicit sha256 pin agrees with the lock, so there
            # is nothing to fetch. The archive sha256 cannot be recomputed from
            # extracted files, so the lock's contentHash is the offline integrity
            # anchor. Refresh identity metadata (module path / version) from the
            # current spec so a build.sem rename or version bump is not dropped,
            # while keeping the verified content pin. A changed/added sha256 pin
            # that disagrees with the lock falls through to a re-fetch + verify.
            return ResolvedDependency(
                spec=spec, cache_dir=cache_dir, warnings=warnings, from_cache=True,
                lock_entry=LockEntry(
                    alias=spec.alias, module_path=spec.module_path,
                    version=spec.version, source_kind=spec.source_kind,
                    resolved=locked_entry.resolved, integrity=locked_entry.integrity,
                    content_hash=locked_entry.content_hash))
        if not allow_network:
            raise DependencyError(
                f"dependency `{spec.alias}` requires a network fetch; run `sem deps sync`")
        if spec.source_kind == "github":
            owner_repo, ref = spec.source_payload
            url = _github_tarball_url(owner_repo, ref)
        else:
            (url,) = spec.source_payload
        data = download(url)
        archive_sha = sha256_bytes(data)
        if expected_sha and archive_sha != expected_sha:
            raise DependencyError(
                f"dependency `{spec.alias}` archive sha256 {archive_sha} does not "
                f"match declared sha256:{spec.integrity_value}")
        if not expected_sha and locked_sha and archive_sha != locked_sha:
            raise DependencyError(
                f"dependency `{spec.alias}` archive sha256 {archive_sha} does not "
                f"match the locked sha256:{locked_sha}; the upstream ref changed — "
                "update build.sem or delete sem.lock to re-pin intentionally")
        if not expected_sha and not locked_sha:
            warnings.append(
                f"dependency `{spec.alias}` was fetched without a `dependencyIntegrity` "
                f"pin (trust-on-first-use); the resolved sha256 is now locked. Add "
                f"`dependencyIntegrity {config.project_name} {spec.alias} sha256:{archive_sha}`")
        _atomic_populate(cache_dir, lambda tmp: _extract_archive(data, tmp, strip_top_level=True))
        resolved = archive_sha
        integrity = f"sha256:{archive_sha}"
        content_hash = tree_hash(cache_dir)
        from_cache = False
    else:
        raise DependencyError(
            f"dependency `{spec.alias}` has unsupported source kind `{spec.source_kind}`")

    lock_entry = LockEntry(
        alias=spec.alias,
        module_path=spec.module_path,
        version=spec.version,
        source_kind=spec.source_kind,
        resolved=resolved,
        integrity=integrity,
        content_hash=content_hash,
    )
    return ResolvedDependency(spec=spec, cache_dir=cache_dir, lock_entry=lock_entry,
                              warnings=warnings, from_cache=from_cache)


# --------------------------------------------------------------------------
# Lock file
# --------------------------------------------------------------------------

def write_lock(config: DependencyConfig, entries) -> None:
    payload = {
        "schemaVersion": LOCK_SCHEMA_VERSION,
        "project": config.project_name,
        "dependencies": [
            {
                "alias": e.alias,
                "modulePath": e.module_path,
                "version": e.version,
                "sourceKind": e.source_kind,
                "resolved": e.resolved,
                "integrity": e.integrity,
                "contentHash": e.content_hash,
            }
            for e in entries
        ],
    }
    with open(config.lock_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_lock(config: DependencyConfig):
    if not os.path.isfile(config.lock_path):
        return None
    with open(config.lock_path, "r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle)
        except (ValueError, UnicodeDecodeError) as parse_error:
            raise DependencyError(
                f"sem.lock at {config.lock_path} is not valid JSON "
                f"({parse_error}); regenerate with `sem deps sync`")
    found_version = payload.get("schemaVersion") if isinstance(payload, dict) else None
    if found_version != LOCK_SCHEMA_VERSION:
        raise DependencyError(
            f"sem.lock schemaVersion `{found_version}` is not "
            f"`{LOCK_SCHEMA_VERSION}`; regenerate with `sem deps sync`")
    entries = []
    for row in payload.get("dependencies", []):
        entries.append(LockEntry(
            alias=row.get("alias", ""),
            module_path=row.get("modulePath", ""),
            version=row.get("version", ""),
            source_kind=row.get("sourceKind", ""),
            resolved=row.get("resolved", ""),
            integrity=row.get("integrity", ""),
            content_hash=row.get("contentHash", ""),
        ))
    return entries


# --------------------------------------------------------------------------
# High-level operations
# --------------------------------------------------------------------------

def sync(config: DependencyConfig, *, allow_network: bool = True,
         downloader: Optional[Callable[[str], bytes]] = None,
         force: bool = False):
    """Materialize every declared dependency and write the lock file.

    Prior lock entries are fed back in so a fetched dependency whose cache
    already matches the lock is reused without a network round-trip. ``force``
    bypasses that reuse and re-fetches + re-verifies every dependency — the way
    to repair a cache flagged corrupt by ``verify``."""
    prior = {entry.alias: entry for entry in (read_lock(config) or [])}
    resolved = [materialize(spec, config, allow_network=allow_network,
                            downloader=downloader, locked_entry=prior.get(spec.alias),
                            force=force)
                for spec in config.specs]
    os.makedirs(config.cache_dir, exist_ok=True)
    write_lock(config, [r.lock_entry for r in resolved])
    return resolved


def _dir_stats(path: str):
    file_count = 0
    total_bytes = 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            file_path = os.path.join(current, name)
            if os.path.isfile(file_path):
                file_count += 1
                try:
                    total_bytes += os.path.getsize(file_path)
                except OSError:
                    pass
    return file_count, total_bytes


def list_cached_packages(roots):
    """Inventory materialized packages across the given ``(scope, root)`` cache
    directories. A package is the topmost directory under a root that holds
    files (github/http/path leaf); transient `.semdeps-*` swap dirs are ignored.
    This is the agent-facing cache listing — it reads the cache only, never the
    network."""
    entries: list = []
    for scope, root in roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".semdeps-"))
            real_files = [f for f in files if os.path.isfile(os.path.join(current, f))]
            if not real_files:
                continue
            rel = os.path.relpath(current, root).replace(os.sep, "/")
            head = rel.split("/", 1)[0]
            kind = {"github.com": "github", "http": "http", "path": "path"}.get(head, "unknown")
            file_count, total_bytes = _dir_stats(current)
            entries.append({
                "scope": scope,
                "key": rel,
                "path": current,
                "sourceKind": kind,
                "fileCount": file_count,
                "bytes": total_bytes,
            })
            dirs[:] = []  # a package is a leaf; don't list its submodule subdirs
    entries.sort(key=lambda entry: (entry["scope"], entry["key"]))
    return entries


def purge(config: DependencyConfig, *, remove_lock: bool = False):
    """Remove the materialized cache directory for every declared dependency,
    and optionally the lock file. The next `sem deps sync` re-fetches from
    scratch. Returns the list of removed paths. Only the current project's
    declared dependency cache keys are touched — never the whole shared cache."""
    removed: list = []
    for spec in config.specs:
        cache_dir = cache_dir_for(config, spec)
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
            removed.append(cache_dir)
    if remove_lock and os.path.isfile(config.lock_path):
        os.remove(config.lock_path)
        removed.append(config.lock_path)
    return removed


def verify(config: DependencyConfig):
    """Offline check that the lock and cache agree with the declared rows.

    Returns a list of (alias, ok, detail). Compares the declared spec, the lock
    entry, and the materialized cache so reproducible builds never silently
    drift from the lock — including ref/version changes in build.sem that leave
    the lock stale."""
    locked = read_lock(config)
    results = []
    if locked is None:
        for spec in config.specs:
            results.append((spec.alias, False, "no sem.lock; run `sem deps sync`"))
        return results
    locked_by_alias = {entry.alias: entry for entry in locked}
    for spec in config.specs:
        entry = locked_by_alias.get(spec.alias)
        if entry is None:
            results.append((spec.alias, False, "missing from sem.lock; run `sem deps sync`"))
            continue
        drift = _spec_lock_drift(spec, entry)
        if drift:
            results.append((spec.alias, False, f"build.sem drifted from sem.lock: {drift}; run `sem deps sync`"))
            continue
        cache_dir = cache_dir_for(config, spec)
        if not os.path.isdir(cache_dir):
            results.append((spec.alias, False, "cache missing; run `sem deps sync`"))
            continue
        actual = tree_hash(cache_dir)
        if entry.content_hash:
            if actual != entry.content_hash:
                results.append((spec.alias, False, "cache content does not match sem.lock"))
                continue
        elif spec.source_kind in ("path", "local"):
            if f"sha256:{actual}" != entry.integrity:
                results.append((spec.alias, False, "cache tree hash does not match sem.lock"))
                continue
        else:
            # A fetched dep with no recorded contentHash cannot be content-verified
            # offline (the archive bytes are gone). Fail closed rather than trust it.
            results.append((spec.alias, False, "lock predates contentHash; run `sem deps sync`"))
            continue
        if spec.integrity_kind == "sha256" and entry.integrity != f"sha256:{spec.integrity_value.lower()}":
            results.append((spec.alias, False, "declared integrity does not match sem.lock"))
            continue
        results.append((spec.alias, True, "ok"))
    return results


def _spec_lock_drift(spec: DependencySpec, entry: LockEntry) -> str:
    if spec.module_path != entry.module_path:
        return f"module path {entry.module_path!r} -> {spec.module_path!r}"
    if spec.version != entry.version:
        return f"version {entry.version!r} -> {spec.version!r}"
    if spec.source_kind != entry.source_kind:
        return f"source kind {entry.source_kind!r} -> {spec.source_kind!r}"
    return ""


def dependency_module_registry(config: DependencyConfig) -> dict:
    """Offline map of importable module path -> source file for every declared
    dependency. Reads only the materialized cache. A declared-but-unmaterialized
    dependency raises, instructing the caller to run `sem deps sync` — import
    resolution must never reach the network on its own."""
    resolved, pending = resolve_import_registry(config)
    if pending:
        first_alias = next(iter(pending))
        raise DependencyError(pending[first_alias])
    return resolved


def resolve_import_registry(config: DependencyConfig):
    """Split declared dependencies into (resolved, pending) for the compiler's
    import bridge. ``resolved`` maps importable module paths to cached source
    files; ``pending`` maps the module path of each declared-but-unmaterialized
    dependency to an actionable message. The bridge merges ``resolved`` into the
    import registry and raises the matching ``pending`` message only if the
    program actually imports that module — so unused, unsynced dependencies do
    not block an otherwise offline build."""
    resolved: dict = {}
    pending: dict = {}
    for spec in config.specs:
        cache_dir = cache_dir_for(config, spec)
        if not os.path.isdir(cache_dir):
            message = (
                f"dependency `{spec.alias}` ({spec.module_path}) is declared in "
                f"{os.path.basename(config.build_sem_path)} but not materialized; "
                "run `sem deps sync` to fetch and lock it")
            pending[spec.module_path] = message
            continue
        for module_path, source_file in _package_modules(cache_dir, spec.module_path).items():
            resolved[module_path] = source_file
    return resolved, pending


def _package_modules(cache_dir: str, declared_module_path: str) -> dict:
    """Map the module paths a cached package exports to source files.

    If the package ships its own build.sem, honor its modulePath + registerModule
    rows so submodules resolve. Otherwise map the consumer-declared module path
    to the package's root source file (main.sem / index.sem / sole source)."""
    modules: dict = {}
    package_build = _find_build_sem(cache_dir)
    if package_build is not None:
        with open(package_build, "r", encoding="utf-8") as handle:
            build_text = handle.read()
        package_root_path = declared_module_path
        register_rows = []
        for raw in build_text.splitlines():
            toks = _tokenize(raw)
            if not toks:
                continue
            if toks[0] == "modulePath" and len(toks) >= 3:
                package_root_path = _unwrap(toks[2])
            elif toks[0] == "registerModule" and len(toks) >= 4:
                register_rows.append((_unwrap(toks[2]), _unwrap(toks[3])))
        build_dir = os.path.dirname(package_build)
        for module_name, folder in register_rows:
            # The folder comes from the FETCHED package's own build.sem, which is
            # untrusted network-controlled input. Clamp it to the cache dir so a
            # hostile package cannot point `registerModule` at `../../etc` or an
            # absolute path and have the compiler inline a file outside its cache.
            candidate = os.path.join(build_dir, folder)
            if not _is_within(cache_dir, candidate):
                raise DependencyError(
                    f"package at {cache_dir} declares registerModule path "
                    f"`{folder}` that escapes its cache directory")
            resolved = _select_module_source(candidate)
            if resolved is not None:
                modules[module_name] = resolved
        if declared_module_path not in modules:
            root_source = _select_module_source(cache_dir)
            if root_source is not None:
                modules.setdefault(package_root_path, root_source)
                modules.setdefault(declared_module_path, root_source)
        return modules

    root_source = _select_module_source(cache_dir)
    if root_source is None:
        raise DependencyError(
            f"cached package at {cache_dir} has no resolvable module source "
            "(expected build.sem, main.sem, index.sem, or a single .sem source)")
    modules[declared_module_path] = root_source
    return modules


def _find_build_sem(cache_dir: str) -> Optional[str]:
    for name in ("build.sem", "build.sscript"):
        candidate = os.path.join(cache_dir, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _select_module_source(folder: str) -> Optional[str]:
    if os.path.isfile(folder):
        return os.path.abspath(folder)
    if not os.path.isdir(folder):
        return None
    for name in ("main.sem", "main.sscript", "index.sem", "index.sscript"):
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    sources = []
    for entry in sorted(os.listdir(folder)):
        lowered = entry.lower()
        if lowered in ("build.sem", "build.sscript"):
            continue
        if lowered.endswith((".test.sem", ".test.sscript")):
            continue
        if lowered.endswith((".sem", ".sscript")):
            sources.append(os.path.join(folder, entry))
    if len(sources) == 1:
        return os.path.abspath(sources[0])
    return None
