"""A program that exercises every host target the runtime in SemanticScript implements (D-130).

tests/test_runtime_nolibc.py builds it with that runtime and requires what it prints, to standard output and standard
error, and its exit code to be exactly what `refined run` gives: byte buffers (text, numbers, bytes, `toBytes`, text
that is not UTF-8), `string.fromBytes`, maps of numbers (thousands of keys, so the index is rebuilt; removals; keys
put again; reading them back in order), maps of text keys and text values (copied into the map's region, which
`arena.remaining` shows), maps whose values are records holding text (D-107, `refined_handle_region`), sets of
numbers and of text, every log level, and a collection's region released and made again.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

DSL = r'''module hosttour "Use every host target the runtime in SemanticScript implements and print what they give"
  path hosttour
  imports standard.console standard.string standard.compare standard.math standard.buffer standard.map standard.set standard.log standard.arena standard.bytes
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability stderrWriter "Authority to write log lines to standard error" write console.stderr none

record Entry "A value stored in a map that holds text"
  field name String
  field size Int64

instance Numbers "Whole numbers by whole number" map.Map Int64 Int64

instance Names "Text by text" map.Map String String

instance Entries "Records holding text, by number" map.Map Int64 Entry

instance NumberSet "A set of whole numbers" set.Set Int64

instance NameSet "A set of text" set.Set String

op say "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op buffers "Buffers: text, numbers, and bytes appended, read back as text and bytes, and bytes that are not UTF-8"
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
:begin
  make: bytesOut = buffer.new(scratch)
  addText: buffer.appendString(bytesOut, greeting="héllo, ")
  addLeast: buffer.appendInt64(bytesOut, least=-9223372036854775808)
  addSpace: buffer.appendByte(bytesOut, space=32)
  addMost: buffer.appendInt64(bytesOut, most=9223372036854775807)
  measure: length = buffer.length(bytesOut)
  showLength: sayNumber(length)
  asText: text = buffer.toString(bytesOut, scratch) ? notText
  showText: say(text)
  asBytes: raw = buffer.toBytes(bytesOut)
  rawLength: rawCount = bytes.length(raw)
  showRawLength: sayNumber(rawCount)
  backToText: again = string.fromBytes(raw, scratch) ? notText
  showAgain: say(again)
  addBad: buffer.appendByte(bytesOut, bad=255)
  addAfter: buffer.appendString(bytesOut, after="!")
  badText: broken = buffer.toString(bytesOut, scratch) ? reportBad
  showBroken: say(broken)
  return
:reportBad
  match badTextError
  case invalidAt offset showOffset
:showOffset
  writeOffset: sayNumber(offset)
  return
:notText
  sayNot: say(notTextLine="not text")
  return

op numbers "A numberMap of numbers: thousands of keys, removals, keys put again, and the keys read back in order"
  effect write console.stdout
  uses stdoutWriter
  region scratch 1048576
  let at Int64 0 mut
  let total Int64 0 mut
  let count Int64 6000
  let shown Int64 0 mut
  let zero Int64 0
:begin
  make: numberMap = Numbers.new(scratch)
  goto eachPut
:eachPut loop=while max=count
  putsDone: donePuts = compare.greaterOrEqualInt64(at, count)
  if donePuts removals putOne
:putOne in=eachPut
  scramble: spread = math.multiplyInt64(at, step=7919)
  wrap: key = math.remainderInt64(spread, prime=10007)
  doubleIt: doubled = math.multiplyInt64(at, two=2)
  put: Numbers.put(numberMap, key, doubled)
  advance: next = math.addInt64(at, one=1)
  set at next
  goto eachPut
:removals
  set at zero
  goto eachRemove
:eachRemove loop=while max=count
  removesDone: doneRemoves = compare.greaterOrEqualInt64(at, count)
  if doneRemoves afterRemovals removeOne
:removeOne in=eachRemove
  scrambleAgain: spreadAgain = math.multiplyInt64(at, step)
  wrapAgain: removedKey = math.remainderInt64(spreadAgain, prime)
  drop: Numbers.remove(numberMap, removedKey) ? missing
  goto nextRemove
:missing in=eachRemove
  sayMissing: say(missingLine="missing")
  goto nextRemove
:nextRemove in=eachRemove
  advanceRemove: nextRemoveAt = math.addInt64(at, three=3)
  set at nextRemoveAt
  goto eachRemove
:afterRemovals
  measure: length = Numbers.length(numberMap)
  showLength: sayNumber(length)
  putBack: Numbers.put(numberMap, zero, minusOne=-1)
  removeAgain: Numbers.remove(numberMap, zero) ? gone
  goto readSome
:gone
  sayGone: say(goneLine="gone twice")
  goto readSome
:readSome
  readKnown: known = Numbers.get(numberMap, prime) ? unknown
  showKnown: sayNumber(known)
  goto checks
:unknown
  sayUnknown: say(unknownLine="unknown")
  goto checks
:checks
  hasCheck: has = Numbers.contains(numberMap, seven=7)
  if has sayHas sayHasNot
:sayHas
  writeHas: say(hasLine="has 7")
  goto order
:sayHasNot
  writeHasNot: say(hasNotLine="has not 7")
  goto order
:order
  putLast: Numbers.put(numberMap, step, one)
  set shown zero
  measureAll: all = Numbers.length(numberMap)
  goto eachKey
:eachKey loop=forEach max=all over=numberMap
  next numberMap seen showKey summed
:showKey in=eachKey
  readValue: value = Numbers.get(numberMap, seen) ? lost
  addKey: withKey = math.addInt64(total, seen)
  addValue: withValue = math.addInt64(withKey, value)
  set total withValue
  fewCheck: few = compare.lessThanInt64(shown, eight=8)
  if few printKey countShown
:printKey in=eachKey
  writeKey: sayNumber(seen)
  goto countShown
:countShown in=eachKey
  moreShown: shownMore = math.addInt64(shown, one)
  set shown shownMore
  goto eachKey
:summed
  showTotal: sayNumber(total)
  return
:lost
  sayLost: say(lostLine="lost")
  return

op names "A nameMap of text by text: keys found by their bytes, values copied into the nameMap's region"
  effect write console.stdout
  uses stdoutWriter
  region scratch 4096
  region keys 4096
:begin
  make: nameMap = Names.new(scratch)
  before: start = arena.remaining(scratch)
  firstKey: alpha = string.fromInt64(oneHundred=100, keys)
  putFirst: Names.put(nameMap, alpha, first="first")
  putSecond: Names.put(nameMap, second="200", other="second")
  putAgain: Names.put(nameMap, alpha, again="again")
  after: left = arena.remaining(scratch)
  used: spent = math.subtractInt64(start, left)
  showSpent: sayNumber(spent)
  readFirst: found = Names.get(nameMap, sameText="100") ? missing
  showFound: say(found)
  measure: length = Names.length(nameMap)
  showLength: sayNumber(length)
  goto eachName
:eachName loop=forEach max=length over=nameMap
  next nameMap name showName done
:showName in=eachName
  writeName: say(name)
  goto eachName
:done
  return
:missing
  sayMissing: say(missingLine="missing")
  return

op entries "A entryMap whose values are records holding text, which is copied into the entryMap's region (D-107)"
  effect write console.stdout
  uses stdoutWriter
  region scratch 4096
  region words 4096
:begin
  make: entryMap = Entries.new(scratch)
  word: name = string.fromInt64(fortyTwo=42, words)
  build: entry = Entry.new(name, size=7, words)
  put: Entries.put(entryMap, one=1, entry)
  read: found = Entries.get(entryMap, one) ? missing
  readName: foundName = Entry.name(found)
  showName: say(foundName)
  readSize: foundSize = Entry.size(found)
  showSize: sayNumber(foundSize)
  return
:missing
  sayMissing: say(missingLine="missing")
  return

op sets "Sets of numbers and of text: each item once, in the order first added"
  effect write console.stdout
  uses stdoutWriter
  region scratch 4096
:begin
  make: numberSet = NumberSet.new(scratch)
  addFive: NumberSet.add(numberSet, five=5)
  addTwo: NumberSet.add(numberSet, two=2)
  addFiveAgain: NumberSet.add(numberSet, five)
  removeTwo: NumberSet.remove(numberSet, two)
  removeNone: NumberSet.remove(numberSet, nine=9)
  addNine: NumberSet.add(numberSet, nine)
  count: length = NumberSet.length(numberSet)
  showLength: sayNumber(length)
  hasCheck: hasFive = NumberSet.contains(numberSet, five)
  if hasFive sayFive texts
:sayFive
  writeFive: say(fiveLine="has 5")
  goto texts
:texts
  makeNames: nameSet = NameSet.new(scratch)
  addB: NameSet.add(nameSet, bee="b")
  addA: NameSet.add(nameSet, ay="a")
  addBAgain: NameSet.add(nameSet, beeAgain="b")
  countNames: nameCount = NameSet.length(nameSet)
  showNames: sayNumber(nameCount)
  goto eachName
:eachName loop=forEach max=nameCount over=nameSet
  next nameSet name showName done
:showName in=eachName
  writeName: say(name)
  goto eachName
:done
  return

op logs "Every log level, to standard error"
  effect write console.stderr
  uses stderrWriter
:begin
  debugLine: log.debug(debugText="a debug line") ~
  infoLine: log.info(infoText="an info line") ~
  warnLine: log.warn(warnText="a warning") ~
  errorLine: log.error(errorText="an error") ~
  return

op main "Run every part in turn, twice, so regions and their host objects are released and made again"
  output ExitCode
  effect write console.stdout
  effect write console.stderr
  uses stdoutWriter
  uses stderrWriter
  let round Int64 0 mut
  let code ExitCode 0
  let two Int64 2
:begin
  goto eachRound
:eachRound loop=while max=two
  roundsDone: done = compare.greaterOrEqualInt64(round, two)
  if done finish runRound
:runRound in=eachRound
  runBuffers: buffers()
  runNumbers: numbers()
  runNames: names()
  runEntries: entries()
  runSets: sets()
  runLogs: logs()
  advance: next = math.addInt64(round, one=1)
  set round next
  goto eachRound
:finish
  return code
'''


def write_project(folder: str) -> None:
    """The project: build.sem and hosttour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    prog = Program()
    m = Module("hosttour")
    prog.modules["hosttour"] = m
    g = Generator(prog, m)
    g.declare(DSL)
    g.parse(DSL)
    sem, _tests = g.render(["# Every host target the runtime in SemanticScript implements (tests/hosttour.py)."], None)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "hosttour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Use every host target of the runtime in SemanticScript"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", "tourProject allows write console.stdout none",
            "tourProject allows write console.stderr none", "tourProject requires none",
            "tourProject includesModule hosttour", "tourProject entry hosttour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
