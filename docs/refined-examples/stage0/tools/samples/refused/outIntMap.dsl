## A program `refined check` accepts that is just outside the stage0 subset,
## from the audit: stage0 refuses it at the word concerned and writes no C.
module outIntMap "An audit program just outside the stage0 subset, which refined accepts"
  path outIntMap
  imports standard.console standard.map
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

instance Ages "Ages by number" map.Map Int64 Int64

op main "Do one thing stage0 should refuse, then print a line"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
:begin
  make: ages = Ages.new(scratch)
  put: Ages.put(ages, one=1, two=2)
  get: got = Ages.get(ages, one) ? finish
  w: console.writeIntegerLine(got) ~
  goto finish
:finish
  writeDone: console.writeLine(doneText="done") ~
  return okCode
