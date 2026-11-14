## A stage0 sample: lists in a region. It fills a list of numbers, a list of
## texts, and a list of records, reads them with `forEach`, `get` (whose
## failure it branches on), `getOrTrap`, and `length`, builds a list in an
## operation that receives the region to build it in, and exits with code 0:
##
##   sum: 14
##   count: 5
##   third: 4
##   no item at 9
##   alpha
##   beta
##   gamma
##   points: 3
##   x total: 6
##   evens: 4
module lists "Fill and read lists of numbers, texts, and records in a region"
  path lists
  imports standard.console standard.math standard.compare standard.list
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record Point "A point on a grid"
  field x Int64
  field y Int64

instance Numbers "A list of numbers" list.List Int64

instance Names "A list of texts" list.List String

instance Points "A list of points" list.List Point

op evens "The even numbers from 0 up to a limit, as a list in the caller's region"
  input limit Int64 copied
  input region Region borrowed
  output Numbers
  owner region
  let number Int64 0 mut
:begin
  makeList: found = Numbers.new(region)
  goto count
:count loop=while max=limit
  pastCheck: past = compare.greaterThanInt64(number, limit)
  if past done keep
:keep in=count
  keepIt: Numbers.append(found, number)
  advance: nextNumber = math.addInt64(number, 2)
  set number nextNumber
  goto count
:done
  return found

op report "Print a label and a number on one line; a failed write is discarded"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op main "Fill three lists and read them back"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 1048576
  let sum Int64 0 mut
  let xTotal Int64 0 mut
  let okCode ExitCode 0
:begin
  makeNumbers: numbers = Numbers.new(scratch)
  addThree: Numbers.append(numbers, three=3)
  addOne: Numbers.append(numbers, one=1)
  addFour: Numbers.append(numbers, four=4)
  addOneAgain: Numbers.append(numbers, one)
  addFive: Numbers.append(numbers, five=5)
  countNumbers: numberCount = Numbers.length(numbers)
  goto sumNumbers
:sumNumbers loop=forEach max=numberCount over=numbers
  next numbers number addNumber summed
:addNumber in=sumNumbers
  addIt: nextSum = math.addInt64(sum, number)
  set sum nextSum
  goto sumNumbers
:summed
  reportSum: report(sumText="sum: ", sum)
  reportCount: report(countText="count: ", numberCount)
  readThird: third = Numbers.getOrTrap(numbers, two=2)
  reportThird: report(thirdText="third: ", third)
  readMissing: missing = Numbers.get(numbers, nine=9) ? noItem
  reportMissing: report(missingText="item at 9: ", missing)
  goto fillNames
:noItem
  writeNoItem: console.writeLine(noItemText="no item at 9") ~
  goto fillNames
:fillNames
  makeNames: names = Names.new(scratch)
  addAlpha: Names.append(names, alpha="alpha")
  addBeta: Names.append(names, beta="beta")
  addGamma: Names.append(names, gamma="gamma")
  countNames: nameCount = Names.length(names)
  goto printNames
:printNames loop=forEach max=nameCount over=names
  next names name printName fillPoints
:printName in=printNames
  writeName: console.writeLine(name) ~
  goto printNames
:fillPoints
  makePoints: points = Points.new(scratch)
  makeFirst: first = Point.new(one, two)
  addFirst: Points.append(points, first)
  makeSecond: second = Point.new(two, three)
  addSecond: Points.append(points, second)
  makeThird: thirdPoint = Point.new(three, four)
  addThird: Points.append(points, thirdPoint)
  countPoints: pointCount = Points.length(points)
  reportPoints: report(pointsText="points: ", pointCount)
  goto sumX
:sumX loop=forEach max=pointCount over=points
  next points point addX summedX
:addX in=sumX
  readX: x = Point.x(point)
  addXValue: nextX = math.addInt64(xTotal, x)
  set xTotal nextX
  goto sumX
:summedX
  reportX: report(xText="x total: ", xTotal)
  makeEvens: evenNumbers = evens(six=6, scratch)
  countEvens: evenCount = Numbers.length(evenNumbers)
  reportEvens: report(evensText="evens: ", evenCount)
  return okCode
