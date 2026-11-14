## A stage0 sample: records, enums with payloads, exhaustive `match`, and an
## operation that raises its own error enum. `area` gives the area of a
## `Shape` (a square's side, a rectangle's two sides as a record, or a dot) and
## raises `AreaError.negativeSide` for a negative side; `main` prints each
## area, prints the error it catches, reads a labelled record's fields, and
## exits with code 4:
##
##   area: 9
##   area: 6
##   area: 0
##   refused a side of -2
##   corner: 3
module shapes "Compute areas of shapes held in enums and records, with an error enum of their own"
  path shapes
  imports standard.console standard.math standard.compare
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record Sides "A rectangle's two sides"
  field width Int64
  field height Int64

enum Shape "A shape whose area can be computed"
  variant square Int64
  variant rectangle Sides
  variant dot

enum AreaError "Why an area cannot be computed"
  variant negativeSide Int64
  variant tooLarge

record Label "A text with a position, so a record holds text"
  field text String
  field column Int64

op sideArea "The area of a rectangle, refusing a negative side"
  input width Int64 copied
  input height Int64 copied
  output Int64
  raises AreaError
:begin
  widthCheck: widthNegative = compare.lessThanInt64(width, 0)
  if widthNegative badWidth heightTest
:heightTest
  heightCheck: heightNegative = compare.lessThanInt64(height, 0)
  if heightNegative badHeight multiply
:multiply
  product: rectangleArea = math.multiplyInt64(width, height)
  return rectangleArea
:badWidth
  makeWidthError: widthError = AreaError.negativeSide(width)
  raise widthError
:badHeight
  makeHeightError: heightError = AreaError.negativeSide(height)
  raise heightError

op area "The area of a shape"
  input shape Shape copied
  output Int64
  raises AreaError
  let zero Int64 0
:begin
  match shape
  case square side ofSquare
  case rectangle sides ofRectangle
  case dot ofDot
:ofSquare
  squareArea: squared = sideArea(side, side) ?^
  return squared
:ofRectangle
  readWidth: width = Sides.width(sides)
  readHeight: height = Sides.height(sides)
  rectangleArea: rectangled = sideArea(width, height) ?^
  return rectangled
:ofDot
  return zero

op printArea "Print the area of a shape, or the side it refused"
  input shape Shape copied
  effect write console.stdout
  uses stdoutWriter
:begin
  compute: computed = area(shape) ! areaError
  iferr compute refused print
:print
  writeLead: console.write(areaText="area: ") ~
  writeArea: console.writeIntegerLine(computed) ~
  return
:refused
  match areaError
  case negativeSide side negative
  case tooLarge tooLarge
:negative
  writeRefused: console.write(refusedText="refused a side of ") ~
  writeSide: console.writeIntegerLine(side) ~
  return
:tooLarge
  writeTooLarge: console.writeLine(tooLargeText="too large") ~
  return

op main "Print the areas of four shapes, then a field of a record that holds text, and exit with code 4"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let doneCode ExitCode 4
:begin
  makeSquare: square = Shape.square(three=3)
  printSquare: printArea(square)
  makeSides: sides = Sides.new(two=2, three)
  makeRectangle: rectangle = Shape.rectangle(sides)
  printRectangle: printArea(rectangle)
  makeDot: dot = Shape.dot()
  printDot: printArea(dot)
  makeBad: bad = Shape.square(minusTwo=-2)
  printBad: printArea(bad)
  makeLabel: label = Label.new(cornerText="corner: ", three, scratch)
  readText: text = Label.text(label)
  readColumn: column = Label.column(label)
  writeText: console.write(text) ~
  writeColumn: console.writeIntegerLine(column) ~
  return doneCode
