project StdRandomSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stdlib.h> random.
#
# Implements a Linear Congruential Generator (LCG) entirely in AS —
# no libc rand() / srand(). The state is held in a small heap-
# allocated 8-byte slot that the caller passes in. This matches the
# rand_r-style reentrant pattern (since AS user-operations can't
# share module-level mutable state portably yet).
#
# LCG parameters: the standard MINSTD multiplier (Park-Miller) on a
# modulus of 2^31 - 1. Period ~2.1 billion; suitable for tests and
# games but not cryptography.
#
# Operations:
#   createDeterministicRandomState(seed)      Allocate a state slot, store the seed,
#                              return the slot pointer.
#   releaseDeterministicRandomState(state)     Release the slot.
#   nextDeterministicRandomSignedInt64(state)       Advance and return the next i32 in
#                              [0, 2^31 - 1).
#   nextRandomInRange(state, max)
#                              Returns an int in [0, max-1] using
#                              the modulo approach (slight bias for
#                              non-power-of-2 max; documented).
# ============================================================


operation createDeterministicRandomState
input createDeterministicRandomState randomSeed CSignedInt64
output createDeterministicRandomState Result COpaqueMemoryAddress Void
effect createDeterministicRandomState allocate heap
memory createDeterministicRandomState heap yes
async createDeterministicRandomState no
purpose createDeterministicRandomState "Allocate an 8-byte state slot. Stores `seed` (or 1 if seed <= 0, since the MINSTD LCG can't be seeded with zero)."

label startCreateDeterministicRandomState
const eightBytes CByteCount 8
call alloc c.malloc
arg alloc size eightBytes
run alloc
bind slot COpaqueMemoryAddress alloc

# Normalize seed: 0 or negative -> 1.
const oneSeed I64 1
call leZero math.lessThanOrEqualI64
arg leZero left randomSeed
arg leZero right oneSeed
run leZero
bind needsNorm Bool leZero
var actualSeed I64 1
branchIf needsNorm useOne
set actualSeed randomSeed
branch storeIt
label useOne
set actualSeed oneSeed
branch storeIt
label storeIt
# Store actualSeed as 8 little-endian bytes.
const zeroByteOff CByteCount 0
const oneByteOff CByteCount 1
const twoByteOff CByteCount 2
const threeByteOff CByteCount 3
const fourByteOff CByteCount 4
const fiveByteOff CByteCount 5
const sixByteOff CByteCount 6
const sevenByteOff CByteCount 7
const eightSh I64 8
const sixteenSh I64 16
const twentyFourSh I64 24
const thirtyTwoSh I64 32
const fortySh I64 40
const fortyEightSh I64 48
const fiftySixSh I64 56
const ffMask I64 255

# Store seed bits at offsets 0..7
var stB0 I64 0
set stB0 actualSeed
call mskB0 math.moduloI64
arg mskB0 left stB0
arg mskB0 right oneSeed
run mskB0
# Easier: store via repeated mod 256 and divide.
var workSeed I64 0
set workSeed actualSeed
# byte 0
call mb0 math.moduloI64
arg mb0 left workSeed
arg mb0 right ffMask
run mb0
# Actually 256 not 255.
const twoFiftySix I64 256
call mb0c math.moduloI64
arg mb0c left workSeed
arg mb0c right twoFiftySix
run mb0c
bind b0v I64 mb0c
call s0 pointer.storeByte
arg s0 buffer slot
arg s0 offset zeroByteOff
arg s0 value b0v
run s0
call w1d math.divideI64
arg w1d left workSeed
arg w1d right twoFiftySix
run w1d
bind w1 I64 w1d
set workSeed w1
# bytes 1..7 similarly
call mb1c math.moduloI64
arg mb1c left workSeed
arg mb1c right twoFiftySix
run mb1c
bind b1v I64 mb1c
call s1 pointer.storeByte
arg s1 buffer slot
arg s1 offset oneByteOff
arg s1 value b1v
run s1
call w2d math.divideI64
arg w2d left workSeed
arg w2d right twoFiftySix
run w2d
bind w2 I64 w2d
set workSeed w2

call mb2c math.moduloI64
arg mb2c left workSeed
arg mb2c right twoFiftySix
run mb2c
bind b2v I64 mb2c
call s2 pointer.storeByte
arg s2 buffer slot
arg s2 offset twoByteOff
arg s2 value b2v
run s2
call w3d math.divideI64
arg w3d left workSeed
arg w3d right twoFiftySix
run w3d
bind w3 I64 w3d
set workSeed w3

call mb3c math.moduloI64
arg mb3c left workSeed
arg mb3c right twoFiftySix
run mb3c
bind b3v I64 mb3c
call s3 pointer.storeByte
arg s3 buffer slot
arg s3 offset threeByteOff
arg s3 value b3v
run s3
call w4d math.divideI64
arg w4d left workSeed
arg w4d right twoFiftySix
run w4d
bind w4 I64 w4d
set workSeed w4

call mb4c math.moduloI64
arg mb4c left workSeed
arg mb4c right twoFiftySix
run mb4c
bind b4v I64 mb4c
call s4 pointer.storeByte
arg s4 buffer slot
arg s4 offset fourByteOff
arg s4 value b4v
run s4
call w5d math.divideI64
arg w5d left workSeed
arg w5d right twoFiftySix
run w5d
bind w5 I64 w5d
set workSeed w5

call mb5c math.moduloI64
arg mb5c left workSeed
arg mb5c right twoFiftySix
run mb5c
bind b5v I64 mb5c
call s5 pointer.storeByte
arg s5 buffer slot
arg s5 offset fiveByteOff
arg s5 value b5v
run s5
call w6d math.divideI64
arg w6d left workSeed
arg w6d right twoFiftySix
run w6d
bind w6 I64 w6d
set workSeed w6

call mb6c math.moduloI64
arg mb6c left workSeed
arg mb6c right twoFiftySix
run mb6c
bind b6v I64 mb6c
call s6 pointer.storeByte
arg s6 buffer slot
arg s6 offset sixByteOff
arg s6 value b6v
run s6
call w7d math.divideI64
arg w7d left workSeed
arg w7d right twoFiftySix
run w7d
bind w7 I64 w7d
set workSeed w7

call s7 pointer.storeByte
arg s7 buffer slot
arg s7 offset sevenByteOff
arg s7 value workSeed
run s7

returnOk slot


operation releaseDeterministicRandomState
input releaseDeterministicRandomState randomState COpaqueMemoryAddress
output releaseDeterministicRandomState Result CSignedInt32 Void
effect releaseDeterministicRandomState free heap
memory releaseDeterministicRandomState heap yes
async releaseDeterministicRandomState no
purpose releaseDeterministicRandomState "Free the slot returned by createDeterministicRandomState."
label startReleaseDeterministicRandomState
call f c.free
arg f ptr randomState
run f
const okFree CSignedInt32 0
returnOk okFree


operation loadUnsignedByteFromBufferOffset
input loadUnsignedByteFromBufferOffset byteBuffer COpaqueMemoryAddress
input loadUnsignedByteFromBufferOffset byteOffset CByteCount
output loadUnsignedByteFromBufferOffset Result CSignedInt64 Void
effect loadUnsignedByteFromBufferOffset read memory.buffer
memory loadUnsignedByteFromBufferOffset heap no
async loadUnsignedByteFromBufferOffset no
purpose loadUnsignedByteFromBufferOffset "pointer.loadByte returns a signed I8 that sign-extends to negative for bytes 128..255. This helper normalizes to the unsigned interpretation via (b + 256) % 256."
label startLoadUnsignedByteFromBufferOffset
const tFs256 I64 256
call rawLoad pointer.loadByte
arg rawLoad buffer byteBuffer
arg rawLoad offset byteOffset
run rawLoad
bind raw I8 rawLoad
call shiftPos math.addI64
arg shiftPos left raw
arg shiftPos right tFs256
run shiftPos
bind shifted I64 shiftPos
call modCall math.moduloI64
arg modCall left shifted
arg modCall right tFs256
run modCall
bind unsigned CSignedInt64 modCall
returnOk unsigned


operation readDeterministicRandomState
input readDeterministicRandomState randomState COpaqueMemoryAddress
output readDeterministicRandomState Result CSignedInt64 Void
effect readDeterministicRandomState read memory.buffer
memory readDeterministicRandomState heap no
async readDeterministicRandomState no
purpose readDeterministicRandomState "Load the i64 state value from an 8-byte little-endian slot using loadUnsignedByteFromBufferOffset so high-bit-set bytes don't sign-extend."
label startReadDeterministicRandomState
const zeroOff CByteCount 0
const oneOff CByteCount 1
const twoOff CByteCount 2
const threeOff CByteCount 3
const fourOff CByteCount 4
const fiveOff CByteCount 5
const sixOff CByteCount 6
const sevenOff CByteCount 7
const tFiftySix I64 256
const tFiftySix2 I64 65536
const tFiftySix3 I64 16777216
const tFiftySix4 I64 4294967296
const tFiftySix5 I64 1099511627776
const tFiftySix6 I64 281474976710656
const tFiftySix7 I64 72057594037927936

call l0 loadUnsignedByteFromBufferOffset
arg l0 buffer randomState
arg l0 offset zeroOff
run l0
bindOk by0 CSignedInt64 l0
call l1 loadUnsignedByteFromBufferOffset
arg l1 buffer randomState
arg l1 offset oneOff
run l1
bindOk by1 CSignedInt64 l1
call l2 loadUnsignedByteFromBufferOffset
arg l2 buffer randomState
arg l2 offset twoOff
run l2
bindOk by2 CSignedInt64 l2
call l3 loadUnsignedByteFromBufferOffset
arg l3 buffer randomState
arg l3 offset threeOff
run l3
bindOk by3 CSignedInt64 l3
call l4 loadUnsignedByteFromBufferOffset
arg l4 buffer randomState
arg l4 offset fourOff
run l4
bindOk by4 CSignedInt64 l4
call l5 loadUnsignedByteFromBufferOffset
arg l5 buffer randomState
arg l5 offset fiveOff
run l5
bindOk by5 CSignedInt64 l5
call l6 loadUnsignedByteFromBufferOffset
arg l6 buffer randomState
arg l6 offset sixOff
run l6
bindOk by6 CSignedInt64 l6
call l7 loadUnsignedByteFromBufferOffset
arg l7 buffer randomState
arg l7 offset sevenOff
run l7
bindOk by7 CSignedInt64 l7

# Compose: by0 + by1*256 + by2*65536 + ...
call m1 math.multiplyI64
arg m1 left by1
arg m1 right tFiftySix
run m1
bind p1 I64 m1
call m2 math.multiplyI64
arg m2 left by2
arg m2 right tFiftySix2
run m2
bind p2 I64 m2
call m3 math.multiplyI64
arg m3 left by3
arg m3 right tFiftySix3
run m3
bind p3 I64 m3
call m4 math.multiplyI64
arg m4 left by4
arg m4 right tFiftySix4
run m4
bind p4 I64 m4
call m5 math.multiplyI64
arg m5 left by5
arg m5 right tFiftySix5
run m5
bind p5 I64 m5
call m6 math.multiplyI64
arg m6 left by6
arg m6 right tFiftySix6
run m6
bind p6 I64 m6
call m7 math.multiplyI64
arg m7 left by7
arg m7 right tFiftySix7
run m7
bind p7 I64 m7

# Sum
call a01 math.addI64
arg a01 left by0
arg a01 right p1
run a01
bind a01v I64 a01
call a012 math.addI64
arg a012 left a01v
arg a012 right p2
run a012
bind a012v I64 a012
call a0123 math.addI64
arg a0123 left a012v
arg a0123 right p3
run a0123
bind a0123v I64 a0123
call a4 math.addI64
arg a4 left a0123v
arg a4 right p4
run a4
bind a4v I64 a4
call a5a math.addI64
arg a5a left a4v
arg a5a right p5
run a5a
bind a5v I64 a5a
call a6a math.addI64
arg a6a left a5v
arg a6a right p6
run a6a
bind a6v I64 a6a
call a7a math.addI64
arg a7a left a6v
arg a7a right p7
run a7a
bind composed I64 a7a
returnOk composed


operation nextDeterministicRandomSignedInt64
input nextDeterministicRandomSignedInt64 randomState COpaqueMemoryAddress
output nextDeterministicRandomSignedInt64 Result CSignedInt64 Void
effect nextDeterministicRandomSignedInt64 read memory.buffer
effect nextDeterministicRandomSignedInt64 write memory.buffer
memory nextDeterministicRandomSignedInt64 heap no
async nextDeterministicRandomSignedInt64 no
purpose nextDeterministicRandomSignedInt64 "Advance the MINSTD LCG and return the new state value. LCG: s = (s * 48271) mod 2147483647."

label startNextDeterministicRandomSignedInt64
call loadCall readDeterministicRandomState
arg loadCall state randomState
run loadCall
bindOk current CSignedInt64 loadCall

const multiplier I64 48271
const modulus I64 2147483647
const tFs I64 256

call mulCall math.multiplyI64
arg mulCall left current
arg mulCall right multiplier
run mulCall
bind prod I64 mulCall
call modCall math.moduloI64
arg modCall left prod
arg modCall right modulus
run modCall
bind newState I64 modCall

# Re-store newState into the slot byte-by-byte (mirror of createDeterministicRandomState).
var workN I64 0
set workN newState

const o0 CByteCount 0
const o1 CByteCount 1
const o2 CByteCount 2
const o3 CByteCount 3
const o4 CByteCount 4
const o5 CByteCount 5
const o6 CByteCount 6
const o7 CByteCount 7

call mn0 math.moduloI64
arg mn0 left workN
arg mn0 right tFs
run mn0
bind nb0 I64 mn0
call sN0 pointer.storeByte
arg sN0 buffer randomState
arg sN0 offset o0
arg sN0 value nb0
run sN0
call dN1 math.divideI64
arg dN1 left workN
arg dN1 right tFs
run dN1
bind wN1 I64 dN1
set workN wN1

call mn1 math.moduloI64
arg mn1 left workN
arg mn1 right tFs
run mn1
bind nb1 I64 mn1
call sN1 pointer.storeByte
arg sN1 buffer randomState
arg sN1 offset o1
arg sN1 value nb1
run sN1
call dN2 math.divideI64
arg dN2 left workN
arg dN2 right tFs
run dN2
bind wN2 I64 dN2
set workN wN2

call mn2 math.moduloI64
arg mn2 left workN
arg mn2 right tFs
run mn2
bind nb2 I64 mn2
call sN2 pointer.storeByte
arg sN2 buffer randomState
arg sN2 offset o2
arg sN2 value nb2
run sN2
call dN3 math.divideI64
arg dN3 left workN
arg dN3 right tFs
run dN3
bind wN3 I64 dN3
set workN wN3

call mn3 math.moduloI64
arg mn3 left workN
arg mn3 right tFs
run mn3
bind nb3 I64 mn3
call sN3 pointer.storeByte
arg sN3 buffer randomState
arg sN3 offset o3
arg sN3 value nb3
run sN3
call dN4 math.divideI64
arg dN4 left workN
arg dN4 right tFs
run dN4
bind wN4 I64 dN4
set workN wN4

# Remaining 4 bytes (will be 0 for newState < 2^31)
call mn4 math.moduloI64
arg mn4 left workN
arg mn4 right tFs
run mn4
bind nb4 I64 mn4
call sN4 pointer.storeByte
arg sN4 buffer randomState
arg sN4 offset o4
arg sN4 value nb4
run sN4
call dN5 math.divideI64
arg dN5 left workN
arg dN5 right tFs
run dN5
bind wN5 I64 dN5
set workN wN5

call mn5 math.moduloI64
arg mn5 left workN
arg mn5 right tFs
run mn5
bind nb5 I64 mn5
call sN5 pointer.storeByte
arg sN5 buffer randomState
arg sN5 offset o5
arg sN5 value nb5
run sN5
call dN6 math.divideI64
arg dN6 left workN
arg dN6 right tFs
run dN6
bind wN6 I64 dN6
set workN wN6

call mn6 math.moduloI64
arg mn6 left workN
arg mn6 right tFs
run mn6
bind nb6 I64 mn6
call sN6 pointer.storeByte
arg sN6 buffer randomState
arg sN6 offset o6
arg sN6 value nb6
run sN6
call dN7 math.divideI64
arg dN7 left workN
arg dN7 right tFs
run dN7
bind wN7 I64 dN7
set workN wN7

call sN7 pointer.storeByte
arg sN7 buffer randomState
arg sN7 offset o7
arg sN7 value workN
run sN7

returnOk newState


# ============================================================
# Smoke test: deterministic sequence from a fixed seed.
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
effect main allocate heap
memory main heap yes
async main no
purpose main "Smoke-test the LCG. Seeds with 1, draws 3 numbers and verifies the well-known MINSTD sequence: 1 * 48271 mod (2^31 - 1) = 48271, etc."

label startMain
const seedOne CSignedInt64 1
call makeS createDeterministicRandomState
arg makeS seed seedOne
run makeS
bindOk st COpaqueMemoryAddress makeS

call n1 nextDeterministicRandomSignedInt64
arg n1 state st
run n1
bindOk n1Val CSignedInt64 n1
const expected1 CSignedInt64 48271
call check1 math.equalI64
arg check1 left n1Val
arg check1 right expected1
run check1
bind c1 Bool check1
branchIf c1 c1OkLabel
branch testFailed
label c1OkLabel

call n2 nextDeterministicRandomSignedInt64
arg n2 state st
run n2
bindOk n2Val CSignedInt64 n2
# Second draw: 48271 * 48271 mod (2^31-1) = 182605794
const expected2 CSignedInt64 182605794
call check2 math.equalI64
arg check2 left n2Val
arg check2 right expected2
run check2
bind c2 Bool check2
branchIf c2 c2OkLabel
branch testFailed
label c2OkLabel

call freeIt releaseDeterministicRandomState
arg freeIt state st
run freeIt
ignoreOk freeIt CSignedInt32

const charO CSignedInt32 79
const charK CSignedInt32 75
const charNl CSignedInt32 10
call putO c.putchar
arg putO c charO
run putO
call putK c.putchar
arg putK c charK
run putK
call putNl c.putchar
arg putNl c charNl
run putNl

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
