## A stage0 sample from the audit: a division whose divisor reaches zero, which
## traps (exit code 70) in the built executable as under `refined run`.
module divtrap "Divide by a number that reaches zero, so the program traps"
  path divtrap
  imports standard.console standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op main "Print 100 divided by 3, 2, 1, then trap dividing by 0"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let d Int64 3 mut
  let limit Int64 10
  let okCode ExitCode 0
:begin
  goto each
:each loop=while max=limit
  divide: q = math.divideInt64(hundred=100, d)
  writeQ: console.writeIntegerLine(q) ~
  lower: nextD = math.subtractInt64(d, 1)
  set d nextD
  goto each
