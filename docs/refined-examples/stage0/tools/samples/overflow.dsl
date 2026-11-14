## A stage0 sample from the audit: doubling a number until Int64 overflows,
## which traps (exit code 70) in the built executable as under `refined run`.
module overflow "Double a number until Int64 overflows, so the program traps"
  path overflow
  imports standard.console standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op main "Print doublings until the multiplication overflows"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let v Int64 1 mut
  let limit Int64 100
:begin
  goto each
:each loop=while max=limit
  double: doubled = math.multiplyInt64(v, 4)
  set v doubled
  writeV: console.writeIntegerLine(v) ~
  goto each
