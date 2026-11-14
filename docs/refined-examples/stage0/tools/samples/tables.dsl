## A stage0 sample: tables as fixed arrays. A table of planets (text, a
## number, and an enum cell) is read with `forEach`, with `rowAt` (whose
## failure past the last row it branches on), and with `length`. It exits
## with code 0:
##
##   Mercury 0
##   Venus 0
##   Earth 1
##   Mars 2
##   moons: 3
##   rows: 4
##   rocky: Venus
##   no row 5
module tables "Read a table of planets by forEach, rowAt, and length"
  path tables
  imports standard.console standard.math standard.list
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

enum Kind "What a planet is made of"
  variant rocky
  variant gas

record Planet "A planet's name, how many moons it has, and what it is made of"
  field name String
  field moons Int64
  field kind Kind

table planets "The inner planets, nearest the sun first" Planet
  row mercury name="Mercury" moons=0 kind=Kind.rocky
  row venus name="Venus" moons=0 kind=Kind.rocky
  row earth name="Earth" moons=1 kind=Kind.rocky
  row mars name="Mars" moons=2 kind=Kind.rocky

op main "Print each planet and its moons, the total, the row count, one row by number, and a row past the end"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  let total Int64 0 mut
  let okCode ExitCode 0
:begin
  countRows: rowCount = planets.length()
  goto eachPlanet
:eachPlanet loop=forEach max=rowCount over=planets
  next planets planet printPlanet summed
:printPlanet in=eachPlanet
  readName: name = Planet.name(planet)
  readMoons: moons = Planet.moons(planet)
  writeName: console.write(name) ~
  writeSpace: console.write(space=" ") ~
  writeMoons: console.writeIntegerLine(moons) ~
  addMoons: nextTotal = math.addInt64(total, moons)
  set total nextTotal
  goto eachPlanet
:summed
  writeTotalLead: console.write(totalText="moons: ") ~
  writeTotal: console.writeIntegerLine(total) ~
  writeRowsLead: console.write(rowsText="rows: ") ~
  writeRows: console.writeIntegerLine(rowCount) ~
  readSecond: second = planets.rowAt(two=2) ? missing
  readSecondName: secondName = Planet.name(second)
  readSecondKind: secondKind = Planet.kind(second)
  match secondKind
  case rocky rocky
  case gas gas
:rocky
  writeRocky: console.write(rockyText="rocky: ") ~
  writeSecond: console.writeLine(secondName) ~
  goto past
:gas
  writeGas: console.writeLine(gasText="gas") ~
  goto past
:past
  readPast: pastRow = planets.rowAt(five=5) ? noRow
  readPastName: pastName = Planet.name(pastRow)
  writePast: console.writeLine(pastName) ~
  return okCode
:noRow
  writeNoRow: console.writeLine(noRowText="no row 5") ~
  return okCode
:missing
  return okCode
