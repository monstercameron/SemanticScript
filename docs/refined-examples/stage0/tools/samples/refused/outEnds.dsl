## A program `refined check` accepts that is just outside the stage0 subset,
## from the audit: stage0 refuses it at the word concerned and writes no C.
module outEnds "An audit program just outside the stage0 subset, which refined accepts"
  path outEnds
  imports standard.console standard.string
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none


op main "Do one thing stage0 should refuse, then print a line"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
:begin
  check: ends = string.endsWith(word="hello", suffix="llo")
  if ends yes no
:yes
  w1: console.writeLine(yesText="yes") ~
  goto finish
:no
  w2: console.writeLine(noText="no") ~
  goto finish
:finish
  writeDone: console.writeLine(doneText="done") ~
  return okCode
