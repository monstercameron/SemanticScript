module subset "Check that a program is in the stage0 subset and collect what the emitter needs"
  path subset
  imports standard.string standard.list standard.map standard.math standard.compare standard.logic standard.test lexer syntax model
  exports LiteralKind TypeInfo Types TypeNames MemberInfo Members ParamInfo Params TargetKind TargetInfo Targets OpInfo Ops OpNames Owners ValueInfo Values CallInfo Calls ArgumentInfo Arguments LabelInfo Labels StepVerb Step Steps declareBuiltins nextModule checkModuleDeclarations checkOperation checkProgram diagnose

## ---------------------------------------------------------------- what the subset reads

enum LiteralKind "Which literals a type takes"
  variant text
  variant integer
  variant exitCode
  variant flag
  variant byte
  variant noLiteral

record TypeRow "A built-in type the subset compiles, numbered by its row: its name, the literals it takes, whether it is a plain value, and its kind (1 built in, 2 the standard errors, whose row has a name no word spells)"
  field text String
  field literal LiteralKind
  field plain Bool
  field kind Int64

enum Predicate "What a row states, by its predicate"
  variant contextRow
  variant pathRow
  variant importsRow
  variant exportsRow
  variant grantsRow
  variant typeParameterRow
  variant fieldRow
  variant variantRow
  variant inRow
  variant instantiatesRow
  variant typeRow
  variant valueRow
  variant inputRow
  variant outputRow
  variant outputOwnedByRow
  variant raisesRow
  variant effectRow
  variant usesRow
  variant memoryHeapRow
  variant asyncRow
  variant maxRecursionRow
  variant labelRow
  variant letRow
  variant atRow
  variant invokesRow
  variant invokesReferenceRow
  variant argumentRow
  variant resultRow
  variant ownedByRow
  variant cleanedByRow
  variant borrowsRow
  variant catchRow
  variant suppressesRow
  variant strategyRow
  variant maxBytesRow
  variant releasedRow
  variant rowTypeRow
  variant rowRow
  variant cellRow

record PredicateRow "A predicate word and what it states"
  field text String
  field predicate Predicate

enum StepVerb "What a step does"
  variant doCall
  variant setValue
  variant jump
  variant branchIf
  variant branchIfError
  variant branchIfNext
  variant matchValue
  variant caseOf
  variant returnOk
  variant returnError
  variant startTask
  variant joinTask

record StepRow "A step word and the verb it begins"
  field text String
  field verb StepVerb

enum LabelFact "What a label row states, as far as the emitter cares"
  variant loopKind
  variant within
  variant maxIterations
  variant over
  variant other

record FactRow "A label fact word and what it states"
  field text String
  field fact LabelFact

record LoopRow "A loop kind word and its number"
  field text String
  field number Int64

enum TargetKind "What a call target is"
  variant builtin
  variant operation
  variant recordNew
  variant fieldRead
  variant variantMake
  variant listNew
  variant listAppend
  variant listLength
  variant listGet
  variant listGetOrTrap
  variant tableRowAt
  variant tableLength
  variant listSet
  variant mapNew
  variant mapPut
  variant mapGet
  variant mapContains
  variant mapRemove
  variant mapLength
  variant reference
  variant recordWith

record BuiltinRow "A standard library target the subset compiles: up to four argument slots with their types (numbered as the types table numbers them; 12 is string.Position, the first type the program declares) and passing modes (1 copy, 2 lend, 3 lendMutable, 4 give), its result type (0 for none), and its error (raises 7, a standard error, with the error type's name; 0 when it cannot fail)"
  field text String
  field count Int64
  field slot1 String
  field type1 Int64
  field mode1 Int64
  field slot2 String
  field type2 Int64
  field mode2 Int64
  field slot3 String
  field type3 Int64
  field mode3 Int64
  field slot4 String
  field type4 Int64
  field mode4 Int64
  field output Int64
  field raises Int64
  field error String

%%TABLES%%

## ---------------------------------------------------------------- what the checker collects

record TypeInfo "A type: built in (codes 1 to 11, 7 the standard errors), or declared by a module of the program (12 on), with the module's name. kind: 1 built in, 2 standard error, 3 record, 4 enum, 5 list, 6 table, 7 map, 8 operationType. A list keeps its item type, a table its row type, a map its key type and value type, and an operationType its output; a record or enum its first member and how many it has, a table its entity's position and how many rows it has, an operationType its first slot and how many it has, and what it raises; an enum whether it is narrow (stored as a tag and one Int64) and whether no variant carries a payload. slots: how many 64-bit slots a value takes when it is passed to the host, as the LLVM backend flattens it"
  field name syntax.Word
  field module syntax.Word
  field kind Int64
  field item Int64
  field value Int64
  field plain Bool
  field holdsText Bool
  field narrow Bool
  field tagOnly Bool
  field first Int64
  field count Int64
  field raises Int64
  field slots Int64

instance Types "Every type, numbered from 1 by its position" list.List TypeInfo

instance TypeNames "The number of every type by its name" map.Map String Int64

record MemberInfo "A field of a record or a variant of an enum: the type it belongs to, its name, its type (0 for a variant without payload), its position among the type's members from 0 (a variant's tag), and for a variant with a payload its position among those, from 1"
  field owner Int64
  field name syntax.Word
  field type Int64
  field index Int64
  field slot Int64

instance Members "The fields and variants of every record and enum, each type's together" list.List MemberInfo

record ParamInfo "One argument slot of a call target: its name, type, and passing mode (1 copy, 2 lend, 3 lendMutable, 4 give)"
  field slot String
  field type Int64
  field mode Int64

instance Params "The argument slots of every call target, each target's together" list.List ParamInfo

record TargetInfo "A call target: what it is, the builtin row, operation, or type it belongs to, the member it reads or makes, its slots, its result type (0 for none), and what it raises (0 nothing, 7 a standard error, else an enum's type)"
  field kind TargetKind
  field owner Int64
  field member Int64
  field firstParam Int64
  field paramCount Int64
  field output Int64
  field raises Int64

instance Targets "Every call target the module may invoke, by its name" map.Map String TargetInfo

record OpInfo "An operation of the program: its name, its module's name and the module's entities (first, and one past the last), its entity's position, its slots in params, its output and error types (0 for none), the region input its output is owned by, and its maxRecursion bound when it recurses"
  field name syntax.Word
  field module syntax.Word
  field moduleFirst Int64
  field moduleEnd Int64
  field entity Int64
  field firstParam Int64
  field paramCount Int64
  field output Int64
  field raises Int64
  field owner syntax.Word
  field owned Bool
  field depth syntax.Word
  field recursive Bool

instance Ops "Every operation of the module, in source order" list.List OpInfo

instance OpNames "The position of every operation by its name" map.Map String Int64

instance Owners "For each entity, the position of the operation it belongs to (a call or region), or -1" list.List Int64

record ValueInfo "A value of an operation: its name, type, whether `set` may change it, where it comes from (1 constant, 2 let, 3 call result, 4 input, 5 bound by a step, 6 caught error, 7 region), the word that sets it first (a region's maxBytes), and whether a region is released at return"
  field name syntax.Word
  field code Int64
  field mutable Bool
  field origin Int64
  field init syntax.Word
  field initIsName Bool
  field initialized Bool
  field released Bool

instance Values "Every value by name, in the order they are declared" map.Map String ValueInfo

record CallInfo "A call of an operation: its name, its target, the value of an operationType it calls through (`invokesReference`) or the field a record's `with` changes (its name otherwise), where its arguments start in the argument list and how many, the value it sets, and the name its error is caught as"
  field name syntax.Word
  field target TargetInfo
  field reference syntax.Word
  field firstArgument Int64
  field arity Int64
  field result syntax.Word
  field hasResult Bool
  field catchName syntax.Word
  field hasCatch Bool

instance Calls "Every call of an operation by name, in source order" map.Map String CallInfo

record ArgumentInfo "A value a call passes, and the type its slot takes"
  field value syntax.Word
  field code Int64

instance Arguments "The arguments of every call of an operation, each call's together" list.List ArgumentInfo

record LabelInfo "A label of an operation: its loop kind (0 none, 1 while, 2 doWhile, 3 counted, 4 forever, 5 forEach), the loop it is within, its maxIterations bound, and what a forEach loop reads"
  field name syntax.Word
  field kind Int64
  field within syntax.Word
  field nested Bool
  field bound syntax.Word
  field bounded Bool
  field over syntax.Word

instance Labels "Every label of an operation by name" map.Map String LabelInfo

record Step "One checked step: its label, its verb, and the words it names (the label word where a verb names fewer); a case keeps the member it matches and the type it binds (0 for none)"
  field label syntax.Word
  field verb StepVerb
  field subject syntax.Word
  field target syntax.Word
  field otherwise syntax.Word
  field extra syntax.Word
  field number Int64
  field code Int64

instance Steps "The steps of an operation in source order" list.List Step

instance Blocks "The labels whose steps have been seen, while steps are checked" map.Map String Int64

%%LOOKUPS%%

## ---------------------------------------------------------------- small checks

op wordAt "Read the word at an offset in a row (0 is the subject)"
  input words syntax.Words borrowed
  input row syntax.Row copied
  input offset Int64 copied
  output syntax.Word
:begin
  readFirst: first = syntax.Row.first(row)
  findIndex: index = math.addInt64(first, offset)
  readWord: word = syntax.Words.getOrTrap(words, index)
  return word

op expectCount "Refuse a row that does not have the number of words its shape in the subset has, at a word of it"
  input row syntax.Row copied
  input count Int64 copied
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  readCount: actual = syntax.Row.count(row)
  countCheck: fits = compare.equalInt64(actual, count)
  if fits done wrongShape
:done
  return
@reject unsupportedPayload word wrongShape

op expectAtLeast "Refuse a row with fewer words than a shape of the subset needs, at a word of it"
  input row syntax.Row copied
  input count Int64 copied
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  readCount: actual = syntax.Row.count(row)
  countCheck: fits = compare.greaterOrEqualInt64(actual, count)
  if fits done wrongShape
:done
  return
@reject unsupportedPayload word wrongShape

op checkWord "Refuse a row whose payload is not exactly the one word the subset fixes for its predicate"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input text String borrowed
  raises syntax.Rejection
:begin
  @wordAt payload 2
  shape: expectCount(row, 3, payload) ?^
  sameCheck: same = syntax.isText(source, payload, text) ?^
  if same done different
:done
  return
@reject unsupportedPayload payload different

op isWord "Decide whether a word spells a text"
  input source String borrowed
  input word syntax.Word copied
  input text String borrowed
  output Bool
  raises syntax.Rejection
:begin
  sameCheck: same = syntax.isText(source, word, text) ?^
  return same

op findType "Find the type a word names: a built-in type or one the module declares"
  input source String borrowed
  input typeNames TypeNames borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
:begin
  @view text word outside
  getCode: code = TypeNames.get(typeNames, text) ? missing
  return code
@reject unsupportedType word missing
@reject outsideSource word outside

op findValue "Find a value of an operation, or a module constant, by the name a word spells"
  input source String borrowed
  input values Values borrowed
  input constants Values borrowed
  input word syntax.Word copied
  output ValueInfo
  raises syntax.Rejection
:begin
  @view text word outside
  getValue: info = Values.get(values, text) ? tryConstant
  return info
:tryConstant
  getConstant: constantInfo = Values.get(constants, text) ? unknown
  return constantInfo
@reject unknownValue word unknown
@reject outsideSource word outside

op knowsValue "Decide whether a word names a value of an operation or a module constant"
  input source String borrowed
  input values Values borrowed
  input constants Values borrowed
  input word syntax.Word copied
  output Bool
  raises syntax.Rejection
:begin
  @view text word outside
  hasValue: inValues = Values.contains(values, text)
  hasConstant: inConstants = Values.contains(constants, text)
  eitherCheck: known = logic.or(inValues, inConstants)
  return known
@reject outsideSource word outside

op requireNewValue "Refuse a name already used by a value of the operation or by a module constant"
  input source String borrowed
  input values Values borrowed
  input constants Values borrowed
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  knownCheck: taken = knowsValue(source, values, constants, word) ?^
  if taken duplicate done
:done
  return
@reject duplicateName word duplicate

op enterValue "Enter a value of an operation under its name"
  input source String borrowed
  input values Values borrowedMutable
  input info ValueInfo copied
  raises syntax.Rejection
:begin
  readName: name = ValueInfo.name(info)
  @view text name outside
  putValue: Values.put(values, text, info)
  return
@reject outsideSource name outside

op typeInfoOf "Read the facts of a type by its number"
  input types Types borrowed
  input code Int64 copied
  output TypeInfo
:begin
  findIndex: index = math.subtractInt64(code, 1)
  readInfo: info = Types.getOrTrap(types, index)
  return info

op slotsOf "How many 64-bit slots a value of a type takes when it is passed to the host, as the LLVM backend flattens it: two for String and Bytes (a pointer and a length), one for any other built-in type, and what a declared type worked out when it was declared"
  input types Types borrowed
  input code Int64 copied
  output Int64
  let one Int64 1
  let two Int64 2
:begin
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText text notText
:text
  return two
:notText
  builtinCheck: isBuiltin = compare.lessOrEqualInt64(code, 11)
  if isBuiltin single declared
:single
  return one
:declared
  readInfo: info = typeInfoOf(types, code)
  readSlots: slots = TypeInfo.slots(info)
  return slots

op declareBuiltins "Number the built-in types 1 to 11 and enter every standard library target of the subset as a call target, once for the whole program"
  invariant numbersBuiltins "The built-in types are numbered 1 to 11 in the order of the builtinTypes table, each entered under its name, and every target of builtinTargets is a call target under its own name"
  input source String borrowed
  input types Types borrowedMutable
  input typeNames TypeNames borrowedMutable
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let no Bool false
:begin
  makePlaceholder: placeholder = placeholderWord()
  goto eachBuiltin
:eachBuiltin loop=forEach max=11 over=builtinTypes
  next builtinTypes typeRow enterBuiltin builtinsDone
:enterBuiltin in=eachBuiltin
  readBuiltinText: builtinText = TypeRow.text(typeRow)
  readBuiltinPlain: builtinPlain = TypeRow.plain(typeRow)
  readBuiltinKind: builtinKind = TypeRow.kind(typeRow)
  countBefore: before = Types.length(types)
  findCode: builtinCode = math.addInt64(before, 1)
  slotsCheck: builtinSlots = slotsOf(types, builtinCode)
  makeBuiltin: builtin = TypeInfo.new(placeholder, placeholder, builtinKind, 0, 0, builtinPlain, no, no, no, 0, 0, 0, builtinSlots)
  appendBuiltin: Types.append(types, builtin)
  putBuiltin: TypeNames.put(typeNames, builtinText, builtinCode)
  goto eachBuiltin
:builtinsDone
  enterBuiltins: registerBuiltins(source, params, targets, region) ?^
  return

op isStandardError "Decide whether a word names an error type of the standard library the subset compiles: the error of a builtin target, list.IndexOutOfRange, or map.KeyMissing"
  input source String borrowed
  input word syntax.Word copied
  output Bool
  raises syntax.Rejection
  let yes Bool true
  let no Bool false
:begin
  listCheck: isList = syntax.isText(source, word, indexError="list.IndexOutOfRange") ?^
  mapCheck: isMap = syntax.isText(source, word, keyError="map.KeyMissing") ?^
  collectionCheck: isCollection = logic.or(isList, isMap)
  if isCollection found scan
:scan
  goto eachTarget
:eachTarget loop=forEach max=%%BUILTIN_COUNT%% over=builtinTargets
  next builtinTargets entry readEntry missing
:readEntry in=eachTarget
  readError: error = BuiltinRow.error(entry)
  sameCheck: same = syntax.isText(source, word, error) ?^
  if same found eachTarget
:found
  return yes
:missing
  return no

op findRaises "Find the error type a raises row names: a type the program declares, or an error of the standard library, which are all type 7 (a standard error is only branched on or passed on, never matched)"
  input source String borrowed
  input typeNames TypeNames borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
  let seven Int64 7
:begin
  @view text word outside
  getCode: code = TypeNames.get(typeNames, text) ? standardCheck
  return code
:standardCheck
  standardTest: isStandard = isStandardError(source, word) ?^
  if isStandard standard unknown
:standard
  return seven
@reject unsupportedType word unknown
@reject outsideSource word outside

op hexEscaped "Decide whether quoted text holds a `\\x` escape: a backslash that is not itself escaped, followed by x"
  input text String borrowed
  output Bool
  let index Int64 0 mut
  let yes Bool true
  let no Bool false
  let backslash Byte 92
  let lowerX Byte 120
:begin
  measure: length = string.byteLength(text)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: allRead = compare.greaterOrEqualInt64(index, length)
  if allRead clean readByte
:readByte in=eachByte
  fetch: byte = string.byteAtOrTrap(text, index)
  stepIndex: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  escapeCheck: isEscape = compare.equalByte(byte, backslash)
  if isEscape readEscaped eachByte
:readEscaped in=eachByte
  endCheck: atEnd = compare.greaterOrEqualInt64(index, length)
  if atEnd clean readNext
:readNext in=eachByte
  fetchNext: escaped = string.byteAtOrTrap(text, index)
  skipIndex: afterEscape = math.addInt64(index, 1)
  set index afterEscape
  hexCheck: isHex = compare.equalByte(escaped, lowerX)
  if isHex found eachByte
:found
  return yes
:clean
  return no

op literalFits "Refuse a literal that does not fit the type whose literals are given"
  input source String borrowed
  input word syntax.Word copied
  input literal LiteralKind copied
  raises syntax.Rejection
  let maxSmall Int64 255
:begin
  readKind: wordKind = syntax.Word.kind(word)
  match literal
  case text wantText
  case integer wantInteger
  case exitCode wantSmall
  case flag wantFlag
  case byte wantSmall
  case noLiteral bad
:wantText
  match wordKind
  case name bad
  case integer textNumber bad
  case text escapeCheck
:escapeCheck
  @view wordText word outside
  hexCheck: hasHex = hexEscaped(wordText)
  if hasHex escaped fits
:wantInteger
  match wordKind
  case name bad
  case integer integerNumber fits
  case text bad
:wantSmall
  match wordKind
  case name bad
  case integer small rangeCheck
  case text bad
:rangeCheck
  lowCheck: tooLow = compare.lessThanInt64(small, 0)
  highCheck: tooHigh = compare.greaterThanInt64(small, maxSmall)
  outsideCheck: outOfRange = logic.or(tooLow, tooHigh)
  if outOfRange bad fits
:wantFlag
  trueCheck: isTrue = syntax.isText(source, word, trueWord="true") ?^
  falseCheck: isFalse = syntax.isText(source, word, falseWord="false") ?^
  flagCheck: isFlag = logic.or(isTrue, isFalse)
  if isFlag fits bad
:fits
  return
@reject badLiteral word bad
@reject unsupportedEscape word escaped
@reject outsideSource word outside

op literalOf "The literals a type takes: a built-in type's from its row, none for any other"
  input code Int64 copied
  output LiteralKind
:begin
  readRow: entry = builtinTypes.rowAt(code) ? declared
  readLiteral: literal = TypeRow.literal(entry)
  return literal
:declared
  makeNone: noLiteral = LiteralKind.noLiteral()
  return noLiteral

op modeOf "The number of a passing mode word: 1 copy, 2 lend, 3 lendMutable, 4 give"
  input source String borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
  let one Int64 1
  let two Int64 2
  let three Int64 3
  let four Int64 4
:begin
  copyCheck: isCopy = syntax.isText(source, word, copyWord="copy") ?^
  if isCopy copy notCopy
:notCopy
  lendCheck: isLend = syntax.isText(source, word, lendWord="lend") ?^
  if isLend lend notLend
:notLend
  mutableCheck: isLendMutable = syntax.isText(source, word, lendMutableWord="lendMutable") ?^
  if isLendMutable lendMutable notLendMutable
:notLendMutable
  giveCheck: isGive = syntax.isText(source, word, giveWord="give") ?^
  if isGive give bad
:copy
  return one
:lend
  return two
:lendMutable
  return three
:give
  return four
@reject unsupportedPayload word bad

op inputModeOf "The argument mode an input mode word asks of a caller: copied 1, borrowed 2, borrowedMutable 3 (owned inputs are outside the subset)"
  input source String borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
  let one Int64 1
  let two Int64 2
  let three Int64 3
:begin
  copiedCheck: isCopied = syntax.isText(source, word, copiedWord="copied") ?^
  if isCopied copied notCopied
:notCopied
  borrowedCheck: isBorrowed = syntax.isText(source, word, borrowedWord="borrowed") ?^
  if isBorrowed borrowed notBorrowed
:notBorrowed
  mutableCheck: isMutable = syntax.isText(source, word, mutableWord="borrowedMutable") ?^
  if isMutable borrowedMutable bad
:copied
  return one
:borrowed
  return two
:borrowedMutable
  return three
@reject unsupportedPayload word bad

op readMode "The mode a slot of a type takes when it only reads the value: copy for a plain value, lend otherwise"
  input types Types borrowed
  input code Int64 copied
  output Int64
  let one Int64 1
  let two Int64 2
:begin
  readInfo: info = typeInfoOf(types, code)
  readPlain: plain = TypeInfo.plain(info)
  if plain copy lend
:copy
  return one
:lend
  return two

op ownMode "The mode a slot of a type takes when it keeps the value: copy for a plain value, give otherwise"
  input types Types borrowed
  input code Int64 copied
  output Int64
  let one Int64 1
  let four Int64 4
:begin
  readInfo: info = typeInfoOf(types, code)
  readPlain: plain = TypeInfo.plain(info)
  if plain copy give
:copy
  return one
:give
  return four

op placeholderWord "A word that names nothing, for values that have no word yet"
  output syntax.Word
:begin
  makeKind: kind = syntax.WordKind.name()
  makeOrigin: origin = string.Position.new(0, 1, 1)
  makeWord: word = syntax.Word.new(kind, origin, 0)
  return word

op memberKey "The name a type's member is invoked by: `<Type>.<member>`"
  input source String borrowed
  input typeName syntax.Word copied
  input member String borrowed
  input region Region borrowed
  output String
  owner region
  raises syntax.Rejection
:begin
  copyName: nameText = syntax.wordText(source, typeName, region) ?^
  addDot: dotted = string.concat(nameText, dot=".", region)
  addMember: key = string.concat(dotted, member, region)
  return key

op addParam "Add one argument slot to the slot list"
  input params Params borrowedMutable
  input slot String borrowed
  input type Int64 copied
  input mode Int64 copied
  input region Region borrowed
:begin
  makeParam: param = ParamInfo.new(slot, type, mode, region)
  appendParam: Params.append(params, param)
  return

op putTarget "Enter a call target under its name, refusing a name entered before"
  input source String borrowed
  input targets Targets borrowedMutable
  input key String borrowed
  input info TargetInfo copied
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  takenCheck: taken = Targets.contains(targets, key)
  if taken duplicate enter
:enter
  putIt: Targets.put(targets, key, info)
  return
@reject duplicateName word duplicate

## ---------------------------------------------------------------- declarations: types and operations by name

op declareNames "Number every record, enum, typeInstance, table, and operationType of one module after the types already numbered, in source order, and every operation after the operations already known"
  input source String borrowed
  input entities model.Entities borrowed
  input first Int64 copied
  input end Int64 copied
  input module syntax.Word copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowedMutable
  input opNames OpNames borrowedMutable
  input opBase Int64 copied
  input region Region borrowed
  raises syntax.Rejection
  let index Int64 0 mut
  let operationCount Int64 0 mut
  let typeKind Int64 0 mut
  let three Int64 3
  let four Int64 4
  let five Int64 5
  let six Int64 6
  let eight Int64 8
  let no Bool false
:begin
  set index first
  set operationCount opBase
  findSpan: span = math.subtractInt64(end, first)
  goto eachEntity
:eachEntity loop=while max=span
  doneCheck: allDone = compare.greaterOrEqualInt64(index, end)
  if allDone done readEntity
:readEntity in=eachEntity
  readTheEntity: entity = model.Entities.getOrTrap(entities, index)
  countIndex: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  readKind: kind = model.Entity.kind(entity)
  readName: name = model.Entity.name(entity)
  operationCheck: isOperation = compare.equalInt64(kind, 4)
  if isOperation numberOperation typeCheck
:numberOperation in=eachEntity
  copyOperationName: operationText = syntax.wordText(source, name, region) ?^
  putOperation: OpNames.put(opNames, operationText, operationCount)
  countOperation: nextCount = math.addInt64(operationCount, 1)
  set operationCount nextCount
  goto eachEntity
:typeCheck in=eachEntity
  recordCheck: isRecord = compare.equalInt64(kind, 6)
  enumCheck: isEnum = compare.equalInt64(kind, 7)
  listCheck: isList = compare.equalInt64(kind, 8)
  tableCheck: isTable = compare.equalInt64(kind, 11)
  referenceCheck: isReference = compare.equalInt64(kind, 12)
  eitherCheck: recordOrEnum = logic.or(isRecord, isEnum)
  listOrTable: collection = logic.or(isList, isTable)
  anyCheck: isStored = logic.or(recordOrEnum, collection)
  referenceToo: isType = logic.or(isStored, isReference)
  if isType numberType eachEntity
:numberType in=eachEntity
  copyTypeName: typeText = syntax.wordText(source, name, region) ?^
  takenCheck: taken = TypeNames.contains(typeNames, typeText)
  if taken duplicate kindRecord
:kindRecord in=eachEntity
  set typeKind three
  if isRecord enterType kindEnum
:kindEnum in=eachEntity
  set typeKind four
  if isEnum enterType kindList
:kindList in=eachEntity
  set typeKind five
  if isList enterType kindTable
:kindTable in=eachEntity
  set typeKind six
  if isTable enterType kindReference
:kindReference in=eachEntity
  set typeKind eight
  goto enterType
:enterType in=eachEntity
  makeType: typeInfo = TypeInfo.new(name, module, typeKind, 0, 0, no, no, no, no, 0, 0, 0, 1)
  appendType: Types.append(types, typeInfo)
  countTypes: typeCode = Types.length(types)
  putType: TypeNames.put(typeNames, typeText, typeCode)
  goto eachEntity
:done
  return
@reject duplicateName name duplicate

op registerBuiltins "Enter every standard library target of the subset as a call target, with its slots"
  input source String borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let row Int64 0 mut
:begin
  makePlaceholder: placeholder = placeholderWord()
  goto eachTarget
:eachTarget loop=forEach max=%%BUILTIN_COUNT%% over=builtinTargets
  next builtinTargets entry readEntry done
:readEntry in=eachTarget
  countRow: nextRow = math.addInt64(row, 1)
  set row nextRow
  firstCheck: firstParam = Params.length(params)
  readCount: count = BuiltinRow.count(entry)
  hasOneCheck: hasOne = compare.greaterThanInt64(count, 0)
  if hasOne addFirst register
:addFirst in=eachTarget
  readSlot1: slot1 = BuiltinRow.slot1(entry)
  readType1: type1 = BuiltinRow.type1(entry)
  readMode1: mode1 = BuiltinRow.mode1(entry)
  addSlot1: addParam(params, slot1, type1, mode1, region)
  hasTwoCheck: hasTwo = compare.greaterThanInt64(count, 1)
  if hasTwo addSecond register
:addSecond in=eachTarget
  readSlot2: slot2 = BuiltinRow.slot2(entry)
  readType2: type2 = BuiltinRow.type2(entry)
  readMode2: mode2 = BuiltinRow.mode2(entry)
  addSlot2: addParam(params, slot2, type2, mode2, region)
  hasThreeCheck: hasThree = compare.greaterThanInt64(count, 2)
  if hasThree addThird register
:addThird in=eachTarget
  readSlot3: slot3 = BuiltinRow.slot3(entry)
  readType3: type3 = BuiltinRow.type3(entry)
  readMode3: mode3 = BuiltinRow.mode3(entry)
  addSlot3: addParam(params, slot3, type3, mode3, region)
  hasFourCheck: hasFour = compare.greaterThanInt64(count, 3)
  if hasFour addFourth register
:addFourth in=eachTarget
  readSlot4: slot4 = BuiltinRow.slot4(entry)
  readType4: type4 = BuiltinRow.type4(entry)
  readMode4: mode4 = BuiltinRow.mode4(entry)
  addSlot4: addParam(params, slot4, type4, mode4, region)
  goto register
:register in=eachTarget
  readText: text = BuiltinRow.text(entry)
  readOutput: output = BuiltinRow.output(entry)
  readRaises: raises = BuiltinRow.raises(entry)
  makeKind: kind = TargetKind.builtin()
  makeTarget: target = TargetInfo.new(kind, row, 0, firstParam, count, output, raises)
  enterTarget: putTarget(source, targets, text, target, placeholder) ?^
  goto eachTarget
:done
  return

## ---------------------------------------------------------------- declarations, kind by kind

op declareModule "Check the rows of the module entity"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  raises syntax.Rejection
:begin
  @rowsBegin
  case contextRow nextRow
  case pathRow nextRow
  case importsRow nextRow
  case exportsRow nextRow
  others refuse
:finish
  return
@rowsNext

op declareCapability "Check the rows of a capability"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  raises syntax.Rejection
:begin
  @rowsBegin
  case contextRow nextRow
  case grantsRow nextRow
  others refuse
:finish
  return
@rowsNext

op declareConstant "Check a module constant: a built-in type with a literal that fits it; enter it as a value every operation reads"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input typeNames TypeNames borrowed
  input constants Values borrowedMutable
  raises syntax.Rejection
  let typeWord syntax.Word unset mut
  let valueWord syntax.Word unset mut
  let no Bool false
  let yes Bool true
:begin
  readName: name = model.Entity.name(entity)
  set typeWord name
  set valueWord name
  @rowsBegin
  case contextRow nextRow
  case typeRow typeFact
  case valueRow valueFact
  others refuse
:typeFact in=eachRow
  @wordAt typePayload 2
  typeShape: expectCount(row, 3, typePayload) ?^
  set typeWord typePayload
  goto nextRow
:valueFact in=eachRow
  @wordAt valuePayload 2
  valueShape: expectCount(row, 3, valuePayload) ?^
  set valueWord valuePayload
  goto nextRow
:finish
  findCode: code = findType(source, typeNames, typeWord) ?^
  readLiteral: literal = literalOf(code)
  checkLiteral: literalFits(source, valueWord, literal) ?^
  @view nameText name outside
  takenCheck: taken = Values.contains(constants, nameText)
  if taken duplicate enter
:enter
  makeInfo: info = ValueInfo.new(name, code, no, 1, valueWord, no, yes, no)
  enterConstant: enterValue(source, constants, info) ?^
  return
@reject duplicateName name duplicate
@reject outsideSource name outside
@rowsNext

op declareRecord "Check a record's fields, number them as members, and enter its constructor and field readers as call targets"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input code Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowed
  input members Members borrowedMutable
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let index Int64 0 mut
  let slots Int64 0 mut
  let plain Bool true mut
  let holdsText Bool false mut
  let no Bool false
:begin
  readName: name = model.Entity.name(entity)
  firstCheck: firstMember = Members.length(members)
  @rowsBegin
  case contextRow nextRow
  case typeParameterRow noParameter
  case fieldRow field
  others refuse
:noParameter in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:field in=eachRow
  @wordAt fieldName 2
  fieldShape: expectCount(row, 4, fieldName) ?^
  @wordAt fieldType 3
  findFieldType: fieldCode = findType(source, typeNames, fieldType) ?^
  checkOrder: orderFits(types, code, fieldCode, fieldType) ?^
  readFieldInfo: fieldInfo = typeInfoOf(types, fieldCode)
  readFieldPlain: fieldPlain = TypeInfo.plain(fieldInfo)
  bothPlain: stillPlain = logic.and(plain, fieldPlain)
  set plain stillPlain
  textCheck: fieldHoldsText = holdsTextOf(types, fieldCode)
  eitherText: stillText = logic.or(holdsText, fieldHoldsText)
  set holdsText stillText
  fieldSlotsCheck: fieldSlots = slotsOf(types, fieldCode)
  addSlots: nextSlots = math.addInt64(slots, fieldSlots)
  set slots nextSlots
  makeMember: member = MemberInfo.new(code, fieldName, fieldCode, index, 0)
  appendMember: Members.append(members, member)
  countMember: nextMember = math.addInt64(index, 1)
  set index nextMember
  goto nextRow
:finish
  readOld: old = typeInfoOf(types, code)
  readModule: module = TypeInfo.module(old)
  makeInfo: info = TypeInfo.new(name, module, 3, 0, 0, plain, holdsText, no, no, firstMember, index, 0, slots)
  findIndex: typeIndex = math.subtractInt64(code, 1)
  setInfo: Types.set(types, typeIndex, info) ! setInfoError
  iferr setInfo lost registered
:registered
  registerTargets: registerRecord(source, code, types, members, params, targets, region) ?^
  return
@reject lostName name lost
@rowsNext

op orderFits "Refuse a record field, enum payload, list item, or map value whose type is a record or enum declared at or below the type holding it, or a type no value may hold: a list, a map, an operationType, a region, or a standard error"
  input types Types borrowed
  input code Int64 copied
  input heldCode Int64 copied
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  readHeld: held = typeInfoOf(types, heldCode)
  readKind: kind = TypeInfo.kind(held)
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  listCheck: isList = compare.equalInt64(kind, 5)
  mapCheck: isMap = compare.equalInt64(kind, 7)
  referenceCheck: isReference = compare.equalInt64(kind, 8)
  errorCheck: isError = compare.equalInt64(kind, 2)
  regionCheck: isRegion = compare.equalInt64(heldCode, 6)
  collectionCheck: isCollection = logic.or(isList, isMap)
  if isCollection unsupported notCollection
:notCollection
  if isReference unsupported notReference
:notReference
  if isError unsupported notError
:notError
  if isRegion unsupported notRegion
:notRegion
  eitherCheck: byValue = logic.or(isRecord, isEnum)
  laterCheck: later = compare.greaterOrEqualInt64(heldCode, code)
  bothCheck: misordered = logic.and(byValue, later)
  if misordered order fits
:fits
  return
@reject typeOrder word order
@reject unsupportedType word unsupported

op holdsTextOf "Decide whether a value of a type holds text (String or Bytes), directly or through record fields and enum payloads"
  input types Types borrowed
  input code Int64 copied
  output Bool
  let yes Bool true
:begin
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText text other
:text
  return yes
:other
  readInfo: info = typeInfoOf(types, code)
  readHolds: holds = TypeInfo.holdsText(info)
  return holds

op registerRecord "Enter a record's constructor (its fields in order, then a region when it holds a value that is not plain), a reader for each field, and `with`, which copies a record with one field changed (its second slot is named by the field)"
  input source String borrowed
  input code Int64 copied
  input types Types borrowed
  input members Members borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  readInfo: info = typeInfoOf(types, code)
  readName: name = TypeInfo.name(info)
  readFirst: first = TypeInfo.first(info)
  readCount: count = TypeInfo.count(info)
  readPlain: plain = TypeInfo.plain(info)
  firstCheck: firstParam = Params.length(params)
  goto eachField
:eachField loop=while max=count
  doneCheck: fieldsDone = compare.greaterOrEqualInt64(index, count)
  if fieldsDone constructor addField
:addField in=eachField
  findMember: memberIndex = math.addInt64(first, index)
  readMember: member = Members.getOrTrap(members, memberIndex)
  readMemberName: memberName = MemberInfo.name(member)
  readMemberType: memberType = MemberInfo.type(member)
  copyMemberName: memberText = syntax.wordText(source, memberName, region) ?^
  modeCheck: memberMode = readMode(types, memberType)
  addMemberParam: addParam(params, memberText, memberType, memberMode, region)
  countField: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachField
:constructor
  if plain registerNew regionSlotNeeded
:regionSlotNeeded
  addRegionParam: addParam(params, regionSlot="region", 6, 2, region)
  goto registerNew
:registerNew
  lastCheck: lastParam = Params.length(params)
  countParams: paramCount = math.subtractInt64(lastParam, firstParam)
  newKey: key = memberKey(source, name, newWord="new", region) ?^
  makeKind: kind = TargetKind.recordNew()
  makeTarget: target = TargetInfo.new(kind, code, 0, firstParam, paramCount, code, 0)
  enterNew: putTarget(source, targets, key, target, name) ?^
  set index zero
  recordModeCheck: recordMode = readMode(types, code)
  goto eachReader
:eachReader loop=while max=count
  readersDone: allRead = compare.greaterOrEqualInt64(index, count)
  if allRead done addReader
:addReader in=eachReader
  findReaderMember: readerIndex = math.addInt64(first, index)
  readReaderMember: readerMember = Members.getOrTrap(members, readerIndex)
  readReaderName: readerName = MemberInfo.name(readerMember)
  readReaderType: readerType = MemberInfo.type(readerMember)
  readerFirst: readerParam = Params.length(params)
  addRecordParam: addParam(params, recordSlot="record", code, recordMode, region)
  copyReaderName: readerText = syntax.wordText(source, readerName, region) ?^
  readerKey: fieldKey = memberKey(source, name, readerText, region) ?^
  makeReaderKind: readerKind = TargetKind.fieldRead()
  makeReader: reader = TargetInfo.new(readerKind, code, readerIndex, readerParam, 1, readerType, 0)
  enterReader: putTarget(source, targets, fieldKey, reader, readerName) ?^
  countReader: nextReader = math.addInt64(index, 1)
  set index nextReader
  goto eachReader
:done
  withFirst: withParam = Params.length(params)
  addWithRecord: addParam(params, recordSlot, code, recordMode, region)
  withKey: withName = memberKey(source, name, withWord="with", region) ?^
  makeWithKind: withKind = TargetKind.recordWith()
  makeWith: withTarget = TargetInfo.new(withKind, code, 0, withParam, 2, code, 0)
  enterWith: putTarget(source, targets, withName, withTarget, name) ?^
  return

op narrowPayload "Decide whether an enum payload fits the narrow layout: an Int64, ExitCode, Bool, or Byte, or an enum none of whose variants carries a payload"
  input types Types borrowed
  input code Int64 copied
  output Bool
  let yes Bool true
  let no Bool false
:begin
  lowCheck: atLeastInt = compare.greaterOrEqualInt64(code, 2)
  highCheck: atMostByte = compare.lessOrEqualInt64(code, 5)
  bothCheck: isSmall = logic.and(atLeastInt, atMostByte)
  if isSmall narrow notSmall
:notSmall
  readInfo: info = typeInfoOf(types, code)
  readKind: kind = TypeInfo.kind(info)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  if isEnum enumKind wide
:enumKind
  readTagOnly: tagOnly = TypeInfo.tagOnly(info)
  return tagOnly
:narrow
  return yes
:wide
  return no

op declareEnum "Check an enum's variants, number them as members, and enter a constructor for each variant as a call target"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input code Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowed
  input members Members borrowedMutable
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let index Int64 0 mut
  let slot Int64 0 mut
  let wideSlots Int64 0 mut
  let one Int64 1
  let plain Bool true mut
  let holdsText Bool false mut
  let narrow Bool true mut
  let tagOnly Bool true mut
  let no Bool false
:begin
  readName: name = model.Entity.name(entity)
  firstCheck: firstMember = Members.length(members)
  @rowsBegin
  case contextRow nextRow
  case typeParameterRow noParameter
  case variantRow variant
  others refuse
:noParameter in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:variant in=eachRow
  @wordAt variantName 2
  variantShape: expectCount(row, 4, variantName) ?^
  @wordAt payloadType 3
  noneCheck: noPayload = syntax.isText(source, payloadType, noneWord) ?^
  if noPayload bare payload
:bare in=eachRow
  makeBare: bareMember = MemberInfo.new(code, variantName, 0, index, 0)
  appendBare: Members.append(members, bareMember)
  goto counted
:payload in=eachRow
  findPayloadType: payloadCode = findType(source, typeNames, payloadType) ?^
  checkOrder: orderFits(types, code, payloadCode, payloadType) ?^
  readPayloadInfo: payloadInfo = typeInfoOf(types, payloadCode)
  readPayloadPlain: payloadPlain = TypeInfo.plain(payloadInfo)
  bothPlain: stillPlain = logic.and(plain, payloadPlain)
  set plain stillPlain
  textCheck: payloadText = holdsTextOf(types, payloadCode)
  eitherText: stillText = logic.or(holdsText, payloadText)
  set holdsText stillText
  narrowCheck: payloadNarrow = narrowPayload(types, payloadCode)
  bothNarrow: stillNarrow = logic.and(narrow, payloadNarrow)
  set narrow stillNarrow
  set tagOnly no
  countSlot: nextSlot = math.addInt64(slot, 1)
  set slot nextSlot
  payloadSlotsCheck: payloadSlots = slotsOf(types, payloadCode)
  addSlots: nextWideSlots = math.addInt64(wideSlots, payloadSlots)
  set wideSlots nextWideSlots
  makeMember: member = MemberInfo.new(code, variantName, payloadCode, index, slot)
  appendMember: Members.append(members, member)
  goto counted
:counted in=eachRow
  countMember: nextMember = math.addInt64(index, 1)
  set index nextMember
  goto nextRow
:finish
  readOld: old = typeInfoOf(types, code)
  readModule: module = TypeInfo.module(old)
  if narrow narrowSlots makeInfoStep
:narrowSlots
  set wideSlots one
  goto makeInfoStep
:makeInfoStep
  countTag: slots = math.addInt64(wideSlots, 1)
  makeInfo: info = TypeInfo.new(name, module, 4, 0, 0, plain, holdsText, narrow, tagOnly, firstMember, index, 0, slots)
  findIndex: typeIndex = math.subtractInt64(code, 1)
  setInfo: Types.set(types, typeIndex, info) ! setInfoError
  iferr setInfo lost registered
:registered
  registerTargets: registerEnum(source, code, types, members, params, targets, region) ?^
  return
@reject lostName name lost
@rowsNext

op registerEnum "Enter a constructor for each variant of an enum: a payload slot when the variant carries one"
  input source String borrowed
  input code Int64 copied
  input types Types borrowed
  input members Members borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  readInfo: info = typeInfoOf(types, code)
  readName: name = TypeInfo.name(info)
  readFirst: first = TypeInfo.first(info)
  readCount: count = TypeInfo.count(info)
  goto eachVariant
:eachVariant loop=while max=count
  doneCheck: variantsDone = compare.greaterOrEqualInt64(index, count)
  if variantsDone done addVariant
:addVariant in=eachVariant
  findMember: memberIndex = math.addInt64(first, index)
  readMember: member = Members.getOrTrap(members, memberIndex)
  readMemberName: memberName = MemberInfo.name(member)
  readMemberType: memberType = MemberInfo.type(member)
  firstCheck: firstParam = Params.length(params)
  payloadCheck: hasPayload = compare.greaterThanInt64(memberType, 0)
  if hasPayload addPayload register
:addPayload in=eachVariant
  modeCheck: payloadMode = ownMode(types, memberType)
  addPayloadParam: addParam(params, payloadSlot="payload", memberType, payloadMode, region)
  goto register
:register in=eachVariant
  lastCheck: lastParam = Params.length(params)
  countParams: paramCount = math.subtractInt64(lastParam, firstParam)
  copyMemberName: memberText = syntax.wordText(source, memberName, region) ?^
  variantKey: key = memberKey(source, name, memberText, region) ?^
  makeKind: kind = TargetKind.variantMake()
  makeTarget: target = TargetInfo.new(kind, code, memberIndex, firstParam, paramCount, code, 0)
  enterVariant: putTarget(source, targets, key, target, memberName) ?^
  countVariant: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachVariant
:done
  return

op declareInstance "Check a typeInstance of list.List, or of map.Map with String keys, and enter its members as call targets"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input code Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let item Int64 0 mut
  let value Int64 0 mut
  let isMap Bool false mut
  let no Bool false
  let yes Bool true
:begin
  readName: name = model.Entity.name(entity)
  @rowsBegin
  case contextRow nextRow
  case inRow noOwner
  case instantiatesRow instance
  others refuse
:noOwner in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:instance in=eachRow
  @wordAt genericWord 2
  instanceShape: expectAtLeast(row, 4, genericWord) ?^
  @wordAt itemWord 3
  listCheck: isList = syntax.isText(source, genericWord, listWord="list.List") ?^
  if isList listShape mapCheck
:listShape in=eachRow
  listCount: expectCount(row, 4, genericWord) ?^
  findItem: itemCode = findType(source, typeNames, itemWord) ?^
  checkOrder: orderFits(types, code, itemCode, itemWord) ?^
  set item itemCode
  goto nextRow
:mapCheck in=eachRow
  mapTest: isMapWord = syntax.isText(source, genericWord, mapWord="map.Map") ?^
  if isMapWord mapShape unsupported
:mapShape in=eachRow
  mapCount: expectCount(row, 5, genericWord) ?^
  @wordAt valueWord 4
  findKey: keyCode = findType(source, typeNames, itemWord) ?^
  stringKey: keyIsString = compare.equalInt64(keyCode, 1)
  if keyIsString mapValue badKey
:mapValue in=eachRow
  findValueType: valueTypeCode = findType(source, typeNames, valueWord) ?^
  checkValueOrder: orderFits(types, code, valueTypeCode, valueWord) ?^
  set item keyCode
  set value valueTypeCode
  set isMap yes
  goto nextRow
:finish
  readOld: old = typeInfoOf(types, code)
  readModule: module = TypeInfo.module(old)
  findIndex: typeIndex = math.subtractInt64(code, 1)
  if isMap mapInfo listInfo
:listInfo
  makeInfo: info = TypeInfo.new(name, module, 5, item, 0, no, no, no, no, 0, 0, 0, 1)
  setInfo: Types.set(types, typeIndex, info) ! setInfoError
  iferr setInfo lost listRegistered
:listRegistered
  registerTargets: registerList(source, code, item, types, params, targets, region) ?^
  return
:mapInfo
  makeMapInfo: mapType = TypeInfo.new(name, module, 7, item, value, no, no, no, no, 0, 0, 0, 1)
  setMapInfo: Types.set(types, typeIndex, mapType) ! setMapInfoError
  iferr setMapInfo lost mapRegistered
:mapRegistered
  registerMapTargets: registerMap(source, code, item, value, types, params, targets, region) ?^
  return
@reject lostName name lost
@reject unsupportedType genericWord unsupported
@reject unsupportedType itemWord badKey
@rowsNext

op registerList "Enter a list type's members: new, append, length, get, getOrTrap, and set"
  input source String borrowed
  input code Int64 copied
  input item Int64 copied
  input types Types borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
:begin
  readInfo: info = typeInfoOf(types, code)
  readName: name = TypeInfo.name(info)
  itemModeCheck: itemMode = ownMode(types, item)
  newFirst: newParam = Params.length(params)
  addNewRegion: addParam(params, regionSlot="region", 6, 2, region)
  newKey: newName = memberKey(source, name, newWord="new", region) ?^
  makeNewKind: newKind = TargetKind.listNew()
  makeNew: newTarget = TargetInfo.new(newKind, code, 0, newParam, 1, code, 0)
  enterNew: putTarget(source, targets, newName, newTarget, name) ?^
  appendFirst: appendParam = Params.length(params)
  addAppendList: addParam(params, listSlot="list", code, 3, region)
  addAppendItem: addParam(params, itemSlot="item", item, itemMode, region)
  appendKey: appendName = memberKey(source, name, appendWord="append", region) ?^
  makeAppendKind: appendKind = TargetKind.listAppend()
  makeAppend: appendTarget = TargetInfo.new(appendKind, code, 0, appendParam, 2, 0, 0)
  enterAppend: putTarget(source, targets, appendName, appendTarget, name) ?^
  lengthFirst: lengthParam = Params.length(params)
  addLengthList: addParam(params, listSlot, code, 2, region)
  lengthKey: lengthName = memberKey(source, name, lengthWord="length", region) ?^
  makeLengthKind: lengthKind = TargetKind.listLength()
  makeLength: lengthTarget = TargetInfo.new(lengthKind, code, 0, lengthParam, 1, 2, 0)
  enterLength: putTarget(source, targets, lengthName, lengthTarget, name) ?^
  getFirst: getParam = Params.length(params)
  addGetList: addParam(params, listSlot, code, 2, region)
  addGetIndex: addParam(params, indexSlot="index", 2, 1, region)
  getKey: getName = memberKey(source, name, getWord="get", region) ?^
  makeGetKind: getKind = TargetKind.listGet()
  makeGet: getTarget = TargetInfo.new(getKind, code, 0, getParam, 2, item, 7)
  enterGet: putTarget(source, targets, getName, getTarget, name) ?^
  trapFirst: trapParam = Params.length(params)
  addTrapList: addParam(params, listSlot, code, 2, region)
  addTrapIndex: addParam(params, indexSlot, 2, 1, region)
  trapKey: trapName = memberKey(source, name, trapWord="getOrTrap", region) ?^
  makeTrapKind: trapKind = TargetKind.listGetOrTrap()
  makeTrap: trapTarget = TargetInfo.new(trapKind, code, 0, trapParam, 2, item, 0)
  enterTrap: putTarget(source, targets, trapName, trapTarget, name) ?^
  setFirst: setParam = Params.length(params)
  addSetList: addParam(params, listSlot, code, 3, region)
  addSetIndex: addParam(params, indexSlot, 2, 1, region)
  addSetItem: addParam(params, itemSlot, item, itemMode, region)
  setKey: setName = memberKey(source, name, setWord="set", region) ?^
  makeSetKind: setKind = TargetKind.listSet()
  makeSet: setTarget = TargetInfo.new(setKind, code, 0, setParam, 3, 0, 7)
  enterSet: putTarget(source, targets, setName, setTarget, name) ?^
  return

op registerMap "Enter a map type's members: new, put, get, contains, remove, and length; a key is lent, and a value kept as a list item is"
  input source String borrowed
  input code Int64 copied
  input key Int64 copied
  input value Int64 copied
  input types Types borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
:begin
  readInfo: info = typeInfoOf(types, code)
  readName: name = TypeInfo.name(info)
  valueModeCheck: valueMode = ownMode(types, value)
  newFirst: newParam = Params.length(params)
  addNewRegion: addParam(params, regionSlot="region", 6, 2, region)
  newKey: newName = memberKey(source, name, newWord="new", region) ?^
  makeNewKind: newKind = TargetKind.mapNew()
  makeNew: newTarget = TargetInfo.new(newKind, code, 0, newParam, 1, code, 0)
  enterNew: putTarget(source, targets, newName, newTarget, name) ?^
  putFirst: putParam = Params.length(params)
  addPutMap: addParam(params, mapSlot="map", code, 3, region)
  addPutKey: addParam(params, keySlot="key", key, 2, region)
  addPutValue: addParam(params, valueSlot="value", value, valueMode, region)
  putKey: putName = memberKey(source, name, putWord="put", region) ?^
  makePutKind: putKind = TargetKind.mapPut()
  makePut: putMember = TargetInfo.new(putKind, code, 0, putParam, 3, 0, 0)
  enterPut: putTarget(source, targets, putName, putMember, name) ?^
  getFirst: getParam = Params.length(params)
  addGetMap: addParam(params, mapSlot, code, 2, region)
  addGetKey: addParam(params, keySlot, key, 2, region)
  getKey: getName = memberKey(source, name, getWord="get", region) ?^
  makeGetKind: getKind = TargetKind.mapGet()
  makeGet: getTarget = TargetInfo.new(getKind, code, 0, getParam, 2, value, 7)
  enterGet: putTarget(source, targets, getName, getTarget, name) ?^
  containsFirst: containsParam = Params.length(params)
  addContainsMap: addParam(params, mapSlot, code, 2, region)
  addContainsKey: addParam(params, keySlot, key, 2, region)
  containsKey: containsName = memberKey(source, name, containsWord="contains", region) ?^
  makeContainsKind: containsKind = TargetKind.mapContains()
  makeContains: containsTarget = TargetInfo.new(containsKind, code, 0, containsParam, 2, 4, 0)
  enterContains: putTarget(source, targets, containsName, containsTarget, name) ?^
  removeFirst: removeParam = Params.length(params)
  addRemoveMap: addParam(params, mapSlot, code, 3, region)
  addRemoveKey: addParam(params, keySlot, key, 2, region)
  removeKey: removeName = memberKey(source, name, removeWord="remove", region) ?^
  makeRemoveKind: removeKind = TargetKind.mapRemove()
  makeRemove: removeTarget = TargetInfo.new(removeKind, code, 0, removeParam, 2, 0, 7)
  enterRemove: putTarget(source, targets, removeName, removeTarget, name) ?^
  lengthFirst: lengthParam = Params.length(params)
  addLengthMap: addParam(params, mapSlot, code, 2, region)
  lengthKey: lengthName = memberKey(source, name, lengthWord="length", region) ?^
  makeLengthKind: lengthKind = TargetKind.mapLength()
  makeLength: lengthTarget = TargetInfo.new(lengthKind, code, 0, lengthParam, 1, 2, 0)
  enterLength: putTarget(source, targets, lengthName, lengthTarget, name) ?^
  return

op lookupMember "Find the member of a record or enum a word names, by its position in the members list"
  input source String borrowed
  input types Types borrowed
  input members Members borrowed
  input code Int64 copied
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  readInfo: info = typeInfoOf(types, code)
  readFirst: first = TypeInfo.first(info)
  readCount: count = TypeInfo.count(info)
  goto eachMember
:eachMember loop=while max=count
  doneCheck: allSeen = compare.greaterOrEqualInt64(index, count)
  if allSeen missing readMember
:readMember in=eachMember
  findIndex: memberIndex = math.addInt64(first, index)
  readMemberInfo: member = Members.getOrTrap(members, memberIndex)
  readName: name = MemberInfo.name(member)
  sameCheck: same = syntax.sameText(source, name, word) ?^
  countMember: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  if same found eachMember
:found
  return memberIndex
@reject unsupportedPayload word missing

op checkCell "Check a table cell: the field it fills belongs to the row type, and its value is a literal of the field's type or a variant without payload of the field's enum"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input rowType Int64 copied
  input types Types borrowed
  input members Members borrowed
  input targets Targets borrowed
  raises syntax.Rejection
:begin
  @wordAt cellRow 2
  cellShape: expectCount(row, 5, cellRow) ?^
  @wordAt fieldWord 3
  @wordAt valueWord 4
  findField: fieldIndex = lookupMember(source, types, members, rowType, fieldWord) ?^
  readField: field = Members.getOrTrap(members, fieldIndex)
  readFieldType: fieldType = MemberInfo.type(field)
  readFieldInfo: fieldInfo = typeInfoOf(types, fieldType)
  readFieldKind: fieldKind = TypeInfo.kind(fieldInfo)
  enumCheck: isEnum = compare.equalInt64(fieldKind, 4)
  if isEnum variantCell literalCell
:literalCell
  readLiteral: literal = literalOf(fieldType)
  checkLiteral: literalFits(source, valueWord, literal) ?^
  return
:variantCell
  @view variantText valueWord outside
  findVariant: variantTarget = Targets.get(targets, variantText) ? badVariant
  readVariantKind: variantKind = TargetInfo.kind(variantTarget)
  readOwner: owner = TargetInfo.owner(variantTarget)
  readCount: argumentCount = TargetInfo.paramCount(variantTarget)
  match variantKind
  case variantMake variantOwner
  others badVariant
:variantOwner
  ownerCheck: sameEnum = compare.equalInt64(owner, fieldType)
  bareCheck: bare = compare.equalInt64(argumentCount, 0)
  bothCheck: fits = logic.and(sameEnum, bare)
  if fits done badVariant
:done
  return
@reject unknownVariant valueWord badVariant
@reject outsideSource valueWord outside

op declareTable "Check a table: its row type is a record, its rows are numbered 1 to n in order, and each cell fills a field of the row with a literal of its type; enter rowAt and length as call targets"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input entityIndex Int64 copied
  input code Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowed
  input members Members borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let rowType Int64 0 mut
  let rowCount Int64 0 mut
  let no Bool false
:begin
  readName: name = model.Entity.name(entity)
  @rowsBegin
  case contextRow nextRow
  case rowTypeRow rowTypeFact
  case rowRow rowFact
  case cellRow cellFact
  others refuse
:rowTypeFact in=eachRow
  @wordAt rowTypeWord 2
  rowTypeShape: expectCount(row, 3, rowTypeWord) ?^
  findRowType: rowCode = findType(source, typeNames, rowTypeWord) ?^
  readRowInfo: rowInfo = typeInfoOf(types, rowCode)
  readRowKind: rowKind = TypeInfo.kind(rowInfo)
  recordCheck: isRecord = compare.equalInt64(rowKind, 3)
  if isRecord keepRowType badRowType
:keepRowType in=eachRow
  set rowType rowCode
  goto nextRow
:rowFact in=eachRow
  @wordAt rowName 2
  rowShape: expectCount(row, 4, rowName) ?^
  @wordAt numberWord 3
  countRow: nextCount = math.addInt64(rowCount, 1)
  set rowCount nextCount
  readNumberKind: numberKind = syntax.Word.kind(numberWord)
  match numberKind
  case integer number numberCheck
  others badNumber
:numberCheck in=eachRow
  orderCheck: inOrder = compare.equalInt64(number, rowCount)
  if inOrder nextRow badNumber
:cellFact in=eachRow
  typedCheck: typed = compare.greaterThanInt64(rowType, 0)
  if typed checkTheCell cellBeforeRowType
:checkTheCell in=eachRow
  checkIt: checkCell(source, words, row, rowType, types, members, targets) ?^
  goto nextRow
:finish
  readOld: old = typeInfoOf(types, code)
  readModule: module = TypeInfo.module(old)
  makeInfo: info = TypeInfo.new(name, module, 6, rowType, 0, no, no, no, no, entityIndex, rowCount, 0, 1)
  findIndex: typeIndex = math.subtractInt64(code, 1)
  setInfo: Types.set(types, typeIndex, info) ! setInfoError
  iferr setInfo lost registered
:registered
  rowAtFirst: rowAtParam = Params.length(params)
  addPosition: addParam(params, positionSlot="position", 2, 1, region)
  rowAtKey: rowAtName = memberKey(source, name, rowAtWord="rowAt", region) ?^
  makeRowAtKind: rowAtKind = TargetKind.tableRowAt()
  makeRowAt: rowAtTarget = TargetInfo.new(rowAtKind, code, 0, rowAtParam, 1, rowType, 7)
  enterRowAt: putTarget(source, targets, rowAtName, rowAtTarget, name) ?^
  lengthFirst: lengthParam = Params.length(params)
  lengthKey: lengthName = memberKey(source, name, lengthWord="length", region) ?^
  makeLengthKind: lengthKind = TargetKind.tableLength()
  makeLength: lengthTarget = TargetInfo.new(lengthKind, code, 0, lengthParam, 0, 2, 0)
  enterLength: putTarget(source, targets, lengthName, lengthTarget, name) ?^
  return
@reject lostName name lost
@reject unsupportedType rowTypeWord badRowType
@reject unsupportedPredicate predicateWord cellBeforeRowType
@reject unsupportedPayload numberWord badNumber
@rowsNext

op declareOperationType "Check an operationType: its inputs (copied, borrowed, or borrowedMutable), its output, `raises none` or an enum, `outputOwnedBy none`, and `async false`; it is a type whose values call an operation of that signature"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input code Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowed
  input params Params borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let output Int64 0 mut
  let raises Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  readName: name = model.Entity.name(entity)
  firstCheck: firstParam = Params.length(params)
  @rowsBegin
  case contextRow nextRow
  case typeParameterRow noParameter
  case effectRow nextRow
  case asyncRow notAsync
  case inputRow inputFact
  case outputRow outputFact
  case outputOwnedByRow noOwner
  case raisesRow raisesFact
  others refuse
:noParameter in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:notAsync in=eachRow
  fixedFalse: checkWord(source, words, row, falseWord="false") ?^
  goto nextRow
:noOwner in=eachRow
  fixedOwner: checkWord(source, words, row, noneWord) ?^
  goto nextRow
:inputFact in=eachRow
  readInputCount: inputCount = syntax.Row.count(row)
  noInputCheck: noInput = compare.equalInt64(inputCount, 3)
  if noInput inputNone inputSlot
:inputNone in=eachRow
  inputFixed: checkWord(source, words, row, noneWord) ?^
  goto nextRow
:inputSlot in=eachRow
  @wordAt inputName 2
  inputShape: expectCount(row, 5, inputName) ?^
  @wordAt inputType 3
  @wordAt inputMode 4
  findInputType: inputCode = findType(source, typeNames, inputType) ?^
  findInputMode: modeCode = inputModeOf(source, inputMode) ?^
  copyInputName: inputText = syntax.wordText(source, inputName, region) ?^
  addInputSlot: addParam(params, inputText, inputCode, modeCode, region)
  goto nextRow
:outputFact in=eachRow
  @wordAt outputWord 2
  outputShape: expectCount(row, 3, outputWord) ?^
  outputNoneCheck: outputNone = syntax.isText(source, outputWord, noneWord) ?^
  if outputNone nextRow outputType
:outputType in=eachRow
  findOutputType: outputCode = findType(source, typeNames, outputWord) ?^
  set output outputCode
  goto nextRow
:raisesFact in=eachRow
  @wordAt raisesWord 2
  raisesShape: expectCount(row, 3, raisesWord) ?^
  raisesNoneCheck: raisesNone = syntax.isText(source, raisesWord, noneWord) ?^
  if raisesNone nextRow raisesType
:raisesType in=eachRow
  findRaisesType: raisesCode = findRaises(source, typeNames, raisesWord) ?^
  readRaisesInfo: raisesInfo = typeInfoOf(types, raisesCode)
  readRaisesKind: raisesKind = TypeInfo.kind(raisesInfo)
  enumCheck: raisesEnum = compare.equalInt64(raisesKind, 4)
  standardCheck: raisesStandard = compare.equalInt64(raisesKind, 2)
  eitherCheck: raisesFits = logic.or(raisesEnum, raisesStandard)
  if raisesFits keepRaises badRaises
:keepRaises in=eachRow
  set raises raisesCode
  goto nextRow
:finish
  lastCheck: lastParam = Params.length(params)
  countParams: paramCount = math.subtractInt64(lastParam, firstParam)
  readOld: old = typeInfoOf(types, code)
  readModule: module = TypeInfo.module(old)
  makeInfo: info = TypeInfo.new(name, module, 8, output, 0, yes, no, no, no, firstParam, paramCount, raises, 1)
  findIndex: typeIndex = math.subtractInt64(code, 1)
  setInfo: Types.set(types, typeIndex, info) ! setInfoError
  iferr setInfo lost registered
:registered
  return
@reject unsupportedType raisesWord badRaises
@reject lostName name lost
@rowsNext

op declareOperation "Check an operation's signature rows, add its slots, and enter it as a call target; main takes no input, gives an ExitCode, and raises nothing"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input entityIndex Int64 copied
  input opIndex Int64 copied
  input module syntax.Word copied
  input moduleFirst Int64 copied
  input moduleEnd Int64 copied
  input types Types borrowed
  input typeNames TypeNames borrowed
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input ops Ops borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let output Int64 0 mut
  let raises Int64 0 mut
  let owner syntax.Word unset mut
  let owned Bool false mut
  let depth syntax.Word unset mut
  let recursive Bool false mut
  let no Bool false
  let yes Bool true
:begin
  readName: name = model.Entity.name(entity)
  set owner name
  set depth name
  firstCheck: firstParam = Params.length(params)
  @rowsBegin
  case contextRow nextRow
  case typeParameterRow noParameter
  case asyncRow notAsync
  case effectRow nextRow
  case usesRow nextRow
  case memoryHeapRow nextRow
  case labelRow nextRow
  case letRow nextRow
  case atRow nextRow
  case inputRow inputFact
  case outputRow outputFact
  case outputOwnedByRow outputOwner
  case raisesRow raisesFact
  case maxRecursionRow recursion
  others refuse
:noParameter in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:notAsync in=eachRow
  @wordAt asyncWord 2
  asyncShape: expectCount(row, 3, asyncWord) ?^
  falseCheck: isFalse = syntax.isText(source, asyncWord, falseWord="false") ?^
  trueCheck: isTrue = syntax.isText(source, asyncWord, trueWord="true") ?^
  flagCheck: isFlag = logic.or(isFalse, isTrue)
  if isFlag nextRow badAsync
@reject unsupportedPayload asyncWord badAsync
:inputFact in=eachRow
  readInputCount: inputCount = syntax.Row.count(row)
  noInputCheck: noInput = compare.equalInt64(inputCount, 3)
  if noInput inputNone inputSlot
:inputNone in=eachRow
  inputFixed: checkWord(source, words, row, noneWord) ?^
  goto nextRow
:inputSlot in=eachRow
  @wordAt inputName 2
  inputShape: expectCount(row, 5, inputName) ?^
  @wordAt inputType 3
  @wordAt inputMode 4
  findInputType: inputCode = findType(source, typeNames, inputType) ?^
  findInputMode: modeCode = inputModeOf(source, inputMode) ?^
  copyInputName: inputText = syntax.wordText(source, inputName, region) ?^
  addInputSlot: addParam(params, inputText, inputCode, modeCode, region)
  goto nextRow
:outputFact in=eachRow
  @wordAt outputWord 2
  outputShape: expectCount(row, 3, outputWord) ?^
  outputNoneCheck: outputNone = syntax.isText(source, outputWord, noneWord) ?^
  if outputNone nextRow outputType
:outputType in=eachRow
  findOutputType: outputCode = findType(source, typeNames, outputWord) ?^
  set output outputCode
  goto nextRow
:outputOwner in=eachRow
  @wordAt ownerWord 2
  ownerShape: expectCount(row, 3, ownerWord) ?^
  ownerNoneCheck: ownerNone = syntax.isText(source, ownerWord, noneWord) ?^
  if ownerNone nextRow ownerCaller
:ownerCaller in=eachRow
  callerCheck: ownerIsCaller = syntax.isText(source, ownerWord, callerWord="caller") ?^
  if ownerIsCaller badOwner ownerInput
:ownerInput in=eachRow
  set owner ownerWord
  set owned yes
  goto nextRow
:raisesFact in=eachRow
  @wordAt raisesWord 2
  raisesShape: expectCount(row, 3, raisesWord) ?^
  raisesNoneCheck: raisesNone = syntax.isText(source, raisesWord, noneWord) ?^
  if raisesNone nextRow raisesType
:raisesType in=eachRow
  findRaisesType: raisesCode = findRaises(source, typeNames, raisesWord) ?^
  readRaisesInfo: raisesInfo = typeInfoOf(types, raisesCode)
  readRaisesKind: raisesKind = TypeInfo.kind(raisesInfo)
  enumCheck: raisesEnum = compare.equalInt64(raisesKind, 4)
  standardCheck: raisesStandard = compare.equalInt64(raisesKind, 2)
  eitherCheck: raisesFits = logic.or(raisesEnum, raisesStandard)
  if raisesFits keepRaises badRaises
:keepRaises in=eachRow
  set raises raisesCode
  goto nextRow
:recursion in=eachRow
  @wordAt depthWord 2
  depthShape: expectCount(row, 3, depthWord) ?^
  depthNoneCheck: depthNone = syntax.isText(source, depthWord, noneWord) ?^
  if depthNone nextRow depthBound
:depthBound in=eachRow
  readDepthKind: depthKind = syntax.Word.kind(depthWord)
  match depthKind
  case integer depthValue keepDepth
  others badDepth
:keepDepth in=eachRow
  set depth depthWord
  set recursive yes
  goto nextRow
:finish
  lastCheck: lastParam = Params.length(params)
  countParams: paramCount = math.subtractInt64(lastParam, firstParam)
  mainCheck: isMain = syntax.isText(source, name, mainWord="main") ?^
  if isMain checkMain register
:checkMain
  noInputs: noParams = compare.equalInt64(paramCount, 0)
  exitCodeCheck: givesExitCode = compare.equalInt64(output, 3)
  raisesNothing: noRaises = compare.equalInt64(raises, 0)
  firstTwo: inputsAndOutput = logic.and(noParams, givesExitCode)
  allThree: mainFits = logic.and(inputsAndOutput, noRaises)
  if mainFits register badMain
:register
  makeOp: op = OpInfo.new(name, module, moduleFirst, moduleEnd, entityIndex, firstParam, paramCount, output, raises, owner, owned, depth, recursive)
  appendOp: Ops.append(ops, op)
  copyName: nameText = syntax.wordText(source, name, region) ?^
  makeKind: kind = TargetKind.operation()
  makeTarget: target = TargetInfo.new(kind, opIndex, 0, firstParam, paramCount, output, raises)
  enterTarget: putTarget(source, targets, nameText, target, name) ?^
  return
@reject unsupportedPayload ownerWord badOwner
@reject unsupportedType raisesWord badRaises
@reject unsupportedPayload depthWord badDepth
@reject badMain name badMain
@rowsNext

op declareOwned "Check the rows of a call or a region and return the position of the operation its `in` row names"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input opNames OpNames borrowed
  output Int64
  raises syntax.Rejection
  let owner Int64 -1 mut
:begin
  readName: name = model.Entity.name(entity)
  @rowsBegin
  case contextRow nextRow
  case inRow ownerFact
  case invokesRow nextRow
  case invokesReferenceRow nextRow
  case argumentRow nextRow
  case resultRow nextRow
  case ownedByRow nextRow
  case borrowsRow nextRow
  case catchRow nextRow
  case suppressesRow nextRow
  case cleanedByRow noCleanup
  case strategyRow arena
  case maxBytesRow capacity
  case releasedRow release
  others refuse
:noCleanup in=eachRow
  fixedNone: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:arena in=eachRow
  fixedArena: checkWord(source, words, row, arenaWord="arena") ?^
  goto nextRow
:capacity in=eachRow
  @wordAt bytesWord 2
  bytesShape: expectCount(row, 3, bytesWord) ?^
  readBytesKind: bytesKind = syntax.Word.kind(bytesWord)
  match bytesKind
  case integer bytes nextRow
  others badBytes
:release in=eachRow
  @wordAt releaseWord 2
  releaseShape: expectCount(row, 3, releaseWord) ?^
  returnCheck: atReturn = syntax.isText(source, releaseWord, atReturnWord="atReturn") ?^
  exitCheck: atExit = syntax.isText(source, releaseWord, atExitWord="atProcessExit") ?^
  eitherCheck: releaseFits = logic.or(atReturn, atExit)
  if releaseFits nextRow badRelease
:ownerFact in=eachRow
  @wordAt ownerWord 2
  ownerShape: expectCount(row, 3, ownerWord) ?^
  @view ownerText ownerWord outside
  findOwner: ownerIndex = OpNames.get(opNames, ownerText) ? unknownOwner
  set owner ownerIndex
  goto nextRow
:finish
  knownCheck: hasOwner = compare.greaterOrEqualInt64(owner, 0)
  if hasOwner done noOwner
:done
  return owner
@reject unsupportedPayload bytesWord badBytes
@reject unsupportedPayload releaseWord badRelease
@reject unknownOwner ownerWord unknownOwner
@reject outsideSource ownerWord outside
@reject unknownOwner name noOwner
@rowsNext

## ---------------------------------------------------------------- one operation: inputs, labels, lets, binds

op copyTypeNames "Enter every name of one type map in another, with the type it names"
  input from TypeNames borrowed
  input to TypeNames borrowedMutable
:begin
  countNames: count = TypeNames.length(from)
  goto eachName
:eachName loop=forEach max=count over=from
  next from key copyOne done
:copyOne in=eachName
  readCode: code = TypeNames.get(from, key) ? eachName
  putCode: TypeNames.put(to, key, code)
  goto eachName
:done
  return

op copyTargets "Enter every call target of one target map in another"
  input from Targets borrowed
  input to Targets borrowedMutable
:begin
  countNames: count = Targets.length(from)
  goto eachName
:eachName loop=forEach max=count over=from
  next from key copyOne done
:copyOne in=eachName
  readTarget: target = Targets.get(from, key) ? eachName
  putIt: Targets.put(to, key, target)
  goto eachName
:done
  return

op publishTypeNames "Enter the types a module declared (the names its map holds past the ones it was seeded with) in the program's map, as `<module>.<name>`"
  input source String borrowed
  input module syntax.Word copied
  input local TypeNames borrowed
  input seeded Int64 copied
  input global TypeNames borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let position Int64 0 mut
:begin
  copyModule: moduleText = syntax.wordText(source, module, region) ?^
  makeScope: scope = string.concat(moduleText, dot=".", region)
  countNames: count = TypeNames.length(local)
  goto eachName
:eachName loop=forEach max=count over=local
  next local key readOne done
:readOne in=eachName
  ownCheck: own = compare.greaterOrEqualInt64(position, seeded)
  countPosition: nextPosition = math.addInt64(position, 1)
  set position nextPosition
  if own publishOne eachName
:publishOne in=eachName
  readCode: code = TypeNames.get(local, key) ? eachName
  qualify: qualified = string.concat(scope, key, region)
  putCode: TypeNames.put(global, qualified, code)
  goto eachName
:done
  return

op publishTargets "Enter the call targets a module declared (those its map holds past the ones it was seeded with) in the program's map, as `<module>.<name>`"
  input source String borrowed
  input module syntax.Word copied
  input local Targets borrowed
  input seeded Int64 copied
  input global Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let position Int64 0 mut
:begin
  copyModule: moduleText = syntax.wordText(source, module, region) ?^
  makeScope: scope = string.concat(moduleText, dot=".", region)
  countNames: count = Targets.length(local)
  goto eachName
:eachName loop=forEach max=count over=local
  next local key readOne done
:readOne in=eachName
  ownCheck: own = compare.greaterOrEqualInt64(position, seeded)
  countPosition: nextPosition = math.addInt64(position, 1)
  set position nextPosition
  if own publishOne eachName
:publishOne in=eachName
  readTarget: target = Targets.get(local, key) ? eachName
  qualify: qualified = string.concat(scope, key, region)
  putIt: Targets.put(global, qualified, target)
  goto eachName
:done
  return

op nextModule "The position one past the last entity of the module that starts at a position: the next module entity's position, or the length of the list"
  invariant findsModuleEnd "Gives the position of the first module entity after the given position, or the number of entities when there is none"
  input entities model.Entities borrowed
  input first Int64 copied
  output Int64
  let index Int64 0 mut
:begin
  countEntities: count = model.Entities.length(entities)
  startAfter: start = math.addInt64(first, 1)
  set index start
  goto scan
:scan loop=while max=count
  endCheck: atEnd = compare.greaterOrEqualInt64(index, count)
  if atEnd finish readEntity
:readEntity in=scan
  readTheEntity: entity = model.Entities.getOrTrap(entities, index)
  readKind: kind = model.Entity.kind(entity)
  moduleCheck: isModule = compare.equalInt64(kind, 1)
  if isModule finish advance
:advance in=scan
  stepIndex: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto scan
:finish
  return index

op checkModuleDeclarations "Check the entities of one module of a program and collect its declarations, under its own names, in maps seeded with the built-in names and every earlier module's `<module>.<name>`; then publish its names as `<module>.<name>` for the modules after it"
  invariant declaresTypes "Built-in types are numbered 1 to 11 (String, Int64, ExitCode, Bool, Byte, Region, the standard errors, ByteBuffer, process.Arguments, time.Deadline, Bytes) and every record, enum, typeInstance, table, and operationType of the program after them in source order; each record field and enum variant is a member, in order"
  invariant declaresTargets "Every standard library target of the subset, operation, record constructor and field reader, enum variant constructor, list and map member, and table reader is a call target with its slots, result type, and error, under its own name in its module and as `<module>.<name>` in the modules after it"
  invariant rejectsOutsideDeclarations "A predicate, payload, type, or kind outside the subset is refused at the word concerned, as is a module whose first entity is not its module entity, a main that takes inputs, a type held by value before it is declared, and a call or region whose operation does not exist"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input first Int64 copied
  input end Int64 copied
  input types Types borrowedMutable
  input typeNames TypeNames borrowedMutable
  input members Members borrowedMutable
  input params Params borrowedMutable
  input targets Targets borrowedMutable
  input ops Ops borrowedMutable
  input opNames OpNames borrowedMutable
  input owners Owners borrowedMutable
  input constants Values borrowedMutable
  input globalTypeNames TypeNames borrowedMutable
  input globalTargets Targets borrowedMutable
  input region Region borrowed
  raises syntax.Rejection
  let entityIndex Int64 0 mut
  let opIndex Int64 0 mut
  let typeCode Int64 0 mut
:begin
  readModuleEntity: moduleEntity = model.Entities.getOrTrap(entities, first)
  readModuleKind: moduleKind = model.Entity.kind(moduleEntity)
  readModuleName: module = model.Entity.name(moduleEntity)
  moduleCheck: isModule = compare.equalInt64(moduleKind, 1)
  if isModule seed notModule
:seed
  seedTypes: copyTypeNames(globalTypeNames, typeNames)
  seedTargets: copyTargets(globalTargets, targets)
  countSeededTypes: seededTypes = TypeNames.length(typeNames)
  countSeededTargets: seededTargets = Targets.length(targets)
  countOps: opBase = Ops.length(ops)
  countTypes: typeBase = Types.length(types)
  set opIndex opBase
  set typeCode typeBase
  set entityIndex first
  numberNames: declareNames(source, entities, first, end, module, types, typeNames, opNames, opBase, region) ?^
  findSpan: span = math.subtractInt64(end, first)
  goto eachEntity
:eachEntity loop=while max=span
  doneCheck: allDone = compare.greaterOrEqualInt64(entityIndex, end)
  if allDone publish readEntity
:readEntity in=eachEntity
  readTheEntity: entity = model.Entities.getOrTrap(entities, entityIndex)
  readKind: kind = model.Entity.kind(entity)
  moduleKindCheck: isModuleEntity = compare.equalInt64(kind, 1)
  if isModuleEntity moduleEntityStep notModuleEntity
:notModuleEntity in=eachEntity
  capabilityCheck: isCapability = compare.equalInt64(kind, 2)
  if isCapability capabilityEntity notCapability
:notCapability in=eachEntity
  constantCheck: isConstant = compare.equalInt64(kind, 3)
  if isConstant constantEntity notConstant
:notConstant in=eachEntity
  operationCheck: isOperation = compare.equalInt64(kind, 4)
  if isOperation operationEntity notOperation
:notOperation in=eachEntity
  callCheck: isCall = compare.equalInt64(kind, 5)
  regionCheck: isRegion = compare.equalInt64(kind, 9)
  taskCheck: isTask = compare.equalInt64(kind, 10)
  callOrRegion: isCallOrRegion = logic.or(isCall, isRegion)
  ownedCheck: isOwned = logic.or(isCallOrRegion, isTask)
  if isOwned ownedEntity notOwned
:notOwned in=eachEntity
  countType: nextCode = math.addInt64(typeCode, 1)
  set typeCode nextCode
  recordCheck: isRecord = compare.equalInt64(kind, 6)
  if isRecord recordEntity notRecord
:notRecord in=eachEntity
  enumCheck: isEnum = compare.equalInt64(kind, 7)
  if isEnum enumEntity notEnum
:notEnum in=eachEntity
  tableCheck: isTable = compare.equalInt64(kind, 11)
  if isTable tableEntity notTable
:notTable in=eachEntity
  referenceCheck: isReference = compare.equalInt64(kind, 12)
  if isReference referenceEntity instanceEntity
:tableEntity in=eachEntity
  checkTableRows: declareTable(source, words, rows, entity, entityIndex, typeCode, types, typeNames, members, params, targets, region) ?^
  goto unowned
:referenceEntity in=eachEntity
  checkReferenceRows: declareOperationType(source, words, rows, entity, typeCode, types, typeNames, params, region) ?^
  goto unowned
:moduleEntityStep in=eachEntity
  checkModuleRows: declareModule(source, words, rows, entity) ?^
  goto unowned
:capabilityEntity in=eachEntity
  checkCapabilityRows: declareCapability(source, words, rows, entity) ?^
  goto unowned
:constantEntity in=eachEntity
  checkConstantRows: declareConstant(source, words, rows, entity, typeNames, constants) ?^
  goto unowned
:operationEntity in=eachEntity
  checkOperationRows: declareOperation(source, words, rows, entity, entityIndex, opIndex, module, first, end, types, typeNames, params, targets, ops, region) ?^
  countOperation: nextOp = math.addInt64(opIndex, 1)
  set opIndex nextOp
  goto unowned
:ownedEntity in=eachEntity
  checkOwnedRows: ownerIndex = declareOwned(source, words, rows, entity, opNames) ?^
  appendOwner: Owners.append(owners, ownerIndex)
  goto advance
:recordEntity in=eachEntity
  checkRecordRows: declareRecord(source, words, rows, entity, typeCode, types, typeNames, members, params, targets, region) ?^
  goto unowned
:enumEntity in=eachEntity
  checkEnumRows: declareEnum(source, words, rows, entity, typeCode, types, typeNames, members, params, targets, region) ?^
  goto unowned
:instanceEntity in=eachEntity
  checkInstanceRows: declareInstance(source, words, rows, entity, typeCode, types, typeNames, params, targets, region) ?^
  goto unowned
:unowned in=eachEntity
  appendNone: Owners.append(owners, minus1=-1)
  goto advance
:advance in=eachEntity
  countEntity: nextEntity = math.addInt64(entityIndex, 1)
  set entityIndex nextEntity
  goto eachEntity
:publish
  publishTypes: publishTypeNames(source, module, typeNames, seededTypes, globalTypeNames, region) ?^
  publishCalls: publishTargets(source, module, targets, seededTargets, globalTargets, region) ?^
  return
@reject notModule module notModule

op addInput "Check an input row of an operation and enter its value"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input typeNames TypeNames borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  raises syntax.Rejection
  let no Bool false
  let yes Bool true
:begin
  readCount: count = syntax.Row.count(row)
  noneCheck: isNone = compare.equalInt64(count, 3)
  if isNone done slot
:slot
  @wordAt name 2
  @wordAt typeWord 3
  findCode: code = findType(source, typeNames, typeWord) ?^
  freshCheck: requireNewValue(source, values, constants, name) ?^
  makeInfo: info = ValueInfo.new(name, code, no, 4, name, no, yes, no)
  enter: enterValue(source, values, info) ?^
  goto done
:done
  return

op signatureFits "Decide whether an operation fits an operationType: the same slots with the same types and modes, the same output, and the same error"
  input params Params borrowed
  input reference TypeInfo copied
  input target TargetInfo copied
  output Bool
  let index Int64 0 mut
  let no Bool false
  let yes Bool true
:begin
  readKind: kind = TargetInfo.kind(target)
  match kind
  case operation compareShape
  others different
:compareShape
  readWantCount: wantCount = TypeInfo.count(reference)
  readHaveCount: haveCount = TargetInfo.paramCount(target)
  readWantOutput: wantOutput = TypeInfo.item(reference)
  readHaveOutput: haveOutput = TargetInfo.output(target)
  readWantRaises: wantRaises = TypeInfo.raises(reference)
  readHaveRaises: haveRaises = TargetInfo.raises(target)
  countCheck: sameCount = compare.equalInt64(wantCount, haveCount)
  outputCheck: sameOutput = compare.equalInt64(wantOutput, haveOutput)
  raisesCheck: sameRaises = compare.equalInt64(wantRaises, haveRaises)
  bothCheck: countAndOutput = logic.and(sameCount, sameOutput)
  allCheck: shapeFits = logic.and(countAndOutput, sameRaises)
  readWantFirst: wantFirst = TypeInfo.first(reference)
  readHaveFirst: haveFirst = TargetInfo.firstParam(target)
  if shapeFits eachSlot different
:eachSlot loop=while max=wantCount
  slotsDone: allSlots = compare.greaterOrEqualInt64(index, wantCount)
  if allSlots same compareSlot
:compareSlot in=eachSlot
  findWant: wantIndex = math.addInt64(wantFirst, index)
  findHave: haveIndex = math.addInt64(haveFirst, index)
  readWant: want = Params.getOrTrap(params, wantIndex)
  readHave: have = Params.getOrTrap(params, haveIndex)
  readWantType: wantType = ParamInfo.type(want)
  readHaveType: haveType = ParamInfo.type(have)
  readWantMode: wantMode = ParamInfo.mode(want)
  readHaveMode: haveMode = ParamInfo.mode(have)
  typeCheck: sameType = compare.equalInt64(wantType, haveType)
  modeCheck: sameMode = compare.equalInt64(wantMode, haveMode)
  slotCheck: slotFits = logic.and(sameType, sameMode)
  countSlot: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  if slotFits eachSlot different
:same
  return yes
:different
  return no

op addLet "Check a let row of an operation and enter its value; a let of an operationType names an operation that fits it"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input types Types borrowed
  input typeNames TypeNames borrowed
  input params Params borrowed
  input targets Targets borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  raises syntax.Rejection
  let isMutable Bool false mut
  let initIsName Bool false mut
  let initialized Bool true mut
  let no Bool false
  let yes Bool true
:begin
  @wordAt name 2
  readCount: count = syntax.Row.count(row)
  threeCheck: isThree = compare.equalInt64(count, 3)
  if isThree noneCheck fullRow
:noneCheck
  letNone: checkWord(source, words, row, noneWord="none") ?^
  goto done
:fullRow
  sixWords: expectCount(row, 6, name) ?^
  @wordAt typeWord 3
  @wordAt valueWord 4
  @wordAt mutabilityWord 5
  findCode: code = findType(source, typeNames, typeWord) ?^
  mutableCheck: saysMutable = syntax.isText(source, mutabilityWord, mutableWord="mutable") ?^
  if saysMutable markMutable immutableCheck
:markMutable
  set isMutable yes
  goto valueCheck
:immutableCheck
  immutableTest: saysImmutable = syntax.isText(source, mutabilityWord, immutableWord="immutable") ?^
  if saysImmutable valueCheck badMutability
:valueCheck
  unsetCheck: isUnset = syntax.isText(source, valueWord, unsetWord="unset") ?^
  if isUnset markUnset sourceCheck
:markUnset
  set initialized no
  goto enter
:sourceCheck
  readValueKind: valueKind = syntax.Word.kind(valueWord)
  match valueKind
  case name nameValue
  case integer valueNumber literalCheck
  case text literalCheck
:nameValue
  flagCheck: isTrue = syntax.isText(source, valueWord, trueWord="true") ?^
  falseCheck: isFalse = syntax.isText(source, valueWord, falseWord="false") ?^
  eitherFlag: isFlag = logic.or(isTrue, isFalse)
  if isFlag literalCheck referenceCheck
:referenceCheck
  readLetType: letType = typeInfoOf(types, code)
  readLetKind: letKind = TypeInfo.kind(letType)
  operationTypeCheck: isReference = compare.equalInt64(letKind, 8)
  if isReference operationValue copyFrom
:operationValue
  @view operationText valueWord outside
  findOperation: operationTarget = Targets.get(targets, operationText) ? wrongType
  fitCheck: fits = signatureFits(params, letType, operationTarget)
  if fits markName wrongType
:copyFrom
  readSource: sourceInfo = findValue(source, values, constants, valueWord) ?^
  sourceCode: fromCode = ValueInfo.code(sourceInfo)
  typeCheck: sameType = compare.equalInt64(fromCode, code)
  if sameType markName wrongType
:markName
  set initIsName yes
  goto enter
:literalCheck
  literalKind: literal = literalOf(code)
  checkLiteral: literalFits(source, valueWord, literal) ?^
  goto enter
:enter
  freshCheck: requireNewValue(source, values, constants, name) ?^
  makeInfo: info = ValueInfo.new(name, code, isMutable, 2, valueWord, initIsName, initialized, no)
  enterIt: enterValue(source, values, info) ?^
  goto done
:done
  return
@reject unsupportedPayload mutabilityWord badMutability
@reject wrongType valueWord wrongType
@reject outsideSource valueWord outside

op lookupLabel "Read what is known of a label so far, or a fresh entry for a label not seen yet"
  input source String borrowed
  input labels Labels borrowed
  input word syntax.Word copied
  output LabelInfo
  raises syntax.Rejection
  let no Bool false
:begin
  @view text word outside
  getLabel: info = Labels.get(labels, text) ? fresh
  return info
:fresh
  makeFresh: freshInfo = LabelInfo.new(word, 0, word, no, word, no, word)
  return freshInfo
@reject outsideSource word outside

op addLabelFact "Check a label row of an operation and record what the emitter needs from it"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input labels Labels borrowedMutable
  raises syntax.Rejection
  let no Bool false
  let yes Bool true
:begin
  @wordAt labelWord 2
  enoughWords: expectAtLeast(row, 5, labelWord) ?^
  @wordAt factWord 3
  @wordAt payload 4
  findFact: fact = lookupFact(source, factWord) ?^
  readInfo: info = lookupLabel(source, labels, labelWord) ?^
  readKind: kind = LabelInfo.kind(info)
  readWithin: within = LabelInfo.within(info)
  readNested: nested = LabelInfo.nested(info)
  readBound: bound = LabelInfo.bound(info)
  readBounded: bounded = LabelInfo.bounded(info)
  readOver: over = LabelInfo.over(info)
  match fact
  case loopKind loopKindFact
  case within withinFact
  case maxIterations boundFact
  case over overFact
  case other done
:loopKindFact
  loopKindShape: expectCount(row, 5, payload) ?^
  findLoop: loopNumber = lookupLoop(source, payload) ?^
  makeKind: kindInfo = LabelInfo.new(labelWord, loopNumber, within, nested, bound, bounded, over)
  goto put
:withinFact
  withinShape: expectCount(row, 5, payload) ?^
  noneCheck: notNested = syntax.isText(source, payload, noneWord="none") ?^
  if notNested topLevel inside
:topLevel
  makeTop: topInfo = LabelInfo.new(labelWord, kind, labelWord, no, bound, bounded, over)
  goto putTop
:inside
  makeInside: insideInfo = LabelInfo.new(labelWord, kind, payload, yes, bound, bounded, over)
  goto putInside
:boundFact
  boundShape: expectCount(row, 5, payload) ?^
  unboundedCheck: isUnbounded = syntax.isText(source, payload, unboundedWord="unbounded") ?^
  if isUnbounded done keepBound
:keepBound
  makeBounded: boundedInfo = LabelInfo.new(labelWord, kind, within, nested, payload, yes, over)
  goto putBounded
:overFact
  overShape: expectCount(row, 5, payload) ?^
  makeOver: overInfo = LabelInfo.new(labelWord, kind, within, nested, bound, bounded, payload)
  goto putOver
:put
  @view kindKey labelWord outside
  putKind: Labels.put(labels, kindKey, kindInfo)
  goto done
:putTop
  @view topKey labelWord outside
  putTopInfo: Labels.put(labels, topKey, topInfo)
  goto done
:putInside
  @view insideKey labelWord outside
  putInsideInfo: Labels.put(labels, insideKey, insideInfo)
  goto done
:putBounded
  @view boundedKey labelWord outside
  putBoundedInfo: Labels.put(labels, boundedKey, boundedInfo)
  goto done
:putOver
  @view overKey labelWord outside
  putOverInfo: Labels.put(labels, overKey, overInfo)
  goto done
:done
  return
@reject outsideSource labelWord outside

op addBind "Enter the value a step binds: the item of a `branch ifNext`, or the payload of a `case` that binds one"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input typeNames TypeNames borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  raises syntax.Rejection
  let no Bool false
  let yes Bool true
:begin
  readCount: count = syntax.Row.count(row)
  shortCheck: tooShort = compare.lessThanInt64(count, 5)
  if tooShort done readVerb
:readVerb
  @wordAt verbWord 3
  branchCheck: isBranch = syntax.isText(source, verbWord, branchWord="branch") ?^
  if isBranch branchKind caseCheck
:branchKind
  enoughCheck: longEnough = compare.greaterThanInt64(count, 8)
  if longEnough readHow done
:readHow
  @wordAt howWord 4
  nextCheck: isNext = syntax.isText(source, howWord, ifNextWord="ifNext") ?^
  if isNext readNextBind done
:readNextBind
  @wordAt nextName 7
  @wordAt nextType 8
  findNextCode: nextCode = findType(source, typeNames, nextType) ?^
  freshNextCheck: requireNewValue(source, values, constants, nextName) ?^
  makeNextInfo: nextInfo = ValueInfo.new(nextName, nextCode, no, 5, nextName, no, yes, no)
  enterNext: enterValue(source, values, nextInfo) ?^
  goto done
:caseCheck
  caseTest: isCase = syntax.isText(source, verbWord, caseWord="case") ?^
  if isCase caseLength done
:caseLength
  caseEnough: caseLongEnough = compare.greaterThanInt64(count, 8)
  if caseLongEnough caseBind done
:caseBind
  @wordAt caseName 6
  noneCheck: bindsNone = syntax.isText(source, caseName, noneWord="none") ?^
  if bindsNone done readBind
:readBind
  @wordAt bindName 6
  @wordAt bindType 7
  findCode: code = findType(source, typeNames, bindType) ?^
  freshCheck: requireNewValue(source, values, constants, bindName) ?^
  makeInfo: info = ValueInfo.new(bindName, code, no, 5, bindName, no, yes, no)
  enter: enterValue(source, values, info) ?^
  goto done
:done
  return

op collectRows "Check the rows of an operation that state its inputs, labels, and lets, and enter the values its steps bind"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input types Types borrowed
  input typeNames TypeNames borrowed
  input params Params borrowed
  input targets Targets borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  input labels Labels borrowedMutable
  raises syntax.Rejection
:begin
  @rowsBegin
  case inputRow inputFact
  case labelRow labelFact
  case letRow letFact
  case atRow atFact
  others nextRow
:inputFact in=eachRow
  enterInput: addInput(source, words, row, typeNames, values, constants) ?^
  goto nextRow
:labelFact in=eachRow
  enterLabel: addLabelFact(source, words, row, labels) ?^
  goto nextRow
:letFact in=eachRow
  enterLet: addLet(source, words, row, types, typeNames, params, targets, values, constants) ?^
  goto nextRow
:atFact in=eachRow
  enterBind: addBind(source, words, row, typeNames, values, constants) ?^
  goto nextRow
:finish
  return
@rowsNext none

## ---------------------------------------------------------------- one operation: regions and calls

op addRegion "Enter a region of an operation as a value: its maxBytes, and whether it is released at return"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input values Values borrowedMutable
  input constants Values borrowed
  raises syntax.Rejection
  let capacity syntax.Word unset mut
  let released Bool true mut
  let no Bool false
  let yes Bool true
:begin
  readName: name = model.Entity.name(entity)
  set capacity name
  @rowsBegin
  case maxBytesRow capacityFact
  case releasedRow releaseFact
  others nextRow
:capacityFact in=eachRow
  @wordAt bytesWord 2
  set capacity bytesWord
  goto nextRow
:releaseFact in=eachRow
  @wordAt releaseWord 2
  returnCheck: atReturn = syntax.isText(source, releaseWord, atReturnWord="atReturn") ?^
  set released atReturn
  goto nextRow
:finish
  freshCheck: requireNewValue(source, values, constants, name) ?^
  makeInfo: info = ValueInfo.new(name, 6, no, 7, capacity, no, yes, released)
  enter: enterValue(source, values, info) ?^
  return
@rowsNext none

op catchFits "Decide whether a catch row's type word names the standard error a target raises"
  input source String borrowed
  input target TargetInfo copied
  input word syntax.Word copied
  output Bool
  raises syntax.Rejection
  let indexError String "list.IndexOutOfRange"
  let keyError String "map.KeyMissing"
:begin
  readKind: kind = TargetInfo.kind(target)
  match kind
  case builtin builtinError
  case mapGet mapError
  case mapRemove mapError
  case operation operationError
  case reference operationError
  others listError
:builtinError
  readOwner: row = TargetInfo.owner(target)
  readRow: entry = builtinTargets.rowAt(row) ? listError
  readError: error = BuiltinRow.error(entry)
  builtinCheck: builtinFits = syntax.isText(source, word, error) ?^
  return builtinFits
:mapError
  mapCheck: mapFits = syntax.isText(source, word, keyError) ?^
  return mapFits
:operationError
  operationCheck: operationFits = isStandardError(source, word) ?^
  return operationFits
:listError
  listCheck: listFits = syntax.isText(source, word, indexError) ?^
  return listFits

op checkCall "Check a call's rows against its target: the slot, type, and mode of each argument, the type of its result, and the type of its error; enter its result and caught error as values and the call itself"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input types Types borrowed
  input members Members borrowed
  input typeNames TypeNames borrowed
  input params Params borrowed
  input targets Targets borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  input calls Calls borrowedMutable
  input arguments Arguments borrowedMutable
  raises syntax.Rejection
  let wantType Int64 0 mut
  let wantMode Int64 0 mut
  let target TargetInfo unset mut
  let hasTarget Bool false mut
  let reference syntax.Word unset mut
  let argumentIndex Int64 0 mut
  let result syntax.Word unset mut
  let hasResult Bool false mut
  let catchName syntax.Word unset mut
  let hasCatch Bool false mut
  let no Bool false
  let yes Bool true
:begin
  readName: name = model.Entity.name(entity)
  set result name
  set catchName name
  set reference name
  firstCheck: firstArgument = Arguments.length(arguments)
  makeKind: placeholderKind = TargetKind.builtin()
  makePlaceholder: placeholder = TargetInfo.new(placeholderKind, 0, 0, 0, 0, 0, 0)
  set target placeholder
  @rowsBegin
  case invokesRow invokes
  case invokesReferenceRow invokesReference
  case argumentRow argument
  case resultRow resultFact
  case catchRow catchFact
  others nextRow
:invokes in=eachRow
  @wordAt targetWord 2
  invokesShape: expectCount(row, 3, targetWord) ?^
  @view targetText targetWord outside
  findTarget: found = Targets.get(targets, targetText) ? unknownTarget
  set target found
  set hasTarget yes
  goto nextRow
:invokesReference in=eachRow
  @wordAt referenceWord 2
  referenceShape: expectCount(row, 3, referenceWord) ?^
  findReference: referenceInfo = findValue(source, values, constants, referenceWord) ?^
  readReferenceCode: referenceCode = ValueInfo.code(referenceInfo)
  readReferenceType: referenceType = typeInfoOf(types, referenceCode)
  readReferenceKind: referenceKind = TypeInfo.kind(referenceType)
  referenceCheck: isReference = compare.equalInt64(referenceKind, 8)
  if isReference throughReference notReference
:throughReference in=eachRow
  readReferenceFirst: referenceFirst = TypeInfo.first(referenceType)
  readReferenceCount: referenceCount = TypeInfo.count(referenceType)
  readReferenceOutput: referenceOutput = TypeInfo.item(referenceType)
  readReferenceRaises: referenceRaises = TypeInfo.raises(referenceType)
  makeReferenceKind: referenceTargetKind = TargetKind.reference()
  makeReferenceTarget: referenceTarget = TargetInfo.new(referenceTargetKind, referenceCode, 0, referenceFirst, referenceCount, referenceOutput, referenceRaises)
  set target referenceTarget
  set hasTarget yes
  set reference referenceWord
  goto nextRow
:argument in=eachRow
  if hasTarget argumentShape lost
:argumentShape in=eachRow
  readArgumentCount: argumentCount = syntax.Row.count(row)
  noArgumentCheck: noArgument = compare.equalInt64(argumentCount, 3)
  if noArgument argumentNone argumentSlot
:argumentNone in=eachRow
  argumentFixed: checkWord(source, words, row, noneWord="none") ?^
  goto nextRow
:argumentSlot in=eachRow
  @wordAt slotWord 2
  argumentFits: expectCount(row, 6, slotWord) ?^
  @wordAt typeWord 3
  @wordAt valueWord 4
  @wordAt modeWord 5
  readParamCount: paramCount = TargetInfo.paramCount(target)
  overCheck: tooMany = compare.greaterOrEqualInt64(argumentIndex, paramCount)
  if tooMany wrongCount readParam
:readParam in=eachRow
  readTargetKind: targetKind = TargetInfo.kind(target)
  secondCheck: isSecond = compare.equalInt64(argumentIndex, 1)
  match targetKind
  case recordWith withSlotCheck
  others plainParam
:withSlotCheck in=eachRow
  if isSecond withField plainParam
:withField in=eachRow
  readWithOwner: withOwner = TargetInfo.owner(target)
  findField: fieldIndex = lookupMember(source, types, members, withOwner, slotWord) ?^
  readField: field = Members.getOrTrap(members, fieldIndex)
  readFieldType: fieldType = MemberInfo.type(field)
  fieldModeCheck: fieldMode = readMode(types, fieldType)
  set wantType fieldType
  set wantMode fieldMode
  set reference slotWord
  goto typeCheck
:plainParam in=eachRow
  readFirstParam: firstParam = TargetInfo.firstParam(target)
  findParam: paramIndex = math.addInt64(firstParam, argumentIndex)
  readParamInfo: param = Params.getOrTrap(params, paramIndex)
  readSlot: slot = ParamInfo.slot(param)
  readType: paramType = ParamInfo.type(param)
  readParamMode: paramMode = ParamInfo.mode(param)
  set wantType paramType
  set wantMode paramMode
  slotCheck: slotFits = syntax.isText(source, slotWord, slot) ?^
  if slotFits typeCheck mismatchSlot
:typeCheck in=eachRow
  findArgumentType: argumentCode = findType(source, typeNames, typeWord) ?^
  typeFitCheck: typeFits = compare.equalInt64(argumentCode, wantType)
  if typeFits modeCheck mismatchType
:modeCheck in=eachRow
  findMode: modeCode = modeOf(source, modeWord) ?^
  modeFitCheck: modeFits = compare.equalInt64(modeCode, wantMode)
  if modeFits keepArgument mismatchMode
:keepArgument in=eachRow
  makeArgument: argumentInfo = ArgumentInfo.new(valueWord, wantType)
  appendArgument: Arguments.append(arguments, argumentInfo)
  countArgument: nextArgument = math.addInt64(argumentIndex, 1)
  set argumentIndex nextArgument
  goto nextRow
:resultFact in=eachRow
  if hasTarget resultShape lost
:resultShape in=eachRow
  @wordAt resultWord 2
  readOutput: output = TargetInfo.output(target)
  readResultCount: resultCount = syntax.Row.count(row)
  noResultCheck: noResult = compare.equalInt64(resultCount, 3)
  if noResult resultNone resultValue
:resultNone in=eachRow
  resultFixed: checkWord(source, words, row, noneWord) ?^
  nothingCheck: givesNothing = compare.equalInt64(output, 0)
  if givesNothing nextRow wrongResult
:resultValue in=eachRow
  resultFits: expectCount(row, 4, resultWord) ?^
  @wordAt resultType 3
  findResultType: resultCode = findType(source, typeNames, resultType) ?^
  resultTypeCheck: resultTypeFits = compare.equalInt64(resultCode, output)
  if resultTypeFits enterResult wrongResultType
:enterResult in=eachRow
  freshResult: requireNewValue(source, values, constants, resultWord) ?^
  makeResult: resultInfo = ValueInfo.new(resultWord, resultCode, no, 3, resultWord, no, yes, no)
  enterResultValue: enterValue(source, values, resultInfo) ?^
  set result resultWord
  set hasResult yes
  goto nextRow
:catchFact in=eachRow
  if hasTarget catchShape lost
:catchShape in=eachRow
  @wordAt catchWord 2
  readRaises: raises = TargetInfo.raises(target)
  readCatchCount: catchCount = syntax.Row.count(row)
  noCatchCheck: noCatch = compare.equalInt64(catchCount, 3)
  if noCatch catchNone catchValue
:catchNone in=eachRow
  catchFixed: checkWord(source, words, row, noneWord) ?^
  goto nextRow
:catchValue in=eachRow
  catchShapeCheck: expectCount(row, 4, catchWord) ?^
  @wordAt catchType 3
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  if canFail errorKind cannotFail
:errorKind in=eachRow
  standardCheck: isStandard = compare.equalInt64(raises, 7)
  if isStandard standardError moduleError
:standardError in=eachRow
  errorTextCheck: standardFits = catchFits(source, target, catchType) ?^
  if standardFits enterCatch wrongCatchType
:moduleError in=eachRow
  findCatchType: catchCode = findType(source, typeNames, catchType) ?^
  catchTypeCheck: catchTypeFits = compare.equalInt64(catchCode, raises)
  if catchTypeFits enterCatch wrongCatchType
:enterCatch in=eachRow
  freshCatch: requireNewValue(source, values, constants, catchWord) ?^
  makeCatch: catchInfo = ValueInfo.new(catchWord, raises, no, 6, catchWord, no, yes, no)
  enterCatchValue: enterValue(source, values, catchInfo) ?^
  set catchName catchWord
  set hasCatch yes
  goto nextRow
:finish
  if hasTarget countCheck lost
:countCheck
  readFinalCount: expected = TargetInfo.paramCount(target)
  arityCheck: arityFits = compare.equalInt64(argumentIndex, expected)
  if arityFits enterCall wrongArity
:enterCall
  @view callText name outside
  takenCheck: taken = Calls.contains(calls, callText)
  if taken duplicate putCall
:putCall
  makeInfo: info = CallInfo.new(name, target, reference, firstArgument, argumentIndex, result, hasResult, catchName, hasCatch)
  putIt: Calls.put(calls, callText, info)
  return
@reject unsupportedTarget targetWord unknownTarget
@reject wrongType referenceWord notReference
@reject outsideSource name outside
@reject lostName name lost
@reject argumentCount slotWord wrongCount
@reject wrongArgument slotWord mismatchSlot
@reject wrongArgument typeWord mismatchType
@reject wrongArgument modeWord mismatchMode
@reject wrongType resultWord wrongResult
@reject wrongType resultType wrongResultType
@reject notFailing catchWord cannotFail
@reject wrongType catchType wrongCatchType
@reject argumentCount name wrongArity
@reject duplicateName name duplicate
@rowsNext none

op collectOwned "Enter the regions of an operation as values, and check its calls; both are entities of the operation's module"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input owners Owners borrowed
  input op OpInfo copied
  input opIndex Int64 copied
  input types Types borrowed
  input members Members borrowed
  input typeNames TypeNames borrowed
  input params Params borrowed
  input targets Targets borrowed
  input values Values borrowedMutable
  input constants Values borrowed
  input calls Calls borrowedMutable
  input arguments Arguments borrowedMutable
  raises syntax.Rejection
  let entityIndex Int64 0 mut
:begin
  readFirst: first = OpInfo.moduleFirst(op)
  readEnd: end = OpInfo.moduleEnd(op)
  findSpan: span = math.subtractInt64(end, first)
  set entityIndex first
  goto eachRegion
:eachRegion loop=while max=span
  regionsDoneCheck: allRegions = compare.greaterOrEqualInt64(entityIndex, end)
  if allRegions regionsDone readRegionOwner
:readRegionOwner in=eachRegion
  readRegionEntity: regionEntity = model.Entities.getOrTrap(entities, entityIndex)
  readRegionOwnerIndex: regionOwner = Owners.getOrTrap(owners, entityIndex)
  countRegionEntity: nextRegionEntity = math.addInt64(entityIndex, 1)
  set entityIndex nextRegionEntity
  regionMine: regionIsMine = compare.equalInt64(regionOwner, opIndex)
  if regionIsMine regionKind eachRegion
:regionKind in=eachRegion
  readRegionKind: regionEntityKind = model.Entity.kind(regionEntity)
  isRegionCheck: isRegion = compare.equalInt64(regionEntityKind, 9)
  if isRegion enterRegion eachRegion
:enterRegion in=eachRegion
  enterRegionValue: addRegion(source, words, rows, regionEntity, values, constants) ?^
  goto eachRegion
:regionsDone
  set entityIndex first
  goto eachCall
:eachCall loop=while max=span
  callsDoneCheck: allCalls = compare.greaterOrEqualInt64(entityIndex, end)
  if allCalls done readCallOwner
:readCallOwner in=eachCall
  readCallEntity: callEntity = model.Entities.getOrTrap(entities, entityIndex)
  readCallOwnerIndex: callOwner = Owners.getOrTrap(owners, entityIndex)
  countCallEntity: nextCallEntity = math.addInt64(entityIndex, 1)
  set entityIndex nextCallEntity
  callMine: callIsMine = compare.equalInt64(callOwner, opIndex)
  if callIsMine callKind eachCall
:callKind in=eachCall
  readCallKind: callEntityKind = model.Entity.kind(callEntity)
  isCallCheck: isCall = compare.equalInt64(callEntityKind, 5)
  isTaskCheck: isTask = compare.equalInt64(callEntityKind, 10)
  callOrTask: runs = logic.or(isCall, isTask)
  if runs enterCall eachCall
:enterCall in=eachCall
  checkTheCall: checkCall(source, words, rows, callEntity, types, members, typeNames, params, targets, values, constants, calls, arguments) ?^
  goto eachCall
:done
  return

## ---------------------------------------------------------------- one operation: steps

op checkCallValues "Refuse a call whose arguments name values that do not exist or have other types than their slots"
  input source String borrowed
  input values Values borrowed
  input constants Values borrowed
  input arguments Arguments borrowed
  input info CallInfo copied
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  readFirst: first = CallInfo.firstArgument(info)
  readArity: arity = CallInfo.arity(info)
  goto eachArgument
:eachArgument loop=while max=arity
  doneCheck: allChecked = compare.greaterOrEqualInt64(index, arity)
  if allChecked done readArgument
:readArgument in=eachArgument
  findArgument: argumentIndex = math.addInt64(first, index)
  readArgumentInfo: argument = Arguments.getOrTrap(arguments, argumentIndex)
  readValueWord: valueWord = ArgumentInfo.value(argument)
  readExpected: expected = ArgumentInfo.code(argument)
  findTheValue: value = findValue(source, values, constants, valueWord) ?^
  readCode: code = ValueInfo.code(value)
  typeCheck: fits = compare.equalInt64(code, expected)
  if fits advance wrong
:advance in=eachArgument
  countArgument: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachArgument
:done
  return
@reject wrongType valueWord wrong

op requireLabel "Refuse a word that names no label of the operation"
  input source String borrowed
  input labels Labels borrowed
  input word syntax.Word copied
  raises syntax.Rejection
:begin
  @view text word outside
  hasLabel: known = Labels.contains(labels, text)
  if known done unknown
:done
  return
@reject unknownLabel word unknown
@reject outsideSource word outside

op findCall "Find a call of the operation by the name a word spells"
  input source String borrowed
  input calls Calls borrowed
  input word syntax.Word copied
  output CallInfo
  raises syntax.Rejection
:begin
  @view text word outside
  getCall: info = Calls.get(calls, text) ? unknown
  return info
@reject unknownCall word unknown
@reject outsideSource word outside

op findLabel "Find a label of the operation by the name a word spells"
  input source String borrowed
  input labels Labels borrowed
  input word syntax.Word copied
  output LabelInfo
  raises syntax.Rejection
:begin
  @view text word outside
  getLabel: info = Labels.get(labels, text) ? unknown
  return info
@reject unknownLabel word unknown
@reject outsideSource word outside

op valueCode "The type of the value a word names"
  input source String borrowed
  input values Values borrowed
  input constants Values borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
:begin
  findTheValue: info = findValue(source, values, constants, word) ?^
  readCode: code = ValueInfo.code(info)
  return code

op checkStep "Check one step of an operation and return it with the words it names"
  input source String borrowed
  input words syntax.Words borrowed
  input row syntax.Row copied
  input types Types borrowed
  input members Members borrowed
  input targets Targets borrowed
  input op OpInfo copied
  input values Values borrowed
  input constants Values borrowed
  input calls Calls borrowed
  input arguments Arguments borrowed
  input labels Labels borrowed
  input matchValue syntax.Word copied
  input matchCode Int64 copied
  input typeNames TypeNames borrowed
  output Step
  raises syntax.Rejection
:begin
  @wordAt labelWord 2
  enoughWords: expectAtLeast(row, 5, labelWord) ?^
  @wordAt verbWord 3
  labelCheck: requireLabel(source, labels, labelWord) ?^
  findVerb: verb = lookupStep(source, verbWord) ?^
  match verb
  case doCall doStep
  case setValue setStep
  case jump jumpStep
  case branchIf branchStep
  case matchValue matchStep
  case caseOf caseStep
  case returnOk returnStep
  case startTask startStep
  case joinTask joinStep
  others unsupported
:startStep
  startShape: expectCount(row, 7, verbWord) ?^
  @wordAt startedWord 4
  @wordAt intoWord 5
  @wordAt slotWord 6
  intoCheck: saysInto = syntax.isText(source, intoWord, intoText="into") ?^
  slotCheck: noSlot = syntax.isText(source, slotWord, noneWord="none") ?^
  bothCheck: startFits = logic.and(saysInto, noSlot)
  if startFits startTaskFound badStart
:startTaskFound
  findStarted: startedInfo = findCall(source, calls, startedWord) ?^
  checkStartedValues: checkCallValues(source, values, constants, arguments, startedInfo) ?^
  makeStart: startDone = Step.new(labelWord, verb, startedWord, labelWord, labelWord, labelWord, 0, 0)
  return startDone
:joinStep
  joinShape: expectCount(row, 5, verbWord) ?^
  @wordAt joinedWord 4
  findJoined: joinedInfo = findCall(source, calls, joinedWord) ?^
  makeJoin: joinDone = Step.new(labelWord, verb, joinedWord, labelWord, labelWord, labelWord, 0, 0)
  return joinDone
:doStep
  doShape: expectCount(row, 5, verbWord) ?^
  @wordAt callWord 4
  findTheCall: callInfo = findCall(source, calls, callWord) ?^
  checkValues: checkCallValues(source, values, constants, arguments, callInfo) ?^
  makeDo: doneStep = Step.new(labelWord, verb, callWord, labelWord, labelWord, labelWord, 0, 0)
  return doneStep
:setStep
  setShape: expectCount(row, 6, verbWord) ?^
  @wordAt targetWord 4
  @wordAt sourceWord 5
  findTarget: targetInfo = findValue(source, values, constants, targetWord) ?^
  findSource: sourceInfo = findValue(source, values, constants, sourceWord) ?^
  readMutable: changeable = ValueInfo.mutable(targetInfo)
  if changeable setTypes immutable
:setTypes
  targetCode: toCode = ValueInfo.code(targetInfo)
  sourceCode: fromCode = ValueInfo.code(sourceInfo)
  setTypeCheck: setFits = compare.equalInt64(toCode, fromCode)
  if setFits makeSetStep setWrongType
:makeSetStep
  makeSet: setDone = Step.new(labelWord, verb, targetWord, sourceWord, labelWord, labelWord, 0, 0)
  return setDone
:jumpStep
  jumpShape: expectCount(row, 5, verbWord) ?^
  @wordAt toWord 4
  toCheck: requireLabel(source, labels, toWord) ?^
  makeJump: jumpDone = Step.new(labelWord, verb, labelWord, toWord, labelWord, labelWord, 0, 0)
  return jumpDone
:branchStep
  branchLength: expectAtLeast(row, 11, verbWord) ?^
  @wordAt howWord 4
  @wordAt conditionWord 5
  ifCheck: onValue = syntax.isText(source, howWord, ifText="if") ?^
  if onValue branchOnValue notIf
:notIf
  ifErrorCheck: onError = syntax.isText(source, howWord, ifErrorText="ifError") ?^
  if onError branchOnError notIfError
:notIfError
  ifNextCheck: onNext = syntax.isText(source, howWord, ifNextText="ifNext") ?^
  if onNext branchOnNext badBranch
:branchOnValue
  ifShape: expectCount(row, 11, howWord) ?^
  @wordAt yesWord 7
  @wordAt noWord 10
  yesCheck: requireLabel(source, labels, yesWord) ?^
  noCheck: requireLabel(source, labels, noWord) ?^
  conditionCode: boolCode = valueCode(source, values, constants, conditionWord) ?^
  boolCheck: isBool = compare.equalInt64(boolCode, 4)
  if isBool makeBranchIf conditionWrongType
:makeBranchIf
  makeIf: ifDone = Step.new(labelWord, verb, conditionWord, yesWord, noWord, labelWord, 0, 0)
  return ifDone
:branchOnError
  ifErrorShape: expectCount(row, 11, howWord) ?^
  @wordAt errorYesWord 7
  @wordAt errorNoWord 10
  errorYesCheck: requireLabel(source, labels, errorYesWord) ?^
  errorNoCheck: requireLabel(source, labels, errorNoWord) ?^
  findFailing: failing = findCall(source, calls, conditionWord) ?^
  readFailingTarget: failingTarget = CallInfo.target(failing)
  readRaises: raises = TargetInfo.raises(failingTarget)
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  if canFail makeBranchIfError cannotFail
:makeBranchIfError
  makeIfErrorVerb: ifErrorVerb = StepVerb.branchIfError()
  makeIfError: ifErrorDone = Step.new(labelWord, ifErrorVerb, conditionWord, errorYesWord, errorNoWord, labelWord, 0, 0)
  return ifErrorDone
:branchOnNext
  ifNextShape: expectCount(row, 14, howWord) ?^
  @wordAt itemWord 7
  @wordAt nextYesWord 10
  @wordAt nextNoWord 13
  nextYesCheck: requireLabel(source, labels, nextYesWord) ?^
  nextNoCheck: requireLabel(source, labels, nextNoWord) ?^
  readLoop: loopInfo = findLabel(source, labels, labelWord) ?^
  readLoopKind: loopKind = LabelInfo.kind(loopInfo)
  forEachCheck: isForEach = compare.equalInt64(loopKind, 5)
  if isForEach collectionCheck notForEach
:collectionCheck
  collectionKnown: isValue = knowsValue(source, values, constants, conditionWord) ?^
  if isValue listCollection tableCollection
:listCollection
  collectionCode: listCode = valueCode(source, values, constants, conditionWord) ?^
  readListInfo: listInfo = typeInfoOf(types, listCode)
  readListKind: listKind = TypeInfo.kind(listInfo)
  listCheck: isList = compare.equalInt64(listKind, 5)
  if isList itemCheck mapCollectionCheck
:mapCollectionCheck
  mapCheck: isMap = compare.equalInt64(listKind, 7)
  if isMap mapKeyCheck notList
:mapKeyCheck
  readKey: keyCode = TypeInfo.item(listInfo)
  keyBound: boundKeyCode = valueCode(source, values, constants, itemWord) ?^
  keyTypeCheck: keyFits = compare.equalInt64(boundKeyCode, keyCode)
  if keyFits makeMapNextStep itemWrongType
:makeMapNextStep
  makeMapNextVerb: mapNextVerb = StepVerb.branchIfNext()
  makeMapNext: mapNextDone = Step.new(labelWord, mapNextVerb, conditionWord, nextYesWord, nextNoWord, itemWord, listCode, keyCode)
  return mapNextDone
:itemCheck
  readItem: item = TypeInfo.item(listInfo)
  itemCode: boundCode = valueCode(source, values, constants, itemWord) ?^
  itemTypeCheck: itemFits = compare.equalInt64(boundCode, item)
  if itemFits makeBranchIfNext itemWrongType
:makeBranchIfNext
  makeIfNextVerb: ifNextVerb = StepVerb.branchIfNext()
  makeIfNext: ifNextDone = Step.new(labelWord, ifNextVerb, conditionWord, nextYesWord, nextNoWord, itemWord, 0, item)
  return ifNextDone
:tableCollection
  findTable: tableCode = findType(source, typeNames, conditionWord) ?^
  readTableInfo: tableInfo = typeInfoOf(types, tableCode)
  readTableKind: tableKind = TypeInfo.kind(tableInfo)
  tableCheck: isTable = compare.equalInt64(tableKind, 6)
  if isTable rowCheck notList
:rowCheck
  readRowType: rowType = TypeInfo.item(tableInfo)
  rowCode: boundRowCode = valueCode(source, values, constants, itemWord) ?^
  rowTypeCheck: rowFits = compare.equalInt64(boundRowCode, rowType)
  if rowFits makeTableNextStep itemWrongType
:makeTableNextStep
  makeTableNextVerb: tableNextVerb = StepVerb.branchIfNext()
  makeTableNext: tableNextDone = Step.new(labelWord, tableNextVerb, conditionWord, nextYesWord, nextNoWord, itemWord, tableCode, rowType)
  return tableNextDone
:matchStep
  matchShape: expectCount(row, 6, verbWord) ?^
  @wordAt matchedWord 4
  @wordAt matchedType 5
  matchedCode: enumCode = valueCode(source, values, constants, matchedWord) ?^
  readEnumInfo: enumInfo = typeInfoOf(types, enumCode)
  readEnumKind: enumKind = TypeInfo.kind(enumInfo)
  enumCheck: isEnum = compare.equalInt64(enumKind, 4)
  if isEnum makeMatch matchWrongType
:makeMatch
  makeMatchStep: matchDone = Step.new(labelWord, verb, matchedWord, labelWord, labelWord, labelWord, 0, enumCode)
  return matchDone
:caseStep
  caseShape: expectCount(row, 10, verbWord) ?^
  @wordAt variantWord 4
  @wordAt bindWord 6
  @wordAt caseLabel 9
  caseLabelCheck: requireLabel(source, labels, caseLabel) ?^
  @view variantText variantWord outside
  findVariant: variantTarget = Targets.get(targets, variantText) ? unknownVariant
  readVariantKind: variantKind = TargetInfo.kind(variantTarget)
  match variantKind
  case variantMake variantOwner
  others unknownVariant
:variantOwner
  readOwner: owner = TargetInfo.owner(variantTarget)
  ownerCheck: sameEnum = compare.equalInt64(owner, matchCode)
  if sameEnum readVariant unknownVariant
:readVariant
  readMemberIndex: memberIndex = TargetInfo.member(variantTarget)
  readMember: member = Members.getOrTrap(members, memberIndex)
  readPayload: payloadCode = MemberInfo.type(member)
  bindNoneCheck: bindsNone = syntax.isText(source, bindWord, noneWord="none") ?^
  if bindsNone noBind someBind
:noBind
  payloadNoneCheck: payloadNone = compare.equalInt64(payloadCode, 0)
  if payloadNone makeBareCase bindWrongType
:makeBareCase
  makeBare: bareDone = Step.new(labelWord, verb, matchValue, caseLabel, variantWord, labelWord, memberIndex, 0)
  return bareDone
:someBind
  bindCode: boundType = valueCode(source, values, constants, bindWord) ?^
  bindTypeCheck: bindFits = compare.equalInt64(boundType, payloadCode)
  if bindFits makeBindCase bindWrongType
:makeBindCase
  makeBound: boundDone = Step.new(labelWord, verb, matchValue, caseLabel, variantWord, bindWord, memberIndex, payloadCode)
  return boundDone
:returnStep
  returnShape: expectCount(row, 6, verbWord) ?^
  @wordAt howReturn 4
  @wordAt resultWord 5
  okCheck: isOk = syntax.isText(source, howReturn, okText="ok") ?^
  readOutput: output = OpInfo.output(op)
  if isOk returnOk errorCheck
:returnOk
  noneCheck: returnsNone = syntax.isText(source, resultWord, noneWord) ?^
  if returnsNone returnNothing returnValue
:returnNothing
  nothingCheck: givesNothing = compare.equalInt64(output, 0)
  if givesNothing makeReturnNone resultWrongType
:makeReturnNone
  makeNone: noneDone = Step.new(labelWord, verb, resultWord, labelWord, labelWord, labelWord, 1, 0)
  return noneDone
:returnValue
  resultCode: returnedCode = valueCode(source, values, constants, resultWord) ?^
  resultCheck: resultFits = compare.equalInt64(returnedCode, output)
  if resultFits makeReturnValue resultWrongType
:makeReturnValue
  makeValue: valueDone = Step.new(labelWord, verb, resultWord, labelWord, labelWord, labelWord, 0, output)
  return valueDone
:errorCheck
  errorTest: isError = syntax.isText(source, howReturn, errorWord="error") ?^
  if isError returnError badReturn
:returnError
  readRaises2: opRaises = OpInfo.raises(op)
  errorCode: raisedCode = valueCode(source, values, constants, resultWord) ?^
  raisesSomething: canRaise = compare.notEqualInt64(opRaises, 0)
  sameError: errorFits = compare.equalInt64(raisedCode, opRaises)
  bothFit: raiseFits = logic.and(canRaise, errorFits)
  if raiseFits makeReturnError resultWrongType
:makeReturnError
  makeErrorVerb: errorVerb = StepVerb.returnError()
  makeError: errorDone = Step.new(labelWord, errorVerb, resultWord, labelWord, labelWord, labelWord, 0, opRaises)
  return errorDone
@reject unsupportedStep verbWord unsupported
@reject unsupportedStep slotWord badStart
@reject notMutable targetWord immutable
@reject wrongType sourceWord setWrongType
@reject unsupportedStep howWord badBranch
@reject wrongType conditionWord conditionWrongType
@reject notFailing conditionWord cannotFail
@reject unsupportedLoop labelWord notForEach
@reject unsupportedLoop conditionWord notList
@reject wrongType itemWord itemWrongType
@reject wrongType matchedWord matchWrongType
@reject unknownVariant variantWord unknownVariant
@reject outsideSource variantWord outside
@reject wrongType bindWord bindWrongType
@reject wrongType resultWord resultWrongType
@reject unsupportedStep howReturn badReturn

op collectSteps "Check the steps of an operation in order, refusing a label whose steps are not together"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input types Types borrowed
  input members Members borrowed
  input targets Targets borrowed
  input op OpInfo copied
  input values Values borrowed
  input constants Values borrowed
  input calls Calls borrowed
  input arguments Arguments borrowed
  input labels Labels borrowed
  input steps Steps borrowedMutable
  input typeNames TypeNames borrowed
  raises syntax.Rejection
  region scratch 16777216
  let previousLabel syntax.Word unset mut
  let matchValue syntax.Word unset mut
  let matchCode Int64 0 mut
  let blockCount Int64 0 mut
:begin
  readName: name = model.Entity.name(entity)
  set previousLabel name
  set matchValue name
  newBlocks: blocks = Blocks.new(scratch)
  @rowsBegin
  case atRow stepRow
  others nextRow
:stepRow in=eachRow
  checkTheStep: step = checkStep(source, words, row, types, members, targets, op, values, constants, calls, arguments, labels, matchValue, matchCode, typeNames) ?^
  appendStep: Steps.append(steps, step)
  readStepVerb: stepVerb = Step.verb(step)
  match stepVerb
  case matchValue rememberMatch
  others blockCheck
:rememberMatch in=eachRow
  readMatched: matched = Step.subject(step)
  readMatchedCode: matchedCode = Step.code(step)
  set matchValue matched
  set matchCode matchedCode
  goto blockCheck
:blockCheck in=eachRow
  readStepLabel: stepLabel = Step.label(step)
  @view labelText stepLabel outside
  seenCheck: seen = Blocks.contains(blocks, labelText)
  if seen sameBlockCheck newBlock
:sameBlockCheck in=eachRow
  sameBlock: continues = syntax.sameText(source, stepLabel, previousLabel) ?^
  if continues nextRow split
:newBlock in=eachRow
  enterBlock: Blocks.put(blocks, labelText, blockCount)
  countBlock: nextBlockCount = math.addInt64(blockCount, 1)
  set blockCount nextBlockCount
  set previousLabel stepLabel
  goto nextRow
:finish
  hasBegin: beginKnown = Blocks.contains(blocks, beginName="begin")
  if beginKnown done noBegin
:done
  return
@reject splitBlock stepLabel split
@reject outsideSource stepLabel outside
@reject unknownLabel name noBegin
@rowsNext none

op checkOperation "Check one operation: its inputs, lets, labels, regions, calls, and steps, collecting what the emitter writes"
  invariant collectsOperation "Enters every input, let, region, call result, caught error, and value a step binds in values, every call with its arguments in calls and arguments, every label with its loop kind, bound, and enclosing loop in labels, and every step in steps, in source order"
  invariant checksOperation "Literals fit their types; arguments match their target's slots, types, and modes and name values of those types; results, errors, returns, conditions, matches, cases, and forEach items have the types their steps need; `set` changes only mutable lets; a label's steps are together"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types Types borrowed
  input typeNames TypeNames borrowed
  input members Members borrowed
  input params Params borrowed
  input targets Targets borrowed
  input ops Ops borrowed
  input owners Owners borrowed
  input constants Values borrowed
  input opIndex Int64 copied
  input values Values borrowedMutable
  input calls Calls borrowedMutable
  input arguments Arguments borrowedMutable
  input labels Labels borrowedMutable
  input steps Steps borrowedMutable
  raises syntax.Rejection
:begin
  readOp: op = Ops.getOrTrap(ops, opIndex)
  readEntityIndex: entityIndex = OpInfo.entity(op)
  readEntity: entity = model.Entities.getOrTrap(entities, entityIndex)
  rowsCheck: collectRows(source, words, rows, entity, types, typeNames, params, targets, values, constants, labels) ?^
  ownedCheck: collectOwned(source, words, rows, entities, owners, op, opIndex, types, members, typeNames, params, targets, values, constants, calls, arguments) ?^
  stepsCheck: collectSteps(source, words, rows, entity, types, members, targets, op, values, constants, calls, arguments, labels, steps, typeNames) ?^
  return

op checkProgram "Check that a modelled program is in the stage0 subset: each module in source order, its declarations and then each of its operations"
  invariant acceptsSubset "A program of modules of records, enums, list and map typeInstances, tables, operationTypes, constants, and operations calling the subset's targets and each other is accepted"
  invariant rejectsOutsideSubset "The first declaration or step outside the subset is refused at the word concerned"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  raises syntax.Rejection
  region work 1073741824
  let first Int64 0 mut
:begin
  newTypes: types = Types.new(work)
  newMembers: members = Members.new(work)
  newParams: params = Params.new(work)
  newOps: ops = Ops.new(work)
  newOwners: owners = Owners.new(work)
  newTypeNames: globalTypeNames = TypeNames.new(work)
  newTargets: globalTargets = Targets.new(work)
  declareAll: declareBuiltins(source, types, globalTypeNames, params, globalTargets, work) ?^
  countEntities: count = model.Entities.length(entities)
  goto eachModule
:eachModule loop=while max=count
  doneCheck: allDone = compare.greaterOrEqualInt64(first, count)
  if allDone done checkOne
:checkOne in=eachModule
  findEnd: end = nextModule(entities, first)
  checkIt: checkOneModule(source, words, rows, entities, first, end, types, members, params, ops, owners, globalTypeNames, globalTargets) ?^
  set first end
  goto eachModule
:done
  return

op checkOneModule "Check one module of a program: its declarations, then each of its operations, with names of its own released when it is checked"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input first Int64 copied
  input end Int64 copied
  input types Types borrowedMutable
  input members Members borrowedMutable
  input params Params borrowedMutable
  input ops Ops borrowedMutable
  input owners Owners borrowedMutable
  input globalTypeNames TypeNames borrowedMutable
  input globalTargets Targets borrowedMutable
  raises syntax.Rejection
  region moduleWork 1073741824
  let opIndex Int64 0 mut
:begin
  newTypeNames: typeNames = TypeNames.new(moduleWork)
  newTargets: targets = Targets.new(moduleWork)
  newOpNames: opNames = OpNames.new(moduleWork)
  newConstants: constants = Values.new(moduleWork)
  countBefore: opBase = Ops.length(ops)
  set opIndex opBase
  declare: checkModuleDeclarations(source, words, rows, entities, first, end, types, typeNames, members, params, targets, ops, opNames, owners, constants, globalTypeNames, globalTargets, moduleWork) ?^
  countOps: opCount = Ops.length(ops)
  goto eachOp
:eachOp loop=while max=opCount
  doneCheck: allChecked = compare.greaterOrEqualInt64(opIndex, opCount)
  if allChecked done checkOne
:checkOne in=eachOp
  checkThis: checkOneOperation(source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex) ?^
  countOp: nextOp = math.addInt64(opIndex, 1)
  set opIndex nextOp
  goto eachOp
:done
  return

op checkOneOperation "Check one operation into collections of its own, released when it is checked"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types Types borrowed
  input typeNames TypeNames borrowed
  input members Members borrowed
  input params Params borrowed
  input targets Targets borrowed
  input ops Ops borrowed
  input owners Owners borrowed
  input constants Values borrowed
  input opIndex Int64 copied
  raises syntax.Rejection
  region opWork 268435456
:begin
  newValues: values = Values.new(opWork)
  newCalls: calls = Calls.new(opWork)
  newArguments: arguments = Arguments.new(opWork)
  newLabels: labels = Labels.new(opWork)
  newSteps: steps = Steps.new(opWork)
  check: checkOperation(source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex, values, calls, arguments, labels, steps) ?^
  return

op diagnose "Run the front end on a program's source and describe the first problem, or say it was accepted"
  invariant reportsFirstProblem "Returns `accepted` for a program in the subset; otherwise the first problem the lexer, rows, model, or subset check finds, as `line:column: message (word)`"
  input source String borrowed
  input region Region borrowed
  output String
  owner region
  let acceptedText String "accepted"
  let lexText String "the lexer refused the source"
:begin
  lex: tokens = lexer.tokenize(source, region) ? lexFailed
  newWords: words = syntax.Words.new(region)
  newRows: rows = syntax.Rows.new(region)
  group: syntax.groupRows(source, tokens, words, rows) ! groupError
  iferr group refusedGroup modelIt
:modelIt
  newEntities: entities = model.Entities.new(region)
  newNames: names = model.EntityNames.new(region)
  buildIt: model.buildModel(source, words, rows, entities, names) ! buildError
  iferr buildIt refusedModel checkIt
:checkIt
  checkAll: checkProgram(source, words, rows, entities) ! checkError
  iferr checkAll refusedCheck accepted
:accepted
  return acceptedText
:lexFailed
  return lexText
:refusedGroup
  describeGroup: groupText = syntax.diagnostic(source, groupError, region)
  return groupText
:refusedModel
  describeModel: modelText = syntax.diagnostic(source, buildError, region)
  return modelText
:refusedCheck
  describeCheck: checkText = syntax.diagnostic(source, checkError, region)
  return checkText
