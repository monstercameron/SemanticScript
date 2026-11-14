## A program `refined check` accepts that is just outside the stage0 subset,
## from the audit: stage0 refuses it at the word concerned and writes no C.
module outEscape "An audit program just outside the stage0 subset, which refined accepts"
  path outEscape
  imports standard.console 
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none


op main "Do one thing stage0 should refuse, then print a line"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
:begin
  w: console.writeLine(escaped="A\x41B") ~
  writeDone: console.writeLine(doneText="done") ~
  return okCode
