"""Golden-assertion tests for semlint.

Each test writes a small .sscript fixture to a temp file, runs the linter, and
asserts on the structured diagnostic codes + kinds produced. Following the
project rule: never promote a checker without a test that would fail under
no-op lowering.

Run from repo root: `python -m unittest SemanticScript/linter/test_semlint.py -v`
"""

from __future__ import annotations

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
        # 213-occurrence false-positive storm across stdlib_sem.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label startMain
""")
        self.assertNotIn("SS0102", _codes(diagnostics))


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
# SS0105  unusedDeclaration.mutableStorage
# ==========================================================================

class TestUnusedMutableStorage(unittest.TestCase):
    def test_never_set_mutable_module_storage_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision I64 zeroCount
""")
        self.assertIn("SS0105", _codes(diagnostics))

    def test_immutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable attemptLimit I64 fiveAttemptCount
""")
        self.assertNotIn("SS0105", _codes(diagnostics))

    def test_set_mutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision I64 zeroCount
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
storage module mutable accountLookupRevision I64 zeroCount
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
# SYNTAX.md which scopes capability coverage as a linter rule)
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
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
authority main console.stdout write
""")
        self.assertNotIn("SS3104", _codes(diagnostics))


# ==========================================================================
# SS3105  capabilityCoverage.unprotectedSharedState
# ==========================================================================

class TestSharedStateProtection(unittest.TestCase):
    def test_unprotected_write_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount I64 zeroCount
operation main
output main Void
purpose main "smoke"
invariant main "increments on lookup failure"
set sharedState lookupFailureCount nextLookupFailureCount
""")
        self.assertIn("SS3105", _codes(diagnostics))

    def test_protected_write_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount I64 zeroCount
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
sharedState cluster mutable lookupFailureCount I64 zeroCount
""")
        self.assertIn("SS3108", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3108")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "lookupFailureCount")
        self.assertEqual(matchingDiagnostic.gapEdge, "processScopeOnly")

    def test_process_scope_is_currently_supported(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount I64 zeroCount
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
        diagnostics = _lint_source("""buildProject todoTui
project TodoTuiApp
modulePath todoTui github.com/monstercameron/SemanticScript/app/todo
languageVersion todoTui "1.0"
sourceRoot todoTui "."
registerModule todoTui app.todo "."
mainFile todoTui "fixture.sscript"
mainOperation todoTui main
testPattern todoTui "*.test.sem"
dependencySource todoTui semstd github.com/monstercameron/SemanticScript/std
dependencyIntegrity todoTui semstd "sha256-example"
buildProfile todoTui dev
runtimeChecks todoTui panic
persistLlvmIr todoTui no
nativeOutput todoTui "todo.exe"
targetRuntime todoTui nativeExe
comptimeOperation todoTui configureTodoTuiBuild
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


# ==========================================================================
# SS250x  project module registry contract
# ==========================================================================

class TestProjectModuleRegistry(unittest.TestCase):
    def test_build_tape_export_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "main.sem").write_text("module app.todo\n", encoding="utf-8")
            buildPath = root / "build.sem"
            buildPath.write_text("""buildProject todoTui
registerModule todoTui app.todo "."
mainFile todoTui "main.sem"
exportOperation app.todo main
""", encoding="utf-8")
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2502", _codes(diagnostics))

    def test_registered_module_exports_are_local_and_clean(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject todoTui
registerModule todoTui app.todo "."
mainFile todoTui "main.sem"
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

    def test_unregistered_module_declaration_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject todoTui
registerModule todoTui app.todo "."
mainFile todoTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.other
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2503", _codes(diagnostics))

    def test_unregistered_module_import_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            root = Path(tempDir)
            (root / "build.sem").write_text("""buildProject todoTui
registerModule todoTui app.todo "."
mainFile todoTui "main.sem"
""", encoding="utf-8")
            modulePath = root / "main.sem"
            modulePath.write_text("""module app.todo
importModule app.missing
""", encoding="utf-8")
            diagnostics = semlint.lint_path(modulePath)
        self.assertIn("SS2504", _codes(diagnostics))

    def test_missing_registered_module_source_is_flagged(self) -> None:
        with TemporaryDirectory() as tempDir:
            buildPath = Path(tempDir) / "build.sem"
            buildPath.write_text("""buildProject todoTui
registerModule todoTui app.todo "missing"
mainFile todoTui "main.sem"
""", encoding="utf-8")
            diagnostics = semlint.lint_path(buildPath)
        self.assertIn("SS2501", _codes(diagnostics))


# ==========================================================================
# SS0106  unusedDeclaration.bindSlot
# ==========================================================================

class TestUnusedBindSlots(unittest.TestCase):
    def test_unread_bind_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call computeCall math.addI64
arg computeCall left someLeftValue
arg computeCall right someRightValue
run computeCall
bind unreadResult I64 computeCall
""")
        self.assertIn("SS0106", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0106")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unreadResult")

    def test_read_bind_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main I64
purpose main "smoke"
call computeCall math.addI64
arg computeCall left someLeftValue
arg computeCall right someRightValue
run computeCall
bind computedSum I64 computeCall
returnValue computedSum
""")
        self.assertNotIn("SS0106", _codes(diagnostics))


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
        self.assertIn("bindError", matchingDiagnostic.gapEdge)
        self.assertIn("branchIfError", matchingDiagnostic.gapEdge)

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

    def test_c_status_call_with_ignore_value_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
effect main write console.stdout
call writeCharacterCall c.putchar
arg writeCharacterCall character escapeByte
run writeCharacterCall
ignoreValue writeCharacterCall CSignedInt32
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
call computeCall math.addI64
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
const tmp I64 zeroCount
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
const dangling I64 zeroCount
""")
        self.assertIn("SS0107", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0107")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "dangling")

    def test_referenced_const_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main I64
purpose main "smoke"
const exitOkCode I64 zeroCount
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
input main unusedParameter I64
output main Void
purpose main "smoke"
""")
        self.assertIn("SS0108", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS0108")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unusedParameter")

    def test_referenced_input_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main usedParameter I64
output main I64
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
storage local mutable counter I64 zeroValue
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
storage local mutable counter I64 zeroValue
operation main
output main I64
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


class TestBindThenIgnore(unittest.TestCase):
    def test_bind_then_ignore_value_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call sideEffectCall math.addI64
run sideEffectCall
bind redundantResult I64 sideEffectCall
ignoreValue redundantResult I64
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
bindOk allocatedBuffer COpaqueMemoryAddress allocationCall
call freeAllocationCall c.free
arg freeAllocationCall ptr allocatedBuffer
run freeAllocationCall
ignoreValue freeAllocationCall Void
""")
        self.assertNotIn("SS3303", _codes(diagnostics))

    def test_allocator_returning_pointer_not_flagged(self) -> None:
        # When the op's output type IS the allocated pointer, ownership
        # transfers to the caller and the lack of free is correct.
        diagnostics = _lint_source("""project Test
operation allocateBuffer
output allocateBuffer COpaqueMemoryAddress
purpose allocateBuffer "allocator"
effect allocateBuffer allocate heap
memoryHeap allocateBuffer yes
memoryAllocationSource allocateBuffer allocationCall
call allocationCall c.malloc
run allocationCall
bind allocatedBuffer COpaqueMemoryAddress allocationCall
returnValue allocatedBuffer
""")
        self.assertNotIn("SS3303", _codes(diagnostics))


class TestStackLimitOverrun(unittest.TestCase):
    def test_tiny_stack_limit_with_many_binds_flagged(self) -> None:
        # Declare a 4-byte limit but bind several I64 values (8 bytes each)
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryStackLimit main 4
const firstValue I64 zeroValue
const secondValue I64 zeroValue
const thirdValue I64 zeroValue
""")
        self.assertIn("SS3304", _codes(diagnostics))

    def test_generous_stack_limit_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryStackLimit main 8192
const firstValue I64 zeroValue
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
arrayType EmptyArray I64
arrayLength EmptyArray 0
""")
        self.assertIn("SS3404", _codes(diagnostics))

    def test_nonzero_length_array_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
arrayType FixedArray I64
arrayLength FixedArray 8
""")
        self.assertNotIn("SS3404", _codes(diagnostics))


class TestInlineCapacityWithoutSpillAllocator(unittest.TestCase):
    def test_capacity_without_spill_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue I64
smallListInlineCapacity TaskQueue 8
""")
        self.assertIn("SS3405", _codes(diagnostics))

    def test_capacity_with_spill_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue I64
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
literal eightByteCount CByteCount
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
operation main
output main Void
purpose main "smoke"
work renderTaskWork
submitWork renderTaskWork backgroundPool
""")
        self.assertIn("SS3506", _codes(diagnostics))

    def test_submit_with_await_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
workerPool backgroundPool
operation main
output main Void
purpose main "smoke"
work renderTaskWork
submitWork renderTaskWork backgroundPool
awaitWork renderTaskWork
""")
        self.assertNotIn("SS3506", _codes(diagnostics))


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
bind openedFileHandle CFileHandle openFileHandleCall
call closeFileHandleCall c.fclose
arg closeFileHandleCall stream openedFileHandle
run closeFileHandleCall
ignoreValue closeFileHandleCall CSignedInt32
""")
        self.assertNotIn("SS3901", _codes(diagnostics))

    def test_handle_returning_op_not_flagged(self) -> None:
        # Op output is CFileHandle — ownership transfers to caller.
        diagnostics = _lint_source("""project Test
operation openConfigurationFile
output openConfigurationFile CFileHandle
purpose openConfigurationFile "opener"
effect openConfigurationFile open file
call openFileHandleCall c.fopen
arg openFileHandleCall path filePath
arg openFileHandleCall mode readMode
run openFileHandleCall
bind openedFileHandle CFileHandle openFileHandleCall
returnValue openedFileHandle
""")
        self.assertNotIn("SS3901", _codes(diagnostics))


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
sharedState process mutable lookupFailureCount I64 zeroCount
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
sharedState process mutable lookupFailureCount I64 zeroCount
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
type UuidV7 CSignedInt64
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
jsonCodecInput taskJsonCodec CNullTerminatedByteString
jsonCodecOutput taskJsonCodec Task
jsonCodecDecodeTarget taskJsonCodec json.decode.Task
jsonCodecEncodeTarget taskJsonCodec json.encode.Task
operation main
output main Void
purpose main "smoke"
call decodeTaskCall json.decode.Task
arg decodeTaskCall value rawTaskJson
run decodeTaskCall
bind decodedTask I64 decodeTaskCall
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
const rawNumber CNullTerminatedByteString "42"
call decodeIntegerCall json.decode.I64
arg decodeIntegerCall value rawNumber
run decodeIntegerCall
bind decodedInteger I64 decodeIntegerCall
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
bind encodedTaskBytes I64 encodeTaskCall
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
bindOk updatedTaskList I64 appendTaskCall
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
bindOk taskValue I64 getTaskCall
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
bindOk updatedTaskList I64 appendTaskCall
""")
        self.assertIn("SS3804", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "SS3804")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "TaskList.append")


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
output main Void
purpose main "smoke"
call writeCall console.writeLine
arg writeCall console consoleHandle
""")
        self.assertNotIn("SS0002", _codes(diagnostics))


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
const leftValue I64 1
call addCall math.addI64
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
        # legitimately carry purpose/invariant/warning per SYNTAX.md.
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
storage module immutable retryAttemptLimit I64 5
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
enum SaveStatus repr CSignedInt32
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
input consoleWriteCapability badInput I64
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
type AccountId CSignedInt64
""")
        self.assertIn("SS4201", _codes(diagnostics))


# ==========================================================================
# SS4301  typeIntegrity.argumentTypeMismatch
# ==========================================================================

class TestArgumentTypeMismatch(unittest.TestCase):
    def test_passing_bool_where_string_expected_flagged(self) -> None:
        # Bool is in the integer family (sext to I64 on the wire);
        # CNullTerminatedByteString is in the pointer family. Distinct
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

    def test_passing_i64_where_i64_expected_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue I64 zeroValue
const rightValue I64 zeroValue
call addCall math.addI64
arg addCall left leftValue
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_csignedint64_canonical_equivalent_to_i64(self) -> None:
        # CSignedInt64 and I64 are width-equivalent; passing one where the
        # other is expected should NOT be flagged after canonical
        # resolution.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue CSignedInt64 zeroValue
const rightValue I64 zeroValue
call addCall math.addI64
arg addCall left leftValue
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_type_alias_resolves_through_to_base(self) -> None:
        # `type AccountId UuidV7; type UuidV7 CSignedInt64` — passing an
        # AccountId where I64 is expected should resolve via aliases.
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type UuidV7 CSignedInt64
operation main
output main Void
purpose main "smoke"
const lookupAccountId AccountId zeroValue
const rightValue I64 zeroValue
call addCall math.addI64
arg addCall left lookupAccountId
arg addCall right rightValue
run addCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_enum_case_uses_repr_width_for_builtin_signature(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation main
output main Void
purpose main "smoke"
call statusCheckCall math.equalCSignedInt32
arg statusCheckCall left SaveSucceeded
arg statusCheckCall right SaveFailed
run statusCheckCall
""")
        self.assertNotIn("SS4301", _codes(diagnostics))

    def test_enum_case_to_wrong_width_builtin_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
enumCase SaveStatus SaveSucceeded 0
const zeroValue I64 0
operation main
output main Void
purpose main "smoke"
call statusCheckCall math.equalI64
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
input processCount inputCount I64
output processCount Void
purpose processCount "smoke"
operation main
output main Void
purpose main "smoke"
const someText CNullTerminatedByteString textValue
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
    def test_i64_compare_with_i32_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus CSignedInt32 1
const rightStatus CSignedInt32 1
call statusCheckCall math.equalI64
arg statusCheckCall left leftStatus
arg statusCheckCall right rightStatus
run statusCheckCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.severity, semlint.Severity.ERROR)
        self.assertTrue(diagnostic.blocksCompile)
        self.assertEqual(diagnostic.fixCandidates[0].shape, "call statusCheckCall math.equalCSignedInt32")

    def test_width_specific_i32_compare_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus CSignedInt32 1
const rightStatus CSignedInt32 1
call statusCheckCall math.equalCSignedInt32
arg statusCheckCall left leftStatus
arg statusCheckCall right rightStatus
run statusCheckCall
""")
        self.assertNotIn("SS4303", _codes(diagnostics))

    def test_i64_compare_with_i64_values_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue I64 1
const rightValue I64 1
call statusCheckCall math.equalI64
arg statusCheckCall left leftValue
arg statusCheckCall right rightValue
run statusCheckCall
""")
        self.assertNotIn("SS4303", _codes(diagnostics))

    def test_i64_arithmetic_with_i32_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftStatus CSignedInt32 1
const rightStatus CSignedInt32 1
call addCall math.addI64
arg addCall left leftStatus
arg addCall right rightStatus
run addCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.fixCandidates[0].name, "makeConversionExplicit")

    def test_i32_compare_with_i64_values_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const leftValue I64 1
const rightValue I64 1
call statusCheckCall math.equalCSignedInt32
arg statusCheckCall left leftValue
arg statusCheckCall right rightValue
run statusCheckCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")
        self.assertEqual(diagnostic.fixCandidates[0].shape, "call statusCheckCall math.equalI64")

    def test_explicit_conversion_target_with_wrong_input_width_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const sourceValue I64 1
call widenCall math.signExtendCSignedInt32ToCSignedInt64
arg widenCall inputValue sourceValue
run widenCall
""")
        self.assertIn("SS4303", _codes(diagnostics))
        diagnostic = _diagnostics_with_code(diagnostics, "SS4303")[0]
        self.assertEqual(diagnostic.kind, "typeIntegrity.mathOperandWidthDrift")


# ==========================================================================
# SS4302  typeIntegrity.enumReturnUsesRawValue
# ==========================================================================

class TestEnumReturnUsesCase(unittest.TestCase):
    def test_enum_output_returning_raw_literal_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
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
        self.assertEqual(diagnostic.fixCandidates[0].shape, "returnValue SaveFailed")

    def test_enum_output_returning_case_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
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
enum SaveStatus repr CSignedInt32
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
storage local immutable nulByte CSignedInt32 0
operation beta
output beta Void
purpose beta "smoke"
storage local immutable nulByte CSignedInt32 0
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable nulByte CSignedInt32 0
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
            fixCandidate.shape.startswith("storage module immutable nulByte CSignedInt32 0")
            for fixCandidate in diagnostic.fixCandidates
        ))

    def test_two_operations_below_threshold_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable nulByte CSignedInt32 0
operation beta
output beta Void
purpose beta "smoke"
storage local immutable nulByte CSignedInt32 0
""")
        self.assertNotIn("SS4401", _codes(diagnostics))

    def test_distinct_init_values_are_not_duplicates(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable offset CSignedInt64 10
operation beta
output beta Void
purpose beta "smoke"
storage local immutable offset CSignedInt64 19
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable offset CSignedInt64 30
""")
        self.assertNotIn("SS4401", _codes(diagnostics))


# ==========================================================================
# SS4402  styleDiscipline.magicAsciiByteLiteral
# ==========================================================================

class TestMagicAsciiByteLiteral(unittest.TestCase):
    def test_printable_ascii_without_rationale_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parser
output parser Void
purpose parser "smoke"
storage local immutable quoteByte CSignedInt32 34
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
storage local immutable quoteByte CSignedInt32 34
""")
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_control_character_codepoint_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation terminal
output terminal Void
purpose terminal "smoke"
storage local immutable escapeByte CSignedInt32 27
""")
        # 27 is below the printable-ASCII range (32..126).
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_non_csignedint32_type_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation counter
output counter Void
purpose counter "smoke"
storage local immutable offsetValue CSignedInt64 65
""")
        self.assertNotIn("SS4402", _codes(diagnostics))

    def test_duplicate_name_suppresses_ascii_diagnostic(self) -> None:
        diagnostics = _lint_source("""project Test
operation alpha
output alpha Void
purpose alpha "smoke"
storage local immutable quoteByte CSignedInt32 34
operation beta
output beta Void
purpose beta "smoke"
storage local immutable quoteByte CSignedInt32 34
operation gamma
output gamma Void
purpose gamma "smoke"
storage local immutable quoteByte CSignedInt32 34
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
storage local immutable zeroIndex CSignedInt64 0
storage local immutable startOffset CSignedInt64 7
storage local mutable cursor CSignedInt64 zeroIndex
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
storage local immutable zeroIndex CSignedInt64 0
storage local mutable cursor CSignedInt64 zeroIndex
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
storage local immutable zeroIndex CSignedInt64 0
storage local mutable cursor CSignedInt64 zeroIndex
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
storage local immutable activeValueOffset CSignedInt64 10
storage local immutable doneValueOffset CSignedInt64 19
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
storage local immutable activeValueOffset CSignedInt64 10
storage local immutable doneValueOffset CSignedInt64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_rationale_mentioning_format_keyword_suppresses_diagnostic(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
# rationale: positions in the fixed JSON format string written upstream.
storage local immutable activeValueOffset CSignedInt64 10
storage local immutable doneValueOffset CSignedInt64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_single_offset_row_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
storage local immutable activeValueOffset CSignedInt64 10
""")
        self.assertNotIn("SS4404", _codes(diagnostics))

    def test_non_offset_named_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation parseLine
output parseLine Void
purpose parseLine "smoke"
storage local immutable activeValue CSignedInt64 10
storage local immutable doneValue CSignedInt64 19
""")
        self.assertNotIn("SS4404", _codes(diagnostics))


# ==========================================================================
# SS4405  styleDiscipline.enumReprComparison
# ==========================================================================

class TestEnumReprComparison(unittest.TestCase):
    def test_int32_repr_enum_compared_with_raw_math_target_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1
operation checkSave
input checkSave status SaveStatus
output checkSave Bool
purpose checkSave "smoke"
call sameCall math.equalCSignedInt32
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

    def test_int64_repr_enum_compared_with_math_equal_i64_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum Mode repr CSignedInt64
enumCase Mode ListMode 0
enumCase Mode EditMode 1
operation checkMode
input checkMode mode Mode
output checkMode Bool
purpose checkMode "smoke"
call modeCall math.equalI64
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
enum SaveStatus repr CSignedInt32
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
input check left CSignedInt32
output check Bool
purpose check "smoke"
call cmpCall math.equalCSignedInt32
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
enum SaveStatus repr CSignedInt32
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
ignoreValue write CSignedInt32
""")
        self.assertNotIn("SS4406", _codes(diagnostics))

    def test_bound_enum_return_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
enum SaveStatus repr CSignedInt32
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
storage local immutable lineBufferBytes CByteCount 384
storage local immutable lineBufferCapacity CSignedInt32 256
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
storage local immutable lineBufferBytes CByteCount 384
storage local immutable lineBufferCapacity CSignedInt32 384
""")
        self.assertNotIn("SS4407", _codes(diagnostics))

    def test_diverging_values_without_anchor_phrase_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main console Console
output main Void
purpose main "smoke"
invariant main "lineBufferBytes is the malloc size; lineBufferCapacity is the c.fgets count."
storage local immutable lineBufferBytes CByteCount 384
storage local immutable lineBufferCapacity CSignedInt32 256
""")
        # Without the `MUST stay equal` anchor the rule does not fire — the
        # values are allowed to differ when the invariant doesn't claim
        # they're paired.
        self.assertNotIn("SS4407", _codes(diagnostics))

    def test_module_scope_paired_scalars_are_resolved(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable retryLimitBytes CByteCount 1024
storage module immutable retryLimitCapacity CSignedInt32 512
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
output edgeHandler CSignedInt32
effect edgeHandler write http.response
memory edgeHandler arena request
async edgeHandler no
useCapability edgeHandler httpResponseWriter
purpose edgeHandler "smoke handler for whitelist test"
invariant edgeHandler "static response so the test can poll"
label startEdgeHandler
storage local immutable bodyText CNullTerminatedByteString "edge\\n"
storage local immutable okStatus CSignedInt32 200
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
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

    def test_lowercase_method_is_flagged(self) -> None:
        # The whitelist is intentionally case-sensitive: the native dispatcher
        # uppercases on parse, and a lowercase verb in source is a typo, not
        # a request to dispatch a different method.
        diagnostics = _lint_source(self._WHITELIST_ROUTE_TEMPLATE.format(method="get"))
        self.assertIn("SS3601", _codes(diagnostics))

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
output probeMiddleware CSignedInt32
{middlewareEffectLine}
memory probeMiddleware arena request
async probeMiddleware no
useCapability probeMiddleware httpRequestReader
purpose probeMiddleware "demo middleware for SS3602 fixture"
invariant probeMiddleware "synchronous middleware that returns 0 to continue"
label startProbeMiddleware
storage local immutable continueStatus CSignedInt32 0
returnValue continueStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
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
output echoHandler CSignedInt32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token back"
invariant echoHandler "static reply on missing token"
{warningLine}label startEchoHandler
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
storage local immutable badStatus CSignedInt32 400
storage local immutable missingBody CNullTerminatedByteString "missing\\n"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenHeaderValue CNullTerminatedByteString headerReadCall
{guardBlock}call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body tokenHeaderValue
run writeCall
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus

label missingPath
call missingWriteCall http.responseText
arg missingWriteCall response response
arg missingWriteCall status badStatus
arg missingWriteCall body missingBody
run missingWriteCall
bind missingWriteStatus CSignedInt32 missingWriteCall
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
input writeTextResponseWrapper status CSignedInt32
input writeTextResponseWrapper body CNullTerminatedByteString
output writeTextResponseWrapper CSignedInt32
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
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler CSignedInt32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via wrapper"
invariant echoHandler "transitive-detection target"
label startEchoHandler
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenHeaderValue CNullTerminatedByteString headerReadCall
call writeWrapperCall writeTextResponseWrapper
arg writeWrapperCall response response
arg writeWrapperCall status okStatus
arg writeWrapperCall body tokenHeaderValue
run writeWrapperCall
bind writeWrapperStatus CSignedInt32 writeWrapperCall
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
output methodHandler CSignedInt32
effect methodHandler read http.request.method
effect methodHandler write http.response
memory methodHandler arena request
async methodHandler no
useCapability methodHandler httpRequestReader
useCapability methodHandler httpResponseWriter
purpose methodHandler "echo request method"
invariant methodHandler "method is never null for dispatched requests"
label startMethodHandler
storage local immutable okStatus CSignedInt32 200
call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
bind requestMethod CNullTerminatedByteString methodReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body requestMethod
run writeCall
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus
""")
        self.assertNotIn("SS3603", _codes(diagnostics))


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
output probeHandler CSignedInt32
effect probeHandler read http.request.header
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpRequestReader
useCapability probeHandler httpResponseWriter
purpose probeHandler "echo X-Token unguarded as a SS3603 test fixture"
invariant probeHandler "intentionally unguarded for opt-out testing"
{optOutLine}label startProbeHandler
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue CNullTerminatedByteString headerReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body tokenValue
run writeCall
bind writeStatus CSignedInt32 writeCall
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
output echoHandler CSignedInt32
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
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
storage local immutable badStatus CSignedInt32 400
storage local immutable missingBody CNullTerminatedByteString "missing\\n"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue CNullTerminatedByteString headerReadCall
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
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus

label missingPath
call missingWriteCall http.responseText
arg missingWriteCall response response
arg missingWriteCall status badStatus
arg missingWriteCall body missingBody
run missingWriteCall
bind missingWriteStatus CSignedInt32 missingWriteCall
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
    invisible to the lint — callers can pass nullable binds to it
    without tripping SS3603 (which is the correct behavior, since the
    wrapper might be safe-by-construction or have its own guard)."""

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
input writeTextResponseWrapper status CSignedInt32
input writeTextResponseWrapper body CNullTerminatedByteString
output writeTextResponseWrapper CSignedInt32
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
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler CSignedInt32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via wrapper"
invariant echoHandler "transitive-detection target"
label startEchoHandler
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue CNullTerminatedByteString headerReadCall
call writeWrapperCall writeTextResponseWrapper
arg writeWrapperCall response response
arg writeWrapperCall status okStatus
arg writeWrapperCall body tokenValue
run writeWrapperCall
bind writeWrapperStatus CSignedInt32 writeWrapperCall
returnValue writeWrapperStatus
"""

    def test_wrapper_with_declaration_propagates_SS3603_to_caller(self) -> None:
        diagnostics = _lint_source(self._CALLER_PROGRAM.format(
            wrapperForwarderDeclaration="responseBodyForwarder writeTextResponseWrapper body\n"
        ))
        self.assertIn("SS3603", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3603")[0]
        self.assertEqual(matching.subjectName, "tokenValue")

    def test_wrapper_without_declaration_does_not_propagate_SS3603(self) -> None:
        # Without the verb, the wrapper is treated as an opaque user op
        # whose internal contract is invisible to the lint. The caller's
        # pass of a nullable bind is NOT flagged — which is the correct
        # default: the wrapper might enforce non-nullity internally or
        # accept null intentionally; without a declaration, we don't
        # know. The verb is the explicit declaration that closes the gap.
        diagnostics = _lint_source(self._CALLER_PROGRAM.format(
            wrapperForwarderDeclaration=""
        ))
        self.assertNotIn("SS3603", _codes(diagnostics))

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
input pretendsToForward body CNullTerminatedByteString
output pretendsToForward CSignedInt32
effect pretendsToForward write http.response
memory pretendsToForward arena request
async pretendsToForward no
useCapability pretendsToForward httpResponseWriter
purpose pretendsToForward "claims to forward body but actually drops it"
invariant pretendsToForward "for SS3607 fixture"
responseBodyForwarder pretendsToForward body
label startPretendsToForward
storage local immutable okStatus CSignedInt32 0
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
input innerWrapper status CSignedInt32
input innerWrapper body CNullTerminatedByteString
output innerWrapper CSignedInt32
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
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus

operation outerWrapper
input outerWrapper response HttpResponse
input outerWrapper status CSignedInt32
input outerWrapper body CNullTerminatedByteString
output outerWrapper CSignedInt32
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
bind innerStatus CSignedInt32 innerCall
returnValue innerStatus

operation echoHandler
input echoHandler request HttpRequest
input echoHandler response HttpResponse
output echoHandler CSignedInt32
effect echoHandler read http.request.header
effect echoHandler write http.response
memory echoHandler arena request
async echoHandler no
useCapability echoHandler httpRequestReader
useCapability echoHandler httpResponseWriter
purpose echoHandler "echo X-Token via two-layer wrapper"
invariant echoHandler "fixed-point forwarder test"
label startEchoHandler
storage local immutable tokenHeaderName CNullTerminatedByteString "x-token"
storage local immutable okStatus CSignedInt32 200
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name tokenHeaderName
run headerReadCall
bind tokenValue CNullTerminatedByteString headerReadCall
call outerCall outerWrapper
arg outerCall response response
arg outerCall status okStatus
arg outerCall body tokenValue
run outerCall
bind outerStatus CSignedInt32 outerCall
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
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
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
storage local immutable okStatus CSignedInt32 0
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
output methodEchoHandler CSignedInt32
effect methodEchoHandler read http.request.method
effect methodEchoHandler write http.response
memory methodEchoHandler arena request
async methodEchoHandler no
useCapability methodEchoHandler httpRequestReader
useCapability methodEchoHandler httpResponseWriter
purpose methodEchoHandler "smoke test that http.request authorizes http.request.method"
invariant methodEchoHandler "if missingCapabilityUse fires here, the hierarchy walk is broken"
label startMethodEchoHandler
storage local immutable okStatus CSignedInt32 200
call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
bind requestMethod CNullTerminatedByteString methodReadCall
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body requestMethod
run writeCall
bind writeStatus CSignedInt32 writeCall
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
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler for SS3609 fixture"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response {responseInputName}
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
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
output tracingMiddleware CSignedInt32
effect tracingMiddleware write http.response
memory tracingMiddleware arena request
async tracingMiddleware no
useCapability tracingMiddleware httpResponseWriter
purpose tracingMiddleware "non-canonical input names should fire SS3609"
invariant tracingMiddleware "middleware ABI follows route ABI"
label startTracingMiddleware
storage local immutable continueStatus CSignedInt32 0
returnValue continueStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "canonical-name handler so only the middleware trips SS3609"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
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
output requestInspector CSignedInt32
memory requestInspector arena request
async requestInspector no
purpose requestInspector "library helper, NOT a route handler"
invariant requestInspector "called only from other ops, not from a route binding"
label startRequestInspector
storage local immutable inspectStatus CSignedInt32 0
returnValue inspectStatus

operation probeHandler
input probeHandler request HttpRequest
input probeHandler response HttpResponse
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "canonical handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus
""")
        self.assertNotIn("SS3609", _codes(diagnostics))


# ==========================================================================
# Source-of-truth drift guard for native HTTP target sets (P9)
# ==========================================================================

class TestHttpTargetSourceOfTruth(unittest.TestCase):
    """The native HTTP target surface lives in three places: semsc.py's
    dispatch block, semlint.py's classifier constants, and SYNTAX.md's
    umbrella rows. Adding a target in one place without the others
    leaves a silent contract drift — SS3603 misses new readers, SS3601
    misses new writers, and SYNTAX.md becomes a lie.

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
        cls.syntaxMdPath = repoRoot / "SYNTAX.md"

    def _http_targets_in_semsc(self) -> "set[str]":
        """Extract every `http.X` literal target referenced anywhere in
        semsc.py. Catches both single-target `if target == "http.X":`
        lines and multi-target list literals like `("http.X", "http.Y",
        ...)` used for multipart dispatch."""
        import re
        sourceText = self.semscPath.read_text(encoding="utf-8")
        targetPattern = re.compile(r'"(http\.[A-Za-z_][A-Za-z0-9_]*)"')
        return set(targetPattern.findall(sourceText))

    def _http_targets_in_syntax_md(self) -> "set[str]":
        """Extract every `http.X` target referenced in SYNTAX.md. The
        spec wraps targets in backticks (` `http.X` `) so the regex is
        anchored on that."""
        import re
        sourceText = self.syntaxMdPath.read_text(encoding="utf-8")
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
                f"HTTP_RESPONSE_OTHER_WRITERS) and to the SYNTAX.md "
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

    def test_every_dispatch_target_appears_in_syntax_md(self) -> None:
        targetsInSemsc = self._http_targets_in_semsc()
        targetsInSyntaxMd = self._http_targets_in_syntax_md()
        missingFromSyntax = targetsInSemsc - targetsInSyntaxMd
        self.assertFalse(
            missingFromSyntax,
            msg=(
                f"http.* targets dispatched in semsc.py but not "
                f"mentioned in SYNTAX.md: {sorted(missingFromSyntax)}. "
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
    on the typed enum; bare CSignedInt32 erases the named-case
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
output probeHandler CSignedInt32
effect probeHandler write http.response
memory probeHandler arena request
async probeHandler no
useCapability probeHandler httpResponseWriter
purpose probeHandler "smoke handler"
invariant probeHandler "static response"
label startProbeHandler
storage local immutable okStatus CSignedInt32 200
storage local immutable bodyText CNullTerminatedByteString "ok\\n"
call writeCall http.responseText
arg writeCall response response
arg writeCall status okStatus
arg writeCall body bodyText
run writeCall
bind writeStatus CSignedInt32 writeCall
returnValue writeStatus
"""

    def test_middleware_with_csignedint32_output_flagged(self) -> None:
        diagnostics = _lint_source(self._program_with_middleware_output(
            "output probeMiddleware CSignedInt32"
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

    def test_non_middleware_op_returning_csignedint32_not_flagged(self) -> None:
        # An operation that's NOT bound via routeMiddleware can return
        # any type — SS3610 only speaks to the dispatcher-bound subset.
        diagnostics = _lint_source("""project Test
operation helperOp
output helperOp CSignedInt32
purpose helperOp "ordinary helper, not a middleware"
invariant helperOp "no routeMiddleware binding => SS3610 does not apply"
label startHelperOp
storage local immutable okValue CSignedInt32 0
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
        self.assertEqual(enumFact.repr, "CSignedInt32")
        caseNames = [name for name, _value in enumFact.cases]
        self.assertEqual(
            caseNames,
            ["continueMiddlewareControl", "shortCircuitMiddlewareControl"],
        )

    def test_case_consts_are_typed_MiddlewareControl_not_csignedint32(self) -> None:
        # The case-name consts carry the enum type so the result-contract
        # checker can compare them apples-to-apples against `output OP
        # MiddlewareControl`. If these come back as CSignedInt32 the
        # contract enforcement falls back to the loose equivalence
        # check and silently allows raw integers at returnValue sites.
        prog = self._parse_with_semsc("project Trivial\n")
        continueType, continueValue = prog.consts["continueMiddlewareControl"]
        shortCircuitType, shortCircuitValue = prog.consts["shortCircuitMiddlewareControl"]
        self.assertEqual(continueType, "MiddlewareControl")
        self.assertEqual(continueValue, 0)
        self.assertEqual(shortCircuitType, "MiddlewareControl")
        self.assertEqual(shortCircuitValue, 1)


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
storage local immutable legacyZeroSentinel CSignedInt32 0
returnValue legacyZeroSentinel
""")
        self.assertIn("SS3612", _codes(diagnostics))
        matching = _diagnostics_with_code(diagnostics, "SS3612")[0]
        self.assertEqual(matching.subjectName, "legacyVoidOp")
        self.assertEqual(matching.gapEdge, "returnVoid")
        self.assertEqual(matching.fixCandidates[0].name, "replaceReturnValueWithReturnVoid")
        self.assertEqual(matching.fixCandidates[0].shape, "returnVoid")
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

    def test_csignedint32_output_with_return_value_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation typedOp
output typedOp CSignedInt32
purpose typedOp "returns a typed status"
invariant typedOp "returnValue is correct for non-Void output"
label startTypedOp
storage local immutable okStatus CSignedInt32 0
returnValue okStatus
""")
        self.assertNotIn("SS3612", _codes(diagnostics))

    def test_cvoid_alias_also_caught(self) -> None:
        diagnostics = _lint_source("""project Test
operation cvoidOp
output cvoidOp CVoid
purpose cvoidOp "CVoid is the C ABI alias for Void"
invariant cvoidOp "rule should treat both alike"
label startCvoidOp
storage local immutable zeroSentinel CSignedInt32 0
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
warning refOp "the assertion at test_http_api_gauntlet.py:273-279 verifies this"
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
invariant refOp "tracked under SYNTAX.md#routeMiddleware as Impl'd"
label startRefOp
returnVoid
""")
        self.assertNotIn("SS3613", _codes(diagnostics))


if __name__ == "__main__":
    unittest.main()
