## The first module of the stage0 sample `modules`: rectangles, what kind of
## rectangle one is, and a constant and a record whose names the module after
## it also uses for things of its own.
module shapes "Rectangles, their areas and kinds, for the app module to use"
  path shapes
  imports standard.math standard.compare standard.test
  exports Kind Rectangle Label area kindOf sideCount

enum Kind "Whether a rectangle's sides are all the same length"
  variant square
  variant oblong

record Rectangle "A rectangle's width and height"
  field width Int64
  field height Int64

record Label "A name shapes gives a rectangle"
  field text String

constant sides "How many sides a rectangle has" Int64 4

op area "A rectangle's area"
  invariant multipliesSides "The area is the width times the height"
  input shape Rectangle copied
  output Int64
:begin
  readWidth: width = Rectangle.width(shape)
  readHeight: height = Rectangle.height(shape)
  multiply: product = math.multiplyInt64(width, height)
  return product

op kindOf "Whether a rectangle is a square or an oblong"
  invariant comparesSides "A rectangle whose width is its height is a square; any other is an oblong"
  input shape Rectangle copied
  output Kind
:begin
  readWidth: width = Rectangle.width(shape)
  readHeight: height = Rectangle.height(shape)
  sameCheck: same = compare.equalInt64(width, height)
  if same square oblong
:square
  makeSquare: squareKind = Kind.square()
  return squareKind
:oblong
  makeOblong: oblongKind = Kind.oblong()
  return oblongKind

op sideCount "How many sides a rectangle has: this module's constant `sides`"
  invariant countsSides "Gives the module's own constant: a rectangle has 4 sides"
  output Int64
:begin
  return sides

@tests

test shapesTest "A 3 by 4 rectangle has area 12 and is an oblong; a 2 by 2 one is a square; a rectangle has 4 sides"
  verifies area multipliesSides
  verifies kindOf comparesSides
  verifies sideCount countsSides
  let yes Bool true
:begin
  makeOblong: oblong = Rectangle.new(three=3, four=4)
  readArea: oblongArea = area(oblong)
  expectArea: test.assertEqualInt64(twelve=12, oblongArea)
  readOblongKind: oblongKind = kindOf(oblong)
  match oblongKind
  case square wrong
  case oblong checkSquare
:checkSquare
  makeSquare: square = Rectangle.new(two=2, two)
  readSquareKind: squareKind = kindOf(square)
  match squareKind
  case square checkSides
  case oblong wrong
:checkSides
  readSides: sideTotal = sideCount()
  expectSides: test.assertEqualInt64(four, sideTotal)
  return
:wrong
  failKind: test.fail(wrongText="a rectangle was given the wrong kind")
  return
