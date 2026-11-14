## A stage0 sample from the audit of the self-hosted compiler: Collatz steps
## and digit sums in loops, ending in an exit code the program computes.
module collatz "Count Collatz steps and sum digits, exiting with a computed code"
  path collatz
  imports standard.console standard.math standard.compare standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op steps "The number of Collatz steps from n down to 1"
  input n Int64 copied
  output Int64
  let value Int64 0 mut
  let count Int64 0 mut
  let limit Int64 1000
:begin
  set value n
  goto walk
:walk loop=while max=limit
  oneCheck: atOne = compare.lessOrEqualInt64(value, 1)
  if atOne finished move
:move in=walk
  half: rest = math.remainderInt64(value, 2)
  evenCheck: isEven = compare.equalInt64(rest, 0)
  addStep: nextCount = math.addInt64(count, 1)
  set count nextCount
  if isEven halve triple
:halve in=walk
  divide: halved = math.divideInt64(value, 2)
  set value halved
  goto walk
:triple in=walk
  times: tripled = math.multiplyInt64(value, 3)
  plus: bumped = math.addInt64(tripled, 1)
  set value bumped
  goto walk
:finished
  return count

op digitSum "The sum of the decimal digits of a number, by recursion"
  input n Int64 copied
  output Int64
  recursion 30
:begin
  small: isSmall = compare.lessThanInt64(n, 10)
  if isSmall base recurse
:base
  return n
:recurse
  lastDigit: last = math.remainderInt64(n, 10)
  shift: rest = math.divideInt64(n, 10)
  inner: restSum = digitSum(rest)
  total: summed = math.addInt64(last, restSum)
  return summed

op report "Print a label and a number"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op main "Print Collatz steps for a few numbers and exit with a code computed from them"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let total Int64 0 mut
  let n Int64 1 mut
  let top Int64 12
:begin
  goto each
:each loop=while max=top
  doneCheck: past = compare.greaterThanInt64(n, top)
  if past summary doOne
:doOne in=each
  count: s = steps(n)
  reportIt: report(stepsText="steps: ", s)
  addIt: nextTotal = math.addInt64(total, s)
  set total nextTotal
  bump: nextN = math.addInt64(n, 1)
  set n nextN
  goto each
:summary
  reportTotal: report(totalText="total: ", total)
  sumDigits: ds = digitSum(big=9876543210)
  reportDigits: report(digitsText="digits: ", ds)
  power: p = math.powerInt64(three=3, five=5)
  reportPower: report(powerText="3^5: ", p)
  neg: negated = math.negateInt64(p)
  absolute: back = math.absoluteInt64(negated)
  reportAbs: report(absText="abs: ", back)
  modCode: code = math.remainderInt64(total, 200)
  toCode: exitCode = convert.int64ToExitCode(code)
  return exitCode
