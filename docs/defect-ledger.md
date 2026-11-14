# SemanticScript defect-class coverage ledger (X-101)

| Defect class | Asset | SemanticScript defense | Status | Owning todo |
| --- | --- | --- | --- | --- |
| SQL/HTML/path/URL injection | trust | SS3071 | ✅ | X-070/X-071 |
| Untrusted value at a trust-sensitive sink | trust | SS3070 | ✅ | X-070 |
| Secret disclosure (logs/transcripts/source) | confidentiality | SS3072 | ✅ | X-072 |
| Timing side-channel on secret compare | confidentiality | SS3074 | ✅ | X-074 |
| Weak/predictable crypto randomness + nonce reuse | confidentiality | SS3073 | ✅ | X-073 |
| SSRF (server-side request forgery) | authority | SS3075 | ✅ | X-075 |
| Path traversal / absolute-escape | authority | SS3076 | ✅ | X-076 |
| Deserialization DoS / type confusion | availability | SS3077 | ✅ | X-077 |
| Resource-exhaustion DoS (slow peer) | availability | SS3078 | ✅ | X-078 |
| Information disclosure via error detail | confidentiality | SS3079 | ✅ | X-079 |
| Insecure-by-default web surface | authority | SS3080 | ✅ | X-080 |
| Supply-chain effect escalation | supply-chain | SS2805 | ✅ | X-081 |
| Malformed-UTF-8 corruption at input boundary | trust | SS3096 | ✅ | X-096 |
| Float used for money/exact value | correctness | SS3093 | ✅ | X-093 |
| Wall-clock arithmetic / elapsed-time bug | correctness | SS3095 | ✅ | X-095 |
| Use-after-free / use-after-move / view escape | memory | SS1564 | ✅ | WS1-111/113 |
| Per-record authorization / session / business logic | authority | application-domain authZ; the stdlib seam is capabilities + the trust types, but the policy is app code | — | n/a (out-of-language) |
| Off-by-one / logic bugs | correctness | inherent app-logic class; mitigated by tests/goldens, not a language invariant | — | n/a (out-of-language) |
| Leak / double-free of plain values (no GC) | memory | value-class move + free-at-last-use; ownership rules drafted, codegen pending | 🟡 | WS1-110 |
| Wrong-region / arena allocation safety | memory | region entity + allocator-as-capability; allocation runtime pending | 🟡 | WS1-112 |
| Buffer/slice out-of-bounds (no OOB/UB) | memory | bounds-checked Buffer/Slice with view lifetimes; buffer runtime pending | 🟡 | WS1-115 |
| Owned-resource leak (file/db/handle) | reliability | SS1503 | ✅ | WS1-114 |
| Divergence / infinite loop | correctness | SS0950 | ✅ | X-100 |
| Source-observable nondeterminism | correctness | clock/random-as-capability + capturedOutputReplay done; collection ordering pends the collections runtime | 🟡 | X-094 |
| Unchecked pre/postconditions | correctness | invariant/guarantee are metadata; statically-discharged/trapping requires/ensures pending | 🟡 | X-092 |
| Protocol/typestate misuse | correctness | SS1564 | 🟡 | X-091 |
| Error-context loss on propagate | reliability | onFailure propagate exists; causedBy provenance chaining pending | 🟡 | X-099 |
| Data race / TOCTOU outside guards | correctness | single-thread backend is race-free; the concurrent backend gates X-082/X-090; race-to-trust outside guards is app discipline + review | — | n/a (out-of-language) |
