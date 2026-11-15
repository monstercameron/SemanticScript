module cstart "What a C program linked with the runtime's C library has done before main: the process's stack kept, the stack protector's canary, and the standard streams' data symbols (D-161)"
  path cstart
  imports standard.machine standard.system standard.test kernel heap clibrary
  exports none

capability memoryAccess "Authority to keep what the process started with and fill the canary" use machine.memory none

capability systemCalls "Authority to set the thread pointer and read random bytes" use system.calls none

## D-161: `refined build semanticscript/runtime --kind clibrary` writes the C library as an object a C program links
## instead of glibc on Linux. Its `_start` (the compiler's few instructions) calls `refined_c_prepare` with the stack the
## kernel gave (argc, argv, envp), then the program's init arrays, then `main(argc, argv, envp)`, then `exit`. The code
## gcc compiles reads the stack protector's canary at %fs:0x28 on x86_64, so the thread pointer is set to a block of
## the library's own that points at itself, with a random canary at 0x28; on AArch64 the canary is the data symbol
## `__stack_chk_guard`, filled from getrandom, and the thread pointer (tpidr_el0) is set to such a block too, which
## threads.h reads (D-166). machine.state byte 2352 holds the block's address.
constant blockAt "Where the thread block's address is kept, in machine.state" Int64 2352

op prepareProgram "Make the process ready for a C program's main: keep argc, argv, and envp; set up the stack protector's canary; point stdin, stdout, and stderr at their FILE blocks"
  invariant readiesProgram "After it, argv and envp are what the stack held and the data symbols point at the FILE blocks"
  input stack machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_c_prepare"
:begin
  kernel.initialStack(stack)
  clibrary.prepare()
  onLinux = system.posix()
  if onLinux linux done
:linux
  onArm = system.aarch64()
  if onArm armGuard intelBlock
:armGuard
  guard = kernel.stateAt(1560)
  system.getrandom(guard, 8, 0)
  armBlock = threadBlock()
  machine.setThreadPointer(armBlock)
  return
:intelBlock
  block = threadBlock()
  calc canary = block + 40
  system.getrandom(canary, 8, 0)
  system.archPrctl(4098, block)
  return
:done
  return

op threadBlock "The first thread's block (D-166): it points at itself (at 0 and 16), with the canary at 0x28, errno's cell of a later thread at 0x40, its record at 0x38, and thread-specific values from 0x80; kept at machine.state 2352"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  slot = kernel.stateAt(blockAt)
  block = heap.take(640)
  machine.storeAddress(block, block)
  calc selfAt = block + 16
  machine.storeAddress(selfAt, block)
  machine.storeAddress(slot, block)
  return block

@tests

test prepareTest "Preparing for a C program keeps the stack's argc and argv and points stdout at its FILE block"
  verifies prepareProgram readiesProgram
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.posix()
  if onLinux skip run
:run
  stack = heap.take(64)
  machine.storeInt64(stack, 0)
  prepareProgram(stack)
  count = kernel.argumentCount()
  test.assertEqualInt64(0, count)
  stdoutCell = kernel.stateAt(1544)
  stdoutFile = machine.loadAddress(stdoutCell)
  expected = kernel.stateAt(2048)
  test.assertTrue(stdoutFile == expected)
  return
:skip
  return
