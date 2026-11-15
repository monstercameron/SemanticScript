"""A program that exercises every json target on the texts it reads, one per line of standard input (D-151).

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and requires what it prints, for thousands
of texts (valid documents of every kind, numbers at the edges of Int64 and Float64, escapes and surrogates, text that
is not UTF-8, and texts broken at every place), to be exactly what `refined run` prints: each text's parse error and
position, or its stringified form, its kind, and what each access gives (with the error each wrong access gives);
then a document built with every setter, shared values changed through `field`, `item`, and `setValue`, included.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

DSL = r'''module jsontour "Parse each line of standard input as JSON and print what every json target gives for it"
  path jsontour
  imports standard.console standard.json standard.time
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability stdinReader "Authority to read the texts from standard input" read console.stdin none

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

op sayAccess "Write the name of an access error, and its position when it has one"
  input problem json.AccessError copied
  effect write console.stdout
  uses stdoutWriter
:begin
  match problem
  case wrongKind showWrongKind
  case missing showMissing
  case outOfRange index showOutOfRange
  case notWhole showNotWhole
:showWrongKind
  sayWrongKind: say(wrongKindText="wrongKind")
  return
:showMissing
  sayMissing: say(missingText="missing")
  return
:showOutOfRange
  sayOutOfRange: say(outOfRangeText="outOfRange")
  sayIndex: sayNumber(index)
  return
:showNotWhole
  sayNotWhole: say(notWholeText="notWhole")
  return

op sayValue "Write a value as stringify writes it"
  input value json.Value borrowed
  effect write console.stdout
  uses stdoutWriter
  region scratch 4194304
:begin
  writeIt: text = json.stringify(value, scratch)
  showIt: say(text)
  return

op probes "Every reading target on a value, and each wrong one's error"
  input value json.Value borrowed
  effect write console.stdout
  uses stdoutWriter
  region scratch 4194304
:begin
  asNumber: number = json.asInt64(value) ? numberFailed
  showNumber: sayNumber(number)
  goto flag
:numberFailed
  showNumberError: sayAccess(asNumberError)
  goto flag
:flag
  asFlag: truth = json.asBool(value) ? flagFailed
  if truth sayTrue sayFalse
:sayTrue
  showTrue: say(trueText="true")
  goto text
:sayFalse
  showFalse: say(falseText="false")
  goto text
:flagFailed
  showFlagError: sayAccess(asFlagError)
  goto text
:text
  asText: words = json.asText(value, scratch) ? textFailed
  showText: say(words)
  goto length
:textFailed
  showTextError: sayAccess(asTextError)
  goto length
:length
  measure: count = json.length(value) ? lengthFailed
  showLength: sayNumber(count)
  goto items
:lengthFailed
  showLengthError: sayAccess(measureError)
  goto items
:items
  firstItem: first = json.item(value, zero=0, scratch) ? firstFailed
  showFirst: sayValue(first)
  goto lastItem
:firstFailed
  showFirstError: sayAccess(firstItemError)
  goto lastItem
:lastItem
  pastItem: past = json.item(value, minusOne=-1, scratch) ? pastFailed
  showPast: sayValue(past)
  goto fieldA
:pastFailed
  showPastError: sayAccess(pastItemError)
  goto fieldA
:fieldA
  readA: a = json.field(value, aName="a", scratch) ? aFailed
  showA: sayValue(a)
  goto done
:aFailed
  showAError: sayAccess(readAError)
  goto done
:done
  return

op kindName "Write a value's kind"
  input value json.Value borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  readKind: kind = json.kind(value)
  match kind
  case null showNull
  case boolean showBoolean
  case number showNumber
  case text showText
  case array showArray
  case object showObject
:showNull
  sayNull: say(nullText="null")
  return
:showBoolean
  sayBoolean: say(booleanText="boolean")
  return
:showNumber
  sayNumber2: say(numberText="number")
  return
:showText
  sayText: say(textText="text")
  return
:showArray
  sayArray: say(arrayText="array")
  return
:showObject
  sayObject: say(objectText="object")
  return

op oneLine "Read a line and show what the json targets give for it; false at the end of input"
  output Bool
  effect write console.stdout
  effect read console.stdin
  uses stdoutWriter
  uses stdinReader
  async
  region scratch 16777216
  let more Bool true
  let finished Bool false
:begin
  makeNever: never = time.Deadline.never()
  task readIt: line = console.readLine(scratch, limit=8388608, never) ? noMore
  parseIt: value = json.parse(line, scratch) ? parseFailed
  showValue: sayValue(value)
  showKind: kindName(value)
  showProbes: probes(value)
  return more
:parseFailed
  match parseItError
  case invalidAt position showInvalid
  case tooDeep showDeep
:showInvalid
  sayInvalid: say(invalidText="invalidAt")
  sayPosition: sayNumber(position)
  return more
:showDeep
  sayDeep: say(deepText="tooDeep")
  return more
:noMore
  return finished

op built "A document built with every setter, its shared values changed through field, item, and setValue"
  effect write console.stdout
  uses stdoutWriter
  region scratch 1048576
:begin
  makeRoot: root = json.newObject(scratch)
  setNumber: json.setInt64(root, nName="n", least=-9223372036854775808) ~
  setWords: json.setText(root, tName="t", tValue="quote \" back \\ tab \t nl \n bell \x07 \xc3\xa9 \xff end") ~
  setFlag: json.setBool(root, bName="b", yes=true) ~
  makeList: list = json.newArray(scratch)
  addNumber: json.appendInt64(list, most=9223372036854775807) ~
  addWords: json.appendText(list, word="w") ~
  setList: json.setValue(root, lName="l", list) ~
  addLater: json.appendInt64(list, later=7) ~
  setAgain: json.setInt64(root, nName, two=2) ~
  showRoot: sayValue(root)
  readList: shared = json.field(root, lName, scratch) ? noList
  addShared: json.appendText(shared, sharedWord="shared") ~
  showShared: sayValue(root)
  readFirst: first = json.item(shared, zero=0, scratch) ? noList
  showFirst: sayValue(first)
  makeInner: inner = json.newObject(scratch)
  addInner: json.appendText(list, innerWord="x") ~
  nest: json.setValue(list, iName="i", inner) ? wrongList
  goto onObject
:wrongList
  showWrongList: sayAccess(nestError)
  goto onObject
:onObject
  appendObject: json.appendInt64(root, one=1) ? wrongObject
  goto nested
:wrongObject
  showWrongObject: sayAccess(appendObjectError)
  goto nested
:nested
  setInner: json.setValue(root, iName, inner) ~
  setDeep: json.setInt64(inner, dName="d", one) ~
  showNested: sayValue(root)
  readNumber: number = json.asInt64(root) ? notNumber
  showNumber: sayNumber(number)
  return
:notNumber
  showNotNumber: sayAccess(readNumberError)
  return
:noList
  sayNoList: say(noListText="no list")
  return

op main "Show every line of standard input as JSON, then a built document"
  output ExitCode
  effect write console.stdout
  effect read console.stdin
  uses stdoutWriter
  uses stdinReader
  async
  let code ExitCode 0
  let forever Int64 1000000
:begin
  goto eachLine
:eachLine loop=while max=forever
  task readOne: more = oneLine()
  if more eachLine finish
:finish
  showBuilt: built()
  return code
'''


def write_project(folder: str) -> None:
    """The project: build.sem and jsontour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    prog = Program()
    m = Module("jsontour")
    prog.modules["jsontour"] = m
    g = Generator(prog, m)
    g.declare(DSL)
    g.parse(DSL)
    sem, _tests = g.render(["# Every json target on the lines of standard input (tests/jsontour.py)."], None)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "jsontour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Use every json target of the runtime in SemanticScript"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", "tourProject allows write console.stdout none",
            "tourProject allows read console.stdin none", "tourProject requires none",
            "tourProject includesModule jsontour", "tourProject entry jsontour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
