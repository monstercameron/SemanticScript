op addExtraArguments "Pass every command-line argument after the compiler's name to the C compiler: the runtime to link (native_runtime.c), then any flags"
  input arguments process.Arguments borrowedMutable
  input count Int64 copied
  input region Region borrowed
  effect read process.arguments
  uses argumentReader
  let index Int64 3 mut
:begin
  goto eachExtra
:eachExtra loop=while max=count
  doneCheck: allPassed = compare.greaterOrEqualInt64(index, count)
  if allPassed done readExtra
:readExtra in=eachExtra
  readExtraArgument: extra = process.argument(index, region) ? done
  addExtra: process.addArgument(arguments, extra)
  countExtra: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachExtra
:done
  return
