## A stage0 sample: maps with String keys, through the host's map. It counts
## words in a map of numbers (putting a key again replaces its value), keeps
## records holding text in a second map (the text is copied into the map's
## region), reads them back by key, branches on a missing key, removes one,
## and walks a map's keys with `forEach` in the order they were first put. It
## exits with code 0:
##
##   the: 3
##   cat: 1
##   keys: 4
##   no dog
##   counted: the cat sat mat
##   Ada is 36, likes tea
##   Linus is 54, likes coffee
##   removed Ada: 1
##   no Ada
module maps "Count words in a map and keep records by name in another"
  path maps
  imports standard.console standard.math standard.map standard.string
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record Person "Someone's age and favourite drink"
  field age Int64
  field drink String

instance Counts "How many times each word was seen" map.Map String Int64

instance People "People by name" map.Map String Person

op count "Count one more sighting of a word"
  input counts Counts borrowedMutable
  input word String borrowed
  let seen Int64 0 mut
:begin
  readSeen: before = Counts.get(counts, word) ? fresh
  set seen before
  goto add
:fresh
  goto add
:add
  addOne: after = math.addInt64(seen, 1)
  putIt: Counts.put(counts, word, after)
  return

op report "Print a label and a number on one line; a failed write is discarded"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op describe "Print a person's name, age, and drink, or that nobody has that name"
  input people People borrowed
  input name String borrowed
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
:begin
  findPerson: person = People.get(people, name) ? missing
  readAge: age = Person.age(person)
  readDrink: drink = Person.drink(person)
  ageText: ageDigits = string.fromInt64(age, scratch)
  joinName: withIs = string.concat(name, isText=" is ", scratch)
  joinAge: withAge = string.concat(withIs, ageDigits, scratch)
  joinLikes: withLikes = string.concat(withAge, likesText=", likes ", scratch)
  joinDrink: line = string.concat(withLikes, drink, scratch)
  writeLine: console.writeLine(line) ~
  return
:missing
  joinNo: noLine = string.concat(noText="no ", name, scratch)
  writeNo: console.writeLine(noLine) ~
  return

op addPerson "Keep a person whose drink is built in a region of this operation, released at its return: the map keeps its own copy of the text"
  input people People borrowedMutable
  input name String borrowed
  input age Int64 copied
  input drink String borrowed
  region scratch 65536
:begin
  copyDrink: drinkCopy = string.concat(drink, emptyText="", scratch)
  makePerson: person = Person.new(age, drinkCopy, scratch)
  putPerson: People.put(people, name, person)
  return

op main "Count words, keep people, and read both maps back"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region store 1048576
  let okCode ExitCode 0
:begin
  makeCounts: counts = Counts.new(store)
  countThe: count(counts, the="the")
  countCat: count(counts, cat="cat")
  countThe2: count(counts, the)
  countSat: count(counts, sat="sat")
  countThe3: count(counts, the)
  countMat: count(counts, mat="mat")
  readThe: theCount = Counts.get(counts, the) ? noThe
  reportThe: report(theText="the: ", theCount)
  readCat: catCount = Counts.get(counts, cat) ? noThe
  reportCat: report(catText="cat: ", catCount)
  countKeys: keyCount = Counts.length(counts)
  reportKeys: report(keysText="keys: ", keyCount)
  dogCheck: hasDog = Counts.contains(counts, dog="dog")
  if hasDog dogFound noDog
:dogFound
  writeDog: console.writeLine(dogText="a dog") ~
  goto listKeys
:noDog
  writeNoDog: console.writeLine(noDogText="no dog") ~
  goto listKeys
:listKeys
  writeCounted: console.write(countedText="counted:") ~
  goto eachKey
:eachKey loop=forEach max=keyCount over=counts
  next counts key printKey keysDone
:printKey in=eachKey
  writeSpace: console.write(space=" ") ~
  writeKey: console.write(key) ~
  goto eachKey
:keysDone
  writeEnd: console.writeLine(empty="") ~
  makePeople: people = People.new(store)
  addAda: addPerson(people, ada="Ada", thirtySix=36, tea="tea")
  addLinus: addPerson(people, linus="Linus", fiftyFour=54, coffee="coffee")
  describeAda: describe(people, ada)
  describeLinus: describe(people, linus)
  removeAda: People.remove(people, ada) ? noThe
  countPeople: peopleCount = People.length(people)
  reportPeople: report(removedText="removed Ada: ", peopleCount)
  describeAgain: describe(people, ada)
  return okCode
:noThe
  writeMissing: console.writeLine(missingText="a word went missing") ~
  return okCode
