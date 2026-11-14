## A stage0 sample whose recursion passes its bound. `countDown` prints its
## number and calls itself with the next one, stating `maxRecursion 4`; started at
## 1 it would stop at 6, but the fifth nested call traps (exit code 70) after
## printing 1 to 4. `refined run` and the executable stage0 builds from it
## stop at the same place.
module depth "Recurse past a stated maxRecursion, so the bound's trap can be compared"
  path depth
  imports standard.console standard.math standard.compare
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op countDown "Print a number, then count on from the next one until past the last, one call deeper each time"
  input number Int64 copied
  input last Int64 copied
  effect write console.stdout
  uses stdoutWriter
  recursion 4
:begin
  pastCheck: past = compare.greaterThanInt64(number, last)
  if past done print
:print
  printIt: console.writeIntegerLine(number) ~
  next: following = math.addInt64(number, 1)
  deeper: countDown(following, last)
  goto done
:done
  return

op main "Count from 1 to 6 by recursion bounded to four nested calls"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let okCode ExitCode 0
:begin
  count: countDown(one=1, six=6)
  return okCode
