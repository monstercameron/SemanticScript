"""setjmp and longjmp in an executable (D-192): a program that calls the runtime's C library's setjmp and longjmp
through `ffi` and prints what setjmp gives each time it returns.

The program keeps its count of setjmp's returns in memory the C library gave (a string one byte longer each pass,
measured with strlen), since what is in its registers after setjmp's second return is what setjmp kept: the first
return gives 0 and longjmps with 7, the second gives 7 and longjmps with 0, the third gives 1 and ends. On Windows
x86_64 the routines are machine code the compiler writes as bytes, so this proves them in an executable built on an
ARM64 machine, whose LLVM has no x86 assembler, as on an x86_64 one.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import threadtour  # noqa: E402

FUNCTIONS = ["calloc", "memset", "strlen", "setjmp", "longjmp"]

DSL = '''module jumptour "Come back to a setjmp twice through longjmp, with 7 and then with 0"
  path jumptour
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

optype LengthFunction "size_t strlen(const char *)"
  input text Int64 copied
  output Int64

optype SaveFunction "int setjmp(jmp_buf)"
  input buffer Int64 copied
  output Int32

optype JumpFunction "void longjmp(jmp_buf, int)"
  input buffer Int64 copied
  input value Int32 copied

instance AllocBinding "Binds calloc" ffi.Function AllocFunction

instance SetBinding "Binds memset" ffi.Function SetFunction

instance LengthBinding "Binds strlen" ffi.Function LengthFunction

instance SaveBinding "Binds setjmp" ffi.Function SaveFunction

instance JumpBinding "Binds longjmp" ffi.Function JumpFunction

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op main "setjmp, then longjmp back to it with 7 and with 0, writing what setjmp gives and how many times it returned before"
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
  bindstrlen: strlenFn = LengthBinding.bind(libc, strlenName="strlen") ? failed
  bindsetjmp: setjmpFn = SaveBinding.bind(libc, setjmpName="setjmp") ? failed
  bindlongjmp: longjmpFn = JumpBinding.bind(libc, longjmpName="longjmp") ? failed
  takeBuffer: buffer = *callocFn(bufferBytes=512, one=1)
  takeMarks: marks = *callocFn(markBytes=16, one2=1)
  save: value = *setjmpFn(buffer)
  count: passes = *strlenFn(marks)
  findMark: at = math.addInt64(marks, passes)
  mark: marked = *memsetFn(at, letterX=120, one3=1)
  widen: wide = convert.int32ToInt64(value)
  showValue: sayNumber(wide)
  showPasses: sayNumber(passes)
  firstCheck: first = compare.equalInt64(passes, zero=0)
  if first jumpSeven notFirst
:jumpSeven
  jumpWith7: *longjmpFn(buffer, seven=7)
  goto failed
:notFirst
  secondCheck: second = compare.equalInt64(passes, one4=1)
  if second jumpZero done
:jumpZero
  jumpWith0: *longjmpFn(buffer, zero32=0)
  goto failed
:done
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''

# setjmp's value and how many times it had returned before: 0 first, 7 from longjmp(7), 1 from longjmp(0)
EXPECTED = ["0", "0", "7", "1", "1", "2"]


def write_project(folder: str) -> None:
    """The project: build.sem and jumptour.sem, generated from the DSL above."""
    threadtour.write_ffi_project(folder, "jumptour", DSL, FUNCTIONS, "setjmp and longjmp through ffi")
