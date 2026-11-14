module model "Group rows into entities and find an entity by its name"
  path model
  imports standard.string standard.list standard.map standard.math standard.compare standard.logic standard.test lexer syntax
  exports Entity Entities EntityNames buildModel

record KindRow "One entity kind stage0 compiles, numbered by its row"
  field text String

table kinds "The entity kinds of the stage0 subset; a kind's number is its row's position" KindRow
  row moduleRow text="module"
  row capabilityRow text="capability"
  row constantRow text="constant"
  row operationRow text="operation"
  row callRow text="call"
  row recordRow text="record"
  row enumRow text="enum"
  row typeInstanceRow text="typeInstance"
  row regionRow text="region"
  row taskRow text="task"
  row tableRow text="table"

record Entity "One entity: its name, its kind's number, and the run of rows it owns"
  field name syntax.Word
  field kind Int64
  field first Int64
  field count Int64

instance Entities "Every entity of a module, in source order" list.List Entity

instance EntityNames "The position of each module-level entity in the entity list, by its name" map.Map String Int64

op lookupKind "Find a kind word in the kinds table and return its number"
  input source String borrowed
  input word syntax.Word copied
  output Int64
  raises syntax.Rejection
  let position Int64 0 mut
:begin
  goto scan
:scan loop=forEach max=11 over=kinds
  next kinds entry compare missing
:compare in=scan
  countRow: nextPosition = math.addInt64(position, 1)
  set position nextPosition
  readText: entryText = KindRow.text(entry)
  sameText: isSame = syntax.isText(source, word, entryText) ?^
  if isSame found scan
:found
  return position
:missing
  makeMissing: missingError = syntax.Rejection.unsupportedKind(word)
  raise missingError

op ownsName "Decide whether an entity of a kind is entered in the name map: calls, tasks, and regions belong to one operation, so their names repeat across operations"
  input kind Int64 copied
  output Bool
  let callKind Int64 5
  let regionKind Int64 9
  let taskKind Int64 10
:begin
  callCheck: isCall = compare.equalInt64(kind, callKind)
  regionCheck: isRegion = compare.equalInt64(kind, regionKind)
  taskCheck: isTask = compare.equalInt64(kind, taskKind)
  eitherCheck: either = logic.or(isCall, isRegion)
  anyCheck: owned = logic.or(either, isTask)
  neitherCheck: owns = logic.not(owned)
  return owns

op closeEntity "Record the entity being built, when there is one, and enter its name in the name map when it is a module-level name"
  input source String borrowed
  input entities Entities borrowedMutable
  input names EntityNames borrowedMutable
  input open Bool copied
  input name syntax.Word copied
  input kind Int64 copied
  input first Int64 copied
  input end Int64 copied
  input region Region borrowed
  raises syntax.Rejection
:begin
  if open add done
:add
  measure: count = math.subtractInt64(end, first)
  makeEntity: entity = Entity.new(name, kind, first, count)
  countEntities: position = Entities.length(entities)
  appendEntity: Entities.append(entities, entity)
  ownsCheck: owned = ownsName(kind)
  if owned enter done
:enter
  copyName: key = syntax.wordText(source, name, region) ?^
  enterName: EntityNames.put(names, key, position)
  goto done
:done
  return

op buildModel "Group rows into entities by their `is` rows and enter each module-level entity's name in a map"
  invariant groupsEntities "Each `<name> is <kind>` row starts an entity of that kind owning it and the rows after it up to the next `is` row; kinds are numbered module 1, capability 2, constant 3, operation 4, call 5, record 6, enum 7, typeInstance 8, region 9, task 10, table 11"
  invariant namesEntities "Each entity's name maps to its position in the entity list, except calls, tasks, and regions, whose names belong to the operation they are in"
  invariant rejectsOutsideModel "Another kind is unsupportedKind, a row whose subject is not the entity above it is strayRow, and a module-level name declared twice is duplicateName"
  input source String borrowed
  input words syntax.Words borrowed
  input rows syntax.Rows borrowed
  input entities Entities borrowedMutable
  input names EntityNames borrowedMutable
  raises syntax.Rejection
  region scratch 1048576
  let rowIndex Int64 0 mut
  let open Bool false mut
  let openName syntax.Word unset mut
  let openKind Int64 0 mut
  let openFirst Int64 0 mut
  let yes Bool true
:begin
  countRows: rowCount = syntax.Rows.length(rows)
  makeNameKind: nameKind = syntax.WordKind.name()
  makeOrigin: origin = string.Position.new(0, 1, 1)
  makePlaceholder: placeholder = syntax.Word.new(nameKind, origin, 0)
  set openName placeholder
  goto visit
:visit loop=forEach max=rowCount over=rows
  next rows row readRow finished
:readRow in=visit
  readFirst: first = syntax.Row.first(row)
  readCount: count = syntax.Row.count(row)
  readSubject: subject = syntax.Words.getOrTrap(words, first)
  findPredicate: predicateAt = math.addInt64(first, 1)
  readPredicate: predicate = syntax.Words.getOrTrap(words, predicateAt)
  isCheck: isIs = syntax.isText(source, predicate, isWord="is") ?^
  if isIs opening continuing
:opening in=visit
  closePrevious: closeEntity(source, entities, names, open, openName, openKind, openFirst, rowIndex, scratch) ?^
  threeCheck: isThree = compare.equalInt64(count, 3)
  if isThree readKindWord longIsRow
:readKindWord in=visit
  findKind: kindAt = math.addInt64(first, 2)
  readKind: kindWord = syntax.Words.getOrTrap(words, kindAt)
  classify: kind = lookupKind(source, kindWord) ?^
  ownsCheck: owned = ownsName(kind)
  if owned nameCheck openIt
:nameCheck in=visit
  copySubject: subjectText = syntax.wordText(source, subject, scratch) ?^
  findName: taken = EntityNames.contains(names, subjectText)
  if taken duplicate openIt
:openIt in=visit
  set open yes
  set openName subject
  set openKind kind
  set openFirst rowIndex
  goto advance
:continuing in=visit
  if open sameCheck stray
:sameCheck in=visit
  subjectCheck: sameSubject = syntax.sameText(source, subject, openName) ?^
  if sameSubject advance stray
:advance in=visit
  stepRow: nextRow = math.addInt64(rowIndex, 1)
  set rowIndex nextRow
  goto visit
:finished
  closeLast: closeEntity(source, entities, names, open, openName, openKind, openFirst, rowIndex, scratch) ?^
  return
:longIsRow
  makeLongIsRow: longIsRowError = syntax.Rejection.unsupportedPayload(predicate)
  raise longIsRowError
:duplicate
  makeDuplicate: duplicateError = syntax.Rejection.duplicateName(subject)
  raise duplicateError
:stray
  makeStray: strayError = syntax.Rejection.strayRow(subject)
  raise strayError

@tests

test modelTest "A module's entities are found by name, with their kinds and the rows they own; calls and regions stay out of the name map"
  verifies buildModel groupsEntities
  verifies buildModel namesEntities
  region store 262144
  let source String "# a comment line\ndemo is module\ndemo purpose \"A module to model\"\ndemo path demo\n\nPoint is record\nPoint field x Int64\n\nmain is operation\nmain input none\n\ngreet is call\ngreet in main\n\nscratch is region\nscratch in main\n"
  let refusedText String "the front end refused the source or a step failed"
:begin
  @front X source refused model
  countEntities: entityCount = Entities.length(entitiesX)
  expectCount: test.assertEqualInt64(five=5, entityCount)
  @expectEntity demo demo 1 0 3
  @expectEntity point Point 6 3 2
  @expectEntity main main 4 5 2
  greetCheck: hasGreet = EntityNames.contains(namesX, greetName="greet")
  greetAbsent: noGreet = logic.not(hasGreet)
  expectNoGreet: test.assertTrue(noGreet)
  readGreet: greet = Entities.getOrTrap(entitiesX, three=3)
  greetKind: greetKindNumber = Entity.kind(greet)
  expectGreetKind: test.assertEqualInt64(five, greetKindNumber)
  readScratch: scratchEntity = Entities.getOrTrap(entitiesX, four=4)
  scratchKind: scratchKindNumber = Entity.kind(scratchEntity)
  expectScratchKind: test.assertEqualInt64(nine=9, scratchKindNumber)
  return
:refused
  failRefused: test.fail(refusedText)
  return
