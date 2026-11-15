"""A program that exercises every net target on loopback and prints what each gives (D-148).

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and requires what it prints and its exit
code to be exactly what `refined run` gives: a listener, a connection made to it and accepted, bytes both ways, a
read that times out, the end of a stream when the other side closes, an accept that times out, a port that is in use,
a port with nothing listening (refused), names resolved (`localhost`) and one that does not exist, a port that is not
a number.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests", "suite"))

PORT, CLOSED = 47861, 47862

DSL = r'''module nettour "Use every net target on loopback and print what each gives"
  path nettour
  imports standard.console standard.string standard.convert standard.net standard.time
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability listenAuthority "Authority to listen on the tour's loopback port" listen net.tcp "127.0.0.1:PORT"

capability connectLoopback "Authority to connect to any loopback port" connect net.outbound "127.0.0.1:"

capability connectNamed "Authority to connect to localhost and to a name that does not exist" connect net.outbound "localhost:"

capability connectMissing "Authority to connect to a name that does not exist" connect net.outbound "nonexistent.invalid:"

capability connectionIo "Authority to use the tour's connections" readWrite net.connection none

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

op sayError "Write the name of a net error, and its number when it has one"
  input problem net.NetError copied
  effect write console.stdout
  uses stdoutWriter
:begin
  match problem
  case closed showClosed
  case timedOut showTimedOut
  case refused showRefused
  case cancelled showCancelled
  case failed code showFailed
:showClosed
  sayClosed: say(closedText="closed")
  return
:showTimedOut
  sayTimedOut: say(timedOutText="timedOut")
  return
:showRefused
  sayRefused: say(refusedText="refused")
  return
:showCancelled
  sayCancelled: say(cancelledText="cancelled")
  return
:showFailed
  sayFailed: say(failedText="failed")
  widen: wide = convert.int32ToInt64(code)
  sayCode: sayNumber(wide)
  return

op tryConnect "Connect to an address and say what happened, closing the connection when there is one"
  input address String borrowed
  effect write console.stdout
  effect connect net.outbound
  effect readWrite net.connection
  uses stdoutWriter
  uses connectLoopback
  uses connectNamed
  uses connectMissing
  uses connectionIo
  async
:begin
  makeDeadline: deadline = time.Deadline.after(fiveSeconds=5000)
  task connectIt: connection = net.connect(address, deadline) ? failed
  sayConnected: say(connectedText="connected")
  closeIt: net.close(connection) ~
  return
:failed
  showError: sayError(connectItError)
  return

op exchange "Bytes both ways over a connection to the tour's own listener, a read that times out, and the end of a stream"
  input listener net.TcpListener borrowedMutable
  effect write console.stdout
  effect listen net.tcp
  effect connect net.outbound
  effect readWrite net.connection
  uses stdoutWriter
  uses listenAuthority
  uses connectLoopback
  uses connectionIo
  async
  region scratch 65536
:begin
  makeDeadline: deadline = time.Deadline.after(fiveSeconds=5000)
  task connectIt: client = net.connect(address="127.0.0.1:PORT", deadline) ? failed
  task acceptIt: server = net.accept(listener, deadline) ? failedAccept
  toBytes: ping = string.toBytes(pingText="ping")
  task sendIt: net.write(client, ping, deadline) ~
  task receiveIt: got = net.read(server, scratch, sixtyFour=64, deadline) ? failedRead
  asText: gotText = string.fromBytes(got, scratch) ? notText
  showGot: say(gotText)
  toPong: pong = string.toBytes(pongText="pong from the server")
  task replyIt: net.write(server, pong, deadline) ~
  task answerIt: answer = net.read(client, scratch, five=5, deadline) ? failedRead
  asAnswer: answerText = string.fromBytes(answer, scratch) ? notText
  showAnswer: say(answerText)
  task restIt: rest = net.read(client, scratch, sixtyFour, deadline) ? failedRead
  asRest: restText = string.fromBytes(rest, scratch) ? notText
  showRest: say(restText)
  makeShort: short = time.Deadline.after(twoHundred=200)
  task quietIt: quiet = net.read(server, scratch, sixtyFour, short) ? quietFailed
  showQuiet: say(quietText="read something")
  goto closeClient
:quietFailed
  showQuietError: sayError(quietItError)
  goto closeClient
:closeClient
  closeIt: net.close(client) ~
  task endIt: ended = net.read(server, scratch, sixtyFour, deadline) ? endFailed
  showEnded: say(endedText="read after the close")
  goto closeServer
:endFailed
  showEndError: sayError(endItError)
  goto closeServer
:closeServer
  closeServerIt: net.close(server) ~
  return
:failed
  showConnectError: sayError(connectItError)
  return
:failedAccept
  showAcceptError: sayError(acceptItError)
  closeLost: net.close(client) ~
  return
:failedRead
  sayReadFailed: say(readFailedText="a read failed")
  goto closeClient
:notText
  sayNotText: say(notTextText="not text")
  goto closeClient

op main "Listen, exchange bytes, time out, be refused, resolve names, and use a closed listener"
  output ExitCode
  effect write console.stdout
  effect listen net.tcp
  effect connect net.outbound
  effect readWrite net.connection
  uses stdoutWriter
  uses listenAuthority
  uses connectLoopback
  uses connectNamed
  uses connectMissing
  uses connectionIo
  async
  let code ExitCode 0
:begin
  listenIt: listener = net.listen(port=PORT) ? listenFailed
  sayListening: say(listeningText="listening")
  task exchangeIt: exchange(listener)
  listenAgain: second = net.listen(port) ? secondFailed
  saySecond: say(secondText="listened twice")
  closeSecond: net.closeListener(second) ~
  goto lonely
:secondFailed
  showSecondError: sayError(listenAgainError)
  goto lonely
:lonely
  makeShort: short = time.Deadline.after(hundred=100)
  task acceptIt: lone = net.accept(listener, short) ? acceptFailed
  sayAccepted: say(acceptedText="accepted")
  closeLone: net.close(lone) ~
  goto named
:acceptFailed
  showAcceptError: sayError(acceptItError)
  goto named
:named
  task namedIt: tryConnect(namedAddress="localhost:PORT")
  closeIt: net.closeListener(listener) ~
  task refusedIt: tryConnect(refusedAddress="127.0.0.1:CLOSED")
  task badPortIt: tryConnect(badPortAddress="127.0.0.1:x9")
  task missingIt: tryConnect(missingAddress="nonexistent.invalid:80")
  return code
:listenFailed
  showListenError: sayError(listenItError)
  return code
'''.replace("CLOSED", str(CLOSED)).replace("PORT", str(PORT))


def write_project(folder: str) -> None:
    """The project: build.sem and nettour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    prog = Program()
    m = Module("nettour")
    prog.modules["nettour"] = m
    g = Generator(prog, m)
    g.declare(DSL)
    g.parse(DSL)
    sem, _tests = g.render(["# Every net target on loopback (tests/nettour.py)."], None)
    # the generator writes `ownedBy none` for a result its caller owns (a listener or connection): it is the
    # operation's own
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and \
                target in ("net.listen", "net.accept", "net.connect"):
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "nettour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Use every net target of the runtime in SemanticScript"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule nettour", "tourProject entry nettour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
