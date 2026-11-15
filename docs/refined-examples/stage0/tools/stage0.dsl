module stage0 "Compile a SemanticScript project in the stage0 subset to C and build it with the C compiler"
  path stage0
  imports standard.console standard.process standard.fs standard.string standard.buffer standard.list standard.compare standard.math standard.convert standard.time lexer syntax model emitc
  exports main

capability argumentReader "Authority to read the project path, output name, and compiler name" read process.arguments none

capability stdoutWriter "Authority to report what was built on standard output" write console.stdout none

capability stderrWriter "Authority to report diagnostics and problems on standard error" write console.stderr none

capability sourceFiles "Authority to read a project's files under the working directory" read fs.files "./"

capability buildFiles "Authority to write the C file under build/ and to make that directory" write fs.files "build/"

capability cCompilers "Authority to run a C compiler named exactly cc, gcc, or clang"
  grants spawn process.programs "cc"
  grants spawn process.programs "gcc"
  grants spawn process.programs "clang"

## The standard library's string.Position, declared for stage0 as a module of its own that comes first in every program
constant libraryText "The standard library's records programs use, as a module stage0 puts before the program's own" String "string is module\nstring purpose \"The records of the standard library's string module, as stage0 declares them\"\nstring path string\nstring imports none\nstring exports Position\n\nPosition is record\nPosition purpose \"A place in a text: a byte offset, and the line and column it is on\"\nPosition typeParameter none\nPosition field offset Int64\nPosition field line Int64\nPosition field column Int64\n"

record SourceFile "A file of the program text: its path, the offset its text starts at, and the line it starts on"
  field path String
  field start Int64
  field line Int64

instance SourceFiles "The files of a program, in the order their texts follow one another" list.List SourceFile

instance Texts "Names or paths, in order" list.List String

enum FileProblem "Why a module's file could not be used, with its position in the list of paths"
  variant unreadable Int64
  variant notText Int64

## ---------------------------------------------------------------- the project

op placeholder "A word that names nothing, at the start of the text"
  output syntax.Word
:begin
  makeKind: kind = syntax.WordKind.name()
  makeOrigin: origin = string.Position.new(0, 1, 1)
  makeWord: word = syntax.Word.new(kind, origin, 0)
  return word

op entryNamesModule "Decide whether an entry names the main operation of an included module: it is `<module>.main`"
  input entry String borrowed
  input names Texts borrowed
  input region Region borrowed
  output Bool
  let yes Bool true
  let no Bool false
:begin
  countNames: nameCount = Texts.length(names)
  goto eachName
:eachName loop=forEach max=nameCount over=names
  next names name compareOne missing
:compareOne in=eachName
  joinMain: mainText = string.concat(name, mainSuffix=".main", region)
  sameCheck: same = string.equals(mainText, entry)
  if same found eachName
:found
  return yes
:missing
  return no

op projectModules "Read build.sem's rows: the modules it includes, in order, and its entry, which must be `<module>.main` for an included module; a module's name has no dot, and the project requires no other project"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input names Texts borrowedMutable
  input region Region borrowed
  output String
  owner region
  raises syntax.Rejection
  let entryText String "" mut
  let hasEntry Bool false mut
  let entryWord syntax.Word unset mut
  let yes Bool true
:begin
  makePlaceholder: nowhere = placeholder()
  set entryWord nowhere
  countRows: rowCount = syntax.Rows.length(rows)
  goto eachRow
:eachRow loop=forEach max=rowCount over=rows
  next rows row readPredicate finish
:readPredicate in=eachRow
  readRowFirst: wordFirst = syntax.Row.first(row)
  findPredicate: predicateAt = math.addInt64(wordFirst, 1)
  readPredicateWord: predicate = syntax.Words.getOrTrap(words, predicateAt)
  findPayload: payloadAt = math.addInt64(wordFirst, 2)
  readPayload: payload = syntax.Words.getOrTrap(words, payloadAt)
  includesCheck: includes = syntax.isText(source, predicate, includesWord="includesModule") ?^
  if includes include notInclude
:include in=eachRow
  copyName: nameText = syntax.wordText(source, payload, region) ?^
  findDot: dotAt = string.find(nameText, dot=".") ? appendName
  goto dotted
:appendName in=eachRow
  addName: Texts.append(names, nameText)
  goto eachRow
:notInclude in=eachRow
  entryCheck: isEntry = syntax.isText(source, predicate, entryRowWord="entry") ?^
  if isEntry keepEntry requiresCheck
:keepEntry in=eachRow
  copyEntry: entryCopy = syntax.wordText(source, payload, region) ?^
  set entryText entryCopy
  set entryWord payload
  set hasEntry yes
  goto eachRow
:requiresCheck in=eachRow
  requiresTest: isRequires = syntax.isText(source, predicate, requiresWord="requires") ?^
  if isRequires requiresNone eachRow
:requiresNone in=eachRow
  noneCheck: requiresNothing = syntax.isText(source, payload, noneWord="none") ?^
  if requiresNothing eachRow otherProject
:finish
  if hasEntry checkEntry noEntry
:checkEntry
  entryFound: named = entryNamesModule(entryText, names, region)
  if named done noEntry
:done
  return entryText
@reject badProject payload dotted
@reject badProject payload otherProject
@reject badProject entryWord noEntry

op modulePaths "The path of each module's file: `<project>/<module>.sem`"
  input project String borrowed
  input names Texts borrowed
  input paths Texts borrowedMutable
  input region Region borrowed
:begin
  countNames: nameCount = Texts.length(names)
  goto eachName
:eachName loop=forEach max=nameCount over=names
  next names name makePath done
:makePath in=eachName
  addSlash: folder = string.concat(project, slash="/", region)
  addName: named = string.concat(folder, name, region)
  addSuffix: path = string.concat(named, suffix=".sem", region)
  addPath: Texts.append(paths, path)
  goto eachName
:done
  return

## ---------------------------------------------------------------- the program text

op countLines "Count the newline bytes of a text"
  input text String borrowed
  output Int64
  let index Int64 0 mut
  let count Int64 0 mut
  let newlineByte Byte 10
:begin
  measure: length = string.byteLength(text)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: allRead = compare.greaterOrEqualInt64(index, length)
  if allRead done readByte
:readByte in=eachByte
  fetch: byte = string.byteAtOrTrap(text, index)
  stepIndex: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  newlineCheck: isNewline = compare.equalByte(byte, newlineByte)
  if isNewline countIt eachByte
:countIt in=eachByte
  addOne: nextCount = math.addInt64(count, 1)
  set count nextCount
  goto eachByte
:done
  return count

op endsWithNewline "Decide whether a text is empty or ends with a newline byte"
  input text String borrowed
  output Bool
  let yes Bool true
  let newlineByte Byte 10
:begin
  measure: length = string.byteLength(text)
  emptyCheck: isEmpty = compare.equalInt64(length, 0)
  if isEmpty empty readLast
:readLast
  findLast: lastAt = math.subtractInt64(length, 1)
  fetch: last = string.byteAtOrTrap(text, lastAt)
  newlineCheck: isNewline = compare.equalByte(last, newlineByte)
  return isNewline
:empty
  return yes

op gatherSources "Put the program text together: stage0's library module, then each module's file in order (a file that does not end in a newline gets one), recording for each where its text starts and on which line"
  input paths Texts borrowed
  input files SourceFiles borrowedMutable
  input all buffer.ByteBuffer borrowedMutable
  input deadline time.Deadline copied
  input region Region borrowed
  raises FileProblem
  effect read fs.files
  uses sourceFiles
  async
  let index Int64 0 mut
  let line Int64 1 mut
  let readLimit Int64 16777216
  let newlineByte Byte 10
  let libraryPath String "stage0:string"
:begin
  makeLibrary: libraryFile = SourceFile.new(libraryPath, 0, 1, region)
  addLibrary: SourceFiles.append(files, libraryFile)
  putLibrary: buffer.appendString(all, libraryText)
  countLibrary: libraryLines = countLines(libraryText)
  afterLibrary: libraryNext = math.addInt64(line, libraryLines)
  set line libraryNext
  countPaths: pathCount = Texts.length(paths)
  goto eachPath
:eachPath loop=forEach max=pathCount over=paths
  next paths path readOne done
:readOne in=eachPath
  task readFile: bytes = fs.readAll(path, region, readLimit, deadline) ? unreadable
  decode: text = string.fromBytes(bytes, region) ? notText
  measureAll: start = buffer.length(all)
  makeFile: file = SourceFile.new(path, start, line, region)
  addFile: SourceFiles.append(files, file)
  putText: buffer.appendString(all, text)
  countText: textLines = countLines(text)
  afterText: textNext = math.addInt64(line, textLines)
  set line textNext
  endsCheck: ends = endsWithNewline(text)
  if ends advance addNewline
:addNewline in=eachPath
  putNewline: buffer.appendByte(all, newlineByte)
  afterNewline: newlineNext = math.addInt64(line, 1)
  set line newlineNext
  goto advance
:advance in=eachPath
  countPath: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachPath
:done
  return
:unreadable
  makeUnreadable: unreadableProblem = FileProblem.unreadable(index)
  raise unreadableProblem
:notText
  makeNotText: notTextProblem = FileProblem.notText(index)
  raise notTextProblem

## ---------------------------------------------------------------- diagnostics

op lexRejection "A lexer error as a rejection at the character it concerns"
  input error lexer.LexError copied
  output syntax.Rejection
  let one Int64 1
:begin
  makeKind: kind = syntax.WordKind.name()
  match error
  case invalidByte badAt invalid
  case unterminatedText openAt unterminated
  case integerTooLarge digitsAt tooLarge
:invalid
  makeInvalidWord: invalidWord = syntax.Word.new(kind, badAt, one)
  makeInvalid: invalidRejection = syntax.Rejection.invalidCharacter(invalidWord)
  return invalidRejection
:unterminated
  makeOpenWord: openWord = syntax.Word.new(kind, openAt, one)
  makeUnterminated: unterminatedRejection = syntax.Rejection.unterminatedText(openWord)
  return unterminatedRejection
:tooLarge
  makeDigitsWord: digitsWord = syntax.Word.new(kind, digitsAt, one)
  makeTooLarge: tooLargeRejection = syntax.Rejection.integerTooLarge(digitsWord)
  return tooLargeRejection

op describeRejection "Write a rejection as `path:line:column: message (word)`: the file is the last one whose text starts at or before the word, and the line is counted from that file's first line"
  input files SourceFiles borrowed
  input source String borrowed
  input rejection syntax.Rejection copied
  input region Region borrowed
  output String
  owner region
  let position Int64 0 mut
  let found Int64 0 mut
  let colon Byte 58
  let separator String ": "
  let open String " ("
  let close Byte 41
:begin
  readWord: word = syntax.rejectionWord(rejection)
  readStart: start = syntax.Word.start(word)
  readOffset: offset = string.Position.offset(start)
  readLine: line = string.Position.line(start)
  readColumn: column = string.Position.column(start)
  countFiles: fileCount = SourceFiles.length(files)
  goto eachFile
:eachFile loop=forEach max=fileCount over=files
  next files file readFile located
:readFile in=eachFile
  readFileStart: fileStart = SourceFile.start(file)
  beforeCheck: startsBefore = compare.lessOrEqualInt64(fileStart, offset)
  countFile: nextPosition = math.addInt64(position, 1)
  set position nextPosition
  if startsBefore keepFile eachFile
:keepFile in=eachFile
  readFound: foundAt = math.subtractInt64(position, 1)
  set found foundAt
  goto eachFile
:located
  fetchFile: foundFile = SourceFiles.getOrTrap(files, found)
  readPath: path = SourceFile.path(foundFile)
  readFirstLine: firstLine = SourceFile.line(foundFile)
  lineInFile: fromFirst = math.subtractInt64(line, firstLine)
  localLine: shownLine = math.addInt64(fromFirst, 1)
  readMessage: message = syntax.rejectionMessage(rejection, region)
  newText: text = buffer.new(region)
  putPath: buffer.appendString(text, path)
  putColon: buffer.appendByte(text, colon)
  putLine: buffer.appendInt64(text, shownLine)
  putColon2: buffer.appendByte(text, colon)
  putColumn: buffer.appendInt64(text, column)
  putSeparator: buffer.appendString(text, separator)
  putMessage: buffer.appendString(text, message)
  putOpen: buffer.appendString(text, open)
  putWordText: syntax.putWord(text, source, word)
  putClose: buffer.appendByte(text, close)
  finish: described = buffer.toString(text, region) ? plain
  return described
:plain
  return message

op reportRejection "Write a rejection on standard error as `path:line:column: message (word)`"
  input files SourceFiles borrowed
  input source String borrowed
  input rejection syntax.Rejection copied
  effect write console.stderr
  uses stderrWriter
  region scratch 16777216
:begin
  describe: described = describeRejection(files, source, rejection, scratch)
  writeIt: console.writeError(described) ~ "The exit code already says the program was refused; a lost message does not change it"
  return

op reportProblem "Write a problem on standard error as `<path><what>`"
  input path String borrowed
  input what String borrowed
  effect write console.stderr
  uses stderrWriter
  region scratch 65536
:begin
  join: message = string.concat(path, what, scratch)
  writeIt: console.writeError(message) ~ "The exit code already says what happened; a message that cannot be written changes nothing"
  return

op addExtraArguments "Pass every command-line argument after the compiler's name to the C compiler: the runtime to link (the runtime in SemanticScript as an object), then any flags"
  input arguments process.Arguments borrowedMutable
  input count Int64 copied
  input region Region borrowed
  effect read process.arguments
  uses argumentReader
  let index Int64 3 mut
:begin
  goto eachExtra
:eachExtra loop=while max=count
  doneCheck: allPassed = compare.greaterOrEqualInt64(index, count)
  if allPassed done readExtra
:readExtra in=eachExtra
  readExtraArgument: extra = process.argument(index, region) ? done
  addExtra: process.addArgument(arguments, extra)
  countExtra: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachExtra
:done
  return

## ---------------------------------------------------------------- main

op main "Compile the project named on the command line to C and build it with the C compiler"
  output ExitCode
  effect read process.arguments
  effect write console.stdout
  effect write console.stderr
  effect read fs.files
  effect write fs.files
  effect spawn process.programs
  uses argumentReader
  uses stdoutWriter
  uses stderrWriter
  uses sourceFiles
  uses buildFiles
  uses cCompilers
  async
  region store 17179869184
  let usageText String "usage: refined run <stage0> -- <project> build/<name> [cc|gcc|clang [runtime.o [flags...]]]"
  let defaultCompiler String "gcc"
  let buildName String "/build.sem"
  let cSuffix String ".c"
  let outputFlag String "-o"
  let buildDirectory String "build"
  let notTextText String ": the source is not UTF-8 text"
  let readFailedText String ": cannot read the source file"
  let writeFailedText String ": cannot write the C file"
  let runFailedText String ": the C compiler could not be run"
  let compilerFailedText String ": the C compiler failed"
  let builtLead String "stage0: "
  let builtMiddle String " -> "
  let readLimit Int64 16777216
  let waitMs Int64 600000
  let okCode ExitCode 0
  let refusedCode ExitCode 1
  let usageCode ExitCode 2
  let fileCode ExitCode 3
  let compilerCode ExitCode 4
  let outputCode ExitCode 5
  let compiler String unset mut
  let rejection syntax.Rejection unset mut
  let problemPath String unset mut
  let problemText String unset mut
:begin
  makeDeadline: deadline = time.Deadline.after(waitMs)
  countArguments: argumentCount = process.argumentCount()
  checkCount: tooFew = compare.lessThanInt64(argumentCount, 2)
  if tooFew usage readPaths
:readPaths
  set compiler defaultCompiler
  readProjectPath: projectPath = process.argument(0, store) ? usage
  readOutputName: outputName = process.argument(1, store) ? usage
  checkCompiler: namesCompiler = compare.greaterOrEqualInt64(argumentCount, 3)
  if namesCompiler readCompiler readBuild
:readCompiler
  readCompilerName: compilerName = process.argument(2, store) ? usage
  set compiler compilerName
  goto readBuild
:readBuild
  makeBuildPath: buildPath = string.concat(projectPath, buildName, store)
  newBuildFiles: projectFiles = SourceFiles.new(store)
  makeBuildFile: buildFile = SourceFile.new(buildPath, 0, 1, store)
  addBuildFile: SourceFiles.append(projectFiles, buildFile)
  set problemPath buildPath
  task readBuildFile: buildBytes = fs.readAll(buildPath, store, readLimit, deadline) ? readFailed
  decodeBuild: buildSource = string.fromBytes(buildBytes, store) ? notText
  lexBuild: buildTokens = lexer.tokenize(buildSource, store) ! buildLexError
  iferr lexBuild buildLexFailed groupBuild
:groupBuild
  newBuildWords: buildWords = syntax.Words.new(store)
  newBuildRows: buildRows = syntax.Rows.new(store)
  groupBuildRows: syntax.groupRows(buildSource, buildTokens, buildWords, buildRows) ! buildRowsError
  iferr groupBuildRows buildRowsRefused readProject
:readProject
  newNames: moduleNames = Texts.new(store)
  readModules: entry = projectModules(buildSource, buildWords, buildRows, moduleNames, store) ! projectError
  iferr readModules projectRefused gather
:gather
  newPaths: paths = Texts.new(store)
  makePaths: modulePaths(projectPath, moduleNames, paths, store)
  newFiles: files = SourceFiles.new(store)
  newAll: all = buffer.new(store)
  task gatherAll: gatherSources(paths, files, all, deadline, store) ! gatherError
  iferr gatherAll gatherFailed joined
:joined
  joinSource: source = buffer.toString(all, store) ? notText
  lex: tokens = lexer.tokenize(source, store) ! lexError
  iferr lex lexFailed groupSourceRows
:groupSourceRows
  newWords: words = syntax.Words.new(store)
  newRows: rows = syntax.Rows.new(store)
  groupSource: syntax.groupRows(source, tokens, words, rows) ! rowsError
  iferr groupSource rowsRefused modelSource
:modelSource
  newEntities: entities = model.Entities.new(store)
  newEntityNames: entityNames = model.EntityNames.new(store)
  buildTheModel: model.buildModel(source, words, rows, entities, entityNames) ! modelError
  iferr buildTheModel modelRefused emit
:emit
  newC: cText = buffer.new(store)
  emitTheProgram: emitc.emitProgram(cText, source, words, rows, entities, entry) ! emitError
  iferr emitTheProgram emitRefused save
:save
  makeCPath: cPath = string.concat(outputName, cSuffix, store)
  makeBuildDirectory: fs.createDirectory(buildDirectory) ~ "The directory usually exists already; if it cannot be made, writing the C file into it fails next and is reported there"
  cBytes: cBytesValue = buffer.toBytes(cText)
  set problemPath cPath
  task writeC: fs.writeAll(cPath, cBytesValue, deadline) ? writeFailed
  newArguments: compilerArguments = process.newArguments(store)
  addCPath: process.addArgument(compilerArguments, cPath)
  addOutputFlag: process.addArgument(compilerArguments, outputFlag)
  addOutputName: process.addArgument(compilerArguments, outputName)
  addExtras: addExtraArguments(compilerArguments, argumentCount, store)
  task runCompiler: status = process.run(compiler, compilerArguments, deadline) ? runFailed
  statusValue: statusNumber = convert.exitCodeToInt64(status)
  successCheck: built = compare.equalInt64(statusNumber, 0)
  if built summarize compilerFailed
:summarize
  newSummary: summary = buffer.new(store)
  putLead: buffer.appendString(summary, builtLead)
  putProject: buffer.appendString(summary, projectPath)
  putMiddle: buffer.appendString(summary, builtMiddle)
  putC: buffer.appendString(summary, cPath)
  putMiddle2: buffer.appendString(summary, builtMiddle)
  putOutput: buffer.appendString(summary, outputName)
  finishSummary: summaryText = buffer.toString(summary, store) ? outputFailed
  printIt: console.writeLine(summaryText) ? outputFailed
  return okCode
:usage
  writeUsage: console.writeError(usageText) ~ "The exit code already says what happened; a message that cannot be written changes nothing"
  return usageCode
:readFailed
  set problemText readFailedText
  goto fileProblem
:notText
  set problemText notTextText
  goto fileProblem
:writeFailed
  set problemText writeFailedText
  goto fileProblem
:gatherFailed
  match gatherError
  case unreadable unreadableAt unreadableModule
  case notText notTextAt notTextModule
:unreadableModule
  readUnreadablePath: unreadablePath = Texts.getOrTrap(paths, unreadableAt)
  reportUnreadable: reportProblem(unreadablePath, readFailedText)
  return fileCode
:notTextModule
  readNotTextPath: notTextPath = Texts.getOrTrap(paths, notTextAt)
  reportNotText: reportProblem(notTextPath, notTextText)
  return fileCode
:fileProblem
  reportFile: reportProblem(problemPath, problemText)
  return fileCode
:runFailed
  reportRun: reportProblem(compiler, runFailedText)
  return compilerCode
:compilerFailed
  reportCompiler: reportProblem(cPath, compilerFailedText)
  return compilerCode
:outputFailed
  return outputCode
:buildLexFailed
  convertBuildLex: buildLexRejection = lexRejection(buildLexError)
  set rejection buildLexRejection
  goto buildReport
:buildRowsRefused
  set rejection buildRowsError
  goto buildReport
:projectRefused
  set rejection projectError
  goto buildReport
:buildReport
  reportBuild: reportRejection(projectFiles, buildSource, rejection)
  return refusedCode
:lexFailed
  convertLex: lexRejectionValue = lexRejection(lexError)
  set rejection lexRejectionValue
  goto report
:rowsRefused
  set rejection rowsError
  goto report
:modelRefused
  set rejection modelError
  goto report
:emitRefused
  set rejection emitError
  goto report
:report
  reportIt: reportRejection(files, source, rejection)
  return refusedCode
