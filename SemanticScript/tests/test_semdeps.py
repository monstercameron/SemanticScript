"""Unit tests for SemanticScript external dependency resolution (semdeps).

These exercise the real fetch/integrity/cache/lock pipeline. The github/http
paths use an injected in-memory downloader so the suite stays offline and
deterministic; the `path` dependency path runs end to end against the
filesystem. Each test asserts behavior that a no-op implementation would fail.
"""

import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "compiler")))

import semdeps  # noqa: E402


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _make_targz(members: dict, *, top_level: str = "pkg-1.0") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for rel, content in members.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=f"{top_level}/{rel}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class ParseTests(unittest.TestCase):
    def _config(self, body: str):
        tmp = tempfile.mkdtemp()
        build = os.path.join(tmp, "build.sem")
        _write(build, body)
        return semdeps.parse_build_sem(body, build), tmp

    def test_parses_github_dependency(self):
        config, _ = self._config(
            "buildProject demo\n"
            "dependency demo semstd github.com/example/semstd v1.0.0\n"
            "dependencyFetch demo semstd github example/semstd v1.0.0\n"
            "dependencyIntegrity demo semstd sha256:" + "a" * 64 + "\n"
        )
        self.assertEqual(config.project_name, "demo")
        spec = config.spec_for("semstd")
        self.assertEqual(spec.module_path, "github.com/example/semstd")
        self.assertEqual(spec.source_kind, "github")
        self.assertEqual(spec.source_payload, ("example/semstd", "v1.0.0"))
        self.assertEqual(spec.integrity_kind, "sha256")

    def test_path_dependency_with_explicit_kind(self):
        config, _ = self._config(
            "buildProject demo\n"
            "dependency demo local github.com/example/local v0.1.0\n"
            "dependencySource demo local path \"../local\"\n"
        )
        spec = config.spec_for("local")
        self.assertEqual(spec.source_kind, "path")
        self.assertEqual(spec.source_payload, ("../local",))

    def test_custom_cache_and_lock_paths(self):
        config, tmp = self._config(
            "buildProject demo\n"
            "dependencyCache demo \".vendorcache\"\n"
            "dependencyLock demo \"deps.lock\"\n"
        )
        self.assertEqual(config.cache_dir, os.path.join(tmp, ".vendorcache"))
        self.assertEqual(config.lock_path, os.path.join(tmp, "deps.lock"))

    def test_source_row_without_dependency_declaration_is_rejected(self):
        with self.assertRaises(semdeps.DependencyError):
            self._config(
                "buildProject demo\n"
                "dependencySource demo orphan path \"../x\"\n"
            )

    def test_weak_integrity_is_rejected(self):
        with self.assertRaises(semdeps.DependencyError):
            self._config(
                "buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1\n"
                "dependencyFetch demo semstd github example/semstd v1\n"
                "dependencyIntegrity demo semstd md5:abc\n"
            )

    def test_dependency_without_source_is_rejected(self):
        with self.assertRaises(semdeps.DependencyError):
            self._config(
                "buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1\n"
            )

    def test_conflicting_source_rows_are_rejected(self):
        with self.assertRaises(semdeps.DependencyError):
            self._config(
                "buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1\n"
                "dependencyFetch demo semstd github example/semstd v1\n"
                "dependencySource demo semstd path \"../semstd\"\n"
            )

    def test_empty_alias_is_rejected(self):
        with self.assertRaises(semdeps.DependencyError):
            self._config(
                "buildProject demo\n"
                "dependency demo \"\" github.com/example/semstd v1\n"
            )


class GithubSafetyTests(unittest.TestCase):
    """The github source is the highest-risk import path: owner/repo/ref flow
    into a network URL and a cache path. These assert no injection is possible."""

    def _parse(self, body):
        tmp = tempfile.mkdtemp()
        build = os.path.join(tmp, "build.sem")
        _write(build, body)
        return semdeps.parse_build_sem(body, build)

    def test_valid_github_url_built_from_owner_repo_ref(self):
        self.assertEqual(
            semdeps._github_tarball_url("example/semstd", "v1.0.0"),
            "https://codeload.github.com/example/semstd/tar.gz/v1.0.0")

    def test_ref_with_slashes_is_encoded_as_path(self):
        self.assertEqual(
            semdeps._github_tarball_url("example/semstd", "refs/tags/v1.0.0"),
            "https://codeload.github.com/example/semstd/tar.gz/refs/tags/v1.0.0")

    def test_url_builder_rejects_path_traversal_ref(self):
        with self.assertRaises(semdeps.DependencyError):
            semdeps._github_tarball_url("example/semstd", "../../other/repo/tar.gz/main")

    def test_url_builder_rejects_query_and_fragment_refs(self):
        for bad in ("v1?x=1", "v1#frag", "v1 2", "v1@host", "http://evil"):
            with self.assertRaises(semdeps.DependencyError):
                semdeps._github_tarball_url("example/semstd", bad)

    def test_url_builder_rejects_bad_owner_repo(self):
        for bad in ("..", "evil/..", "a b/c", "only-one-part"):
            with self.assertRaises(semdeps.DependencyError):
                semdeps._github_tarball_url(bad, "v1.0.0")

    def test_fetch_row_with_injection_ref_is_rejected_at_parse(self):
        with self.assertRaises(semdeps.DependencyError):
            self._parse(
                "buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1\n"
                "dependencyFetch demo semstd github example/semstd \"v1?evil=1\"\n")

    def test_fetch_row_with_bad_owner_is_rejected_at_parse(self):
        with self.assertRaises(semdeps.DependencyError):
            self._parse(
                "buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1\n"
                "dependencyFetch demo semstd github \"evil/../x\" v1\n")


class CacheKeyTests(unittest.TestCase):
    def test_github_key_is_stable_and_safe(self):
        spec = semdeps.DependencySpec(
            alias="a", module_path="github.com/example/semstd",
            source_kind="github", source_payload=("example/semstd", "v1.0.0"))
        key = semdeps.cache_subdir(spec)
        self.assertEqual(key, os.path.join("github.com", "example", "semstd", "v1.0.0"))
        self.assertEqual(key, semdeps.cache_subdir(spec))

    def test_http_key_hashes_url(self):
        spec = semdeps.DependencySpec(
            alias="a", source_kind="http",
            source_payload=("https://example.com/a.tar.gz",))
        self.assertTrue(semdeps.cache_subdir(spec).startswith("http" + os.sep))


class IntegrityTests(unittest.TestCase):
    def test_tree_hash_is_order_independent_and_content_sensitive(self):
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        _write(os.path.join(tmp_a, "z.sem"), "operation z\n")
        _write(os.path.join(tmp_a, "a", "m.sem"), "operation m\n")
        _write(os.path.join(tmp_b, "a", "m.sem"), "operation m\n")
        _write(os.path.join(tmp_b, "z.sem"), "operation z\n")
        self.assertEqual(semdeps.tree_hash(tmp_a), semdeps.tree_hash(tmp_b))
        _write(os.path.join(tmp_b, "z.sem"), "operation zChanged\n")
        self.assertNotEqual(semdeps.tree_hash(tmp_a), semdeps.tree_hash(tmp_b))

    def test_sha256_bytes(self):
        self.assertEqual(len(semdeps.sha256_bytes(b"hi")), 64)


class ExtractTests(unittest.TestCase):
    def test_targz_strips_top_level(self):
        dest = tempfile.mkdtemp()
        data = _make_targz({"main.sem": "operation main\n", "sub/x.sem": "operation x\n"})
        semdeps._extract_archive(data, dest, strip_top_level=True)
        self.assertTrue(os.path.isfile(os.path.join(dest, "main.sem")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "sub", "x.sem")))

    def test_zip_extracts(self):
        dest = tempfile.mkdtemp()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("pkg/main.sem", "operation main\n")
        semdeps._extract_archive(buffer.getvalue(), dest, strip_top_level=True)
        self.assertTrue(os.path.isfile(os.path.join(dest, "main.sem")))

    def test_path_traversal_member_is_rejected(self):
        dest = tempfile.mkdtemp()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            payload = b"x"
            info = tarfile.TarInfo(name="pkg/../../escape.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        with self.assertRaises(semdeps.DependencyError):
            semdeps._extract_archive(buffer.getvalue(), dest, strip_top_level=True)

    def test_symlink_member_is_rejected(self):
        dest = tempfile.mkdtemp()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(name="pkg/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
        with self.assertRaises(semdeps.DependencyError):
            semdeps._extract_archive(buffer.getvalue(), dest, strip_top_level=True)

    def test_hardlink_member_is_rejected(self):
        dest = tempfile.mkdtemp()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(name="pkg/hard")
            info.type = tarfile.LNKTYPE
            info.linkname = "main.sem"
            archive.addfile(info)
        with self.assertRaises(semdeps.DependencyError):
            semdeps._extract_archive(buffer.getvalue(), dest, strip_top_level=True)

    def test_leading_slash_is_neutralized_not_absolute(self):
        # A leading-slash member is stripped to a relative path inside dest.
        self.assertEqual(semdeps._strip("/etc/passwd", strip_top_level=False), "etc/passwd")

    def test_absolute_member_that_escapes_after_strip_is_rejected(self):
        dest = tempfile.mkdtemp()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            payload = b"x\n"
            info = tarfile.TarInfo(name="pkg//etc/passwd")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        with self.assertRaises(semdeps.DependencyError):
            semdeps._extract_archive(buffer.getvalue(), dest, strip_top_level=True)

    def test_windows_reserved_name_is_rejected(self):
        dest = tempfile.mkdtemp()
        data = _make_targz({"CON": "x\n"})
        with self.assertRaises(semdeps.DependencyError):
            semdeps._extract_archive(data, dest, strip_top_level=True)

    def test_decompression_bomb_guard(self):
        with self.assertRaises(semdeps.DependencyError):
            semdeps._guard_extracted_size(0, semdeps._MAX_EXTRACTED_BYTES + 1, "big")

    def test_https_only_redirect_handler_rejects_http(self):
        handler = semdeps._HttpsOnlyRedirectHandler()
        with self.assertRaises(semdeps.DependencyError):
            handler.redirect_request(None, None, 302, "", {}, "http://evil.example/x")

    def test_public_url_guard_blocks_internal_addresses(self):
        for bad in ("https://127.0.0.1/x", "https://169.254.169.254/latest/meta-data",
                    "https://10.0.0.5/pkg.tar.gz", "https://[::1]/x", "https://192.168.1.1/x"):
            with self.assertRaises(semdeps.DependencyError):
                semdeps._assert_public_url(bad)

    def test_public_url_guard_blocks_internal_redirect(self):
        handler = semdeps._HttpsOnlyRedirectHandler()
        with self.assertRaises(semdeps.DependencyError):
            handler.redirect_request(None, None, 302, "", {}, "https://169.254.169.254/x")


class MaterializePathTests(unittest.TestCase):
    def _project_with_path_dep(self):
        root = tempfile.mkdtemp()
        dep = os.path.join(root, "packages", "greet")
        _write(os.path.join(dep, "main.sem"), "module greet\noperation greetMain\n")
        build = os.path.join(root, "app", "build.sem")
        body = (
            "buildProject app\n"
            "dependency app greet example.com/greet v0.1.0\n"
            "dependencySource app greet path \"../packages/greet\"\n"
        )
        _write(build, body)
        return semdeps.parse_build_sem(body, build), root

    def test_path_dependency_materializes_and_pins(self):
        config, _ = self._project_with_path_dep()
        resolved = semdeps.materialize(config.specs[0], config, allow_network=False)
        self.assertTrue(os.path.isfile(os.path.join(resolved.cache_dir, "main.sem")))
        self.assertTrue(resolved.lock_entry.integrity.startswith("sha256:"))
        self.assertEqual(resolved.lock_entry.module_path, "example.com/greet")

    def test_sync_writes_lock_and_verify_passes(self):
        config, _ = self._project_with_path_dep()
        semdeps.sync(config, allow_network=False)
        self.assertTrue(os.path.isfile(config.lock_path))
        results = semdeps.verify(config)
        self.assertEqual(results, [("greet", True, "ok")])

    def test_verify_detects_cache_tamper(self):
        config, _ = self._project_with_path_dep()
        semdeps.sync(config, allow_network=False)
        cache_dir = os.path.join(config.cache_dir, semdeps.cache_subdir(config.specs[0]))
        _write(os.path.join(cache_dir, "main.sem"), "module greet\noperation tampered\n")
        results = semdeps.verify(config)
        self.assertFalse(results[0][1])

    def test_resync_replaces_existing_cache_atomically(self):
        config, root = self._project_with_path_dep()
        semdeps.sync(config, allow_network=False)
        cache_dir = semdeps.cache_dir_for(config, config.specs[0])
        first = semdeps.tree_hash(cache_dir)
        _write(os.path.join(root, "packages", "greet", "main.sem"),
               "module greet\noperation greetMain\noperation extra\n")
        resolved = semdeps.sync(config, allow_network=False)
        self.assertNotEqual(semdeps.tree_hash(cache_dir), first)
        self.assertTrue(os.path.isfile(os.path.join(cache_dir, "main.sem")))
        # No leftover swap-aside directories in the cache parent.
        leftovers = [n for n in os.listdir(os.path.dirname(cache_dir))
                     if "semdeps-old" in n or "semdeps-tmp" in n]
        self.assertEqual(leftovers, [])

    def test_registry_maps_declared_module_path(self):
        config, _ = self._project_with_path_dep()
        semdeps.sync(config, allow_network=False)
        registry = semdeps.dependency_module_registry(config)
        self.assertIn("example.com/greet", registry)
        self.assertTrue(registry["example.com/greet"].endswith("main.sem"))

    def test_registry_requires_sync(self):
        config, _ = self._project_with_path_dep()
        with self.assertRaises(semdeps.DependencyError):
            semdeps.dependency_module_registry(config)

    def test_verify_detects_build_sem_version_drift(self):
        config, root = self._project_with_path_dep()
        semdeps.sync(config, allow_network=False)
        drifted_body = (
            "buildProject app\n"
            "dependency app greet example.com/greet v0.2.0\n"
            "dependencySource app greet path \"../packages/greet\"\n")
        drifted = semdeps.parse_build_sem(drifted_body, config.build_sem_path)
        results = semdeps.verify(drifted)
        self.assertFalse(results[0][1])
        self.assertIn("drift", results[0][2])


class MaterializeNetworkTests(unittest.TestCase):
    def setUp(self):
        # Isolate the shared cache to a temp dir so github materialization never
        # writes into the real per-user cache (%LOCALAPPDATA%/XDG).
        self._prev_cache = os.environ.get("SEMANTICSCRIPT_CACHE")
        cache = tempfile.mkdtemp()
        os.environ["SEMANTICSCRIPT_CACHE"] = cache
        self.addCleanup(shutil.rmtree, cache, ignore_errors=True)

    def tearDown(self):
        if self._prev_cache is None:
            os.environ.pop("SEMANTICSCRIPT_CACHE", None)
        else:
            os.environ["SEMANTICSCRIPT_CACHE"] = self._prev_cache

    def _github_config(self, integrity_sha: str):
        root = tempfile.mkdtemp()
        build = os.path.join(root, "build.sem")
        body = (
            "buildProject demo\n"
            "dependency demo semstd github.com/example/semstd v1.0.0\n"
            "dependencyFetch demo semstd github example/semstd v1.0.0\n"
            f"dependencyIntegrity demo semstd sha256:{integrity_sha}\n"
        )
        _write(build, body)
        return semdeps.parse_build_sem(body, build)

    def test_github_fetch_verifies_integrity(self):
        archive = _make_targz({"main.sem": "module semstd\noperation semstdMain\n",
                               "build.sem": "buildProject semstd\nmodulePath semstd github.com/example/semstd\n"})
        sha = semdeps.sha256_bytes(archive)
        config = self._github_config(sha)
        captured = {}

        def fake_download(url):
            captured["url"] = url
            return archive

        resolved = semdeps.materialize(config.specs[0], config,
                                       allow_network=True, downloader=fake_download)
        self.assertEqual(captured["url"],
                         "https://codeload.github.com/example/semstd/tar.gz/v1.0.0")
        self.assertTrue(os.path.isfile(os.path.join(resolved.cache_dir, "main.sem")))
        self.assertEqual(resolved.lock_entry.integrity, f"sha256:{sha}")

    def test_github_fetch_rejects_integrity_mismatch(self):
        archive = _make_targz({"main.sem": "module semstd\n"})
        config = self._github_config("b" * 64)
        with self.assertRaises(semdeps.DependencyError):
            semdeps.materialize(config.specs[0], config, allow_network=True,
                                downloader=lambda url: archive)

    def test_network_fetch_blocked_when_offline(self):
        config = self._github_config("c" * 64)
        with self.assertRaises(semdeps.DependencyError):
            semdeps.materialize(config.specs[0], config, allow_network=False,
                                downloader=lambda url: b"")

    def _github_config_no_pin(self):
        root = tempfile.mkdtemp()
        build = os.path.join(root, "build.sem")
        body = ("buildProject demo\n"
                "dependency demo semstd github.com/example/semstd v1.0.0\n"
                "dependencyFetch demo semstd github example/semstd v1.0.0\n")
        _write(build, body)
        return semdeps.parse_build_sem(body, build)

    def test_sync_is_idempotent_and_skips_network(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            archive = _make_targz({"main.sem": "module semstd\n"})
            config = self._github_config(semdeps.sha256_bytes(archive))
            calls = {"n": 0}

            def counting(url):
                calls["n"] += 1
                return archive

            semdeps.sync(config, downloader=counting)
            second = semdeps.sync(config, downloader=counting)
            self.assertEqual(calls["n"], 1)
            self.assertTrue(second[0].from_cache)
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_unpinned_fetch_is_tofu_then_lock_pins(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            archive = _make_targz({"main.sem": "module semstd\n"})
            config = self._github_config_no_pin()
            resolved = semdeps.sync(config, downloader=lambda url: archive)
            self.assertTrue(any("trust-on-first-use" in w for w in resolved[0].warnings))
            # Fresh machine (cache cleared) + upstream bytes changed -> lock guard fires.
            import shutil
            shutil.rmtree(semdeps.cache_dir_for(config, config.specs[0]))
            changed = _make_targz({"main.sem": "module semstdChanged\n"})
            with self.assertRaises(semdeps.DependencyError):
                semdeps.sync(config, downloader=lambda url: changed)
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_resync_with_changed_version_updates_lock_not_permanent_drift(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            archive = _make_targz({"main.sem": "module semstd\n"})
            sha = semdeps.sha256_bytes(archive)
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            first_body = ("buildProject demo\n"
                          "dependency demo semstd github.com/example/semstd v1.0.0\n"
                          "dependencyFetch demo semstd github example/semstd v1.0.0\n"
                          f"dependencyIntegrity demo semstd sha256:{sha}\n")
            _write(build, first_body)
            semdeps.sync(semdeps.parse_build_sem(first_body, build),
                         downloader=lambda u: archive)
            # Bump only the dependency version; ref/content unchanged.
            second_body = ("buildProject demo\n"
                           "dependency demo semstd github.com/example/semstd v1.1.0\n"
                           "dependencyFetch demo semstd github example/semstd v1.0.0\n"
                           f"dependencyIntegrity demo semstd sha256:{sha}\n")
            _write(build, second_body)
            config = semdeps.parse_build_sem(second_body, build)
            resolved = semdeps.sync(config, downloader=lambda u: archive)
            self.assertTrue(resolved[0].from_cache)
            self.assertEqual(resolved[0].lock_entry.version, "v1.1.0")
            self.assertEqual(semdeps.verify(config), [("semstd", True, "ok")])
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_verify_fails_for_fetched_entry_without_content_hash(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            archive = _make_targz({"main.sem": "module semstd\n"})
            config = self._github_config(semdeps.sha256_bytes(archive))
            semdeps.sync(config, downloader=lambda u: archive)
            # Simulate a legacy/hand-edited lock that lacks contentHash.
            import json
            with open(config.lock_path, encoding="utf-8") as handle:
                data = json.load(handle)
            for row in data["dependencies"]:
                row["contentHash"] = ""
            with open(config.lock_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            results = semdeps.verify(config)
            self.assertFalse(results[0][1])
            self.assertIn("contentHash", results[0][2])
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_commit_pin_emits_advisory_warning(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            body = ("buildProject demo\n"
                    "dependency demo semstd github.com/example/semstd v1.0.0\n"
                    "dependencyFetch demo semstd github example/semstd v1.0.0\n"
                    f"dependencyIntegrity demo semstd commit:{'a' * 40}\n")
            _write(build, body)
            config = semdeps.parse_build_sem(body, build)
            archive = _make_targz({"main.sem": "module semstd\n"})
            resolved = semdeps.sync(config, downloader=lambda url: archive)
            self.assertTrue(any("commit:" in w for w in resolved[0].warnings))
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]


class CacheRoutingTests(unittest.TestCase):
    def _github_spec(self, ref: str):
        return semdeps.DependencySpec(
            alias="semstd", module_path="github.com/example/semstd",
            source_kind="github", source_payload=("example/semstd", ref))

    def test_versions_coexist_in_distinct_cache_dirs(self):
        v1 = semdeps.cache_subdir(self._github_spec("v1.0.0"))
        v2 = semdeps.cache_subdir(self._github_spec("v2.0.0"))
        self.assertNotEqual(v1, v2)
        self.assertTrue(v1.endswith("v1.0.0"))
        self.assertTrue(v2.endswith("v2.0.0"))

    def test_fetched_dep_uses_shared_cache_when_set(self):
        shared = tempfile.mkdtemp()
        os.environ["SEMANTICSCRIPT_CACHE"] = shared
        try:
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            body = ("buildProject demo\n"
                    "dependency demo semstd github.com/example/semstd v1.0.0\n"
                    "dependencyFetch demo semstd github example/semstd v1.0.0\n")
            _write(build, body)
            config = semdeps.parse_build_sem(body, build)
            target = semdeps.cache_dir_for(config, config.specs[0])
            self.assertTrue(target.startswith(os.path.abspath(shared)))
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_explicit_cache_row_keeps_fetched_dep_local(self):
        shared = tempfile.mkdtemp()
        os.environ["SEMANTICSCRIPT_CACHE"] = shared
        try:
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            body = ("buildProject demo\n"
                    "dependency demo semstd github.com/example/semstd v1.0.0\n"
                    "dependencyFetch demo semstd github example/semstd v1.0.0\n"
                    "dependencyCache demo \".semcache\"\n")
            _write(build, body)
            config = semdeps.parse_build_sem(body, build)
            target = semdeps.cache_dir_for(config, config.specs[0])
            self.assertTrue(target.startswith(os.path.abspath(root)))
            self.assertFalse(target.startswith(os.path.abspath(shared)))
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_path_dep_ignores_shared_cache(self):
        shared = tempfile.mkdtemp()
        os.environ["SEMANTICSCRIPT_CACHE"] = shared
        try:
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            body = ("buildProject demo\n"
                    "dependency demo greet example.com/greet v0.1.0\n"
                    "dependencySource demo greet path \"../greet\"\n")
            _write(build, body)
            config = semdeps.parse_build_sem(body, build)
            target = semdeps.cache_dir_for(config, config.specs[0])
            self.assertTrue(target.startswith(os.path.abspath(root)))
            self.assertFalse(target.startswith(os.path.abspath(shared)))
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]


class LockRoundTripTests(unittest.TestCase):
    def test_read_lock_rejects_wrong_schema(self):
        root = tempfile.mkdtemp()
        build = os.path.join(root, "build.sem")
        body = "buildProject demo\n"
        _write(build, body)
        config = semdeps.parse_build_sem(body, build)
        _write(config.lock_path, '{"schemaVersion": "sem.lock.v0"}')
        with self.assertRaises(semdeps.DependencyError):
            semdeps.read_lock(config)


class ImportBridgeTests(unittest.TestCase):
    """Drive the bridge through the compiler's real import resolver. These fail
    under a no-op bridge: without the merge, the dependency module path never
    resolves and the inlined source never contains the dependency operation."""

    def _project(self):
        root = tempfile.mkdtemp()
        dep = os.path.join(root, "packages", "greet")
        _write(os.path.join(dep, "main.sem"),
               "module greet\noperation greetWorld\n"
               "purpose operation greetWorld \"Return a greeting marker.\"\n")
        build = os.path.join(root, "app", "build.sem")
        body = (
            "buildProject app\n"
            "dependency app greet example.com/greet v0.1.0\n"
            "dependencySource app greet path \"../packages/greet\"\n"
            "import greet example.com/greet\n"
        )
        _write(build, body)
        return body, build

    def test_import_resolves_after_sync(self):
        import semsc
        body, build = self._project()
        config = semdeps.parse_build_sem(body, build)
        semdeps.sync(config, allow_network=False)
        inlined = semsc._resolve_imports(body, build)
        self.assertIn("greetWorld", inlined)

    def test_import_without_sync_raises_actionable_error(self):
        import semsc
        body, build = self._project()
        with self.assertRaises(SyntaxError) as ctx:
            semsc._resolve_imports(body, build)
        self.assertIn("sem deps sync", str(ctx.exception))

    def test_regular_source_without_deps_is_unaffected(self):
        import semsc
        root = tempfile.mkdtemp()
        plain = os.path.join(root, "plain.sem")
        _write(plain, "operation main\npurpose operation main \"noop\"\n")
        inlined = semsc._resolve_imports("operation main\n", plain)
        self.assertIn("operation main", inlined)


class CliPayloadTests(unittest.TestCase):
    """Exercise the `sem deps` payload builder directly so the CLI surface
    (sem.deps.v1) is covered without spawning subprocesses."""

    def _load_sem(self):
        tools = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for path in (tools, root):
            if path not in sys.path:
                sys.path.insert(0, path)
        import sem
        return sem

    def _project(self):
        root = tempfile.mkdtemp()
        dep = os.path.join(root, "packages", "greet")
        _write(os.path.join(dep, "main.sem"), "module greet\noperation greetWorld\n")
        app = os.path.join(root, "app")
        _write(os.path.join(app, "build.sem"),
               "buildProject app\n"
               "dependency app greet example.com/greet v0.1.0\n"
               "dependencySource app greet path \"../packages/greet\"\n")
        return app

    def test_list_then_sync_then_verify(self):
        from pathlib import Path
        sem = self._load_sem()
        app = self._project()
        listing = sem._deps_payload(Path(app), "list", allow_network=False)
        self.assertEqual(listing["schemaVersion"], "sem.deps.v1")
        self.assertEqual(listing["status"], "pending")
        synced = sem._deps_payload(Path(app), "sync", allow_network=False)
        self.assertTrue(synced["ok"])
        self.assertEqual(synced["dependencies"][0]["status"], "synced")
        verified = sem._deps_payload(Path(app), "verify", allow_network=False)
        self.assertTrue(verified["ok"])
        self.assertEqual(verified["status"], "verified")

    def test_no_build_tape_reports_actionable_status(self):
        from pathlib import Path
        sem = self._load_sem()
        empty = tempfile.mkdtemp()
        payload = sem._deps_payload(Path(empty), "list", allow_network=False)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no-build-tape")

    def test_corrupt_lock_returns_error_payload_not_crash(self):
        from pathlib import Path
        sem = self._load_sem()
        app = self._project()
        sem._deps_payload(Path(app), "sync", allow_network=False)
        _write(os.path.join(app, "sem.lock"), "{ broken json")
        payload = sem._deps_payload(Path(app), "verify", allow_network=False)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error")
        self.assertIn("sem.lock", payload["error"])

    def test_cache_action_inventories_packages(self):
        from pathlib import Path
        sem = self._load_sem()
        app = self._project()
        sem._deps_payload(Path(app), "sync", allow_network=False)
        payload = sem._deps_payload(Path(app), "cache", allow_network=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertIn("cached", payload)

    def test_purge_action_removes_cache(self):
        from pathlib import Path
        sem = self._load_sem()
        app = self._project()
        sem._deps_payload(Path(app), "sync", allow_network=False)
        payload = sem._deps_payload(Path(app), "purge", allow_network=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "purged")
        self.assertTrue(payload["removed"])


class CrudAndHardeningTests(unittest.TestCase):
    def _path_dep_project(self, package_build=""):
        root = tempfile.mkdtemp()
        dep = os.path.join(root, "packages", "greet")
        _write(os.path.join(dep, "main.sem"), "module greet\noperation greetMain\n")
        if package_build:
            _write(os.path.join(dep, "build.sem"), package_build)
        build = os.path.join(root, "app", "build.sem")
        body = ("buildProject app\n"
                "dependency app greet example.com/greet v0.1.0\n"
                "dependencySource app greet path \"../packages/greet\"\n")
        _write(build, body)
        return semdeps.parse_build_sem(body, build), root

    def test_cache_escape_via_package_registermodule_is_rejected(self):
        # A fetched/copied package's own build.sem is untrusted: a registerModule
        # pointing outside the cache dir must be refused, not inlined.
        malicious = ("buildProject greet\n"
                     "modulePath greet example.com/greet\n"
                     "registerModule greet example.com/greet/evil \"../../../../etc\"\n")
        config, _ = self._path_dep_project(package_build=malicious)
        semdeps.sync(config, allow_network=False)
        with self.assertRaises(semdeps.DependencyError):
            semdeps.dependency_module_registry(config)

    def test_corrupt_lock_raises_dependency_error(self):
        config, _ = self._path_dep_project()
        _write(config.lock_path, "{ this is not valid json ]")
        with self.assertRaises(semdeps.DependencyError):
            semdeps.read_lock(config)

    def test_force_resync_refetches(self):
        os.environ["SEMANTICSCRIPT_CACHE"] = tempfile.mkdtemp()
        try:
            archive = _make_targz({"main.sem": "module semstd\n"})
            sha = semdeps.sha256_bytes(archive)
            root = tempfile.mkdtemp()
            build = os.path.join(root, "build.sem")
            body = ("buildProject demo\n"
                    "dependency demo semstd github.com/example/semstd v1.0.0\n"
                    "dependencyFetch demo semstd github example/semstd v1.0.0\n"
                    f"dependencyIntegrity demo semstd sha256:{sha}\n")
            _write(build, body)
            config = semdeps.parse_build_sem(body, build)
            calls = {"n": 0}

            def counting(url):
                calls["n"] += 1
                return archive

            semdeps.sync(config, downloader=counting)
            semdeps.sync(config, downloader=counting)          # idempotent: no refetch
            self.assertEqual(calls["n"], 1)
            semdeps.sync(config, downloader=counting, force=True)  # forced refetch
            self.assertEqual(calls["n"], 2)
        finally:
            del os.environ["SEMANTICSCRIPT_CACHE"]

    def test_purge_removes_cache_and_optionally_lock(self):
        config, _ = self._path_dep_project()
        semdeps.sync(config, allow_network=False)
        cache_dir = semdeps.cache_dir_for(config, config.specs[0])
        self.assertTrue(os.path.isdir(cache_dir))
        removed = semdeps.purge(config)
        self.assertIn(cache_dir, removed)
        self.assertFalse(os.path.isdir(cache_dir))
        self.assertTrue(os.path.isfile(config.lock_path))  # lock kept by default
        semdeps.sync(config, allow_network=False)
        removed2 = semdeps.purge(config, remove_lock=True)
        self.assertIn(config.lock_path, removed2)
        self.assertFalse(os.path.isfile(config.lock_path))

    def test_list_cached_packages_inventory(self):
        config, _ = self._path_dep_project()
        semdeps.sync(config, allow_network=False)
        entries = semdeps.list_cached_packages([("project", config.cache_dir)])
        self.assertTrue(entries)
        entry = entries[0]
        self.assertEqual(entry["sourceKind"], "path")
        self.assertGreaterEqual(entry["fileCount"], 1)
        self.assertEqual(entry["scope"], "project")


@unittest.skipUnless(
    os.environ.get("SEMANTICSCRIPT_NETWORK_TESTS"),
    "live network test; set SEMANTICSCRIPT_NETWORK_TESTS=1 to run")
class LiveNetworkTests(unittest.TestCase):
    """Exercises the real urllib transfer against a tiny, immutable public
    GitHub repo. Skipped by default so offline CI stays deterministic; opt in
    with SEMANTICSCRIPT_NETWORK_TESTS=1.

    Skip discipline: ONLY `semdeps.NetworkError` (DNS/TLS/HTTP/timeout) is
    treated as "network unavailable". Integrity, extraction, and policy failures
    raise plain `DependencyError`, which is NOT caught here — a real regression
    in fetch/verify/extract fails loudly instead of green-skipping.

    Determinism: assertions check the extracted file *content* (stable for an
    immutable commit), never the archive's byte-level sha256 — GitHub does not
    guarantee codeload tarballs are byte-reproducible over time.
    """

    # octocat/Hello-World pinned to an immutable commit (tiny, stable repo).
    OWNER_REPO = "octocat/Hello-World"
    COMMIT = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"

    def setUp(self):
        self._prev_cache = os.environ.get("SEMANTICSCRIPT_CACHE")
        cache = tempfile.mkdtemp()
        os.environ["SEMANTICSCRIPT_CACHE"] = cache
        self.addCleanup(shutil.rmtree, cache, ignore_errors=True)

    def tearDown(self):
        if self._prev_cache is None:
            os.environ.pop("SEMANTICSCRIPT_CACHE", None)
        else:
            os.environ["SEMANTICSCRIPT_CACHE"] = self._prev_cache

    def _config(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        build = os.path.join(root, "build.sem")
        body = (
            "buildProject demo\n"
            f"dependency demo hello github.com/{self.OWNER_REPO} {self.COMMIT}\n"
            f"dependencyFetch demo hello github {self.OWNER_REPO} {self.COMMIT}\n")
        _write(build, body)
        return semdeps.parse_build_sem(body, build)

    def _readme_text(self, cache_dir):
        for name in os.listdir(cache_dir):
            if name.lower().startswith("readme"):
                with open(os.path.join(cache_dir, name), encoding="utf-8") as handle:
                    return handle.read()
        self.fail(f"expected a README in the extracted package; found {os.listdir(cache_dir)}")

    def test_default_download_fetches_real_tarball(self):
        url = semdeps._github_tarball_url(self.OWNER_REPO, self.COMMIT)
        try:
            data = semdeps._default_download(url)
        except semdeps.NetworkError as exc:
            self.skipTest(f"network unavailable: {exc}")
        self.assertGreater(len(data), 0)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            self.assertTrue(archive.getnames())

    def test_github_dependency_syncs_over_real_network(self):
        config = self._config()
        try:
            resolved = semdeps.sync(config)  # real _default_download
        except semdeps.NetworkError as exc:
            self.skipTest(f"network unavailable: {exc}")
        entry = resolved[0].lock_entry
        # Lock consistency: integrity anchors the resolved archive digest, and
        # contentHash matches the actually-extracted tree.
        self.assertEqual(entry.integrity, f"sha256:{entry.resolved}")
        self.assertEqual(entry.content_hash, semdeps.tree_hash(resolved[0].cache_dir))
        # Content-level proof the right bytes were fetched + extracted.
        self.assertIn("Hello World", self._readme_text(resolved[0].cache_dir))
        self.assertEqual(semdeps.verify(config), [("hello", True, "ok")])

    def test_real_sync_is_idempotent_without_refetch(self):
        config = self._config()
        try:
            semdeps.sync(config)
        except semdeps.NetworkError as exc:
            self.skipTest(f"network unavailable: {exc}")

        def must_not_fetch(url):
            raise AssertionError("idempotent re-sync attempted a network fetch")

        again = semdeps.sync(config, downloader=must_not_fetch)
        self.assertTrue(again[0].from_cache)


if __name__ == "__main__":
    unittest.main()
