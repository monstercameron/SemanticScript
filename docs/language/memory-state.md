# Memory, Storage, and State

SemanticScript makes mutation and memory behavior visible. Use immutable values by
default; declare mutable state only when mutation is part of the program
contract.

## Storage

```semanticscript
storage module immutable zeroCount I64 0
storage module mutable lastRevision I64 zeroCount

operation updateRevision
output updateRevision I64

storage local immutable incrementStep I64 1
storage local mutable currentRevision I64 lastRevision
```

Schema:

```text
storage SCOPE MUTABILITY NAME TYPE [VALUE]
```

Current compiler behavior:

- `storage module immutable` registers a module const.
- `storage module mutable` registers a module const and emits an LLVM global.
- `storage local immutable` registers an operation-local const.
- `storage local mutable` allocates an operation-local mutable slot.

## Mutation

```semanticscript
set local currentRevision nextRevision
set module lastRevision nextRevision ownedBy moduleStateOwner
set sharedState failureCount nextFailureCount protectedBy failureCountGuardToken
```

Schema:

```text
set local NAME VALUE
set module NAME VALUE [ownedBy OWNER]
set sharedState NAME VALUE [protectedBy TOKEN]
```

The `ownedBy` and `protectedBy` tails are accepted as metadata. Current codegen
stores into local slots, module globals, or shared-state globals when the target
is known.

## Shared State

```semanticscript
sharedState process mutable accountLookupFailureCount I64 zeroCount
sharedStateOwner accountLookupFailureCount accountLookupRuntime
sharedStateGuard accountLookupFailureCount accountLookupGuardToken

read sharedState currentFailureCount I64 accountLookupFailureCount protectedBy accountLookupGuardToken
```

Schemas:

```text
sharedState SCOPE MUTABILITY NAME TYPE [INITIAL]
sharedStateOwner NAME OWNER
sharedStateGuard NAME GUARD
read sharedState OUT TYPE BACKING [protectedBy TOKEN]
```

Current lowering models mutable shared state as an LLVM module global. It is
visible across operations in a single process. `sharedState process` is the only
scope with concrete 1.0 lowering. Cross-process, cluster, or distributed shared
state is future runtime work; do not rely on the compiler for inter-process
visibility.

## Guard Tokens

```semanticscript
guardTokenSource accountLookupGuardToken acquireMetricsLockCall
guardTokenOwner accountLookupGuardToken accountLookupRuntime
guardTokenProtects accountLookupGuardToken accountLookupFailureCount
guardTokenRelease accountLookupGuardToken releaseMetricsLock
```

Guard-token lines describe authority around shared resources. They are metadata
for current codegen and active input for linter checks. The 1.0 runtime does
not enforce guard-token ownership or protection at load/store time. `protectedBy`
therefore means "this access claims the named token in the source contract",
not "the generated code validates the token".

`semlint2.py` checks for guard-token sources without releases, shared-state
access without `protectedBy`, and `protectedBy` tokens that do not declare a
matching `guardTokenProtects TOKEN RESOURCE` edge.

## Operation Memory Metadata

```semanticscript
memory appendAndReadTask noHeapAllocation
memoryHeap appendAndReadTask no
memoryArena appendAndReadTask arena.request
memoryAllocationSource appendAndReadTask allocateTaskBufferCall
memoryStackLimit appendAndReadTask 4096
```

These lines declare memory behavior for review and checking. They do not
replace actual allocation checks. `semlint2.py` can flag contradictions such as
declaring no heap while allocating, missing allocation source metadata, and
stack-limit overruns based on primitive size estimates.

## Pointer Primitives

```semanticscript
call loadByteCall pointer.loadByte
arg loadByteCall buffer sourceBuffer
arg loadByteCall offset currentOffset
run loadByteCall
bind loadedByte CSignedByte loadByteCall

call storeByteCall pointer.storeByte
arg storeByteCall buffer destinationBuffer
arg storeByteCall offset currentOffset
arg storeByteCall value loadedByte
run storeByteCall
ignoreValue storeByteCall Void
```

Supported pointer targets:

| Target | Behavior |
|---|---|
| `pointer.loadByte` | `getelementptr` plus `load i8` |
| `pointer.storeByte` | `getelementptr` plus `store i8` |
| `pointer.offset` | pointer plus byte offset |
| `pointer.difference` | byte distance between two pointers |
| `pointer.isNull` | returns `1` for null, `0` otherwise |

Pointer operations expose memory effects to the linter. Do not hide raw pointer
work behind vague helper names.
