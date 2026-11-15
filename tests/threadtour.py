"""threads.h's waits in an executable (D-191): a program that calls the runtime's C library through `ffi` and prints
what its mutexes and condition variables give.

On Windows the mutexes and condition variables block in the system (SRW locks and condition variables, kernel32's
own), and this is the proof that the executable's build of them, x86_64 even where the JIT is ARM64, runs: a plain
mutex taken, refused to a second take, and timed out on by mtx_timedlock once a deadline a second ahead has passed (the
clock read again after it says it waited), cnd_timedwait timing out the same way and holding the mutex again after,
signals with no waiter, a recursive mutex taken twice. Contention between threads is cthreads' contentionTest under
`refined test`: a program reaching the library through `ffi` cannot hand thrd_create a function of its own. The test
runs on Windows; Linux's threads are proved by tests/cprograms/threads_c11.c.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

FUNCTIONS = ["calloc", "memset", "time", "mtx_init", "mtx_lock", "mtx_trylock", "mtx_timedlock", "mtx_unlock",
             "cnd_init", "cnd_timedwait", "cnd_signal", "cnd_broadcast"]

DSL = '''module threadtour "Take, refuse, and time out on threads.h's mutexes and condition variables through ffi"
  path threadtour
  imports standard.console standard.ffi standard.convert standard.compare standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

CAPS

optype AllocFunction "void *calloc(size_t, size_t), the address as a whole number"
  input count Int64 copied
  input size Int64 copied
  output Int64

optype SetFunction "void *memset(void *, int, size_t)"
  input target Int64 copied
  input value Int32 copied
  input bytes Int64 copied
  output Int64

optype TimeFunction "time_t time(time_t *)"
  input where Int64 copied
  output Int64

optype OneFunction "int f(void *)"
  input target Int64 copied
  output Int32

optype KindFunction "int mtx_init(mtx_t *, int)"
  input target Int64 copied
  input kind Int32 copied
  output Int32

optype TwoFunction "int f(void *, const void *)"
  input target Int64 copied
  input other Int64 copied
  output Int32

optype ThreeFunction "int cnd_timedwait(cnd_t *, mtx_t *, const struct timespec *)"
  input condition Int64 copied
  input mutex Int64 copied
  input deadline Int64 copied
  output Int32

instance AllocBinding "Binds calloc" ffi.Function AllocFunction

instance SetBinding "Binds memset" ffi.Function SetFunction

instance TimeBinding "Binds time" ffi.Function TimeFunction

instance OneBinding "Binds a function of one pointer" ffi.Function OneFunction

instance KindBinding "Binds mtx_init" ffi.Function KindFunction

instance TwoBinding "Binds a function of two pointers" ffi.Function TwoFunction

instance ThreeBinding "Binds cnd_timedwait" ffi.Function ThreeFunction

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op sayInt "Write an int on a line"
  input value Int32 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  widen: wide = convert.int32ToInt64(value)
  write: console.writeIntegerLine(wide) ~
  return

op putLong "Put a non-negative long at an address, a byte at a time through memset"
  input setter SetFunction copied
  input at Int64 copied
  input value Int64 copied
  let left Int64 0 mut
  let index Int64 0 mut
  let bytes Int64 8
:begin
  set left value
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(index, bytes)
  if done finish put
:put in=eachByte
  lowOf: low = math.remainderInt64(left, base=256)
  narrow: code = convert.int64ToInt32(low)
  whereOf: where = math.addInt64(at, index)
  setIt: unused = *setter(where, code, one=1)
  shiftOf: rest = math.divideInt64(left, base2=256)
  set left rest
  stepOf: next = math.addInt64(index, step=1)
  set index next
  goto eachByte
:finish
  return

op deadlineAhead "Put a TIME_UTC deadline at the start of the next second but one at an address: time() + 1 seconds and 0 nanoseconds; the seconds"
  input setter SetFunction copied
  input clock TimeFunction copied
  input at Int64 copied
  output Int64
:begin
  readNow: now = *clock(nothing=0)
  dueOf: due = math.addInt64(now, oneSecond=1)
  putSeconds: putLong(setter, at, due)
  nanosAt: nanos = math.addInt64(at, eight=8)
  putNanos: putLong(setter, nanos, zero=0)
  return due

op sayPassed "Write 1 when the clock has reached a second, else 0"
  input clock TimeFunction copied
  input due Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  readNow: now = *clock(nothing=0)
  check: passed = compare.greaterOrEqualInt64(now, due)
  if passed yes no
:yes
  sayYes: sayNumber(one=1)
  return
:no
  sayNo: sayNumber(zero=0)
  return

op main "Take, refuse, time out on, and give back a mutex and a condition variable of the C library"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
USES
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
  bindcalloc: callocFn = AllocBinding.bind(libc, callocName="calloc") ? failed
  bindmemset: memsetFn = SetBinding.bind(libc, memsetName="memset") ? failed
  bindtime: timeFn = TimeBinding.bind(libc, timeName="time") ? failed
  bindinit: initFn = KindBinding.bind(libc, initName="mtx_init") ? failed
  bindlock: lockFn = OneBinding.bind(libc, lockName="mtx_lock") ? failed
  bindtry: tryFn = OneBinding.bind(libc, tryName="mtx_trylock") ? failed
  bindtimed: timedFn = TwoBinding.bind(libc, timedName="mtx_timedlock") ? failed
  bindunlock: unlockFn = OneBinding.bind(libc, unlockName="mtx_unlock") ? failed
  bindcinit: condInitFn = OneBinding.bind(libc, condInitName="cnd_init") ? failed
  bindcwait: condWaitFn = ThreeBinding.bind(libc, condWaitName="cnd_timedwait") ? failed
  bindcsignal: signalFn = OneBinding.bind(libc, signalName="cnd_signal") ? failed
  bindcbroadcast: broadcastFn = OneBinding.bind(libc, broadcastName="cnd_broadcast") ? failed
  takeMutex: mutex = *callocFn(mutexBytes=64, one=1)
  takeCondition: condition = *callocFn(conditionBytes=64, one2=1)
  takeDeadline: deadline = *callocFn(deadlineBytes=16, one3=1)
  init: inited = *initFn(mutex, plain=0)
  showInit: sayInt(inited)
  lock: locked = *lockFn(mutex)
  showLock: sayInt(locked)
  try: tried = *tryFn(mutex)
  showTry: sayInt(tried)
  aheadLock: lockDue = deadlineAhead(memsetFn, timeFn, deadline)
  timed: timedOut = *timedFn(mutex, deadline)
  showTimed: sayInt(timedOut)
  passedLock: sayPassed(timeFn, lockDue)
  condInit: condInited = *condInitFn(condition)
  showCondInit: sayInt(condInited)
  aheadWait: waitDue = deadlineAhead(memsetFn, timeFn, deadline)
  wait: waited = *condWaitFn(condition, mutex, deadline)
  showWait: sayInt(waited)
  passedWait: sayPassed(timeFn, waitDue)
  stillHeld: heldAfter = *tryFn(mutex)
  showHeld: sayInt(heldAfter)
  signal: signalled = *signalFn(condition)
  showSignal: sayInt(signalled)
  broadcast: broadcasted = *broadcastFn(condition)
  showBroadcast: sayInt(broadcasted)
  unlock: unlocked = *unlockFn(mutex)
  showUnlock: sayInt(unlocked)
  tryFree: freeTry = *tryFn(mutex)
  showFree: sayInt(freeTry)
  unlockFree: freeUnlocked = *unlockFn(mutex)
  showFreeUnlock: sayInt(freeUnlocked)
  initRecursive: recursiveInited = *initFn(mutex, recursive=1)
  showRecursive: sayInt(recursiveInited)
  lockOnce: first = *lockFn(mutex)
  showOnce: sayInt(first)
  lockTwice: second = *lockFn(mutex)
  showTwice: sayInt(second)
  unlockOnce: firstBack = *unlockFn(mutex)
  showBackOnce: sayInt(firstBack)
  unlockTwice: secondBack = *unlockFn(mutex)
  showBackTwice: sayInt(secondBack)
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''

# init, lock, a refused try, the timed lock's thrd_timedout and its deadline reached, cnd_init, the timed wait's
# thrd_timedout and its deadline reached, the mutex still held after, two signals with no waiter, unlock, a free try
# and its unlock, a recursive mutex taken twice and given back twice
EXPECTED = ["0", "0", "1", "4", "1", "0", "4", "1", "1", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"]


def write_project(folder: str) -> None:
    """The project: build.sem and threadtour.sem, generated from the DSL above."""
    write_ffi_project(folder, "threadtour", DSL, FUNCTIONS, "threads.h's waits through ffi")


def write_ffi_project(folder: str, name: str, dsl: str, functions: list[str], purpose: str) -> None:
    """A project of one module, `name`, generated from a DSL whose `CAPS` and `USES` stand for a capability to bind
    each of the C functions and the main operation's use of each, its entry `<name>.main`."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    caps = "\n\n".join(f'capability {n.replace("_", "")}Symbol "Authority to bind the C function {n}" load '
                       f'ffi.symbols "{n}"' for n in functions)
    uses = "\n".join(f"  uses {n.replace('_', '')}Symbol" for n in functions)
    dsl = dsl.replace("CAPS", caps).replace("USES", uses)
    prog = Program()
    m = Module(name)
    prog.modules[name] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render([f"# {purpose} (tests/{name}.py)."], None)
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and target == "ffi.open":
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{name}.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", f'tourProject purpose "{purpose}"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            f"tourProject includesModule {name}", f"tourProject entry {name}.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
