## A stage0 sample that reads past the end of a list with `getOrTrap`, the
## trapping twin of `get` (D-101): it prints the list's length, then traps
## (exit code 70). `refined run` and the executable stage0 builds from it
## stop at the same place.
module outofrange "Read past the end of a list with getOrTrap, so the trap can be compared"
  path outofrange
  imports standard.console standard.list
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

instance Numbers "A list of numbers" list.List Int64

op main "Print a list's length, then read one item past its end"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 4096
  let okCode ExitCode 0
:begin
  makeNumbers: numbers = Numbers.new(scratch)
  addSeven: Numbers.append(numbers, seven=7)
  addEight: Numbers.append(numbers, eight=8)
  countNumbers: count = Numbers.length(numbers)
  printCount: console.writeIntegerLine(count) ~
  readPast: past = Numbers.getOrTrap(numbers, count)
  printPast: console.writeIntegerLine(past) ~
  return okCode
