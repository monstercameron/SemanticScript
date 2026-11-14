## A stage0 sample of every comparison, logic, and arithmetic target at its
## boundaries: each Int64 and Byte comparison on a smaller, an equal, and a
## larger operand, the truth tables of and, or, xor, and not, and division and
## remainder with negative operands. A C operator written wrong (`<=` for `<`)
## changes a line of its output, which the built executable must print as
## `refined run` does. It exits with code 0.
module boundaries "Print comparisons, logic, and arithmetic at their boundaries"
  path boundaries
  imports standard.console standard.compare standard.logic standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op flag "Print a label and a Bool as 0 or 1 on one line"
  input label String borrowed
  input value Bool copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  if value yes no
:yes
  writeOne: console.writeLine(oneText="1") ~
  return
:no
  writeZero: console.writeLine(zeroText="0") ~
  return

op number "Print a label and a number on one line"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op compareInt64 "Print every Int64 comparison of two numbers"
  input left Int64 copied
  input right Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  lessCheck: less = compare.lessThanInt64(left, right)
  showLess: flag(lessText="lessThan ", less)
  lessEqualCheck: lessEqual = compare.lessOrEqualInt64(left, right)
  showLessEqual: flag(lessEqualText="lessOrEqual ", lessEqual)
  greaterCheck: greater = compare.greaterThanInt64(left, right)
  showGreater: flag(greaterText="greaterThan ", greater)
  greaterEqualCheck: greaterEqual = compare.greaterOrEqualInt64(left, right)
  showGreaterEqual: flag(greaterEqualText="greaterOrEqual ", greaterEqual)
  equalCheck: equal = compare.equalInt64(left, right)
  showEqual: flag(equalText="equal ", equal)
  notEqualCheck: notEqual = compare.notEqualInt64(left, right)
  showNotEqual: flag(notEqualText="notEqual ", notEqual)
  return

op compareByte "Print every Byte comparison of two bytes"
  input left Byte copied
  input right Byte copied
  effect write console.stdout
  uses stdoutWriter
:begin
  lessCheck: less = compare.lessThanByte(left, right)
  showLess: flag(lessText="byte lessThan ", less)
  lessEqualCheck: lessEqual = compare.lessOrEqualByte(left, right)
  showLessEqual: flag(lessEqualText="byte lessOrEqual ", lessEqual)
  greaterCheck: greater = compare.greaterThanByte(left, right)
  showGreater: flag(greaterText="byte greaterThan ", greater)
  greaterEqualCheck: greaterEqual = compare.greaterOrEqualByte(left, right)
  showGreaterEqual: flag(greaterEqualText="byte greaterOrEqual ", greaterEqual)
  equalCheck: equal = compare.equalByte(left, right)
  showEqual: flag(equalText="byte equal ", equal)
  notEqualCheck: notEqual = compare.notEqualByte(left, right)
  showNotEqual: flag(notEqualText="byte notEqual ", notEqual)
  return

op logicOf "Print and, or, xor of two Bools and not of the first"
  input left Bool copied
  input right Bool copied
  effect write console.stdout
  uses stdoutWriter
:begin
  andCheck: both = logic.and(left, right)
  showAnd: flag(andText="and ", both)
  orCheck: either = logic.or(left, right)
  showOr: flag(orText="or ", either)
  xorCheck: oneOf = logic.xor(left, right)
  showXor: flag(xorText="xor ", oneOf)
  notCheck: negated = logic.not(left)
  showNot: flag(notText="not ", negated)
  return

op arithmetic "Print the quotient, remainder, difference, product, negation, and magnitude of numbers"
  input left Int64 copied
  input right Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  divide: quotient = math.divideInt64(left, right)
  showQuotient: number(quotientText="divide ", quotient)
  remain: remainder = math.remainderInt64(left, right)
  showRemainder: number(remainderText="remainder ", remainder)
  subtract: difference = math.subtractInt64(left, right)
  showDifference: number(differenceText="subtract ", difference)
  multiply: product = math.multiplyInt64(left, right)
  showProduct: number(productText="multiply ", product)
  negate: negated = math.negateInt64(left)
  showNegated: number(negateText="negate ", negated)
  absolute: magnitude = math.absoluteInt64(left)
  showMagnitude: number(absoluteText="absolute ", magnitude)
  return

op main "Compare, combine, and divide numbers at their boundaries"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let one Int64 1
  let two Int64 2
  let three Int64 3
  let smallByte Byte 1
  let middleByte Byte 2
  let largeByte Byte 250
  let yes Bool true
  let no Bool false
  let minusSeven Int64 -7
  let okCode ExitCode 0
:begin
  compareSmaller: compareInt64(one, two)
  compareEqual: compareInt64(two, two)
  compareLarger: compareInt64(three, two)
  compareSmallerByte: compareByte(smallByte, middleByte)
  compareEqualByte: compareByte(middleByte, middleByte)
  compareLargerByte: compareByte(largeByte, middleByte)
  logicBoth: logicOf(yes, yes)
  logicFirst: logicOf(yes, no)
  logicSecond: logicOf(no, yes)
  logicNeither: logicOf(no, no)
  arithmeticNegative: arithmetic(minusSeven, two)
  arithmeticPositive: arithmetic(three, minusSeven)
  return okCode
