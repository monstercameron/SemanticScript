"""A program that exercises every http target on requests of every shape and prints what each gives (D-152).

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and requires what it prints to be exactly
what `refined run` prints: each request's method and path, or malformed; its headers looked up in other cases (and by
names that are not ASCII); and responses of named and unnamed statuses written out; with the region's remaining
bytes after each parse, so the copies a parse makes (and makes before it finds a later line malformed) agree too.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

REQUESTS = [
    r"GET / HTTP/1.1\x0d\x0aHost: example.com\x0d\x0a\x0d\x0a",
    r"post /items?x=1 HTTP/1.0\x0d\x0aContent-Type:  text/plain \x0d\x0aX-Count:\t3\x0d\x0ax-count: 4\x0d\x0a\x0d\x0abody",
    r"PATCH /a HTTP/2\x0aKey: v\x0a\x0arest",
    r"DELETE /x HTTP/1.1",
    r"OPTIONS /o HTTP/1.1\x0d\x0aWeird\xff\xfe: yes\x0d\x0aKind: k1\x0d\x0a\x0d\x0a",
    r"HEAD /h HTTP/1.1\x0d\x0aA: 1\x0d\x0aNoColon\x0d\x0a\x0d\x0a",
    r"GET  / HTTP/1.1\x0d\x0a\x0d\x0a",
    r"GET / HTTP/1.1 extra\x0d\x0a\x0d\x0a",
    r"FETCH / HTTP/1.1\x0d\x0a\x0d\x0a",
    r"GET relative HTTP/1.1\x0d\x0a\x0d\x0a",
    r"GET / FTP/1.1\x0d\x0a\x0d\x0a",
    r"",
    r"\x0d\x0a\x0d\x0a",
    r"GET / HTTP/1.1\x0d\x0aHost: a\x0d\x0d\x0aTrail: x \x0d\x0a\x0d\x0a",
    r"GeT /\xc3\xa9 HTTP/1.1\x0d\x0a  Spaced  :  value with spaces  \x0d\x0a\x0d\x0a",
    r"PUT /p HTTP/1.1\x0d\x0aHost: h\x0d\x0a\x0d\x0aGET /second HTTP/1.1\x0d\x0a\x0d\x0a",
]
NAMES = ["host", "HOST", "x-count", "content-type", r"weird\xef\xbf\xbd\xef\xbf\xbd", r"\xe2\x84\xaaind", "key",
         "missing", "spaced", "trail", "a", r"\xff"]


def _dsl() -> str:
    calls = []
    for i, request in enumerate(REQUESTS):
        calls.append(f'  run{i}: oneRequest(request{i}="{request}")')
    names = []
    for i, name in enumerate(NAMES):
        names.append(f'  look{i}: lookUp(request, name{i}="{name}")')
    return DSL.replace("@REQUESTS@", "\n".join(calls)).replace("@NAMES@", "\n".join(names))


DSL = r'''module httptour "Use every http target on requests of every shape and print what each gives"
  path httptour
  imports standard.console standard.string standard.http standard.arena
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

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

op lookUp "Look a header of a request up and say its value or that it is absent"
  input request http.HttpRequest borrowed
  input name String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  find: value = http.header(request, name) ? absent
  show: say(value)
  return
:absent
  sayAbsent: say(absentText="absent")
  return

op methodName "Write a request's method"
  input method http.HttpMethod copied
  effect write console.stdout
  uses stdoutWriter
:begin
  match method
  case get showGet
  case head showHead
  case post showPost
  case put showPut
  case delete showDelete
  case options showOptions
  case patch showPatch
:showGet
  sayGet: say(getText="get")
  return
:showHead
  sayHead: say(headText="head")
  return
:showPost
  sayPost: say(postText="post")
  return
:showPut
  sayPut: say(putText="put")
  return
:showDelete
  sayDelete: say(deleteText="delete")
  return
:showOptions
  sayOptions: say(optionsText="options")
  return
:showPatch
  sayPatch: say(patchText="patch")
  return

op oneRequest "Parse a request and say what it holds, with what is left of its region"
  input raw String borrowed
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
:begin
  toBytes: data = string.toBytes(raw)
  parseIt: request = http.parseRequest(data, scratch) ? malformed
  readMethod: method = http.HttpRequest.method(request)
  showMethod: methodName(method)
  readPath: path = http.HttpRequest.path(request)
  showPath: say(path)
@NAMES@
  measure: left = arena.remaining(scratch)
  showLeft: sayNumber(left)
  return
:malformed
  sayMalformed: say(malformedText="malformed")
  measureMalformed: leftMalformed = arena.remaining(scratch)
  showLeftMalformed: sayNumber(leftMalformed)
  return

op respond "Write a response of a status and a body out"
  input status Int32 copied
  input body String borrowed
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
:begin
  makeIt: response = http.response(status, body, scratch)
  writeIt: data = http.serializeResponse(response, scratch)
  asText: text = string.fromBytes(data, scratch) ? notText
  showIt: say(text)
  return
:notText
  sayNotText: say(notTextText="not text")
  return

op main "Parse every request and write responses"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let code ExitCode 0
:begin
@REQUESTS@
  ok: respond(okStatus=200, okBody="fine")
  created: respond(createdStatus=201, createdBody="")
  missing: respond(missingStatus=404, missingBody="gone \xc3\xa9")
  teapot: respond(teapotStatus=418, teapotBody="short and stout")
  negative: respond(negativeStatus=-5, negativeBody="odd")
  return code
'''


def write_project(folder: str) -> None:
    """The project: build.sem and httptour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    prog = Program()
    m = Module("httptour")
    prog.modules["httptour"] = m
    g = Generator(prog, m)
    text = _dsl()
    g.declare(text)
    g.parse(text)
    sem, _tests = g.render(["# Every http target on requests of every shape (tests/httptour.py)."], None)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "httptour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Use every http target of the runtime in SemanticScript"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", "tourProject allows write console.stdout none", "tourProject requires none",
            "tourProject includesModule httptour", "tourProject entry httptour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
