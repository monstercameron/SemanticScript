## A stage0 sample from the audit: transactions held in enums applied to an
## account record, with an error enum the program raises and branches on.
module ledger "Apply transactions held in enums to an account record, with an error enum"
  path ledger
  imports standard.console standard.math standard.compare standard.list standard.string
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record Account "An account's owner and balance"
  field owner String
  field balance Int64

enum Move "A transaction"
  variant deposit Int64
  variant withdraw Int64
  variant fee
  variant rename String

enum LedgerError "Why a transaction was refused"
  variant overdrawn Int64
  variant negative Int64

instance Moves "A list of transactions" list.List Move

op apply "Apply one transaction to a balance"
  input balance Int64 copied
  input move Move borrowed
  output Int64
  raises LedgerError
  let feeAmount Int64 3
:begin
  match move
  case deposit amount onDeposit
  case withdraw amount2 onWithdraw
  case fee onFee
  case rename newName onRename
:onDeposit
  negCheck: isNeg = compare.lessThanInt64(amount, 0)
  if isNeg badAmount addIt
:addIt
  plus: added = math.addInt64(balance, amount)
  return added
:badAmount
  makeNeg: negError = LedgerError.negative(amount)
  raise negError
:onWithdraw
  minus: left = math.subtractInt64(balance, amount2)
  overCheck: over = compare.lessThanInt64(left, 0)
  if over overdrawn keep
:keep
  return left
:overdrawn
  makeOver: overError = LedgerError.overdrawn(left)
  raise overError
:onFee
  charge: charged = math.subtractInt64(balance, feeAmount)
  return charged
:onRename
  return balance

op main "Run a list of transactions and print the balance after each"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 1048576
  let balance Int64 0 mut
  let refused Int64 0 mut
  let doneCode ExitCode 0
  let failCode ExitCode 9
:begin
  makeMoves: moves = Moves.new(scratch)
  m1: d1 = Move.deposit(fifty=50)
  a1: Moves.append(moves, d1)
  m2: w1 = Move.withdraw(twenty=20)
  a2: Moves.append(moves, w1)
  m3: f1 = Move.fee()
  a3: Moves.append(moves, f1)
  m4: w2 = Move.withdraw(hundred=100)
  a4: Moves.append(moves, w2)
  m5: d2 = Move.deposit(minusFive=-5)
  a5: Moves.append(moves, d2)
  m6: r1 = Move.rename(bob="Bob")
  a6: Moves.append(moves, r1)
  m7: d3 = Move.deposit(seven=7)
  a7: Moves.append(moves, d3)
  countMoves: moveCount = Moves.length(moves)
  makeAccount: account = Account.new(alice="Alice", zero=0, scratch)
  goto each
:each loop=forEach max=moveCount over=moves
  next moves move applyOne done
:applyOne in=each
  applying: after = apply(balance, move) ! problem
  iferr applying refusedOne accepted
:accepted in=each
  set balance after
  writeLead: console.write(balanceText="balance ") ~
  writeBalance: console.writeIntegerLine(balance) ~
  goto each
:refusedOne in=each
  bumpRefused: nextRefused = math.addInt64(refused, 1)
  set refused nextRefused
  match problem
  case overdrawn by onOverdrawn
  case negative amount onNegative
:onOverdrawn in=each
  writeOver: console.write(overText="overdrawn to ") ~
  writeBy: console.writeIntegerLine(by) ~
  goto each
:onNegative in=each
  writeNeg: console.write(negText="negative deposit ") ~
  writeAmount: console.writeIntegerLine(amount) ~
  goto each
:done
  readOwner: owner = Account.owner(account)
  greet: line = string.concat(owner, endText=" done", scratch)
  writeOwner: console.writeLine(line) ~
  writeRefusedLead: console.write(refusedText="refused: ") ~
  writeRefused: console.writeIntegerLine(refused) ~
  checkRefused: tooMany = compare.greaterThanInt64(refused, 1)
  if tooMany failing fine
:failing
  return failCode
:fine
  return doneCode
