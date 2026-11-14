module emitc "Write a checked stage0 program as one C file"
  path emitc
  imports standard.string standard.buffer standard.list standard.map standard.math standard.compare standard.logic standard.test lexer syntax model subset
  exports emitProgram

## ---------------------------------------------------------------- C spellings

record CTarget "How a standard library target is written in C: the text before, between, and after its arguments; or, for a target of the host library, the name refined_host dispatches on, with how many 64-bit slots its arguments and result take, and for a scoped target the effect (verb and resource) whose scope text it is given last"
  field text String
  field before String
  field between String
  field after String
  field host Bool
  field key String
  field slots Int64
  field results Int64
  field scoped Bool
  field verb String
  field resource String

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

op putCType "Append the C type of a type: a built-in type's spelling, or `t_` and the declared type's module and name"
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
  @s typePrefix "t_"
  putName: putTypeName(buffer, source, info)
  return

op putTypeName "Append a declared type's C name: its module's name, `_`, and its own name, so two modules may declare the same name"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input info subset.TypeInfo copied
:begin
  readModule: module = subset.TypeInfo.module(info)
  readName: name = subset.TypeInfo.name(info)
  putModule: syntax.putWord(buffer, source, module)
  @s underscore "_"
  putOwnName: syntax.putWord(buffer, source, name)
  return

op putCodeName "Append a declared type's C name by its number"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
:begin
  readInfo: info = typeInfoAt(types, code)
  putName: putTypeName(buffer, source, info)
  return

op putOpName "Append an operation's C name: `o_`, its module's name, `_`, and its own name"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input op subset.OpInfo copied
:begin
  readModule: module = subset.OpInfo.module(op)
  readName: name = subset.OpInfo.name(op)
  @s opPrefix "o_"
  putModule: syntax.putWord(buffer, source, module)
  @s underscore "_"
  putOwnName: syntax.putWord(buffer, source, name)
  return

op putDepthName "Append the C name of a recursive operation's depth counter: `d_`, its module's name, `_`, and its own name"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input op subset.OpInfo copied
:begin
  readModule: module = subset.OpInfo.module(op)
  readName: name = subset.OpInfo.name(op)
  @s depthPrefix "d_"
  putModule: syntax.putWord(buffer, source, module)
  @s underscore "_"
  putOwnName: syntax.putWord(buffer, source, name)
  return

op putReturnType "Append the C return type of an operation or operationType: bool when it raises (true on failure), its output's C type, or void"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input output Int64 copied
  input raises Int64 copied
  raises syntax.Rejection
:begin
  raisesCheck: canFail = compare.notEqualInt64(raises, 0)
  outputCheck: hasOutput = compare.notEqualInt64(output, 0)
  if canFail boolReturn valueReturn
:boolReturn
  @s boolText "bool"
  return
:valueReturn
  if hasOutput outputReturn voidReturn
:outputReturn
  putOutputType: putCType(buffer, source, types, output) ?^
  return
:voidReturn
  @s voidText "void"
  return

op putParameters "Append the C parameter list of an operation or operationType: out pointers for its output and error when it raises, then its inputs as `v_<slot>`"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input output Int64 copied
  input raises Int64 copied
  input first Int64 copied
  input count Int64 copied
  raises syntax.Rejection
  let index Int64 0 mut
  let started Bool false mut
  let yes Bool true
:begin
  raisesCheck: canFail = compare.notEqualInt64(raises, 0)
  outputCheck: hasOutput = compare.notEqualInt64(output, 0)
  @s open "("
  if canFail outPointers eachInput
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
  goto eachInput
:eachInput loop=while max=count
  inputsDone: allInputs = compare.greaterOrEqualInt64(index, count)
  if allInputs close putInput
:putInput in=eachInput
  if started comma inputType
:comma in=eachInput
  @s commaText ", "
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

op putReferenceType "Declare an operationType as a C function pointer type, `t_<module>_<name>`, with an operation's return type and parameters"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input info subset.TypeInfo copied
  raises syntax.Rejection
:begin
  readOutput: output = subset.TypeInfo.item(info)
  readRaises: raises = subset.TypeInfo.raises(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  @s typedefStart "typedef "
  putReturnText: putReturnType(buffer, source, types, output, raises) ?^
  @s pointerOpen " (*t_"
  putName: putTypeName(buffer, source, info)
  @s pointerClose ")"
  putTheParameters: putParameters(buffer, source, types, params, output, raises, first, count) ?^
  @s lineEnd ";\n"
  return

op putSlotAt "Append `<slots>[<offset>]`, one of the 64-bit slots a value is flattened into"
  input buffer buffer.ByteBuffer borrowedMutable
  input slots String borrowed
  input offset Int64 copied
:begin
  @s slots
  @s open "["
  buffer.appendInt64(buffer, offset)
  @s close "]"
  return

op putFlatten "Append the C statement that flattens a value into 64-bit slots from an offset on, as the LLVM backend does: text as a pointer and a length, Bool as 0 or 1, Byte and ExitCode sign-extended, pointers as integers, a record or enum by its `fl_` function, anything else as it is"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  input slots String borrowed
  input offset Int64 copied
  input value String borrowed
  raises syntax.Rejection
:begin
  @s indent "  "
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText text notText
:text
  putPointerSlot: putSlotAt(buffer, slots, offset)
  @s pointerStart " = (int64_t)(intptr_t)("
  @s value
  @s pointerEnd ").p; "
  findLength: lengthAt = math.addInt64(offset, 1)
  putLengthSlot: putSlotAt(buffer, slots, lengthAt)
  @s lengthStart " = ("
  @s value
  @s lengthEnd ").n;\n"
  return
:notText
  boolCheck: isBool = compare.equalInt64(code, 4)
  if isBool flag notBool
:flag
  putFlagSlot: putSlotAt(buffer, slots, offset)
  @s flagStart " = ("
  @s value
  @s flagEnd ") ? 1 : 0;\n"
  return
:notBool
  byteCheck: isByte = compare.equalInt64(code, 5)
  if isByte signedByte notByte
:signedByte
  putByteSlot: putSlotAt(buffer, slots, offset)
  @s byteStart " = (int64_t)(int8_t)("
  @s value
  @s closeLine ");\n"
  return
:notByte
  regionCheck: isRegion = compare.equalInt64(code, 6)
  if isRegion pointer notRegion
:notRegion
  builtinCheck: isBuiltin = compare.lessOrEqualInt64(code, 11)
  if isBuiltin integer declared
:declared
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  listCheck: isList = compare.equalInt64(kind, 5)
  referenceCheck: isReference = compare.equalInt64(kind, 8)
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  pointerCheck: isPointer = logic.or(isList, isReference)
  structCheck: isStruct = logic.or(isRecord, isEnum)
  if isPointer pointer notPointer
:notPointer
  if isStruct structured integer
:structured
  @s flattenStart "fl_"
  putFlattenName: putTypeName(buffer, source, info)
  @s open "("
  @s slots
  @s plus " + "
  buffer.appendInt64(buffer, offset)
  @s comma ", "
  @s value
  @s closeLine
  return
:pointer
  putPointer: putSlotAt(buffer, slots, offset)
  @s integerPointer " = (int64_t)(intptr_t)("
  @s value
  @s closeLine
  return
:integer
  putInteger: putSlotAt(buffer, slots, offset)
  @s integerStart " = (int64_t)("
  @s value
  @s closeLine
  return

op putUnflatten "Append the C expression that reads a value of a type back from 64-bit slots from an offset on, the reverse of putFlatten"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  input slots String borrowed
  input offset Int64 copied
  raises syntax.Rejection
:begin
  stringCheck: isString = compare.equalInt64(code, 1)
  bytesCheck: isBytes = compare.equalInt64(code, 11)
  textCheck: isText = logic.or(isString, isBytes)
  if isText text notText
:text
  @s textStart "(ss_string){ (const char *)(intptr_t)"
  putPointerSlot: putSlotAt(buffer, slots, offset)
  @s comma ", "
  findLength: lengthAt = math.addInt64(offset, 1)
  putLengthSlot: putSlotAt(buffer, slots, lengthAt)
  @s textEnd " }"
  return
:notText
  boolCheck: isBool = compare.equalInt64(code, 4)
  if isBool flag notBool
:flag
  @s flagStart "(("
  putFlagSlot: putSlotAt(buffer, slots, offset)
  @s flagEnd " & 1) != 0)"
  return
:notBool
  builtinCheck: isBuiltin = compare.lessOrEqualInt64(code, 11)
  if isBuiltin cast declared
:declared
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  listCheck: isList = compare.equalInt64(kind, 5)
  referenceCheck: isReference = compare.equalInt64(kind, 8)
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  enumCheck: isEnum = compare.equalInt64(kind, 4)
  pointerCheck: isPointer = logic.or(isList, isReference)
  structCheck: isStruct = logic.or(isRecord, isEnum)
  if isPointer pointer notPointer
:notPointer
  if isStruct structured cast
:structured
  @s unflattenStart "uf_"
  putUnflattenName: putTypeName(buffer, source, info)
  @s open "("
  @s slots
  @s plus " + "
  buffer.appendInt64(buffer, offset)
  @s close ")"
  return
:pointer
  @s pointerOpen "("
  putPointerType: putCType(buffer, source, types, code) ?^
  @s pointerCast ")(intptr_t)"
  putPointer: putSlotAt(buffer, slots, offset)
  return
:cast
  @s castOpen "("
  putCastType: putCType(buffer, source, types, code) ?^
  @s castClose ")"
  putCast: putSlotAt(buffer, slots, offset)
  return

op putSlotMembers "Append the statements that flatten a record or enum value `v` into slots `s` (or, reading, set `v` from them): a record's fields in order; an enum's tag in slot 0, then one payload slot for a narrow enum or each variant's payload in order for a wide one"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input code Int64 copied
  input reading Bool copied
  raises syntax.Rejection
  region scratch 1048576
  let index Int64 0 mut
  let offset Int64 0 mut
  let one Int64 1
:begin
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  readNarrow: narrow = subset.TypeInfo.narrow(info)
  recordCheck: isRecord = compare.equalInt64(kind, 3)
  if isRecord eachMember enumTag
:enumTag
  if reading readTag writeTag
:writeTag
  @s writeTagText "  s[0] = (int64_t)v.tag;\n"
  goto tagDone
:readTag
  @s readTagText "  v.tag = (int32_t)s[0];\n"
  goto tagDone
:tagDone
  set offset one
  if narrow narrowPayload eachMember
:narrowPayload
  if reading readPayload writePayload
:writePayload
  @s writePayloadText "  s[1] = v.payload;\n"
  return
:readPayload
  @s readPayloadText "  v.payload = s[1];\n"
  return
:eachMember loop=while max=count
  membersDone: allMembers = compare.greaterOrEqualInt64(index, count)
  if allMembers finish readMember
:readMember in=eachMember
  findMember: memberIndex = math.addInt64(first, index)
  readMemberInfo: member = memberAt(members, memberIndex)
  readMemberName: memberName = subset.MemberInfo.name(member)
  readMemberType: memberType = subset.MemberInfo.type(member)
  countMember: nextMember = math.addInt64(index, 1)
  set index nextMember
  payloadCheck: hasType = compare.greaterThanInt64(memberType, 0)
  if hasType memberValue eachMember
:memberValue in=eachMember
  copyMemberName: memberText = syntax.wordText(source, memberName, scratch) ?^
  if isRecord fieldExpression payloadExpression
:fieldExpression in=eachMember
  joinField: fieldValue = string.concat(fieldPrefix="v.m_", memberText, scratch)
  if reading readField writeField
:writeField in=eachMember
  flattenField: putFlatten(buffer, source, types, memberType, slotsName="s", offset, fieldValue) ?^
  goto advance
:readField in=eachMember
  @s indent "  "
  @s fieldValue
  @s assign " = "
  unflattenField: putUnflatten(buffer, source, types, memberType, slotsName, offset) ?^
  @s lineEnd ";\n"
  goto advance
:payloadExpression in=eachMember
  joinPayload: payloadValue = string.concat(payloadPrefix="v.p_", memberText, scratch)
  if reading readVariant writeVariant
:writeVariant in=eachMember
  flattenPayload: putFlatten(buffer, source, types, memberType, slotsName, offset, payloadValue) ?^
  goto advance
:readVariant in=eachMember
  @s indent
  @s payloadValue
  @s assign
  unflattenPayload: putUnflatten(buffer, source, types, memberType, slotsName, offset) ?^
  @s lineEnd
  goto advance
:advance in=eachMember
  memberSlots: width = subsetSlots(types, memberType)
  stepOffset: nextOffset = math.addInt64(offset, width)
  set offset nextOffset
  goto eachMember
:finish
  return

op putFlatteners "Define `fl_<Type>` and `uf_<Type>`, which flatten a record or enum value into 64-bit slots and read it back, laid out for the host as the LLVM backend lays it out"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input code Int64 copied
  raises syntax.Rejection
  let yes Bool true
  let no Bool false
:begin
  readInfo: info = typeInfoAt(types, code)
  @s flattenStart "static void fl_"
  putFlattenName: putTypeName(buffer, source, info)
  @s flattenParams "(int64_t *s, t_"
  putFlattenType: putTypeName(buffer, source, info)
  @s flattenOpen " v) {\n"
  writeSlots: putSlotMembers(buffer, source, types, members, code, no) ?^
  @s flattenEnd "}\n\n"
  @s unflattenStart "static t_"
  putUnflattenType: putTypeName(buffer, source, info)
  @s unflattenName " uf_"
  putUnflattenName: putTypeName(buffer, source, info)
  @s unflattenOpen "(const int64_t *s) {\n  t_"
  putValueType: putTypeName(buffer, source, info)
  @s unflattenValue " v;\n  memset(&v, 0, sizeof v);\n"
  readSlots: putSlotMembers(buffer, source, types, members, code, yes) ?^
  @s unflattenEnd "  return v;\n}\n\n"
  return

op subsetSlots "How many 64-bit slots a value of a type takes when it is passed to the host: two for String and Bytes, one for another built-in type, and what a declared type worked out"
  input types subset.Types borrowed
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
  readInfo: info = typeInfoAt(types, code)
  readSlots: slots = subset.TypeInfo.slots(info)
  return slots

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

op putRelocated "Append a C expression for a value with its text copied into a region (as the LLVM backend does where a value is stored in a collection or returned in its caller's region); a value without text is written as it is"
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
  @s relocatePrefix "rl_"
  putName: putCodeName(buffer, source, types, code)
  @s open "("
  goto arguments
:arguments
  @s value
  @s comma ", "
  @s region
  @s close ")"
  return

op memberAt "Read a member of a record or enum by its position"
  input members subset.Members borrowed
  input index Int64 copied
  output subset.MemberInfo
:begin
  readMember: member = subset.Members.getOrTrap(members, index)
  return member

## ---------------------------------------------------------------- the module's types

op putTypedefs "Declare a module's records and enums as struct types, its lists as list pointers, its maps as host handles, and its operationTypes as function pointers"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input first Int64 copied
  raises syntax.Rejection
  let code Int64 0 mut
:begin
  set code first
  countTypes: typeCount = subset.Types.length(types)
  goto eachType
:eachType loop=while max=typeCount
  doneCheck: allDone = compare.greaterOrEqualInt64(code, typeCount)
  if allDone done readType
:readType in=eachType
  countCode: nextCode = math.addInt64(code, 1)
  set code nextCode
  readInfo: info = typeInfoAt(types, code)
  readKind: kind = subset.TypeInfo.kind(info)
  listCheck: isList = compare.equalInt64(kind, 5)
  tableCheck: isTable = compare.equalInt64(kind, 6)
  mapCheck: isMap = compare.equalInt64(kind, 7)
  referenceCheck: isReference = compare.equalInt64(kind, 8)
  if isTable eachType notTable
:notTable in=eachType
  if isList listType notList
:notList in=eachType
  if isMap mapType notMap
:notMap in=eachType
  if isReference referenceType structType
:listType in=eachType
  @s listStart "typedef ss_list *t_"
  putListName: putTypeName(buffer, source, info)
  @s lineEnd ";\n"
  goto eachType
:mapType in=eachType
  @s mapStart "typedef int64_t t_"
  putMapName: putTypeName(buffer, source, info)
  @s lineEnd
  goto eachType
:referenceType in=eachType
  putReference: putReferenceType(buffer, source, types, params, info) ?^
  goto eachType
:structType in=eachType
  @s structStart "typedef struct t_"
  putStructName: putTypeName(buffer, source, info)
  @s structMiddle " t_"
  putStructAlias: putTypeName(buffer, source, info)
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
  readKind: kind = subset.TypeInfo.kind(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  readNarrow: narrow = subset.TypeInfo.narrow(info)
  @s structStart "struct t_"
  putName: putTypeName(buffer, source, info)
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
  readKind: kind = subset.TypeInfo.kind(info)
  readFirst: first = subset.TypeInfo.first(info)
  readCount: count = subset.TypeInfo.count(info)
  @s staticStart "static t_"
  putTypeOut: putTypeName(buffer, source, info)
  @s relocateName " rl_"
  putRelocatorName: putTypeName(buffer, source, info)
  @s relocateParams "(t_"
  putTypeIn: putTypeName(buffer, source, info)
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

op putListHelpers "Define a list type's append (`la_`), get (`lg_`), getOrTrap (`lt_`), and set (`ls_`), each typed by the list's item; what the list keeps has its text copied into the list's region first"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  raises syntax.Rejection
:begin
  readInfo: info = typeInfoAt(types, code)
  readItem: item = subset.TypeInfo.item(info)
  @s appendStart "static void la_"
  putTypeName(buffer, source, info)
  @s appendList "(t_"
  putTypeName(buffer, source, info)
  @s appendItem " l, "
  putItemType: putCType(buffer, source, types, item) ?^
  @s appendOpen " v) {\n  v = "
  putItemValue: putRelocated(buffer, source, types, item, itemValue="v", itemRegion="l->region") ?^
  @s appendSlot ";\n  *("
  putSlotType: putCType(buffer, source, types, item) ?^
  @s appendSize " *)ss_list_slot(l, (int64_t)sizeof("
  putSizeType: putCType(buffer, source, types, item) ?^
  @s appendEnd ")) = v;\n}\n\nstatic bool lg_"
  putTypeName(buffer, source, info)
  @s getOut "("
  putOutType: putCType(buffer, source, types, item) ?^
  @s getList " *out, t_"
  putTypeName(buffer, source, info)
  @s getBody " l, int64_t i) {\n  if (ss_list_outside(l, i)) return true;\n  *out = (("
  putGetType: putCType(buffer, source, types, item) ?^
  @s getEnd " *)l->data)[i];\n  return false;\n}\n\nstatic "
  putTrapReturn: putCType(buffer, source, types, item) ?^
  @s trapName " lt_"
  putTypeName(buffer, source, info)
  @s trapList "(t_"
  putTypeName(buffer, source, info)
  @s trapBody " l, int64_t i) {\n  if (ss_list_outside(l, i)) ss_list_trap();\n  return (("
  putTrapType: putCType(buffer, source, types, item) ?^
  @s trapEnd " *)l->data)[i];\n}\n\nstatic bool ls_"
  putTypeName(buffer, source, info)
  @s setList "(t_"
  putTypeName(buffer, source, info)
  @s setIndex " l, int64_t i, "
  putSetItemType: putCType(buffer, source, types, item) ?^
  @s setOpen " v) {\n  v = "
  putSetValue: putRelocated(buffer, source, types, item, itemValue, itemRegion) ?^
  @s setBody ";\n  if (ss_list_outside(l, i)) return true;\n  (("
  putSetType: putCType(buffer, source, types, item) ?^
  @s setEnd " *)l->data)[i] = v;\n  return false;\n}\n\n"
  return

op putMapHelpers "Define a map type's members as calls of the host's map, keys and values flattened to 64-bit slots as the LLVM backend flattens them: new (`mn_`, telling the host its keys are text and whether its values are), put (`mp_`, copying the text a stored record or enum holds into the map's region first), get (`mg_`), contains (`mc_`), remove (`mr_`), length (`ml_`), and the key at a position (`mk_`, for forEach)"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input code Int64 copied
  raises syntax.Rejection
:begin
  readInfo: info = typeInfoAt(types, code)
  readValue: value = subset.TypeInfo.value(info)
  valueSlots: slots = subsetSlots(types, value)
  stringCheck: isString = compare.equalInt64(value, 1)
  bytesCheck: isBytes = compare.equalInt64(value, 11)
  textCheck: textValues = logic.or(isString, isBytes)
  holdsCheck: holds = holdsText(types, value)
  notTextCheck: notTextValue = logic.not(textValues)
  relocateCheck: relocates = logic.and(holds, notTextValue)
  @s newStart "static int64_t mn_"
  putTypeName(buffer, source, info)
  @s newBody "(ss_region *r) {\n  int64_t a[3] = { (int64_t)(intptr_t)r, 1, "
  if textValues textFlag plainFlag
:textFlag
  @s oneText "1"
  goto newEnd
:plainFlag
  @s zeroText "0"
  goto newEnd
:newEnd
  @s newRest " };\n  int64_t o[1] = {0};\n  int64_t e = 0;\n  (void)SS_HOST(\"map.Map.new|1,1,1|1\", a, o, &e);\n  return o[0];\n}\n\nstatic void mp_"
  putTypeName(buffer, source, info)
  @s putParams "(int64_t m, ss_string k, "
  putValueType: putCType(buffer, source, types, value) ?^
  @s putOpen " v) {\n  int64_t a["
  findPutSlots: putSlots = math.addInt64(slots, 3)
  buffer.appendInt64(buffer, putSlots)
  @s putArrays "];\n  int64_t o[1] = {0};\n  int64_t e = 0;\n"
  if relocates relocateValue putKey
:relocateValue
  @s relocateStart "  v = "
  putRelocation: putRelocated(buffer, source, types, value, valueText="v", regionText="refined_handle_region(m)") ?^
  @s lineEnd ";\n"
  goto putKey
:putKey
  @s putKeyText "  a[0] = m;\n  a[1] = (int64_t)(intptr_t)k.p;\n  a[2] = k.n;\n"
  flattenValue: putFlatten(buffer, source, types, value, slotsName="a", 3, valueText) ?^
  @s putHostText "  (void)SS_HOST(\"map.Map.put|1,2,"
  buffer.appendInt64(buffer, slots)
  @s putEnd "|0\", a, o, &e);\n}\n\nstatic bool mg_"
  putTypeName(buffer, source, info)
  @s getParams "("
  putOutType: putCType(buffer, source, types, value) ?^
  @s getOpen " *out, int64_t m, ss_string k) {\n  int64_t a[3] = { m, (int64_t)(intptr_t)k.p, k.n };\n  int64_t o["
  buffer.appendInt64(buffer, slots)
  @s getArrays "];\n  int64_t e = 0;\n  memset(o, 0, sizeof o);\n  if (SS_HOST(\"map.Map.get|1,2|"
  buffer.appendInt64(buffer, slots)
  @s getCall "\", a, o, &e) != 0) return true;\n  if (out) *out = "
  readBack: putUnflatten(buffer, source, types, value, resultsName="o", 0) ?^
  @s getEnd ";\n  return false;\n}\n\nstatic bool mc_"
  putTypeName(buffer, source, info)
  @s containsBody "(int64_t m, ss_string k) {\n  int64_t a[3] = { m, (int64_t)(intptr_t)k.p, k.n };\n  int64_t o[1] = {0};\n  int64_t e = 0;\n  (void)SS_HOST(\"map.Map.contains|1,2|1\", a, o, &e);\n  return (o[0] & 1) != 0;\n}\n\nstatic bool mr_"
  putTypeName(buffer, source, info)
  @s removeBody "(int64_t m, ss_string k) {\n  int64_t a[3] = { m, (int64_t)(intptr_t)k.p, k.n };\n  int64_t o[1] = {0};\n  int64_t e = 0;\n  return SS_HOST(\"map.Map.remove|1,2|0\", a, o, &e) != 0;\n}\n\nstatic int64_t ml_"
  putTypeName(buffer, source, info)
  @s lengthBody "(int64_t m) {\n  int64_t a[1] = { m };\n  int64_t o[1] = {0};\n  int64_t e = 0;\n  (void)SS_HOST(\"map.Map.length|1|1\", a, o, &e);\n  return o[0];\n}\n\nstatic ss_string mk_"
  putTypeName(buffer, source, info)
  @s keyBody "(int64_t m, int64_t i) {\n  int64_t a[2] = { m, i };\n  int64_t o[2] = {0, 0};\n  int64_t e = 0;\n  (void)SS_HOST(\"map.Map.keyAt|1,1|2\", a, o, &e);\n  return (ss_string){ (const char *)(intptr_t)o[0], o[1] };\n}\n\n"
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

op putTable "Define a table as a static array of its rows, each a record of its cells in field order, and `tr_<module>_<table>`, which reads row 1 to n or fails"
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
  putTypeName(buffer, source, info)
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
  putTypeName(buffer, source, info)
  @s readerOpen "("
  putOutType: putCType(buffer, source, types, rowType) ?^
  @s readerBody " *out, int64_t p) {\n  if (p < 1 || p > "
  buffer.appendInt64(buffer, rowCount)
  @s readerMiddle ") return true;\n  *out = tb_"
  putTypeName(buffer, source, info)
  @s readerEnd "[p - 1];\n  return false;\n}\n\n"
  return

op putTypes "Write a module's types: typedefs, struct definitions in source order with their relocators (for those that hold text) and flatteners, then list and map helpers, and tables"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input params subset.Params borrowed
  input targets subset.Targets borrowed
  input first Int64 copied
  raises syntax.Rejection
  let code Int64 0 mut
:begin
  putAllTypedefs: putTypedefs(buffer, source, types, params, first) ?^
  countTypes: typeCount = subset.Types.length(types)
  set code first
  goto eachStruct
:eachStruct loop=while max=typeCount
  structsDone: allStructs = compare.greaterOrEqualInt64(code, typeCount)
  if allStructs helpers readStruct
:readStruct in=eachStruct
  countStruct: nextStruct = math.addInt64(code, 1)
  set code nextStruct
  readStructInfo: structInfo = typeInfoAt(types, code)
  readStructKind: structKind = subset.TypeInfo.kind(structInfo)
  recordCheck: isRecord = compare.equalInt64(structKind, 3)
  enumCheck: isEnum = compare.equalInt64(structKind, 4)
  structCheck: isStruct = logic.or(isRecord, isEnum)
  if isStruct putOneStruct eachStruct
:putOneStruct in=eachStruct
  putTheStruct: putStruct(buffer, source, types, members, code) ?^
  textCheck: structText = subset.TypeInfo.holdsText(structInfo)
  if structText putOneRelocator putOneFlattener
:putOneRelocator in=eachStruct
  putTheRelocator: putRelocator(buffer, source, types, members, code) ?^
  goto putOneFlattener
:putOneFlattener in=eachStruct
  putTheFlattener: putFlatteners(buffer, source, types, members, code) ?^
  goto eachStruct
:helpers
  set code first
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
  if tableType putOneTable mapKind
:mapKind in=eachList
  isMapCheck: mapType = compare.equalInt64(listKind, 7)
  if mapType putOneMap eachList
:putOneTable in=eachList
  putTheTable: putTable(buffer, source, words, rows, entities, types, members, targets, code) ?^
  goto eachList
:putOneList in=eachList
  putTheList: putListHelpers(buffer, source, types, code) ?^
  goto eachList
:putOneMap in=eachList
  putTheMap: putMapHelpers(buffer, source, types, code) ?^
  goto eachList
:done
  return

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

op putConstants "Define every constant of a module as a static C value, `k_<module>_<name>`"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input constants subset.Values borrowed
  input module syntax.Word copied
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
  @s constantStart " k_"
  @w module
  @s underscore "_"
  @w name
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
  makeLostName: lostError = syntax.Rejection.lostName(module)
  raise lostError

op putSignature "Append an operation's C signature: `static`, its return type (bool when it raises, so the caller can branch), `o_<module>_<name>`, then out pointers for its output and error when it raises, then its inputs"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input op subset.OpInfo copied
  raises syntax.Rejection
:begin
  readOutput: output = subset.OpInfo.output(op)
  readRaises: raises = subset.OpInfo.raises(op)
  readFirst: first = subset.OpInfo.firstParam(op)
  readCount: count = subset.OpInfo.paramCount(op)
  @s staticStart "static "
  putReturnText: putReturnType(buffer, source, types, output, raises) ?^
  @s space " "
  putName: putOpName(buffer, source, op)
  putTheParameters: putParameters(buffer, source, types, params, output, raises, first, count) ?^
  return

op putPrototypes "Declare every operation of a module (those from a position in the operation list on), and a depth counter for each one that recurses"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input params subset.Params borrowed
  input ops subset.Ops borrowed
  input first Int64 copied
  raises syntax.Rejection
  let index Int64 0 mut
:begin
  set index first
  countOps: opCount = subset.Ops.length(ops)
  goto eachOp
:eachOp loop=while max=opCount
  doneCheck: allDone = compare.greaterOrEqualInt64(index, opCount)
  if allDone done putOne
:putOne in=eachOp
  readOp: op = subset.Ops.getOrTrap(ops, index)
  countOp: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  putTheSignature: putSignature(buffer, source, types, params, op) ?^
  @s lineEnd ";\n"
  readRecursive: recursive = subset.OpInfo.recursive(op)
  if recursive depth eachOp
:depth in=eachOp
  @s depthStart "static int64_t "
  putDepth: putDepthName(buffer, source, op)
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

op putGrants "Append the scope of every grant of `<verb> <resource>` in a capability of an operation's module, each after a newline, as C text: the scope a `uses` row gives the operation"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input op subset.OpInfo copied
  input capability syntax.Word copied
  input verb String borrowed
  input resource String borrowed
  raises syntax.Rejection
  let entityIndex Int64 0 mut
  let rowIndex Int64 0 mut
:begin
  readFirst: first = subset.OpInfo.moduleFirst(op)
  readEnd: end = subset.OpInfo.moduleEnd(op)
  findSpan: span = math.subtractInt64(end, first)
  set entityIndex first
  goto eachEntity
:eachEntity loop=while max=span
  entitiesDone: allEntities = compare.greaterOrEqualInt64(entityIndex, end)
  if allEntities done readEntity
:readEntity in=eachEntity
  readTheEntity: entity = model.Entities.getOrTrap(entities, entityIndex)
  countEntity: nextEntity = math.addInt64(entityIndex, 1)
  set entityIndex nextEntity
  readKind: kind = model.Entity.kind(entity)
  capabilityCheck: isCapability = compare.equalInt64(kind, 2)
  if isCapability nameCheck eachEntity
:nameCheck in=eachEntity
  readName: name = model.Entity.name(entity)
  sameName: named = syntax.sameText(source, name, capability) ?^
  if named rowsStart eachEntity
:rowsStart in=eachEntity
  readRowsFirst: rowsFirst = model.Entity.first(entity)
  readRowsCount: rowsCount = model.Entity.count(entity)
  findRowsEnd: rowsEnd = math.addInt64(rowsFirst, rowsCount)
  set rowIndex rowsFirst
  goto eachRow
:eachRow loop=while max=rowsCount in=eachEntity
  rowsDone: allRows = compare.greaterOrEqualInt64(rowIndex, rowsEnd)
  if allRows eachEntity readRow
:readRow in=eachRow
  fetchRow: row = syntax.Rows.getOrTrap(rows, rowIndex)
  advanceRow: nextRow = math.addInt64(rowIndex, 1)
  set rowIndex nextRow
  readCount: count = syntax.Row.count(row)
  shapeCheck: isFive = compare.equalInt64(count, 5)
  if isFive readGrant eachRow
:readGrant in=eachRow
  readRowFirst: wordFirst = syntax.Row.first(row)
  findPredicate: predicateAt = math.addInt64(wordFirst, 1)
  readPredicate: predicate = syntax.Words.getOrTrap(words, predicateAt)
  grantsCheck: isGrant = syntax.isText(source, predicate, grantsWord="grants") ?^
  if isGrant verbCheck eachRow
:verbCheck in=eachRow
  findVerb: verbAt = math.addInt64(wordFirst, 2)
  readVerbWord: verbWord = syntax.Words.getOrTrap(words, verbAt)
  findResource: resourceAt = math.addInt64(wordFirst, 3)
  readResourceWord: resourceWord = syntax.Words.getOrTrap(words, resourceAt)
  findScope: scopeAt = math.addInt64(wordFirst, 4)
  readScopeWord: scopeWord = syntax.Words.getOrTrap(words, scopeAt)
  sameVerb: verbFits = syntax.isText(source, verbWord, verb) ?^
  sameResource: resourceFits = syntax.isText(source, resourceWord, resource) ?^
  bothCheck: grantFits = logic.and(verbFits, resourceFits)
  readScopeKind: scopeKind = syntax.Word.kind(scopeWord)
  if grantFits scopeCheck eachRow
:scopeCheck in=eachRow
  match scopeKind
  case text putGrant
  others eachRow
:putGrant in=eachRow
  @s separator " \"\\n\" "
  @w scopeWord
  goto eachRow
:done
  return

op putScope "Append, as C text, the scope text the runtime checks a scoped target's argument against (D-38): `<verb> <resource>`, then the scope of each grant of it in the capabilities the operation uses, each after a newline, as the LLVM backend writes it"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input op subset.OpInfo copied
  input verb String borrowed
  input resource String borrowed
  raises syntax.Rejection
  let rowIndex Int64 0 mut
:begin
  @s quote "\""
  @s verb
  @s space " "
  @s resource
  @s quote
  readEntityIndex: entityIndex = subset.OpInfo.entity(op)
  readEntity: entity = model.Entities.getOrTrap(entities, entityIndex)
  readRowsFirst: rowsFirst = model.Entity.first(entity)
  readRowsCount: rowsCount = model.Entity.count(entity)
  findRowsEnd: rowsEnd = math.addInt64(rowsFirst, rowsCount)
  set rowIndex rowsFirst
  goto eachRow
:eachRow loop=while max=rowsCount
  rowsDone: allRows = compare.greaterOrEqualInt64(rowIndex, rowsEnd)
  if allRows done readRow
:readRow in=eachRow
  fetchRow: row = syntax.Rows.getOrTrap(rows, rowIndex)
  advanceRow: nextRow = math.addInt64(rowIndex, 1)
  set rowIndex nextRow
  readCount: count = syntax.Row.count(row)
  shapeCheck: isThree = compare.equalInt64(count, 3)
  if isThree readUses eachRow
:readUses in=eachRow
  readRowFirst: wordFirst = syntax.Row.first(row)
  findPredicate: predicateAt = math.addInt64(wordFirst, 1)
  readPredicate: predicate = syntax.Words.getOrTrap(words, predicateAt)
  usesCheck: isUses = syntax.isText(source, predicate, usesWord="uses") ?^
  if isUses capabilityName eachRow
:capabilityName in=eachRow
  findCapability: capabilityAt = math.addInt64(wordFirst, 2)
  readCapability: capability = syntax.Words.getOrTrap(words, capabilityAt)
  putTheGrants: putGrants(buffer, source, words, rows, entities, op, capability, verb, resource) ?^
  goto eachRow
:done
  return

op putHostCall "Write a call of a host library target as one C block that flattens its arguments into 64-bit slots, calls refined_host by the target's name and slot counts (as the LLVM backend does), and reads back its result and failure"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  input spelling CTarget borrowed
  input op subset.OpInfo copied
  raises syntax.Rejection
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
  readScoped: scoped = CTarget.scoped(spelling)
  if scoped scopeSlots resultArray
:scopeSlots
  readVerb: verb = CTarget.verb(spelling)
  readResource: resource = CTarget.resource(spelling)
  @s scopeStart ", (int64_t)(intptr_t)("
  putScopeText: putScope(buffer, source, words, rows, entities, op, verb, resource) ?^
  @s scopeLength "), (int64_t)(sizeof("
  putScopeAgain: putScope(buffer, source, words, rows, entities, op, verb, resource) ?^
  @s scopeEnd ") - 1)"
  goto resultArray
:resultArray
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
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input ops subset.Ops borrowed
  input arguments subset.Arguments borrowed
  input info subset.CallInfo copied
  input op subset.OpInfo copied
  raises syntax.Rejection
  let yes Bool true
  let no Bool false
:begin
  readName: name = subset.CallInfo.name(info)
  readTarget: target = subset.CallInfo.target(info)
  readResult: result = subset.CallInfo.result(info)
  readHasResult: hasResult = subset.CallInfo.hasResult(info)
  readRaises: raises = subset.TargetInfo.raises(target)
  readOutput: output = subset.TargetInfo.output(target)
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
  writeHostCall: putHostCall(buffer, source, words, rows, entities, arguments, info, hostRow, op) ?^
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
  case reference referenceCall
  case recordNew recordNewCall
  case fieldRead fieldReadCall
  case variantMake variantCall
  case listNew listNewCall
  case listAppend listAppendCall
  case listLength listLengthCall
  case listGet listGetCall
  case listGetOrTrap listGetOrTrapCall
  case listSet listSetCall
  case tableRowAt tableRowAtCall
  case tableLength tableLengthCall
  case mapNew mapNewCall
  case mapPut mapPutCall
  case mapGet mapGetCall
  case mapContains mapContainsCall
  case mapRemove mapRemoveCall
  case mapLength mapLengthCall
  case recordWith recordWithCall
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
  readOp: calledOp = subset.Ops.getOrTrap(ops, owner)
  putCalledName: putOpName(buffer, source, calledOp)
  goto callOpen
:referenceCall
  readReference: reference = subset.CallInfo.reference(info)
  putReferenceName: putValue(buffer, source, reference)
  goto callOpen
:callOpen
  @s open "("
  if canFail outPointers operationArguments
:outPointers
  outputCheck: hasOutput = compare.notEqualInt64(output, 0)
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
  @s appendPrefix "la_"
  putAppendName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:listLengthCall
  readLengthList: lengthList = argumentAt(arguments, info, 0)
  putLengthList: putValue(buffer, source, lengthList)
  @s lengthText "->length"
  goto finish
:listGetCall
  @s getPrefix "lg_"
  putGetName: putCodeName(buffer, source, types, owner)
  goto outArguments
:listGetOrTrapCall
  @s trapPrefix "lt_"
  putTrapName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:listSetCall
  @s setPrefix "ls_"
  putSetName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:tableRowAtCall
  @s rowAtPrefix "tr_"
  putRowAtName: putCodeName(buffer, source, types, owner)
  goto outArguments
:tableLengthCall
  readLengthInfo: lengthInfo = typeInfoAt(types, owner)
  readRowCount: rowCount = subset.TypeInfo.count(lengthInfo)
  buffer.appendInt64(buffer, rowCount)
  goto finish
:mapNewCall
  @s mapNewPrefix "mn_"
  putMapNewName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:mapPutCall
  @s mapPutPrefix "mp_"
  putMapPutName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:mapGetCall
  @s mapGetPrefix "mg_"
  putMapGetName: putCodeName(buffer, source, types, owner)
  goto outArguments
:mapContainsCall
  @s mapContainsPrefix "mc_"
  putMapContainsName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:mapRemoveCall
  @s mapRemovePrefix "mr_"
  putMapRemoveName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:mapLengthCall
  @s mapLengthPrefix "ml_"
  putMapLengthName: putCodeName(buffer, source, types, owner)
  goto helperArguments
:recordWithCall
  if hasResult withValue withNothing
:withValue
  readWithRecord: withRecord = argumentAt(arguments, info, 0)
  readWithValue: withNew = argumentAt(arguments, info, 1)
  readWithField: withField = subset.CallInfo.reference(info)
  putWithRecord: putValue(buffer, source, withRecord)
  @s statementEnd "; "
  putWithResult: putValue(buffer, source, result)
  @w withField fieldPrefix
  @s assign
  putWithNew: putValue(buffer, source, withNew)
  goto finish
:withNothing
  @s nothingText "(void)0"
  goto finish
:outArguments
  @s open
  if hasResult outAddress outNull
:outAddress
  @s address
  putHelperOut: putValue(buffer, source, result)
  goto outRest
:outNull
  @s null
  goto outRest
:outRest
  putOutArguments: putArguments(buffer, source, arguments, info, comma, no, yes)
  @s close
  goto finish
:helperArguments
  @s open
  putHelperArguments: putArguments(buffer, source, arguments, info, comma, no, no)
  @s close
  goto finish
:finish
  @s lineEnd ";\n"
  return
@reject lostName name lost
  let flagPrefix String "f_"
  let fieldPrefix String ".m_"

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
  putDepth: putDepthName(buffer, source, op)
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
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
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
  writeCall: putCall(buffer, source, words, rows, entities, types, members, ops, arguments, callInfo, op) ?^
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
  collectionCheck: overCollection = compare.greaterThanInt64(number, 0)
  if overCollection collectionKind listNextStep
:collectionKind
  readCollectionInfo: collectionInfo = typeInfoAt(types, number)
  readCollectionKind: collectionKindCode = subset.TypeInfo.kind(collectionInfo)
  mapCheck: overMap = compare.equalInt64(collectionKindCode, 7)
  if overMap mapNextStep tableNextStep
:mapNextStep
  @s ifIndex "  if (i_"
  @w label
  @s mapLength " < ml_"
  putLengthName: putTypeName(buffer, source, collectionInfo)
  @s open "("
  putLengthMap: putValue(buffer, source, subject)
  @s mapOpen ")) { "
  putKey: putValue(buffer, source, extra)
  @s keyRead " = mk_"
  putKeyName: putTypeName(buffer, source, collectionInfo)
  @s open
  putKeyMap: putValue(buffer, source, subject)
  @s keyIndex ", i_"
  @w label
  @s keyIndexEnd "); i_"
  @w label
  @s indexEnd " += 1; "
  putMapYes: putJump(buffer, source, labels, label, target) ?^
  @s nextElse " } else "
  putMapNo: putJump(buffer, source, labels, label, otherwise) ?^
  @s newline
  goto done
:tableNextStep
  readRowCount: rowCount = subset.TypeInfo.count(collectionInfo)
  @s ifIndex
  @w label
  @s less " < "
  buffer.appendInt64(buffer, rowCount)
  @s tableOpen ") { "
  putTableItem: putValue(buffer, source, extra)
  @s tableRead " = tb_"
  putTableName: putTypeName(buffer, source, collectionInfo)
  @s tableIndex "[i_"
  @w label
  @s indexStep "]; i_"
  @w label
  @s indexEnd
  putTableYes: putJump(buffer, source, labels, label, target) ?^
  @s nextElse
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
  @s indexStep
  @w label
  @s indexEnd
  putNextYes: putJump(buffer, source, labels, label, target) ?^
  @s nextElse
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

op putLocals "Declare an operation's values, failure flags, loop counters and positions, and regions; read its module's constants; then set its lets (a let of an operationType names an operation, `o_<module>_<name>`)"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input types subset.Types borrowed
  input targets subset.Targets borrowed
  input ops subset.Ops borrowed
  input op subset.OpInfo copied
  input constants subset.Values borrowed
  input values subset.Values borrowed
  input calls subset.Calls borrowed
  input labels subset.Labels borrowed
  raises syntax.Rejection
:begin
  readOpName: opName = subset.OpInfo.name(op)
  readModule: module = subset.OpInfo.module(op)
  countConstants: constantCount = subset.Values.length(constants)
  goto eachConstant
:eachConstant loop=forEach max=constantCount over=constants
  next constants constantKey readConstant valuesStart
:readConstant in=eachConstant
  readConstantInfo: constantInfo = subset.Values.get(constants, constantKey) ? lost
  readConstantName: constantName = subset.ValueInfo.name(constantInfo)
  readConstantCode: constantCode = subset.ValueInfo.code(constantInfo)
  @s indent "  "
  putConstantType: putCType(buffer, source, types, constantCode) ?^
  @s space " "
  putConstantName: putValue(buffer, source, constantName)
  @s constantStart " = k_"
  @w module
  @s underscore "_"
  @w constantName
  @s lineEnd ";\n"
  goto eachConstant
:valuesStart
  countValues: valueCount = subset.Values.length(values)
  goto eachValue
:eachValue loop=forEach max=valueCount over=values
  next values key readValue flags
:readValue in=eachValue
  readInfo: info = subset.Values.get(values, key) ? lost
  readOrigin: origin = subset.ValueInfo.origin(info)
  readCode: code = subset.ValueInfo.code(info)
  inputCheck: isInput = compare.equalInt64(origin, 4)
  if isInput eachValue declare
:declare in=eachValue
  readName: name = subset.ValueInfo.name(info)
  @s indent
  putType: putCType(buffer, source, types, code) ?^
  @s space
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
  readLetCode: letCode = subset.ValueInfo.code(letInfo)
  readInit: init = subset.ValueInfo.init(letInfo)
  readInitIsName: initIsName = subset.ValueInfo.initIsName(letInfo)
  @s indent
  putLetName: putValue(buffer, source, letName)
  @s assign " = "
  builtinCheck: isBuiltin = compare.lessOrEqualInt64(letCode, 11)
  if isBuiltin literal referenceCheck
:referenceCheck in=eachLet
  readLetType: letType = typeInfoAt(types, letCode)
  readLetKind: letKind = subset.TypeInfo.kind(letType)
  referenceKindCheck: isReference = compare.equalInt64(letKind, 8)
  if isReference operationLet literal
:operationLet in=eachLet
  @view operationText init lost
  findOperation: operationTarget = subset.Targets.get(targets, operationText) ? lost
  readOperationIndex: operationIndex = subset.TargetInfo.owner(operationTarget)
  readOperation: operation = subset.Ops.getOrTrap(ops, operationIndex)
  putOperation: putOpName(buffer, source, operation)
  goto letEnd
:literal in=eachLet
  putInit: putLiteral(buffer, source, init, initIsName)
  goto letEnd
:letEnd in=eachLet
  @s lineEnd
  goto eachLet
:done
  return
:lost
  makeLost: lostError = syntax.Rejection.lostName(opName)
  raise lostError

op putFunction "Write one checked operation as a C function: its signature, the depth check of a recursive operation, its locals, then each label and its steps"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input types subset.Types borrowed
  input members subset.Members borrowed
  input params subset.Params borrowed
  input targets subset.Targets borrowed
  input ops subset.Ops borrowed
  input op subset.OpInfo copied
  input constants subset.Values borrowed
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
  @s depthStart "  ss_deeper(&"
  putDepth: putDepthName(buffer, source, op)
  @s comma ", "
  @w depth
  @s quote ", \""
  @w name
  @s depthEnd "\");\n"
  goto locals
:locals
  putTheLocals: putLocals(buffer, source, types, targets, ops, op, constants, values, calls, labels) ?^
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
  putOneStep: putStep(buffer, source, words, rows, entities, types, members, ops, op, values, calls, arguments, labels, step) ?^
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
  region opWork 1073741824
:begin
  newValues: values = subset.Values.new(opWork)
  newCalls: calls = subset.Calls.new(opWork)
  newArguments: arguments = subset.Arguments.new(opWork)
  newLabels: labels = subset.Labels.new(opWork)
  newSteps: steps = subset.Steps.new(opWork)
  check: subset.checkOperation(source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex, values, calls, arguments, labels, steps) ?^
  readOp: op = subset.Ops.getOrTrap(ops, opIndex)
  write: putFunction(buffer, source, words, rows, entities, types, members, params, targets, ops, op, constants, values, calls, arguments, labels, steps) ?^
  return

## ---------------------------------------------------------------- the whole module

op emitModule "Check one module of a program and write it: its types, its constants, a prototype for each of its operations, then each operation; what it declares is published for the modules after it"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input first Int64 copied
  input end Int64 copied
  input types subset.Types borrowedMutable
  input members subset.Members borrowedMutable
  input params subset.Params borrowedMutable
  input ops subset.Ops borrowedMutable
  input owners subset.Owners borrowedMutable
  input globalTypeNames subset.TypeNames borrowedMutable
  input globalTargets subset.Targets borrowedMutable
  raises syntax.Rejection
  region moduleWork 1073741824
  let opIndex Int64 0 mut
:begin
  newTypeNames: typeNames = subset.TypeNames.new(moduleWork)
  newTargets: targets = subset.Targets.new(moduleWork)
  newOpNames: opNames = subset.OpNames.new(moduleWork)
  newConstants: constants = subset.Values.new(moduleWork)
  countTypes: typeBase = subset.Types.length(types)
  countBefore: opBase = subset.Ops.length(ops)
  set opIndex opBase
  declare: subset.checkModuleDeclarations(source, words, rows, entities, first, end, types, typeNames, members, params, targets, ops, opNames, owners, constants, globalTypeNames, globalTargets, moduleWork) ?^
  readModuleEntity: moduleEntity = model.Entities.getOrTrap(entities, first)
  readModule: module = model.Entity.name(moduleEntity)
  putModuleTypes: putTypes(buffer, source, words, rows, entities, types, members, params, targets, typeBase) ?^
  putModuleConstants: putConstants(buffer, source, types, constants, module) ?^
  putModulePrototypes: putPrototypes(buffer, source, types, params, ops, opBase) ?^
  countOps: opCount = subset.Ops.length(ops)
  goto eachOp
:eachOp loop=while max=opCount
  doneCheck: allDone = compare.greaterOrEqualInt64(opIndex, opCount)
  if allDone done emitOne
:emitOne in=eachOp
  emitThis: emitOperation(buffer, source, words, rows, entities, types, typeNames, members, params, targets, ops, owners, constants, opIndex) ?^
  countOp: nextOp = math.addInt64(opIndex, 1)
  set opIndex nextOp
  goto eachOp
:done
  return

op entryModule "Find the module entity whose `<name>.main` is the program's entry, for a diagnostic that the entry is missing; the first entity when no module has that name"
  input source String borrowed
  input entities model.Entities borrowed
  input entry String borrowed
  input region Region borrowed
  output syntax.Word
  raises syntax.Rejection
:begin
  readFirst: firstEntity = model.Entities.getOrTrap(entities, 0)
  readFirstName: firstName = model.Entity.name(firstEntity)
  countEntities: count = model.Entities.length(entities)
  goto eachEntity
:eachEntity loop=forEach max=count over=entities
  next entities entity readEntity missing
:readEntity in=eachEntity
  readKind: kind = model.Entity.kind(entity)
  moduleCheck: isModule = compare.equalInt64(kind, 1)
  if isModule compareName eachEntity
:compareName in=eachEntity
  readName: name = model.Entity.name(entity)
  copyName: nameText = syntax.wordText(source, name, region) ?^
  joinMain: mainText = string.concat(nameText, mainSuffix=".main", region)
  sameCheck: same = string.equals(mainText, entry)
  if same found eachEntity
:found
  return name
:missing
  return firstName

op emitProgram "Check a modelled program and write it as one C file: the prelude, each module in source order (its types, constants, prototypes, and operations), and a C main that runs the entry operation"
  invariant writesC "Writes the prelude, then for each module typedefs and structs for its records, enums, lists, maps, and operationTypes, relocators, flatteners, list and map helpers, tables, constants, a prototype per operation, and each operation as a C function whose labels and steps follow in source order; then a C main returning the entry operation's ExitCode. Every name a module declares is written `<module>_<name>`, so modules may share names"
  invariant countsLoopPasses "A jump to a bounded loop header from inside the loop counts a pass, which traps past the bound; a jump from outside resets the count, and a forEach loop's position"
  invariant refusesOutsideSubset "A program outside the subset is refused at the first word concerned, as checkProgram refuses it, and a program whose entry is not an operation is refused at its module"
  input buffer buffer.ByteBuffer borrowedMutable
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities model.Entities borrowed
  input entry String borrowed
  raises syntax.Rejection
  region work 4294967296
  let first Int64 0 mut
:begin
  newTypes: types = subset.Types.new(work)
  newMembers: members = subset.Members.new(work)
  newParams: params = subset.Params.new(work)
  newOps: ops = subset.Ops.new(work)
  newOwners: owners = subset.Owners.new(work)
  newTypeNames: globalTypeNames = subset.TypeNames.new(work)
  newTargets: globalTargets = subset.Targets.new(work)
  declareAll: subset.declareBuiltins(source, types, globalTypeNames, params, globalTargets, work) ?^
  countEntities: count = model.Entities.length(entities)
  emptyCheck: isEmpty = compare.equalInt64(count, 0)
  if isEmpty empty start
:start
  @s prelude
  goto eachModule
:eachModule loop=while max=count
  doneCheck: allDone = compare.greaterOrEqualInt64(first, count)
  if allDone entryCheck emitOne
:emitOne in=eachModule
  findEnd: end = subset.nextModule(entities, first)
  emitIt: emitModule(buffer, source, words, rows, entities, first, end, types, members, params, ops, owners, globalTypeNames, globalTargets) ?^
  set first end
  goto eachModule
:entryCheck
  findEntry: entryTarget = subset.Targets.get(globalTargets, entry) ? noEntry
  readEntryKind: entryKind = subset.TargetInfo.kind(entryTarget)
  match entryKind
  case operation entryOperation
  others noEntry
:entryOperation
  readOwner: owner = subset.TargetInfo.owner(entryTarget)
  readEntryOp: entryOp = subset.Ops.getOrTrap(ops, owner)
  @s mainStart "int main(int argc, char **argv) {\n  refined_start(argc, argv);\n  return "
  putEntryName: putOpName(buffer, source, entryOp)
  @s mainEnd "();\n}\n"
  return
:noEntry
  findModule: moduleName = entryModule(source, entities, entry, work) ?^
  makeNoMain: noMainError = syntax.Rejection.noMain(moduleName)
  raise noMainError
:empty
  makePlaceholderKind: placeholderKind = syntax.WordKind.name()
  makeOrigin: origin = string.Position.new(0, 1, 1)
  makePlaceholder: placeholder = syntax.Word.new(placeholderKind, origin, 0)
  makeNoModule: noModuleError = syntax.Rejection.notModule(placeholder)
  raise noModuleError
