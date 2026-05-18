"""Golden-assertion tests for aslint2.

Each test writes a small .as fixture to a temp file, runs the linter, and
asserts on the structured diagnostic codes + kinds produced. Following the
project rule: never promote a checker without a test that would fail under
no-op lowering.

Run from repo root: `python -m unittest AgentScript/linter/test_aslint2.py -v`
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

import aslint2  # noqa: E402


def _lint_source(sourceText: str) -> List[aslint2.Diagnostic]:
    with TemporaryDirectory() as tempDir:
        fixturePath = Path(tempDir) / "fixture.as"
        fixturePath.write_text(sourceText, encoding="utf-8")
        return aslint2.lint_path(fixturePath)


def _codes(diagnostics: Sequence[aslint2.Diagnostic]) -> List[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def _diagnostics_with_code(
    diagnostics: Sequence[aslint2.Diagnostic],
    code: str,
) -> List[aslint2.Diagnostic]:
    return [diagnostic for diagnostic in diagnostics if diagnostic.code == code]


# ==========================================================================
# AS0101  unusedDeclaration.call
# ==========================================================================

class TestUnusedCalls(unittest.TestCase):
    def test_unused_call_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call unusedCallSite console.writeLine
""")
        self.assertIn("AS0101", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0101")[0]
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
        self.assertNotIn("AS0101", _codes(diagnostics))


# ==========================================================================
# AS0102  unusedDeclaration.label   (entry-anchor convention suppressed)
# ==========================================================================

class TestUnusedLabels(unittest.TestCase):
    def test_orphan_label_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label notAnEntryAnchor
""")
        self.assertIn("AS0102", _codes(diagnostics))

    def test_entry_anchor_pattern_is_suppressed(self) -> None:
        # The stdlib convention `label start<OperationName>` at the top of a
        # body is a readability anchor; treating it as unused causes a
        # 213-occurrence false-positive storm across stdlib_as.
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
label startMain
""")
        self.assertNotIn("AS0102", _codes(diagnostics))


# ==========================================================================
# AS0103  unusedDeclaration.capability
# ==========================================================================

class TestUnusedCapabilities(unittest.TestCase):
    def test_dangling_capability_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
""")
        self.assertIn("AS0103", _codes(diagnostics))

    def test_used_capability_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
operation main
output main Void
purpose main "smoke"
useCapability main consoleCap
""")
        self.assertNotIn("AS0103", _codes(diagnostics))


# ==========================================================================
# AS0104  unusedDeclaration.errorCase
# ==========================================================================

class TestUnusedErrorCases(unittest.TestCase):
    def test_unused_variant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
error MainError
errorCase MainError NeverRaisedVariant
""")
        self.assertIn("AS0104", _codes(diagnostics))

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
        self.assertNotIn("AS0104", _codes(diagnostics))


# ==========================================================================
# AS0105  unusedDeclaration.mutableStorage
# ==========================================================================

class TestUnusedMutableStorage(unittest.TestCase):
    def test_never_set_mutable_module_storage_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision I64 zeroCount
""")
        self.assertIn("AS0105", _codes(diagnostics))

    def test_immutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module immutable attemptLimit I64 fiveAttemptCount
""")
        self.assertNotIn("AS0105", _codes(diagnostics))

    def test_set_mutable_storage_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision I64 zeroCount
operation main
output main Void
purpose main "smoke"
set module accountLookupRevision nextAccountLookupRevision
""")
        self.assertNotIn("AS0105", _codes(diagnostics))


# ==========================================================================
# AS1201  partiallyDeclared.retryPolicy
# ==========================================================================

class TestPartialRetryPolicy(unittest.TestCase):
    def test_policy_missing_max_attempts_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
retryPolicy networkRetryPolicy
""")
        self.assertIn("AS1201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS1201")[0]
        self.assertIn("retryMaxAttempts", matchingDiagnostic.gapEdge)

    def test_complete_policy_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
retryPolicy networkRetryPolicy
retryMaxAttempts networkRetryPolicy 5
retryInitialDelay networkRetryPolicy 100ms
retryMaximumDelay networkRetryPolicy 5s
retryJitter networkRetryPolicy yes
""")
        self.assertNotIn("AS1201", _codes(diagnostics))


# ==========================================================================
# AS1202  partiallyDeclared.trustBoundary
# ==========================================================================

class TestPartialTrustBoundary(unittest.TestCase):
    def test_missing_triad_member_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
trustBoundary AccountToken
trustBoundaryInput AccountToken RawAccountToken
""")
        self.assertIn("AS1202", _codes(diagnostics))

    def test_complete_triad_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
trustBoundary AccountToken
trustBoundaryInput AccountToken RawAccountToken
trustBoundaryOutput AccountToken TrustedAccountToken
trustBoundaryValidator AccountToken validateAccountTokenStructure
""")
        self.assertNotIn("AS1202", _codes(diagnostics))


# ==========================================================================
# AS1203  partiallyDeclared.externalLiteral
# ==========================================================================

class TestLiteralWithoutDigest(unittest.TestCase):
    def test_external_source_without_digest_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
literal embeddedConfig String
literalSource embeddedConfig "config.json"
""")
        self.assertIn("AS1203", _codes(diagnostics))

    def test_external_source_with_digest_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
literal embeddedConfig String
literalSource embeddedConfig "config.json"
literalDigest embeddedConfig sha256 abc123
""")
        self.assertNotIn("AS1203", _codes(diagnostics))


# ==========================================================================
# AS3101 / AS3102  operationMetadataGap.{purpose,invariant}
# ==========================================================================

class TestOperationMetadataGaps(unittest.TestCase):
    def test_missing_purpose_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
call writeLineCall console.writeLine
run writeLineCall
""")
        self.assertIn("AS3101", _codes(diagnostics))

    def test_state_touching_op_without_invariant_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
storage module mutable accountLookupRevision I64 zeroCount
operation main
output main Void
purpose main "smoke"
set module accountLookupRevision nextAccountLookupRevision
""")
        self.assertIn("AS3102", _codes(diagnostics))

    def test_purpose_present_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
run writeLineCall
""")
        self.assertNotIn("AS3101", _codes(diagnostics))


# ==========================================================================
# AS3104  capabilityCoverage.missing  (T3, NOT compile-blocking — matches
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
        self.assertIn("AS3104", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3104")[0]
        self.assertFalse(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, aslint2.Tier.T3_REFINEMENT)

    def test_use_capability_satisfies_check(self) -> None:
        diagnostics = _lint_source("""project Test
capability consoleCap console.stdout write
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
useCapability main consoleCap
""")
        self.assertNotIn("AS3104", _codes(diagnostics))

    def test_inline_authority_satisfies_check(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
effect main write console.stdout
purpose main "smoke"
authority main console.stdout write
""")
        self.assertNotIn("AS3104", _codes(diagnostics))


# ==========================================================================
# AS3105  capabilityCoverage.unprotectedSharedState
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
        self.assertIn("AS3105", _codes(diagnostics))

    def test_protected_write_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
sharedState process mutable lookupFailureCount I64 zeroCount
operation main
output main Void
purpose main "smoke"
invariant main "increments on lookup failure"
set sharedState lookupFailureCount nextLookupFailureCount protectedBy lookupFailureGuard
""")
        self.assertNotIn("AS3105", _codes(diagnostics))


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
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3104")[0]
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
        renderedOutput = aslint2.render_human(diagnostics)
        self.assertIn("subject", renderedOutput)
        self.assertIn("intent", renderedOutput)

    def test_agent_render_is_parseable_json(self) -> None:
        diagnostics = _lint_source(self.SAMPLE_SOURCE)
        import json
        payload = json.loads(aslint2.render_agent(diagnostics))
        self.assertIn("refinementQueue", payload)

    def test_as_record_render_has_draft_header(self) -> None:
        diagnostics = _lint_source(self.SAMPLE_SOURCE)
        renderedOutput = aslint2.render_as_record(diagnostics)
        self.assertIn("DRAFT", renderedOutput)
        self.assertIn("diagnostic", renderedOutput)


# ==========================================================================
# AS0001  grammar.unknownVerb   (T0 — non-overridable error)
# ==========================================================================

class TestUnknownVerbs(unittest.TestCase):
    def test_typo_verb_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operationn main
output main Void
""")
        self.assertIn("AS0001", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0001")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "operationn")
        self.assertTrue(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, aslint2.Tier.T0_PARSE)

    def test_known_verbs_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
""")
        self.assertNotIn("AS0001", _codes(diagnostics))


# ==========================================================================
# AS0106  unusedDeclaration.bindSlot
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
        self.assertIn("AS0106", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0106")[0]
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
        self.assertNotIn("AS0106", _codes(diagnostics))


# ==========================================================================
# AS3106  errorPathCoverage.hiddenFailure
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
        self.assertIn("AS3106", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3106")[0]
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
        self.assertNotIn("AS3106", _codes(diagnostics))


# ==========================================================================
# AS3107  metadataConsistency.siblingDrift
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
        self.assertIn("AS3107", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3107")[0]
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
        self.assertNotIn("AS3107", _codes(diagnostics))


# ==========================================================================
# AS4001 / AS4002 / AS4003 / AS4004  namingDiscipline.*
# ==========================================================================

class TestNamingDiscipline(unittest.TestCase):
    def test_call_without_call_suffix_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call wA console.writeLine
""")
        self.assertIn("AS4001", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS4001")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "wA")
        self.assertEqual(matchingDiagnostic.tier, aslint2.Tier.T4_STYLE)

    def test_call_with_call_suffix_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeLineCall console.writeLine
""")
        self.assertNotIn("AS4001", _codes(diagnostics))

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
        self.assertIn("AS4002", _codes(diagnostics))

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
        self.assertIn("AS4003", _codes(diagnostics))

    def test_blacklist_name_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const tmp I64 zeroCount
""")
        self.assertIn("AS4004", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS4004")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "tmp")


# ==========================================================================
# AS0107  unusedDeclaration.const
# ==========================================================================

class TestUnusedConst(unittest.TestCase):
    def test_unreferenced_const_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
const dangling I64 zeroCount
""")
        self.assertIn("AS0107", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0107")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "dangling")

    def test_referenced_const_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main I64
purpose main "smoke"
const exitOkCode I64 zeroCount
returnValue exitOkCode
""")
        self.assertNotIn("AS0107", _codes(diagnostics))


# ==========================================================================
# AS0108  unusedDeclaration.input
# ==========================================================================

class TestUnusedInput(unittest.TestCase):
    def test_unreferenced_input_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main unusedParameter I64
output main Void
purpose main "smoke"
""")
        self.assertIn("AS0108", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0108")[0]
        self.assertEqual(matchingDiagnostic.subjectName, "unusedParameter")

    def test_referenced_input_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
input main usedParameter I64
output main I64
purpose main "smoke"
returnValue usedParameter
""")
        self.assertNotIn("AS0108", _codes(diagnostics))


# ==========================================================================
# AS3111  effectCoverage.undeclaredBodyEffect
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
        self.assertIn("AS3111", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3111")[0]
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
        self.assertNotIn("AS3111", _codes(diagnostics))

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
        self.assertNotIn("AS3111", _codes(diagnostics))


# ==========================================================================
# AS3112  errorPathCoverage.unknownVariant
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
        self.assertIn("AS3112", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3112")[0]
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
        self.assertNotIn("AS3112", _codes(diagnostics))


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
        self.assertIn("AS3201", _codes(diagnostics))

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
        self.assertNotIn("AS3201", _codes(diagnostics))


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
        self.assertIn("AS3202", _codes(diagnostics))

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
        self.assertNotIn("AS3202", _codes(diagnostics))


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
        self.assertIn("AS3204", _codes(diagnostics))


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
        self.assertIn("AS3301", _codes(diagnostics))

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
        self.assertNotIn("AS3301", _codes(diagnostics))


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
        self.assertIn("AS3302", _codes(diagnostics))

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
        self.assertNotIn("AS3302", _codes(diagnostics))


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
        self.assertIn("AS3303", _codes(diagnostics))

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
        self.assertNotIn("AS3303", _codes(diagnostics))

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
        self.assertNotIn("AS3303", _codes(diagnostics))


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
        self.assertIn("AS3304", _codes(diagnostics))

    def test_generous_stack_limit_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
memoryStackLimit main 8192
const firstValue I64 zeroValue
""")
        self.assertNotIn("AS3304", _codes(diagnostics))


class TestRecordAlignPowerOfTwo(unittest.TestCase):
    def test_non_power_of_two_align_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
record SomeRecord
recordAlign SomeRecord 3
""")
        self.assertIn("AS3401", _codes(diagnostics))

    def test_power_of_two_align_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
record SomeRecord
recordAlign SomeRecord 8
""")
        self.assertNotIn("AS3401", _codes(diagnostics))


class TestArrayLengthZero(unittest.TestCase):
    def test_zero_length_array_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
arrayType EmptyArray I64
arrayLength EmptyArray 0
""")
        self.assertIn("AS3404", _codes(diagnostics))

    def test_nonzero_length_array_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
arrayType FixedArray I64
arrayLength FixedArray 8
""")
        self.assertNotIn("AS3404", _codes(diagnostics))


class TestInlineCapacityWithoutSpillAllocator(unittest.TestCase):
    def test_capacity_without_spill_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue I64
smallListInlineCapacity TaskQueue 8
""")
        self.assertIn("AS3405", _codes(diagnostics))

    def test_capacity_with_spill_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
smallListType TaskQueue I64
smallListInlineCapacity TaskQueue 8
smallListSpillAllocator TaskQueue heapAllocator
""")
        self.assertNotIn("AS3405", _codes(diagnostics))


class TestLiteralEncodingMissing(unittest.TestCase):
    def test_external_literal_without_encoding_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ConfigBlob ConfigBlobBaseType
literal embeddedConfig ConfigBlob
literalSource embeddedConfig "config.bin"
""")
        self.assertIn("AS3406", _codes(diagnostics))

    def test_external_literal_with_encoding_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type ConfigBlob ConfigBlobBaseType
typeLiteralEncoding ConfigBlob utf8
literal embeddedConfig ConfigBlob
literalSource embeddedConfig "config.bin"
""")
        self.assertNotIn("AS3406", _codes(diagnostics))

    def test_primitive_typed_literal_not_flagged(self) -> None:
        # Primitive types are encoded by representation; no
        # typeLiteralEncoding expected.
        diagnostics = _lint_source("""project Test
literal eightByteCount CByteCount
literalSource eightByteCount "size.bin"
""")
        self.assertNotIn("AS3406", _codes(diagnostics))


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
        self.assertIn("AS3501", _codes(diagnostics))

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
        self.assertNotIn("AS3501", _codes(diagnostics))


class TestLockWithoutCleanup(unittest.TestCase):
    def test_lock_without_unlock_or_defer_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
""")
        self.assertIn("AS3503", _codes(diagnostics))

    def test_lock_with_unlock_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
unlock accountUpdateMutex
""")
        self.assertNotIn("AS3503", _codes(diagnostics))

    def test_lock_with_defer_unlock_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
lock accountUpdateMutex
defer releaseAccountUpdateMutex unlock accountUpdateMutex
""")
        self.assertNotIn("AS3503", _codes(diagnostics))


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
        self.assertIn("AS3506", _codes(diagnostics))

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
        self.assertNotIn("AS3506", _codes(diagnostics))


class TestSelectWithoutCases(unittest.TestCase):
    def test_zero_case_select_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
select messagePump
""")
        self.assertIn("AS3507", _codes(diagnostics))

    def test_select_with_cases_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
select messagePump
selectCase messagePump readyToken handleReadyLabel
""")
        self.assertNotIn("AS3507", _codes(diagnostics))


class TestSelectCaseReferencesUnknownSelect(unittest.TestCase):
    def test_case_referencing_undeclared_select_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
selectCase undeclaredMessagePump readyToken handleReadyLabel
""")
        self.assertIn("AS3508", _codes(diagnostics))


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
        self.assertIn("AS3510", _codes(diagnostics))

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
        self.assertNotIn("AS3510", _codes(diagnostics))


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
        self.assertIn("AS3901", _codes(diagnostics))

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
        self.assertNotIn("AS3901", _codes(diagnostics))

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
        self.assertNotIn("AS3901", _codes(diagnostics))


class TestGuardTokenSourceWithoutRelease(unittest.TestCase):
    def test_source_without_release_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
guardTokenSource accountUpdateGuard acquireAccountUpdateCall
guardTokenProtects accountUpdateGuard accountRecordSlot
""")
        self.assertIn("AS3903", _codes(diagnostics))

    def test_source_with_release_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
guardTokenSource accountUpdateGuard acquireAccountUpdateCall
guardTokenProtects accountUpdateGuard accountRecordSlot
guardTokenRelease accountUpdateGuard releaseAccountUpdate
""")
        self.assertNotIn("AS3903", _codes(diagnostics))


class TestCircularTypeAlias(unittest.TestCase):
    def test_two_step_cycle_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type FirstAlias SecondAlias
type SecondAlias FirstAlias
""")
        self.assertIn("AS3701", _codes(diagnostics))

    def test_terminating_alias_chain_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type UuidV7 CSignedInt64
""")
        self.assertNotIn("AS3701", _codes(diagnostics))


class TestJsonCodecIncomplete(unittest.TestCase):
    def test_codec_missing_edges_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
jsonCodec accountRequestCodec
jsonCodecInput accountRequestCodec RequestPayload
""")
        self.assertIn("AS3801", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS3801")[0]
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
        self.assertNotIn("AS3801", _codes(diagnostics))


# ==========================================================================
# Foundational basics — arity / unresolved references / duplicates
# ==========================================================================

class TestArgumentArity(unittest.TestCase):
    def test_operation_without_name_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation
""")
        self.assertIn("AS0002", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS0002")[0]
        self.assertTrue(matchingDiagnostic.blocksCompile)
        self.assertEqual(matchingDiagnostic.tier, aslint2.Tier.T0_PARSE)

    def test_arg_with_only_two_tokens_is_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
arg writeCall console
""")
        self.assertIn("AS0002", _codes(diagnostics))

    def test_correctly_arity_lines_not_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
arg writeCall console consoleHandle
""")
        self.assertNotIn("AS0002", _codes(diagnostics))


class TestUnresolvedReferences(unittest.TestCase):
    def test_arg_referencing_undeclared_call_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
arg neverDeclaredCall consoleArgName consoleHandle
""")
        self.assertIn("AS4101", _codes(diagnostics))

    def test_run_referencing_undeclared_call_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
run mistypedCallName
""")
        self.assertIn("AS4101", _codes(diagnostics))

    def test_branch_referencing_undeclared_label_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
branch undeclaredLabelName
""")
        self.assertIn("AS4102", _codes(diagnostics))

    def test_branchIfError_referencing_undeclared_label_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
call writeCall console.writeLine
run writeCall
branchIfError writeCall labelTypoName
""")
        self.assertIn("AS4102", _codes(diagnostics))

    def test_useCapability_referencing_undeclared_capability_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
operation main
output main Void
purpose main "smoke"
useCapability main typoedCapabilityName
""")
        self.assertIn("AS4103", _codes(diagnostics))

    def test_attachment_referencing_undeclared_operation_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
purpose neverDeclaredOperation "this op doesn't exist"
""")
        self.assertIn("AS4104", _codes(diagnostics))

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
        unresolvedCodes = {"AS4101", "AS4102", "AS4103", "AS4104"}
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
        self.assertIn("AS4201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS4201")[0]
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
        self.assertIn("AS4201", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS4201")[0]
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
            if d.code == "AS4201" and d.subjectKind == "label"
        ]
        self.assertFalse(labelDuplicates)

    def test_duplicate_type_alias_flagged(self) -> None:
        diagnostics = _lint_source("""project Test
type AccountId UuidV7
type AccountId CSignedInt64
""")
        self.assertIn("AS4201", _codes(diagnostics))


# ==========================================================================
# AS4301  typeIntegrity.argumentTypeMismatch
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
        self.assertIn("AS4301", _codes(diagnostics))
        matchingDiagnostic = _diagnostics_with_code(diagnostics, "AS4301")[0]
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
        self.assertNotIn("AS4301", _codes(diagnostics))

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
        self.assertNotIn("AS4301", _codes(diagnostics))

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
        self.assertNotIn("AS4301", _codes(diagnostics))

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
        self.assertIn("AS4301", _codes(diagnostics))

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
        self.assertNotIn("AS4301", _codes(diagnostics))


if __name__ == "__main__":
    unittest.main()
