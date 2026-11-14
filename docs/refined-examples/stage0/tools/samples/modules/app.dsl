## A stage0 sample of two modules: `app` uses the record, enum, and
## operations of `shapes`, which build.sem includes before it, by their
## qualified names (`shapes.Rectangle.new`, `shapes.area`, `shapes.Kind`),
## widens a square with `shapes.Rectangle.with`, and declares a record `Label`
## and a constant `sides` of its own whose names shapes also uses. It exits
## with code 0:
##
##   area: 12
##   oblong
##   area: 25
##   square
##   area: 35
##   oblong
##   app label: app (width 3)
##   shapes label: shapes
##   app sides: 3
##   shapes sides: 4
module app "Measure rectangles with the shapes module, and keep names of its own"
  path app
  imports standard.console standard.string shapes
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record Label "A name the app gives something, with a width of its own"
  field text String
  field width Int64

constant sides "How many sides the app's own shape, a triangle, has" Int64 3

op report "Print a label and a number on one line; a failed write is discarded"
  input label String borrowed
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  writeLabel: console.write(label) ~
  writeValue: console.writeIntegerLine(value) ~
  return

op measure "Print a rectangle's area and kind"
  input shape shapes.Rectangle copied
  effect write console.stdout
  uses stdoutWriter
:begin
  readArea: shapeArea = shapes.area(shape)
  reportArea: report(areaText="area: ", shapeArea)
  readKind: kind = shapes.kindOf(shape)
  match kind
  case square square
  case oblong oblong
:square
  writeSquare: console.writeLine(squareText="square") ~
  return
:oblong
  writeOblong: console.writeLine(oblongText="oblong") ~
  return

op main "Measure two rectangles and print labels and constants of both modules"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region store 65536
  let seven Int64 7
  let okCode ExitCode 0
:begin
  makeOblong: oblong = shapes.Rectangle.new(three=3, four=4)
  measureOblong: measure(oblong)
  makeSquare: square = shapes.Rectangle.new(five=5, five)
  measureSquare: measure(square)
  widenSquare: wide = shapes.Rectangle.with(square, width:seven)
  measureWide: measure(wide)
  makeAppLabel: appLabel = Label.new(appName="app", three, store)
  readAppText: appText = Label.text(appLabel)
  readAppWidth: appWidth = Label.width(appLabel)
  writeAppLead: console.write(appLead="app label: ") ~
  writeAppText: console.write(appText) ~
  writeAppOpen: console.write(widthOpen=" (width ") ~
  widthText: widthDigits = string.fromInt64(appWidth, store)
  writeAppWidth: console.write(widthDigits) ~
  writeAppClose: console.writeLine(close=")") ~
  makeShapesLabel: shapesLabel = shapes.Label.new(shapesName="shapes", store)
  readShapesText: shapesText = shapes.Label.text(shapesLabel)
  writeShapesLead: console.write(shapesLead="shapes label: ") ~
  writeShapesText: console.writeLine(shapesText) ~
  reportAppSides: report(appSidesText="app sides: ", sides)
  readShapesSides: shapesSides = shapes.sideCount()
  reportShapesSides: report(shapesSidesText="shapes sides: ", shapesSides)
  return okCode
