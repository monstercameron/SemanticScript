## A stage0 sample: files through the host library, each target checked
## against the scope of the capability that grants it (D-38). It makes the
## build/ directory, writes a file there from an operation that raises the
## standard library's fs.FileError, reads it back, and then reads a file
## outside build/, which the runtime refuses before the file is touched: the
## program stops with the trap exit code, 70, after printing
##
##   wrote 2 lines
##   first line
##   second line
module files "Write a file under build/, read it back, and try to read outside build/"
  path files
  imports standard.console standard.fs standard.string standard.time
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability buildFiles "Authority to read and write files under build/"
  grants read fs.files "build/"
  grants write fs.files "build/"

op save "Make the build/ directory when it is missing and write a text to a file in it"
  input path String borrowed
  input text String borrowed
  input deadline time.Deadline copied
  raises fs.FileError
  effect write fs.files
  uses buildFiles
  async
:begin
  makeDirectory: fs.createDirectory(directory="build") ~ "The directory usually exists already; if it cannot be made, writing the file fails next and says so"
  makeBytes: textBytes = string.toBytes(text)
  task writeIt: fs.writeAll(path, textBytes, deadline) ?^
  return

op main "Write a file, read it back, then try to read outside build/"
  output ExitCode
  effect write console.stdout
  effect read fs.files
  effect write fs.files
  uses stdoutWriter
  uses buildFiles
  async
  region store 1048576
  let path String "build/files-sample.txt"
  let outsideName String "outside.txt"
  let text String "first line\nsecond line"
  let limit Int64 4096
  let okCode ExitCode 0
  let failedCode ExitCode 3
:begin
  makeDeadline: deadline = time.Deadline.after(tenSeconds=10000)
  task saveIt: save(path, text, deadline) ? failed
  writeWrote: console.writeLine(wroteText="wrote 2 lines") ~
  task readIt: bytes = fs.readAll(path, store, limit, deadline) ? failed
  decode: readBack = string.fromBytes(bytes, store) ? failed
  writeReadBack: console.writeLine(readBack) ~
  makeOutsidePath: outsidePath = string.concat(outsideLead="files-", outsideName, store)
  task readOutside: outsideBytes = fs.readAll(outsidePath, store, limit, deadline) ? failed
  writeOutside: console.writeLine(outsideText="read outside build/") ~
  return okCode
:failed
  writeFailed: console.writeLine(failedText="a file could not be written or read") ~
  return failedCode
