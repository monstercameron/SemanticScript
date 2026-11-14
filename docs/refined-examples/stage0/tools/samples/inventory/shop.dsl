## A stage0 sample of two modules from the audit: `shop` uses the map of
## records `stock` declares, by qualified names.
module shop "Use the stock module's map by qualified names"
  path shop
  imports standard.console standard.map stock
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op main "Restock and take items, then list every item"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region store 1048576
  let okCode ExitCode 0
:begin
  makeCounts: counts = stock.Counts.new(store)
  r1: stock.restock(counts, nails="nails", forty=40)
  r2: stock.restock(counts, screws="screws", twelve=12)
  r3: stock.restock(counts, nails, five=5)
  r4: stock.restock(counts, glue="glue", one=1)
  t1: leftNails = stock.take(counts, nails, nine=9)
  writeNailsLead: console.write(nailsText="nails left: ") ~
  writeNails: console.writeIntegerLine(leftNails) ~
  t2: leftTape = stock.take(counts, tape="tape", one)
  writeTapeLead: console.write(tapeText="tape left: ") ~
  writeTape: console.writeIntegerLine(leftTape) ~
  countKeys: keyCount = stock.Counts.length(counts)
  goto eachKey
:eachKey loop=forEach max=keyCount over=counts
  next counts key printKey keysDone
:printKey in=eachKey
  readItem: item = stock.Counts.get(counts, key) ? eachKey
  readCount: n = stock.Item.count(item)
  readShelf: shelf = stock.Item.shelf(item)
  writeKey: console.write(key) ~
  writeColon: console.write(colon=": ") ~
  writeCount: console.writeIntegerLine(n) ~
  writeShelfLead: console.write(shelfText="  shelf ") ~
  writeShelf: console.writeIntegerLine(shelf) ~
  goto eachKey
:keysDone
  hasGlue: glueThere = stock.Counts.contains(counts, glue)
  if glueThere sayGlue done
:sayGlue
  writeGlue: console.writeLine(glueText="glue is stocked") ~
  goto done
:done
  return okCode
