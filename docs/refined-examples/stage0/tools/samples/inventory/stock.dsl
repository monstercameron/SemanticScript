## The first module of the stage0 sample `inventory`, from the audit: item
## counts kept in a map of records with String keys.
module stock "Keep item counts in a map with String keys"
  path stock
  imports standard.math standard.map standard.test
  exports Counts Item restock take

record Item "An item's count and shelf"
  field count Int64
  field shelf Int64

instance Counts "Items by name" map.Map String Item

op restock "Add to an item's count, putting it on a shelf when it is new"
  invariant adds "The item's count grows by the amount"
  input counts Counts borrowedMutable
  input name String borrowed
  input amount Int64 copied
  let have Int64 0 mut
  let shelf Int64 0 mut
:begin
  readItem: item = Counts.get(counts, name) ? fresh
  readCount: before = Item.count(item)
  set have before
  readShelf: oldShelf = Item.shelf(item)
  set shelf oldShelf
  goto add
:fresh
  countAll: size = Counts.length(counts)
  set shelf size
  goto add
:add
  addIt: after = math.addInt64(have, amount)
  makeItem: fresh2 = Item.new(after, shelf)
  putIt: Counts.put(counts, name, fresh2)
  return

op take "Take some of an item, giving what is left, or -1 when there is no such item"
  invariant takes "Gives the count less the amount, or -1 for a missing item"
  input counts Counts borrowedMutable
  input name String borrowed
  input amount Int64 copied
  output Int64
  let missing Int64 -1
:begin
  readItem: item = Counts.get(counts, name) ? absent
  readCount: before = Item.count(item)
  readShelf: shelf = Item.shelf(item)
  less: after = math.subtractInt64(before, amount)
  makeItem: changed = Item.new(after, shelf)
  putIt: Counts.put(counts, name, changed)
  return after
:absent
  return missing

@tests

test stockTest "Restocking 5 then 3 nails and taking 2 leaves 6; taking a missing item gives -1"
  verifies restock adds
  verifies take takes
  region store 65536
:begin
  makeCounts: counts = Counts.new(store)
  r1: restock(counts, nails="nails", five=5)
  r2: restock(counts, nails, three=3)
  t1: left = take(counts, nails, two=2)
  expectLeft: test.assertEqualInt64(six=6, left)
  t2: none2 = take(counts, tape="tape", two)
  expectNone: test.assertEqualInt64(minusOne=-1, none2)
  return
