"""Golden-assertion tests for semlint.

Each test writes a small .sscript fixture to a temp file, runs the linter, and
asserts on the structured diagnostic codes + kinds produced. Following the
project rule: never promote a checker without a test that would fail under
no-op lowering.

Run from repo root: `python -m unittest SemanticScript/linter/test_semlint.py -v`
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Sequence

_LINTER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
if _LINTER_DIRECTORY not in sys.path:
    sys.path.insert(0, _LINTER_DIRECTORY)

import semlint  # noqa: E402


def _lint_source(sourceText: str) -> List[semlint.Diagnostic]:
    with TemporaryDirectory() as tempDir:
        fixturePath = Path(tempDir) / "fixture.sscript"
        fixturePath.write_text(sourceText, encoding="utf-8")
        return semlint.lint_path(fixturePath)


def _lint_source_at(relativePath: str, sourceText: str) -> List[semlint.Diagnostic]:
    with TemporaryDirectory() as tempDir:
        fixturePath = Path(tempDir) / relativePath
        fixturePath.parent.mkdir(parents=True, exist_ok=True)
        fixturePath.write_text(sourceText, encoding="utf-8")
        return semlint.lint_path(fixturePath)


def _codes(diagnostics: Sequence[semlint.Diagnostic]) -> List[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def _diagnostics_with_code(
    diagnostics: Sequence[semlint.Diagnostic],
    code: str,
) -> List[semlint.Diagnostic]:
    return [diagnostic for diagnostic in diagnostics if diagnostic.code == code]


# ==========================================================================
# SS0101  unusedDeclaration.call
# ==========================================================================

class TestUnusedCalls(unittest.TestCase):
    def test_unused_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call unusedCallSite console.writeLine
""")
        self.assertIn("SS0101", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0101")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unusedCallSite")
        self.assertEqual(matchingDiagnostic.subjectKind, "call")
        self.assertEqual(matchingDiagnostic.gapEdge, "executionSite")

    def test_run_call_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
run writeLineCall
""")
        self.assertNotIn("SS0101", _codes(diagnostics))

    def test_collect_paths_accepts_sem_alias(self) -> None:
        with TemporaryDirectory() as tempDir:
            fixturePath = Path(tempDir) / "fixture.sem"
            fixturePath.write_text("project Alias\n", encoding="utf-8")
            self.assertEqual(semlint.collect_paths([str(fixturePath)]), [fixturePath])

    def test_collect_paths_skips_sem_suffix_directories(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            semDirectory = root / ".sem"
            semDirectory.mkdir()
            fixturePath = root / "fixture.sem"
            fixturePath.write_text("project Alias\n", encoding="utf-8")

            self.assertEqual(semlint.collect_paths([str(root)]), [fixturePath])


# ==========================================================================
# SS0102  unusedDeclaration.label   (entry-anchor convention suppressed)
# ==========================================================================

class TestUnusedLabels(unittest.TestCase):
    def test_orphan_label_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label notAnEntryAnchor
""")
        self.assertIn("SS0102", _codes(diagnostics))

    def test_entry_anchor_pattern_is_suppressed(self) -> None:
        # The stdlib convention `label start<OperationName>` at the top of a
        # body is a readability anchor; treating it as unused causes a
        # 213-occurrence false-positive storm across std.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label startMain
""")
        self.assertNotIn("SS0102", _codes(diagnostics))


# ==========================================================================
# SS3630  controlFlow.unreachableRow
# ==========================================================================

class TestUnreachableOperationRows(unittest.TestCase):
    def test_label_after_unconditional_return_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main ExitCode
purpose main "smoke"
storage module immutable success ExitCode 0
storage module immutable failure ExitCode 1
return value success
label stalePath
return value failure
""")
        self.assertIn("SS3630", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3630")[0]
        self.assertEqual(matchingDiagnostic.kind, "controlFlow.unreachableRow")
        self.assertEqual(matchingDiagnostic.subjectName, "stalePath")

    def test_failure_label_reached_by_branch_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main ExitCode
purpose main "smoke"
storage module immutable success ExitCode 0
storage module immutable failure ExitCode 1
call riskyCall runtime.risky
run riskyCall
bind error riskyError RuntimeError riskyCall
branch error source riskyCall target failed
return value success
label failed
return value failure
""")
        self.assertNotIn("SS3630", _codes(diagnostics))

    def test_attached_branch_else_row_is_not_flagged(self) -> None:
        # The idiomatic two-line conditional: `branch if ... target L1` followed
        # by `branch else target L2`. The CFG model consumes the else row as the
        # branch-if's else edge, so it never lands in the reachable set — but it
        # is a live edge, not stale unreachable code, and must not flag SS3630.
        diagnostics = _lint_source("""project Test
operation main
output main ExitCode
purpose main "smoke"
invariant main "idiomatic two-line conditional must not flag the else row"
storage local immutable threshold Int64 5
storage local immutable probe Int64 3
storage module immutable lowExit ExitCode 0
storage module immutable highExit ExitCode 1
call condCall math.lessThanInt64
arg condCall left probe
arg condCall right threshold
run condCall
bind value cond Bool condCall
branch if condition cond target lowPath
branch else target highPath
label lowPath
return value lowExit
label highPath
return value highExit
""")
        self.assertNotIn("SS3630", _codes(diagnostics))

    def test_top_level_import_after_operation_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main ExitCode
purpose main "smoke"
storage local immutable success ExitCode 0
return value success
import pages app.example.pages
""")
        self.assertNotIn("SS3630", _codes(diagnostics))

    def test_wait_set_case_rows_are_not_unreachable_rows(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main ExitCode
purpose main "smoke"
label waitNextFetch
await nextFetch
case healthFetchCall printHealthResponse
done allFetchesPrinted
label printHealthResponse
jump target waitNextFetch
label allFetchesPrinted
storage local immutable success ExitCode 0
return value success
""")
        self.assertNotIn("SS3630", _codes(diagnostics))


# ==========================================================================
# SS0103  unusedDeclaration.capability
# ==========================================================================

class TestUnusedCapabilities(unittest.TestCase):
    def test_dangling_capability_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
""")
        self.assertIn("SS0103", _codes(diagnostics))

    def test_used_capability_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
operation main
output main Void
purpose main "smoke"
useCapability main consoleCap
""")
        self.assertNotIn("SS0103", _codes(diagnostics))


# ==========================================================================
# SS0104  unusedDeclaration.errorCase
# ==========================================================================

class TestUnusedErrorCases(unittest.TestCase):
    def test_unused_variant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError NeverRaisedVariant
""")
        self.assertIn("SS0104", _codes(diagnostics))

    def test_raised_variant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError ConfiguredFailure
operation main
output main Result Void MainError
purpose main "smoke"
makeError mainFailure MainError.ConfiguredFailure
returnError mainFailure
""")
        self.assertNotIn("SS0104", _codes(diagnostics))


# ==========================================================================
# semlint-allow  — per-line advisory suppression with rationale
# ==========================================================================

class TestLintSuppression(unittest.TestCase):
    BASE = """project Test
error MainError
errorCase MainError NeverRaisedVariant
"""

    def test_allow_suppresses_targeted_advisory(self) -> None:
        # The unused errorCase is SS0104 (a non-blocking advisory); a
        # semlint-allow with rationale on the line above removes it.
        annotated = """project Test
error MainError
# semlint-allow SS0104: variant reserved for an upcoming failure path
errorCase MainError NeverRaisedVariant
"""
        self.assertIn("SS0104", _codes(_lint_source(self.BASE)))
        self.assertNotIn("SS0104", _codes(_lint_source(annotated)))

    def test_allow_requires_a_rationale(self) -> None:
        # No rationale → annotation is ignored, so the advisory still fires
        # (a forgotten reason must never silently hide a finding).
        no_rationale = """project Test
error MainError
# semlint-allow SS0104
errorCase MainError NeverRaisedVariant
"""
        self.assertIn("SS0104", _codes(_lint_source(no_rationale)))

    def test_allow_only_affects_the_named_code(self) -> None:
        # Suppressing a different code (SS3104, which does not fire here) leaves
        # SS0104 in place — an allow is scoped to exactly its named code.
        other_code = """project Test
error MainError
# semlint-allow SS3104: unrelated code does not suppress SS0104
errorCase MainError NeverRaisedVariant
"""
        self.assertIn("SS0104", _codes(_lint_source(other_code)))

    def test_allow_cannot_suppress_compile_blocking_diagnostic(self) -> None:
        # Duplicate export is a compile-blocking error (SS2507). semlint-allow
        # must NOT be able to hide it — only advisories are suppressible.
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject blk
registerModule blk app.todo "."
mainFile blk "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
# semlint-allow SS2507: attempting (and required to fail) to hide a real error
exportOperation app.todo main
exportOperation app.todo main
operation main
output main Void
purpose main "smoke"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2507", _codes(diagnostics))

    def test_allow_mixed_with_advisory_still_cannot_hide_blocker(self) -> None:
        annotated = """project Test
error MainError
# semlint-allow SS0104: variant reserved for an upcoming failure path
errorCase MainError NeverRaisedVariant
operation main
# semlint-allow SS0003: old output form is intentionally still an error
output main Void
purpose operation main "smoke"
return void
"""
        codes = _codes(_lint_source(annotated))
        self.assertNotIn("SS0104", codes)
        self.assertIn("SS0003", codes)


# ==========================================================================
# SS0105  unusedDeclaration.mutableStorage
# ==========================================================================

class TestUnusedMutableStorage(unittest.TestCase):
    def test_never_set_mutable_module_storage_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision Int64 zeroCount
""")
        self.assertIn("SS0105", _codes(diagnostics))

    def test_immutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable attemptLimit Int64 fiveAttemptCount
""")
        self.assertNotIn("SS0105", _codes(diagnostics))

    def test_set_mutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision Int64 zeroCount
operation main
output main Void
purpose main "smoke"
set module accountLookupRevision nextAccountLookupRevision
""")
        self.assertNotIn("SS0105", _codes(diagnostics))


# ==========================================================================
# SS1201  partiallyDeclared.retryPolicy
# ==========================================================================

class TestPartialRetryPolicy(unittest.TestCase):
    def test_policy_missing_max_attempts_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
retryPolicy networkRetryPolicy
""")
        self.assertIn("SS1201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS1201")[0]
        self.assertIn("retryMaxAttempts", matchingDiagnostic.gapEdge)

    def test_complete_policy_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
retryPolicy networkRetryPolicy
retryMaxAttempts networkRetryPolicy 5
retryInitialDelay networkRetryPolicy 100ms
retryMaximumDelay networkRetryPolicy 5s
retryJitter networkRetryPolicy yes
""")
        self.assertNotIn("SS1201", _codes(diagnostics))


# ==========================================================================
# SS1202  partiallyDeclared.trustBoundary
# ==========================================================================

class TestPartialTrustBoundary(unittest.TestCase):
    def test_missing_triad_member_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
trustBoundary AccountToken
trustBoundaryInput AccountToken RawAccountToken
""")
        self.assertIn("SS1202", _codes(diagnostics))

    def test_complete_triad_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
trustBoundary AccountToken
trustBoundaryInput AccountToken RawAccountToken
trustBoundaryOutput AccountToken TrustedAccountToken
trustBoundaryValidator AccountToken validateAccountTokenStructure
""")
        self.assertNotIn("SS1202", _codes(diagnostics))


# ==========================================================================
# SS1203  partiallyDeclared.externalLiteral
# ==========================================================================

class TestLiteralWithoutDigest(unittest.TestCase):
    def test_external_source_without_digest_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
literal embeddedConfig String
literalSource embeddedConfig "config.json"
""")
        self.assertIn("SS1203", _codes(diagnostics))

    def test_external_source_with_digest_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
literal embeddedConfig String
literalSource embeddedConfig "config.json"
literalDigest embeddedConfig sha256 abc123
""")
        self.assertNotIn("SS1203", _codes(diagnostics))


class TestLiteralSourcePins(unittest.TestCase):
    def test_missing_literal_source_is_compile_blocking(self) -> None:
        diagnostics = _lint_source_at("src/main.sem", """project Test
literal embeddedConfig String
literalSource embeddedConfig "../config.json"
literalBytes embeddedConfig 2
literalDigest embeddedConfig sha256 44136fa355b3678a1146ad16f7e8649e94fb4f0c4f2d2276f7e9d9a7a08f8894
""")
        matching = _diagnostics_with_code(diagnostics, "SS1204")[0]
        self.assertTrue(matching.blocksCompile)

    def test_literal_source_resolves_relative_to_source_file(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            sourceDir = root / "src"
            sourceDir.mkdir()
            (root / "config.json").write_text("{}\n", encoding="utf-8")
            normalizedBytes = "{}\n".encode("utf-8")
            digest = hashlib.sha256(normalizedBytes).hexdigest()
            fixturePath = sourceDir / "main.sem"
            fixturePath.write_text(f"""project Test
literal embeddedConfig String
literalSource embeddedConfig "../config.json"
literalBytes embeddedConfig {len(normalizedBytes)}
literalDigest embeddedConfig sha256 {digest}
""", encoding="utf-8")

            diagnostics = semlint.lint_path(fixturePath)

        self.assertNotIn("SS1204", _codes(diagnostics))
        self.assertNotIn("SS1205", _codes(diagnostics))
        self.assertNotIn("SS1206", _codes(diagnostics))

    def test_literal_byte_and_digest_pins_must_match_resolved_source(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            sourceDir = root / "src"
            sourceDir.mkdir()
            (root / "config.json").write_text("{}\n", encoding="utf-8")
            fixturePath = sourceDir / "main.sem"
            fixturePath.write_text("""project Test
literal embeddedConfig String
literalSource embeddedConfig "../config.json"
literalBytes embeddedConfig 99
literalDigest embeddedConfig sha256 deadbeef
""", encoding="utf-8")

            diagnostics = semlint.lint_path(fixturePath)

        self.assertIn("SS1205", _codes(diagnostics))
        self.assertIn("SS1206", _codes(diagnostics))


# ==========================================================================
# SS3101 / SS3102  operationMetadataGap.{purpose,invariant}
# ==========================================================================

class TestOperationMetadataGaps(unittest.TestCase):
    def test_missing_purpose_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
call writeLineCall console.writeLine
run writeLineCall
""")
        self.assertIn("SS3101", _codes(diagnostics))

    def test_state_touching_op_without_invariant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision Int64 zeroCount
operation main
output main Void
purpose main "smoke"
set module accountLookupRevision nextAccountLookupRevision
""")
        self.assertIn("SS3102", _codes(diagnostics))

    def test_purpose_present_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
run writeLineCall
""")
        self.assertNotIn("SS3101", _codes(diagnostics))


# ==========================================================================
# SS3104  capabilityCoverage.missing  (T3, NOT compile-blocking — matches
# docs/reference/syntax-inventory.md which scopes capability coverage as a linter rule)
# ==========================================================================

class TestEffectWithoutCapability(unittest.TestCase):
    def test_effect_without_capability_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
""")
        self.assertIn("SS3104", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3104")[0]
        self.assertFalse(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, semlint.Tier.T3_REFINEMENT)

    def test_use_capability_satisfies_check(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
useCapability main consoleCap
""")
        self.assertNotIn("SS3104", _codes(diagnostics))

    def test_inline_authority_satisfies_check(self) -> None:
        # Canonical authority order is action-first (`authority OP ACTION PATH`),
        # mirroring the `effect OP ACTION PATH` it backs. A correctly-ordered
        # grant satisfies SS3104 AND is not flagged by SS3109.
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
authority main write console.stdout
""")
        self.assertNotIn("SS3104", _codes(diagnostics))
        self.assertNotIn("SS3109", _codes(diagnostics))

    def test_capability_coverage_fix_candidate_authority_is_access_first(self) -> None:
        # Regression: the SS3104 inlineAuthority fix once emitted a path-first
        # `authority OP PATH ACTION` row, which then tripped SS3109. The
        # suggested grant must be action-first so applying it actually clears
        # the effect and stays consistent.
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
""")
        ss3104 = _diagnostics_with_code(diagnostics, "SS3104")[0]
        inline = next(c for c in ss3104.fixCandidates if c.name == "inlineAuthority")
        self.assertEqual(inline.shape, "authority main write console.stdout")


# ==========================================================================
# SS3105  capabilityCoverage.unprotectedSharedState
# ==========================================================================

class TestSharedStateProtection(unittest.TestCase):
    def test_unprotected_write_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount Int64 zeroCount
operation main
output main Void
purpose main "smoke"
invariant main "increments on lookup failure"
set sharedState lookupFailureCount nextLookupFailureCount
""")
        self.assertIn("SS3105", _codes(diagnostics))

    def test_protected_write_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount Int64 zeroCount
operation main
output main Void
purpose main "smoke"
invariant main "increments on lookup failure"
set sharedState lookupFailureCount nextLookupFailureCount protectedBy lookupFailureGuard
""")
        self.assertNotIn("SS3105", _codes(diagnostics))


class TestSupportedSharedStateScope(unittest.TestCase):
    def test_cross_process_scope_is_flagged_as_unsupported_runtime_claim(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState cluster mutable lookupFailureCount Int64 zeroCount
""")
        self.assertIn("SS3108", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3108")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "lookupFailureCount")
        self.assertEqual(matchingDiagnostic.gapEdge, "processScopeOnly")

    def test_process_scope_is_currently_supported(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount Int64 zeroCount
""")
        self.assertNotIn("SS3108", _codes(diagnostics))


# ==========================================================================
# Narrative citations — diagnostics on an op should CITE its existing
# narrative attachments (purpose/invariant/warning/guarantee/…) rather than
# restate the gap in prose.
# ==========================================================================

class TestNarrativeCitations(unittest.TestCase):
    def test_capability_gap_cites_purpose(self) -> None:
        diagnostics = _lint_source("""project Test
operation exitProcess
output exitProcess Void
effect exitProcess write process.lifecycle
purpose exitProcess "terminate process cleanly"
invariant exitProcess "control flow does not return"
""")
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3104")[0]
        citationKinds = [citation.edgeKind for citation in matchingDiagnostic.citations]
        self.assertIn("purpose", citationKinds)
        self.assertIn("invariant", citationKinds)


# ==========================================================================
# Sort + render smoke tests — make sure the output channels stay usable.
# ==========================================================================

class TestRendering(unittest.TestCase):
    SAMPLE_SOURCE = """project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
"""

    def test_human_render_contains_subject_and_intent(self) -> None:
        diagnostics = _lint_source(self.SAMPLE_SOURCE)
        renderedOutput = semlint.render_human(diagnostics)
        self.assertIn("subject", renderedOutput)
        self.assertIn("intent", renderedOutput)

    def test_agent_render_is_parseable_json(self) -> None:
        diagnostics = _lint_source(self.SAMPLE_SOURCE)
        import json
        payload = json.loads(semlint.render_agent(diagnostics))
        self.assertIn("refinementQueue", payload)

    def test_sem_record_render_has_draft_header(self) -> None:
        diagnostics = _lint_source(self.SAMPLE_SOURCE)
        renderedOutput = semlint.render_sem_record(diagnostics)
        self.assertIn("DRAFT", renderedOutput)
        self.assertIn("diagnostic", renderedOutput)


# ==========================================================================
# SS0001  grammar.unknownVerb   (T0 — non-overridable error)
# ==========================================================================

class TestUnknownVerbs(unittest.TestCase):
    def test_typo_verb_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operationn main
output main Void
""")
        self.assertIn("SS0001", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0001")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "operationn")
        self.assertTrue(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, semlint.Tier.T0_PARSE)

    def test_known_verbs_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
""")
        self.assertNotIn("SS0001", _codes(diagnostics))

    def test_build_tape_verbs_not_flagged(self) -> None:
        diagnostics = _lint_source("""buildProject taskForgeTui
project TaskForgeTui
modulePath taskForgeTui github.com/monstercameron/SemanticScript/apps/taskforge-tui
languageVersion taskForgeTui "1.0"
projectVersion taskForgeTui "1.0.0"
projectLicense taskForgeTui MIT
sourceRoot taskForgeTui "."
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "fixture.sscript"
mainOperation taskForgeTui main
testPattern taskForgeTui "*.test.sem"
testRoot taskForgeTui "."
dependencySource taskForgeTui semstd github.com/monstercameron/SemanticScript/std
dependencyIntegrity taskForgeTui semstd "sha256-example"
buildProfile taskForgeTui dev
runtimeChecks taskForgeTui panic
persistLlvmIr taskForgeTui no
optLevel taskForgeTui 2
emitLlvmIr taskForgeTui auto
llvmIrOutput taskForgeTui "build/todo.ll"
emitOptimizedLlvmIr taskForgeTui no
optimizedLlvmIrOutput taskForgeTui "build/todo.opt.ll"
buildRoot taskForgeTui "."
buildFolderName taskForgeTui build
cpuBaseline taskForgeTui generic
cpuTune taskForgeTui generic
cpuFeature taskForgeTui avx2 off
cpuFeatureCheck taskForgeTui auto
nativeOutput taskForgeTui "taskforge_tui.exe"
nativeHttpHost taskForgeTui "127.0.0.1"
nativeHttpPort taskForgeTui 18080
formatterSetting taskForgeTui lineWidth 100
linterSetting taskForgeTui maxTier T4
docsOutput taskForgeTui "docs"
keepResources taskForgeTui no
resourcesDir taskForgeTui "build/resources"
targetRuntime taskForgeTui nativeExe
comptimeOperation taskForgeTui configureTaskForgeTuiBuild
iconRoleDefinition applicationPrimary "Primary app icon."
icon todoPrimaryIcon
iconRole todoPrimaryIcon applicationPrimary
iconPurpose todoPrimaryIcon "Primary shell icon."
iconImage todoPrimaryAt16
iconImageGroup todoPrimaryAt16 todoPrimaryIcon
iconImagePath todoPrimaryAt16 "assets/icons/icon-16.png"
iconImageFormat todoPrimaryAt16 png
iconImageWidth todoPrimaryAt16 16
iconImageHeight todoPrimaryAt16 16
iconImageScale todoPrimaryAt16 1
iconImageDepth todoPrimaryAt16 bits32
iconImagePlatform todoPrimaryAt16 any
iconImagePurpose todoPrimaryAt16 "Small shell icon."
""")
        self.assertNotIn("SS0001", _codes(diagnostics))
        self.assertNotIn("SS0002", _codes(diagnostics))

    def test_gui_function_calls_not_flagged(self) -> None:
        diagnostics = _lint_source("""project GuiLint
target windowsGui
import gui standard.gui
storage module immutable title GuiText "Todo"
storage module immutable width GuiPixels 640
storage module immutable height GuiPixels 480
storage module immutable yesFlag Int32 1
storage module immutable maxTitleLength Int32 120
operation main
output operation main ExitCode
effect main allocate gui.application
effect main allocate gui.window
effect main allocate gui.control
effect main write gui.window
authority main allocate gui.application
authority main allocate gui.window
authority main allocate gui.control
authority main write gui.window
purpose operation main "compose the GUI through standard function calls"
call createApplicationCall gui.applicationCreate
argument createApplicationCall title GuiText title
run createApplicationCall
bind value application GuiApplication createApplicationCall
call createWindowCall gui.windowCreate
argument createWindowCall title GuiText title
argument createWindowCall width GuiPixels width
argument createWindowCall height GuiPixels height
argument createWindowCall layout GuiWindowLayout verticalStackGuiWindowLayout
argument createWindowCall resizable Int32 yesFlag
run createWindowCall
bind value window GuiWindow createWindowCall
call createTextBoxCall gui.textBoxCreate
argument createTextBoxCall placeholder GuiText title
argument createTextBoxCall maxLength Int32 maxTitleLength
run createTextBoxCall
bind value textBox GuiTextBox createTextBoxCall
call addControlCall gui.windowAddControl
argument addControlCall window GuiWindow window
argument addControlCall control GuiControl textBox
run addControlCall
ignore value source addControlCall type Int32
call setMainWindowCall gui.applicationSetMainWindow
argument setMainWindowCall application GuiApplication application
argument setMainWindowCall window GuiWindow window
run setMainWindowCall
ignore value source setMainWindowCall type Int32
call runApplicationCall gui.applicationRun
argument runApplicationCall application GuiApplication application
run runApplicationCall
bind value status ExitCode runApplicationCall
return value status
""")
        self.assertNotIn("SS0001", _codes(diagnostics))
        self.assertNotIn("SS0002", _codes(diagnostics))

    def test_gui_declarative_keyword_rows_are_not_standard_syntax(self) -> None:
        diagnostics = _lint_source("""project GuiLint
target windowsGui
importModule gui standard.gui
guiApplication todoGuiApp
guiWindow todoMainWindow
guiButton addTodoButton
""")
        codes = _codes(diagnostics)
        self.assertIn("SS0001", codes)
        unknownSubjects = {
            diagnostic.subjectName
            for diagnostic in diagnostics
            if diagnostic.code == "SS0001"
        }
        self.assertIn("guiApplication", unknownSubjects)
        self.assertIn("guiWindow", unknownSubjects)
        self.assertIn("guiButton", unknownSubjects)


class TestHtmlSyntaxIsland(unittest.TestCase):
    def test_html_template_verbs_and_body_lines_are_known(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <section class="{{cardClassName}}">
    <style>
      .meter { width: 100%; content: "{literal-braces-stay-static}"; }
    </style>
    <h1>{{titleText}}</h1>
  </section>
operation main
output operation main Void
purpose operation main "html lint smoke"
""")
        self.assertNotIn("SS0001", _codes(diagnostics))
        self.assertNotIn("SS0002", _codes(diagnostics))
        self.assertNotIn("SS3520", _codes(diagnostics))

    def test_html_body_can_continue_through_blank_lines_and_eof(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <section>

    <h1>{{titleText}}</h1>
  </section>
""")
        self.assertNotIn("SS0001", _codes(diagnostics))
        self.assertNotIn("SS0002", _codes(diagnostics))

    def test_column_zero_after_html_body_is_linted_normally(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <h1>{{titleText}}</h1>
operation main
output main Void
purpose main "html lint smoke"
definitelyNotAVerb afterHtmlBody
""")
        self.assertIn("SS0001", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0001")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "definitelyNotAVerb")

    def test_indented_markup_without_html_body_is_still_unknown(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
  <h1>not in an htmlBody island</h1>
operation main
output main Void
purpose main "html lint smoke"
""")
        self.assertIn("SS0001", _codes(diagnostics))

    def test_html_parameter_rows_are_rejected(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html parameter template CardTemplate titleText String
html body template CardTemplate
  <h1>{{titleText}}</h1>
""")
        self.assertIn("SS0003", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0003")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "html")

    def test_html_body_arity_is_checked(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template
  <h1>missing template name</h1>
""")
        self.assertIn("SS0003", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0003")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "html")

    def test_html_hydrate_reports_missing_double_brace_hole_arg(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <h1>{{titleText}}</h1>
operation main
output operation main Void
purpose operation main "html lint smoke"
call hydrateCardCall html.hydrate.CardTemplate
run hydrateCardCall
return void
""")
        matching = [
            diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3520")
            if diagnostic.intentSlogan == "hydrate arg missing"
        ]
        self.assertEqual(1, len(matching))
        self.assertIn("titleText", matching[0].invariantRule)

    def test_html_hydrate_reports_extra_arg(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <h1>{{titleText}}</h1>
operation main
output operation main Void
purpose operation main "html lint smoke"
storage local immutable titleValue String "Title"
storage local immutable extraValue String "Extra"
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall titleText String titleValue
argument hydrateCardCall extraText String extraValue
run hydrateCardCall
return void
""")
        matching = [
            diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3520")
            if diagnostic.intentSlogan == "hydrate arg extra"
        ]
        self.assertEqual(1, len(matching))
        self.assertIn("extraText", matching[0].invariantRule)

    def test_html_legacy_single_brace_hole_blocks_with_migration_text(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <h1>{titleText}</h1>
""")
        matching = [
            diagnostic for diagnostic in diagnostics
            if diagnostic.code == "SS3520"
            and diagnostic.intentSlogan == "legacy HTML hole delimiter rejected"
        ][0]
        self.assertTrue(matching.blocksCompile)
        self.assertIn("{{titleText}}", matching.invariantRule)

    def test_html_literal_js_and_css_braces_are_not_holes(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <style>
    .meter { width: 100%; color: red; }
  </style>
  <script>
    const state = { open: true, count: 1 };
    import { initHTMLeX } from "/assets/app.js";
  </script>
""")
        self.assertNotIn("SS3520", _codes(diagnostics))

    def test_html_record_field_hole_root_is_the_required_argument(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <h1>{{profile.titleText}}</h1>
operation main
output operation main Void
purpose operation main "html lint smoke"
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall profile Profile profileValue
run hydrateCardCall
return void
""")
        self.assertNotIn("SS3520", _codes(diagnostics))

    def test_request_data_cannot_be_hydrated_as_raw_html(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <section>{{bodyHtml}}</section>
operation unsafeHandler
input operation unsafeHandler request HttpRequest
output operation unsafeHandler Void
purpose operation unsafeHandler "request body must not become raw HTML"
call bodyReadCall http.requestBodyText
argument bodyReadCall request HttpRequest request
run bodyReadCall
bind value bodyValue String bodyReadCall
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall bodyHtml HtmlFragment bodyValue
run hydrateCardCall
ignore value source hydrateCardCall type HtmlDocument
return void
""")
        matching = _diagnostics_with_code(diagnostics, "SS3616")
        self.assertEqual(1, len(matching))
        self.assertEqual(matching[0].kind, "webserver.untrustedHtmlHydration")
        self.assertEqual(matching[0].subjectName, "bodyValue")

    def test_request_data_may_be_hydrated_as_escaped_string(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <section>{{bodyText}}</section>
operation safeHandler
input operation safeHandler request HttpRequest
output operation safeHandler Void
purpose operation safeHandler "request body enters an escaped String hole"
call bodyReadCall http.requestBodyText
argument bodyReadCall request HttpRequest request
run bodyReadCall
bind value bodyValue String bodyReadCall
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall bodyText String bodyValue
run hydrateCardCall
ignore value source hydrateCardCall type HtmlDocument
return void
""")
        self.assertNotIn("SS3616", _codes(diagnostics))

    def test_href_dynamic_string_hole_requires_safe_url(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
html template CardTemplate
html body template CardTemplate
  <a href="{{plainString}}">open</a>
operation main
output operation main Void
purpose operation main "html safe url lint smoke"
storage local immutable linkText String "/unsafe"
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall plainString String linkText
run hydrateCardCall
return void
""")
        matching = [
            diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3520")
            if diagnostic.intentSlogan == "URL hydrate arg must be HtmlSafeUrl"
        ]
        self.assertEqual(1, len(matching))
        self.assertIn("HtmlSafeUrl", matching[0].invariantRule)

    def test_href_dynamic_safe_url_hole_is_accepted(self) -> None:
        diagnostics = _lint_source("""project HtmlLint
type HtmlSafeUrl String
html template CardTemplate
html body template CardTemplate
  <a href="{{safeUrl}}">open</a>
operation main
output operation main Void
purpose operation main "html safe url lint smoke"
storage local immutable linkText HtmlSafeUrl "/safe"
call hydrateCardCall html.hydrate.CardTemplate
argument hydrateCardCall safeUrl HtmlSafeUrl linkText
run hydrateCardCall
return void
""")
        self.assertNotIn("SS3520", _codes(diagnostics))


class TestGuiRuntimeContracts(unittest.TestCase):
    def test_gui_declarative_handles_feed_builtin_signature_check(self) -> None:
        diagnostics = _lint_source("""project GuiLint
importModule gui standard.gui
operation handleTitleChanged
input handleTitleChanged session GuiSession
input handleTitleChanged event GuiEvent
input handleTitleChanged todoTitleTextBox GuiTextBox
output handleTitleChanged Int32
effect handleTitleChanged read gui.control.textBox.text
authority handleTitleChanged gui.control.textBox.text read
purpose handleTitleChanged "read the live text box text after a GUI event"
call titleReadCall gui.textBoxText
arg titleReadCall session session
arg titleReadCall textBox todoTitleTextBox
run titleReadCall
ignoreValue titleReadCall String
returnValue 0
""")
        codes = _codes(diagnostics)
        self.assertNotIn("SS4105", codes)
        self.assertNotIn("SS4301", codes)
        self.assertNotIn("SS3111", codes)

    def test_gui_runtime_wrong_handle_type_is_flagged(self) -> None:
        diagnostics = _lint_source("""project GuiLint
importModule gui standard.gui
operation handleTitleChanged
input handleTitleChanged session GuiSession
input handleTitleChanged event GuiEvent
input handleTitleChanged addTodoButton GuiButton
output handleTitleChanged Int32
effect handleTitleChanged read gui.control.textBox.text
authority handleTitleChanged gui.control.textBox.text read
purpose handleTitleChanged "read the live text box text after a GUI event"
call titleReadCall gui.textBoxText
arg titleReadCall session session
arg titleReadCall textBox addTodoButton
run titleReadCall
ignoreValue titleReadCall String
returnValue 0
""")
        self.assertIn("SS4301", _codes(diagnostics))

    def test_gui_runtime_effect_uses_generic_body_effect_checker(self) -> None:
        diagnostics = _lint_source("""project GuiLint
importModule gui standard.gui
operation handleClose
input handleClose session GuiSession
input handleClose event GuiEvent
input handleClose todoMainWindow GuiWindow
output handleClose Int32
purpose handleClose "close the main GUI window"
call closeCall gui.windowClose
arg closeCall session session
arg closeCall window todoMainWindow
run closeCall
ignoreValue closeCall Int32
returnValue 0
""")
        matching = _diagnostics_with_code(diagnostics, "SS3111")[0]
        self.assertEqual(matching.gapEdge, "effect")
        self.assertIn("gui.window", matching.invariantRule)

    def test_gui_control_event_handler_arg_is_operation_reference(self) -> None:
        diagnostics = _lint_source("""project GuiLint
importModule gui standard.gui
storage module mutable addTodoButton GuiButton 0
operation main
output main ExitCode
effect main write gui.control.event
authority main gui.control.event write
purpose main "register a GUI click handler"
call registerClickCall gui.controlOnEvent
arg registerClickCall control addTodoButton
arg registerClickCall eventKind clickGuiEventKind
arg registerClickCall handler addTaskFromInput
run registerClickCall
ignoreValue registerClickCall Int32
returnValue 0
operation addTaskFromInput
input addTaskFromInput session GuiSession
input addTaskFromInput event GuiEvent
output addTaskFromInput Int32
purpose addTaskFromInput "handle a GUI click"
returnValue 0
""")
        codes = _codes(diagnostics)
        self.assertNotIn("SS4105", codes)
        self.assertNotIn("SS4301", codes)
        self.assertNotIn("SS3111", codes)


# ==========================================================================
# SS252x  build.sem project build tape schema
# ==========================================================================

class TestProjectBuildTapeSchema(unittest.TestCase):
    def _write_complete_project(self, root: Path, extraRows: str = "") -> Path:
        (root / "main.sem").write_text("module app.todo\n", encoding="utf-8")
        buildPath = root / "build.sem"
        buildPath.write_text(f"""buildProject taskForgeTui
project TaskForgeTui
modulePath taskForgeTui github.com/example/todo
languageVersion taskForgeTui "1.0"
projectVersion taskForgeTui "1.0.0"
projectLicense taskForgeTui MIT
sourceRoot taskForgeTui "."
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
mainOperation taskForgeTui main
testPattern taskForgeTui "*.test.sem"
testRoot taskForgeTui "."
targetRuntime taskForgeTui nativeExe
buildProfile taskForgeTui dev
runtimeChecks taskForgeTui panic
persistLlvmIr taskForgeTui auto
optLevel taskForgeTui 2
emitLlvmIr taskForgeTui auto
emitOptimizedLlvmIr taskForgeTui no
buildFolderName taskForgeTui build
cpuBaseline taskForgeTui generic
cpuTune taskForgeTui generic
cpuFeatureCheck taskForgeTui auto
formatterSetting taskForgeTui lineWidth 100
linterSetting taskForgeTui maxTier T4
docsOutput taskForgeTui "docs"
{extraRows}""", encoding="utf-8")
        return buildPath

    def _write_windows_gui_project(self, root: Path, extraRows: str = "") -> Path:
        (root / "main.sem").write_text("module app.todo_gui\n", encoding="utf-8")
        buildPath = root / "build.sem"
        buildPath.write_text(f"""buildProject todoGui
project TodoGuiApp
modulePath todoGui github.com/example/todo-gui
languageVersion todoGui "1.0"
projectVersion todoGui "1.0.0"
projectLicense todoGui MIT
sourceRoot todoGui "."
registerModule todoGui app.todo_gui "."
mainFile todoGui "main.sem"
testPattern todoGui "*.test.sem"
testRoot todoGui "."
targetRuntime todoGui windowsGui
buildProfile todoGui dev
runtimeChecks todoGui panic
persistLlvmIr todoGui auto
optLevel todoGui 2
emitLlvmIr todoGui auto
emitOptimizedLlvmIr todoGui no
buildFolderName todoGui build
cpuBaseline todoGui generic
cpuTune todoGui generic
cpuFeatureCheck todoGui auto
formatterSetting todoGui lineWidth 100
linterSetting todoGui maxTier T4
docsOutput todoGui "docs"
{extraRows}""", encoding="utf-8")
        return buildPath

    def _write_regular_build_plan_project(
        self,
        root: Path,
        *,
        targetRuntime: str = "nativeExe",
        guiBackend: str = "win32",
        optLevel: int = 2,
    ) -> Path:
        (root / "main.sem").write_text("module app.todo\n", encoding="utf-8")
        buildPath = root / "build.sem"
        buildPath.write_text(f"""module app.todo.build
record BuildProject
field BuildProject id String
field BuildProject name String
field BuildProject modulePath String
field BuildProject languageVersion String
field BuildProject projectVersion String
field BuildProject license String
record BuildModule
field BuildModule moduleName String
field BuildModule sourceRoot String
field BuildModule sourcePath String
field BuildModule mainFile String
field BuildModule mainOperation String
record BuildTarget
field BuildTarget runtime String
field BuildTarget guiBackend String
field BuildTarget profile String
field BuildTarget optLevel Int64
field BuildTarget runtimeChecks String
field BuildTarget persistLlvmIr Bool
field BuildTarget buildFolderName String
record BuildPlan
field BuildPlan project BuildProject
field BuildPlan module BuildModule
field BuildPlan target BuildTarget
storage module immutable todoBuildPlan BuildPlan
jsonBody todoBuildPlan
  {{
    "project": {{
      "id": "taskForgeTui",
      "name": "TaskForgeTui",
      "modulePath": "github.com/example/todo",
      "languageVersion": "1.0",
      "projectVersion": "1.0.0",
      "license": "MIT"
    }},
    "module": {{
      "moduleName": "app.todo",
      "sourceRoot": ".",
      "sourcePath": ".",
      "mainFile": "main.sem",
      "mainOperation": "main"
    }},
    "target": {{
      "runtime": "{targetRuntime}",
      "guiBackend": "{guiBackend}",
      "profile": "dev",
      "optLevel": {optLevel},
      "runtimeChecks": "panic",
      "persistLlvmIr": true,
      "buildFolderName": "build"
    }}
  }}
""", encoding="utf-8")
        return buildPath

    def test_complete_build_tape_schema_is_clean(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(Path(tempDir))
            diagnostics = semlint.lint_path(buildPath)
        self.assertNotIn("SS2521", _codes(diagnostics))
        self.assertNotIn("SS2522", _codes(diagnostics))
        self.assertNotIn("SS2523", _codes(diagnostics))
        self.assertNotIn("SS2524", _codes(diagnostics))
        self.assertNotIn("SS2525", _codes(diagnostics))
        self.assertNotIn("SS2526", _codes(diagnostics))
        self.assertNotIn("SS2527", _codes(diagnostics))

    def test_windows_gui_build_tape_allows_standard_entry_console(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_windows_gui_project(
                Path(tempDir),
                extraRows="mainOperation todoGui main\nentry console main\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2522", codes)
        self.assertNotIn("SS2525", codes)

    def test_gui_backend_build_tape_choice_is_validated(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_windows_gui_project(
                Path(tempDir),
                extraRows="guiBackend todoGui win32\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertNotIn("SS2525", _codes(diagnostics))

        with TemporaryDirectory() as tempDir:
            buildPath = self._write_windows_gui_project(
                Path(tempDir),
                extraRows="guiBackend todoGui qt\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2525", _codes(diagnostics))

    def test_regular_build_plan_schema_is_clean_and_registers_module(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_regular_build_plan_project(Path(tempDir))
            diagnostics = semlint.lint_path(buildPath)
            facts = semlint.parse_file(buildPath)
            registered, mainFiles = semlint._collect_registered_modules(facts)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2521", codes)
        self.assertNotIn("SS2522", codes)
        self.assertNotIn("SS2525", codes)
        self.assertEqual({"app.todo"}, set(registered))
        self.assertEqual(["main.sem"], mainFiles)

    def test_regular_build_plan_invalid_runtime_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_regular_build_plan_project(
                Path(tempDir),
                targetRuntime="desktopWizard",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2525", _codes(diagnostics))

    def test_regular_build_plan_invalid_gui_backend_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_regular_build_plan_project(
                Path(tempDir),
                targetRuntime="windowsGui",
                guiBackend="qt",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2525", _codes(diagnostics))

    def test_missing_required_rows_are_flagged(self) -> None:
        diagnostics = _lint_source("""buildProject taskForgeTui
project TaskForgeTui
""")
        self.assertIn("SS2522", _codes(diagnostics))

    def test_invalid_opt_level_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="optLevel taskForgeTui 9\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2524", _codes(diagnostics))
        self.assertIn("SS2525", _codes(diagnostics))

    def test_duplicate_singleton_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="buildProfile taskForgeTui prod\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2524", _codes(diagnostics))

    def test_project_name_mismatch_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="modulePath otherProject github.com/example/other\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2527", _codes(diagnostics))

    def test_build_folder_name_rejects_path(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="buildFolderName taskForgeTui nested/build\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2526", _codes(diagnostics))

    def test_cpu_feature_state_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="cpuFeature taskForgeTui avx2 maybe\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2525", _codes(diagnostics))

    def test_dependency_fetch_github_and_http_rows_are_clean(self) -> None:
        with TemporaryDirectory() as tempDir:
            digest = "a" * 64
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows=(
                    "dependency taskForgeTui semstd github.com/example/semstd v1.0.0\n"
                    "dependencyFetch taskForgeTui semstd github example/semstd v1.0.0\n"
                    "dependencyIntegrity taskForgeTui semstd commit:abcdef1234567890\n"
                    "dependency taskForgeTui api github.com/example/api v2.0.0\n"
                    "dependencyFetch taskForgeTui api http \"https://example.com/api.tar.gz\"\n"
                    f"dependencyIntegrity taskForgeTui api sha256:{digest}\n"
                    "dependencyCache taskForgeTui \".semcache\"\n"
                    "dependencyLock taskForgeTui \"sem.lock\"\n"
                ),
            )
            diagnostics = semlint.lint_path(buildPath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2550", codes)
        self.assertNotIn("SS2551", codes)
        self.assertNotIn("SS2552", codes)
        self.assertNotIn("SS2553", codes)
        self.assertNotIn("SS2554", codes)
        self.assertNotIn("SS2555", codes)

    def test_github_owner_repo_rejects_confusable_host(self) -> None:
        self.assertTrue(semlint._github_owner_repo_is_valid("github.com/example/semstd"))
        self.assertFalse(semlint._github_owner_repo_is_valid("github.com.evil/example"))

    def test_dependency_fetch_rejects_unknown_alias_and_insecure_http(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows="dependencyFetch taskForgeTui missing http \"http://example.com/api.tar.gz\"\n",
            )
            diagnostics = semlint.lint_path(buildPath)
        codes = _codes(diagnostics)
        self.assertIn("SS2551", codes)
        self.assertIn("SS2552", codes)

    def test_dependency_source_rejects_unknown_explicit_kind(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows=(
                    "dependency taskForgeTui api github.com/example/api v1.0.0\n"
                    "dependencySource taskForgeTui api git \"https://example.com/api.git\"\n"
                ),
            )
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2552", _codes(diagnostics))

    def test_remote_dependency_warns_for_missing_integrity_cache_and_lock(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = self._write_complete_project(
                Path(tempDir),
                extraRows=(
                    "dependency taskForgeTui semstd github.com/example/semstd main\n"
                    "dependencyFetch taskForgeTui semstd github example/semstd main\n"
                ),
            )
            diagnostics = semlint.lint_path(buildPath)
        codes = _codes(diagnostics)
        self.assertIn("SS2553", codes)
        self.assertIn("SS2554", codes)
        self.assertIn("SS2555", codes)


# ==========================================================================
# SS250x  project module registry contract
# ==========================================================================

class TestProjectModuleRegistry(unittest.TestCase):
    def test_build_tape_export_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "main.sem").write_text("module app.todo\n", encoding="utf-8")
            buildPath = root / "build.sem"
            buildPath.write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
exportOperation app.todo main
""", encoding="utf-8")
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2502", _codes(diagnostics))

    def test_registered_module_exports_are_local_and_clean(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportOperation app.todo main
operation main
output main Void
purpose main "smoke"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertNotIn("SS2503", _codes(diagnostics))
        self.assertNotIn("SS2504", _codes(diagnostics))
        self.assertNotIn("SS2505", _codes(diagnostics))
        self.assertNotIn("SS2506", _codes(diagnostics))

    def test_exported_symbol_must_be_declared(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportOperation app.todo missingMain
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2506", _codes(diagnostics))

    def test_storage_constant_export_counts_as_declared(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportConstant app.todo publicLimit
storage module immutable publicLimit Int64 5
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertNotIn("SS2506", _codes(diagnostics))

    def test_unregistered_module_declaration_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.other
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2503", _codes(diagnostics))

    def test_unregistered_module_import_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
importModule app.missing
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2504", _codes(diagnostics))

    def test_standard_html_import_is_allowed_in_registered_module(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
importModule html standard.html
html template CardTemplate
html body template CardTemplate
  <h1>{{titleText}}</h1>
storage module immutable titleText String "Title"
operation main
output main HtmlDocument
purpose main "hydrate through the imported standard.html namespace"
call hydrateCardCall html.hydrate.CardTemplate
arg hydrateCardCall titleText titleText
run hydrateCardCall
bind cardHtml HtmlDocument hydrateCardCall
returnValue cardHtml
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertNotIn("SS2504", _codes(diagnostics))
        self.assertNotIn("SS2534", _codes(diagnostics))

    def test_standard_import_uses_env_std_path_outside_repo(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            customStd = root / "custom-std"
            (customStd / "customlint").mkdir(parents=True)
            (customStd / "module.sem").write_text("""module standard
modulePurpose standard "Temporary std relay for linter tests."
moduleOwns standard "The standard.customlint relay import."
moduleDoesNotOwn standard "Bundled standard-library modules."
moduleInvariant standard "This fixture proves env-configured std discovery."
importModule standard.customlint
""", encoding="utf-8")
            (customStd / "customlint" / "main.sem").write_text(
                """module standard.customlint
modulePurpose standard.customlint "Temporary custom std module."
moduleOwns standard.customlint "The customLintVersionText export."
moduleDoesNotOwn standard.customlint "Application code."
moduleInvariant standard.customlint "The module is visible only through SEMANTICSCRIPT_STD_PATH."
exportConstant standard.customlint customLintVersionText
storage module immutable customLintVersionText String "custom"
""", encoding="utf-8")
            appRoot = root / "app"
            appRoot.mkdir()
            (appRoot / "build.sem").write_text("""buildProject appProject
registerModule appProject app.consumer "main.sem"
mainFile appProject "main.sem"
""", encoding="utf-8")
            modulePath = appRoot / "main.sem"
            modulePath.write_text("""module app.consumer
importModule custom standard.customlint
importConstant importedCustomText custom customLintVersionText
storage module immutable okCode ExitCode 0
operation main
output main ExitCode
purpose main "prove linter resolves std from env path"
returnValue okCode
""", encoding="utf-8")
            oldEnv = os.environ.get("SEMANTICSCRIPT_STD_PATH")
            os.environ["SEMANTICSCRIPT_STD_PATH"] = str(customStd)
            try:
                diagnostics = semlint.lint_path(modulePath)
            finally:
                if oldEnv is None:
                    os.environ.pop("SEMANTICSCRIPT_STD_PATH", None)
                else:
                    os.environ["SEMANTICSCRIPT_STD_PATH"] = oldEnv
        self.assertNotIn("SS2504", _codes(diagnostics))
        self.assertNotIn("SS2534", _codes(diagnostics))

    def test_stdlib_module_relay_is_clean_and_exposes_standard_modules(self) -> None:
        semanticScriptRoot = Path(_LINTER_DIRECTORY).resolve().parent
        relayPath = semanticScriptRoot / "std" / "module.sem"
        diagnostics = semlint.lint_path(relayPath)
        self.assertEqual(set(), set(_codes(diagnostics)))
        relayText = relayPath.read_text(encoding="utf-8")
        canonicalModules = (
            "array", "assert", "bit", "bool", "char", "compare", "constants",
            "convert", "ctype", "errno", "errno_more", "gui", "html", "http",
            "inttypes", "iso646", "json", "limits", "math",
            "memory", "numeric", "process", "random", "signal", "signal_more",
            "sqlite", "sort", "stddef", "stdio", "stdlib", "string", "time",
        )
        for moduleName in canonicalModules:
            self.assertIn(
                f"import {moduleName} standard.{moduleName}",
                relayText,
            )
            self.assertTrue(
                (semanticScriptRoot / "std" / moduleName / "main.sem").is_file()
            )
            self.assertTrue(
                (semanticScriptRoot / "std" / moduleName / "main.test.sem").is_file()
            )

    def test_standard_http_and_json_imports_allow_intrinsic_targets(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject runtimeImports
registerModule runtimeImports app.runtime_imports "main.sem"
mainFile runtimeImports "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.runtime_imports
importModule http standard.http
importModule json standard.json
importCapability importedHttpResponseWriter http httpResponseWriter
storage module immutable okBody String "ok"
storage module immutable plainType String "text/plain; charset=utf-8"
storage module immutable builderCapacity ByteCount 128
operation main
output main Void
effect main write http.response
useCapability main importedHttpResponseWriter
memoryHeap main yes
purpose main "prove official stdlib imports do not hide compiler-owned http/json intrinsic targets"
call writeCall http.responseText
arg writeCall status 200
arg writeCall body okBody
arg writeCall contentType plainType
run writeCall
ignoreValue writeCall Int32
call createBuilderCall json.createBuilder
arg createBuilderCall capacity builderCapacity
run createBuilderCall
ignoreValue createBuilderCall JsonBuilder
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2504", codes)
        self.assertNotIn("SS2534", codes)

    def test_standard_sqlite_import_allows_exec_intrinsic_target(self) -> None:
        # Regression: sqlite.exec is fully lowered by the compiler (the
        # Result-returning DDL form) and is recommended by the linter's own
        # transaction fix hints, but was missing from standard.sqlite's export
        # tape, so qualified calls were rejected with SS2534. execStatus and
        # exec must both resolve from the official export tape.
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject sqliteImports
registerModule sqliteImports app.sqlite_imports "main.sem"
mainFile sqliteImports "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.sqlite_imports
importModule sqlite standard.sqlite
importConstant inMemoryMode sqlite inMemorySqliteOpenMode
storage module immutable dbPath String ":memory:"
storage module immutable createSql SqlText
sql body createSql
  CREATE TABLE t (a TEXT)
operation main
output main Void
purpose main "prove sqlite.exec intrinsic target resolves from the official export tape"
call openCall sqlite.openDatabase
arg openCall path dbPath
arg openCall mode inMemoryMode
run openCall
bind openedDb SqliteDatabase openCall
call execCall sqlite.exec
arg execCall database openedDb
arg execCall sql createSql
run execCall
ignoreValue execCall Int32
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertNotIn("SS2534", _codes(diagnostics))

    def test_standard_json_import_allows_stringify_and_parse_targets(self) -> None:
        # Regression: qualified json.stringify.<T> / json.parse.<T> calls are
        # compiler-owned intrinsics lowered identically to json.encode.* /
        # json.decode.* (and treated equivalently elsewhere in the linter), but
        # the SS2534 allowlist only listed the encode./decode. verb forms, so
        # the stringify./parse. forms were wrongly rejected as private symbols
        # in module-form projects (project-form .sscript files never hit this
        # import path, which is why the existing json tests missed it).
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject jsonStringify
registerModule jsonStringify app.json_stringify "main.sem"
mainFile jsonStringify "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.json_stringify
importModule json standard.json
storage module immutable sampleValue Int64 42
operation main
output main Void
purpose main "prove qualified json.stringify/parse resolve like json.encode/decode"
call encodeCall json.encode.Int64
arg encodeCall value sampleValue
run encodeCall
ignoreValue encodeCall JsonText
call stringifyCall json.stringify.Int64
arg stringifyCall value sampleValue
run stringifyCall
ignoreValue stringifyCall JsonText
call parseCall json.parse.Int64
arg parseCall text sampleValue
run parseCall
ignoreValue parseCall Int64
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertNotIn("SS2534", _codes(diagnostics))

    def test_standard_json_import_allows_record_stringify_target(self) -> None:
        # Regression for the exact blocker the dashboard hit: a qualified
        # json.stringify.<Record> call (the verb-form alias of json.encode.
        # <Record>) was rejected with SS2534, and the diagnostic's own fix
        # suggestion (`exportOperation standard.json stringify.<Record>`) sent
        # the author down a dead end. The compiler lowers it to a real
        # structural codec, so neither SS2534 nor the stale SS3802 should fire.
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject jsonRecord
registerModule jsonRecord app.json_record "main.sem"
mainFile jsonRecord "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.json_record
importModule json standard.json
record SummaryMetrics layout row align 8
purpose operation SummaryMetrics "dashboard metrics"
field SummaryMetrics activeProjects Int64
field SummaryMetrics openTasks Int64
operation main
output main Void
purpose main "stringify and parse a record via the high-level verb aliases"
new metrics SummaryMetrics
fieldSet metrics activeProjects activeCount
call stringifyCall json.stringify.SummaryMetrics
arg stringifyCall value metrics
run stringifyCall
bind encoded JsonText stringifyCall
call parseCall json.parse.SummaryMetrics
arg parseCall value encoded
run parseCall
bind decoded SummaryMetrics parseCall
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2534", codes)
        self.assertNotIn("SS3802", codes)

    def test_missing_registered_module_source_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = Path(tempDir) / "build.sem"
            buildPath.write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "missing"
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2501", _codes(diagnostics))

    def test_duplicate_export_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportOperation app.todo main
exportOperation app.todo main
operation main
output main Void
purpose main "smoke"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2507", _codes(diagnostics))

    def test_mutable_storage_export_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportConstant app.todo mutableRevision
storage module mutable mutableRevision Int64 0
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2508", _codes(diagnostics))

    def test_local_storage_export_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportConstant app.todo scratchLimit
operation main
output main Void
purpose main "smoke"
storage local immutable scratchLimit Int64 5
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2509", _codes(diagnostics))

    def test_private_operation_from_imported_module_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject appProject
registerModule appProject app.consumer "main.sem"
registerModule appProject app.provider "provider.sem"
mainFile appProject "main.sem"
""", encoding="utf-8")
            (root / "provider.sem").write_text("""module app.provider
operation hiddenProviderOperation
output hiddenProviderOperation Void
purpose hiddenProviderOperation "provider internal"
returnVoid
""", encoding="utf-8")
            consumerPath = root / "main.sem"
            consumerPath.write_text("""module app.consumer
importModule app.provider
operation main
output main Void
purpose main "consumer"
call providerCall hiddenProviderOperation
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2510", _codes(diagnostics))

    def test_export_contract_tape_extracts_operation_edges(self) -> None:
        with TemporaryDirectory() as tempDir:
            modulePath = Path(tempDir) / "main.sem"
            modulePath.write_text("""module app.todo
exportError app.todo MainError
exportOperation app.todo main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
capability stdoutWriter console.stdout write
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
useCapability main stdoutWriter
memory main heap no
async main no
purpose main "public console entry"
returnOk 0
""", encoding="utf-8")
            facts = semlint.gather_extended(semlint.parse_file(modulePath))
            tape = semlint.build_export_contract_tape(facts)
        edgeKinds = {edge.edgeKind for edge in tape}
        self.assertIn("operation.input", edgeKinds)
        self.assertIn("operation.output", edgeKinds)
        self.assertIn("operation.effect", edgeKinds)
        self.assertIn("operation.failureType", edgeKinds)
        self.assertIn("operation.failureCase", edgeKinds)
        self.assertTrue(all(edge.line.number > 0 for edge in tape))

    def test_export_contract_tape_extracts_type_error_capability_and_constant_edges(self) -> None:
        with TemporaryDirectory() as tempDir:
            modulePath = Path(tempDir) / "main.sem"
            modulePath.write_text("""module app.todo
exportType app.todo TodoStatus
exportType app.todo TodoItem
exportError app.todo TodoError
exportCapability app.todo todoWriter
exportConstant app.todo maxTodoCount
enum TodoStatus repr Int32
enumCase TodoStatus openTodoStatus 0
record TodoItem
field TodoItem title String
error TodoError
errorCase TodoError SaveFailed SaveTodosFailure
capability todoWriter todo write
storage module immutable maxTodoCount Int64 128
""", encoding="utf-8")
            facts = semlint.gather_extended(semlint.parse_file(modulePath))
            tape = semlint.build_export_contract_tape(facts)
        edgeKinds = {edge.edgeKind for edge in tape}
        self.assertIn("type.enumCase", edgeKinds)
        self.assertIn("type.field", edgeKinds)
        self.assertIn("error.case", edgeKinds)
        self.assertIn("capability.authority", edgeKinds)
        self.assertIn("constant.value", edgeKinds)

    def test_exported_operation_quality_diagnostics(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject taskForgeTui
registerModule taskForgeTui app.todo "."
mainFile taskForgeTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
exportOperation app.todo helper
operation helper
output helper Void
call writeCall console.writeLine
run writeCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        codes = _codes(diagnostics)
        self.assertIn("SS2511", codes)
        self.assertIn("SS2512", codes)
        self.assertIn("SS2513", codes)
        self.assertIn("SS2514", codes)


class TestProjectModuleImports(unittest.TestCase):
    def _write_project(self, root: Path) -> Path:
        (root / "build.sem").write_text("""buildProject appProject
registerModule appProject app.consumer "main.sem"
registerModule appProject app.provider "provider.sem"
registerModule appProject app.other "other.sem"
mainFile appProject "main.sem"
""", encoding="utf-8")
        (root / "provider.sem").write_text("""module app.provider
exportType app.provider ProviderCount
exportError app.provider ProviderError
exportCapability app.provider providerReader
exportConstant app.provider providerLimit
exportConstant app.provider mutableCounter
exportOperation app.provider providerPing
exportOperation app.provider providerCount
type ProviderCount Int64
error ProviderError
errorCase ProviderError Failed ProviderFailure
capability providerReader provider read
storage module immutable providerLimit Int64 7
storage module mutable mutableCounter Int64 0
operation providerPing
output providerPing Void
purpose providerPing "public provider ping"
returnVoid
operation providerCount
input providerCount count Int64
output providerCount Result Int64 ProviderError
effect providerCount read provider
useCapability providerCount providerReader
purpose providerCount "public provider count"
returnOk count
operation hiddenProviderOperation
output hiddenProviderOperation Void
purpose hiddenProviderOperation "provider internal"
returnVoid
""", encoding="utf-8")
        (root / "other.sem").write_text("""module app.other
exportOperation app.other providerPing
operation providerPing
output providerPing Void
purpose providerPing "other public ping"
returnVoid
""", encoding="utf-8")
        return root / "main.sem"

    def test_import_contract_index_carries_exported_contract_edges(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
operation main
output main Void
purpose main "consumer"
returnVoid
""", encoding="utf-8")
            facts = semlint.gather_extended(semlint.parse_file(consumerPath))
            index = semlint.build_import_contract_index(facts)
        self.assertIn("svc.providerCount", index.qualifiedSymbols)
        self.assertIn("svc.ProviderCount", index.qualifiedSymbols)
        self.assertIn("svc.ProviderError", index.qualifiedSymbols)
        self.assertIn("svc.providerReader", index.qualifiedSymbols)
        self.assertIn("svc.providerLimit", index.qualifiedSymbols)
        edgeKinds = {
            edge.edgeKind
            for edge in index.qualifiedSymbols["svc.providerCount"].edges
        }
        self.assertIn("operation.input", edgeKinds)
        self.assertIn("operation.output", edgeKinds)
        self.assertIn("operation.effect", edgeKinds)

    def test_qualified_operation_call_happy_path(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
operation main
output main Void
purpose main "consumer"
call providerCall svc.providerPing
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2534", codes)
        self.assertNotIn("SS2537", codes)

    def test_singular_operation_type_error_capability_and_constant_imports(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
importOperation countProvider svc providerCount
importType LocalProviderCount svc ProviderCount
importError LocalProviderError svc ProviderError
importCapability LocalProviderReader svc providerReader
importConstant LocalProviderLimit svc providerLimit
operation main
output main Result LocalProviderCount LocalProviderError
effect main read provider
useCapability main LocalProviderReader
purpose main "consumer"
call providerCall countProvider
arg providerCall count LocalProviderLimit
run providerCall
bindOk count LocalProviderCount providerCall
bindError providerError LocalProviderError providerCall
branchIfError providerCall providerFailed
returnOk count
label providerFailed
returnError providerError
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        codes = _codes(diagnostics)
        self.assertNotIn("SS2533", codes)
        self.assertNotIn("SS2534", codes)
        self.assertNotIn("SS4103", codes)
        self.assertNotIn("SS4105", codes)
        self.assertNotIn("SS4301", codes)

    def test_standard_constant_imports_resolve_without_build_tape(self) -> None:
        with TemporaryDirectory() as tempDir:
            consumerPath = Path(tempDir) / "main.sem"
            consumerPath.write_text("""module app.consumer
import char standard.char
importConstant importedAsciiNewline char asciiNewlineCharacterCode
storage module immutable expectedNewline Int32 10
operation main
output main Void
purpose main "consumer"
call compareNewlineCall math.equalInt32
argument compareNewlineCall left Int32 importedAsciiNewline
argument compareNewlineCall right Int32 expectedNewline
run compareNewlineCall
ignore value source compareNewlineCall type Bool
returnVoid
""", encoding="utf-8")
            facts = semlint.gather_extended(semlint.parse_file(consumerPath))
            index = semlint.build_import_contract_index(facts)
            diagnostics = semlint.lint_path(consumerPath)
        codes = _codes(diagnostics)
        self.assertIn("char.asciiNewlineCharacterCode", index.qualifiedSymbols)
        self.assertIn("importedAsciiNewline", index.singularSymbols)
        self.assertNotIn("SS4105", codes)
        self.assertNotIn("SS4301", codes)

    def test_imported_operation_signature_checks_arguments(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
importOperation countProvider svc providerCount
const wrongCount String "wrong"
operation main
output main Void
purpose main "consumer"
call providerCall countProvider
arg providerCall count wrongCount
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS4301", _codes(diagnostics))

    def test_imported_operation_effect_must_be_redeclared_by_caller(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
const countValue Int64 1
operation main
output main Void
purpose main "consumer"
call providerCall svc.providerCount
arg providerCall count countValue
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        matching = _diagnostics_with_code(diagnostics, "SS2542")[0]
        self.assertFalse(matching.blocksCompile)
        self.assertEqual(matching.gapEdge, "callerEffectContract")

    def test_imported_operation_effect_can_be_declared_broadly(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
const countValue Int64 1
operation main
output main Void
effect main read provider
purpose main "consumer"
call providerCall svc.providerCount
arg providerCall count countValue
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertNotIn("SS2542", _codes(diagnostics))

    def test_private_qualified_operation_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
operation main
output main Void
purpose main "consumer"
call providerCall svc.hiddenProviderOperation
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2534", _codes(diagnostics))

    def test_qualified_mutable_storage_constant_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
operation main
output main Void
purpose main "consumer"
call providerCall svc.providerCount
arg providerCall count svc.mutableCounter
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2541", _codes(diagnostics))

    def test_alias_collision_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
importModule svc app.other
operation main
output main Void
purpose main "consumer"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2531", _codes(diagnostics))

    def test_wildcard_singular_import_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
importOperation * svc providerPing
operation main
output main Void
purpose main "consumer"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2532", _codes(diagnostics))

    def test_ambiguous_unqualified_import_reference_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
importModule other app.other
operation main
output main Void
purpose main "consumer"
call providerCall providerPing
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2536", _codes(diagnostics))

    def test_implicit_singular_import_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            consumerPath = self._write_project(root)
            consumerPath.write_text("""module app.consumer
importModule svc app.provider
operation main
output main Void
purpose main "consumer"
call providerCall providerCount
arg providerCall count providerLimit
run providerCall
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(consumerPath)
        self.assertIn("SS2537", _codes(diagnostics))

    def test_import_cycle_is_rejected(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject appProject
registerModule appProject app.a "a.sem"
registerModule appProject app.b "b.sem"
mainFile appProject "a.sem"
""", encoding="utf-8")
            aPath = root / "a.sem"
            aPath.write_text("""module app.a
importModule b app.b
operation main
output main Void
purpose main "a"
returnVoid
""", encoding="utf-8")
            (root / "b.sem").write_text("""module app.b
importModule a app.a
operation helper
output helper Void
purpose helper "b"
returnVoid
""", encoding="utf-8")
            diagnostics = semlint.lint_path(aPath)
        self.assertIn("SS2540", _codes(diagnostics))


# ==========================================================================
# SS0106  unusedDeclaration.bindSlot
# ==========================================================================

class TestUnusedBindSlots(unittest.TestCase):
    def test_unread_bind_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call computeCall math.addInt64
arg computeCall left someLeftValue
arg computeCall right someRightValue
run computeCall
bind unreadResult Int64 computeCall
""")
        self.assertIn("SS0106", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0106")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unreadResult")

    def test_read_bind_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Int64
purpose main "smoke"
call computeCall math.addInt64
arg computeCall left someLeftValue
arg computeCall right someRightValue
run computeCall
bind computedSum Int64 computeCall
returnValue computedSum
""")
        self.assertNotIn("SS0106", _codes(diagnostics))

    def test_error_slot_discharged_by_branch_error_not_flagged(self) -> None:
        # `bind error <slot> <call>` is the vehicle SS3106 requires; when its
        # call is discharged by `branch error source <call>`, the typed slot is
        # legitimately never read (the branch consumes the error via the call
        # name). It must NOT flag SS0106 — that would contradict SS3106.
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError DbFailure
operation persistRow
output persistRow Result Void MainError
purpose persistRow "smoke"
invariant persistRow "error is handled via branch; typed slot is the required vehicle"
call prepareCall sqlite.prepareStatement
arg prepareCall database database
arg prepareCall sql someSql
run prepareCall
bind ok preparedStatement SqliteStatement prepareCall
bind error prepareError SqlitePrepareFailure prepareCall
branch error source prepareCall target dbFailed
returnOk noResult
label dbFailed
makeError dbFailure MainError.DbFailure
returnError dbFailure
""")
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS0106")}
        self.assertNotIn("prepareError", flagged)

    def test_unread_error_slot_without_branch_discharge_still_flagged(self) -> None:
        # An error slot whose call is NOT branch-error-discharged and is never
        # read is still a genuine unused bind (exemption must not over-apply).
        diagnostics = _lint_source("""project Test
operation persistRow
output persistRow Void
purpose persistRow "smoke"
call prepareCall sqlite.prepareStatement
arg prepareCall database database
arg prepareCall sql someSql
run prepareCall
bind ok preparedStatement SqliteStatement prepareCall
bind error prepareError SqlitePrepareFailure prepareCall
ignore void source preparedStatement
""")
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS0106")}
        self.assertIn("prepareError", flagged)


# ==========================================================================
# SS3109  capabilityCoverage.authorityEffectMismatch
# ==========================================================================

class TestAuthorityEffectMismatch(unittest.TestCase):
    def test_authority_matching_effect_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
effect main write console.stdout
authority main write console.stdout
""")
        self.assertNotIn("SS3109", _codes(diagnostics))

    def test_hierarchical_authority_covers_narrower_effect(self) -> None:
        # A grant at `http.request` authorizes a narrower `http.request.method` read.
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
effect main read http.request.method
authority main read http.request
""")
        self.assertNotIn("SS3109", _codes(diagnostics))

    def test_access_verb_mismatch_is_flagged(self) -> None:
        # write effect, read grant — the grant authorizes nothing.
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
effect main write database.account
authority main read database.account
""")
        self.assertIn("SS3109", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3109")[0]
        self.assertEqual(matching.subjectName, "main")
        self.assertEqual(matching.gapEdge, "authority")

    def test_unrelated_path_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
effect main write database.account
authority main write filesystem.config
""")
        self.assertIn("SS3109", _codes(diagnostics))

    def test_operation_without_effects_not_flagged(self) -> None:
        # No declared effects to reconcile against — a different gap, not SS3109.
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
authority main read database.account
""")
        self.assertNotIn("SS3109", _codes(diagnostics))


# ==========================================================================
# SS3110  resourceLifetime.columnUseAfterFree
# ==========================================================================

class TestColumnUseAfterFree(unittest.TestCase):
    _PREAMBLE = """project Kv
operation getValue
output operation getValue Int32
purpose operation getValue "read a column then respond"
effect getValue write http.response
"""

    def test_column_value_used_after_explicit_finalize_is_flagged(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call readValueCall sqlite.columnText
argument readValueCall statement SqliteStatement selectStatement
argument readValueCall columnIndex Int32 columnIndexZero
run readValueCall
bind value storedValue String readValueCall
call finalizeCall sqlite.finalizeStatement
argument finalizeCall statement SqliteStatement selectStatement
run finalizeCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String storedValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertIn("SS3110", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3110")[0]
        self.assertEqual(matching.subjectName, "storedValue")

    def test_column_value_used_after_database_close_in_response_html_is_flagged(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call readValueCall sqlite.columnText
argument readValueCall statement SqliteStatement selectStatement
argument readValueCall columnIndex Int32 columnIndexZero
run readValueCall
bind value storedValue String readValueCall
call closeCall sqlite.closeDatabase
argument closeCall database SqliteDatabase database
run closeCall
call writeHtmlCall http.responseHtml
argument writeHtmlCall response HttpResponse response
argument writeHtmlCall body HtmlFragment storedValue
run writeHtmlCall
bind value writeStatus Int32 writeHtmlCall
return value writeStatus
""")
        self.assertIn("SS3110", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3110")[0]
        self.assertEqual(matching.subjectName, "storedValue")

    def test_defer_release_is_not_flagged(self) -> None:
        # `defer` runs the finalize at scope exit (after the response), so the
        # column value is still valid when used — the idiomatic, safe form.
        diagnostics = _lint_source(self._PREAMBLE + """call readValueCall sqlite.columnText
argument readValueCall statement SqliteStatement selectStatement
argument readValueCall columnIndex Int32 columnIndexZero
run readValueCall
bind value storedValue String readValueCall
defer finalizeDefer sqlite.finalizeStatement selectStatement
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String storedValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertNotIn("SS3110", _codes(diagnostics))

    def test_finalize_of_other_statement_is_not_flagged(self) -> None:
        # Finalizing a DIFFERENT statement does not free this value.
        diagnostics = _lint_source(self._PREAMBLE + """call readValueCall sqlite.columnText
argument readValueCall statement SqliteStatement selectStatement
argument readValueCall columnIndex Int32 columnIndexZero
run readValueCall
bind value storedValue String readValueCall
call finalizeOtherCall sqlite.finalizeStatement
argument finalizeOtherCall statement SqliteStatement otherStatement
run finalizeOtherCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String storedValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertNotIn("SS3110", _codes(diagnostics))

    def test_use_before_finalize_is_not_flagged(self) -> None:
        # Correct ordering: consume the column value, THEN finalize.
        diagnostics = _lint_source(self._PREAMBLE + """call readValueCall sqlite.columnText
argument readValueCall statement SqliteStatement selectStatement
argument readValueCall columnIndex Int32 columnIndexZero
run readValueCall
bind value storedValue String readValueCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String storedValue
run writeCall
bind value writeStatus Int32 writeCall
call finalizeCall sqlite.finalizeStatement
argument finalizeCall statement SqliteStatement selectStatement
run finalizeCall
return value writeStatus
""")
        self.assertNotIn("SS3110", _codes(diagnostics))


# ==========================================================================
# SS3113  resourceLifetime.columnTextOverwrittenBeforeUse
# ==========================================================================

class TestColumnTextOverwrittenBeforeUse(unittest.TestCase):
    _PREAMBLE = """project Kv
operation getRow
output operation getRow Int32
purpose operation getRow "read two text columns then respond"
effect getRow write http.response
call titleCall sqlite.columnText
argument titleCall statement SqliteStatement selectStatement
argument titleCall columnIndex Int32 columnIndexZero
run titleCall
bind value titleValue String titleCall
"""

    def test_column_value_used_after_next_same_statement_read_is_not_flagged(self) -> None:
        # SQLite keeps sibling column values valid until the statement advances
        # or resets; reading column 1 does not invalidate column 0's pointer.
        diagnostics = _lint_source(self._PREAMBLE + """call projectCall sqlite.columnText
argument projectCall statement SqliteStatement selectStatement
argument projectCall columnIndex Int32 columnIndexOne
run projectCall
bind value projectValue String projectCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String titleValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertNotIn("SS3113", _codes(diagnostics))

    def test_consume_before_next_read_is_not_flagged(self) -> None:
        # The idiomatic fix: use/copy titleValue BEFORE the second columnText.
        diagnostics = _lint_source(self._PREAMBLE + """call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String titleValue
run writeCall
bind value writeStatus Int32 writeCall
call projectCall sqlite.columnText
argument projectCall statement SqliteStatement selectStatement
argument projectCall columnIndex Int32 columnIndexOne
run projectCall
bind value projectValue String projectCall
return value writeStatus
""")
        self.assertNotIn("SS3113", _codes(diagnostics))

    def test_read_of_a_different_statement_does_not_flag(self) -> None:
        # A columnText on a DIFFERENT statement does not overwrite this buffer.
        diagnostics = _lint_source(self._PREAMBLE + """call otherCall sqlite.columnText
argument otherCall statement SqliteStatement otherStatement
argument otherCall columnIndex Int32 columnIndexZero
run otherCall
bind value otherValue String otherCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String titleValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertNotIn("SS3113", _codes(diagnostics))

    def test_step_on_same_statement_invalidates_before_use(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call nextRowCall sqlite.stepStatement
argument nextRowCall statement SqliteStatement selectStatement
run nextRowCall
bind ok nextRowResult SqliteStepResult nextRowCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String titleValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertIn("SS3113", _codes(diagnostics))

    def test_reset_of_a_different_statement_does_not_flag(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call resetOtherCall sqlite.resetStatement
argument resetOtherCall statement SqliteStatement otherStatement
run resetOtherCall
bind ok resetOtherResult Int32 resetOtherCall
call writeCall http.responseText
argument writeCall response HttpResponse response
argument writeCall body String titleValue
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
""")
        self.assertNotIn("SS3113", _codes(diagnostics))


# ==========================================================================
# SS3114  resourceLifetime.httpBodyFreedBeforeWrite
# ==========================================================================

class TestHttpResponseBodyFreedBeforeWrite(unittest.TestCase):
    _PREAMBLE = """project Server
operation handle
input operation handle response HttpResponse
output operation handle Int32
purpose operation handle "allocate a response body and write it"
effect handle allocate heap
effect handle free heap
effect handle write http.response
memory handle heap yes
memoryAllocationSource handle allocationCall
storage local immutable allocationSize ByteCount 16
storage local immutable okStatus HttpStatusCode 200
storage local immutable contentType HttpContentType "application/octet-stream"
storage local immutable failureStatus Int32 500
call allocationCall c.malloc
arg allocationCall size allocationSize
runChecked allocationCall ok allocatedBuffer OpaquePointer error allocationError Int32 else allocationFailed
"""

    _WRITE_RESPONSE = """call writeCall http.responseBytes
argument writeCall response HttpResponse response
argument writeCall status HttpStatusCode okStatus
argument writeCall body HttpByteBody allocatedBuffer
argument writeCall bodyLength HttpBodyLength allocationSize
argument writeCall contentType HttpContentType contentType
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
label allocationFailed
return value failureStatus
"""

    def test_explicit_free_before_response_write_is_flagged(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call freeCall c.free
arg freeCall ptr allocatedBuffer
run freeCall
ignoreValue freeCall Void
""" + self._WRITE_RESPONSE)
        self.assertIn("SS3114", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3114")[0]
        self.assertEqual(matching.subjectName, "allocatedBuffer")

    def test_response_write_before_explicit_free_is_not_flagged(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """call writeCall http.responseBytes
argument writeCall response HttpResponse response
argument writeCall status HttpStatusCode okStatus
argument writeCall body HttpByteBody allocatedBuffer
argument writeCall bodyLength HttpBodyLength allocationSize
argument writeCall contentType HttpContentType contentType
run writeCall
bind value writeStatus Int32 writeCall
call freeCall c.free
arg freeCall ptr allocatedBuffer
run freeCall
ignoreValue freeCall Void
return value writeStatus
label allocationFailed
return value failureStatus
""")
        self.assertNotIn("SS3114", _codes(diagnostics))

    def test_defer_release_before_response_write_is_not_flagged(self) -> None:
        diagnostics = _lint_source(self._PREAMBLE + """defer releaseAllocationCall c.free allocatedBuffer
""" + self._WRITE_RESPONSE)
        self.assertNotIn("SS3114", _codes(diagnostics))

    def test_memory_release_before_response_write_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Server
operation handle
input operation handle response HttpResponse
output operation handle Int32
purpose operation handle "allocate a response body and write it"
effect handle allocate heap
effect handle free heap
effect handle write http.response
memory handle heap yes
memoryAllocationSource handle allocationCall
storage local immutable allocationSize ByteCount 16
storage local immutable okStatus HttpStatusCode 200
storage local immutable contentType HttpContentType "application/octet-stream"
storage local immutable failureStatus Int32 500
call allocationCall memory.allocateMemoryBytes
argument allocationCall byteCount ByteCount allocationSize
run allocationCall
bind ok allocatedBuffer OpaquePointer allocationCall
bind error allocationError MemoryAllocationError allocationCall
branch error source allocationCall target allocationFailed
call releaseCall memory.releaseMemoryBytes
argument releaseCall memoryBuffer OpaquePointer allocatedBuffer
run releaseCall
ignore void source releaseCall
call writeCall http.responseBytes
argument writeCall response HttpResponse response
argument writeCall status HttpStatusCode okStatus
argument writeCall body HttpByteBody allocatedBuffer
argument writeCall bodyLength HttpBodyLength allocationSize
argument writeCall contentType HttpContentType contentType
run writeCall
bind value writeStatus Int32 writeCall
return value writeStatus
label allocationFailed
return value failureStatus
""")
        self.assertIn("SS3114", _codes(diagnostics))


# ==========================================================================
# --strict gates on substance, not T4 style/naming advisories (SS4001-SS4004)
# ==========================================================================

class TestStrictExemptsStyleTier(unittest.TestCase):
    # A call name lacking the `Call` suffix yields the T4 SS4001 advisory; the
    # unused errorCase/bind yield T3 advisories.
    _SRC = """project Test
error MainError
errorCase MainError NeverRaised
operation main
output operation main Void
purpose operation main "mixed-tier diagnostics for the strict gate"
storage module immutable leftAddend Int64 1
storage module immutable rightAddend Int64 2
label startMain
call addThem math.addInt64
argument addThem left Int64 leftAddend
argument addThem right Int64 rightAddend
run addThem
bind value sumValue Int64 addThem
return void
"""

    def test_t4_style_only_does_not_fail_strict(self) -> None:
        diagnostics = _lint_source(self._SRC)
        styleOnly = [d for d in diagnostics if d.tier == semlint.Tier.T4_STYLE]
        self.assertTrue(styleOnly, "expected at least one T4 style advisory (SS4001)")
        self.assertIn("SS4001", [d.code for d in styleOnly])
        self.assertFalse(semlint._strict_run_failed(styleOnly))

    def test_substantive_diagnostics_still_fail_strict(self) -> None:
        diagnostics = _lint_source(self._SRC)
        substantive = [d for d in diagnostics if d.tier != semlint.Tier.T4_STYLE]
        self.assertTrue(substantive, "expected at least one non-style diagnostic")
        self.assertTrue(semlint._strict_run_failed(substantive))
        # The full mixed set fails strict because it contains substance.
        self.assertTrue(semlint._strict_run_failed(diagnostics))


# ==========================================================================
# SS3106  errorPathCoverage.hiddenFailure
# ==========================================================================

class TestHiddenFailure(unittest.TestCase):
    def test_console_write_without_error_disposition_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
run writeLineCall
ignoreOk writeLineCall Void
""")
        self.assertIn("SS3106", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3106")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "writeLineCall")
        self.assertIn("bind error", matchingDiagnostic.gapEdge)
        self.assertIn("branch error", matchingDiagnostic.gapEdge)

    def test_console_write_with_full_error_disposition_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailure
operation main
output main Result Void MainError
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
run writeLineCall
ignoreOk writeLineCall Void
bindError writeLineCallError MainError writeLineCall
branchIfError writeLineCall writeFailed
returnOk noResult
label writeFailed
makeError writeLineFailure MainError.WriteFailure
returnError writeLineFailure
""")
        self.assertNotIn("SS3106", _codes(diagnostics))

    def test_sqlite_bind_in_error_handled_transaction_not_flagged(self) -> None:
        # A parameter bind discharged with `ignore void` is NOT flagged when the
        # operation already error-handles the statement lifecycle (prepare here);
        # the bind's failure surfaces at the handled step/exec.
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError DbFailure
operation persistRow
output persistRow Result Void MainError
purpose persistRow "smoke"
invariant persistRow "statement lifecycle is error-handled; binds are best-effort"
call prepareCall sqlite.prepareStatement
arg prepareCall database database
arg prepareCall sql someSql
run prepareCall
bind ok preparedStatement SqliteStatement prepareCall
bind error prepareError SqlitePrepareFailure prepareCall
branch error source prepareCall target dbFailed
call bindValueCall sqlite.bindText
arg bindValueCall statement preparedStatement
arg bindValueCall parameterIndex oneIndex
arg bindValueCall value someValue
run bindValueCall
ignore void source bindValueCall
returnOk noResult
label dbFailed
makeError dbFailure MainError.DbFailure
returnError dbFailure
""")
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS3106")}
        self.assertNotIn("bindValueCall", flagged)

    def test_sqlite_bind_without_handled_lifecycle_still_flagged(self) -> None:
        # No error-handled lifecycle call in the operation -> the bind's own
        # hidden failure is still flagged (suppression must not over-apply).
        diagnostics = _lint_source("""project Test
operation bindOnly
output bindOnly Void
purpose bindOnly "smoke"
call bindValueCall sqlite.bindText
arg bindValueCall statement preparedStatement
arg bindValueCall parameterIndex oneIndex
arg bindValueCall value someValue
run bindValueCall
ignore void source bindValueCall
""")
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS3106")}
        self.assertIn("bindValueCall", flagged)

    def test_run_checked_counts_as_fallible_disposition(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailure
operation main
output main Result Void MainError
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
runChecked writeLineCall ok writeLineStatus Int32 error writeLineError MainError else writeFailed
returnOk noResult
label writeFailed
returnError writeLineError
""")
        self.assertNotIn("SS3106", _codes(diagnostics))

    def test_mixed_run_and_run_checked_same_fallible_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailure
operation main
output main Result Void MainError
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
run writeLineCall
runChecked writeLineCall ok writeLineStatus Int32 error writeLineError MainError else writeFailed
returnOk noResult
label writeFailed
returnError writeLineError
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "writeLineCall"
                and diagnostic.gapEdge == "runOrRunChecked"
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_mixed_start_and_run_checked_same_fallible_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailure
operation main
output main Result Void MainError
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
start writeLineCall
runChecked writeLineCall ok writeLineStatus Int32 error writeLineError MainError else writeFailed
returnOk noResult
label writeFailed
returnError writeLineError
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "writeLineCall"
                and diagnostic.gapEdge == "runOrRunChecked"
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_mixed_start_in_group_and_run_checked_same_fallible_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailure
operation main
output main Result Void MainError
purpose main "smoke"
effect main write console.stdout
taskGroup writeGroup
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
startInGroup writeLineCall writeGroup
runChecked writeLineCall ok writeLineStatus Int32 error writeLineError MainError else writeFailed
awaitGroup writeGroup
returnOk noResult
label writeFailed
returnError writeLineError
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "writeLineCall"
                and diagnostic.gapEdge == "runOrRunChecked"
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_non_wait_set_ignore_error_counts_as_error_disposition(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call firstFetchCall net.fetchText
start firstFetchCall
await firstFetchCall
ignore error source firstFetchCall
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "firstFetchCall"
                and "bind/ignore ok" in diagnostic.gapEdge
                and "bind error" not in diagnostic.gapEdge
                and "branch error" not in diagnostic.gapEdge
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_result_call_bind_value_is_not_success_disposition(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call firstFetchCall net.fetchText
start firstFetchCall
label waitNextResult
await nextResult
case firstFetchCall fetchReady
done allDone
label fetchReady
bind value firstFetchCallResponse HttpTextResponse firstFetchCall
ignore error source firstFetchCall
jump target waitNextResult
label allDone
return void
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "firstFetchCall"
                and "bind/ignore ok" in diagnostic.gapEdge
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_pre_run_fallible_dispositions_do_not_count(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
ignore ok source writeLineCall type Int32
bind error writeLineCallError MainError writeLineCall
branch error source writeLineCall target writeFailed
run writeLineCall
return void
label writeFailed
return void
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "writeLineCall"
                and "bind/ignore ok" in diagnostic.gapEdge
                and "bind error" in diagnostic.gapEdge
                and "branch error" in diagnostic.gapEdge
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_wait_set_pre_wait_ignore_error_does_not_count_as_handler_disposition(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call firstFetchCall net.fetchText
start firstFetchCall
ignore error source firstFetchCall
label waitNextResult
await nextResult
case firstFetchCall fetchReady
done allDone
label fetchReady
bind ok firstFetchCallResponse HttpTextResponse firstFetchCall
jump target waitNextResult
label allDone
return void
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "firstFetchCall"
                and "bind error" in diagnostic.gapEdge
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_pre_wait_call_ignore_error_inside_wait_handler_is_still_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
effect main write console.stdout
storage local immutable someMessageText String "hello"
call writeLineCall console.writeLine
argument writeLineCall text String someMessageText
run writeLineCall
ignore ok source writeLineCall type Void
call asyncCall net.fetchText
start asyncCall
label waitNextResult
await nextResult
case asyncCall asyncReady
done allDone
label asyncReady
ignore error source writeLineCall
jump target waitNextResult
label allDone
return void
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3106")
        self.assertTrue(
            any(
                diagnostic.subjectName == "writeLineCall"
                and "branch error" in diagnostic.gapEdge
                for diagnostic in matchingDiagnostics
            ),
            diagnostics,
        )

    def test_c_status_call_with_ignore_value_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
call writeCharacterCall c.putchar
arg writeCharacterCall character escapeByte
run writeCharacterCall
ignoreValue writeCharacterCall Int32
""")
        self.assertNotIn("SS3106", _codes(diagnostics))

    def test_c_status_call_without_value_disposition_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
call writeCharacterCall c.putchar
arg writeCharacterCall character escapeByte
run writeCharacterCall
""")
        self.assertIn("SS3106", _codes(diagnostics))


# ==========================================================================
# SS3107  metadataConsistency.siblingDrift
# ==========================================================================

class TestSiblingMetadataDrift(unittest.TestCase):
    def test_minority_op_missing_edge_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation operationOne
output operationOne Void
purpose operationOne "first"
memoryHeap operationOne no
memoryStackLimit operationOne 1024
async operationOne no
operation operationTwo
output operationTwo Void
purpose operationTwo "second"
memoryHeap operationTwo no
memoryStackLimit operationTwo 1024
async operationTwo no
operation operationThree
output operationThree Void
purpose operationThree "third"
memoryHeap operationThree no
async operationThree no
""")
        # operationThree lacks memoryStackLimit while operations 1+2 have it
        # (2/3 = 67% adoption → above 60% threshold → drift on operationThree)
        self.assertIn("SS3107", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3107")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "operationThree")
        self.assertEqual(matchingDiagnostic.gapEdge, "memoryStackLimit")

    def test_consistent_metadata_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation operationOne
output operationOne Void
purpose operationOne "first"
memoryHeap operationOne no
async operationOne no
operation operationTwo
output operationTwo Void
purpose operationTwo "second"
memoryHeap operationTwo no
async operationTwo no
operation operationThree
output operationThree Void
purpose operationThree "third"
memoryHeap operationThree no
async operationThree no
""")
        self.assertNotIn("SS3107", _codes(diagnostics))


# ==========================================================================
# SS4001 / SS4002 / SS4003 / SS4004  namingDiscipline.*
# ==========================================================================

class TestNamingDiscipline(unittest.TestCase):
    def test_call_without_call_suffix_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call wA console.writeLine
""")
        self.assertIn("SS4001", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS4001")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "wA")
        self.assertEqual(matchingDiagnostic.tier, semlint.Tier.T4_STYLE)

    def test_call_with_call_suffix_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
""")
        self.assertNotIn("SS4001", _codes(diagnostics))

    def test_bind_error_without_error_suffix_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError SomeFailure
operation main
output main Result Void MainError
purpose main "smoke"
call computeCall math.addInt64
run computeCall
bindError oopsie MainError computeCall
""")
        self.assertIn("SS4002", _codes(diagnostics))

    def test_make_error_without_failure_suffix_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError SomeFailure
operation main
output main Result Void MainError
purpose main "smoke"
makeError shortname MainError.SomeFailure
returnError shortname
""")
        self.assertIn("SS4003", _codes(diagnostics))

    def test_blacklist_name_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const tmp Int64 zeroCount
""")
        self.assertIn("SS4004", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS4004")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "tmp")


# ==========================================================================
# SS4005 / SS4006  top-level .sem sample shape
# ==========================================================================

class TestSemOneZeroSampleShape(unittest.TestCase):
    def test_agent_runtime_one_zero_sem_legacy_const_is_flagged(self) -> None:
        diagnostics = _lint_source_at("sem/fixture.sem", """project Test
target console
runtime AgentRuntime 1.0
entry console main
operation main
output main Void
purpose main "sample"
const legacyExitCode ExitCode 0
call writeLineCall console.writeLine
run writeLineCall
returnOk legacyExitCode
""")
        self.assertIn("SS4005", _codes(diagnostics))

    def test_declaration_only_sem_sample_is_flagged(self) -> None:
        diagnostics = _lint_source_at("sem/fixture.sem", """project Test
target console
runtime AgentRuntime 1.0
entry console main
operation main
output main Void
purpose main "sample"
storage local immutable successfulExitCode ExitCode 0
returnOk successfulExitCode
""")
        self.assertIn("SS4006", _codes(diagnostics))

    def test_executable_sem_sample_shape_not_flagged(self) -> None:
        diagnostics = _lint_source_at("sem/fixture.sem", """project Test
target console
runtime AgentRuntime 1.0
entry console main
operation main
output main Void
purpose main "sample"
storage local immutable messageText String "Hello"
call writeLineCall console.writeLine
arg writeLineCall text messageText
run writeLineCall
returnOk noResult
""")
        self.assertNotIn("SS4005", _codes(diagnostics))
        self.assertNotIn("SS4006", _codes(diagnostics))


# ==========================================================================
# SS0107  unusedDeclaration.const
# ==========================================================================

class TestUnusedConst(unittest.TestCase):
    def test_unreferenced_const_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const dangling Int64 zeroCount
""")
        self.assertIn("SS0107", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0107")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "dangling")

    def test_referenced_const_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Int64
purpose main "smoke"
const exitOkCode Int64 zeroCount
returnValue exitOkCode
""")
        self.assertNotIn("SS0107", _codes(diagnostics))


# ==========================================================================
# SS0108  unusedDeclaration.input
# ==========================================================================

class TestUnusedInput(unittest.TestCase):
    def test_unreferenced_input_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main unusedParameter Int64
output main Void
purpose main "smoke"
""")
        self.assertIn("SS0108", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0108")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unusedParameter")

    def test_referenced_input_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main usedParameter Int64
output main Int64
purpose main "smoke"
returnValue usedParameter
""")
        self.assertNotIn("SS0108", _codes(diagnostics))

    def test_opaque_dependency_input_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main console Console
output main Void
purpose main "console dependency entry"
effect main write console.stdout
""")
        self.assertNotIn("SS0108", _codes(diagnostics))


# ==========================================================================
# SS3111  effectCoverage.undeclaredBodyEffect
# ==========================================================================

class TestUndeclaredBodyEffect(unittest.TestCase):
    def test_console_write_without_declared_effect_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
run writeLineCall
""")
        self.assertIn("SS3111", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3111")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "main")
        self.assertEqual(matchingDiagnostic.gapEdge, "effect")

    def test_declared_effect_satisfies_check(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text someMessageText
run writeLineCall
""")
        self.assertNotIn("SS3111", _codes(diagnostics))

    def test_user_op_call_not_flagged(self) -> None:
        # User-op targets are not in CALL_TARGET_IMPLIED_EFFECTS so the
        # transitive effect isn't asserted here.
        diagnostics = _lint_source("""project Test
operation helper
output helper Void
purpose helper "helper"
operation main
output main Void
purpose main "smoke"
call helperCall helper
run helperCall
""")
        self.assertNotIn("SS3111", _codes(diagnostics))


# ==========================================================================
# SS3112  errorPathCoverage.unknownVariant
# ==========================================================================

class TestUnknownErrorVariant(unittest.TestCase):
    def test_typo_variant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError ConfiguredFailure
operation main
output main Result Void MainError
purpose main "smoke"
makeError mainFailure MainError.ConfigurdFailure
returnError mainFailure
""")
        self.assertIn("SS3112", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3112")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "MainError.ConfigurdFailure")

    def test_correct_variant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError ConfiguredFailure
operation main
output main Result Void MainError
purpose main "smoke"
makeError mainFailure MainError.ConfiguredFailure
returnError mainFailure
""")
        self.assertNotIn("SS3112", _codes(diagnostics))


# ==========================================================================
# C-style performance / memory / layout discipline
# ==========================================================================

class TestDeadStore(unittest.TestCase):
    def test_two_sets_without_read_between_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage local mutable counter Int64 zeroValue
operation main
output main Void
purpose main "smoke"
invariant main "counter mutates"
set local counter firstValue
set local counter secondValue
""")
        self.assertIn("SS3201", _codes(diagnostics))

    def test_read_between_sets_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage local mutable counter Int64 zeroValue
operation main
output main Int64
purpose main "smoke"
invariant main "counter mutates"
set local counter firstValue
returnValue counter
""")
        self.assertNotIn("SS3201", _codes(diagnostics))

    def test_branch_to_failure_label_reads_set_before_next_set(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError WriteFailed ConsoleWriteError
operation main
output main Result Void MainError
purpose main "smoke"
invariant main "latest error is stored before failure branch"
storage local mutable lastConsoleWriteErrorCode ConsoleWriteErrorCode 0
call firstWriteCall console.writeLine
run firstWriteCall
bindError firstWriteError ConsoleWriteError firstWriteCall
set local lastConsoleWriteErrorCode firstWriteError
branchIfError firstWriteCall consoleWriteFailed
call secondWriteCall console.writeLine
run secondWriteCall
bindError secondWriteError ConsoleWriteError secondWriteCall
set local lastConsoleWriteErrorCode secondWriteError
branchIfError secondWriteCall consoleWriteFailed
returnOk noResult
label consoleWriteFailed
makeError consoleWriteFailure MainError.WriteFailed lastConsoleWriteErrorCode
returnError consoleWriteFailure
""")
        self.assertNotIn("SS3201", _codes(diagnostics))

    def test_real_in_block_dead_store_still_flags(self) -> None:
        # Guard the basic-block-local rewrite against over-clearing: a genuine
        # straight-line dead store (two sets, no boundary, no read between) must
        # still flag SS3201.
        diagnostics = _lint_source("""project Test
storage local mutable counter Int64 zeroValue
operation main
output main Void
purpose main "smoke"
invariant main "first counter write is overwritten before any read"
storage local immutable firstValue Int64 1
storage local immutable secondValue Int64 2
set local counter firstValue
set local counter secondValue
returnValue counter
""")
        self.assertIn("SS3201", _codes(diagnostics))

    def test_sets_on_disjoint_branches_not_flagged(self) -> None:
        # The two `set cursorId` writes sit on mutually exclusive branches; the
        # first jumps to the join before the second is reachable, so it is NOT
        # shadowed. A textual set-set scan used to mis-flag this.
        diagnostics = _lint_source("""project Test
operation main
output main Int64
purpose main "smoke"
invariant main "cursorId is set on two disjoint branches that both reach the join"
storage local mutable cursorId Int64 zeroValue
storage local immutable firstValue Int64 1
storage local immutable secondValue Int64 2
storage local immutable threshold Int64 5
storage local immutable probe Int64 3
call condCall math.lessThanInt64
arg condCall left probe
arg condCall right threshold
run condCall
bind value cond Bool condCall
branch if condition cond target altPath
set local cursorId firstValue
jump target joinPath
label altPath
set local cursorId secondValue
jump target joinPath
label joinPath
returnValue cursorId
""")
        self.assertNotIn("SS3201", _codes(diagnostics))

    def test_set_then_jump_to_reading_block_not_flagged(self) -> None:
        # First set's value escapes via the jump to a block that reads it before
        # the textually-later second set is reached.
        diagnostics = _lint_source("""project Test
operation main
output main Int64
purpose main "smoke"
invariant main "first write is read at the jump target before the later write"
storage local mutable cursorId Int64 zeroValue
storage local immutable firstValue Int64 1
storage local immutable secondValue Int64 2
set local cursorId firstValue
jump target useCursor
label resetCursor
set local cursorId secondValue
returnValue cursorId
label useCursor
returnValue cursorId
""")
        self.assertNotIn("SS3201", _codes(diagnostics))


class TestAllocationInLoop(unittest.TestCase):
    def test_malloc_in_back_edge_loop_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main perIterationAllocationCall
label loopHeader
call perIterationAllocationCall c.malloc
arg perIterationAllocationCall size eightBytes
run perIterationAllocationCall
branch loopHeader
""")
        self.assertIn("SS3202", _codes(diagnostics))

    def test_malloc_outside_loop_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main outsideLoopAllocationCall
call outsideLoopAllocationCall c.malloc
arg outsideLoopAllocationCall size eightBytes
run outsideLoopAllocationCall
label loopHeader
branchIf someCondition loopHeader
""")
        self.assertNotIn("SS3202", _codes(diagnostics))


class TestLoopInvariantPureCall(unittest.TestCase):
    def test_pure_call_with_invariant_args_in_loop_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "sum of two constants recomputed each iteration"
storage local immutable leftValue Int64 10
storage local immutable rightValue Int64 20
label loopHeader
call sumCall math.addInt64
arg sumCall left leftValue
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
jump target loopHeader
""")
        self.assertIn("SS3208", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3208")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "sumCall")
        self.assertEqual(matchingDiagnostic.gapEdge, "loopHoist")

    def test_pure_call_with_set_mutated_arg_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "one operand is the mutated loop counter"
storage local immutable rightValue Int64 20
storage local mutable counter Int64 zeroValue
label loopHeader
call sumCall math.addInt64
arg sumCall left counter
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
set local counter sumValue
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_pure_call_with_loop_bound_arg_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "left operand is rebound inside the loop"
storage local immutable rightValue Int64 20
label loopHeader
call loadCall pointer.loadByte
arg loadCall buffer someBuffer
arg loadCall offset rightValue
run loadCall
bind value scannedByte Int64 loadCall
call sumCall math.addInt64
arg sumCall left scannedByte
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_effectful_call_in_loop_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "strlen is not a pure-hoistable target"
storage local immutable someText String "constant"
label loopHeader
call lenCall c.strlen
arg lenCall text someText
run lenCall
bind value textLength Int64 lenCall
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_pure_call_outside_loop_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "constant sum computed once, before any loop"
storage local immutable leftValue Int64 10
storage local immutable rightValue Int64 20
call sumCall math.addInt64
arg sumCall left leftValue
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
label loopHeader
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_conditional_branch_back_edge_is_detected(self) -> None:
        # Back-edge via the canonical `branch if condition C target L` form
        # (target is args[4]); the ad-hoc parser used to miss this entirely.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "loop closes with a conditional branch back to the header"
storage local immutable leftValue Int64 10
storage local immutable rightValue Int64 20
storage local immutable oneValue Int64 1
storage local mutable counter Int64 zeroValue
label loopHeader
call sumCall math.addInt64
arg sumCall left leftValue
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
call advanceCall math.addInt64
arg advanceCall left counter
arg advanceCall right oneValue
run advanceCall
bind value nextCounter Int64 advanceCall
set local counter nextCounter
call keepGoingCall math.lessThanInt64
arg keepGoingCall left counter
arg keepGoingCall right rightValue
run keepGoingCall
bind value keepGoing Bool keepGoingCall
branch if condition keepGoing target loopHeader
""")
        self.assertIn("SS3208", _codes(diagnostics))
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS3208")}
        self.assertIn("sumCall", flagged)
        # advanceCall/keepGoingCall both read the mutated counter — not invariant.
        self.assertNotIn("advanceCall", flagged)
        self.assertNotIn("keepGoingCall", flagged)

    def test_set_memory_scope_mutation_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "operand mutated via set memory, not set local"
storage local immutable rightValue Int64 20
memory main mutable counter Int64 0
label loopHeader
call sumCall math.addInt64
arg sumCall left counter
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
set memory counter sumValue
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_storage_redeclaration_in_loop_not_flagged(self) -> None:
        # A `storage` row inside the loop redefines its name each iteration; if
        # the initializer reads a mutated value the call is NOT invariant.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "derivedLeft is re-declared from the mutated counter each pass"
storage local immutable rightValue Int64 20
storage local mutable counter Int64 zeroValue
label loopHeader
storage local immutable derivedLeft Int64 counter
call sumCall math.addInt64
arg sumCall left derivedLeft
arg sumCall right rightValue
run sumCall
bind value sumValue Int64 sumCall
set local counter sumValue
jump target loopHeader
""")
        self.assertNotIn("SS3208", _codes(diagnostics))

    def test_nested_loop_inner_invariant_call_is_flagged(self) -> None:
        # Mirrors std/sort bubble: a call in the INNER loop whose operands are
        # mutated only in the OUTER loop is invariant w.r.t. the inner loop.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
invariant main "inner length recomputed each inner pass but only changes per outer pass"
storage local immutable arrayLength Int64 64
storage local immutable oneValue Int64 1
storage local immutable zeroValue Int64 0
memory main mutable outerIndex Int64 0
memory main mutable innerIndex Int64 0
label outerHead
call outerDoneCall math.greaterThanOrEqualInt64
arg outerDoneCall left outerIndex
arg outerDoneCall right arrayLength
run outerDoneCall
bind value outerDone Bool outerDoneCall
branch if condition outerDone target doneLabel
set memory innerIndex zeroValue
label innerHead
call innerLengthCall math.subtractInt64
arg innerLengthCall left arrayLength
arg innerLengthCall right outerIndex
run innerLengthCall
bind value innerLength Int64 innerLengthCall
call innerDoneCall math.greaterThanOrEqualInt64
arg innerDoneCall left innerIndex
arg innerDoneCall right innerLength
run innerDoneCall
bind value innerDone Bool innerDoneCall
branch if condition innerDone target outerAdvance
call advanceInnerCall math.addInt64
arg advanceInnerCall left innerIndex
arg advanceInnerCall right oneValue
run advanceInnerCall
bind value nextInner Int64 advanceInnerCall
set memory innerIndex nextInner
jump target innerHead
label outerAdvance
call advanceOuterCall math.addInt64
arg advanceOuterCall left outerIndex
arg advanceOuterCall right oneValue
run advanceOuterCall
bind value nextOuter Int64 advanceOuterCall
set memory outerIndex nextOuter
jump target outerHead
label doneLabel
""")
        flagged = {d.subjectName for d in _diagnostics_with_code(diagnostics, "SS3208")}
        self.assertIn("innerLengthCall", flagged)
        self.assertNotIn("advanceInnerCall", flagged)
        self.assertNotIn("advanceOuterCall", flagged)


class TestStringAccumulatorAppendInLoop(unittest.TestCase):
    def test_strcat_in_back_edge_loop_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryHeap main no
label loopHeader
call appendCall c.strcat
arg appendCall destination accumulator
arg appendCall source fragment
run appendCall
branch loopHeader
""")
        self.assertIn("SS3203", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3203")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "appendCall")
        self.assertEqual(matchingDiagnostic.gapEdge, "cursorBuilder")

    def test_strncat_in_back_edge_loop_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryHeap main no
label loopHeader
call appendCall c.strncat
arg appendCall destination accumulator
arg appendCall source fragment
arg appendCall count fragmentByteCount
run appendCall
branch loopHeader
""")
        self.assertIn("SS3203", _codes(diagnostics))

    def test_strcat_outside_loop_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryHeap main no
call appendCall c.strcat
arg appendCall destination accumulator
arg appendCall source fragment
run appendCall
label loopHeader
branchIf someCondition loopHeader
""")
        self.assertNotIn("SS3203", _codes(diagnostics))


class TestSnprintfInt32OffsetWithoutWidening(unittest.TestCase):
    def test_snprintf_result_added_to_int64_cursor_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
storage local immutable buffer OpaquePointer 0
storage local immutable capacity Int64 256
storage local immutable format String "%s"
storage local immutable text String "row"
storage local mutable writeOffset Int64 0
call formatRowCall c.snprintf
arg formatRowCall buffer buffer
arg formatRowCall size capacity
arg formatRowCall format format
arg formatRowCall first text
run formatRowCall
bind rowBytesWritten Int32 formatRowCall
call afterRowOffsetCall math.addInt64
arg afterRowOffsetCall left writeOffset
arg afterRowOffsetCall right rowBytesWritten
run afterRowOffsetCall
bind afterRowOffset Int64 afterRowOffsetCall
""")
        self.assertIn("SS3205", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3205")[0]
        self.assertEqual(matching.subjectName, "afterRowOffsetCall")
        self.assertEqual(matching.gapEdge, "signExtendInt32ToInt64")

    def test_explicit_widen_before_int64_cursor_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
storage local immutable buffer OpaquePointer 0
storage local immutable capacity Int64 256
storage local immutable format String "%s"
storage local immutable text String "row"
storage local mutable writeOffset Int64 0
call formatRowCall c.snprintf
arg formatRowCall buffer buffer
arg formatRowCall size capacity
arg formatRowCall format format
arg formatRowCall first text
run formatRowCall
bind rowBytesWritten Int32 formatRowCall
call widenRowBytesWrittenCall math.signExtendInt32ToInt64
arg widenRowBytesWrittenCall inputValue rowBytesWritten
run widenRowBytesWrittenCall
bind rowBytesWrittenInt64 Int64 widenRowBytesWrittenCall
call afterRowOffsetCall math.addInt64
arg afterRowOffsetCall left writeOffset
arg afterRowOffsetCall right rowBytesWrittenInt64
run afterRowOffsetCall
bind afterRowOffset Int64 afterRowOffsetCall
""")
        self.assertNotIn("SS3205", _codes(diagnostics))


class TestGuiSelectionHandlerAppendsListItem(unittest.TestCase):
    def test_selection_reader_and_append_in_same_handler_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation markSelectedTask
input markSelectedTask session GuiSession
input markSelectedTask event GuiEvent
output markSelectedTask Int32
purpose markSelectedTask "complete selected task"
invariant markSelectedTask "selection handler"
call selectedIndexCall gui.listBoxSelectedIndex
arg selectedIndexCall session session
arg selectedIndexCall listBox taskListHandle
run selectedIndexCall
bind selectedTaskIndex Int32 selectedIndexCall
call appendCompletedCall gui.listBoxAppendItem
arg appendCompletedCall session session
arg appendCompletedCall listBox taskListHandle
arg appendCompletedCall text completedText
run appendCompletedCall
bind appendStatus Int32 appendCompletedCall
""")
        self.assertIn("SS3206", _codes(diagnostics))

    def test_selection_reader_without_append_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation markSelectedTask
input markSelectedTask session GuiSession
input markSelectedTask event GuiEvent
output markSelectedTask Int32
purpose markSelectedTask "complete selected task"
invariant markSelectedTask "selection handler"
call selectedIndexCall gui.listBoxSelectedIndex
arg selectedIndexCall session session
arg selectedIndexCall listBox taskListHandle
run selectedIndexCall
bind selectedTaskIndex Int32 selectedIndexCall
call statusCall gui.textLabelSetText
arg statusCall session session
arg statusCall textLabel statusLabelHandle
arg statusCall text completedText
run statusCall
bind status Int32 statusCall
""")
        self.assertNotIn("SS3206", _codes(diagnostics))


class TestRowCountMutationUnchecked(unittest.TestCase):
    def test_insert_empty_row_without_unchanged_count_branch_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation handleEnter
output handleEnter Void
purpose handleEnter "insert row"
storage local mutable activeRowCount Int64 4
storage local immutable maxRows Int64 4
call addEmptyAtEndCall insertEmptyRowAt
arg addEmptyAtEndCall rowsBuffer rowsBuffer
arg addEmptyAtEndCall rowLengths rowLengths
arg addEmptyAtEndCall activeRowCount activeRowCount
arg addEmptyAtEndCall rowIndex activeRowCount
arg addEmptyAtEndCall maxRows maxRows
arg addEmptyAtEndCall rowCapacity rowCapacity
run addEmptyAtEndCall
bind rowsAfterAddEmpty Int64 addEmptyAtEndCall
set local activeRowCount rowsAfterAddEmpty
""")
        self.assertIn("SS3207", _codes(diagnostics))

    def test_insert_empty_row_with_unchanged_count_branch_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation handleEnter
output handleEnter Void
purpose handleEnter "insert row"
storage local mutable activeRowCount Int64 4
storage local immutable maxRows Int64 4
call addEmptyAtEndCall insertEmptyRowAt
arg addEmptyAtEndCall rowsBuffer rowsBuffer
arg addEmptyAtEndCall rowLengths rowLengths
arg addEmptyAtEndCall activeRowCount activeRowCount
arg addEmptyAtEndCall rowIndex activeRowCount
arg addEmptyAtEndCall maxRows maxRows
arg addEmptyAtEndCall rowCapacity rowCapacity
run addEmptyAtEndCall
bind rowsAfterAddEmpty Int64 addEmptyAtEndCall
call addEmptyAtEndFailedCheckCall math.equalInt64
arg addEmptyAtEndFailedCheckCall left rowsAfterAddEmpty
arg addEmptyAtEndFailedCheckCall right activeRowCount
run addEmptyAtEndFailedCheckCall
bind addEmptyAtEndFailed Bool addEmptyAtEndFailedCheckCall
branchIf addEmptyAtEndFailed noMutation
set local activeRowCount rowsAfterAddEmpty
label noMutation
returnVoid
""")
        self.assertNotIn("SS3207", _codes(diagnostics))

    def test_insert_empty_row_with_current_branch_syntax_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation handleEnter
output operation handleEnter Void
purpose operation handleEnter "insert row"
storage local mutable activeRowCount Int64 4
storage local immutable maxRows Int64 4
call addEmptyAtEndCall insertEmptyRowAt
argument addEmptyAtEndCall rowsBuffer OpaquePointer rowsBuffer
argument addEmptyAtEndCall rowLengths OpaquePointer rowLengths
argument addEmptyAtEndCall activeRowCount Int64 activeRowCount
argument addEmptyAtEndCall rowIndex Int64 activeRowCount
argument addEmptyAtEndCall maxRows Int64 maxRows
argument addEmptyAtEndCall rowCapacity Int64 rowCapacity
run addEmptyAtEndCall
bind value rowsAfterAddEmpty Int64 addEmptyAtEndCall
call addEmptyAtEndFailedCheckCall math.equalInt64
argument addEmptyAtEndFailedCheckCall left Int64 rowsAfterAddEmpty
argument addEmptyAtEndFailedCheckCall right Int64 activeRowCount
run addEmptyAtEndFailedCheckCall
bind value addEmptyAtEndFailed Bool addEmptyAtEndFailedCheckCall
branch if condition addEmptyAtEndFailed target noMutation
set memory activeRowCount rowsAfterAddEmpty
label noMutation
return void
""")
        self.assertNotIn("SS3207", _codes(diagnostics))


class TestBindThenIgnore(unittest.TestCase):
    def test_bind_then_ignore_value_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call sideEffectCall math.addInt64
run sideEffectCall
bind redundantResult Int64 sideEffectCall
ignoreValue redundantResult Int64
""")
        self.assertIn("SS3204", _codes(diagnostics))


class TestMemoryHeapContradiction(unittest.TestCase):
    def test_no_heap_with_malloc_body_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main no
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
""")
        self.assertIn("SS3301", _codes(diagnostics))

    def test_yes_heap_with_malloc_body_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main allocationCall
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
""")
        self.assertNotIn("SS3301", _codes(diagnostics))


class TestAllocationSourceMissing(unittest.TestCase):
    def test_heap_yes_without_source_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
call allocationCall c.malloc
run allocationCall
""")
        self.assertIn("SS3302", _codes(diagnostics))

    def test_heap_yes_with_source_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main allocationCall
call allocationCall c.malloc
run allocationCall
""")
        self.assertNotIn("SS3302", _codes(diagnostics))


class TestUncheckedHeapAllocation(unittest.TestCase):
    def _allocation_source(self, targetName: str, disposition: str) -> str:
        return f"""project Test
error MainError
errorCase MainError OutOfMemory
operation main
output main Result Void MainError
purpose main "smoke"
effect main allocate heap
authority main heap allocate
memoryHeap main yes
memoryAllocationSource main allocationCall
storage local immutable allocationSize ByteCount 8
call allocationCall {targetName}
arg allocationCall size allocationSize
run allocationCall
{disposition}
"""

    def test_heap_allocators_without_error_disposition_are_flagged(self) -> None:
        for targetName in ("c.malloc", "c.calloc", "c.realloc"):
            with self.subTest(targetName=targetName):
                diagnostics = _lint_source(self._allocation_source(
                    targetName,
                    """defer releaseAllocationCall c.free allocationCall
returnOk noResult""",
                ))
                self.assertIn("SS3305", _codes(diagnostics))
                matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3305")[0]
                self.assertEqual(matchingDiagnostic.subjectName, "allocationCall")
                self.assertEqual(matchingDiagnostic.subjectKind, "call")
                self.assertEqual(matchingDiagnostic.gapEdge, "bindError,branchIfError")
                self.assertIn(targetName, matchingDiagnostic.invariantRule)

    def test_heap_allocator_with_bind_error_and_branch_not_flagged(self) -> None:
        diagnostics = _lint_source(self._allocation_source(
            "c.malloc",
            """bindError allocationCallError MainError allocationCall
branchIfError allocationCall allocationFailed
defer releaseAllocationCall c.free allocationCall
returnOk noResult
label allocationFailed
returnError allocationCallError""",
        ))
        self.assertNotIn("SS3305", _codes(diagnostics))

    def test_heap_allocator_with_run_checked_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError OutOfMemory
operation main
output main Result Void MainError
purpose main "smoke"
effect main allocate heap
authority main heap allocate
memoryHeap main yes
memoryAllocationSource main allocationCall
storage local immutable allocationSize ByteCount 8
call allocationCall c.malloc
arg allocationCall size allocationSize
runChecked allocationCall ok allocatedBuffer OpaquePointer error allocationError MainError else allocationFailed
defer releaseAllocationCall c.free allocatedBuffer
returnOk noResult
label allocationFailed
returnError allocationError
""")
        codes = _codes(diagnostics)
        self.assertNotIn("SS3305", codes)
        self.assertNotIn("SS3106", codes)

    def test_heap_allocator_with_bind_error_only_is_flagged(self) -> None:
        diagnostics = _lint_source(self._allocation_source(
            "c.calloc",
            """bindError allocationCallError MainError allocationCall
defer releaseAllocationCall c.free allocationCall
returnError allocationCallError""",
        ))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3305")[0]
        self.assertEqual(matchingDiagnostic.gapEdge, "branchIfError")

    def test_heap_allocator_with_branch_only_is_flagged(self) -> None:
        diagnostics = _lint_source(self._allocation_source(
            "c.realloc",
            """branchIfError allocationCall allocationFailed
defer releaseAllocationCall c.free allocationCall
returnOk noResult
label allocationFailed
makeError allocationFailure MainError.OutOfMemory
returnError allocationFailure""",
        ))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3305")[0]
        self.assertEqual(matchingDiagnostic.gapEdge, "bindError")


class TestAllocateFreeUnpaired(unittest.TestCase):
    def test_malloc_without_free_defer_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main allocationCall
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
""")
        self.assertIn("SS3303", _codes(diagnostics))

    def test_malloc_with_free_defer_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main allocationCall
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
defer releaseAllocationCall c.free allocationCall
""")
        self.assertNotIn("SS3303", _codes(diagnostics))

    def test_malloc_with_explicit_free_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main allocate heap
effect main free heap
memoryHeap main yes
memoryAllocationSource main allocationCall
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
bindOk allocatedBuffer OpaquePointer allocationCall
call freeAllocationCall c.free
arg freeAllocationCall ptr allocatedBuffer
run freeAllocationCall
ignoreValue freeAllocationCall Void
""")
        self.assertNotIn("SS3303", _codes(diagnostics))

    def test_allocator_transferred_to_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable cachedBuffer OpaquePointer null
operation main
output main Void
purpose main "initialize a process-lifetime buffer cache"
effect main allocate heap
memoryHeap main yes
memoryAllocationSource main allocationCall
storage local immutable eightBytes ByteCount 8
call allocationCall c.malloc
arg allocationCall size eightBytes
run allocationCall
bindOk allocatedBuffer OpaquePointer allocationCall
set storage cachedBuffer allocatedBuffer
returnVoid
""")
        self.assertNotIn("SS3303", _codes(diagnostics))

    def test_allocator_returning_pointer_not_flagged(self) -> None:
        # When the op's output type IS the allocated pointer, ownership
        # transfers to the caller and the lack of free is correct.
        diagnostics = _lint_source("""project Test
operation allocateBuffer
output allocateBuffer OpaquePointer
purpose allocateBuffer "allocator"
effect allocateBuffer allocate heap
memoryHeap allocateBuffer yes
memoryAllocationSource allocateBuffer allocationCall
call allocationCall c.malloc
run allocationCall
bind allocatedBuffer OpaquePointer allocationCall
returnValue allocatedBuffer
""")
        self.assertNotIn("SS3303", _codes(diagnostics))

    def test_allocator_returning_result_pointer_new_output_shape_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error AllocationError
errorCase AllocationError Failed Int32
operation allocateBuffer
output operation allocateBuffer Result OpaquePointer AllocationError
purpose operation allocateBuffer "allocator"
effect allocateBuffer allocate heap
memory allocateBuffer heap yes
memoryAllocationSource allocateBuffer allocationCall
call allocationCall c.malloc
argument allocationCall size ByteCount requestedByteCount
run allocationCall
bind value allocatedBuffer OpaquePointer allocationCall
bind error allocationError Int32 allocationCall
branch error source allocationCall target allocationFailed
return ok allocatedBuffer
label allocationFailed
makeError allocationFailure AllocationError.Failed allocationError
return error allocationFailure
""")
        self.assertNotIn("SS3303", _codes(diagnostics))


class TestStackLimitOverrun(unittest.TestCase):
    def test_tiny_stack_limit_with_many_binds_flagged(self) -> None:
        # Declare a 4-byte limit but bind several Int64 values (8 bytes each)
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryStackLimit main 4
const firstValue Int64 zeroValue
const secondValue Int64 zeroValue
const thirdValue Int64 zeroValue
""")
        self.assertIn("SS3304", _codes(diagnostics))

    def test_generous_stack_limit_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryStackLimit main 8192
const firstValue Int64 zeroValue
""")
        self.assertNotIn("SS3304", _codes(diagnostics))


class TestRecordAlignPowerOfTwo(unittest.TestCase):
    def test_non_power_of_two_align_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
record SomeRecord
recordAlign SomeRecord 3
""")
        self.assertIn("SS3401", _codes(diagnostics))

    def test_power_of_two_align_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
record SomeRecord
recordAlign SomeRecord 8
""")
        self.assertNotIn("SS3401", _codes(diagnostics))


class TestArrayLengthZero(unittest.TestCase):
    def test_zero_length_array_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
arrayType EmptyArray Int64
arrayLength EmptyArray 0
""")
        self.assertIn("SS3404", _codes(diagnostics))

    def test_nonzero_length_array_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
arrayType FixedArray Int64
arrayLength FixedArray 8
""")
        self.assertNotIn("SS3404", _codes(diagnostics))


class TestInlineCapacityWithoutSpillAllocator(unittest.TestCase):
    def test_capacity_without_spill_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue Int64
smallListInlineCapacity TaskQueue 8
""")
        self.assertIn("SS3405", _codes(diagnostics))

    def test_capacity_with_spill_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue Int64
smallListInlineCapacity TaskQueue 8
smallListSpillAllocator TaskQueue heapAllocator
""")
        self.assertNotIn("SS3405", _codes(diagnostics))


class TestLiteralEncodingMissing(unittest.TestCase):
    def test_external_literal_without_encoding_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ConfigBlob ConfigBlobBaseType
literal embeddedConfig ConfigBlob
literalSource embeddedConfig "config.bin"
""")
        self.assertIn("SS3406", _codes(diagnostics))

    def test_external_literal_with_encoding_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ConfigBlob ConfigBlobBaseType
typeLiteralEncoding ConfigBlob utf8
literal embeddedConfig ConfigBlob
literalSource embeddedConfig "config.bin"
""")
        self.assertNotIn("SS3406", _codes(diagnostics))

    def test_primitive_typed_literal_not_flagged(self) -> None:
        # Primitive types are encoded by representation; no
        # typeLiteralEncoding expected.
        diagnostics = _lint_source("""project Test
literal eightByteCount ByteCount
literalSource eightByteCount "size.bin"
""")
        self.assertNotIn("SS3406", _codes(diagnostics))


# ==========================================================================
# Concurrency / resource / type / codec discipline
# ==========================================================================

class TestUnawaitedTaskGroup(unittest.TestCase):
    def test_start_in_group_without_await_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation childOperation
output childOperation Void
purpose childOperation "child"
operation main
output main Void
purpose main "smoke"
taskGroup onboardingGroup
call childCall childOperation
startInGroup childCall onboardingGroup
""")
        self.assertIn("SS3501", _codes(diagnostics))

    def test_start_in_group_with_await_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation childOperation
output childOperation Void
purpose childOperation "child"
operation main
output main Void
purpose main "smoke"
taskGroup onboardingGroup
call childCall childOperation
startInGroup childCall onboardingGroup
awaitGroup onboardingGroup
""")
        self.assertNotIn("SS3501", _codes(diagnostics))


class TestLockWithoutCleanup(unittest.TestCase):
    def test_lock_without_unlock_or_defer_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
""")
        self.assertIn("SS3503", _codes(diagnostics))

    def test_lock_with_unlock_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
unlock accountUpdateMutex
""")
        self.assertNotIn("SS3503", _codes(diagnostics))

    def test_lock_with_defer_unlock_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
defer releaseAccountUpdateMutex unlock accountUpdateMutex
""")
        self.assertNotIn("SS3503", _codes(diagnostics))


class TestUnawaitedSubmitWork(unittest.TestCase):
    def test_submit_without_await_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
submitWork renderTaskWork backgroundPool
""")
        self.assertIn("SS3506", _codes(diagnostics))

    def test_submit_with_await_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        self.assertNotIn("SS3506", _codes(diagnostics))

    def test_submit_missing_work_declaration_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation main
output main Void
purpose main "smoke"
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        self.assertIn("SS3514", _codes(diagnostics))

    def test_submit_work_with_unknown_target_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation main
output main Void
purpose main "smoke"
work renderTaskWork target missingRenderTask
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        self.assertIn("SS3514", _codes(diagnostics))

    def test_submit_work_with_unknown_pool_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
submitWork renderTaskWork missingPool
awaitWork renderTaskWork
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3514")
        self.assertTrue(
            any(diagnostic.gapEdge == "workerPool" for diagnostic in matchingDiagnostics),
            diagnostics,
        )

    def test_submit_work_missing_target_input_arg_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3514")
        self.assertTrue(
            any(diagnostic.gapEdge == "workArg" for diagnostic in matchingDiagnostics),
            diagnostics,
        )

    def test_submit_work_late_target_input_arg_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
submitWork renderTaskWork backgroundPool
workArg renderTaskWork renderInput inputValue
awaitWork renderTaskWork
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3514")
        self.assertTrue(
            any(diagnostic.gapEdge == "workArg" for diagnostic in matchingDiagnostics),
            diagnostics,
        )

    def test_submit_work_late_work_declaration_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
workArg renderTaskWork renderInput inputValue
submitWork renderTaskWork backgroundPool
work renderTaskWork target renderTask
awaitWork renderTaskWork
""")
        matchingDiagnostics = _diagnostics_with_code(diagnostics, "SS3514")
        self.assertTrue(
            any(diagnostic.gapEdge == "workDeclaration" for diagnostic in matchingDiagnostics),
            diagnostics,
        )

    def test_submit_work_late_duplicate_work_after_valid_declaration_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
workArg renderTaskWork renderInput inputValue
submitWork renderTaskWork backgroundPool
work renderTaskWork target renderTask
awaitWork renderTaskWork
""")
        self.assertFalse(
            [
                diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3514")
                if diagnostic.subjectName == "renderTaskWork"
            ],
            diagnostics,
        )

    def test_submit_work_late_duplicate_arg_after_valid_arg_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
workArg renderTaskWork renderInput inputValue
submitWork renderTaskWork backgroundPool
workArg renderTaskWork renderInput replacementInputValue
awaitWork renderTaskWork
""")
        self.assertFalse(
            [
                diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3514")
                if diagnostic.subjectName == "renderTaskWork"
            ],
            diagnostics,
        )

    def test_submit_work_non_target_duplicate_before_submit_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation renderTask
input renderTask renderInput Int64
output renderTask Void
purpose renderTask "render"
operation main
output main Void
purpose main "smoke"
work renderTaskWork target renderTask
workArg renderTaskWork renderInput inputValue
work renderTaskWork
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        self.assertFalse(
            [
                diagnostic for diagnostic in _diagnostics_with_code(diagnostics, "SS3514")
                if diagnostic.subjectName == "renderTaskWork"
            ],
            diagnostics,
        )


class TestSelectWithoutCases(unittest.TestCase):
    def test_zero_case_select_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
select messagePump
""")
        self.assertIn("SS3507", _codes(diagnostics))

    def test_select_with_cases_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
select messagePump
selectCase messagePump readyToken handleReadyLabel
""")
        self.assertNotIn("SS3507", _codes(diagnostics))


class TestSelectCaseReferencesUnknownSelect(unittest.TestCase):
    def test_case_referencing_undeclared_select_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
selectCase undeclaredMessagePump readyToken handleReadyLabel
""")
        self.assertIn("SS3508", _codes(diagnostics))


class TestAsyncCallMissingBoundary(unittest.TestCase):
    def test_await_without_timeout_or_cancel_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation backgroundOperation
output backgroundOperation Void
purpose backgroundOperation "bg"
async backgroundOperation yes
operation main
output main Void
purpose main "smoke"
async main yes
call backgroundCall backgroundOperation
start backgroundCall
await backgroundCall
""")
        self.assertIn("SS3510", _codes(diagnostics))

    def test_await_with_timeout_and_cancel_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation backgroundOperation
output backgroundOperation Void
purpose backgroundOperation "bg"
async backgroundOperation yes
operation main
output main Void
purpose main "smoke"
async main yes
call backgroundCall backgroundOperation
start backgroundCall
timeout backgroundCall fiveSecondDuration
cancelOn backgroundCall mainCancellationToken
await backgroundCall
""")
        self.assertNotIn("SS3510", _codes(diagnostics))


class TestFileHandleNotClosed(unittest.TestCase):
    def test_fopen_without_fclose_defer_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main open file
call openFileHandleCall c.fopen
arg openFileHandleCall path filePath
arg openFileHandleCall mode readMode
run openFileHandleCall
""")
        self.assertIn("SS3901", _codes(diagnostics))

    def test_fopen_with_fclose_defer_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main open file
call openFileHandleCall c.fopen
arg openFileHandleCall path filePath
arg openFileHandleCall mode readMode
run openFileHandleCall
defer releaseFileHandle c.fclose openedFileHandle
""")
        self.assertNotIn("SS3901", _codes(diagnostics))

    def test_fopen_with_explicit_fclose_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main open file
effect main close file
call openFileHandleCall c.fopen
arg openFileHandleCall path filePath
arg openFileHandleCall mode readMode
run openFileHandleCall
bind openedFileHandle FileHandle openFileHandleCall
call closeFileHandleCall c.fclose
arg closeFileHandleCall stream openedFileHandle
run closeFileHandleCall
ignoreValue closeFileHandleCall Int32
""")
        self.assertNotIn("SS3901", _codes(diagnostics))

    def test_handle_returning_op_not_flagged(self) -> None:
        # Op output is FileHandle — ownership transfers to caller.
        diagnostics = _lint_source("""project Test
operation openConfigurationFile
output openConfigurationFile FileHandle
purpose openConfigurationFile "opener"
effect openConfigurationFile open file
call openFileHandleCall c.fopen
arg openFileHandleCall path filePath
arg openFileHandleCall mode readMode
run openFileHandleCall
bind openedFileHandle FileHandle openFileHandleCall
returnValue openedFileHandle
""")
        self.assertNotIn("SS3901", _codes(diagnostics))


class TestSqliteDatabaseFailureCleanupMissing(unittest.TestCase):
    def test_post_open_failure_without_close_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error DbError
errorCase DbError OpenFailed SqliteDatabaseOpenFailure
errorCase DbError SchemaFailed SqliteDatabaseExecFailure
operation openConfiguredDb
output openConfiguredDb Result SqliteDatabase DbError
purpose openConfiguredDb "open and bootstrap sqlite"
storage local immutable databasePath String ":memory:"
storage local immutable schemaSql String "CREATE TABLE t(id INTEGER);"
call openCall sqlite.openDatabase
arg openCall path databasePath
arg openCall mode inMemorySqliteOpenMode
run openCall
bindOk freshDatabase SqliteDatabase openCall
bindError openError DbError.OpenFailed openCall
branchIfError openCall databaseOpenFailed
call applySchemaCall sqlite.exec
arg applySchemaCall database freshDatabase
arg applySchemaCall sql schemaSql
run applySchemaCall
ignoreOk applySchemaCall Void
bindError schemaError DbError.SchemaFailed applySchemaCall
branchIfError applySchemaCall schemaApplyFailed
returnOk freshDatabase
label databaseOpenFailed
returnError openError
label schemaApplyFailed
returnError schemaError
""")
        self.assertIn("SS3905", _codes(diagnostics))

    def test_post_open_failure_with_close_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error DbError
errorCase DbError OpenFailed SqliteDatabaseOpenFailure
errorCase DbError SchemaFailed SqliteDatabaseExecFailure
operation openConfiguredDb
output openConfiguredDb Result SqliteDatabase DbError
purpose openConfiguredDb "open and bootstrap sqlite"
storage local immutable databasePath String ":memory:"
storage local immutable schemaSql String "CREATE TABLE t(id INTEGER);"
call openCall sqlite.openDatabase
arg openCall path databasePath
arg openCall mode inMemorySqliteOpenMode
run openCall
bindOk freshDatabase SqliteDatabase openCall
bindError openError DbError.OpenFailed openCall
branchIfError openCall databaseOpenFailed
call applySchemaCall sqlite.exec
arg applySchemaCall database freshDatabase
arg applySchemaCall sql schemaSql
run applySchemaCall
ignoreOk applySchemaCall Void
bindError schemaError DbError.SchemaFailed applySchemaCall
branchIfError applySchemaCall schemaApplyFailed
returnOk freshDatabase
label databaseOpenFailed
returnError openError
label schemaApplyFailed
call closeFreshDatabaseCall sqlite.closeDatabase
arg closeFreshDatabaseCall database freshDatabase
run closeFreshDatabaseCall
ignoreOk closeFreshDatabaseCall Void
returnError schemaError
""")
        self.assertNotIn("SS3905", _codes(diagnostics))


class TestSqliteMutationEffectUnchecked(unittest.TestCase):
    def _program(self, sqlBody: str, tail: str = "") -> str:
        return f"""project Test
storage module immutable mutateSql SqlText
sql body mutateSql
  {sqlBody}
operation applyMutation
input applyMutation database SqliteDatabase
output applyMutation Void
purpose applyMutation "apply a mutation"
call execCall sqlite.exec
arg execCall database database
arg execCall sql mutateSql
run execCall
ignoreOk execCall Void
{tail}returnVoid
"""

    def test_targeted_update_without_row_count_check_is_flagged(self) -> None:
        diagnostics = _lint_source(self._program(
            "UPDATE tasks SET status = ? WHERE id = ?"))
        self.assertIn("SS3641", _codes(diagnostics))

    def test_targeted_delete_without_row_count_check_is_flagged(self) -> None:
        diagnostics = _lint_source(self._program(
            "DELETE FROM sessions WHERE token = ?"))
        self.assertIn("SS3641", _codes(diagnostics))

    def test_row_count_check_silences_the_nudge(self) -> None:
        diagnostics = _lint_source(self._program(
            "UPDATE tasks SET status = ? WHERE id = ?",
            tail=(
                "call rowsCall sqlite.changedRowCount\n"
                "arg rowsCall database database\n"
                "run rowsCall\n"
                "bind changedRows Int64 rowsCall\n"
            )))
        self.assertNotIn("SS3641", _codes(diagnostics))

    def test_unconditional_bulk_delete_is_not_flagged(self) -> None:
        # `DELETE FROM t` with no WHERE intentionally clears the table; zero
        # affected rows is not a silent-no-op surprise, so do not nudge.
        diagnostics = _lint_source(self._program("DELETE FROM tasks"))
        self.assertNotIn("SS3641", _codes(diagnostics))


class TestSqliteStatementFinalizeMissing(unittest.TestCase):
    def test_prepare_without_finalize_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation queryDb
output queryDb Void
purpose queryDb "query sqlite"
call prepareCall sqlite.prepareStatement
arg prepareCall database database
arg prepareCall sql selectSql
run prepareCall
bindOk statement SqliteStatement prepareCall
bindError prepareError SqliteStatementPrepareFailure prepareCall
branchIfError prepareCall prepareFailed
returnVoid
label prepareFailed
returnVoid
""")
        self.assertIn("SS3906", _codes(diagnostics))

    def test_prepare_with_finalize_defer_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation queryDb
output queryDb Void
purpose queryDb "query sqlite"
call prepareCall sqlite.prepareStatement
arg prepareCall database database
arg prepareCall sql selectSql
run prepareCall
bindOk statement SqliteStatement prepareCall
bindError prepareError SqliteStatementPrepareFailure prepareCall
branchIfError prepareCall prepareFailed
defer finalizeStatementDefer sqlite.finalizeStatement statement
returnVoid
label prepareFailed
returnVoid
""")
        self.assertNotIn("SS3906", _codes(diagnostics))


class TestGuardTokenSourceWithoutRelease(unittest.TestCase):
    def test_source_without_release_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
guardTokenSource accountUpdateGuard acquireAccountUpdateCall
guardTokenProtects accountUpdateGuard accountRecordSlot
""")
        self.assertIn("SS3903", _codes(diagnostics))

    def test_source_with_release_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
guardTokenSource accountUpdateGuard acquireAccountUpdateCall
guardTokenProtects accountUpdateGuard accountRecordSlot
guardTokenRelease accountUpdateGuard releaseAccountUpdate
""")
        self.assertNotIn("SS3903", _codes(diagnostics))


class TestGuardTokenProtectsSharedStateAccess(unittest.TestCase):
    def test_protected_by_without_matching_protects_edge_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount Int64 zeroCount
operation main
output main Void
purpose main "smoke"
invariant main "guarded state access"
set sharedState lookupFailureCount nextLookupFailureCount protectedBy lookupFailureGuard
""")
        self.assertIn("SS3904", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3904")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "lookupFailureGuard")
        self.assertIn("guardTokenProtects", matchingDiagnostic.gapEdge)

    def test_protected_by_matching_protects_edge_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount Int64 zeroCount
guardTokenProtects lookupFailureGuard lookupFailureCount
operation main
output main Void
purpose main "smoke"
invariant main "guarded state access"
set sharedState lookupFailureCount nextLookupFailureCount protectedBy lookupFailureGuard
""")
        self.assertNotIn("SS3904", _codes(diagnostics))


class TestCircularTypeAlias(unittest.TestCase):
    def test_two_step_cycle_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type FirstAlias SecondAlias
type SecondAlias FirstAlias
""")
        self.assertIn("SS3701", _codes(diagnostics))

    def test_terminating_alias_chain_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type UuidV7 Int64
""")
        self.assertNotIn("SS3701", _codes(diagnostics))


class TestJsonCodecIncomplete(unittest.TestCase):
    def test_codec_missing_edges_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
jsonCodec accountRequestCodec
jsonCodecInput accountRequestCodec RequestPayload
""")
        self.assertIn("SS3801", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3801")[0]
        self.assertIn("jsonCodecOutput", matchingDiagnostic.gapEdge)
        self.assertIn("jsonCodecDecodeTarget", matchingDiagnostic.gapEdge)
        self.assertIn("jsonCodecEncodeTarget", matchingDiagnostic.gapEdge)

    def test_complete_codec_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
jsonCodec accountRequestCodec
jsonCodecInput accountRequestCodec RequestPayload
jsonCodecOutput accountRequestCodec ResponsePayload
jsonCodecDecodeTarget accountRequestCodec decodeAccountRequest
jsonCodecEncodeTarget accountRequestCodec encodeAccountRequest
""")
        self.assertNotIn("SS3801", _codes(diagnostics))


# ==========================================================================
# Foundational basics — arity / unresolved references / duplicates
# ==========================================================================

class TestRuntimeBackingMissing(unittest.TestCase):
    def test_record_json_generated_target_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
jsonCodec taskJsonCodec
jsonCodecInput taskJsonCodec String
jsonCodecOutput taskJsonCodec Task
jsonCodecDecodeTarget taskJsonCodec json.decode.Task
jsonCodecEncodeTarget taskJsonCodec json.encode.Task
operation main
output main Void
purpose main "smoke"
call decodeTaskCall json.decode.Task
arg decodeTaskCall value rawTaskJson
run decodeTaskCall
bind decodedTask Int64 decodeTaskCall
""")
        self.assertIn("SS3802", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3802")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "json.decode.Task")
        self.assertEqual(matchingDiagnostic.gapEdge, "runtimeBinding")

    def test_primitive_json_target_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const rawNumber String "42"
call decodeIntegerCall json.decode.Int64
arg decodeIntegerCall value rawNumber
run decodeIntegerCall
bind decodedInteger Int64 decodeIntegerCall
""")
        self.assertNotIn("SS3802", _codes(diagnostics))

    def test_declared_record_json_codec_not_flagged(self) -> None:
        # Regression: a json codec target whose type is a declared `record`
        # lowers to a real structural codec (ss_json_document_* /
        # ss_json_set_object_field_*), so SS3802's "runtime missing" warning is
        # stale and must NOT fire — it previously misled authors into believing
        # record JSON was unimplemented and hand-rolling serialization.
        diagnostics = _lint_source("""project Test
record Point layout row align 8
purpose operation Point "A 2D point."
field Point x Int64
field Point y Int64
operation main
output main Void
purpose main "smoke"
new myPoint Point
fieldSet myPoint x xVal
call encodePointCall json.encode.Point
arg encodePointCall value myPoint
run encodePointCall
bind encodedPoint JsonText encodePointCall
""")
        self.assertNotIn("SS3802", _codes(diagnostics))

    def test_alias_of_record_json_codec_not_flagged(self) -> None:
        # The compiler resolves type aliases before routing, so a `type` alias
        # of a record (`type Coordinate Point`) also lowers to the real codec.
        # The SS3802 skip must resolve the alias head too, or the false positive
        # survives one indirection away.
        diagnostics = _lint_source("""project Test
record Point layout row align 8
purpose operation Point "A 2D point."
field Point x Int64
type Coordinate Point
operation main
output main Void
purpose main "smoke"
new myPoint Point
fieldSet myPoint x xVal
call encodeCoordCall json.encode.Coordinate
arg encodeCoordCall value myPoint
run encodeCoordCall
bind encodedCoord JsonText encodeCoordCall
""")
        self.assertNotIn("SS3802", _codes(diagnostics))

    def test_generic_codec_target_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
codec taskBinaryCodec binary
operation main
output main Void
purpose main "smoke"
call encodeTaskCall taskBinaryCodec.encode
arg encodeTaskCall value taskRecord
run encodeTaskCall
bind encodedTaskBytes Int64 encodeTaskCall
""")
        self.assertIn("SS3803", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3803")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "taskBinaryCodec.encode")

    def test_declared_collection_operation_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
listType TaskList Task
collectionOperation TaskList.append
operation main
output main Void
purpose main "smoke"
call appendTaskCall TaskList.append
arg appendTaskCall list taskList
arg appendTaskCall item taskRecord
run appendTaskCall
bindOk updatedTaskList Int64 appendTaskCall
""")
        self.assertIn("SS3804", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3804")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "TaskList.append")

    def test_declared_map_get_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
mapType TaskMap
mapKey TaskMap TaskId
mapValue TaskMap Task
operation main
output main Void
purpose main "smoke"
call getTaskCall TaskMap.get
arg getTaskCall map taskMap
arg getTaskCall key taskId
run getTaskCall
bindOk taskValue Int64 getTaskCall
""")
        self.assertIn("SS3804", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3804")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "TaskMap.get")

    def test_collection_shaped_target_without_metadata_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call appendTaskCall TaskList.append
arg appendTaskCall list taskList
arg appendTaskCall item taskRecord
run appendTaskCall
bindOk updatedTaskList Int64 appendTaskCall
""")
        self.assertIn("SS3804", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3804")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "TaskList.append")


class TestJsonCrudSafetyRules(unittest.TestCase):
    def test_unguarded_json_access_fires_when_cursor_used_before_error_branch(self) -> None:
        diagnostics = _lint_source("""project Test
operation readTitle
input readTitle document JsonDocument
output readTitle Void
purpose readTitle "generic JSON cursor safety fixture"
storage local immutable titlePath JsonPath ".title"
call cursorAtPathCall json.cursorAtPath
arg cursorAtPathCall document document
arg cursorAtPathCall path titlePath
run cursorAtPathCall
bindOk titleCursor JsonCursor cursorAtPathCall
call kindCall json.cursorKind
arg kindCall document document
arg kindCall cursor titleCursor
run kindCall
branchIfError cursorAtPathCall jsonFailed
label jsonFailed
returnVoid
""")
        self.assertIn("SS3620", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3620")[0]
        self.assertEqual(matching.subjectName, "titleCursor")
        self.assertEqual(matching.gapEdge, "branchIfErrorBeforeCursorUse")

    def test_guarded_json_access_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation readTitle
input readTitle document JsonDocument
output readTitle Void
purpose readTitle "generic JSON cursor safety fixture"
storage local immutable titlePath JsonPath ".title"
call cursorAtPathCall json.cursorAtPath
arg cursorAtPathCall document document
arg cursorAtPathCall path titlePath
run cursorAtPathCall
bindOk titleCursor JsonCursor cursorAtPathCall
branchIfError cursorAtPathCall jsonFailed
call kindCall json.cursorKind
arg kindCall document document
arg kindCall cursor titleCursor
run kindCall
label jsonFailed
returnVoid
""")
        self.assertNotIn("SS3620", _codes(diagnostics))

    def test_document_root_cursor_is_exempt_from_unguarded_access(self) -> None:
        diagnostics = _lint_source("""project Test
operation readRoot
input readRoot document JsonDocument
output readRoot Void
purpose readRoot "json.documentRoot is total"
call rootCall json.documentRoot
arg rootCall document document
run rootCall
bind rootCursor JsonCursor rootCall
call kindCall json.cursorKind
arg kindCall document document
arg kindCall cursor rootCursor
run kindCall
returnVoid
""")
        self.assertNotIn("SS3620", _codes(diagnostics))

    def test_structural_mutators_make_prior_cursor_stale(self) -> None:
        structuralMutators = sorted(semlint.JSON_STRUCTURAL_CURSOR_MUTATOR_TARGETS)
        for targetName in structuralMutators:
            with self.subTest(targetName=targetName):
                diagnostics = _lint_source(f"""project Test
operation mutateDocument
input mutateDocument document JsonDocument
output mutateDocument Void
purpose mutateDocument "generic JSON structural mutation fixture"
storage local immutable titlePath JsonPath ".title"
call cursorAtPathCall json.cursorAtPath
arg cursorAtPathCall document document
arg cursorAtPathCall path titlePath
run cursorAtPathCall
bindOk titleCursor JsonCursor cursorAtPathCall
branchIfError cursorAtPathCall jsonFailed
call mutateCall {targetName}
arg mutateCall document document
arg mutateCall cursor titleCursor
run mutateCall
call kindCall json.cursorKind
arg kindCall document document
arg kindCall cursor titleCursor
run kindCall
label jsonFailed
returnVoid
""")
                self.assertIn("SS3621", _codes(diagnostics))
                matching = _diagnostics_with_code(diagnostics, "SS3621")[0]
                self.assertEqual(matching.subjectName, "titleCursor")
                self.assertEqual(matching.gapEdge, "freshCursorAfterStructuralMutation")

    def test_fresh_cursor_after_structural_mutator_is_not_stale(self) -> None:
        diagnostics = _lint_source("""project Test
operation mutateDocument
input mutateDocument document JsonDocument
output mutateDocument Void
purpose mutateDocument "generic JSON structural mutation fixture"
storage local immutable titlePath JsonPath ".title"
call cursorAtPathCall json.cursorAtPath
arg cursorAtPathCall document document
arg cursorAtPathCall path titlePath
run cursorAtPathCall
bindOk titleCursor JsonCursor cursorAtPathCall
branchIfError cursorAtPathCall jsonFailed
call clearCall json.clearObject
arg clearCall document document
arg clearCall cursor titleCursor
run clearCall
call refreshCursorAtPathCall json.cursorAtPath
arg refreshCursorAtPathCall document document
arg refreshCursorAtPathCall path titlePath
run refreshCursorAtPathCall
bindOk titleCursor JsonCursor refreshCursorAtPathCall
branchIfError refreshCursorAtPathCall jsonFailed
call kindCall json.cursorKind
arg kindCall document document
arg kindCall cursor titleCursor
run kindCall
label jsonFailed
returnVoid
""")
        self.assertNotIn("SS3621", _codes(diagnostics))

    def test_malformed_json_path_literals_block_compile(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable missingBracket JsonPath ".items[0"
storage module immutable emptySegment JsonPath ".items..name"
storage module immutable nonNumericIndex JsonPath ".items[abc]"
storage module immutable missingStepPrefix JsonPath "items[0]"
""")
        self.assertEqual(4, len(_diagnostics_with_code(diagnostics, "SS3622")))
        for matching in _diagnostics_with_code(diagnostics, "SS3622"):
            self.assertTrue(matching.blocksCompile)
            self.assertEqual(matching.tier, semlint.Tier.T1_SPEC)

    def test_valid_json_path_literal_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable nestedPath JsonPath ".items[0].title"
""")
        self.assertNotIn("SS3622", _codes(diagnostics))

    def test_json_snprintf_string_interpolation_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation renderRow
output renderRow Void
purpose renderRow "generic JSON formatting fixture"
storage local immutable buffer OpaquePointer 0
storage local immutable capacity Int64 256
storage local immutable rowFormat String "{\\"title\\":\\"%s\\"}"
storage local immutable title String "hello"
call formatRowCall c.snprintf
arg formatRowCall buffer buffer
arg formatRowCall size capacity
arg formatRowCall format rowFormat
arg formatRowCall first title
run formatRowCall
returnVoid
""")
        self.assertIn("SS3623", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3623")[0]
        self.assertEqual(matching.subjectName, "formatRowCall")
        self.assertEqual(matching.gapEdge, "jsonStringEscape")

    def test_non_json_snprintf_string_interpolation_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation renderText
output renderText Void
purpose renderText "plain text formatting fixture"
storage local immutable buffer OpaquePointer 0
storage local immutable capacity Int64 256
storage local immutable rowFormat String "title=%s"
storage local immutable title String "hello"
call formatRowCall c.snprintf
arg formatRowCall buffer buffer
arg formatRowCall size capacity
arg formatRowCall format rowFormat
arg formatRowCall first title
run formatRowCall
returnVoid
""")
        self.assertNotIn("SS3623", _codes(diagnostics))

    def test_deprecated_json_builder_call_blocks_compile(self) -> None:
        diagnostics = _lint_source("""project Test
operation legacyBuilder
output legacyBuilder Void
purpose legacyBuilder "legacy JSON builder fixture"
storage local immutable capacity ByteCount 128
call createBuilderCall json.createBuilder
arg createBuilderCall capacity capacity
run createBuilderCall
returnVoid
""")
        self.assertIn("SS3624", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3624")[0]
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.subjectName, "createBuilderCall")
        self.assertEqual(matching.fixCandidates[0].name, "migrateToJsonCrudApi")
        self.assertIn("json.stringify.<TypeName>", matching.fixCandidates[0].shape)
        self.assertIn("json.createEmptyDocument", matching.fixCandidates[0].shape)
        self.assertIn("document mutator API", matching.agentHint)

    def test_deprecated_json_finder_call_blocks_compile(self) -> None:
        diagnostics = _lint_source("""project Test
operation legacyFinder
input legacyFinder jsonText JsonText
output legacyFinder Void
purpose legacyFinder "legacy JSON finder fixture"
storage local immutable titlePath JsonPath ".title"
call findTitleCall json.findString
arg findTitleCall json jsonText
arg findTitleCall path titlePath
run findTitleCall
returnVoid
""")
        self.assertIn("SS3625", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3625")[0]
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.subjectName, "findTitleCall")
        self.assertEqual(matching.fixCandidates[0].name, "migrateToJsonCrudApi")
        self.assertIn("json.createDocument", matching.fixCandidates[0].shape)
        self.assertIn("json.cursorAtPath", matching.fixCandidates[0].shape)
        self.assertIn("typed cursor accessor", matching.agentHint)

    def test_json_body_invalid_json_blocks_compile(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable payload JsonText
jsonBody payload
  {"title":}
""")
        self.assertIn("SS3626", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3626")[0]
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.kind, "json.invalidJsonBody")
        self.assertEqual(matching.primary.line, 4)
        self.assertEqual(matching.primary.role, "jsonBodyLine")

    def test_json_body_valid_json_text_is_silent(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable payload JsonText
jsonBody payload
  {"title":"ok","count":1}
operation main
output main Void
purpose main "smoke"
returnVoid
""")
        self.assertNotIn("SS3626", _codes(diagnostics))

    def test_json_body_missing_storage_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
jsonBody payload
  {"ok":true}
""")
        self.assertIn("SS3626", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3626")[0]
        self.assertEqual(matching.kind, "json.orphanJsonBody")

    def test_json_body_record_target_is_type_checked(self) -> None:
        diagnostics = _lint_source("""project Test
record Payload
field Payload title JsonText
storage module immutable payload Payload
jsonBody payload
  {"title":"ok"}
""")
        self.assertNotIn("SS3626", _codes(diagnostics))

    def test_json_body_record_missing_required_field_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
record Payload
field Payload title JsonText
field Payload count Int64
storage module immutable payload Payload
jsonBody payload
  {"title":"ok"}
""")
        self.assertIn("SS3626", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3626")[0]
        self.assertEqual(matching.kind, "json.jsonBodyMissingRequired")

    def test_json_body_record_json_name_and_omit_policy_are_honored(self) -> None:
        diagnostics = _lint_source("""project Test
record Payload
field Payload title JsonText
field Payload count Int64
recordFieldJsonName Payload title "display_title"
recordFieldJsonOmitWhen Payload count zero
storage module immutable payload Payload
jsonBody payload
  {"display_title":"ok"}
""")
        self.assertNotIn("SS3626", _codes(diagnostics))


class TestSqlBodySyntaxIsland(unittest.TestCase):
    def test_sql_body_argument_reference_is_declared_by_unvalued_storage(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable selectSql SqlText
sql body selectSql
  SELECT body FROM markers
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareCall sqlite.prepareStatement
argument prepareCall database SqliteDatabase databaseHandle
argument prepareCall sql SqlText selectSql
""")
        codes = _codes(diagnostics)
        self.assertNotIn("SS3627", codes)
        self.assertNotIn("SS4105", codes)
        self.assertNotIn("SS4301", codes)

    def test_sql_body_string_literal_braces_are_not_holes(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable createSql SqlText
sql body createSql
  CREATE TABLE events (payload TEXT DEFAULT '{}')
""")
        self.assertNotIn("SS3627", _codes(diagnostics))

    def test_sql_body_dynamic_hole_blocks_compile(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable selectSql SqlText
sql body selectSql
  SELECT {unsafeValue}
""")
        self.assertIn("SS3627", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3627")[0]
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.kind, "sql.sqlBodyDynamicHole")
        self.assertEqual(matching.primary.line, 4)
        self.assertEqual(matching.primary.role, "sqlBodyLine")

    def test_inline_sql_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable selectSql SqlText "SELECT 1"
""")
        self.assertIn("SS3628", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3628")[0]
        self.assertEqual(matching.kind, "sql.inlineLiteral")
        self.assertEqual(matching.subjectName, "selectSql")

    def test_http_method_delete_string_is_not_inline_sql(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable methodDelete String "DELETE"
""")
        self.assertNotIn("SS3628", _codes(diagnostics))

    def test_sql_body_redundant_case_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable selectSql SqlText
sql body selectSql
  SELECT CASE WHEN ?1 IS NULL THEN body ELSE body END FROM notes
""")
        self.assertIn("SS3629", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3629")[0]
        self.assertEqual(matching.kind, "sql.redundantCaseBranches")
        self.assertEqual(matching.subjectName, "selectSql")

    def test_sql_body_last_insert_rowid_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable insertEventSql SqlText
sql body insertEventSql
  INSERT INTO events(message_id) SELECT message_id FROM messages WHERE rowid = last_insert_rowid()
""")
        self.assertIn("SS3639", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3639")[0]
        self.assertEqual(matching.kind, "sql.lastInsertRowidFunction")
        self.assertEqual(matching.subjectName, "insertEventSql")
        self.assertIn("INSERT ... RETURNING id", matching.agentHint)
        self.assertIn("sqlite.columnInt64", matching.fixCandidates[0].shape)
        self.assertIn("activity-log INSERT", matching.fixCandidates[0].shape)

    def test_native_last_insert_rowid_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call rowidCall sqlite.lastInsertRowId
argument rowidCall database SqliteDatabase databaseHandle
run rowidCall
bind value insertedRowId SqliteRowId rowidCall
""")
        self.assertIn("SS3639", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3639")[0]
        self.assertEqual(matching.kind, "sqlite.lastInsertRowIdCall")
        self.assertEqual(matching.subjectName, "rowidCall")
        self.assertIn("beginImmediateTransaction/commit", matching.agentHint)
        self.assertIn("sqlite.stepResultIsDone", matching.fixCandidates[0].shape)

    def test_sql_body_returning_generated_id_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable insertMessageSql SqlText
sql body insertMessageSql
  INSERT INTO messages(message_id) VALUES ('msg_' || lower(hex(randomblob(8)))) RETURNING message_id
""")
        self.assertNotIn("SS3639", _codes(diagnostics))

    def test_wide_sql_existence_probe_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable selectSql SqlText
sql body selectSql
  SELECT status, revision FROM auctions WHERE auction_id = ? LIMIT 1
operation main
input operation main databaseHandle SqliteDatabase
input operation main auctionId String
output operation main Void
purpose operation main "smoke"
call prepareCall sqlite.prepareStatement
argument prepareCall database SqliteDatabase databaseHandle
argument prepareCall sql SqlText selectSql
run prepareCall
bind ok statement SqliteStatement prepareCall
call bindAuctionCall sqlite.bindText
argument bindAuctionCall statement SqliteStatement statement
argument bindAuctionCall parameterIndex Int32 1
argument bindAuctionCall value String auctionId
run bindAuctionCall
ignore void source bindAuctionCall
call stepCall sqlite.stepStatement
argument stepCall statement SqliteStatement statement
run stepCall
bind ok stepStatus Int32 stepCall
""")
        self.assertIn("SS3631", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3631")[0]
        self.assertEqual(matching.kind, "sql.wideExistenceProbe")
        self.assertEqual(matching.subjectName, "prepareCall")

    def test_sql_projection_with_column_read_is_not_existence_probe(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable selectSql SqlText
sql body selectSql
  SELECT status, revision FROM auctions WHERE auction_id = ? LIMIT 1
operation main
input operation main databaseHandle SqliteDatabase
input operation main auctionId String
output operation main Void
purpose operation main "smoke"
call prepareCall sqlite.prepareStatement
argument prepareCall database SqliteDatabase databaseHandle
argument prepareCall sql SqlText selectSql
run prepareCall
bind ok statement SqliteStatement prepareCall
call bindAuctionCall sqlite.bindText
argument bindAuctionCall statement SqliteStatement statement
argument bindAuctionCall parameterIndex Int32 1
argument bindAuctionCall value String auctionId
run bindAuctionCall
ignore void source bindAuctionCall
call stepCall sqlite.stepStatement
argument stepCall statement SqliteStatement statement
run stepCall
bind ok stepStatus Int32 stepCall
call statusCall sqlite.columnInt64
argument statusCall statement SqliteStatement statement
argument statusCall columnIndex Int32 0
run statusCall
bind value status Int64 statusCall
""")
        self.assertNotIn("SS3631", _codes(diagnostics))

    def test_sql_write_then_read_same_table_suggests_returning(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable upsertSql SqlText
sql body upsertSql
  INSERT INTO rate_limit_buckets(bucket_key, window_start, count) VALUES (?, ?, 1) ON CONFLICT(bucket_key, window_start) DO UPDATE SET count = count + 1
storage module immutable selectSql SqlText
sql body selectSql
  SELECT count FROM rate_limit_buckets WHERE bucket_key = ? AND window_start = ? LIMIT 1
operation main
input operation main databaseHandle SqliteDatabase
input operation main bucketKey String
output operation main Void
purpose operation main "smoke"
call prepareUpsertCall sqlite.prepareStatement
argument prepareUpsertCall database SqliteDatabase databaseHandle
argument prepareUpsertCall sql SqlText upsertSql
run prepareUpsertCall
bind ok upsertStatement SqliteStatement prepareUpsertCall
call stepUpsertCall sqlite.stepStatement
argument stepUpsertCall statement SqliteStatement upsertStatement
run stepUpsertCall
ignore ok source stepUpsertCall type Int32
call prepareSelectCall sqlite.prepareStatement
argument prepareSelectCall database SqliteDatabase databaseHandle
argument prepareSelectCall sql SqlText selectSql
run prepareSelectCall
bind ok selectStatement SqliteStatement prepareSelectCall
""")
        self.assertIn("SS3632", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3632")[0]
        self.assertEqual(
            matching.kind,
            "sql.writeThenReadReturningOpportunity",
        )
        self.assertEqual(matching.subjectName, "prepareSelectCall")

    def test_sql_write_with_returning_then_read_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable upsertSql SqlText
sql body upsertSql
  INSERT INTO rate_limit_buckets(bucket_key, window_start, count) VALUES (?, ?, 1) ON CONFLICT(bucket_key, window_start) DO UPDATE SET count = count + 1 RETURNING count
storage module immutable selectSql SqlText
sql body selectSql
  SELECT count FROM rate_limit_buckets WHERE bucket_key = ? AND window_start = ? LIMIT 1
operation main
input operation main databaseHandle SqliteDatabase
input operation main bucketKey String
output operation main Void
purpose operation main "smoke"
call prepareUpsertCall sqlite.prepareStatement
argument prepareUpsertCall database SqliteDatabase databaseHandle
argument prepareUpsertCall sql SqlText upsertSql
run prepareUpsertCall
bind ok upsertStatement SqliteStatement prepareUpsertCall
call stepUpsertCall sqlite.stepStatement
argument stepUpsertCall statement SqliteStatement upsertStatement
run stepUpsertCall
bind ok upsertStatus Int32 stepUpsertCall
call readReturnedCountCall sqlite.columnInt64
argument readReturnedCountCall statement SqliteStatement upsertStatement
argument readReturnedCountCall columnIndex Int32 0
run readReturnedCountCall
bind value count Int64 readReturnedCountCall
call prepareSelectCall sqlite.prepareStatement
argument prepareSelectCall database SqliteDatabase databaseHandle
argument prepareSelectCall sql SqlText selectSql
run prepareSelectCall
bind ok selectStatement SqliteStatement prepareSelectCall
""")
        self.assertNotIn("SS3632", _codes(diagnostics))

    def test_multiple_sql_writes_without_transaction_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable insertAuditSql SqlText
sql body insertAuditSql
  INSERT INTO audit_events(actor_id, action) VALUES (?, ?)
storage module immutable insertRequestLogSql SqlText
sql body insertRequestLogSql
  INSERT INTO request_log(route, status) VALUES (?, ?)
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareAuditCall sqlite.prepareStatement
argument prepareAuditCall database SqliteDatabase databaseHandle
argument prepareAuditCall sql SqlText insertAuditSql
run prepareAuditCall
bind ok auditStatement SqliteStatement prepareAuditCall
call stepAuditCall sqlite.stepStatement
argument stepAuditCall statement SqliteStatement auditStatement
run stepAuditCall
ignore ok source stepAuditCall type Int32
call prepareRequestLogCall sqlite.prepareStatement
argument prepareRequestLogCall database SqliteDatabase databaseHandle
argument prepareRequestLogCall sql SqlText insertRequestLogSql
run prepareRequestLogCall
bind ok requestLogStatement SqliteStatement prepareRequestLogCall
call stepRequestLogCall sqlite.stepStatement
argument stepRequestLogCall statement SqliteStatement requestLogStatement
run stepRequestLogCall
ignore ok source stepRequestLogCall type Int32
""")
        self.assertIn("SS3635", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3635")[0]
        self.assertEqual(
            matching.kind,
            "sqlite.multipleWritesWithoutTransaction",
        )
        self.assertEqual(matching.subjectName, "main")

    def test_multiple_sql_writes_with_transaction_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable beginSql SqlText
sql body beginSql
  BEGIN IMMEDIATE
storage module immutable commitSql SqlText
sql body commitSql
  COMMIT
storage module immutable insertAuditSql SqlText
sql body insertAuditSql
  INSERT INTO audit_events(actor_id, action) VALUES (?, ?)
storage module immutable insertRequestLogSql SqlText
sql body insertRequestLogSql
  INSERT INTO request_log(route, status) VALUES (?, ?)
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call beginTxCall sqlite.exec
argument beginTxCall database SqliteDatabase databaseHandle
argument beginTxCall sql SqlText beginSql
run beginTxCall
ignore void source beginTxCall
call prepareAuditCall sqlite.prepareStatement
argument prepareAuditCall database SqliteDatabase databaseHandle
argument prepareAuditCall sql SqlText insertAuditSql
run prepareAuditCall
bind ok auditStatement SqliteStatement prepareAuditCall
call stepAuditCall sqlite.stepStatement
argument stepAuditCall statement SqliteStatement auditStatement
run stepAuditCall
ignore ok source stepAuditCall type Int32
call prepareRequestLogCall sqlite.prepareStatement
argument prepareRequestLogCall database SqliteDatabase databaseHandle
argument prepareRequestLogCall sql SqlText insertRequestLogSql
run prepareRequestLogCall
bind ok requestLogStatement SqliteStatement prepareRequestLogCall
call stepRequestLogCall sqlite.stepStatement
argument stepRequestLogCall statement SqliteStatement requestLogStatement
run stepRequestLogCall
ignore ok source stepRequestLogCall type Int32
call commitTxCall sqlite.exec
argument commitTxCall database SqliteDatabase databaseHandle
argument commitTxCall sql SqlText commitSql
run commitTxCall
ignore void source commitTxCall
""")
        self.assertNotIn("SS3635", _codes(diagnostics))

    def test_returning_statement_drain_is_not_counted_as_second_write(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable insertReturningSql SqlText
sql body insertReturningSql
  INSERT INTO todo(title) VALUES (?) RETURNING id
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareInsertCall sqlite.prepareStatement
argument prepareInsertCall database SqliteDatabase databaseHandle
argument prepareInsertCall sql SqlText insertReturningSql
run prepareInsertCall
bind ok insertStatement SqliteStatement prepareInsertCall
call stepInsertCall sqlite.stepStatement
argument stepInsertCall statement SqliteStatement insertStatement
run stepInsertCall
bind ok insertRowStatus SqliteStepResult stepInsertCall
call readInsertedIdCall sqlite.columnInt64
argument readInsertedIdCall statement SqliteStatement insertStatement
argument readInsertedIdCall columnIndex Int32 0
run readInsertedIdCall
bind value insertedId Int64 readInsertedIdCall
call drainInsertCall sqlite.stepStatement
argument drainInsertCall statement SqliteStatement insertStatement
run drainInsertCall
ignore ok source drainInsertCall type SqliteStepResult
""")
        self.assertNotIn("SS3635", _codes(diagnostics))

    def test_multiple_sql_writes_with_transaction_helpers_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable insertAuditSql SqlText
sql body insertAuditSql
  INSERT INTO audit_events(actor_id, action) VALUES (?, ?)
storage module immutable insertRequestLogSql SqlText
sql body insertRequestLogSql
  INSERT INTO request_log(route, status) VALUES (?, ?)
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call beginTxCall sqlite.beginImmediateTransaction
argument beginTxCall database SqliteDatabase databaseHandle
run beginTxCall
ignore void source beginTxCall
call prepareAuditCall sqlite.prepareStatement
argument prepareAuditCall database SqliteDatabase databaseHandle
argument prepareAuditCall sql SqlText insertAuditSql
run prepareAuditCall
bind ok auditStatement SqliteStatement prepareAuditCall
call stepAuditCall sqlite.stepStatement
argument stepAuditCall statement SqliteStatement auditStatement
run stepAuditCall
ignore ok source stepAuditCall type Int32
call prepareRequestLogCall sqlite.prepareStatement
argument prepareRequestLogCall database SqliteDatabase databaseHandle
argument prepareRequestLogCall sql SqlText insertRequestLogSql
run prepareRequestLogCall
bind ok requestLogStatement SqliteStatement prepareRequestLogCall
call stepRequestLogCall sqlite.stepStatement
argument stepRequestLogCall statement SqliteStatement requestLogStatement
run stepRequestLogCall
ignore ok source stepRequestLogCall type Int32
call commitTxCall sqlite.commitTransaction
argument commitTxCall database SqliteDatabase databaseHandle
run commitTxCall
ignore void source commitTxCall
""")
        self.assertNotIn("SS3635", _codes(diagnostics))

    def test_multiple_sql_writes_with_project_transaction_helpers_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
import tx app.server.persistence_tx
storage module immutable insertAuditSql SqlText
sql body insertAuditSql
  INSERT INTO audit_events(actor_id, action) VALUES (?, ?)
storage module immutable insertRequestLogSql SqlText
sql body insertRequestLogSql
  INSERT INTO request_log(route, status) VALUES (?, ?)
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call beginTxCall tx.beginSqliteCommandTransaction
argument beginTxCall database SqliteDatabase databaseHandle
run beginTxCall
ignore void source beginTxCall
call prepareAuditCall sqlite.prepareStatement
argument prepareAuditCall database SqliteDatabase databaseHandle
argument prepareAuditCall sql SqlText insertAuditSql
run prepareAuditCall
bind ok auditStatement SqliteStatement prepareAuditCall
call stepAuditCall sqlite.stepStatement
argument stepAuditCall statement SqliteStatement auditStatement
run stepAuditCall
ignore ok source stepAuditCall type Int32
call prepareRequestLogCall sqlite.prepareStatement
argument prepareRequestLogCall database SqliteDatabase databaseHandle
argument prepareRequestLogCall sql SqlText insertRequestLogSql
run prepareRequestLogCall
bind ok requestLogStatement SqliteStatement prepareRequestLogCall
call stepRequestLogCall sqlite.stepStatement
argument stepRequestLogCall statement SqliteStatement requestLogStatement
run stepRequestLogCall
ignore ok source stepRequestLogCall type Int32
call commitTxCall tx.commitSqliteCommandTransaction
argument commitTxCall database SqliteDatabase databaseHandle
run commitTxCall
ignore void source commitTxCall
""")
        self.assertNotIn("SS3635", _codes(diagnostics))

    def test_multiple_sql_writes_via_declared_sql_forwarder_transaction_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable beginSql SqlText
sql body beginSql
  BEGIN IMMEDIATE
storage module immutable commitSql SqlText
sql body commitSql
  COMMIT
storage module immutable insertAuditSql SqlText
sql body insertAuditSql
  INSERT INTO audit_events(actor_id, action) VALUES (?, ?)
storage module immutable insertRequestLogSql SqlText
sql body insertRequestLogSql
  INSERT INTO request_log(route, status) VALUES (?, ?)
operation runStatement
input operation runStatement databaseHandle SqliteDatabase
input operation runStatement sql SqlText
output operation runStatement Void
purpose operation runStatement "smoke"
sqliteSqlForwarder runStatement sql
call prepareCall sqlite.prepareStatement
argument prepareCall database SqliteDatabase databaseHandle
argument prepareCall sql SqlText sql
run prepareCall
bind ok preparedStatement SqliteStatement prepareCall
call stepCall sqlite.stepStatement
argument stepCall statement SqliteStatement preparedStatement
run stepCall
ignore ok source stepCall type Int32
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call beginCall runStatement
argument beginCall databaseHandle SqliteDatabase databaseHandle
argument beginCall sql SqlText beginSql
run beginCall
ignore void source beginCall
call auditCall runStatement
argument auditCall databaseHandle SqliteDatabase databaseHandle
argument auditCall sql SqlText insertAuditSql
run auditCall
ignore void source auditCall
call requestLogCall runStatement
argument requestLogCall databaseHandle SqliteDatabase databaseHandle
argument requestLogCall sql SqlText insertRequestLogSql
run requestLogCall
ignore void source requestLogCall
call commitCall runStatement
argument commitCall databaseHandle SqliteDatabase databaseHandle
argument commitCall sql SqlText commitSql
run commitCall
ignore void source commitCall
""")
        self.assertNotIn("SS3635", _codes(diagnostics))

    def test_returning_statement_commit_without_drain_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable commitSql SqlText
sql body commitSql
  COMMIT
storage module immutable upsertSql SqlText
sql body upsertSql
  INSERT INTO rate_limit_buckets(bucket_key, count) VALUES (?, 1) ON CONFLICT(bucket_key) DO UPDATE SET count = count + 1 RETURNING count
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareUpsertCall sqlite.prepareStatement
argument prepareUpsertCall database SqliteDatabase databaseHandle
argument prepareUpsertCall sql SqlText upsertSql
run prepareUpsertCall
bind ok upsertStatement SqliteStatement prepareUpsertCall
call stepUpsertCall sqlite.stepStatement
argument stepUpsertCall statement SqliteStatement upsertStatement
run stepUpsertCall
bind ok upsertStatus Int32 stepUpsertCall
call readReturnedCountCall sqlite.columnInt64
argument readReturnedCountCall statement SqliteStatement upsertStatement
argument readReturnedCountCall columnIndex Int32 0
run readReturnedCountCall
bind value count Int64 readReturnedCountCall
call commitTxCall sqlite.exec
argument commitTxCall database SqliteDatabase databaseHandle
argument commitTxCall sql SqlText commitSql
run commitTxCall
ignore void source commitTxCall
""")
        self.assertIn("SS3636", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3636")[0]
        self.assertEqual(
            matching.kind,
            "sqlite.returningStatementNotDrainedBeforeCommit",
        )
        self.assertEqual(matching.subjectName, "commitTxCall")

    def test_returning_statement_drained_before_commit_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable commitSql SqlText
sql body commitSql
  COMMIT
storage module immutable upsertSql SqlText
sql body upsertSql
  INSERT INTO rate_limit_buckets(bucket_key, count) VALUES (?, 1) ON CONFLICT(bucket_key) DO UPDATE SET count = count + 1 RETURNING count
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareUpsertCall sqlite.prepareStatement
argument prepareUpsertCall database SqliteDatabase databaseHandle
argument prepareUpsertCall sql SqlText upsertSql
run prepareUpsertCall
bind ok upsertStatement SqliteStatement prepareUpsertCall
call stepUpsertCall sqlite.stepStatement
argument stepUpsertCall statement SqliteStatement upsertStatement
run stepUpsertCall
bind ok upsertStatus Int32 stepUpsertCall
call readReturnedCountCall sqlite.columnInt64
argument readReturnedCountCall statement SqliteStatement upsertStatement
argument readReturnedCountCall columnIndex Int32 0
run readReturnedCountCall
bind value count Int64 readReturnedCountCall
call drainUpsertCall sqlite.stepStatement
argument drainUpsertCall statement SqliteStatement upsertStatement
run drainUpsertCall
ignore ok source drainUpsertCall type Int32
call commitTxCall sqlite.exec
argument commitTxCall database SqliteDatabase databaseHandle
argument commitTxCall sql SqlText commitSql
run commitTxCall
ignore void source commitTxCall
""")
        self.assertNotIn("SS3636", _codes(diagnostics))

    def test_process_environment_read_without_cache_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation resolveSecret
output operation resolveSecret String
effect resolveSecret read process.environment
purpose operation resolveSecret "smoke"
storage module immutable secretEnvName String "APP_SECRET"
call getenvSecretCall c.getenv
argument getenvSecretCall name String secretEnvName
run getenvSecretCall
bind value secret String getenvSecretCall
return value secret
""")
        self.assertIn("SS3633", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3633")[0]
        self.assertEqual(matching.kind, "process.getenvUncached")
        self.assertEqual(matching.subjectName, "getenvSecretCall")

    def test_process_environment_read_with_cache_guard_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable cachedSecret String ""
storage module mutable cachedSecretReady Int32 0
operation resolveSecret
output operation resolveSecret String
effect resolveSecret read process.environment
purpose operation resolveSecret "smoke"
storage module immutable secretEnvName String "APP_SECRET"
call readyCall math.equalInt32
argument readyCall left Int32 cachedSecretReady
argument readyCall right Int32 1
run readyCall
bind value ready Bool readyCall
branch if condition ready target returnCached
call getenvSecretCall c.getenv
argument getenvSecretCall name String secretEnvName
run getenvSecretCall
bind value secret String getenvSecretCall
set storage cachedSecret secret
set storage cachedSecretReady 1
return value cachedSecret
label returnCached
return value cachedSecret
""")
        self.assertNotIn("SS3633", _codes(diagnostics))

    def test_repeated_request_time_read_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import http standard.http
operation main
input operation main request HttpRequest
output operation main Void
purpose operation main "smoke"
call requestNowCall http.nowMillis
run requestNowCall
bind value requestNow Int64 requestNowCall
call laterNowCall http.nowMillis
run laterNowCall
bind value laterNow Int64 laterNowCall
""")
        self.assertIn("SS3637", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3637")[0]
        self.assertEqual(matching.kind, "performance.repeatedRequestTimeRead")
        self.assertEqual(matching.subjectName, "laterNowCall")

    def test_single_request_time_read_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import http standard.http
operation main
input operation main request HttpRequest
output operation main Void
purpose operation main "smoke"
call requestNowCall http.nowMillis
run requestNowCall
bind value requestNow Int64 requestNowCall
return void
""")
        self.assertNotIn("SS3637", _codes(diagnostics))

    def test_idempotency_replay_body_classification_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable selectIdem SqlText
sql body selectIdem
  SELECT request_hash, response_json, response_status FROM idempotency_keys WHERE scope = ? LIMIT 1
storage module immutable conflictBody String "{}"
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareIdemCall sqlite.prepareStatement
argument prepareIdemCall database SqliteDatabase databaseHandle
argument prepareIdemCall sql SqlText selectIdem
run prepareIdemCall
bind ok idemStatement SqliteStatement prepareIdemCall
call readReplayBodyCall sqlite.columnText
argument readReplayBodyCall statement SqliteStatement idemStatement
argument readReplayBodyCall columnIndex Int32 1
run readReplayBodyCall
bind value replayBody String readReplayBodyCall
call compareReplayBodyCall c.strcmp
argument compareReplayBodyCall left String replayBody
argument compareReplayBodyCall right String conflictBody
run compareReplayBodyCall
bind value compareResult Int32 compareReplayBodyCall
""")
        self.assertIn("SS3638", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3638")[0]
        self.assertEqual(
            matching.kind,
            "performance.idempotencyReplayBodyClassification",
        )
        self.assertEqual(matching.subjectName, "compareReplayBodyCall")

    def test_idempotency_replay_status_branch_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
storage module immutable selectIdem SqlText
sql body selectIdem
  SELECT request_hash, response_json, response_status FROM idempotency_keys WHERE scope = ? LIMIT 1
operation main
input operation main databaseHandle SqliteDatabase
output operation main Void
purpose operation main "smoke"
call prepareIdemCall sqlite.prepareStatement
argument prepareIdemCall database SqliteDatabase databaseHandle
argument prepareIdemCall sql SqlText selectIdem
run prepareIdemCall
bind ok idemStatement SqliteStatement prepareIdemCall
call readReplayStatusCall sqlite.columnInt64
argument readReplayStatusCall statement SqliteStatement idemStatement
argument readReplayStatusCall columnIndex Int32 2
run readReplayStatusCall
bind value replayStatus Int64 readReplayStatusCall
call replayConflictCall math.equalInt64
argument replayConflictCall left Int64 replayStatus
argument replayConflictCall right Int64 409
run replayConflictCall
bind value replayConflict Bool replayConflictCall
""")
        self.assertNotIn("SS3638", _codes(diagnostics))

    def test_non_sql_method_literal_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable methods String "GET, POST, PUT, PATCH, DELETE, OPTIONS"
""")
        self.assertNotIn("SS3628", _codes(diagnostics))


class TestArgumentArity(unittest.TestCase):
    def test_operation_without_name_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation
""")
        self.assertIn("SS0002", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0002")[0]
        self.assertTrue(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, semlint.Tier.T0_PARSE)

    def test_arg_with_only_two_tokens_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
arg writeCall console
""")
        self.assertIn("SS0002", _codes(diagnostics))

    def test_correctly_arity_lines_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
call writeCall console.writeLine
argument writeCall console Console consoleHandle
""")
        self.assertNotIn("SS0002", _codes(diagnostics))


class TestSemanticSyntaxCutover(unittest.TestCase):
    def test_new_cutover_rows_are_accepted_by_grammar_passes(self) -> None:
        diagnostics = _lint_source("""project Test
import math standard.math
type MainResult result ok ExitCode error MainError
error MainError
errorCase MainError Failed
storage module immutable okCode ExitCode 0
html template CardTemplate
html body template CardTemplate
  <h1>{{titleText}}</h1>
operation main
input operation main console Console
output operation main MainResult
purpose operation main "smoke"
effect main write console.stdout
authority main write console.stdout
memory main heap no
memory main mutable counter Int64 0
call writeCall console.writeLine
argument writeCall console Console console
argument writeCall text String someMessageText
run writeCall
bind error writeCallError MainError writeCall
branch error source writeCall target failed
branch else target succeeded
label succeeded
return ok okCode
label failed
makeError writeFailure MainError.Failed
return error writeFailure
""")
        self.assertNotIn("SS0002", _codes(diagnostics))
        self.assertNotIn("SS0003", _codes(diagnostics))

    def test_replaced_old_rows_emit_cutover_error(self) -> None:
        diagnostics = _lint_source("""project Test
importModule math standard.math
operation main
output main Void
purpose main "old fixture"
memoryHeap main no
htmlTemplate CardTemplate
htmlArg CardTemplate titleText String
htmlBody CardTemplate
  <h1>{{titleText}}</h1>
arg callName param value
bind result Int64 callName
bindOk ok Int64 callName
bindError bad MainError callName
branchIf condition done
branchIfError callName failed
branch done
returnValue result
returnOk ok
returnError bad
returnVoid
ignoreValue callName Int64
ignoreOk callName Int64
ignoreError callName
""")
        cutoverSubjects = {
            diagnostic.subjectName
            for diagnostic in _diagnostics_with_code(diagnostics, "SS0003")
        }
        self.assertIn("importModule", cutoverSubjects)
        self.assertIn("arg", cutoverSubjects)
        self.assertIn("htmlTemplate", cutoverSubjects)
        self.assertIn("htmlArg", cutoverSubjects)
        self.assertIn("htmlBody", cutoverSubjects)
        self.assertIn("bind", cutoverSubjects)
        self.assertIn("branchIf", cutoverSubjects)
        self.assertIn("returnVoid", cutoverSubjects)
        self.assertIn("ignoreError", cutoverSubjects)

    def test_set_storage_is_canonical_mutation_form(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable requestCount Int64 0
operation main
output operation main Void
purpose operation main "canonical set storage fixture"
storage local immutable nextCount Int64 1
set storage requestCount nextCount
return void
""")
        self.assertNotIn("SS0003", _codes(diagnostics))

    def test_set_local_and_set_module_ownedby_emit_cutover_error(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "stale set forms fixture"
storage local immutable nextCount Int64 1
set local requestCount nextCount
set module requestCount nextCount ownedBy moduleOwner
return void
""")
        cutover = _diagnostics_with_code(diagnostics, "SS0003")
        self.assertEqual(len(cutover), 2)
        self.assertTrue(all(diagnostic.subjectName == "set" for diagnostic in cutover))
        self.assertTrue(any("set local" in diagnostic.intentSlogan for diagnostic in cutover))
        self.assertTrue(any("ownedBy" in diagnostic.invariantRule for diagnostic in cutover))
        fixShapes = [
            fix.shape
            for diagnostic in cutover
            for fix in diagnostic.fixCandidates
            if fix.name == "rewriteToNewSyntax"
        ]
        self.assertIn("set storage requestCount nextCount", fixShapes)

    def test_branch_if_condition_must_be_bool(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
memory main immutable count Int64 1
branch if condition count target done
label done
return void
""")
        self.assertIn("SS4106", _codes(diagnostics))

    def test_branch_error_requires_fallible_source(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
call addCall math.addInt64
branch error source addCall target failed
label failed
return void
""")
        self.assertIn("SS4107", _codes(diagnostics))

    def test_branch_error_accepts_user_result_operation(self) -> None:
        diagnostics = _lint_source("""project Test
error ProbeError
errorCase ProbeError Failed Int32
operation maybeFail
output operation maybeFail Result Int64 ProbeError
purpose operation maybeFail "smoke"
storage local immutable resultValue Int64 7
return ok resultValue
operation main
output operation main ExitCode
purpose operation main "smoke"
call maybeFailCall maybeFail
run maybeFailCall
bind ok okValue Int64 maybeFailCall
bind error failValue ProbeError maybeFailCall
branch error source maybeFailCall target failed
storage local immutable successExit ExitCode 0
return value successExit
label failed
storage local immutable failedExit ExitCode 1
return value failedExit
""")
        self.assertNotIn("SS4107", _codes(diagnostics))

    def test_branch_error_accepts_nested_user_result_operations(self) -> None:
        diagnostics = _lint_source("""project Test
error ProbeError
errorCase ProbeError Failed Int32
operation leafHelper
output operation leafHelper Result Int64 ProbeError
purpose operation leafHelper "smoke"
storage local immutable resultValue Int64 7
return ok resultValue
operation middleHelper
output operation middleHelper Result Int64 ProbeError
purpose operation middleHelper "smoke"
call leafCall leafHelper
run leafCall
bind ok leafOkValue Int64 leafCall
bind error leafError ProbeError leafCall
branch error source leafCall target leafFailed
return ok leafOkValue
label leafFailed
return error leafError
operation outerHelper
output operation outerHelper Result Int64 ProbeError
purpose operation outerHelper "smoke"
call middleCall middleHelper
run middleCall
bind ok middleOkValue Int64 middleCall
bind error middleError ProbeError middleCall
branch error source middleCall target middleFailed
return ok middleOkValue
label middleFailed
return error middleError
operation main
output operation main ExitCode
purpose operation main "smoke"
call outerCall outerHelper
run outerCall
bind ok outerOkValue Int64 outerCall
bind error outerError ProbeError outerCall
branch error source outerCall target outerFailed
storage local immutable successExit ExitCode 0
return value successExit
label outerFailed
storage local immutable failedExit ExitCode 1
return value failedExit
""")
        self.assertNotIn("SS4107", _codes(diagnostics))

    def test_branch_else_must_be_physically_adjacent(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
memory main immutable isReady Bool true
branch if condition isReady target ready
# comment breaks adjacency
branch else target notReady
label ready
return void
label notReady
return void
""")
        self.assertIn("SS4108", _codes(diagnostics))

    def test_jump_target_resolution_uses_new_shape(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
jump target missingLabel
""")
        self.assertIn("SS4102", _codes(diagnostics))

    def test_argument_repeated_type_must_match_signature(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output operation main Void
purpose operation main "smoke"
memory main immutable leftValue Int64 1
call addCall math.addInt64
argument addCall left Bool leftValue
""")
        self.assertIn("SS4301", _codes(diagnostics))


class TestUnresolvedReferences(unittest.TestCase):
    def test_arg_referencing_undeclared_call_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
arg neverDeclaredCall consoleArgName consoleHandle
""")
        self.assertIn("SS4101", _codes(diagnostics))

    def test_arg_referencing_undeclared_value_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Int64 1
call addCall math.addInt64
arg addCall left leftValue
arg addCall right typoValue
run addCall
""")
        self.assertIn("SS4105", _codes(diagnostics))

    def test_run_referencing_undeclared_call_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
run mistypedCallName
""")
        self.assertIn("SS4101", _codes(diagnostics))

    def test_branch_referencing_undeclared_label_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
branch undeclaredLabelName
""")
        self.assertIn("SS4102", _codes(diagnostics))

    def test_branchIfError_referencing_undeclared_label_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
branchIfError writeCall labelTypoName
""")
        self.assertIn("SS4102", _codes(diagnostics))

    def test_useCapability_referencing_undeclared_capability_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
useCapability main typoedCapabilityName
""")
        self.assertIn("SS4103", _codes(diagnostics))

    def test_attachment_referencing_undeclared_operation_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
purpose neverDeclaredAnything "this subject doesn't exist anywhere"
""")
        self.assertIn("SS4104", _codes(diagnostics))

    def test_purpose_on_webserver_not_flagged(self) -> None:
        # Pre-P1 this incorrectly tripped SS4104 because webServer subjects
        # weren't in the linter's attachment-subject table even though they
        # legitimately carry purpose/invariant/warning per docs/reference/syntax-inventory.md.
        diagnostics = _lint_source("""project Test
webServer demoServer
purpose demoServer "smoke test for non-operation purpose subjects"
""")
        self.assertNotIn("SS4104", _codes(diagnostics))

    def test_purpose_on_capability_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleWriteCapability console.stdout write
purpose consoleWriteCapability "describe the capability's authority"
""")
        self.assertNotIn("SS4104", _codes(diagnostics))

    def test_purpose_on_module_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable retryAttemptLimit Int64 5
purpose retryAttemptLimit "max attempts before giving up on a transient failure"
""")
        self.assertNotIn("SS4104", _codes(diagnostics))

    def test_purpose_on_timeout_budget_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
timeoutBudget requestTimeoutBudget DurationMilliseconds 2000
purpose requestTimeoutBudget "per-request budget the future preemptive runtime will enforce"
""")
        self.assertNotIn("SS4104", _codes(diagnostics))

    def test_purpose_on_enum_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
purpose SaveStatus "result domain for the save operation"
""")
        self.assertNotIn("SS4104", _codes(diagnostics))

    def test_operation_body_verb_on_webserver_flagged_with_SS4105(self) -> None:
        # `effect` on a webServer subject is nonsense — effects are an
        # operation-body concept. The subject EXISTS, so this isn't SS4104;
        # the new SS4105 (attachmentSubjectKindMismatch) catches it.
        diagnostics = _lint_source("""project Test
webServer demoServer
effect demoServer write http.response
""")
        self.assertIn("SS4105", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS4105")[0]
        self.assertEqual(matching.subjectName, "demoServer")
        self.assertEqual(matching.gapEdge, "operationDeclaration")
        self.assertTrue(matching.blocksCompile)

    def test_operation_body_verb_on_capability_flagged_with_SS4105(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleWriteCapability console.stdout write
input consoleWriteCapability badInput Int64
""")
        self.assertIn("SS4105", _codes(diagnostics))

    def test_purpose_on_operation_still_works(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "normal operation purpose attachment"
""")
        # No SS4104 / SS4105 — operation is the canonical attachment subject.
        codes = _codes(diagnostics)
        self.assertNotIn("SS4104", codes)
        self.assertNotIn("SS4105", codes)

    def test_all_references_resolved_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleWriteCapability console.stdout write
operation main
output main Void
purpose main "smoke"
useCapability main consoleWriteCapability
label happyPath
branch happyPath
""")
        unresolvedCodes = {"SS4101", "SS4102", "SS4103", "SS4104"}
        seenCodes = set(_codes(diagnostics))
        self.assertFalse(unresolvedCodes & seenCodes,
                         f"unexpected unresolved-ref diagnostics: {unresolvedCodes & seenCodes}")


class TestDuplicateDeclarations(unittest.TestCase):
    def test_duplicate_operation_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "first"
operation main
output main Void
purpose main "duplicate"
""")
        self.assertIn("SS4201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS4201")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "main")
        self.assertEqual(matchingDiagnostic.subjectKind, "operation")
        self.assertTrue(matchingDiagnostic.blocksCompile)

    def test_duplicate_label_within_op_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label sameLabel
label sameLabel
""")
        self.assertIn("SS4201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS4201")[0]
        self.assertEqual(matchingDiagnostic.subjectKind, "label")

    def test_same_label_different_ops_not_flagged(self) -> None:
        # Labels are op-scoped; same name in different ops is fine.
        diagnostics = _lint_source("""project Test
operation operationOne
output operationOne Void
purpose operationOne "first"
label startLabel
operation operationTwo
output operationTwo Void
purpose operationTwo "second"
label startLabel
""")
        labelDuplicates = [
            d for d in diagnostics
            if d.code == "SS4201" and d.subjectKind == "label"
        ]
        self.assertFalse(labelDuplicates)

    def test_duplicate_type_alias_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type AccountId Int64
""")
        self.assertIn("SS4201", _codes(diagnostics))


# ==========================================================================
# SS4301  typeIntegrity.argumentTypeMismatch
# ==========================================================================

class TestArgumentTypeMismatch(unittest.TestCase):
    def test_passing_bool_where_string_expected_flagged(self) -> None:
        # Bool is in the integer family (sext to Int64 on the wire);
        # String is in the pointer family. Distinct
        # families → must be flagged.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const trueFlag Bool true
input main console Console
call writeCall console.writeLine
arg writeCall console console
arg writeCall text trueFlag
run writeCall
""")
        self.assertIn("SS4301", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS4301")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "trueFlag")
        self.assertTrue(matchingDiagnostic.blocksCompile)

    def test_passing_int64_where_int64_expected_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Int64 zeroValue
const rightValue Int64 zeroValue
call addCall math.addInt64
arg addCall left leftValue
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_canonical_int64_arg_not_flagged(self) -> None:
        # A correctly annotated Int64 argument should not trip the
        # builtin-signature checker.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Int64 zeroValue
const rightValue Int64 zeroValue
call addCall math.addInt64
arg addCall left leftValue
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_float_builtin_with_integer_arg_type_is_flagged(self) -> None:
        # Regression: math.greaterThanFloat64 is a float-domain builtin; an
        # `argument` row annotated with an integer C-ABI type (Int64)
        # is a real type-context bug (found in std/compare + std/convert).
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Float64 zeroValue
const rightValue Float64 zeroValue
call gtCall math.greaterThanFloat64
argument gtCall left Int64 leftValue
argument gtCall right Int64 rightValue
run gtCall
""")
        self.assertIn("SS4301", _codes(diagnostics))

    def test_float_builtin_with_float64_arg_type_not_flagged(self) -> None:
        # A Float64 argument annotation against a Float64 builtin signature
        # must not flag.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Float64 zeroValue
const rightValue Float64 zeroValue
call gtCall math.greaterThanFloat64
argument gtCall left Float64 leftValue
argument gtCall right Float64 rightValue
run gtCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_type_alias_resolves_through_to_base(self) -> None:
        # `type AccountId UuidV7; type UuidV7 Int64` — passing an
        # AccountId where Int64 is expected should resolve via aliases.
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type UuidV7 Int64
operation main
output main Void
purpose main "smoke"
const lookupAccountId AccountId zeroValue
const rightValue Int64 zeroValue
call addCall math.addInt64
arg addCall left lookupAccountId
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_bcrypt_role_alias_argument_site_coercions_are_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "bcrypt role alias smoke"
storage local immutable passwordText String "pw"
storage local immutable costValue Int32 12
storage local immutable hashBuffer OpaquePointer 0
storage local immutable hashCapacity Int32 61
call hashCall bcrypt.hashPasswordResult
argument hashCall plaintext String passwordText
argument hashCall cost Int32 costValue
argument hashCall outBuffer OpaquePointer hashBuffer
argument hashCall outCapacity Int32 hashCapacity
run hashCall
bind ok hashWritten Bool hashCall
bind error hashError Int32 hashCall
call verifyCall bcrypt.verifyPasswordResult
argument verifyCall plaintext String passwordText
argument verifyCall expectedHash String hashBuffer
run verifyCall
bind ok matched Bool verifyCall
bind error verifyError Int32 verifyCall
storage local immutable sessionTokenText String "issued-session-token"
call sessionHashCall bcrypt.hashSessionTokenResult
argument sessionHashCall token String sessionTokenText
argument sessionHashCall cost Int32 costValue
argument sessionHashCall outBuffer OpaquePointer hashBuffer
argument sessionHashCall outCapacity Int32 hashCapacity
run sessionHashCall
bind ok sessionHashWritten Bool sessionHashCall
bind error sessionHashError Int32 sessionHashCall
call sessionVerifyCall bcrypt.verifySessionTokenResult
argument sessionVerifyCall token String sessionTokenText
argument sessionVerifyCall expectedHash String hashBuffer
run sessionVerifyCall
bind ok sessionMatched Bool sessionVerifyCall
bind error sessionVerifyError Int32 sessionVerifyCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_guarded_http_form_password_can_flow_to_bcrypt_plaintext_role(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "hash password from a form field"
input main request HttpRequest
storage local immutable bodyText HttpRequestValue "password=secret"
storage local immutable passwordFieldName String "password"
storage local immutable scratchBuffer OpaquePointer 0
storage local immutable scratchCapacity Int64 64
storage local immutable costValue Int32 12
storage local immutable hashBuffer OpaquePointer 0
storage local immutable hashCapacity Int32 61
call passwordFieldCall http.formField
argument passwordFieldCall body HttpRequestValue bodyText
argument passwordFieldCall name String passwordFieldName
argument passwordFieldCall scratch OpaquePointer scratchBuffer
argument passwordFieldCall scratchCapacity Int64 scratchCapacity
run passwordFieldCall
bind value passwordValue HttpRequestValue passwordFieldCall
call passwordMissingCall pointer.isNull
argument passwordMissingCall pointer OpaquePointer passwordValue
run passwordMissingCall
bind value passwordMissing Bool passwordMissingCall
branch if condition passwordMissing target missingPassword
call hashCall bcrypt.hashPassword
argument hashCall plaintext BcryptPlaintextPassword passwordValue
argument hashCall cost Int32 costValue
argument hashCall outBuffer BcryptHashBuffer hashBuffer
argument hashCall outCapacity Int32 hashCapacity
run hashCall
bind value hashStatus Int32 hashCall
label missingPassword
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_enum_case_uses_repr_width_for_builtin_signature(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation main
output main Void
purpose main "smoke"
call statusCheckCall math.equalInt32
arg statusCheckCall left SaveSucceeded
arg statusCheckCall right SaveFailed
run statusCheckCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_sqlite_step_result_predicates_accept_step_result(self) -> None:
        diagnostics = _lint_source("""project Test
import sqlite standard.sqlite
operation main
output operation main Bool
purpose operation main "smoke"
memory main heap no
async main no
call rowCheckCall sqlite.stepResultIsRow
argument rowCheckCall stepResult SqliteStepResult rowSqliteStepResult
run rowCheckCall
bind value isRow Bool rowCheckCall
call doneCheckCall sqlite.stepResultIsDone
argument doneCheckCall stepResult SqliteStepResult doneSqliteStepResult
run doneCheckCall
bind value isDone Bool doneCheckCall
return value isRow
""")
        self.assertNotIn("SS4301", _codes(diagnostics))
        self.assertNotIn("SS4105", _codes(diagnostics))

    def test_enum_case_to_wrong_width_builtin_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
const zeroValue Int64 0
operation main
output main Void
purpose main "smoke"
call statusCheckCall math.equalInt64
arg statusCheckCall left SaveSucceeded
arg statusCheckCall right zeroValue
run statusCheckCall
""")
        self.assertIn("SS4301", _codes(diagnostics))

    def test_user_operation_input_signature_checked(self) -> None:
        # Pass a pointer-typed value where the user op declared an integer
        # input — distinct families, must flag.
        diagnostics = _lint_source("""project Test
operation processCount
input processCount inputCount Int64
output processCount Void
purpose processCount "smoke"
operation main
output main Void
purpose main "smoke"
const someText String textValue
call processCountCall processCount
arg processCountCall inputCount someText
run processCountCall
""")
        self.assertIn("SS4301", _codes(diagnostics))

    def test_unknown_target_signature_not_flagged(self) -> None:
        # External call to a target with no known signature; skip rather
        # than guess (avoids false positives on novel libc calls).
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const flag Bool true
call externalCall some.unknown.target
arg externalCall flagArg flag
run externalCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))


# ==========================================================================
# SS4303  typeIntegrity.mathOperandWidthDrift
# ==========================================================================

class TestMathOperandWidthDrift(unittest.TestCase):
    def test_int64_compare_with_int32_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus Int32 1
const rightStatus Int32 1
call statusCheckCall math.equalInt64
arg statusCheckCall left leftStatus
arg statusCheckCall right rightStatus
run statusCheckCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.severity, semlint.Severity.ERROR)
        self.assertTrue(diagnostic.blocksCompile)
        self.assertEqual(diagnostic.fixCandidates[0].shape, "call statusCheckCall math.equalInt32")

    def test_width_specific_int32_compare_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus Int32 1
const rightStatus Int32 1
call statusCheckCall math.equalInt32
arg statusCheckCall left leftStatus
arg statusCheckCall right rightStatus
run statusCheckCall
""")
        self.assertNotIn("SS4303", _codes(diagnostics))

    def test_int64_compare_with_int64_values_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Int64 1
const rightValue Int64 1
call statusCheckCall math.equalInt64
arg statusCheckCall left leftValue
arg statusCheckCall right rightValue
run statusCheckCall
""")
        self.assertNotIn("SS4303", _codes(diagnostics))

    def test_int64_arithmetic_with_int32_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus Int32 1
const rightStatus Int32 1
call addCall math.addInt64
arg addCall left leftStatus
arg addCall right rightStatus
run addCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.fixCandidates[0].name, "makeConversionExplicit")

    def test_int32_compare_with_int64_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue Int64 1
const rightValue Int64 1
call statusCheckCall math.equalInt32
arg statusCheckCall left leftValue
arg statusCheckCall right rightValue
run statusCheckCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.fixCandidates[0].shape, "call statusCheckCall math.equalInt64")

    def test_explicit_conversion_target_with_wrong_input_width_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const sourceValue Int64 1
call widenCall math.signExtendInt32ToInt64
arg widenCall inputValue sourceValue
run widenCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")

    def test_imported_repr_int32_enum_constant_passes_integer_comparison(self) -> None:
        # rowSqliteStepResult is a builtin constant of type SqliteStepResult
        # (repr Int32). Passing it to math.equalInt32 must NOT fire SS4301:
        # the enum's repr must be visible via the import contract index once
        # the caller has `importType SqliteStepResult sqlite SqliteStepResult`.
        # Without that import, typeAliases["SqliteStepResult"]="SqliteStepResult"
        # (a self-alias from the import loop) puts "SqliteStepResult" in the
        # visited set, which historically blocked the enumReprs lookup.
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text(
                "buildProject enumReprFix\n"
                "registerModule enumReprFix app.enum_repr_fix \"main.sem\"\n"
                "mainFile enumReprFix \"main.sem\"\n",
                encoding="utf-8",
            )
            (root / "main.sem").write_text(
                "module app.enum_repr_fix\n"
                "import sqlite standard.sqlite\n"
                "importType SqliteStepResult sqlite SqliteStepResult\n"
                "storage module immutable expectedCode Int32 100\n"
                "operation main\n"
                "output operation main Bool\n"
                "async main no\n"
                "purpose operation main"
                " \"Verify imported repr Int32 enum const passes integer comparison.\"\n"
                "call eqCall math.equalInt32\n"
                "argument eqCall left Int32 rowSqliteStepResult\n"
                "argument eqCall right Int32 expectedCode\n"
                "run eqCall\n"
                "bind value isMatch Bool eqCall\n"
                "return value isMatch\n",
                encoding="utf-8",
            )
            diagnostics = semlint.lint_path(root / "main.sem")
        self.assertNotIn("SS4301", _codes(diagnostics))


# ==========================================================================
# SS4308  typeIntegrity.divisionByConstantZero   (cause B6)
# SS4309  typeIntegrity.shiftCountOutOfRange      (cause B5)
# ==========================================================================

class TestConstantDivisionOrShiftUb(unittest.TestCase):
    # ---- SS4308: divide / modulo by a provable constant zero ----

    def test_divide_by_inline_literal_zero_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 0
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4308")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.divisionByConstantZero")
        self.assertEqual(diagnostic.severity, semlint.Severity.ERROR)
        self.assertTrue(diagnostic.blocksCompile)
        self.assertEqual(diagnostic.subjectName, "divideCall")

    def test_modulo_by_inline_literal_zero_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call moduloCall math.moduloInt64
argument moduloCall left Int64 numeratorValue
argument moduloCall right Int64 0
run moduloCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_divide_alias_modInt64_by_zero_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call modCall math.modInt64
argument modCall left Int64 numeratorValue
argument modCall right Int64 0
run modCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_divide_by_domain_literal_zero_is_flagged(self) -> None:
        # The divisor is a named module constant bound to 0 — resolution must
        # see through `domainLiteral` exactly like the stdlib uses it.
        diagnostics = _lint_source("""project Test
domainLiteral integerZeroDivisor Int64 0
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 integerZeroDivisor
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_divide_by_const_zero_legacy_arg_form_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
const zeroDivisor Int64 0
call divideCall math.divideInt64
arg divideCall left numeratorValue
arg divideCall right zeroDivisor
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_divide_by_nonzero_constant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
domainLiteral integerTwoBaseValue Int64 2
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 integerTwoBaseValue
run divideCall
""")
        self.assertNotIn("SS4308", _codes(diagnostics))

    def test_divide_by_runtime_value_not_flagged(self) -> None:
        # A non-constant divisor cannot be proven zero, so this floor pass stays
        # silent (the dataflow-guard case is tracked separately).
        diagnostics = _lint_source("""project Test
operation main
input operation main divisorInput Int64
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 divisorInput
run divideCall
""")
        self.assertNotIn("SS4308", _codes(diagnostics))

    def test_add_by_zero_not_flagged(self) -> None:
        # Only sdiv/srem are UB on a zero operand; add/sub/mul are fine.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call addCall math.addInt64
argument addCall left Int64 numeratorValue
argument addCall right Int64 0
run addCall
""")
        self.assertNotIn("SS4308", _codes(diagnostics))

    # ---- SS4309: shift count proven outside [0, 63] ----

    def test_shift_left_by_64_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftLeftInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 64
run shiftCall
""")
        self.assertIn("SS4309", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4309")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.shiftCountOutOfRange")
        self.assertTrue(diagnostic.blocksCompile)

    def test_shift_right_logical_by_negative_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftRightLogicalInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 -1
run shiftCall
""")
        self.assertIn("SS4309", _codes(diagnostics))

    def test_shift_right_arithmetic_by_constant_128_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
domainLiteral shiftCountValue Int64 128
operation main
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftRightArithmeticInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 shiftCountValue
run shiftCall
""")
        self.assertIn("SS4309", _codes(diagnostics))

    def test_shift_by_63_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftLeftInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 63
run shiftCall
""")
        self.assertNotIn("SS4309", _codes(diagnostics))

    def test_shift_by_zero_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftLeftInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 0
run shiftCall
""")
        self.assertNotIn("SS4309", _codes(diagnostics))

    def test_shift_by_runtime_count_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input operation main bitIndex Int64
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftLeftInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 bitIndex
run shiftCall
""")
        self.assertNotIn("SS4309", _codes(diagnostics))

    # ---- scope soundness regressions (found in iteration-1 critique) ----

    def test_constant_does_not_leak_across_operations(self) -> None:
        # `countSlot` is a local immutable 64 in `alpha`; in `beta` the same
        # name is a runtime input. The constant must not leak into `beta`.
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
const inputValueAlpha Int64 1
storage local immutable countSlot Int64 8
call shiftAlpha math.shiftLeftInt64
argument shiftAlpha left Int64 inputValueAlpha
argument shiftAlpha right Int64 countSlot
run shiftAlpha
operation beta
input operation beta countSlot Int64
output beta Void
purpose beta "smoke"
const inputValueBeta Int64 1
call shiftBeta math.shiftLeftInt64
argument shiftBeta left Int64 inputValueBeta
argument shiftBeta right Int64 countSlot
run shiftBeta
""")
        # alpha shifts by constant 8 (in range) -> no diagnostic; beta shifts by
        # a runtime input -> must NOT be flagged via a leaked constant.
        self.assertNotIn("SS4309", _codes(diagnostics))

    def test_input_shadowing_module_constant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable shiftAmount Int64 64
operation main
input operation main shiftAmount Int64
output main Void
purpose main "smoke"
const inputValue Int64 1
call shiftCall math.shiftLeftInt64
argument shiftCall left Int64 inputValue
argument shiftCall right Int64 shiftAmount
run shiftCall
""")
        self.assertNotIn("SS4309", _codes(diagnostics))

    def test_local_rebind_shadows_module_constant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable divisorSlot Int64 0
operation main
input operation main userValue Int64
output main Void
purpose main "smoke"
const numeratorValue Int64 10
bind value divisorSlot Int64 userValue
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 divisorSlot
run divideCall
""")
        self.assertNotIn("SS4308", _codes(diagnostics))

    def test_storage_module_immutable_zero_divisor_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable zeroDivisor Int64 0
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 zeroDivisor
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_transitive_constant_zero_divisor_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
domainLiteral zeroBase Int64 0
domainLiteral zeroAlias Int64 zeroBase
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 zeroAlias
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_modulo_by_domain_literal_zero_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
domainLiteral integerZeroDivisor Int64 0
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call moduloCall math.moduloInt64
argument moduloCall left Int64 numeratorValue
argument moduloCall right Int64 integerZeroDivisor
run moduloCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_domain_typed_divide_by_zero_is_flagged(self) -> None:
        # Idiomatic domain-typed arithmetic: `QuotaCount.divide` lowers to
        # math.divideInt64, so a constant-zero divisor must still be caught.
        diagnostics = _lint_source("""project Test
type QuotaCount Int64
domainLiteral zeroDivisor QuotaCount 0
operation main
output main Void
purpose main "smoke"
const numeratorValue QuotaCount 10
call divideCall QuotaCount.divide
argument divideCall left QuotaCount numeratorValue
argument divideCall right QuotaCount zeroDivisor
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_shared_state_immutable_zero_divisor_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState module immutable configuredZero Int64 0
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 configuredZero
run divideCall
""")
        self.assertIn("SS4308", _codes(diagnostics))

    def test_shared_state_mutable_divisor_not_flagged(self) -> None:
        # A mutable shared slot initialized to 0 is reassigned at runtime; its
        # initializer is not its value at the divide site.
        diagnostics = _lint_source("""project Test
sharedState module mutable runningDivisor Int64 0
operation main
output main Void
purpose main "smoke"
const numeratorValue Int64 10
call divideCall math.divideInt64
argument divideCall left Int64 numeratorValue
argument divideCall right Int64 runningDivisor
run divideCall
""")
        self.assertNotIn("SS4308", _codes(diagnostics))


# ==========================================================================
# Generic semsc <-> semlint security-rule parity harness (capstone Rec 2)
# ==========================================================================
#
# For each security rule, feed the SAME single-file program to BOTH the compiler
# checks and the linter, and assert they agree — so future drift (like the
# SS4604 const-chain parity break) is caught mechanically, not by a per-rule
# spot test. Single-file programs avoid the (documented) cross-module
# under-report on the import-less linter floor.

class TestSecurityRuleParity(unittest.TestCase):
    @staticmethod
    def _compiler_security_codes(source: str) -> set:
        import os
        import re as _re
        import sys as _sys
        compilerDir = os.path.join(os.path.dirname(_LINTER_DIRECTORY), "compiler")
        if compilerDir not in _sys.path:
            _sys.path.insert(0, compilerDir)
        import semsc  # noqa: E402
        prog = semsc.parse(source)
        prog.source_path = "parity_probe.sem"  # non-test path (no floor exemption)
        diags: list = []
        for checkName in (
            "_check_strict_constant_division_or_shift",
            "_check_strict_insecure_random",
            "_check_strict_weak_password_hash_cost",
            "_check_strict_command_string_is_constant",
            "_check_strict_hardcoded_secret",
            "_check_strict_sql_string_is_constant",
            "_check_strict_format_string_is_constant",
        ):
            try:
                getattr(semsc, checkName)(prog, diags)
            except Exception:
                pass
        return {m.group(1) for _ln, msg in diags
                if (m := _re.match(r"(SS\d+)", msg))}

    # (label, source, code, dual_surface)
    #   dual_surface=True  -> BOTH compiler and linter must flag it.
    #   dual_surface=False -> compiler-only by design (no semlint floor rule),
    #                         a DOCUMENTED asymmetry the harness pins.
    CASES = [
        ("divide-by-zero", "\n".join([
            "project P", "operation main", "output operation main Int64",
            "purpose operation main \"x\"",
            "storage module immutable numeratorValue Int64 10",
            "storage module immutable zeroDivisor Int64 0",
            "call divideCall math.divideInt64",
            "argument divideCall left Int64 numeratorValue",
            "argument divideCall right Int64 zeroDivisor", "run divideCall",
        ]), "SS4308", True),
        ("shift-out-of-range", "\n".join([
            "project P", "operation main", "output operation main Int64",
            "purpose operation main \"x\"",
            "storage module immutable inputValue Int64 1",
            "storage module immutable shiftCountValue Int64 64",
            "call shiftCall math.shiftLeftInt64",
            "argument shiftCall left Int64 inputValue",
            "argument shiftCall right Int64 shiftCountValue", "run shiftCall",
        ]), "SS4309", True),
        ("insecure-prng", "\n".join([
            "project P", "operation main", "output operation main Void",
            "purpose operation main \"x\"",
            "call randomCall c.rand", "run randomCall",
        ]), "SS4601", True),
        ("weak-bcrypt-cost", "\n".join([
            "project P", "operation registerUser",
            "output operation registerUser Void",
            "purpose operation registerUser \"x\"",
            "storage local immutable plaintextValue String \"pw\"",
            "storage module immutable weakCost Int32 4",
            "call hashCall bcrypt.hashPassword",
            "argument hashCall plaintext String plaintextValue",
            "argument hashCall cost Int32 weakCost", "run hashCall",
        ]), "SS4602", True),
        ("command-injection", "\n".join([
            "project P", "operation runShell",
            "input operation runShell userCommand String",
            "output operation runShell Void", "purpose operation runShell \"x\"",
            "call systemCall c.system",
            "argument systemCall command String userCommand", "run systemCall",
        ]), "SS4603", True),
        # Uses the CONST-CHAIN form (secret <- realSecret <- "literal"), not a
        # direct literal — so this case genuinely guards the BUG-1 parity break
        # (both surfaces must follow the chain, not just flag a quoted literal).
        ("hard-coded-secret", "\n".join([
            "project P", "type ApiKey String", "typeTrust ApiKey secret",
            "storage module immutable realSecretValue String \"sk-live-abc123\"",
            "storage module immutable serviceKey ApiKey realSecretValue",
            "operation main", "output operation main Void",
            "purpose operation main \"x\"",
            "call writeCall console.writeLine", "run writeCall",
        ]), "SS4604", True),
        # Exercises BOTH resolvers at once: a type-alias of a secret type whose
        # value is a const-chain to a literal. Must fire on both surfaces.
        ("alias-secret-via-chain", "\n".join([
            "project P", "type ApiKey String", "typeTrust ApiKey secret",
            "type AppSecret ApiKey",
            "storage module immutable realSecretValue String \"sk-live-xyz\"",
            "storage module immutable appKey AppSecret realSecretValue",
            "operation main", "output operation main Void",
            "purpose operation main \"x\"",
            "call writeCall console.writeLine", "run writeCall",
        ]), "SS4604", True),
        # Compiler strict wall plus semlint floor:
        ("dynamic-format", "\n".join([
            "project P", "operation main", "output operation main Void",
            "purpose operation main \"x\"",
            "storage module mutable runtimeFormat String \"\"",
            "call writeCall c.snprintf",
            "argument writeCall format String runtimeFormat", "run writeCall",
        ]), "SS3310", True),
    ]

    def test_compiler_and_linter_agree_per_rule(self) -> None:
        for label, source, code, dualSurface in self.CASES:
            compilerCodes = self._compiler_security_codes(source)
            linterCodes = set(_codes(_lint_source(source)))
            self.assertIn(code, compilerCodes,
                          f"{label}: compiler must flag {code}")
            if dualSurface:
                self.assertIn(code, linterCodes,
                              f"{label}: linter must flag {code} (semsc<->semlint parity)")
            else:
                self.assertNotIn(code, linterCodes,
                                 f"{label}: {code} is compiler-only by design "
                                 f"(no semlint floor rule) — update this harness "
                                 f"if a linter rule is added")


class TestFormatStringMustBeConstant(unittest.TestCase):
    def test_c_snprintf_runtime_format_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input operation main requestFormat String
output operation main Void
purpose operation main "format string injection fixture"
call writeCall c.snprintf
argument writeCall format String requestFormat
run writeCall
return void
""")
        self.assertIn("SS3310", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3310")[0]
        self.assertEqual(matching.subjectName, "writeCall")
        self.assertEqual(matching.gapEdge, "constantFormatString")

    def test_mutable_format_storage_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable runtimeFormat String ""
operation main
output operation main Void
purpose operation main "format string injection fixture"
call writeCall c.snprintf
argument writeCall format String runtimeFormat
run writeCall
return void
""")
        self.assertIn("SS3310", _codes(diagnostics))

    def test_immutable_module_and_local_formats_are_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable moduleFormat String "%s"
operation main
output operation main Void
purpose operation main "safe format string fixture"
storage local immutable localFormat String "%d"
call moduleWriteCall c.snprintf
argument moduleWriteCall format String moduleFormat
run moduleWriteCall
call localWriteCall c.snprintf
argument localWriteCall format String localFormat
run localWriteCall
return void
""")
        self.assertNotIn("SS3310", _codes(diagnostics))

    def test_mutable_local_format_selected_from_immutable_constants_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable defaultFormat String "%s"
storage module immutable alternateFormat String "%lld"
operation main
output operation main Void
purpose operation main "safe selected format string fixture"
storage local mutable selectedFormat String defaultFormat
set memory selectedFormat alternateFormat
call writeCall c.snprintf
argument writeCall format String selectedFormat
run writeCall
return void
""")
        self.assertNotIn("SS3310", _codes(diagnostics))

    def test_mutable_local_format_assigned_runtime_value_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable defaultFormat String "%s"
operation main
input operation main requestFormat String
output operation main Void
purpose operation main "unsafe selected format string fixture"
storage local mutable selectedFormat String defaultFormat
set memory selectedFormat requestFormat
call writeCall c.snprintf
argument writeCall format String selectedFormat
run writeCall
return void
""")
        self.assertIn("SS3310", _codes(diagnostics))


# ==========================================================================
# SS4601  security.insecurePseudoRandom   (cause G2 / CWE-338)
# ==========================================================================

class TestInsecurePseudoRandom(unittest.TestCase):
    def test_c_rand_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call randomCall c.rand
run randomCall
""")
        self.assertIn("SS4601", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4601")[0]
        self.assertEqual(diagnostic.kind, "security.insecurePseudoRandom")
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)
        self.assertFalse(diagnostic.blocksCompile)
        # Fix steers to the portable platform CSPRNG, not the Windows-only rand_s.
        self.assertIn("bcrypt.randomBytes", diagnostic.fixCandidates[0].shape)

    def test_c_srand_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const seedValue UInt32 1
call seedCall c.srand
argument seedCall seed UInt32 seedValue
run seedCall
""")
        self.assertIn("SS4601", _codes(diagnostics))

    def test_c_random_posix_family_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call randomCall c.random
run randomCall
""")
        self.assertIn("SS4601", _codes(diagnostics))

    def test_csprng_rand_s_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call secureCall c.rand_s
run secureCall
""")
        self.assertNotIn("SS4601", _codes(diagnostics))

    def test_linter_and_compiler_insecure_random_sets_match(self) -> None:
        # Parity guard: the advisory floor and the strict wall must flag exactly
        # the same target set (an iteration-2/3 critique theme — wall/floor drift
        # is a real bug class). Import the compiler set and compare.
        import os
        import sys
        compilerDir = os.path.join(
            os.path.dirname(_LINTER_DIRECTORY), "compiler")
        if compilerDir not in sys.path:
            sys.path.insert(0, compilerDir)
        import semsc  # noqa: E402
        self.assertEqual(
            set(semlint.INSECURE_PSEUDORANDOM_TARGETS),
            set(semsc._STRICT_INSECURE_RANDOM_TARGETS.keys()),
        )

    def test_no_random_call_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4601", _codes(diagnostics))


# ==========================================================================
# SS4604  security.hardCodedSecret   (cause E6 / CWE-798)
# ==========================================================================

class TestHardCodedSecret(unittest.TestCase):
    def test_secret_typed_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ApiSecret String
typeTrust ApiSecret secret
storage module immutable serviceApiSecret ApiSecret "sk-live-abcdef123456"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertIn("SS4604", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4604")[0]
        self.assertEqual(diagnostic.kind, "security.hardCodedSecret")
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)
        self.assertEqual(diagnostic.subjectName, "serviceApiSecret")

    def test_mutable_secret_typed_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type SigningSecret String
typeTrust SigningSecret secret
storage module mutable cachedSecret SigningSecret "hardcoded-value"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertIn("SS4604", _codes(diagnostics))

    def test_empty_sentinel_not_flagged(self) -> None:
        # The good pattern: empty sentinel filled from env at runtime.
        diagnostics = _lint_source("""project Test
type SigningSecret String
typeTrust SigningSecret secret
storage module mutable cachedSecret SigningSecret ""
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4604", _codes(diagnostics))

    def test_non_secret_typed_literal_not_flagged(self) -> None:
        # A plain String literal (no typeTrust secret) is not a credential.
        diagnostics = _lint_source("""project Test
storage module immutable fieldPassword String "password"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4604", _codes(diagnostics))

    def test_alias_of_secret_type_literal_is_flagged(self) -> None:
        # `type AppSecret ApiKey` (alias of a secret type) must inherit
        # secret-ness — closing the iteration-7 critique BUG 2 alias evasion.
        diagnostics = _lint_source("""project Test
type ApiKey String
typeTrust ApiKey secret
type AppSecret ApiKey
storage module immutable leakedKey AppSecret "super-secret-prod-key-12345"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertIn("SS4604", _codes(diagnostics))

    def test_sharedstate_secret_typed_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ApiKey String
typeTrust ApiKey secret
sharedState module mutable leakedKey ApiKey "hardcoded-shared-secret"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertIn("SS4604", _codes(diagnostics))

    def test_secret_via_const_chain_is_flagged(self) -> None:
        # Parity with the compiler (capstone BUG 1): a secret bound to another
        # constant that resolves to a non-empty literal is still hard-coded.
        diagnostics = _lint_source("""project Test
type ApiKey String
typeTrust ApiKey secret
storage module immutable realSecretValue String "super-secret-prod-key"
storage module immutable apiSigningKey ApiKey realSecretValue
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertIn("SS4604", _codes(diagnostics))

    def test_secret_bound_to_mutable_sentinel_by_name_not_flagged(self) -> None:
        # A secret referencing a runtime-filled mutable sentinel by name is the
        # good pattern (not a source literal) — must NOT be a false positive.
        diagnostics = _lint_source("""project Test
type ApiKey String
typeTrust ApiKey secret
storage module mutable runtimeFilledKey ApiKey ""
storage module immutable aliasOfRuntimeKey ApiKey runtimeFilledKey
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4604", _codes(diagnostics))

    def test_trusted_typed_literal_not_flagged(self) -> None:
        # typeTrust other than `secret` must not be flagged.
        diagnostics = _lint_source("""project Test
type PublicToken String
typeTrust PublicToken trusted
storage module immutable publicToken PublicToken "pub-123"
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4604", _codes(diagnostics))


# ==========================================================================
# SS4603  security.shellCommandNotConstant   (cause D2/D3 / CWE-78)
# ==========================================================================

class TestShellCommandNotConstant(unittest.TestCase):
    def test_runtime_command_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation runShell
input operation runShell userCommand String
output runShell Void
purpose runShell "smoke"
call systemCall c.system
argument systemCall command String userCommand
run systemCall
""")
        self.assertIn("SS4603", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4603")[0]
        self.assertEqual(diagnostic.kind, "security.shellCommandNotConstant")
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)

    def test_bind_result_command_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation runShell
output runShell Void
purpose runShell "smoke"
storage local immutable templateValue String "echo %s"
storage local immutable userValue String "x"
call buildCall string.format
argument buildCall template String templateValue
argument buildCall value String userValue
run buildCall
bind value builtCommand String buildCall
call systemCall c.system
argument systemCall command String builtCommand
run systemCall
""")
        self.assertIn("SS4603", _codes(diagnostics))

    def test_constant_command_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable listCommand String "ls -la"
operation runShell
output runShell Void
purpose runShell "smoke"
call systemCall c.system
argument systemCall command String listCommand
run systemCall
""")
        self.assertNotIn("SS4603", _codes(diagnostics))

    def test_inline_literal_command_not_flagged(self) -> None:
        # The canonical safe form `c.system("ls -la")` (inline string literal)
        # must NOT be flagged (iteration-6 critique BUG #1).
        diagnostics = _lint_source("""project Test
operation runShell
output runShell Void
purpose runShell "smoke"
call systemCall c.system
argument systemCall command String "ls -la"
run systemCall
""")
        self.assertNotIn("SS4603", _codes(diagnostics))

    def test_no_system_call_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
""")
        self.assertNotIn("SS4603", _codes(diagnostics))


# ==========================================================================
# SS4602  security.weakPasswordHashCost   (cause G9 / CWE-916)
# ==========================================================================

class TestWeakPasswordHashCost(unittest.TestCase):
    def _hash_with_cost(self, cost_decl: str, cost_ref: str) -> list:
        return _codes(_lint_source(f"""project Test
{cost_decl}
operation registerUser
output registerUser Void
purpose registerUser "smoke"
storage local immutable plaintextValue String "pw"
storage local immutable bufferCapacity Int32 61
call hashCall bcrypt.hashPassword
argument hashCall plaintext String plaintextValue
argument hashCall cost Int32 {cost_ref}
argument hashCall outCapacity Int32 bufferCapacity
run hashCall
"""))

    def test_constant_cost_four_is_flagged(self) -> None:
        codes = self._hash_with_cost("storage module immutable weakCost Int32 4", "weakCost")
        self.assertIn("SS4602", codes)

    def test_inline_cost_below_floor_is_flagged(self) -> None:
        # cost 9 is below the floor of 10
        diagnostics = _lint_source("""project Test
operation registerUser
output registerUser Void
purpose registerUser "smoke"
storage local immutable plaintextValue String "pw"
call hashCall bcrypt.hashPassword
argument hashCall plaintext String plaintextValue
argument hashCall cost Int32 9
run hashCall
""")
        self.assertIn("SS4602", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4602")[0]
        self.assertEqual(diagnostic.kind, "security.weakPasswordHashCost")
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)
        self.assertIn("bcryptRecommendedCost", diagnostic.fixCandidates[0].shape)

    def test_cost_at_floor_ten_not_flagged(self) -> None:
        codes = self._hash_with_cost("storage module immutable okCost Int32 10", "okCost")
        self.assertNotIn("SS4602", codes)

    def test_recommended_cost_twelve_not_flagged(self) -> None:
        codes = self._hash_with_cost("storage module immutable recCost Int32 12", "recCost")
        self.assertNotIn("SS4602", codes)

    def test_runtime_cost_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation registerUser
input operation registerUser chosenCost Int32
output registerUser Void
purpose registerUser "smoke"
storage local immutable plaintextValue String "pw"
call hashCall bcrypt.hashPassword
argument hashCall plaintext String plaintextValue
argument hashCall cost Int32 chosenCost
run hashCall
""")
        self.assertNotIn("SS4602", _codes(diagnostics))

    def test_missing_cost_arg_is_flagged(self) -> None:
        # Omitting `cost` must not slip past the check (CWE-916: unspecified
        # work factor) — closes the iteration-4 critique evasion.
        diagnostics = _lint_source("""project Test
operation registerUser
output registerUser Void
purpose registerUser "smoke"
storage local immutable plaintextValue String "pw"
call hashCall bcrypt.hashPassword
argument hashCall plaintext String plaintextValue
run hashCall
""")
        self.assertIn("SS4602", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4602")[0]
        self.assertEqual(diagnostic.intentSlogan, "bcrypt missing cost factor")

    def test_user_op_named_hashPassword_not_misclassified(self) -> None:
        # A user operation literally named `hashPassword` that takes a `cost`
        # must NOT be treated as the bcrypt intrinsic (iteration-4 critique BUG 1).
        diagnostics = _lint_source("""project Test
operation hashPassword
input operation hashPassword cost Int32
output hashPassword Void
purpose hashPassword "unrelated user op that happens to take a cost"
storage local immutable noteValue String "x"
operation caller
output caller Void
purpose caller "smoke"
storage local immutable cheapCost Int32 3
call doItCall hashPassword
argument doItCall cost Int32 cheapCost
run doItCall
""")
        self.assertNotIn("SS4602", _codes(diagnostics))


# ==========================================================================
# SS4302  typeIntegrity.enumReturnUsesRawValue
# ==========================================================================

class TestEnumReturnUsesCase(unittest.TestCase):
    def test_enum_output_returning_raw_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 2
operation saveTodos
output saveTodos SaveStatus
purpose saveTodos "smoke"
returnValue 2
""")
        self.assertIn("SS4302", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4302")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.enumReturnUsesRawValue")
        self.assertEqual(diagnostic.fixCandidates[0].shape, "return value SaveFailed")

    def test_enum_output_returning_case_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 2
operation saveTodos
output saveTodos SaveStatus
purpose saveTodos "smoke"
returnValue SaveFailed
""")
        self.assertNotIn("SS4302", _codes(diagnostics))

    def test_result_enum_ok_returning_raw_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 2
error SaveError
errorCase SaveError SaveCrashed
operation saveTodos
output saveTodos Result SaveStatus SaveError
purpose saveTodos "smoke"
returnOk 0
""")
        self.assertIn("SS4302", _codes(diagnostics))


# ==========================================================================
# SS4401  styleDiscipline.duplicateLocalImmutableAcrossOps
# ==========================================================================

class TestDuplicateLocalImmutableAcrossOps(unittest.TestCase):
    def test_three_operations_with_same_local_immutable_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable nulByte Int32 0
operation beta
output beta Void
purpose beta "smoke"
storage local immutable nulByte Int32 0
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable nulByte Int32 0
""")
        ss4401 = _diagnostics_with_code(diagnostics, "SS4401")
        self.assertEqual(len(ss4401), 3, "expected one info per duplicate site")
        diagnostic = ss4401[0]
        self.assertEqual(diagnostic.subjectName, "nulByte")
        self.assertEqual(diagnostic.subjectKind, "storageSlot")
        self.assertEqual(diagnostic.gapEdge, "storage module immutable")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)
        self.assertTrue(any(
            fixCandidate.shape.startswith("storage module immutable nulByte Int32 0")
            for fixCandidate in diagnostic.fixCandidates
        ))

    def test_two_operations_below_threshold_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable nulByte Int32 0
operation beta
output beta Void
purpose beta "smoke"
storage local immutable nulByte Int32 0
""")
        self.assertNotIn("SS4401", _codes(diagnostics))

    def test_distinct_init_values_are_not_duplicates(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable offset Int64 10
operation beta
output beta Void
purpose beta "smoke"
storage local immutable offset Int64 19
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable offset Int64 30
""")
        self.assertNotIn("SS4401", _codes(diagnostics))


# ==========================================================================
# SS3634  performance.largeLocalStaticLiteral
# ==========================================================================

class TestLargeLocalStaticLiteral(unittest.TestCase):
    def test_large_local_static_literal_is_flagged(self) -> None:
        largeBody = "x" * 520
        diagnostics = _lint_source(f"""project Test
operation metrics
output metrics Void
purpose metrics "smoke"
storage local immutable metricsFormat String "{largeBody}"
""")
        ss3634 = _diagnostics_with_code(diagnostics, "SS3634")
        self.assertEqual(len(ss3634), 1)
        diagnostic = ss3634[0]
        self.assertEqual(diagnostic.subjectName, "metricsFormat")
        self.assertEqual(diagnostic.subjectKind, "storageSlot")
        self.assertEqual(diagnostic.gapEdge, "storage module immutable")
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)

    def test_large_module_static_literal_is_not_flagged(self) -> None:
        largeBody = "x" * 520
        diagnostics = _lint_source(f"""project Test
storage module immutable metricsFormat String "{largeBody}"
operation metrics
output metrics Void
purpose metrics "smoke"
returnVoid
""")
        self.assertNotIn("SS3634", _codes(diagnostics))

    def test_small_local_static_literal_is_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation metrics
output metrics Void
purpose metrics "smoke"
storage local immutable routeName String "/metrics"
""")
        self.assertNotIn("SS3634", _codes(diagnostics))


# ==========================================================================
# SS4402  styleDiscipline.magicAsciiByteLiteral
# ==========================================================================

class TestMagicAsciiByteLiteral(unittest.TestCase):
    def test_printable_ascii_without_rationale_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parser
output parser Void
purpose parser "smoke"
storage local immutable quoteByte Int32 34
""")
        ss4402 = _diagnostics_with_code(diagnostics, "SS4402")
        self.assertEqual(len(ss4402), 1)
        diagnostic = ss4402[0]
        self.assertEqual(diagnostic.subjectName, "quoteByte")
        self.assertEqual(diagnostic.subjectKind, "storageSlot")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)

    def test_printable_ascii_with_rationale_naming_character_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parser
output parser Void
purpose parser "smoke"
# rationale: 34 = ASCII double quote; bounded JSON string delimiter.
storage local immutable quoteByte Int32 34
""")
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_control_character_codepoint_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation terminal
output terminal Void
purpose terminal "smoke"
storage local immutable escapeByte Int32 27
""")
        # 27 is below the printable-ASCII range (32..126).
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_non_int32_type_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation counter
output counter Void
purpose counter "smoke"
storage local immutable offsetValue Int64 65
""")
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_duplicate_name_suppresses_ascii_diagnostic(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable quoteByte Int32 34
operation beta
output beta Void
purpose beta "smoke"
storage local immutable quoteByte Int32 34
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable quoteByte Int32 34
""")
        # SS4401 catches the cross-op duplication; SS4402 must not pile on
        # additional info diagnostics for the same name.
        self.assertIn("SS4401", _codes(diagnostics))
        self.assertNotIn("SS4402", _codes(diagnostics))


# ==========================================================================
# SS4403  styleDiscipline.deadStorageInitializer
# ==========================================================================

class TestDeadStorageInitializer(unittest.TestCase):
    def test_storage_mutable_followed_by_immediate_set_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation loop
output loop Void
purpose loop "smoke"
storage local immutable zeroIndex Int64 0
storage local immutable startOffset Int64 7
storage local mutable cursor Int64 zeroIndex
set local cursor startOffset
""")
        ss4403 = _diagnostics_with_code(diagnostics, "SS4403")
        self.assertEqual(len(ss4403), 1)
        diagnostic = ss4403[0]
        self.assertEqual(diagnostic.subjectName, "cursor")
        self.assertEqual(diagnostic.subjectKind, "storageSlot")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)
        self.assertEqual(diagnostic.fixCandidates[0].name, "seedWithRealFirstValue")

    def test_intervening_call_clears_dead_init_signal(self) -> None:
        diagnostics = _lint_source("""project Test
operation loop
output loop Void
purpose loop "smoke"
storage local immutable zeroIndex Int64 0
storage local mutable cursor Int64 zeroIndex
call probe console.writeLine
arg probe text zeroIndex
run probe
set local cursor zeroIndex
""")
        self.assertNotIn("SS4403", _codes(diagnostics))

    def test_initial_value_actually_read_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation loop
output loop Void
purpose loop "smoke"
storage local immutable zeroIndex Int64 0
storage local mutable cursor Int64 zeroIndex
call printCursor console.writeIntegerLine
arg printCursor value cursor
run printCursor
set local cursor zeroIndex
""")
        self.assertNotIn("SS4403", _codes(diagnostics))


# ==========================================================================
# SS4404  styleDiscipline.fixedOffsetParserNeedsRationale
# ==========================================================================

class TestFixedOffsetParserNeedsRationale(unittest.TestCase):
    def test_two_offset_rows_without_rationale_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
storage local immutable activeValueOffset Int64 10
storage local immutable doneValueOffset Int64 19
""")
        ss4404 = _diagnostics_with_code(diagnostics, "SS4404")
        self.assertEqual(len(ss4404), 1)
        diagnostic = ss4404[0]
        self.assertEqual(diagnostic.subjectName, "parseLine")
        self.assertEqual(diagnostic.subjectKind, "operation")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)

    def test_rationale_naming_emitter_suppresses_diagnostic(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
# rationale: Offsets count bytes into the line emitted by saveTodos's
# itemPrefixFormatText; an edit to that format must update these in lockstep.
storage local immutable activeValueOffset Int64 10
storage local immutable doneValueOffset Int64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_rationale_mentioning_format_keyword_suppresses_diagnostic(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
# rationale: positions in the fixed JSON format string written upstream.
storage local immutable activeValueOffset Int64 10
storage local immutable doneValueOffset Int64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_single_offset_row_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
storage local immutable activeValueOffset Int64 10
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_non_offset_named_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
storage local immutable activeValue Int64 10
storage local immutable doneValue Int64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))


# ==========================================================================
# SS4405  styleDiscipline.enumReprComparison
# ==========================================================================

class TestEnumReprComparison(unittest.TestCase):
    def test_int32_repr_enum_compared_with_raw_math_target_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation checkSave
input checkSave status SaveStatus
output checkSave Bool
purpose checkSave "smoke"
call sameCall math.equalInt32
arg sameCall left status
arg sameCall right SaveSucceeded
run sameCall
bind isSame Bool sameCall
returnValue isSame
""")
        ss4405 = _diagnostics_with_code(diagnostics, "SS4405")
        self.assertEqual(len(ss4405), 1)
        diagnostic = ss4405[0]
        self.assertEqual(diagnostic.subjectName, "sameCall")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)
        self.assertEqual(
            diagnostic.fixCandidates[0].shape,
            "call sameCall SaveStatus.equal",
        )

    def test_int64_repr_enum_compared_with_math_equal_int64_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum Mode repr Int64
enumCase Mode ListMode 0
enumCase Mode EditMode 1
operation checkMode
input checkMode mode Mode
output checkMode Bool
purpose checkMode "smoke"
call modeCall math.equalInt64
arg modeCall left mode
arg modeCall right EditMode
run modeCall
bind isEdit Bool modeCall
returnValue isEdit
""")
        ss4405 = _diagnostics_with_code(diagnostics, "SS4405")
        self.assertEqual(len(ss4405), 1)
        self.assertEqual(
            ss4405[0].fixCandidates[0].shape,
            "call modeCall Mode.equal",
        )

    def test_enum_domain_method_call_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation checkSave
input checkSave status SaveStatus
output checkSave Bool
purpose checkSave "smoke"
call sameCall SaveStatus.equal
arg sameCall left status
arg sameCall right SaveSucceeded
run sameCall
bind isSame Bool sameCall
returnValue isSame
""")
        self.assertNotIn("SS4405", _codes(diagnostics))

    def test_non_enum_int_compare_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation check
input check left Int32
output check Bool
purpose check "smoke"
call cmpCall math.equalInt32
arg cmpCall left left
arg cmpCall right left
run cmpCall
bind isEqual Bool cmpCall
returnValue isEqual
""")
        self.assertNotIn("SS4405", _codes(diagnostics))


# ==========================================================================
# SS4406  styleDiscipline.enumResultDiscarded
# ==========================================================================

class TestEnumResultDiscarded(unittest.TestCase):
    def test_ignore_value_on_enum_typed_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation saveAndForget
output saveAndForget Void
purpose saveAndForget "smoke"
call doSave saveData
run doSave
ignoreValue doSave SaveStatus
operation saveData
output saveData SaveStatus
purpose saveData "smoke"
returnValue SaveSucceeded
""")
        ss4406 = _diagnostics_with_code(diagnostics, "SS4406")
        self.assertEqual(len(ss4406), 1)
        diagnostic = ss4406[0]
        self.assertEqual(diagnostic.subjectName, "doSave")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.INFO)

    def test_ignore_value_on_primitive_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation logIt
output logIt Void
purpose logIt "smoke"
call write console.writeLine
arg write console console
arg write text someText
run write
ignoreValue write Int32
""")
        self.assertNotIn("SS4406", _codes(diagnostics))

    def test_bound_enum_return_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr Int32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation doIt
output doIt Void
purpose doIt "smoke"
call doSave saveData
run doSave
bind result SaveStatus doSave
operation saveData
output saveData SaveStatus
purpose saveData "smoke"
returnValue SaveSucceeded
""")
        self.assertNotIn("SS4406", _codes(diagnostics))


# ==========================================================================
# SS4407  styleDiscipline.pairedScalarMustStayEqual
# ==========================================================================

class TestPairedScalarMustStayEqual(unittest.TestCase):
    def test_diverging_init_values_with_must_stay_equal_invariant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main console Console
output main Void
purpose main "smoke"
invariant main "lineBufferBytes and lineBufferCapacity MUST stay equal: the malloc size and the c.fgets count argument must agree."
storage local immutable lineBufferBytes ByteCount 384
storage local immutable lineBufferCapacity Int32 256
""")
        ss4407 = _diagnostics_with_code(diagnostics, "SS4407")
        self.assertEqual(len(ss4407), 1)
        diagnostic = ss4407[0]
        self.assertEqual(diagnostic.subjectName, "main")
        self.assertEqual(diagnostic.tier, semlint.Tier.T4_STYLE)
        self.assertEqual(diagnostic.severity, semlint.Severity.WARNING)
        self.assertIn("lineBufferBytes=384", diagnostic.invariantRule)
        self.assertIn("lineBufferCapacity=256", diagnostic.invariantRule)

    def test_aligned_init_values_with_must_stay_equal_invariant_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main console Console
output main Void
purpose main "smoke"
invariant main "lineBufferBytes and lineBufferCapacity MUST stay equal."
storage local immutable lineBufferBytes ByteCount 384
storage local immutable lineBufferCapacity Int32 384
""")
        self.assertNotIn("SS4407", _codes(diagnostics))

    def test_diverging_values_without_anchor_phrase_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main console Console
output main Void
purpose main "smoke"
invariant main "lineBufferBytes is the malloc size; lineBufferCapacity is the c.fgets count."
storage local immutable lineBufferBytes ByteCount 384
storage local immutable lineBufferCapacity Int32 256
""")
        # Without the `MUST stay equal` anchor the rule does not fire — the
        # values are allowed to differ when the invariant doesn't claim
        # they're paired.
        self.assertNotIn("SS4407", _codes(diagnostics))

    def test_module_scope_paired_scalars_are_resolved(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable retryLimitBytes ByteCount 1024
storage module immutable retryLimitCapacity Int32 512
operation main
input main console Console
output main Void
purpose main "smoke"
invariant main "retryLimitBytes and retryLimitCapacity must be equal across modules."
""")
        ss4407 = _diagnostics_with_code(diagnostics, "SS4407")
        self.assertEqual(len(ss4407), 1)


# ==========================================================================
# SS3601  webserver.invalidRouteMethod
# ==========================================================================

class TestInvalidRouteMethod(unittest.TestCase):
    """Routes must use methods from the native dispatcher's whitelist.
    CONNECT and TRACE are deliberately excluded (no tunneling semantics,
    TRACE would echo opaque request bytes back to the client)."""

    _WHITELIST_ROUTE_TEMPLATE = """project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer {method} "/edge" edgeHandler

capability httpResponseWriter http.response write

operation edgeHandler
input edgeHandler request HttpRequest
input edgeHandler response HttpResponse
output edgeHandler Int32
effect edgeHandler write http.response
memory edgeHandler arena request
async edgeHandler no
useCapability edgeHandler httpResponseWriter
purpose edgeHandler "smoke handler for whitelist test"
invariant edgeHandler "static response so the test can poll"
label startEdgeHandler
storage local immutable bodyText String "edge\\n"
storage local immutable okStatus Int32 200
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_connect_method_is_flagged(self) -> None:
        diagnostics = _lint_source(self._WHITELIST_ROUTE_TEMPLATE.format(method="CONNECT"))
        self.assertIn("SS3601", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3601")[0]
        self.assertEqual(matching.subjectName, "/edge")
        self.assertEqual(matching.subjectKind, "route")
        self.assertEqual(matching.gapEdge, "route.method")
        self.assertIn("CONNECT", matching.intentSlogan)

    def test_trace_method_is_flagged(self) -> None:
        diagnostics = _lint_source(self._WHITELIST_ROUTE_TEMPLATE.format(method="TRACE"))
        self.assertIn("SS3601", _codes(diagnostics))

    def test_lowercase_method_is_not_flagged(self) -> None:
        # Route method validation is case-insensitive; the native dispatcher
        # normalizes supported methods before matching.
        diagnostics = _lint_source(self._WHITELIST_ROUTE_TEMPLATE.format(method="get"))
        self.assertNotIn("SS3601", _codes(diagnostics))

    def test_whitelisted_methods_are_not_flagged(self) -> None:
        for whitelistedMethod in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            diagnostics = _lint_source(
                self._WHITELIST_ROUTE_TEMPLATE.format(method=whitelistedMethod)
            )
            self.assertNotIn(
                "SS3601",
                _codes(diagnostics),
                msg=f"whitelisted method {whitelistedMethod} should not trip SS3601",
            )


# ==========================================================================
# SS3602  webserver.middlewareMissingResponseEffect
# ==========================================================================

class TestMiddlewareMissingResponseEffect(unittest.TestCase):
    """Ops bound via `routeMiddleware` must declare `write http.response*`
    because the native dispatcher calls middleware before the handler
    specifically so it can write response state."""

    def _minimal_program(self, middlewareEffectLine: str) -> str:
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler
routeMiddleware testServer "/probe" probeMiddleware

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation probeMiddleware
input probeMiddleware request HttpRequest
input probeMiddleware response HttpResponse
output probeMiddleware Int32
{middlewareEffectLine}
memory probeMiddleware arena request
async probeMiddleware no
useCapability probeMiddleware httpRequestReader
purpose probeMiddleware "demo middleware for SS3602 fixture"
invariant probeMiddleware "synchronous middleware that returns 0 to continue"
label startProbeMiddleware
storage local immutable continueStatus Int32 0
returnValue continueStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_middleware_without_response_effect_is_flagged(self) -> None:
        # Middleware that only reads the request path; no response write
        # effect declared. The dispatcher would still execute the op, but
        # there's nothing for it to write — the binding is misshapen.
        diagnostics = _lint_source(self._minimal_program(
            "effect probeMiddleware read http.request.path"
        ))
        self.assertIn("SS3602", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3602")[0]
        self.assertEqual(matching.subjectName, "probeMiddleware")
        self.assertEqual(matching.gapEdge, "effect.write.http.response")

    def test_middleware_with_response_write_effect_not_flagged(self) -> None:
        diagnostics = _lint_source(self._minimal_program(
            "effect probeMiddleware write http.response"
        ))
        self.assertNotIn("SS3602", _codes(diagnostics))

    def test_middleware_with_narrower_response_effect_not_flagged(self) -> None:
        # `http.response.header` is narrower than `http.response`; the rule
        # accepts any path starting with `http.response` so a middleware
        # that only writes headers (not body) is still authorized.
        diagnostics = _lint_source(self._minimal_program(
            "effect probeMiddleware write http.response.header"
        ))
        self.assertNotIn("SS3602", _codes(diagnostics))


# ==========================================================================
# SS3603  webserver.unguardedHttpInput
# ==========================================================================

class TestUnguardedHttpInput(unittest.TestCase):
    """Values bound from nullable http.request* reads must pass a
    pointer.isNull guard before reaching the body argument of an
    http.response* writer (or a wrapper that forwards body to one).
    Per-op opt-out via warning text marker `null-body failure path`."""

    def _program_passing_header_to_responseText(
        self,
        addGuard: bool,
        addOptOutMarker: bool,
    ) -> str:
        guardBlock = (
            """call tokenMissingCheckCall pointer.isNull
arg tokenMissingCheckCall pointer tokenHeaderValue
run tokenMissingCheckCall
bind tokenMissing Bool tokenMissingCheckCall
branchIf tokenMissing missingPath
"""
            if addGuard
            else ""
        )
        warningLine = (
            'warning echoHandler "this route intentionally exercises the adapter null-body failure path"\n'
            if addOptOutMarker
            else ""
        )
        # The handler reads X-Token (nullable) and routes it straight to
        # http.responseText body; with neither a guard nor the opt-out
        # marker this is exactly the SS3603 trigger pattern.
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token back"
invariant echoHandler "static reply on missing token"
{warningLine}label startEchoHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
storage local immutable badStatus Int32 400
storage local immutable missingBody String "missing\\n"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenHeaderValue String headerReadCall
{guardBlock}call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body tokenHeaderValue
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

label missingPath
call missingWriteCall http.responseText
arg missingWriteCall response response
arg missingWriteCall status badStatus
arg missingWriteCall body missingBody
run missingWriteCall
bind missingWriteStatus Int32 missingWriteCall
returnValue missingWriteStatus
"""

    def test_unguarded_header_reaching_responseText_is_flagged(self) -> None:
        diagnostics = _lint_source(self._program_passing_header_to_responseText(
            addGuard=False, addOptOutMarker=False,
        ))
        self.assertIn("SS3603", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3603")[0]
        self.assertEqual(matching.subjectName, "tokenHeaderValue")
        self.assertEqual(matching.subjectKind, "bind")
        self.assertEqual(matching.gapEdge, "pointer.isNull")

    def test_pointer_isnull_guard_silences_the_warning(self) -> None:
        diagnostics = _lint_source(self._program_passing_header_to_responseText(
            addGuard=True, addOptOutMarker=False,
        ))
        self.assertNotIn("SS3603", _codes(diagnostics))

    def _program_passing_nullable_request_param_to_responseText(
        self,
        target: str,
        bindName: str,
        paramName: str,
        routePath: str,
        addGuard: bool,
    ) -> str:
        guardBlock = (
            f"""call valueMissingCheckCall pointer.isNull
arg valueMissingCheckCall pointer {bindName}
run valueMissingCheckCall
bind valueMissing Bool valueMissingCheckCall
branchIf valueMissing missingPath
"""
            if addGuard
            else ""
        )
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "{routePath}" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo nullable request parameter"
invariant echoHandler "static reply on missing value"
label startEchoHandler
storage local immutable paramName String "{paramName}"
storage local immutable okStatus Int32 200
storage local immutable badStatus Int32 400
storage local immutable missingBody String "missing\\n"
call paramReadCall {target}
arg paramReadCall request request
arg paramReadCall name paramName
run paramReadCall
bind {bindName} String paramReadCall
{guardBlock}call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body {bindName}
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

label missingPath
call missingWriteCall http.responseText
arg missingWriteCall response response
arg missingWriteCall status badStatus
arg missingWriteCall body missingBody
run missingWriteCall
bind missingWriteStatus Int32 missingWriteCall
returnValue missingWriteStatus
"""

    def test_request_path_and_query_params_are_nullable_for_SS3603(self) -> None:
        cases = [
            ("http.requestPathParam", "taskIdValue", "taskId", "/tasks/:taskId"),
            ("http.requestQueryParam", "queryValue", "q", "/search"),
        ]
        for target, bindName, paramName, routePath in cases:
            with self.subTest(target=target):
                diagnostics = _lint_source(
                    self._program_passing_nullable_request_param_to_responseText(
                        target, bindName, paramName, routePath, addGuard=False,
                    )
                )
                self.assertIn("SS3603", _codes(diagnostics))
                matching = _diagnostics_with_code(diagnostics, "SS3603")[0]
                self.assertEqual(matching.subjectName, bindName)
                self.assertEqual(matching.gapEdge, "pointer.isNull")

    def test_pointer_isnull_guard_silences_path_and_query_param_warning(self) -> None:
        cases = [
            ("http.requestPathParam", "taskIdValue", "taskId", "/tasks/:taskId"),
            ("http.requestQueryParam", "queryValue", "q", "/search"),
        ]
        for target, bindName, paramName, routePath in cases:
            with self.subTest(target=target):
                diagnostics = _lint_source(
                    self._program_passing_nullable_request_param_to_responseText(
                        target, bindName, paramName, routePath, addGuard=True,
                    )
                )
                self.assertNotIn("SS3603", _codes(diagnostics))

    def test_warning_marker_opt_out_silences_the_warning(self) -> None:
        # The intentional negative-test contract: an op that explicitly
        # opts into the adapter's null-body failure path via a marker
        # phrase in its `warning` text is not flagged.
        diagnostics = _lint_source(self._program_passing_header_to_responseText(
            addGuard=False, addOptOutMarker=True,
        ))
        self.assertNotIn("SS3603", _codes(diagnostics))

    def test_transitive_wrapper_is_recognized(self) -> None:
        # writeTextResponseWrapper takes a `body` input and forwards it
        # to http.responseText; after P3, the wrapper MUST declare
        # `responseBodyForwarder OP body` for the rule's transitive walk
        # to recognize it. Without the verb, the wrapper is opaque and
        # the caller's pass-through of a nullable bind is NOT flagged
        # (covered by TestResponseBodyForwarderVerb).
        diagnostics = _lint_source("""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation writeTextResponseWrapper
input writeTextResponseWrapper response HttpResponse
input writeTextResponseWrapper status Int32
input writeTextResponseWrapper body String
output writeTextResponseWrapper Int32
effect writeTextResponseWrapper write http.response
memory writeTextResponseWrapper arena request
async writeTextResponseWrapper no
useCapability writeTextResponseWrapper httpResponseWriter
purpose writeTextResponseWrapper "forward body to http.responseText"
invariant writeTextResponseWrapper "thin wrapper for transitive-detection test"
responseBodyForwarder writeTextResponseWrapper body
label startWriteTextResponseWrapper
call writeCall http.responseText
arg writeCall response response
arg writeCall status status
arg writeCall body body
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via wrapper"
invariant echoHandler "transitive-detection target"
label startEchoHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenHeaderValue String headerReadCall
call writeWrapperCall writeTextResponseWrapper
arg writeWrapperCall response response
arg writeWrapperCall status okStatus
arg writeWrapperCall body tokenHeaderValue
run writeWrapperCall
bind writeWrapperStatus Int32 writeWrapperCall
returnValue writeWrapperStatus
""")
        codes = _codes(diagnostics)
        self.assertIn("SS3603", codes)
        matching = _diagnostics_with_code(diagnostics, "SS3603")[0]
        self.assertEqual(matching.subjectName, "tokenHeaderValue")

    def test_no_nullable_bind_no_warning(self) -> None:
        # Echoing the request METHOD (which is non-nullable for any
        # dispatched request) into the response body should not trip
        # SS3603 — http.requestMethod is not in NULLABLE_HTTP_REQUEST_READS.
        diagnostics = _lint_source("""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/method" methodHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation methodHandler
input methodHandler request HttpRequest
input methodHandler response HttpResponse
output methodHandler Int32
effect methodHandler read http.request.method
effect methodHandler write http.response
memory methodHandler arena request
async methodHandler no
useCapability methodHandler httpRequestReader
useCapability methodHandler httpResponseWriter
purpose methodHandler "echo request method"
invariant methodHandler "method is never null for dispatched requests"
label startMethodHandler
storage local immutable okStatus Int32 200
call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
bind requestMethod String methodReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body requestMethod
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
""")
        self.assertNotIn("SS3603", _codes(diagnostics))


# ==========================================================================
# SS3619  webserver.responseHeaderAfterBody
# ==========================================================================

class TestResponseHeaderAfterBody(unittest.TestCase):
    """Headers staged after the first body writer run do not affect the
    already-latched response."""

    def _program(self, header_after_body: bool) -> str:
        header_block = """call setCookieCall http.responseHeader
arg setCookieCall response response
arg setCookieCall name setCookieHeaderName
arg setCookieCall value cookieValue
run setCookieCall
bind setCookieStatus Int32 setCookieCall
"""
        body_block = """call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
"""
        ordered_blocks = body_block + header_block if header_after_body else header_block + body_block
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/cookie" cookieHandler

capability httpResponseWriter http.response write

storage module immutable setCookieHeaderName String "Set-Cookie"
storage module immutable cookieValue String "sid=abc; HttpOnly"

operation cookieHandler
input cookieHandler request HttpRequest
input cookieHandler response HttpResponse
output cookieHandler Int32
effect cookieHandler write http.response
memory cookieHandler arena request
async cookieHandler no
useCapability cookieHandler httpResponseWriter
purpose cookieHandler "write a response with a staged cookie header"
invariant cookieHandler "headers must be staged before the body writer runs"
label startCookieHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
{ordered_blocks}returnValue writeStatus
"""

    def test_header_after_body_is_flagged(self) -> None:
        diagnostics = _lint_source(self._program(header_after_body=True))
        self.assertIn("SS3619", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3619")[0]
        self.assertEqual(matching.subjectName, "setCookieCall")
        self.assertEqual(matching.gapEdge, "http.responseHeader.order")
        self.assertIn("writeCall", matching.intentSlogan)

    def test_header_before_body_is_not_flagged(self) -> None:
        diagnostics = _lint_source(self._program(header_after_body=False))
        self.assertNotIn("SS3619", _codes(diagnostics))


# ==========================================================================
# SS3603 opt-out via new pinsNullBodyFailurePath verb
# ==========================================================================

class TestPinsNullBodyFailurePathVerb(unittest.TestCase):
    """The canonical SS3603 opt-out replaced the stringly-typed
    `null-body failure path` warning-text marker. The verb is
    `pinsNullBodyFailurePath OP "rationale"`; the rationale string is
    required (SS3606) so the contract is human-readable and machine-
    detectable both."""

    def _program_unguarded_with(self, optOutLine: str) -> str:
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler read http.request.header
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpRequestReader
useCapability probeHandler httpResponseWriter
purpose probeHandler "echo X-Token unguarded as a SS3603 test fixture"
invariant probeHandler "intentionally unguarded for opt-out testing"
{optOutLine}label startProbeHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue String headerReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body tokenValue
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_new_verb_with_rationale_silences_SS3603(self) -> None:
        diagnostics = _lint_source(self._program_unguarded_with(
            'pinsNullBodyFailurePath probeHandler "intentional negative-test coverage of the adapter\'s null-body 500 path"\n'
        ))
        codes = _codes(diagnostics)
        self.assertNotIn("SS3603", codes)
        self.assertNotIn("SS3605", codes)
        self.assertNotIn("SS3606", codes)

    def test_legacy_marker_still_silences_SS3603_for_one_cycle(self) -> None:
        diagnostics = _lint_source(self._program_unguarded_with(
            'warning probeHandler "this route intentionally exercises the adapter null-body failure path"\n'
        ))
        codes = _codes(diagnostics)
        # SS3603 is silenced by the legacy marker but SS3605 fires to
        # point the agent at the new verb.
        self.assertNotIn("SS3603", codes)
        self.assertIn("SS3605", codes)
        matching = _diagnostics_with_code(diagnostics, "SS3605")[0]
        self.assertEqual(matching.subjectName, "probeHandler")
        self.assertEqual(matching.gapEdge, "pinsNullBodyFailurePath")

    def test_new_verb_without_rationale_trips_SS3606(self) -> None:
        diagnostics = _lint_source(self._program_unguarded_with(
            "pinsNullBodyFailurePath probeHandler\n"
        ))
        codes = _codes(diagnostics)
        self.assertIn("SS3606", codes)
        matching = _diagnostics_with_code(diagnostics, "SS3606")[0]
        self.assertEqual(matching.gapEdge, "rationaleText")

    def test_warning_text_mentioning_marker_for_negative_documentation_not_flagged(self) -> None:
        # A handler that GUARDS with pointer.isNull and discusses the
        # null-body contract in its warning text (e.g. "do not switch
        # this back to the null-body failure path") must not trip SS3605:
        # the marker is not load-bearing because the op is already
        # guarded.
        diagnostics = _lint_source("""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token with a defensive guard"
invariant echoHandler "missing X-Token returns 400, never falls into the null-body failure path"
warning echoHandler "do not switch this route back to the null-body failure path; the 400 contract is tested"
label startEchoHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
storage local immutable badStatus Int32 400
storage local immutable missingBody String "missing\\n"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue String headerReadCall
call guardCall pointer.isNull
arg guardCall pointer tokenValue
run guardCall
bind tokenMissing Bool guardCall
branchIf tokenMissing missingPath
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body tokenValue
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

label missingPath
call missingWriteCall http.responseText
arg missingWriteCall response response
arg missingWriteCall status badStatus
arg missingWriteCall body missingBody
run missingWriteCall
bind missingWriteStatus Int32 missingWriteCall
returnValue missingWriteStatus
""")
        codes = _codes(diagnostics)
        # The pointer.isNull guard handles the absence case; the warning
        # text discusses the contract for documentation but is not
        # load-bearing — neither SS3603 nor SS3605 should fire.
        self.assertNotIn("SS3603", codes)
        self.assertNotIn("SS3605", codes)


# ==========================================================================
# SS3603 transitive detection via responseBodyForwarder verb (replaces the
# old `arg X body body` arg-name-shape inference)
# ==========================================================================

class TestResponseBodyForwarderVerb(unittest.TestCase):
    """Wrappers around http.response* writers must declare
    `responseBodyForwarder OP bodyArgName` for SS3603 to follow the body
    through the wrapper. A wrapper that does NOT declare the verb is
    flagged by SS3615 so nullable-body flows do not disappear behind
    helper operations."""

    _CALLER_PROGRAM = """project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation writeTextResponseWrapper
input writeTextResponseWrapper response HttpResponse
input writeTextResponseWrapper status Int32
input writeTextResponseWrapper body String
output writeTextResponseWrapper Int32
effect writeTextResponseWrapper write http.response
memory writeTextResponseWrapper arena request
async writeTextResponseWrapper no
useCapability writeTextResponseWrapper httpResponseWriter
purpose writeTextResponseWrapper "forward body to http.responseText"
invariant writeTextResponseWrapper "thin wrapper for forwarder-verb test"
{wrapperForwarderDeclaration}label startWriteTextResponseWrapper
call writeCall http.responseText
arg writeCall response response
arg writeCall status status
arg writeCall body body
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via wrapper"
invariant echoHandler "transitive-detection target"
label startEchoHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue String headerReadCall
call writeWrapperCall writeTextResponseWrapper
arg writeWrapperCall response response
arg writeWrapperCall status okStatus
arg writeWrapperCall body tokenValue
run writeWrapperCall
bind writeWrapperStatus Int32 writeWrapperCall
returnValue writeWrapperStatus
"""

    def test_wrapper_with_declaration_propagates_SS3603_to_caller(self) -> None:
        diagnostics = _lint_source(self._CALLER_PROGRAM.format(
            wrapperForwarderDeclaration="responseBodyForwarder writeTextResponseWrapper body\n"
        ))
        codes = _codes(diagnostics)
        self.assertIn("SS3603", codes)
        self.assertNotIn("SS3615", codes)
        matching = _diagnostics_with_code(diagnostics, "SS3603")[0]
        self.assertEqual(matching.subjectName, "tokenValue")

    def test_wrapper_without_declaration_trips_SS3615(self) -> None:
        diagnostics = _lint_source(self._CALLER_PROGRAM.format(
            wrapperForwarderDeclaration=""
        ))
        codes = _codes(diagnostics)
        self.assertNotIn("SS3603", codes)
        self.assertIn("SS3615", codes)
        matching = _diagnostics_with_code(diagnostics, "SS3615")[0]
        self.assertEqual(matching.subjectName, "writeTextResponseWrapper")
        self.assertEqual(matching.gapEdge, "responseBodyForwarder")

    def test_unhonored_forwarder_declaration_trips_SS3607(self) -> None:
        # An op declares responseBodyForwarder but does NOT actually
        # wire its body input to a known writer — false claim.
        diagnostics = _lint_source("""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099

capability httpResponseWriter http.response write

operation pretendsToForward
input pretendsToForward response HttpResponse
input pretendsToForward body String
output pretendsToForward Int32
effect pretendsToForward write http.response
memory pretendsToForward arena request
async pretendsToForward no
useCapability pretendsToForward httpResponseWriter
purpose pretendsToForward "claims to forward body but actually drops it"
invariant pretendsToForward "for SS3607 fixture"
responseBodyForwarder pretendsToForward body
label startPretendsToForward
storage local immutable okStatus Int32 0
returnValue okStatus
""")
        self.assertIn("SS3607", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3607")[0]
        self.assertEqual(matching.subjectName, "pretendsToForward")
        self.assertEqual(matching.gapEdge, "forwarderImplementation")

    def test_wrapper_of_wrapper_walks_to_fixed_point(self) -> None:
        # Two layers of wrappers, each declared. The outer caller's
        # nullable bind should propagate all the way through both layers
        # and trip SS3603.
        diagnostics = _lint_source("""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" echoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation innerWrapper
input innerWrapper response HttpResponse
input innerWrapper status Int32
input innerWrapper body String
output innerWrapper Int32
effect innerWrapper write http.response
memory innerWrapper arena request
async innerWrapper no
useCapability innerWrapper httpResponseWriter
purpose innerWrapper "calls http.responseText directly"
invariant innerWrapper "first layer of the forwarder chain"
responseBodyForwarder innerWrapper body
label startInnerWrapper
call writeCall http.responseText
arg writeCall response response
arg writeCall status status
arg writeCall body body
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus

operation outerWrapper
input outerWrapper response HttpResponse
input outerWrapper status Int32
input outerWrapper body String
output outerWrapper Int32
effect outerWrapper write http.response
memory outerWrapper arena request
async outerWrapper no
useCapability outerWrapper httpResponseWriter
purpose outerWrapper "calls innerWrapper"
invariant outerWrapper "second layer of the forwarder chain"
responseBodyForwarder outerWrapper body
label startOuterWrapper
call innerCall innerWrapper
arg innerCall response response
arg innerCall status status
arg innerCall body body
run innerCall
bind innerStatus Int32 innerCall
returnValue innerStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler Int32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via two-layer wrapper"
invariant echoHandler "fixed-point forwarder test"
label startEchoHandler
storage local immutable tokenHeaderName String "x-token"
storage local immutable okStatus Int32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue String headerReadCall
call outerCall outerWrapper
arg outerCall response response
arg outerCall status okStatus
arg outerCall body tokenValue
run outerCall
bind outerStatus Int32 outerCall
returnValue outerStatus
""")
        self.assertIn("SS3603", _codes(diagnostics))
        self.assertNotIn("SS3607", _codes(diagnostics))


# ==========================================================================
# SS3604  webserver.routeCoverageDrift
# ==========================================================================

class TestRouteCoverageDrift(unittest.TestCase):
    """Every declared route should have a matching routeTimeout +
    routeMiddleware OR an explicit routeTimeoutOptOut /
    routeMiddlewareOptOut so cross-cutting coverage gaps are declared
    choices, not silent omissions."""

    def _minimal_route_program(self, extraCoverageLines: str = "") -> str:
        return f"""project WebTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler
{extraCoverageLines}
capability httpResponseWriter http.response write

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_route_without_timeout_or_optout_is_flagged(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program())
        codes = _codes(diagnostics)
        # Two SS3604 hits expected: one for routeTimeout, one for routeMiddleware
        self.assertEqual(
            len(_diagnostics_with_code(diagnostics, "SS3604")),
            2,
            msg=f"expected both timeout and middleware drift; got {codes}",
        )

    def test_explicit_timeout_silences_timeout_drift(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program(
            'timeoutBudget probeBudget DurationMilliseconds 2000\n'
            'routeTimeout testServer "/probe" probeBudget\n'
        ))
        coverageDriftKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3604")
        }
        # routeMiddleware coverage still drifts; routeTimeout coverage doesn't.
        self.assertNotIn("webserver.routeTimeoutCoverageDrift", coverageDriftKinds)
        self.assertIn("webserver.routeMiddlewareCoverageDrift", coverageDriftKinds)

    def test_route_timeout_warns_when_metadata_only(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program(
            'timeoutBudget probeBudget DurationMilliseconds 2000\n'
            'routeTimeout testServer "/probe" probeBudget\n'
            'routeMiddlewareOptOut testServer "/probe" "no middleware"\n'
        ))
        self.assertIn("SS3618", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3618")[0]
        self.assertEqual(matching.kind, "webserver.routeTimeoutMetadataOnly")
        self.assertEqual(matching.gapEdge, "preemptiveTimeoutEnforcement")
        self.assertEqual(matching.subjectName, "/probe")

    def test_explicit_timeout_optout_silences_timeout_drift(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program(
            'routeTimeoutOptOut testServer "/probe" "smoke handler is uninterruptible — no budget needed"\n'
        ))
        coverageDriftKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3604")
        }
        self.assertNotIn("webserver.routeTimeoutCoverageDrift", coverageDriftKinds)

    def test_explicit_middleware_optout_silences_middleware_drift(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program(
            'routeMiddlewareOptOut testServer "/probe" "bare healthcheck — middleware would re-enter the probe loop"\n'
        ))
        coverageDriftKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3604")
        }
        self.assertNotIn("webserver.routeMiddlewareCoverageDrift", coverageDriftKinds)

    def test_both_opt_outs_clean(self) -> None:
        diagnostics = _lint_source(self._minimal_route_program(
            'routeTimeoutOptOut testServer "/probe" "no budget"\n'
            'routeMiddlewareOptOut testServer "/probe" "no middleware"\n'
        ))
        self.assertEqual(_diagnostics_with_code(diagnostics, "SS3604"), [])

    def test_server_wide_wildcard_optouts_cover_every_route(self) -> None:
        # A single `... SERVER "*" "rationale"` row is a server-wide default
        # opt-out, so an app with no per-route middleware/timeout does not need
        # one opt-out row per route (the field-log 28-rows-across-14-routes pain).
        diagnostics = _lint_source(self._minimal_route_program(
            'routeTimeoutOptOut testServer "*" "this server opts out of route timeouts by default"\n'
            'routeMiddlewareOptOut testServer "*" "this server opts out of route middleware by default"\n'
        ))
        self.assertEqual(_diagnostics_with_code(diagnostics, "SS3604"), [])

    def test_server_wide_middleware_wildcard_leaves_timeout_drift(self) -> None:
        # The wildcard is per-contract: a middleware-only server-wide opt-out
        # silences middleware drift but not the still-missing timeout coverage.
        diagnostics = _lint_source(self._minimal_route_program(
            'routeMiddlewareOptOut testServer "*" "no middleware anywhere"\n'
        ))
        coverageDriftKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3604")
        }
        self.assertNotIn("webserver.routeMiddlewareCoverageDrift", coverageDriftKinds)
        self.assertIn("webserver.routeTimeoutCoverageDrift", coverageDriftKinds)


# ==========================================================================
# SS3617  webserver.lifecycleHookContract
# ==========================================================================

class TestWebserverLifecycleHookContract(unittest.TestCase):
    def _program(self, hookRows: str, hookOperation: str) -> str:
        return f"""project WebLifecycleTest
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
{hookRows}
route testServer GET "/probe" probeHandler
routeTimeoutOptOut testServer "/probe" "no budget"
routeMiddlewareOptOut testServer "/probe" "no middleware"

operation probeHandler
input operation probeHandler request HttpRequest
input operation probeHandler response HttpResponse
output operation probeHandler Int32
memory probeHandler arena request
async probeHandler no
purpose operation probeHandler "smoke handler"
storage local immutable okStatus Int32 0
return value okStatus

{hookOperation}
"""

    def test_lifecycle_hook_handler_must_exist(self) -> None:
        diagnostics = _lint_source(self._program(
            "webServerStartup testServer missingStartup",
            "",
        ))
        lifecycleKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3617")
        }
        self.assertIn("webserver.lifecycleHookUndefinedHandler", lifecycleKinds)

    def test_lifecycle_hook_handler_must_not_take_inputs(self) -> None:
        diagnostics = _lint_source(self._program(
            "webServerStartup testServer startup",
            """operation startup
input operation startup request HttpRequest
output operation startup Int32
memory startup heap no
async startup no
purpose operation startup "bad startup"
storage local immutable okStatus Int32 0
return value okStatus
""",
        ))
        lifecycleKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3617")
        }
        self.assertIn("webserver.lifecycleHookHasInputs", lifecycleKinds)

    def test_lifecycle_hook_handler_must_return_int32(self) -> None:
        diagnostics = _lint_source(self._program(
            "webServerShutdown testServer shutdown",
            """operation shutdown
output operation shutdown ExitCode
memory shutdown heap no
async shutdown no
purpose operation shutdown "bad shutdown"
storage local immutable okStatus ExitCode 0
return value okStatus
""",
        ))
        lifecycleKinds = {
            d.kind for d in _diagnostics_with_code(diagnostics, "SS3617")
        }
        self.assertIn("webserver.lifecycleHookOutputMustBeInt32", lifecycleKinds)

    def test_valid_lifecycle_hooks_are_clean(self) -> None:
        diagnostics = _lint_source(self._program(
            "webServerStartup testServer startup\nwebServerShutdown testServer shutdown",
            """storage module immutable successStatus Int32 0
operation startup
output operation startup Int32
memory startup heap no
async startup no
purpose operation startup "good startup"
return value successStatus
operation shutdown
output operation shutdown Int32
memory shutdown heap no
async shutdown no
purpose operation shutdown "good shutdown"
return value successStatus
""",
        ))
        self.assertEqual(_diagnostics_with_code(diagnostics, "SS3617"), [])


# ==========================================================================
# SS3608  webserver.rationaleReferencesUnknownCall / rationaleMissingText
# ==========================================================================

class TestRationaleCallVerb(unittest.TestCase):
    """`rationale CALL "text"` attaches a rationale to a specific call.
    It must name a real call AND carry non-empty text — both are part
    of the contract that distinguishes the verb from a `# rationale:`
    proximity comment."""

    _HANDLER_TEMPLATE = """project Test
operation main
output main Void
purpose main "smoke"
invariant main "smoke"
label startMain
storage local immutable okStatus Int32 0
call ackCall console.writeLine
arg ackCall console console
arg ackCall text okStatus
run ackCall
{rationaleLines}returnValue okStatus
"""

    def test_rationale_attached_to_known_call_not_flagged(self) -> None:
        diagnostics = _lint_source(self._HANDLER_TEMPLATE.format(
            rationaleLines='rationale ackCall "console.writeLine here documents why we ack instead of bind"\n'
        ))
        self.assertNotIn("SS3608", _codes(diagnostics))

    def test_rationale_attached_to_unknown_call_flagged(self) -> None:
        diagnostics = _lint_source(self._HANDLER_TEMPLATE.format(
            rationaleLines='rationale typedCallNameMismatch "this call name does not exist in the op"\n'
        ))
        self.assertIn("SS3608", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3608")[0]
        self.assertEqual(matching.subjectName, "typedCallNameMismatch")
        self.assertEqual(matching.kind, "webserver.rationaleReferencesUnknownCall")
        self.assertTrue(matching.blocksCompile)

    def test_rationale_with_empty_text_flagged(self) -> None:
        diagnostics = _lint_source(self._HANDLER_TEMPLATE.format(
            rationaleLines='rationale ackCall ""\n'
        ))
        self.assertIn("SS3608", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3608")[0]
        self.assertEqual(matching.kind, "webserver.rationaleMissingText")


# ==========================================================================
# Capability hierarchy smoke test (P11) — proves http.request authorizes
# http.request.method without a narrower capability declaration
# ==========================================================================

class TestCapabilityHierarchy(unittest.TestCase):
    """A broad `capability X http.request read` must authorize narrow
    effects like `effect OP read http.request.method` without requiring
    a per-narrow capability declaration. If _effect_path_covers regresses
    to literal equality, this test fires SS3101
    `missingCapabilityUse` and fails."""

    def test_broad_capability_authorizes_narrow_effect(self) -> None:
        diagnostics = _lint_source("""project Test
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/echo" methodEchoHandler

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation methodEchoHandler
input methodEchoHandler request HttpRequest
input methodEchoHandler response HttpResponse
output methodEchoHandler Int32
effect methodEchoHandler read http.request.method
effect methodEchoHandler write http.response
memory methodEchoHandler arena request
async methodEchoHandler no
useCapability methodEchoHandler httpRequestReader
useCapability methodEchoHandler httpResponseWriter
purpose methodEchoHandler "smoke test that http.request authorizes http.request.method"
invariant methodEchoHandler "if missingCapabilityUse fires here, the hierarchy walk is broken"
label startMethodEchoHandler
storage local immutable okStatus Int32 200
call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
bind requestMethod String methodReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body requestMethod
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
""")
        # The whole point: no missing-capability diagnostic for the narrow
        # `read http.request.method` effect, because the broad
        # `http.request read` capability covers it via _effect_path_covers.
        capabilityCoverageCodes = {
            d.code for d in diagnostics
            if "missingCapability" in d.kind or "effectWithoutCapability" in d.kind
        }
        self.assertFalse(
            capabilityCoverageCodes,
            msg=f"capability hierarchy regression — narrow effect was not authorized by broad capability: {capabilityCoverageCodes}",
        )


# ==========================================================================
# SS3609  webserver.routeHandlerInputNameMismatch
# ==========================================================================

class TestRouteHandlerInputNames(unittest.TestCase):
    """Route- and middleware-bound ops MUST name their HttpRequest input
    `request` and their HttpResponse input `response`. The names are
    part of the native HTTP ABI's name-based-lookup contract — a
    mismatch compiles and runs but silently breaks SS3603 / citation
    walks / agent reading. Graded ERROR + blocksCompile."""

    _PROGRAM_WITH_HANDLER_NAMED = """project Test
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler

capability httpResponseWriter http.response write

operation probeHandler
input probeHandler {requestInputName} HttpRequest
input probeHandler {responseInputName} HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler for SS3609 fixture"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response {responseInputName}
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_canonical_names_not_flagged(self) -> None:
        diagnostics = _lint_source(self._PROGRAM_WITH_HANDLER_NAMED.format(
            requestInputName="request",
            responseInputName="response",
        ))
        self.assertNotIn("SS3609", _codes(diagnostics))

    def test_request_input_named_req_flagged(self) -> None:
        diagnostics = _lint_source(self._PROGRAM_WITH_HANDLER_NAMED.format(
            requestInputName="req",
            responseInputName="response",
        ))
        self.assertIn("SS3609", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3609")[0]
        self.assertEqual(matching.subjectName, "probeHandler")
        self.assertEqual(matching.gapEdge, "input.canonicalName")
        # Strictness assertions — SS3609 is a hard contract violation, not a hint.
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.severity.value, "error")
        # The diagnostic cites the route binding site so an agent can
        # see WHY this op is held to the canonical-name contract.
        self.assertTrue(matching.related, "expected related span citing the route binding")
        # And the fix candidate is exact, with evidence pointing at the
        # offending line.
        self.assertEqual(matching.fixCandidates[0].name, "renameInputToCanonical")
        self.assertIn("input probeHandler request HttpRequest", matching.fixCandidates[0].shape)
        self.assertTrue(matching.fixCandidates[0].autoApplicable)

    def test_response_input_named_resp_flagged(self) -> None:
        diagnostics = _lint_source(self._PROGRAM_WITH_HANDLER_NAMED.format(
            requestInputName="request",
            responseInputName="resp",
        ))
        self.assertIn("SS3609", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3609")[0]
        self.assertIn("response slot", matching.intentSlogan)

    def test_both_inputs_mismatched_emits_two_diagnostics(self) -> None:
        diagnostics = _lint_source(self._PROGRAM_WITH_HANDLER_NAMED.format(
            requestInputName="r",
            responseInputName="w",
        ))
        ss3609 = _diagnostics_with_code(diagnostics, "SS3609")
        self.assertEqual(len(ss3609), 2)

    def test_middleware_inputs_held_to_same_contract(self) -> None:
        # A middleware op bound via routeMiddleware is also reachable
        # from the route ABI — same canonical-name contract applies.
        diagnostics = _lint_source("""project Test
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler
routeMiddleware testServer "/probe" tracingMiddleware

capability httpResponseWriter http.response write

operation tracingMiddleware
input tracingMiddleware req HttpRequest
input tracingMiddleware resp HttpResponse
output tracingMiddleware Int32
effect tracingMiddleware write http.response
memory tracingMiddleware arena request
async tracingMiddleware no
useCapability tracingMiddleware httpResponseWriter
purpose tracingMiddleware "non-canonical input names should fire SS3609"
invariant tracingMiddleware "middleware ABI follows route ABI"
label startTracingMiddleware
storage local immutable continueStatus Int32 0
returnValue continueStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "canonical-name handler so only the middleware trips SS3609"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
""")
        ss3609 = _diagnostics_with_code(diagnostics, "SS3609")
        # Two hits — one for the middleware's `req`, one for its `resp`.
        self.assertEqual(len(ss3609), 2)
        for diag in ss3609:
            self.assertEqual(diag.subjectName, "tracingMiddleware")

    def test_non_route_op_with_HttpRequest_input_not_flagged(self) -> None:
        # An operation that happens to take an HttpRequest but is NOT
        # reachable from any route binding is NOT a route handler —
        # SS3609 does not apply.
        diagnostics = _lint_source("""project Test
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler

capability httpResponseWriter http.response write

operation requestInspector
input requestInspector req HttpRequest
output requestInspector Int32
memory requestInspector arena request
async requestInspector no
purpose requestInspector "library helper, NOT a route handler"
invariant requestInspector "called only from other ops, not from a route binding"
label startRequestInspector
storage local immutable inspectStatus Int32 0
returnValue inspectStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "canonical handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
""")
        self.assertNotIn("SS3609", _codes(diagnostics))


# ==========================================================================
# Source-of-truth drift guard for native HTTP target sets (P9)
# ==========================================================================

class TestHttpTargetSourceOfTruth(unittest.TestCase):
    """The native HTTP target surface lives in three places: semsc.py's
    dispatch block, semlint.py's classifier constants, and docs/reference/syntax-inventory.md's
    umbrella rows. Adding a target in one place without the others
    leaves a silent contract drift — SS3603 misses new readers, SS3601
    misses new writers, and docs/reference/syntax-inventory.md becomes a lie.

    This test parses semsc.py for every `"http.*"` literal target,
    then asserts the resulting set equals
    `semlint.ALL_NATIVE_HTTP_TARGETS`. A mismatch prints a sorted-set
    diff naming which targets are in semsc but not the linter, and
    vice versa, so the fix site is obvious.

    The test deliberately reads source rather than reflecting on
    imported names — semsc.py imports llvmlite, which is too heavy a
    dep for the linter test suite. Source-grep is sufficient because
    the dispatch block is the only place in semsc.py that
    pattern-matches on `"http.*"` literal targets.
    """

    @classmethod
    def setUpClass(cls) -> None:
        repoRoot = Path(__file__).resolve().parents[2]
        cls.semscPath = repoRoot / "SemanticScript" / "compiler" / "semsc.py"
        cls.syntaxInventoryPath = repoRoot / "docs" / "reference" / "syntax-inventory.md"

    def _http_targets_in_semsc(self) -> "set[str]":
        """Extract every `http.X` literal target referenced anywhere in
        semsc.py. Catches both single-target `if target == "http.X":`
        lines and multi-target list literals like `("http.X", "http.Y",
        ...)` used for multipart dispatch."""
        import re
        sourceText = self.semscPath.read_text(encoding="utf-8")
        targetPattern = re.compile(r'"(http\.[A-Za-z_][A-Za-z0-9_]*)"')
        return set(targetPattern.findall(sourceText))

    def _http_targets_in_syntax_inventory(self) -> "set[str]":
        """Extract every `http.X` target referenced in docs/reference/syntax-inventory.md. The
        spec wraps targets in backticks (` `http.X` `) so the regex is
        anchored on that."""
        import re
        sourceText = self.syntaxInventoryPath.read_text(encoding="utf-8")
        targetPattern = re.compile(r'`(http\.[A-Za-z_][A-Za-z0-9_]*)`')
        return set(targetPattern.findall(sourceText))

    def test_semsc_dispatch_set_matches_linter_classifier_set(self) -> None:
        targetsInSemsc = self._http_targets_in_semsc()
        targetsInLinter = set(semlint.ALL_NATIVE_HTTP_TARGETS)
        onlyInSemsc = targetsInSemsc - targetsInLinter
        onlyInLinter = targetsInLinter - targetsInSemsc
        # Allowlist for non-target `"http.X"` strings inside semsc.py
        # that aren't dispatched (e.g., diagnostic message strings).
        # Currently empty — every quoted http.* in semsc is a real
        # dispatch target. Add entries here with a comment explaining
        # WHY a particular literal isn't a dispatch target.
        ALLOWED_NON_TARGETS_IN_SEMSC: set = set()
        onlyInSemsc -= ALLOWED_NON_TARGETS_IN_SEMSC
        self.assertFalse(
            onlyInSemsc,
            msg=(
                f"http.* targets dispatched in semsc.py but NOT classified "
                f"in semlint.ALL_NATIVE_HTTP_TARGETS: "
                f"{sorted(onlyInSemsc)}. Add each to the appropriate "
                f"classifier set (NON_NULLABLE_HTTP_REQUEST_READS / "
                f"NULLABLE_HTTP_REQUEST_READS / HTTP_RESPONSE_BODY_WRITERS / "
                f"HTTP_RESPONSE_OTHER_WRITERS / HTTP_UTILITY_TARGETS) and to the docs/reference/syntax-inventory.md "
                f"umbrella row."
            ),
        )
        self.assertFalse(
            onlyInLinter,
            msg=(
                f"http.* targets classified in semlint but NOT dispatched "
                f"in semsc.py: {sorted(onlyInLinter)}. Either the lowering "
                f"is missing (compile would zero-stub these silently!) or "
                f"the linter constants are stale and the target was "
                f"removed from the runtime without a matching linter sweep."
            ),
        )

    def test_every_dispatch_target_appears_in_syntax_inventory(self) -> None:
        targetsInSemsc = self._http_targets_in_semsc()
        targetsInSyntaxInventory = self._http_targets_in_syntax_inventory()
        missingFromSyntax = targetsInSemsc - targetsInSyntaxInventory
        self.assertFalse(
            missingFromSyntax,
            msg=(
                f"http.* targets dispatched in semsc.py but not "
                f"mentioned in docs/reference/syntax-inventory.md: {sorted(missingFromSyntax)}. "
                f"Add each to the umbrella row so the spec inventory "
                f"matches the runtime surface."
            ),
        )

    def test_classifier_sets_are_disjoint(self) -> None:
        """A target must belong to exactly one of the four classifier
        sets — otherwise membership-based decisions in SS3603 / SS3601
        become ambiguous."""
        classifierSets = {
            "NON_NULLABLE_HTTP_REQUEST_READS": semlint.NON_NULLABLE_HTTP_REQUEST_READS,
            "NULLABLE_HTTP_REQUEST_READS": semlint.NULLABLE_HTTP_REQUEST_READS,
            "HTTP_RESPONSE_BODY_WRITERS": semlint.HTTP_RESPONSE_BODY_WRITERS,
            "HTTP_RESPONSE_OTHER_WRITERS": semlint.HTTP_RESPONSE_OTHER_WRITERS,
        }
        sortedNames = sorted(classifierSets.keys())
        for indexA in range(len(sortedNames)):
            for indexB in range(indexA + 1, len(sortedNames)):
                nameA = sortedNames[indexA]
                nameB = sortedNames[indexB]
                overlap = classifierSets[nameA] & classifierSets[nameB]
                self.assertFalse(
                    overlap,
                    msg=(
                        f"classifier sets {nameA} and {nameB} overlap on "
                        f"{sorted(overlap)}; each http.* target must "
                        f"belong to exactly ONE set"
                    ),
                )


# ==========================================================================
# SS3610  webserver.middlewareReturnNotMiddlewareControl
# ==========================================================================

class TestMiddlewareReturnType(unittest.TestCase):
    """Middleware ops bound via routeMiddleware MUST declare `output OP
    MiddlewareControl`. The dispatcher's short-circuit semantics depend
    on the typed enum; bare Int32 erases the named-case
    contract."""

    def _program_with_middleware_output(self, outputDeclaration: str) -> str:
        return f"""project Test
target webServer
runtime native 1
webServer testServer
serverHost testServer "127.0.0.1"
serverPort testServer 18099
route testServer GET "/probe" probeHandler
routeMiddleware testServer "/probe" probeMiddleware

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation probeMiddleware
input probeMiddleware request HttpRequest
input probeMiddleware response HttpResponse
{outputDeclaration}
effect probeMiddleware read http.request.path
effect probeMiddleware write http.response
memory probeMiddleware arena request
async probeMiddleware no
useCapability probeMiddleware httpRequestReader
useCapability probeMiddleware httpResponseWriter
purpose probeMiddleware "fixture for SS3610"
invariant probeMiddleware "returns the continue case to fall through to the handler"
label startProbeMiddleware
returnValue continueMiddlewareControl

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler Int32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus Int32 200
storage local immutable bodyText String "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus Int32 writeCall
returnValue writeStatus
"""

    def test_middleware_with_int32_output_flagged(self) -> None:
        diagnostics = _lint_source(self._program_with_middleware_output(
            "output probeMiddleware Int32"
        ))
        self.assertIn("SS3610", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3610")[0]
        self.assertEqual(matching.subjectName, "probeMiddleware")
        self.assertEqual(matching.gapEdge, "output.MiddlewareControl")
        # Strictness checks — SS3610 is a hard ABI violation.
        self.assertTrue(matching.blocksCompile)
        self.assertEqual(matching.severity.value, "error")
        # The diagnostic cites the route binding line so the agent sees
        # which routeMiddleware row is forcing this op onto the contract.
        self.assertTrue(matching.related)
        # Fix candidate is exact + auto-applicable.
        self.assertEqual(matching.fixCandidates[0].name, "changeOutputTypeToMiddlewareControl")
        self.assertIn("output probeMiddleware MiddlewareControl", matching.fixCandidates[0].shape)
        self.assertTrue(matching.fixCandidates[0].autoApplicable)

    def test_middleware_with_middleware_control_output_not_flagged(self) -> None:
        diagnostics = _lint_source(self._program_with_middleware_output(
            "output probeMiddleware MiddlewareControl"
        ))
        self.assertNotIn("SS3610", _codes(diagnostics))

    def test_middleware_with_other_typed_output_flagged(self) -> None:
        # A middleware returning a domain-specific enum that ISN'T
        # MiddlewareControl is still wrong — the dispatcher reads the
        # raw i32 as a MiddlewareControl, so any other typing is a
        # silent contract drift.
        diagnostics = _lint_source(self._program_with_middleware_output(
            "output probeMiddleware ExitCode"
        ))
        self.assertIn("SS3610", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3610")[0]
        self.assertIn("ExitCode", matching.intentSlogan)

    def test_non_middleware_op_returning_int32_not_flagged(self) -> None:
        # An operation that's NOT bound via routeMiddleware can return
        # any type — SS3610 only speaks to the dispatcher-bound subset.
        diagnostics = _lint_source("""project Test
operation helperOp
output helperOp Int32
purpose helperOp "ordinary helper, not a middleware"
invariant helperOp "no routeMiddleware binding => SS3610 does not apply"
label startHelperOp
storage local immutable okValue Int32 0
returnValue okValue
""")
        self.assertNotIn("SS3610", _codes(diagnostics))


# ==========================================================================
# MiddlewareControl built-in enum auto-registration
# ==========================================================================

class TestMiddlewareControlBuiltinEnum(unittest.TestCase):
    """semsc.py auto-registers the MiddlewareControl enum on every
    parsed program so middleware ops can declare
    `output OP MiddlewareControl` and use the named cases
    `continueMiddlewareControl` / `shortCircuitMiddlewareControl`
    without an explicit `enum MiddlewareControl …` declaration in
    source. The linter must see the same registration."""

    def _parse_with_semsc(self, source: str):
        import importlib.util
        repoRoot = Path(__file__).resolve().parents[2]
        semscPath = repoRoot / "SemanticScript" / "compiler" / "semsc.py"
        moduleSpec = importlib.util.spec_from_file_location("semsc_under_test", semscPath)
        semscModule = importlib.util.module_from_spec(moduleSpec)
        moduleSpec.loader.exec_module(semscModule)
        return semscModule.parse(source)

    def test_middleware_control_enum_present_in_every_parsed_program(self) -> None:
        prog = self._parse_with_semsc("project Trivial\n")
        self.assertIn("MiddlewareControl", prog.enums)
        enumFact = prog.enums["MiddlewareControl"]
        self.assertEqual(enumFact.repr, "Int32")
        caseNames = [name for name, _value in enumFact.cases]
        self.assertEqual(
            caseNames,
            ["continueMiddlewareControl", "shortCircuitMiddlewareControl"],
        )

    def test_case_consts_are_typed_MiddlewareControl_not_int32(self) -> None:
        # The case-name consts carry the enum type so the result-contract
        # checker can compare them apples-to-apples against `output OP
        # MiddlewareControl`. If these come back as Int32 the
        # contract enforcement falls back to the loose equivalence
        # check and silently allows raw integers at returnValue sites.
        prog = self._parse_with_semsc("project Trivial\n")
        continueType, continueValue = prog.consts["continueMiddlewareControl"]
        shortCircuitType, shortCircuitValue = prog.consts["shortCircuitMiddlewareControl"]
        self.assertEqual(continueType, "MiddlewareControl")
        self.assertEqual(continueValue, 0)
        self.assertEqual(shortCircuitType, "MiddlewareControl")
        self.assertEqual(shortCircuitValue, 1)


class TestSqliteBuiltinSurface(unittest.TestCase):
    """The proposed standard.sqlite sample relies on compiler/linter built-ins
    for enum case values and opaque handle aliases."""

    def test_sqlite_builtin_values_are_registered_for_reference_checks(self) -> None:
        with TemporaryDirectory() as tempDir:
            fixturePath = Path(tempDir) / "fixture.sscript"
            fixturePath.write_text("project Trivial\n", encoding="utf-8")
            facts = semlint.parse_file(fixturePath)

        self.assertEqual(
            facts.consts["inMemorySqliteOpenMode"].type_name,
            "SqliteOpenMode",
        )
        self.assertEqual(facts.type_aliases["SqliteRowId"], "Int64")
        self.assertIn("SqliteDatabase", facts.type_aliases)

    def test_sqlite_builtin_case_is_not_an_unresolved_arg_value(self) -> None:
        diagnostics = _lint_source("""project SqliteBuiltinSmoke
operation openDatabase
output openDatabase Void
purpose openDatabase "prove sqlite enum cases are visible to semlint"
storage local immutable sqlitePath String ":memory:"
call openDatabaseCall sqlite.openDatabase
arg openDatabaseCall path sqlitePath
arg openDatabaseCall mode inMemorySqliteOpenMode
run openDatabaseCall
""")
        self.assertNotIn("SS4105", _codes(diagnostics))


# ==========================================================================
# SS3612  returnContract.voidReturnValueShouldBeReturnVoid
# ==========================================================================

class TestVoidReturnValueShouldBeReturnVoid(unittest.TestCase):
    """`output OP Void` operations should end with `returnVoid`, not
    `returnValue NAME` — the legacy form leaks the user-op ABI's i32
    zero sentinel into the source. The rule fires WARNING because the
    legacy form compiles correctly; --strict promotes to fatal."""

    def test_void_output_with_return_value_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation legacyVoidOp
output legacyVoidOp Void
purpose legacyVoidOp "returns Void per the output line but uses returnValue sentinel"
invariant legacyVoidOp "legacy shape"
label startLegacyVoidOp
storage local immutable legacyZeroSentinel Int32 0
returnValue legacyZeroSentinel
""")
        self.assertIn("SS3612", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3612")[0]
        self.assertEqual(matching.subjectName, "legacyVoidOp")
        self.assertEqual(matching.gapEdge, "returnVoid")
        self.assertEqual(matching.fixCandidates[0].name, "replaceReturnValueWithReturnVoid")
        self.assertEqual(matching.fixCandidates[0].shape, "return void")
        self.assertTrue(matching.fixCandidates[0].autoApplicable)

    def test_void_output_with_return_void_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation cleanVoidOp
output cleanVoidOp Void
purpose cleanVoidOp "explicit returnVoid form"
invariant cleanVoidOp "source matches semantic contract"
label startCleanVoidOp
returnVoid
""")
        self.assertNotIn("SS3612", _codes(diagnostics))

    def test_int32_output_with_return_value_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation typedOp
output typedOp Int32
purpose typedOp "returns a typed status"
invariant typedOp "returnValue is correct for non-Void output"
label startTypedOp
storage local immutable okStatus Int32 0
returnValue okStatus
""")
        self.assertNotIn("SS3612", _codes(diagnostics))

    def test_second_void_output_fixture_also_caught(self) -> None:
        diagnostics = _lint_source("""project Test
operation voidSentinelOp
output voidSentinelOp Void
purpose voidSentinelOp "Void output still requires returnVoid"
invariant voidSentinelOp "returnValue should be rejected for Void outputs"
label startVoidSentinelOp
storage local immutable zeroSentinel Int32 0
returnValue zeroSentinel
""")
        self.assertIn("SS3612", _codes(diagnostics))


# ==========================================================================
# SS3613  narrative.referencesLineNumber
# ==========================================================================

class TestNarrativeReferencesLineNumber(unittest.TestCase):
    """Narrative text (purpose/invariant/warning/rationale) should cite
    stable identifiers — function names, rule IDs, grep-anchors — not
    `<file>:<line>` patterns that drift on the next insertion."""

    def test_invariant_with_filename_colon_line_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
invariant refOp "see semsc.py:3674 for the lowering details"
label startRefOp
returnVoid
""")
        self.assertIn("SS3613", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3613")[0]
        self.assertEqual(matching.subjectKind, "invariant")
        self.assertIn("semsc.py:3674", matching.intentSlogan)

    def test_warning_with_test_file_line_range_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
warning refOp "the assertion at test_http_runtime_gauntlet.py:273-279 verifies this"
label startRefOp
returnVoid
""")
        self.assertIn("SS3613", _codes(diagnostics))

    def test_invariant_with_bare_line_NN_phrase_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
invariant refOp "the C runtime branches at line 182 to default the type"
label startRefOp
returnVoid
""")
        self.assertIn("SS3613", _codes(diagnostics))

    def test_invariant_citing_function_name_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
invariant refOp "see semsc.py's _check_route_methods for the dispatcher logic"
label startRefOp
returnVoid
""")
        self.assertNotIn("SS3613", _codes(diagnostics))

    def test_invariant_citing_rule_id_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
invariant refOp "the SS3603 lint rule enforces the null-guard contract here"
label startRefOp
returnVoid
""")
        self.assertNotIn("SS3613", _codes(diagnostics))

    def test_invariant_citing_spec_anchor_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation refOp
output refOp Void
purpose refOp "smoke"
invariant refOp "tracked under docs/reference/syntax-inventory.md#routeMiddleware as Impl'd"
label startRefOp
returnVoid
""")
        self.assertNotIn("SS3613", _codes(diagnostics))


# ==========================================================================
# SS3614  buildTape.mainFileMustExist
# ==========================================================================

class TestMainFileMustExist(unittest.TestCase):
    """`mainFile PROJECT "PATH"` in a build tape must reference a file
    that exists on disk. Catches rename-rot: when the module source
    gets renamed but the build tape's mainFile row isn't updated, the
    build silently fails later. SS3614 surfaces the mismatch up front."""

    def _write_build_tape(self, tempDirPath: Path, mainFileName: str,
                          alsoCreate=None) -> Path:
        """Write a build.sem fixture referencing `mainFileName`. If
        `alsoCreate` is non-empty, also drop an actual file with that
        name in the temp dir — used to test both the present-file and
        missing-file paths against the same template."""
        buildTapeSource = f"""project SampleProject
buildProject sampleProject
modulePath sampleProject github.com/example/sample
languageVersion sampleProject "1.0"
sourceRoot sampleProject "."
mainFile sampleProject "{mainFileName}"
"""
        buildTapePath = tempDirPath / "build.sem"
        buildTapePath.write_text(buildTapeSource, encoding="utf-8")
        if alsoCreate:
            (tempDirPath / alsoCreate).write_text(
                "module example.sample\n", encoding="utf-8"
            )
        return buildTapePath

    def test_missing_main_file_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            tempDirPath = Path(tempDir)
            buildTapePath = self._write_build_tape(
                tempDirPath, "main.sem", alsoCreate=None
            )
            diagnostics = semlint.lint_path(buildTapePath)
            self.assertIn("SS3614", _codes(diagnostics))
            matching = _diagnostics_with_code(diagnostics, "SS3614")[0]
            self.assertEqual(matching.subjectName, "main.sem")
            self.assertEqual(matching.subjectKind, "mainFile")
            self.assertEqual(matching.gapEdge, "filesystem.exists")
            self.assertTrue(matching.blocksCompile)
            self.assertEqual(matching.severity.value, "error")
            # The invariantRule should name the resolved path so an agent
            # reading the diagnostic knows where the resolver looked.
            self.assertIn("main.sem", matching.invariantRule)

    def test_present_main_file_is_not_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            tempDirPath = Path(tempDir)
            buildTapePath = self._write_build_tape(
                tempDirPath, "main.sem", alsoCreate="main.sem"
            )
            diagnostics = semlint.lint_path(buildTapePath)
            self.assertNotIn("SS3614", _codes(diagnostics))

    def test_typoed_main_file_caught(self) -> None:
        # A common rename-rot shape: the real file is `main.sem` but the
        # build tape still says `main.sscript`.
        with TemporaryDirectory() as tempDir:
            tempDirPath = Path(tempDir)
            buildTapePath = self._write_build_tape(
                tempDirPath, "main.sscript", alsoCreate="main.sem"
            )
            diagnostics = semlint.lint_path(buildTapePath)
            self.assertIn("SS3614", _codes(diagnostics))
            matching = _diagnostics_with_code(diagnostics, "SS3614")[0]
            self.assertEqual(matching.subjectName, "main.sscript")

    def test_non_build_tape_emits_no_diagnostic(self) -> None:
        # A regular module file with no `mainFile` row must not trip
        # the rule (the linter is sweeping every file, not just build
        # tapes).
        with TemporaryDirectory() as tempDir:
            tempDirPath = Path(tempDir)
            modulePath = tempDirPath / "main.sem"
            modulePath.write_text(
                "module example.sample\n"
                "operation main\n"
                "output main Void\n"
                "purpose main \"smoke\"\n"
                "label startMain\n"
                "returnVoid\n",
                encoding="utf-8",
            )
            diagnostics = semlint.lint_path(modulePath)
            self.assertNotIn("SS3614", _codes(diagnostics))


# ==========================================================================
# SS2515  module.standardLibraryDefinesSmokeMain
# ==========================================================================

class TestStdlibModuleNoSmokeMain(unittest.TestCase):
    _STDLIB_MODULE_WITH_MAIN = (
        "module standard.demo\n"
        "exportConstant standard.demo demoModuleVersionText\n"
        "storage module immutable demoModuleVersionText "
        "String \"standard.demo 0.1\"\n"
        "operation main\n"
        "output operation main ExitCode\n"
        "memory main heap no\n"
        "async main no\n"
        "purpose operation main \"smoke\"\n"
        "label startMain\n"
        "storage module immutable exitOkCode ExitCode 0\n"
        "return value exitOkCode\n"
    )

    def test_stdlib_implementation_module_with_main_is_flagged(self) -> None:
        diagnostics = _lint_source_at("main.sem", self._STDLIB_MODULE_WITH_MAIN)
        self.assertIn("SS2515", _codes(diagnostics))

    def test_colocated_test_file_with_main_is_not_flagged(self) -> None:
        # The smoke main legitimately lives in main.test.sem.
        diagnostics = _lint_source_at("main.test.sem", self._STDLIB_MODULE_WITH_MAIN)
        self.assertNotIn("SS2515", _codes(diagnostics))

    def test_non_standard_module_with_main_is_not_flagged(self) -> None:
        # App modules under app.* legitimately declare the entry `main`.
        appModule = self._STDLIB_MODULE_WITH_MAIN.replace(
            "standard.demo", "app.demo"
        )
        diagnostics = _lint_source_at("main.sem", appModule)
        self.assertNotIn("SS2515", _codes(diagnostics))

    def test_stdlib_module_without_main_is_not_flagged(self) -> None:
        moduleOnly = (
            "module standard.demo\n"
            "exportConstant standard.demo demoModuleVersionText\n"
            "storage module immutable demoModuleVersionText "
            "String \"standard.demo 0.1\"\n"
        )
        diagnostics = _lint_source_at("main.sem", moduleOnly)
        self.assertNotIn("SS2515", _codes(diagnostics))


# ==========================================================================
# SS4302  typeIntegrity.bindReturnDomainMismatch
# ==========================================================================

class TestBindReturnDomainMismatch(unittest.TestCase):
    _SERVER_HEAD = (
        "project P\n"
        "target webServer\n"
        "module examples.p\n"
        "webServer s\n"
        "serverHost s \"127.0.0.1\"\n"
        "serverPort s 8080\n"
        "route s GET \"/\" h\n"
        "routeTimeoutOptOut s \"/\" \"d\"\n"
        "routeMiddlewareOptOut s \"/\" \"d\"\n"
        "operation h\n"
        "input operation h request HttpRequest\n"
        "input operation h response HttpResponse\n"
        "output operation h Int32\n"
        "effect h write http.response\n"
        "async h no\n"
        "purpose operation h \"x\"\n"
        "storage local immutable a String \"a\"\n"
        "storage local immutable b String \"b\"\n"
    )

    def test_string_result_bound_as_html_fragment_is_flagged(self) -> None:
        # The string.concat -> HtmlFragment SIGSEGV class, caught at lint.
        diagnostics = _lint_source(self._SERVER_HEAD + (
            "call joinCall string.concat\n"
            "argument joinCall left String a\n"
            "argument joinCall right String b\n"
            "run joinCall\n"
            "bind value cardsFragment HtmlFragment joinCall\n"
            "return value 0\n"
        ))
        self.assertIn("SS4302", _codes(diagnostics))
        diag = _diagnostics_with_code(diagnostics, "SS4302")[0]
        self.assertEqual(diag.subjectName, "cardsFragment")
        self.assertTrue(diag.blocksCompile)

    def test_string_result_bound_as_string_is_clean(self) -> None:
        diagnostics = _lint_source(self._SERVER_HEAD + (
            "call joinCall string.concat\n"
            "argument joinCall left String a\n"
            "argument joinCall right String b\n"
            "run joinCall\n"
            "bind value joined String joinCall\n"
            "return value 0\n"
        ))
        self.assertNotIn("SS4302", _codes(diagnostics))

    def test_http_status_int_bound_as_html_fragment_is_flagged(self) -> None:
        diagnostics = _lint_source(self._SERVER_HEAD + (
            "storage local immutable okStatus Int32 200\n"
            "call writeCall http.responseText\n"
            "argument writeCall response HttpResponse response\n"
            "argument writeCall status HttpStatusCode okStatus\n"
            "argument writeCall body String a\n"
            "run writeCall\n"
            "bind value frag HtmlFragment writeCall\n"
            "return value 0\n"
        ))
        self.assertIn("SS4302", _codes(diagnostics))


# ==========================================================================
# SS0109  unusedDeclaration.htmlTemplate
# ==========================================================================

class TestUnusedHtmlTemplate(unittest.TestCase):
    def test_unhydrated_template_is_flagged(self) -> None:
        diagnostics = _lint_source(
            "project P\n"
            "module examples.p\n"
            "html template Orphan\n"
            "html body template Orphan\n"
            "    <p>{{msg}}</p>\n"
            "operation main\n"
            "output operation main ExitCode\n"
            "async main no\n"
            "purpose operation main \"x\"\n"
            "return value 0\n"
        )
        self.assertIn("SS0109", _codes(diagnostics))
        diag = _diagnostics_with_code(diagnostics, "SS0109")[0]
        self.assertEqual(diag.subjectName, "Orphan")
        self.assertFalse(diag.blocksCompile)

    def test_hydrated_template_is_clean(self) -> None:
        diagnostics = _lint_source(
            "project P\n"
            "module examples.p\n"
            "html template Page\n"
            "html body template Page\n"
            "    <p>{{msg}}</p>\n"
            "operation main\n"
            "output operation main ExitCode\n"
            "async main no\n"
            "purpose operation main \"x\"\n"
            "storage local immutable m String \"hi\"\n"
            "call renderCall html.hydrate.Page\n"
            "argument renderCall msg String m\n"
            "run renderCall\n"
            "bind value page HtmlDocument renderCall\n"
            "return value 0\n"
        )
        self.assertNotIn("SS0109", _codes(diagnostics))


# ==========================================================================
# SS2516  buildTape.placeholderModulePath
# ==========================================================================

class TestPlaceholderModulePath(unittest.TestCase):
    def test_placeholder_module_path_is_flagged_once_a_dependency_exists(self) -> None:
        # The placeholder only causes the harm this rule names (dependency
        # resolution against a bogus origin) once the project declares a
        # dependency, so the nudge is gated on that.
        diagnostics = _lint_source_at("build.sem",
            "project Demo\nmodulePath Demo github.com/example/demo\n"
            "dependency Demo dep github.com/example/dep v1.0.0\n")
        self.assertIn("SS2516", _codes(diagnostics))
        diag = _diagnostics_with_code(diagnostics, "SS2516")[0]
        self.assertFalse(diag.blocksCompile)

    def test_placeholder_module_path_clean_without_dependencies(self) -> None:
        # A freshly-scaffolded project (placeholder modulePath, no dependencies)
        # must be check-clean so `sem new` -> `sem check` is green out of the box.
        diagnostics = _lint_source_at("build.sem",
            "project Demo\nmodulePath Demo github.com/example/demo\n")
        self.assertNotIn("SS2516", _codes(diagnostics))

    def test_real_module_path_is_clean(self) -> None:
        diagnostics = _lint_source_at("build.sem",
            "project Demo\nmodulePath Demo github.com/acme/demo\n"
            "dependency Demo dep github.com/acme/dep v1.0.0\n")
        self.assertNotIn("SS2516", _codes(diagnostics))


# ==========================================================================
# SS3611  webserver.duplicateRoute
# ==========================================================================

class TestDuplicateRoute(unittest.TestCase):
    _HEAD = (
        "project P\n"
        "target webServer\n"
        "module examples.p\n"
        "webServer s\n"
        "serverHost s \"127.0.0.1\"\n"
        "serverPort s 8080\n"
    )

    def test_duplicate_method_path_is_flagged(self) -> None:
        diagnostics = _lint_source(self._HEAD + (
            "route s GET \"/health\" h1\n"
            "route s GET \"/health\" h2\n"
        ))
        self.assertIn("SS3611", _codes(diagnostics))
        diag = _diagnostics_with_code(diagnostics, "SS3611")[0]
        self.assertTrue(diag.blocksCompile)

    def test_distinct_method_is_clean(self) -> None:
        diagnostics = _lint_source(self._HEAD + (
            "route s GET \"/health\" h1\n"
            "route s POST \"/health\" h2\n"
        ))
        self.assertNotIn("SS3611", _codes(diagnostics))


# ==========================================================================
# SS3640  effectIntegrity.underDeclaredEffect
# ==========================================================================

class TestEffectUnderDeclaration(unittest.TestCase):
    _BODY = (
        "project P\n"
        "module examples.p\n"
        "operation main\n"
        "output operation main ExitCode\n"
        "{EFFECTS}"
        "async main no\n"
        "purpose operation main \"x\"\n"
        "storage local immutable t String \"hi\"\n"
        "call wCall console.writeLine\n"
        "argument wCall text String t\n"
        "run wCall\n"
        "ignore void source wCall\n"
        "return value 0\n"
    )

    def test_console_write_without_effect_is_flagged(self) -> None:
        diagnostics = _lint_source(self._BODY.replace("{EFFECTS}", ""))
        self.assertIn("SS3640", _codes(diagnostics))
        diag = _diagnostics_with_code(diagnostics, "SS3640")[0]
        self.assertEqual(diag.subjectName, "main")
        self.assertFalse(diag.blocksCompile)

    def test_console_write_with_effect_is_clean(self) -> None:
        diagnostics = _lint_source(
            self._BODY.replace("{EFFECTS}", "effect main write console.stdout\n"))
        self.assertNotIn("SS3640", _codes(diagnostics))


if __name__ == "__main__":
    unittest.main()
