module emitc "Write a checked stage0 module as one C file"
  path emitc
  imports standard.string standard.buffer standard.list standard.map standard.math standard.compare standard.logic standard.test lexer syntax model subset
  exports emitModule

## ---------------------------------------------------------------- C spellings

record CTarget "How a standard library target is written in C: the text before, between, and after its arguments; or, for a target of the host library, the name refined_host dispatches on, with how many 64-bit slots its arguments and result take"
  field text String
  field before String
  field between String
  field after String
  field host Bool
  field key String
  field slots Int64
  field results Int64

record CType "How a built-in type is written in C"
  field text String
  field cType String

%%TABLES%%

## ---------------------------------------------------------------- names and types

op putValue "Append a value's C name: `v_` and its name"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input word syntax.Word copied
:begin
  @v word
  return

op putSlotName "Append an input's C name from its slot text: `v_` and the slot"
  input buffer buffer.ByteBuffer borrowedMutable
  input slot String borrowed
:begin
  @s valuePrefix "v_"
  @s slot
  return

op putCType "Append the C type of a type: a built-in type's spelling, or `t_` and the declared type's name"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  raises syntax.Rejection
:begin
  readRow: entry = cTypes.rowAt(code) ? declared
  readSpelling: spelling = CType.cType(entry)
  @s spelling
  return
:declared
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  @w name typePrefix
  return
  let typePrefix String "t_"

op typeInfoAt "Read the facts of a type by its number"
  input types subset.Types borrowed
  input code Int64 copied
  output subset.TypeInfo
:begin
  findIndex: index = math.subtractInt64(code, 1)
  readInfo: info = subset.Types.getOrTrap(types, index)
  return info

op holdsText "Decide whether a value of a type holds text (String or Bytes), directly or inside it"
  input types subset.Types borrowed
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
  readInfo: info = typeInfoAt(types, code)
  readHolds: holds = subset.TypeInfo.holdsText(info)
  return holds

op putRelocated "Append a C expression for a value with its text copied into a region (as the LLVM backend does where a value is stored in a list or returned in its caller's region); a value without text is written as it is"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  input value String borrowed
  input region String borrowed
  raises syntax.Rejection
:begin
  textCheck: hasText = holdsText(types, code)
  if hasText relocate plain
:plain
  @s value
  return
:relocate
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck2: isText = logic.or(isString, isBytes)
  if isText relocateString relocateRecord
:relocateString
  @s stringStart "ss_relocate("
  goto arguments
:relocateRecord
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  @w name relocatePrefix
  @s open "("
  goto arguments
:arguments
  @s value
  @s comma ", "
  @s region
  @s close ")"
  return
  let relocatePrefix String "rl_"

op memberAt "Read a member of a record or enum by its position"
  input members subset.Members borrowed
  input index Int64 copied
  output subset.MemberInfo
:begin
  readMember: member = subset.Members.getOrTrap(members, index)
  return member

## ---------------------------------------------------------------- the module's types

op putTypedefs "Declare every record and enum as a struct type and every list type as a list pointer"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  let code Int64 11 mut
:begin
  countTypes: typeCount = subset.Types.length(types)
  goto eachType
:eachType loop=while max=typeCount
  doneCheck: allDone = compare.greaterOrEqualInt64(code, typeCount)
  if allDone done readType
:readType in=eachType
  countCode: nextCode = math.addInt64(code, 1)
  set code nextCode
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  readKind: kind = subset.TypeInfo.kind(info)
  listCheck: isList = compare.equalInt64(kind, 5)
  tableCheck: isTable = compare.equalInt64(kind, 6)
  if isTable eachType notTable
:notTable in=eachType
  if isList listType structType
:listType in=eachType
  @s listStart "typedef ss_list *t_"
  @w name
  @s lineEnd ";\n"
  goto eachType
:structType in=eachType
  @s structStart "typedef struct t_"
  @w name
  @s structMiddle " t_"
  @w name
  @s lineEnd
  goto eachType
:done
  @s newline "\n"
  return

op putStruct "Define a record's or enum's struct: a record's fields in order; a narrow enum as a tag and one Int64; a wide enum as a tag and one field for each variant's payload"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input code Int64 copied
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  readKind: kind = subset.TypeInfo.kind(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  readNarrow: narrow = subset.TypeInfo.narrow(info)
  @s structStart "struct t_"
  @w name
  @s structOpen " {\n"
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  if isRecord eachField enumKind
:enumKind
  @s tagField "  int32_t tag;\n"
  if narrow narrowEnum eachVariant
:narrowEnum
  @s payloadField "  int64_t payload;\n"
  goto close
:eachField loop=while max=count
  fieldsDone: allFields = compare.greaterOrEqualInt64(index, count)
  if allFields close putField
:putField in=eachField
  findField: fieldIndex = math.addInt64(first, index)
  readField: field = memberAt(members, fieldIndex)
  readFieldName: fieldName = subset.MemberInfo.name(field)
  readFieldType: fieldType = subset.MemberInfo.type(field)
  @s indent "  "
  putFieldType: putCType(buffer, source, types, fieldType) ?^
  @s fieldPrefix " m_"
  @w fieldName
  @s lineEnd ";\n"
  countField: nextField = math.addInt64(index, 1)
  set index nextField
  goto eachField
:eachVariant loop=while max=count
  variantsDone: allVariants = compare.greaterOrEqualInt64(index, count)
  if allVariants close readVariant
:readVariant in=eachVariant
  findVariant: variantIndex = math.addInt64(first, index)
  readVariantInfo: variant = memberAt(members, variantIndex)
  readVariantName: variantName = subset.MemberInfo.name(variant)
  readVariantType: variantType = subset.MemberInfo.type(variant)
  countVariant: nextVariant = math.addInt64(index, 1)
  set index nextVariant
  payloadCheck: hasPayload = compare.greaterThanInt64(variantType, 0)
  if hasPayload putPayload eachVariant
:putPayload in=eachVariant
  @s indent
  putPayloadType: putCType(buffer, source, types, variantType) ?^
  @s payloadPrefix " p_"
  @w variantName
  @s lineEnd
  goto eachVariant
:close
  @s structClose "};\n\n"
  return

op putRelocator "Define `rl_<Type>`, which copies every text a record or enum value holds into a region"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input code Int64 copied
  raises syntax.Rejection
  region scratch 65536
  let index Int64 0 mut
:begin
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  readKind: kind = subset.TypeInfo.kind(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  @s staticStart "static t_"
  @w name
  @s relocateName " rl_"
  @w name
  @s relocateParams "(t_"
  @w name
  @s relocateRest " v, ss_region *r) {\n"
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  goto eachMember
:eachMember loop=while max=count
  membersDone: allMembers = compare.greaterOrEqualInt64(index, count)
  if allMembers close readMember
:readMember in=eachMember
  findMember: memberIndex = math.addInt64(first, index)
  readMemberInfo: member = memberAt(members, memberIndex)
  readMemberName: memberName = subset.MemberInfo.name(member)
  readMemberType: memberType = subset.MemberInfo.type(member)
  countMember: nextMember = math.addInt64(index, 1)
  set index nextMember
  payloadCheck: hasType = compare.greaterThanInt64(memberType, 0)
  if hasType textCheck eachMember
:textCheck in=eachMember
  memberText: memberHoldsText = holdsText(types, memberType)
  if memberHoldsText fieldKind eachMember
:fieldKind in=eachMember
  if isRecord recordField payloadField
:recordField in=eachMember
  @s fieldStart "  v.m_"
  goto assign
:payloadField in=eachMember
  @s payloadStart "  v.p_"
  goto assign
:assign in=eachMember
  @w memberName
  @s assignText " = "
  if isRecord recordValue payloadValue
:recordValue in=eachMember
  copyFieldName: fieldText = syntax.wordText(source, memberName, scratch) ?^
  joinField: fieldValue = string.concat(fieldPrefix="v.m_", fieldText, scratch)
  putRecordValue: putRelocated(buffer, source, types, memberType, fieldValue, regionName="r") ?^
  goto finishMember
:payloadValue in=eachMember
  copyPayloadName: payloadText = syntax.wordText(source, memberName, scratch) ?^
  joinPayload: payloadExpression = string.concat(payloadPrefix="v.p_", payloadText, scratch)
  putPayloadValue: putRelocated(buffer, source, types, memberType, payloadExpression, regionName) ?^
  goto finishMember
:finishMember in=eachMember
  @s lineEnd ";\n"
  goto eachMember
:close
  @s relocateEnd "  return v;\n}\n\n"
  return

op putListHelpers "Define a list type's append (`la_`), get (`lg_`), and getOrTrap (`lt_`), each typed by the list's item"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  raises syntax.Rejection
:begin
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  readItem: item = subset.TypeInfo.item(info)
  @s appendStart "static void la_"
  @w name
  @s appendList "(t_"
  @w name
  @s appendItem " l, "
  putItemType: putCType(buffer, source, types, item) ?^
  @s appendOpen " v) {\n  v = "
  putItemValue: putRelocated(buffer, source, types, item, itemValue="v", itemRegion="l->region") ?^
  @s appendSlot ";\n  *("
  putSlotType: putCType(buffer, source, types, item) ?^
  @s appendSize " *)ss_list_slot(l, (int64_t)sizeof("
  putSizeType: putCType(buffer, source, types, item) ?^
  @s appendEnd ")) = v;\n}\n\nstatic bool lg_"
  @w name
  @s getOut "("
  putOutType: putCType(buffer, source, types, item) ?^
  @s getList " *out, t_"
  @w name
  @s getBody " l, int64_t i) {\n  if (ss_list_outside(l, i)) return true;\n  *out = (("
  putGetType: putCType(buffer, source, types, item) ?^
  @s getEnd " *)l->data)[i];\n  return false;\n}\n\nstatic "
  putTrapReturn: putCType(buffer, source, types, item) ?^
  @s trapName " lt_"
  @w name
  @s trapList "(t_"
  @w name
  @s trapBody " l, int64_t i) {\n  if (ss_list_outside(l, i)) ss_list_trap();\n  return (("
  putTrapType: putCType(buffer, source, types, item) ?^
  @s trapEnd " *)l->data)[i];\n}\n\n"
  return

op findCell "Find the value of the cell of a table row that fills a field"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entity model.Entity copied
  input rowName syntax.Word copied
  input fieldName syntax.Word copied
  output syntax.Word
  raises syntax.Rejection
  let rowIndex Int64 0 mut
:begin
  readEntityFirst: entityFirst = model.Entity.first(entity)
  readEntityCount: entityCount = model.Entity.count(entity)
  findEnd: entityEnd = math.addInt64(entityFirst, entityCount)
  set rowIndex entityFirst
  goto eachRow
:eachRow loop=while max=entityCount
  endCheck: rowsDone = compare.greaterOrEqualInt64(rowIndex, entityEnd)
  if rowsDone missing readRow
:readRow in=eachRow
  fetchRow: row = syntax.Rows.getOrTrap(rows, rowIndex)
  advanceRow: nextIndex = math.addInt64(rowIndex, 1)
  set rowIndex nextIndex
  readCount: count = syntax.Row.count(row)
  shapeCheck: isFive = compare.equalInt64(count, 5)
  if isFive readCell eachRow
:readCell in=eachRow
  readFirstWord: first = syntax.Row.first(row)
  findPredicate: predicateAt = math.addInt64(first, 1)
  readPredicate: predicate = syntax.Words.getOrTrap(words, predicateAt)
  cellCheck: isCell = syntax.isText(source, predicate, cellWord="cell") ?^
  if isCell rowCheck eachRow
:rowCheck in=eachRow
  findRowWord: rowAt = math.addInt64(first, 2)
  readRowWord: cellRow = syntax.Words.getOrTrap(words, rowAt)
  sameRow: isRow = syntax.sameText(source, cellRow, rowName) ?^
  if isRow fieldCheck eachRow
:fieldCheck in=eachRow
  findFieldWord: fieldAt = math.addInt64(first, 3)
  readFieldWord: cellField = syntax.Words.getOrTrap(words, fieldAt)
  sameField: isField = syntax.sameText(source, cellField, fieldName) ?^
  if isField found eachRow
:found
  findValueWord: valueAt = math.addInt64(first, 4)
  readValueWord: value = syntax.Words.getOrTrap(words, valueAt)
  return value
@reject unsupportedPayload rowName missing

op putCellValue "Append a table cell's value as C: text as SS_STATIC, an enum variant as its tag, anything else as written"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input targets subset.Targets borrowed
  input code Int64 copied
  input value syntax.Word copied
  raises syntax.Rejection
:begin
  stringCheck: isString = compare.equalInt64(code, 1)
  if isString text notText
:text
  @s textStart "SS_STATIC("
  @w value
  @s close ")"
  return
:notText
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  if isEnum variant plain
:plain
  @w value
  return
:variant
  @view variantText value outside
  findVariant: target = subset.Targets.get(targets, variantText) ? missing
  readMemberIndex: memberIndex = subset.TargetInfo.member(target)
  readMember: member = memberAt(members, memberIndex)
  readTag: tag = subset.MemberInfo.index(member)
  readNarrow: narrow = subset.TypeInfo.narrow(info)
  if narrow narrowTag wideTag
:narrowTag
  @s open "{ "
  buffer.appendInt64(buffer, tag)
  @s narrowEnd ", 0 }"
  return
:wideTag
  @s wideOpen "{ .tag = "
  buffer.appendInt64(buffer, tag)
  @s wideEnd " }"
  return
@reject unknownVariant value missing
@reject outsideSource value outside

op putTable "Define a table as a static array of its rows, each a record of its cells in field order, and `tr_<table>`, which reads row 1 to n or fails"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input targets subset.Targets borrowed
  input code Int64 copied
  raises syntax.Rejection
  let rowIndex Int64 0 mut
  let fieldIndex Int64 0 mut
  let zero Int64 0
:begin
  readInfo: info = typeInfoAt(types, code)
  readName: name = subset.TypeInfo.name(info)
  readRowType: rowType = subset.TypeInfo.item(info)
  readEntityIndex: entityIndex = subset.TypeInfo.first(info)
  readRowCount: rowCount = subset.TypeInfo.count(info)
  readEntity: entity = model.Entities.getOrTrap(entities, entityIndex)
  readRecord: record = typeInfoAt(types, rowType)
  readFirstField: firstField = subset.TypeInfo.first(record)
  readFieldCount: fieldCount = subset.TypeInfo.count(record)
  @s staticStart "static const "
  putRowType: putCType(buffer, source, types, rowType) ?^
  @s arrayName " tb_"
  @w name
  @s arrayOpen "["
  buffer.appendInt64(buffer, rowCount)
  @s arrayStart "] = {\n"
  readEntityFirst: entityFirst = model.Entity.first(entity)
  readEntityCount: entityCount = model.Entity.count(entity)
  findEnd: entityEnd = math.addInt64(entityFirst, entityCount)
  set rowIndex entityFirst
  goto eachRow
:eachRow loop=while max=entityCount
  endCheck: rowsDone = compare.greaterOrEqualInt64(rowIndex, entityEnd)
  if rowsDone finish readRow
:readRow in=eachRow
  fetchRow: row = syntax.Rows.getOrTrap(rows, rowIndex)
  advanceRow: nextIndex = math.addInt64(rowIndex, 1)
  set rowIndex nextIndex
  readCount: count = syntax.Row.count(row)
  shapeCheck: isFour = compare.equalInt64(count, 4)
  if isFour readPredicate eachRow
:readPredicate in=eachRow
  readFirstWord: first = syntax.Row.first(row)
  findPredicate: predicateAt = math.addInt64(first, 1)
  readPredicateWord: predicate = syntax.Words.getOrTrap(words, predicateAt)
  rowCheck: isRow = syntax.isText(source, predicate, rowWord="row") ?^
  if isRow putRow eachRow
:putRow in=eachRow
  findRowName: rowNameAt = math.addInt64(first, 2)
  readRowName: rowName = syntax.Words.getOrTrap(words, rowNameAt)
  @s rowOpen "  { "
  set fieldIndex zero
  goto eachField
:eachField loop=while max=fieldCount in=eachRow
  fieldsDone: allFields = compare.greaterOrEqualInt64(fieldIndex, fieldCount)
  if allFields rowDone readField
:readField in=eachField
  findField: memberIndex = math.addInt64(firstField, fieldIndex)
  readMember: field = memberAt(members, memberIndex)
  readFieldName: fieldName = subset.MemberInfo.name(field)
  readFieldType: fieldType = subset.MemberInfo.type(field)
  firstCheck: isFirst = compare.equalInt64(fieldIndex, 0)
  countField: nextField = math.addInt64(fieldIndex, 1)
  set fieldIndex nextField
  if isFirst cell comma
:comma in=eachField
  @s commaText ", "
  goto cell
:cell in=eachField
  findTheCell: value = findCell(source, words, rows, entity, rowName, fieldName) ?^
  putTheCell: putCellValue(buffer, source, types, members, targets, fieldType, value) ?^
  goto eachField
:rowDone in=eachRow
  @s rowClose " },\n"
  goto eachRow
:finish
  @s arrayEnd "};\n\nstatic bool tr_"
  @w name
  @s readerOpen "("
  putOutType: putCType(buffer, source, types, rowType) ?^
  @s readerBody " *out, int64_t p) {\n  if (p < 1 || p > "
  buffer.appendInt64(buffer, rowCount)
  @s readerMiddle ") return true;\n  *out = tb_"
  @w name
  @s readerEnd "[p - 1];\n  return false;\n}\n\n"
  return

op putTypes "Write the module's types: typedefs, struct definitions in source order, relocators for those that hold text, list helpers, and tables"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input targets subset.Targets borrowed
  raises syntax.Rejection
  let code Int64 11 mut
:begin
  putAllTypedefs: putTypedefs(buffer, source, types)
  countTypes: typeCount = subset.Types.length(types)
  goto eachStruct
:eachStruct loop=while max=typeCount
  structsDone: allStructs = compare.greaterOrEqualInt64(code, typeCount)
  if allStructs relocators readStruct
:readStruct in=eachStruct
  countStruct: nextStruct = math.addInt64(code, 1)
  set code nextStruct
  readStructInfo: structInfo = typeInfoAt(types, code)
  readStructKind: structKind = subset.TypeInfo.kind(structInfo)
  listCheck: isList = compare.equalInt64(structKind, 5)
  tableCheck: isTable = compare.equalInt64(structKind, 6)
  noStruct: skipStruct = logic.or(isList, isTable)
  if skipStruct eachStruct putOneStruct
:putOneStruct in=eachStruct
  putTheStruct: putStruct(buffer, source, types, members, code) ?^
  textCheck: structText = subset.TypeInfo.holdsText(structInfo)
  if structText putOneRelocator eachStruct
:putOneRelocator in=eachStruct
  putTheRelocator: putRelocator(buffer, source, types, members, code) ?^
  goto eachStruct
:relocators
  set code eleven
  goto eachList
:eachList loop=while max=typeCount
  listsDone: allLists = compare.greaterOrEqualInt64(code, typeCount)
  if allLists done readList
:readList in=eachList
  countList: nextList = math.addInt64(code, 1)
  set code nextList
  readListInfo: listInfo = typeInfoAt(types, code)
  readListKind: listKind = subset.TypeInfo.kind(listInfo)
  isListCheck: listType = compare.equalInt64(listKind, 5)
  if listType putOneList tableKind
:tableKind in=eachList
  isTableCheck: tableType = compare.equalInt64(listKind, 6)
  if tableType putOneTable eachList
:putOneTable in=eachList
  putTheTable: putTable(buffer, source, words, rows, entities, types, members, targets, code) ?^
  goto eachList
:putOneList in=eachList
  putTheList: putListHelpers(buffer, source, types, code) ?^
  goto eachList
:done
  return
  let eleven Int64 11

## ---------------------------------------------------------------- constants and signatures

op putLiteral "Append a literal or a value's name as C: text as `SS_TEXT`, a name as its value"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input word syntax.Word copied
  input isName Bool copied
:begin
  if isName name literal
:name
  putName: putValue(buffer, source, word)
  return
:literal
  readKind: kind = syntax.Word.kind(word)
  match kind
  case text text
  others plain
:text
  @s textStart "SS_TEXT("
  @w word
  @s close ")"
  return
:plain
  @w word
  return

op putConstants "Define every module constant as a static C value"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input constants subset.Values borrowed
  raises syntax.Rejection
:begin
  countConstants: constantCount = subset.Values.length(constants)
  goto eachConstant
:eachConstant loop=forEach max=constantCount over=constants
  next constants key readConstant done
:readConstant in=eachConstant
  readInfo: info = subset.Values.get(constants, key) ? lost
  readName: name = subset.ValueInfo.name(info)
  readCode: code = subset.ValueInfo.code(info)
  readInit: init = subset.ValueInfo.init(info)
  @s staticStart "static const "
  putType: putCType(buffer, source, types, code) ?^
  @s space " "
  putName: putValue(buffer, source, name)
  @s assign " = "
  stringCheck: isString = compare.equalInt64(code, 1)
  if isString staticText plain
:staticText in=eachConstant
  @s staticTextStart "SS_STATIC("
  @w init
  @s close ")"
  goto endLine
:plain in=eachConstant
  @w init
  goto endLine
:endLine in=eachConstant
  @s lineEnd ";\n"
  goto eachConstant
:done
  @s newline "\n"
  return
:lost
  makeKind: placeholderKind = syntax.WordKind.name()
  makeOrigin: origin = string.Position.new(0, 1, 1)
  makePlaceholder: placeholder = syntax.Word.new(placeholderKind, origin, 0)
  makeLost: lostError = syntax.Rejection.lostName(placeholder)
  raise lostError

op putSignature "Append an operation's C signature: `static`, its return type (bool when it raises, so the caller can branch), `o_<name>`, then out pointers for its output and error when it raises, then its inputs"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input op subset.OpInfo copied
  raises syntax.Rejection
  let index Int64 0 mut
  let started Bool false mut
  let yes Bool true
:begin
  readName: name = subset.OpInfo.name(op)
  readOutput: output = subset.OpInfo.output(op)
  readRaises: raises = subset.OpInfo.raises(op)
  readFirst: first = subset.OpInfo.firstParam(op)
  readCount: count = subset.OpInfo.paramCount(op)
  @s staticStart "static "
  raisesCheck: canFail = compare.notEqualInt64(raises, 0)
  outputCheck: hasOutput = compare.notEqualInt64(output, 0)
  if canFail boolReturn valueReturn
:boolReturn
  @s boolText "bool"
  goto named
:valueReturn
  if hasOutput outputReturn voidReturn
:outputReturn
  putOutputType: putCType(buffer, source, types, output) ?^
  goto named
:voidReturn
  @s voidText "void"
  goto named
:named
  @w name namePrefix
  @s open "("
  if canFail outPointers inputs
:outPointers
  if hasOutput outPointer errorPointer
:outPointer
  putOutType: putCType(buffer, source, types, output) ?^
  @s outText " *ss_out, "
  goto errorPointer
:errorPointer
  putErrorType: putCType(buffer, source, types, raises) ?^
  @s errorText " *ss_err"
  set started yes
  goto inputs
:inputs
  goto eachInput
:eachInput loop=while max=count
  inputsDone: allInputs = compare.greaterOrEqualInt64(index, count)
  if allInputs close putInput
:putInput in=eachInput
  if started comma firstInput
:comma in=eachInput
  @s commaText ", "
  goto inputType
:firstInput in=eachInput
  goto inputType
:inputType in=eachInput
  findParam: paramIndex = math.addInt64(first, index)
  readParam: param = subset.Params.getOrTrap(params, paramIndex)
  readSlot: slot = subset.ParamInfo.slot(param)
  readType: type = subset.ParamInfo.type(param)
  putInputType: putCType(buffer, source, types, type) ?^
  @s space " "
  putInputName: putSlotName(buffer, slot)
  set started yes
  countInput: nextInput = math.addInt64(index, 1)
  set index nextInput
  goto eachInput
:close
  if started closeParams voidParams
:voidParams
  @s voidParamsText "void)"
  return
:closeParams
  @s closeText ")"
  return
  let namePrefix String " o_"

op putPrototypes "Declare every operation, and a depth counter for each one that recurses"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input ops subset.Ops borrowed
  raises syntax.Rejection
:begin
  countOps: opCount = subset.Ops.length(ops)
  goto eachOp
:eachOp loop=forEach max=opCount over=ops
  next ops op putOne done
:putOne in=eachOp
  putTheSignature: putSignature(buffer, source, types, params, op) ?^
  @s lineEnd ";\n"
  readRecursive: recursive = subset.OpInfo.recursive(op)
  if recursive depth eachOp
:depth in=eachOp
  readName: name = subset.OpInfo.name(op)
  @s depthStart "static int64_t d_"
  @w name
  @s lineEnd
  goto eachOp
:done
  @s newline "\n"
  return

## ---------------------------------------------------------------- jumps

op isInside "Decide whether a jump from one label to another returns to a loop from inside it: the labels are the same, or the target is a loop the source is within"
  input source String borrowed
  input labels subset.Labels borrowed
  input from syntax.Word copied
  input to syntax.Word copied
  output Bool
  raises syntax.Rejection
  let current syntax.Word from mut
  let yes Bool true
  let no Bool false
:begin
  countLabels: limit = subset.Labels.length(labels)
  goto climb
:climb loop=while max=limit note="\"Each pass moves to the loop around the current label; `within` never cycles (refined check, R503)\""
  sameCheck: arrived = syntax.sameText(source, current, to) ?^
  if arrived inside outward
:outward in=climb
  @view currentText current outside
  getLabel: info = subset.Labels.get(labels, currentText) ? unknown
  readNested: nested = subset.LabelInfo.nested(info)
  if nested moveOut outsideLoop
:moveOut in=climb
  readWithin: around = subset.LabelInfo.within(info)
  set current around
  goto climb
:inside
  return yes
:outsideLoop
  return no
@reject unknownLabel current unknown
@reject outsideSource current outside

op putJump "Write a jump to a label as a C block, counting or resetting the target loop's passes, and resetting a forEach loop's position when the loop is entered"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input labels subset.Labels borrowed
  input from syntax.Word copied
  input to syntax.Word copied
  raises syntax.Rejection
:begin
  @s open "{ "
  @view toText to outside
  getLabel: info = subset.Labels.get(labels, toText) ? unknown
  readKind: kind = subset.LabelInfo.kind(info)
  readBounded: bounded = subset.LabelInfo.bounded(info)
  loopCheck: isLoop = compare.notEqualInt64(kind, 0)
  if isLoop loop jump
:loop
  insideCheck: back = isInside(source, labels, from, to) ?^
  if back pass enter
:pass
  if bounded passCount jump
:passCount
  @s passText "ss_pass(&n_"
  @w to
  @s comma ", "
  readBound: bound = subset.LabelInfo.bound(info)
  readBoundKind: boundKind = syntax.Word.kind(bound)
  match boundKind
  case name boundName
  others boundLiteral
:boundName
  putBoundName: putValue(buffer, source, bound)
  goto passLabel
:boundLiteral
  @w bound
  goto passLabel
:passLabel
  @s quote ", \""
  @w to
  @s passEnd "\"); "
  goto jump
:enter
  if bounded resetCount resetIndex
:resetCount
  @s resetText "n_"
  @w to
  @s resetEnd " = 0; "
  goto resetIndex
:resetIndex
  forEachCheck: isForEach = compare.equalInt64(kind, 5)
  if isForEach resetPosition jump
:resetPosition
  @s indexText "i_"
  @w to
  @s resetEnd
  goto jump
:jump
  @s gotoText "goto l_"
  @w to
  @s close "; }"
  return
@reject unknownLabel to unknown
@reject outsideSource to outside

## ---------------------------------------------------------------- calls

op putArguments "Append a call's argument values, each as its C name, separated by a text, leaving out values in Region slots when asked"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  input between String borrowed
  input skipRegions Bool copied
  input started Bool copied
  let index Int64 0 mut
  let written Bool false mut
  let yes Bool true
:begin
  set written started
  readFirst: first = subset.CallInfo.firstArgument(info)
  readArity: arity = subset.CallInfo.arity(info)
  goto eachArgument
:eachArgument loop=while max=arity
  doneCheck: allDone = compare.greaterOrEqualInt64(index, arity)
  if allDone done readArgument
:readArgument in=eachArgument
  findArgument: argumentIndex = math.addInt64(first, index)
  readArgumentInfo: argument = subset.Arguments.getOrTrap(arguments, argumentIndex)
  readValue: value = subset.ArgumentInfo.value(argument)
  readCode: code = subset.ArgumentInfo.code(argument)
  countArgument: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  regionCheck: isRegion = compare.equalInt64(code, 6)
  skipCheck: skip = logic.and(isRegion, skipRegions)
  if skip eachArgument separate
:separate in=eachArgument
  if written separator putIt
:separator in=eachArgument
  @s between
  goto putIt
:putIt in=eachArgument
  putName: putValue(buffer, source, value)
  set written yes
  goto eachArgument
:done
  return

op argumentAt "Read the value word of a call's argument by its position among the call's arguments"
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  input position Int64 copied
  output syntax.Word
:begin
  readFirst: first = subset.CallInfo.firstArgument(info)
  findArgument: index = math.addInt64(first, position)
  readArgument: argument = subset.Arguments.getOrTrap(arguments, index)
  readValue: value = subset.ArgumentInfo.value(argument)
  return value

op putWidened "Append a narrow enum's payload as the Int64 it is stored as"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  input value syntax.Word copied
:begin
  intCheck: isInt = compare.equalInt64(code, 2)
  if isInt plain notInt
:plain
  putName: putValue(buffer, source, value)
  return
:notInt
  @s cast "(int64_t)"
  putCastName: putValue(buffer, source, value)
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  if isEnum tag done
:tag
  @s tagText ".tag"
  return
:done
  return

op putNarrowed "Append a narrow enum's stored Int64 as the payload type it carries"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  input value syntax.Word copied
  raises syntax.Rejection
:begin
  intCheck: isInt = compare.equalInt64(code, 2)
  if isInt plain notInt
:plain
  putName: putValue(buffer, source, value)
  @s payloadText ".payload"
  return
:notInt
  boolCheck: isBool = compare.equalInt64(code, 4)
  if isBool flag notBool
:flag
  @s flagStart "("
  putFlagName: putValue(buffer, source, value)
  @s flagEnd ".payload != 0)"
  return
:notBool
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  if isEnum tag cast
:tag
  @s tagStart "("
  putEnumType: putCType(buffer, source, types, code) ?^
  @s tagMiddle "){ (int32_t)"
  putTagName: putValue(buffer, source, value)
  @s tagEnd ".payload, 0 }"
  return
:cast
  @s castStart "("
  putCastType: putCType(buffer, source, types, code) ?^
  @s castEnd ")"
  putCastName: putValue(buffer, source, value)
  @s payloadText
  return

op putSlot "Append a value as the 64-bit slots refined_host reads: text and bytes as a pointer and a length, a region as a pointer, anything else as one integer"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input value syntax.Word copied
  input code Int64 copied
:begin
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText text notText
:text
  @s pointerStart "(int64_t)(intptr_t)"
  putTextPointer: putValue(buffer, source, value)
  @s pointerEnd ".p, "
  putTextLength: putValue(buffer, source, value)
  @s lengthEnd ".n"
  return
:notText
  regionCheck: isRegion = compare.equalInt64(code, 6)
  if isRegion region integer
:region
  @s pointerStart
  putRegion: putValue(buffer, source, value)
  return
:integer
  @s integerStart "(int64_t)"
  putInteger: putValue(buffer, source, value)
  return

op putHostCall "Write a call of a host library target as one C block that flattens its arguments into 64-bit slots, calls refined_host by the target's name and slot counts (as the LLVM backend does), and reads back its result and failure"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  input spelling CTarget borrowed
  let index Int64 0 mut
  let started Bool false mut
  let yes Bool true
:begin
  readName: name = subset.CallInfo.name(info)
  readTarget: target = subset.CallInfo.target(info)
  readResult: result = subset.CallInfo.result(info)
  readHasResult: hasResult = subset.CallInfo.hasResult(info)
  readFirst: first = subset.CallInfo.firstArgument(info)
  readArity: arity = subset.CallInfo.arity(info)
  readRaises: raises = subset.TargetInfo.raises(target)
  readOutput: output = subset.TargetInfo.output(target)
  readKey: key = CTarget.key(spelling)
  readSlots: slots = CTarget.slots(spelling)
  readResults: results = CTarget.results(spelling)
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  @s open "  { int64_t ss_a["
  argumentsCheck: hasSlots = compare.greaterThanInt64(slots, 0)
  if hasSlots slotCount oneSlot
:slotCount
  buffer.appendInt64(buffer, slots)
  goto slotsOpen
:oneSlot
  @s oneText "1"
  goto slotsOpen
:slotsOpen
  @s slotsOpenText "] = { "
  if hasSlots eachArgument zeroSlot
:zeroSlot
  @s zeroText "0"
  goto resultSlots
:eachArgument loop=while max=arity
  doneCheck: allDone = compare.greaterOrEqualInt64(index, arity)
  if allDone resultSlots readArgument
:readArgument in=eachArgument
  findArgument: argumentIndex = math.addInt64(first, index)
  readArgumentInfo: argument = subset.Arguments.getOrTrap(arguments, argumentIndex)
  readValue: value = subset.ArgumentInfo.value(argument)
  readCode: code = subset.ArgumentInfo.code(argument)
  countArgument: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  if started comma slot
:comma in=eachArgument
  @s commaText ", "
  goto slot
:slot in=eachArgument
  putArgumentSlots: putSlot(buffer, source, value, code)
  set started yes
  goto eachArgument
:resultSlots
  @s resultsOpen " }; int64_t ss_r["
  resultsCheck: hasResults = compare.greaterThanInt64(results, 0)
  if hasResults resultSlotCount oneResult
:resultSlotCount
  buffer.appendInt64(buffer, results)
  goto call
:oneResult
  @s oneText
  goto call
:call
  @s callOpen "] = {0}; int64_t ss_e = 0; "
  if canFail flag discard
:flag
  @w name flagPrefix
  @s assign " = "
  goto host
:discard
  @s voidCast "(void)"
  goto host
:host
  @s hostOpen "refined_host(\""
  @s key
  @s keyLength "\", (int64_t)sizeof(\""
  @s key
  @s hostArguments "\") - 1, ss_a, ss_r, &ss_e)"
  if canFail failed called
:failed
  @s notZero " != 0"
  goto called
:called
  @s semicolon "; "
  if hasResult readBack close
:readBack
  putResultName: putValue(buffer, source, result)
  @s assignResult " = "
  stringCheck: isString = compare.equalInt64(output, 1)
  bytesCheck: isBytes = compare.equalInt64(output, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText textResult notText
:textResult
  @s textResultText "(ss_string){ (const char *)(intptr_t)ss_r[0], ss_r[1] }; "
  goto close
:notText
  boolCheck: isBool = compare.equalInt64(output, 4)
  if isBool boolResult notBool
:boolResult
  @s boolResultText "(ss_r[0] & 1) != 0; "
  goto close
:notBool
  byteCheck: isByte = compare.equalInt64(output, 5)
  if isByte byteResult notByte
:byteResult
  @s byteResultText "(uint8_t)ss_r[0]; "
  goto close
:notByte
  exitCheck: isExitCode = compare.equalInt64(output, 3)
  if isExitCode exitResult integerResult
:exitResult
  @s exitResultText "(int)ss_r[0]; "
  goto close
:integerResult
  @s integerResultText "ss_r[0]; "
  goto close
:close
  @s closeText "(void)ss_e; }\n"
  return
  let flagPrefix String "f_"

op putCall "Write a call as one C statement: its failure flag or result set from the target, written by what the target is"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input ops subset.Ops borrowed
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  raises syntax.Rejection
  let yes Bool true
  let no Bool false
:begin
  readName: name = subset.CallInfo.name(info)
  readTarget: target = subset.CallInfo.target(info)
  readResult: result = subset.CallInfo.result(info)
  readHasResult: hasResult = subset.CallInfo.hasResult(info)
  readArity: arity = subset.CallInfo.arity(info)
  readRaises: raises = subset.TargetInfo.raises(target)
  readOwner: owner = subset.TargetInfo.owner(target)
  readKind: kind = subset.TargetInfo.kind(target)
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  match kind
  case builtin hostCheck
  others inline
:hostCheck
  readHostRow: hostRow = cTargets.rowAt(owner) ? lost
  readHost: isHost = CTarget.host(hostRow)
  if isHost hostCall inline
:hostCall
  writeHostCall: putHostCall(buffer, source, arguments, info, hostRow)
  return
:inline
  @s indent "  "
  if canFail flagSide valueSide
:flagSide
  @w name flagPrefix
  @s assign " = "
  goto dispatch
:valueSide
  if hasResult resultSide dispatch
:resultSide
  putResultName: putValue(buffer, source, result)
  @s assign
  goto dispatch
:dispatch
  match kind
  case builtin builtinCall
  case operation operationCall
  case recordNew recordNewCall
  case fieldRead fieldReadCall
  case variantMake variantCall
  case listNew listNewCall
  case listAppend listAppendCall
  case listLength listLengthCall
  case listGet listGetCall
  case listGetOrTrap listGetOrTrapCall
  case tableRowAt tableRowAtCall
  case tableLength tableLengthCall
:builtinCall
  readSpelling: spelling = cTargets.rowAt(owner) ? lost
  readBefore: before = CTarget.before(spelling)
  readBetween: between = CTarget.between(spelling)
  readAfter: after = CTarget.after(spelling)
  @s before
  both: outFirst = logic.and(canFail, hasResult)
  if outFirst builtinOut builtinArguments
:builtinOut
  @s address "&"
  putOutName: putValue(buffer, source, result)
  goto builtinArguments
:builtinArguments
  putBuiltinArguments: putArguments(buffer, source, arguments, info, between, no, outFirst)
  @s after
  goto finish
:operationCall
  readOp: op = subset.Ops.getOrTrap(ops, owner)
  readOpName: opName = subset.OpInfo.name(op)
  readOpOutput: opOutput = subset.OpInfo.output(op)
  @w opName opPrefix
  @s open "("
  if canFail outPointers operationArguments
:outPointers
  outputCheck: hasOutput = compare.notEqualInt64(opOutput, 0)
  if hasOutput outPointer errorPointer
:outPointer
  if hasResult outValue outNone
:outValue
  @s address
  putOutValue: putValue(buffer, source, result)
  @s comma ", "
  goto errorPointer
:outNone
  @s nullComma "0, "
  goto errorPointer
:errorPointer
  readHasCatch: hasCatch = subset.CallInfo.hasCatch(info)
  if hasCatch errorValue errorNone
:errorValue
  readCatch: catchName = subset.CallInfo.catchName(info)
  @s address
  putErrorValue: putValue(buffer, source, catchName)
  goto pointersDone
:errorNone
  @s null "0"
  goto pointersDone
:pointersDone
  putOperationArgumentsAfter: putArguments(buffer, source, arguments, info, comma, no, yes)
  @s close ")"
  goto finish
:operationArguments
  putOperationArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:recordNewCall
  @s compoundStart "("
  putRecordType: putCType(buffer, source, types, owner) ?^
  @s compoundOpen "){ "
  putFields: putArguments(buffer, source, arguments, info, comma, yes, no)
  @s compoundClose " }"
  goto finish
:fieldReadCall
  readRecord: record = argumentAt(arguments, info, 0)
  readMemberIndex: memberIndex = subset.TargetInfo.member(target)
  readField: field = memberAt(members, memberIndex)
  readFieldName: fieldName = subset.MemberInfo.name(field)
  putRecordName: putValue(buffer, source, record)
  @w fieldName fieldPrefix
  goto finish
:variantCall
  readVariantIndex: variantIndex = subset.TargetInfo.member(target)
  readVariant: variant = memberAt(members, variantIndex)
  readVariantName: variantName = subset.MemberInfo.name(variant)
  readTag: tag = subset.MemberInfo.index(variant)
  readPayloadType: payloadType = subset.MemberInfo.type(variant)
  readEnumInfo: enumInfo = typeInfoAt(types, owner)
  readNarrow: narrow = subset.TypeInfo.narrow(enumInfo)
  @s compoundStart
  putEnumType: putCType(buffer, source, types, owner) ?^
  @s compoundOpen
  payloadCheck: hasPayload = compare.greaterThanInt64(payloadType, 0)
  if narrow narrowVariant wideVariant
:narrowVariant
  buffer.appendInt64(buffer, tag)
  @s comma
  if hasPayload narrowPayload narrowZero
:narrowPayload
  readNarrowValue: narrowValue = argumentAt(arguments, info, 0)
  putNarrowValue: putWidened(buffer, source, types, payloadType, narrowValue)
  @s compoundClose
  goto finish
:narrowZero
  @s zeroClose "0 }"
  goto finish
:wideVariant
  @s tagStart ".tag = "
  buffer.appendInt64(buffer, tag)
  if hasPayload widePayload wideClose
:widePayload
  @s payloadStart ", .p_"
  @w variantName
  @s assign
  readWideValue: wideValue = argumentAt(arguments, info, 0)
  putWideValue: putValue(buffer, source, wideValue)
  goto wideClose
:wideClose
  @s compoundClose
  goto finish
:listNewCall
  readRegion: listRegion = argumentAt(arguments, info, 0)
  @s listNewText "ss_list_new("
  putListRegion: putValue(buffer, source, listRegion)
  @s close
  goto finish
:listAppendCall
  readListInfo: listInfo = typeInfoAt(types, owner)
  readListName: listName = subset.TypeInfo.name(listInfo)
  @w listName appendPrefix
  @s open
  putAppendArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:listLengthCall
  readLengthList: lengthList = argumentAt(arguments, info, 0)
  putLengthList: putValue(buffer, source, lengthList)
  @s lengthText "->length"
  goto finish
:listGetCall
  readGetInfo: getInfo = typeInfoAt(types, owner)
  readGetName: getName = subset.TypeInfo.name(getInfo)
  @w getName getPrefix
  @s open
  @s address
  putGetResult: putValue(buffer, source, result)
  @s comma
  putGetArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:listGetOrTrapCall
  readTrapInfo: trapInfo = typeInfoAt(types, owner)
  readTrapName: trapName = subset.TypeInfo.name(trapInfo)
  @w trapName trapPrefix
  @s open
  putTrapArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:tableRowAtCall
  readTableInfo: tableInfo = typeInfoAt(types, owner)
  readTableName: tableName = subset.TypeInfo.name(tableInfo)
  @w tableName rowAtPrefix
  @s open
  @s address
  putRowAtResult: putValue(buffer, source, result)
  @s comma
  putRowAtArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:tableLengthCall
  readLengthInfo: lengthInfo = typeInfoAt(types, owner)
  readRowCount: rowCount = subset.TypeInfo.count(lengthInfo)
  buffer.appendInt64(buffer, rowCount)
  goto finish
:finish
  @s lineEnd ";\n"
  return
@reject lostName name lost
  let rowAtPrefix String "tr_"
  let flagPrefix String "f_"
  let opPrefix String "o_"
  let fieldPrefix String ".m_"
  let appendPrefix String "la_"
  let getPrefix String "lg_"
  let trapPrefix String "lt_"

## ---------------------------------------------------------------- steps

op putFrees "Append the C that releases an operation's regions released at return, and leaves its recursion depth"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input values subset.Values borrowed
  input op subset.OpInfo copied
  raises syntax.Rejection
:begin
  countValues: valueCount = subset.Values.length(values)
  goto eachValue
:eachValue loop=forEach max=valueCount over=values
  next values key readValue depth
:readValue in=eachValue
  readInfo: info = subset.Values.get(values, key) ? lost
  readOrigin: origin = subset.ValueInfo.origin(info)
  readReleased: released = subset.ValueInfo.released(info)
  regionCheck: isRegion = compare.equalInt64(origin, 7)
  bothCheck: frees = logic.and(isRegion, released)
  if frees free eachValue
:free in=eachValue
  readName: name = subset.ValueInfo.name(info)
  @s freeStart "ss_region_free(v_"
  @w name
  @s freeEnd "); "
  goto eachValue
:depth
  readRecursive: recursive = subset.OpInfo.recursive(op)
  if recursive leave done
:leave
  readOpName: opName = subset.OpInfo.name(op)
  @s leaveStart "d_"
  @w opName
  @s leaveEnd " -= 1; "
  goto done
:done
  return
:lost
  readOpWord: opWord = subset.OpInfo.name(op)
  makeLost: lostError = syntax.Rejection.lostName(opWord)
  raise lostError

op putReturn "Write a return: the result (copied into the caller's region when the output is owned by one) or error through the out pointers, the regions released, then the C return"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input values subset.Values borrowed
  input op subset.OpInfo copied
  input step subset.Step copied
  raises syntax.Rejection
:begin
  readVerb: verb = subset.Step.verb(step)
  readSubject: subject = subset.Step.subject(step)
  readNone: returnsNone = subset.Step.number(step)
  readRaises: raises = subset.OpInfo.raises(op)
  readOutput: output = subset.OpInfo.output(op)
  readOwned: owned = subset.OpInfo.owned(op)
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  noneCheck: givesNone = compare.equalInt64(returnsNone, 1)
  @s open "  { "
  match verb
  case returnError error
  others ok
:error
  @s errorStart "if (ss_err) *ss_err = v_"
  @w subject
  @s semicolon "; "
  freeForError: putFrees(buffer, source, values, op) ?^
  @s returnTrue "return true; }\n"
  return
:ok
  if givesNone nothing something
:nothing
  freeForNothing: putFrees(buffer, source, values, op) ?^
  if canFail returnFalse returnVoid
:returnFalse
  @s returnFalseText "return false; }\n"
  return
:returnVoid
  @s returnVoidText "return; }\n"
  return
:something
  copyName: subjectText = syntax.wordText(source, subject, scratch) ?^
  prefixValue: valueText = string.concat(valuePrefix="v_", subjectText, scratch)
  if canFail outValue resultValue
:outValue
  @s outStart "if (ss_out) *ss_out = "
  goto expression
:resultValue
  putResultType: putCType(buffer, source, types, output) ?^
  @s resultStart " ss_result = "
  goto expression
:expression
  if owned relocated plain
:relocated
  readOwner: owner = subset.OpInfo.owner(op)
  copyOwner: ownerText = syntax.wordText(source, owner, scratch) ?^
  prefixOwner: ownerValue = string.concat(valuePrefix, ownerText, scratch)
  putRelocatedValue: putRelocated(buffer, source, types, output, valueText, ownerValue) ?^
  goto expressionDone
:plain
  @s valueText
  goto expressionDone
:expressionDone
  @s semicolon
  freeForValue: putFrees(buffer, source, values, op) ?^
  if canFail returnFalse returnResult
:returnResult
  @s returnResultText "return ss_result; }\n"
  return
  region scratch 65536

op putStep "Write one step of an operation as C"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input ops subset.Ops borrowed
  input op subset.OpInfo copied
  input values subset.Values borrowed
  input calls subset.Calls borrowed
  input arguments subset.Arguments borrowed
  input labels subset.Labels borrowed
  input step subset.Step copied
  raises syntax.Rejection
:begin
  readLabel: label = subset.Step.label(step)
  readVerb: verb = subset.Step.verb(step)
  readSubject: subject = subset.Step.subject(step)
  readTarget: target = subset.Step.target(step)
  readOtherwise: otherwise = subset.Step.otherwise(step)
  readExtra: extra = subset.Step.extra(step)
  readNumber: number = subset.Step.number(step)
  readCode: code = subset.Step.code(step)
  match verb
  case doCall doStep
  case setValue setStep
  case jump jumpStep
  case branchIf branchIfStep
  case branchIfError branchIfErrorStep
  case branchIfNext branchIfNextStep
  case matchValue done
  case caseOf caseStep
  case returnOk returnStep
  case returnError returnStep
  case startTask doStep
  case joinTask done
:doStep
  @view callText subject outside
  readCall: callInfo = subset.Calls.get(calls, callText) ? lost
  writeCall: putCall(buffer, source, types, members, ops, arguments, callInfo) ?^
  goto done
:setStep
  @s indent "  "
  putSetTarget: putValue(buffer, source, subject)
  @s assign " = "
  putSetSource: putValue(buffer, source, target)
  @s lineEnd ";\n"
  goto done
:jumpStep
  @s indent
  putGoto: putJump(buffer, source, labels, label, target) ?^
  @s newline "\n"
  goto done
:branchIfStep
  @s ifValue "  if ("
  putCondition: putValue(buffer, source, subject)
  goto branchArms
:branchIfErrorStep
  @s ifValue
  @w subject flagPrefix
  goto branchArms
:branchArms
  @s ifThen ") "
  putYes: putJump(buffer, source, labels, label, target) ?^
  @s elseText " else "
  putNo: putJump(buffer, source, labels, label, otherwise) ?^
  @s newline
  goto done
:branchIfNextStep
  tableCheck: overTable = compare.greaterThanInt64(number, 0)
  if overTable tableNextStep listNextStep
:tableNextStep
  readTableInfo: tableInfo = typeInfoAt(types, number)
  readTableName: tableName = subset.TypeInfo.name(tableInfo)
  readRowCount: rowCount = subset.TypeInfo.count(tableInfo)
  @s ifIndex "  if (i_"
  @w label
  @s less " < "
  buffer.appendInt64(buffer, rowCount)
  @s tableOpen ") { "
  putTableItem: putValue(buffer, source, extra)
  @s tableRead " = tb_"
  @w tableName
  @s tableIndex "[i_"
  @w label
  @s indexStep "]; i_"
  @w label
  @s indexEnd " += 1; "
  putTableYes: putJump(buffer, source, labels, label, target) ?^
  @s nextElse " } else "
  putTableNo: putJump(buffer, source, labels, label, otherwise) ?^
  @s newline
  goto done
:listNextStep
  @s ifIndex
  @w label
  @s less
  putCollection: putValue(buffer, source, subject)
  @s lengthOpen "->length) { "
  putItem: putValue(buffer, source, extra)
  @s itemCast " = (("
  putItemType: putCType(buffer, source, types, code) ?^
  @s itemData " *)"
  putCollectionData: putValue(buffer, source, subject)
  @s dataIndex "->data)[i_"
  @w label
  @s indexStep "]; i_"
  @w label
  @s indexEnd " += 1; "
  putNextYes: putJump(buffer, source, labels, label, target) ?^
  @s nextElse " } else "
  putNextNo: putJump(buffer, source, labels, label, otherwise) ?^
  @s newline
  goto done
:caseStep
  readMember: member = subset.Members.getOrTrap(members, number)
  readTag: tag = subset.MemberInfo.index(member)
  readOwner: owner = subset.MemberInfo.owner(member)
  readOwnerInfo: ownerInfo = typeInfoAt(types, owner)
  readNarrow: narrow = subset.TypeInfo.narrow(ownerInfo)
  @s ifValue
  putMatched: putValue(buffer, source, subject)
  @s tagTest ".tag == "
  buffer.appendInt64(buffer, tag)
  @s caseOpen ") { "
  bindCheck: binds = compare.greaterThanInt64(code, 0)
  if binds bind caseJump
:bind
  putBind: putValue(buffer, source, extra)
  @s assign
  if narrow narrowPayload widePayload
:narrowPayload
  putNarrow: putNarrowed(buffer, source, types, code, subject) ?^
  goto bindEnd
:widePayload
  putWide: putValue(buffer, source, subject)
  readPayloadName: payloadName = subset.MemberInfo.name(member)
  @w payloadName payloadPrefix
  goto bindEnd
:bindEnd
  @s semicolon "; "
  goto caseJump
:caseJump
  putCaseJump: putJump(buffer, source, labels, label, target) ?^
  @s caseClose " }\n"
  goto done
:returnStep
  writeReturn: putReturn(buffer, source, types, values, op, step) ?^
  goto done
:done
  return
@reject lostName subject lost
@reject outsideSource subject outside
  let flagPrefix String "f_"
  let payloadPrefix String ".p_"

## ---------------------------------------------------------------- one operation as a C function

op putLocals "Declare an operation's values, failure flags, loop counters and positions, and regions, then set its lets"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input op subset.OpInfo copied
  input values subset.Values borrowed
  input calls subset.Calls borrowed
  input labels subset.Labels borrowed
  raises syntax.Rejection
:begin
  readOpName: opName = subset.OpInfo.name(op)
  countValues: valueCount = subset.Values.length(values)
  goto eachValue
:eachValue loop=forEach max=valueCount over=values
  next values key readValue flags
:readValue in=eachValue
  readInfo: info = subset.Values.get(values, key) ? lost
  readOrigin: origin = subset.ValueInfo.origin(info)
  readCode: code = subset.ValueInfo.code(info)
  inputCheck: isInput = compare.equalInt64(origin, 4)
  errorCheck: isStandardError = compare.equalInt64(code, 7)
  skipCheck: skip = logic.or(isInput, isStandardError)
  if skip eachValue declare
:declare in=eachValue
  readName: name = subset.ValueInfo.name(info)
  @s indent "  "
  putType: putCType(buffer, source, types, code) ?^
  @s space " "
  putName: putValue(buffer, source, name)
  @s zeroText " = {0};\n"
  goto eachValue
:flags
  countCalls: callCount = subset.Calls.length(calls)
  goto eachCall
:eachCall loop=forEach max=callCount over=calls
  next calls callKey readCall counters
:readCall in=eachCall
  readCallInfo: callInfo = subset.Calls.get(calls, callKey) ? lost
  readTarget: target = subset.CallInfo.target(callInfo)
  readRaises: raises = subset.TargetInfo.raises(target)
  failCheck: canFail = compare.notEqualInt64(raises, 0)
  if canFail flag eachCall
:flag in=eachCall
  readCallName: callName = subset.CallInfo.name(callInfo)
  @s flagStart "  bool f_"
  @w callName
  @s flagEnd " = false;\n"
  goto eachCall
:counters
  countLabels: labelCount = subset.Labels.length(labels)
  goto eachLabel
:eachLabel loop=forEach max=labelCount over=labels
  next labels labelKey readLabel regions
:readLabel in=eachLabel
  readLabelInfo: labelInfo = subset.Labels.get(labels, labelKey) ? lost
  readLabelName: labelName = subset.LabelInfo.name(labelInfo)
  readBounded: bounded = subset.LabelInfo.bounded(labelInfo)
  readKind: kind = subset.LabelInfo.kind(labelInfo)
  if bounded counter position
:counter in=eachLabel
  @s counterStart "  int64_t n_"
  @w labelName
  @s counterEnd " = 0;\n"
  goto position
:position in=eachLabel
  forEachCheck: isForEach = compare.equalInt64(kind, 5)
  if isForEach index eachLabel
:index in=eachLabel
  @s indexStart "  int64_t i_"
  @w labelName
  @s counterEnd
  goto eachLabel
:regions
  goto eachRegion
:eachRegion loop=forEach max=valueCount over=values
  next values regionKey readRegion lets
:readRegion in=eachRegion
  readRegionInfo: regionInfo = subset.Values.get(values, regionKey) ? lost
  readRegionOrigin: regionOrigin = subset.ValueInfo.origin(regionInfo)
  regionCheck: isRegion = compare.equalInt64(regionOrigin, 7)
  if isRegion newRegion eachRegion
:newRegion in=eachRegion
  readRegionName: regionName = subset.ValueInfo.name(regionInfo)
  readCapacity: capacity = subset.ValueInfo.init(regionInfo)
  @s indent
  putRegionName: putValue(buffer, source, regionName)
  @s regionStart " = ss_region_new("
  @w capacity
  @s regionLabel ", \"region `"
  @w regionName
  @s regionOf "` of `"
  @w opName
  @s regionEnd "`\");\n"
  goto eachRegion
:lets
  goto eachLet
:eachLet loop=forEach max=valueCount over=values
  next values letKey readLet done
:readLet in=eachLet
  readLetInfo: letInfo = subset.Values.get(values, letKey) ? lost
  readLetOrigin: letOrigin = subset.ValueInfo.origin(letInfo)
  readInitialized: initialized = subset.ValueInfo.initialized(letInfo)
  letCheck: isLet = compare.equalInt64(letOrigin, 2)
  setCheck: setsHere = logic.and(isLet, initialized)
  if setsHere assignLet eachLet
:assignLet in=eachLet
  readLetName: letName = subset.ValueInfo.name(letInfo)
  readInit: init = subset.ValueInfo.init(letInfo)
  readInitIsName: initIsName = subset.ValueInfo.initIsName(letInfo)
  @s indent
  putLetName: putValue(buffer, source, letName)
  @s assign " = "
  putInit: putLiteral(buffer, source, init, initIsName)
  @s lineEnd ";\n"
  goto eachLet
:done
  return
:lost
  makeLost: lostError = syntax.Rejection.lostName(opName)
  raise lostError

op putFunction "Write one checked operation as a C function: its signature, the depth check of a recursive operation, its locals, then each label and its steps"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input params subset.Params borrowed
  input ops subset.Ops borrowed
  input op subset.OpInfo copied
  input values subset.Values borrowed
  input calls subset.Calls borrowed
  input arguments subset.Arguments borrowed
  input labels subset.Labels borrowed
  input steps subset.Steps borrowed
  raises syntax.Rejection
  let started Bool false mut
  let yes Bool true
:begin
  readName: name = subset.OpInfo.name(op)
  let previous syntax.Word unset mut
  set previous name
  putTheSignature: putSignature(buffer, source, types, params, op) ?^
  @s open " {\n"
  readRecursive: recursive = subset.OpInfo.recursive(op)
  if recursive depthCheck locals
:depthCheck
  readDepth: depth = subset.OpInfo.depth(op)
  @s depthStart "  ss_deeper(&d_"
  @w name
  @s comma ", "
  @w depth
  @s quote ", \""
  @w name
  @s depthEnd "\");\n"
  goto locals
:locals
  putTheLocals: putLocals(buffer, source, types, op, values, calls, labels) ?^
  @s startText "  goto l_begin;\n"
  countSteps: stepCount = subset.Steps.length(steps)
  goto eachStep
:eachStep loop=forEach max=stepCount over=steps
  next steps step readStep finish
:readStep in=eachStep
  readLabel: label = subset.Step.label(step)
  if started compareLabel newLabel
:compareLabel in=eachStep
  sameLabel: sameBlock = syntax.sameText(source, label, previous) ?^
  if sameBlock writeStep newLabel
:newLabel in=eachStep
  @w label labelPrefix
  @s labelEnd ":;\n"
  set started yes
  set previous label
  goto writeStep
:writeStep in=eachStep
  putOneStep: putStep(buffer, source, types, members, ops, op, values, calls, arguments, labels, step) ?^
  goto eachStep
:finish
  @s close "}\n\n"
  return
  let labelPrefix String "l_"

op emitOperation "Check one operation into collections of its own and write it as a C function"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input typeNames subset.TypeNames borrowed
  input members subset.Members borrowed
  input params subset.Params borrowed
  input targets subset.Targets borrowed
  input ops subset.Ops borrowed
  input owners subset.Owners borrowed
  input constants subset.Values borrowed
  input opIndex Int64 copied
  raises syntax.Rejection
  region opWork 268435456
:begin
  newValues: values = subset.Values.new(opWork)
  newCalls: calls = subset.Calls.new(opWork)
  newArguments: arguments = subset.Arguments.new(opWork)
  newLabels: labels = subset.Labels.new(opWork)
  newSteps: steps = subset.Steps.new(opWork)
  check: subset.checkOperation(source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex, values, calls, arguments, labels, steps) ?^
  readOp: op = subset.Ops.getOrTrap(ops, opIndex)
  write: putFunction(buffer, source, types, members, params, ops, op, values, calls, arguments, labels, steps) ?^
  return

## ---------------------------------------------------------------- the whole module

op emitModule "Check a modelled module and write it as one C file: the prelude, its types, constants, operation prototypes, each operation, and a C main that runs main"
  invariant writesC "Writes the prelude, typedefs and structs for records, enums, and lists, relocators and list helpers, constants, a prototype per operation, then each operation as a C function whose labels and steps follow in source order, and a C main returning main's ExitCode"
  invariant countsLoopPasses "A jump to a bounded loop header from inside the loop counts a pass, which traps past the bound; a jump from outside resets the count, and a forEach loop's position"
  invariant refusesOutsideSubset "A module outside the subset is refused, as checkModule refuses it, before anything is written"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  raises syntax.Rejection
  region work 268435456
  let opIndex Int64 0 mut
:begin
  newTypes: types = subset.Types.new(work)
  newTypeNames: typeNames = subset.TypeNames.new(work)
  newMembers: members = subset.Members.new(work)
  newParams: params = subset.Params.new(work)
  newTargets: targets = subset.Targets.new(work)
  newOps: ops = subset.Ops.new(work)
  newOpNames: opNames = subset.OpNames.new(work)
  newOwners: owners = subset.Owners.new(work)
  newConstants: constants = subset.Values.new(work)
  declare: subset.checkDeclarations(source, words, rows, entities, types, typeNames, members, params, targets, ops, opNames, owners, constants, work) ?^
  checkAll: subset.checkModule(source, words, rows, entities) ?^
  @s prelude
  putModuleTypes: putTypes(buffer, source, words, rows, entities, types, members, targets) ?^
  putModuleConstants: putConstants(buffer, source, types, constants) ?^
  putModulePrototypes: putPrototypes(buffer, source, types, params, ops) ?^
  countOps: opCount = subset.Ops.length(ops)
  goto eachOp
:eachOp loop=while max=opCount
  doneCheck: allDone = compare.greaterOrEqualInt64(opIndex, opCount)
  if allDone finish emitOne
:emitOne in=eachOp
  emitThis: emitOperation(buffer, source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex) ?^
  countOp: nextOp = math.addInt64(opIndex, 1)
  set opIndex nextOp
  goto eachOp
:finish
  @s mainText "int main(int argc, char **argv) {\n  refined_start(argc, argv);\n  return o_main();\n}\n"
  return
