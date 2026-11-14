## A stage0 sample: several operations calling each other. `square` and
## `power` take copied inputs and give one output; `factorial` and `gcd`
## recurse (each states its maxRecursion); `report` borrows a label and prints
## it with a number, discarding a failed write (its catch is none and it
## suppresses console.WriteError's variant). It prints, and exits with code 0:
##
##   square of 7: 49
##   2 to the 10: 1024
##   factorial of 10: 3628800
##   gcd of 1071 and 462: 21
module calls "Call operations with inputs and outputs, two of them recursive"
  path calls
  imports standard.console standard.math standard.compare
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op square "The square of a number"
  input value Int64 copied
  output Int64
:begin
  multiply: squared = math.multiplyInt64(value, value)
  return squared

op power "A base raised to a non-negative exponent, by repeated multiplication"
  input base Int64 copied
  input exponent Int64 copied
  output Int64
  let result Int64 1 mut
  let count Int64 0 mut
:begin
  goto multiplyMore
:multiplyMore loop=while max=exponent
  doneCheck: done = compare.greaterOrEqualInt64(count, exponent)
  if done finished step
:step in=multiplyMore
  multiply: product = math.multiplyInt64(result, base)
  set result product
  countStep: nextCount = math.addInt64(count, 1)
  set count nextCount
  goto multiplyMore
:finished
  return result

op factorial "The factorial of a number, by recursion"
  input n Int64 copied
  output Int64
  recursion 25
  let one Int64 1
:begin
  baseCheck: atBase = compare.lessOrEqualInt64(n, 1)
  if atBase base recurse
:base
  return one
:recurse
  lower: smaller = math.subtractInt64(n, one)
  inner: rest = factorial(smaller)
  multiply: product = math.multiplyInt64(n, rest)
  return product

op gcd "The greatest common divisor of two numbers, by Euclid's recursion"
  input left Int64 copied
  input right Int64 copied
  output Int64
  recursion 100
:begin
  zeroCheck: rightIsZero = compare.equalInt64(right, 0)
  if rightIsZero done recurse
:done
  return left
:recurse
  remainder: rest = math.remainderInt64(left, right)
  inner: result = gcd(right, rest)
  return result

op report "Print a label and then a number on its line; a failed write is discarded"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op main "Print a square, a power, a factorial, and a greatest common divisor"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
:begin
  squareSeven: squared = square(seven=7)
  reportSquare: report(squareText="square of 7: ", squared)
  powerTwo: powered = power(two=2, ten=10)
  reportPower: report(powerText="2 to the 10: ", powered)
  factorialTen: factored = factorial(ten)
  reportFactorial: report(factorialText="factorial of 10: ", factored)
  gcdOf: divisor = gcd(big=1071, small=462)
  reportGcd: report(gcdText="gcd of 1071 and 462: ", divisor)
  return okCode
  let okCode ExitCode 0
