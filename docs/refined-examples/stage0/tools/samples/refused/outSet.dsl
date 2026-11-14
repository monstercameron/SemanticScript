## A program `refined check` accepts that is just outside the stage0 subset,
## from the audit: stage0 refuses it at the word concerned and writes no C.
module outSet "An audit program just outside the stage0 subset, which refined accepts"
  path outSet
  imports standard.console standard.set
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

instance Names "A set of names" set.Set String

op main "Do one thing stage0 should refuse, then print a line"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
:begin
  make: names = Names.new(scratch)
  add: Names.add(names, ann="ann")
  has: there = Names.contains(names, ann)
  if there yes finish
:yes
  w: console.writeLine(yesText="yes") ~
  goto finish
:finish
  writeDone: console.writeLine(doneText="done") ~
  return okCode
