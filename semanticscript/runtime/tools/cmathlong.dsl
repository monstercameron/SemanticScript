module cmathlong "math.h's transcendental long double functions in SemanticScript: sinl, cosl, tanl, asinl, acosl, atanl, atan2l, expl, exp2l, expm1l, logl, log2l, log10l, log1pl, powl, cbrtl, hypotl, sinhl, coshl, tanhl, asinhl, acoshl, atanhl, erfl, erfcl, tgammal, lgammal, lgammal_r, and fmal, on 320-bit numbers for x87, binary128 and double layouts alike"
  path cmathlong
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.bits standard.logic standard.test heap clibrary clong
  exports none

capability memoryAccess "Authority to read and write a call's workspace and a long double's parts" use machine.memory none

capability systemCalls "Authority to take memory for a call's workspace" use system.calls none

## Each function works on a 320-bit floating point number of its own (a sign, a kind, a power of two, ten
## 32-bit limbs), in the 128 registers of a workspace taken from the heap for the call (nothing is shared, so every
## function is reentrant), and the result is rounded once into the layout by clong's settleAs. The code is the same
## for x87's 64 bits, binary128's 113 and a double's 53, so its tests run on all three layouts from any machine. The
## generator tools/cmathlonggen.py writes this file (and the tables in it).
constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

op limbOr "A cell of an array of limbs in the workspace, 0 outside the array"
  input ws machine.Address copied
  input base Int64 copied
  input count Int64 copied
  input w Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
:begin
  when w < 0 || w >= count yes1 join3
:yes1
  return nothing
:join3
  calc t1 = machine.loadUInt64(ws + (base + w * 8))
  return t1

op bitsAt "32 bits of an array of limbs from a bit place (which may be below 0 or past the end: zeros)"
  input ws machine.Address copied
  input base Int64 copied
  input count Int64 copied
  input p Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = p + 1024
  calc t2 = (t1 >> 5) - 32
  calc t3 = t1 & 31
  calc t4 = limbOr(ws, base, count, t2)
  calc t5 = limbOr(ws, base, count, t2 + 1)
  calc t6 = 32 - t3
  calc t7 = ((t4 >> t3) | (t5 << t6)) & 4294967295
  return t7

op getHead "A register's sign (0), kind (1: 0 zero, 1 finite), or power (2)"
  input ws machine.Address copied
  input r Int64 copied
  input k Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = machine.loadInt64(ws + (r * 128 + k * 8))
  return t1

op setHead "Set a register's sign, kind, or power"
  input ws machine.Address copied
  input r Int64 copied
  input k Int64 copied
  input v Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  machine.storeInt64(ws + (r * 128 + k * 8), v)
  return

op getLimb "A register's limb, from the lowest"
  input ws machine.Address copied
  input r Int64 copied
  input i Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = machine.loadUInt64(ws + ((r) * 128 + 24 + (i) * 8))
  return t1

op setLimb "Set a register's limb"
  input ws machine.Address copied
  input r Int64 copied
  input i Int64 copied
  input v UInt64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  machine.storeUInt64(ws + ((r) * 128 + 24 + (i) * 8), v)
  return

op bfPack "Put the value of an array of limbs (cells of the workspace, from the lowest) times 2 to a power in a register: normalized to ten limbs, the bits below truncated"
  input ws machine.Address copied
  input d Int64 copied
  input base Int64 copied
  input count Int64 copied
  input sign Int64 copied
  input power Int64 copied
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let i1 Int64 0 mut
  let i6 Int64 0 mut
:begin
  calc i1 := count - 1
  goto head1
:head1 loop=while max=forever
  when i1 >= 0 body2 done3
:body2 in=head1
  calc t2 = machine.loadUInt64(ws + (base + i1 * 8))
  when t2 != nothing yes4 join6
:yes4 in=head1
  goto done3
:join6 in=head1
  calc i1 := i1 - 1
  goto head1
:done3
  when i1 < 0 yes7 join9
:yes7
  setHead(ws, d, 0, sign)
  setHead(ws, d, 1, 0)
  return
:join9
  calc t3 = machine.loadUInt64(ws + (base + i1 * 8))
  calc t4 = clong.bitLength(nothing, t3)
  calc t5 = i1 * 32 + t4
  setHead(ws, d, 0, sign)
  setHead(ws, d, 1, 1)
  setHead(ws, d, 2, power + t5 - 320)
  calc i6 := 0
  goto head10
:head10 loop=while max=forever
  when i6 < 10 body11 done12
:body11 in=head10
  calc t7 = bitsAt(ws, base, count, t5 - 320 + i6 * 32)
  setLimb(ws, d, i6, t7)
  calc i6 := i6 + 1
  goto head10
:done12
  return

op bfCopy "Copy a register"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i1 Int64 0 mut
:begin
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < 13 body2 done3
:body2 in=head1
  machine.storeUInt64(ws + ((d) * 128 + 0 + i1 * 8), machine.loadUInt64(ws + ((a) * 128 + 0 + i1 * 8)))
  calc i1 := i1 + 1
  goto head1
:done3
  return

op bfNegate "Flip a register's sign"
  input ws machine.Address copied
  input a Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, a, 0)
  setHead(ws, a, 0, 1 - t1)
  return

op bfShift "Multiply a register by 2 to a power"
  input ws machine.Address copied
  input a Int64 copied
  input k Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, a, 2)
  setHead(ws, a, 2, t1 + k)
  return

op bfSetInt "Set a register to a whole number (below 2^62 in magnitude) times 2 to a power"
  input ws machine.Address copied
  input d Int64 copied
  input v Int64 copied
  input power Int64 copied
  effect use machine.memory
  uses memoryAccess
  let m2 Int64 0 mut
  let s4 Int64 0 mut
:begin
  calc t1 = v < 0
  when t1 yes1 no2
:yes1
  calc m2 := 0 - v
  goto join3
:no2
  calc m2 := v
  goto join3
:join3
  calc t3 = convert.int64ToUInt64(m2)
  machine.storeUInt64(ws + (16384), t3 & 4294967295)
  machine.storeUInt64(ws + (16384 + 8), t3 >> 32)
  when t1 yes4 join6
:yes4
  calc s4 := 1
  goto join6
:join6
  bfPack(ws, d, 16384, 2, s4, power)
  return

op bfKind "A register's kind (0 zero, 1 finite)"
  input ws machine.Address copied
  input a Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, a, 1)
  return t1

op bfLog2Of "floor(log2 |a|) + 1 of a nonzero register: its value is below 2 to this and not below half of it"
  input ws machine.Address copied
  input a Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, a, 2)
  calc t2 = t1 + 320
  return t2

op bfMul "d = a * b (the product truncated to the register's 320 bits)"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  input b Int64 copied
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let i8 Int64 0 mut
  let i9 Int64 0 mut
  let c10 UInt64 0 mut
  let i12 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 0)
  calc t2 = getHead(ws, b, 0)
  calc t3 = (t1 + t2) & 1
  calc t4 = getHead(ws, a, 1)
  calc t5 = getHead(ws, b, 1)
  when t4 == 0 || t5 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, t3)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t6 = getHead(ws, a, 2)
  calc t7 = getHead(ws, b, 2)
  calc i8 := 0
  goto head4
:head4 loop=while max=forever
  when i8 < 20 body5 done6
:body5 in=head4
  machine.storeUInt64(ws + (16384 + i8 * 8), nothing)
  calc i8 := i8 + 1
  goto head4
:done6
  calc i9 := 0
  goto head7
:head7 loop=while max=forever
  when i9 < 10 body8 done9
:body8 in=head7
  calc c10 := nothing
  calc t11 = machine.loadUInt64(ws + ((a) * 128 + 24 + (i9) * 8))
  calc i12 := 0
  goto head10
:head10 loop=while max=forever in=head7
  when i12 < 10 body11 done12
:body11 in=head10
  calc t13 = machine.loadUInt64(ws + ((b) * 128 + 24 + (i12) * 8))
  calc t14 = machine.loadUInt64(ws + (16384 + (i9 + i12) * 8))
  calc t15 = t11 * t13 + t14 + c10
  machine.storeUInt64(ws + (16384 + (i9 + i12) * 8), t15 & 4294967295)
  calc c10 := t15 >> 32
  calc i12 := i12 + 1
  goto head10
:done12 in=head7
  machine.storeUInt64(ws + (16384 + (i9 + 10) * 8), c10)
  calc i9 := i9 + 1
  goto head7
:done9
  bfPack(ws, d, 16384, 20, t3, t6 + t7)
  return

op bfCompareMagnitude "How |a| compares with |b|: -1, 0, or 1"
  input ws machine.Address copied
  input a Int64 copied
  input b Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let less Int64 -1
  let same Int64 0
  let more Int64 1
  let i5 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, b, 1)
  when t1 == 0 && t2 == 0 yes1 join3
:yes1
  return same
:join3
  when t1 == 0 yes4 join6
:yes4
  return less
:join6
  when t2 == 0 yes7 join9
:yes7
  return more
:join9
  calc t3 = getHead(ws, a, 2)
  calc t4 = getHead(ws, b, 2)
  when t3 < t4 yes10 join12
:yes10
  return less
:join12
  when t3 > t4 yes13 join15
:yes13
  return more
:join15
  calc i5 := 9
  goto head16
:head16 loop=while max=forever
  when i5 >= 0 body17 done18
:body17 in=head16
  calc t6 = machine.loadUInt64(ws + ((a) * 128 + 24 + (i5) * 8))
  calc t7 = machine.loadUInt64(ws + ((b) * 128 + 24 + (i5) * 8))
  when t6 < t7 yes19 join21
:yes19 in=head16
  return less
:join21 in=head16
  when t6 > t7 yes22 join24
:yes22 in=head16
  return more
:join24 in=head16
  calc i5 := i5 - 1
  goto head16
:done18
  return same

op bfCompare "How a compares with b: -1, 0, or 1"
  input ws machine.Address copied
  input a Int64 copied
  input b Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let less Int64 -1
  let more Int64 1
  let res6 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, b, 1)
  calc t3 = getHead(ws, a, 0) * t1
  calc t4 = getHead(ws, b, 0) * t2
  when t3 != t4 yes1 join3
:yes1
  when t3 == 1 yes4 no5
:yes4
  return less
:no5
  return more
:join3
  calc t5 = bfCompareMagnitude(ws, a, b)
  when t3 == 1 yes7 no8
:yes7
  calc res6 := 0 - t5
  goto join9
:no8
  calc res6 := t5
  goto join9
:join9
  return res6

op bfSmall "Whether a term is negligible against a sum: zero, or below the sum's top bit by more than 330 bits"
  input ws machine.Address copied
  input term Int64 copied
  input sum Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let yes Bool true
  let no Bool false
:begin
  calc t1 = getHead(ws, term, 1)
  when t1 == 0 yes1 join3
:yes1
  return yes
:join3
  calc t2 = getHead(ws, sum, 1)
  when t2 == 0 yes4 join6
:yes4
  return no
:join6
  calc t3 = getHead(ws, term, 2)
  calc t4 = getHead(ws, sum, 2)
  calc t5 = t3 < t4 - 330
  return t5

op bfAdd "d = a + b, or a - b when negate is 1, exact in a window of 640 bits below the larger"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  input b Int64 copied
  input negate Int64 copied
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let big6 Int64 0 mut
  let small7 Int64 0 mut
  let sbig8 Int64 0 mut
  let i12 Int64 0 mut
  let oneCell UInt64 1
  let c15 UInt64 0 mut
  let i17 Int64 0 mut
  let i21 Int64 0 mut
  let u26 UInt64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, b, 1)
  calc t3 = getHead(ws, a, 0)
  calc t4 = (getHead(ws, b, 0) + negate) & 1
  when t2 == 0 yes1 join3
:yes1
  when d != a yes4 join6
:yes4
  bfCopy(ws, d, a)
  goto join6
:join6
  return
:join3
  when t1 == 0 yes7 join9
:yes7
  bfCopy(ws, d, b)
  when t2 != 0 yes10 join12
:yes10
  setHead(ws, d, 0, t4)
  goto join12
:join12
  return
:join9
  calc t5 = bfCompareMagnitude(ws, a, b)
  when t5 >= 0 yes13 no14
:yes13
  calc big6 := a
  calc small7 := b
  calc sbig8 := t3
  goto join15
:no14
  calc big6 := b
  calc small7 := a
  calc sbig8 := t4
  goto join15
:join15
  calc t9 = getHead(ws, big6, 2)
  calc t10 = getHead(ws, small7, 2)
  calc t11 = t9 - t10
  when t11 > 700 yes16 join18
:yes16
  when d != big6 yes19 join21
:yes19
  bfCopy(ws, d, big6)
  goto join21
:join21
  setHead(ws, d, 0, sbig8)
  return
:join18
  calc i12 := 0
  goto head22
:head22 loop=while max=forever
  when i12 < 20 body23 done24
:body23 in=head22
  calc t13 = bitsAt(ws, (big6) * 128 + 24, 10, i12 * 32 - 320)
  machine.storeUInt64(ws + (16384 + i12 * 8), t13)
  calc t14 = bitsAt(ws, (small7) * 128 + 24, 10, i12 * 32 - 320 + t11)
  machine.storeUInt64(ws + (16640 + i12 * 8), t14)
  calc i12 := i12 + 1
  goto head22
:done24
  machine.storeUInt64(ws + (16384 + 20 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 20 * 8), nothing)
  calc c15 := nothing
  calc t16 = (t3 + t4) & 1
  when t16 == 0 yes25 no26
:yes25
  calc i17 := 0
  goto head28
:head28 loop=while max=forever
  when i17 < 21 body29 done30
:body29 in=head28
  calc t18 = machine.loadUInt64(ws + (16384 + i17 * 8))
  calc t19 = machine.loadUInt64(ws + (16640 + i17 * 8))
  calc t20 = t18 + t19 + c15
  machine.storeUInt64(ws + (16384 + i17 * 8), t20 & 4294967295)
  calc c15 := t20 >> 32
  calc i17 := i17 + 1
  goto head28
:done30
  goto join27
:no26
  calc i21 := 0
  goto head31
:head31 loop=while max=forever
  when i21 < 21 body32 done33
:body32 in=head31
  calc t22 = machine.loadUInt64(ws + (16384 + i21 * 8))
  calc t23 = machine.loadUInt64(ws + (16640 + i21 * 8))
  calc t24 = t23 + c15
  calc t25 = t22 < t24
  when t25 yes34 no35
:yes34 in=head31
  calc u26 := t22 + 4294967296 - t24
  calc c15 := oneCell
  goto join36
:no35 in=head31
  calc u26 := t22 - t24
  calc c15 := nothing
  goto join36
:join36 in=head31
  machine.storeUInt64(ws + (16384 + i21 * 8), u26)
  calc i21 := i21 + 1
  goto head31
:done33
  goto join27
:join27
  bfPack(ws, d, 16384, 21, sbig8, t9 - 320)
  return

op bfMulSmall "d = a * k for a whole number k below 2^31"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  input k Int64 copied
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let c4 UInt64 0 mut
  let i5 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, a, 0)
  when t1 == 0 || k == 0 yes1 join3
:yes1
  setHead(ws, d, 0, t2)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t3 = convert.int64ToUInt64(k)
  calc c4 := nothing
  calc i5 := 0
  goto head4
:head4 loop=while max=forever
  when i5 < 10 body5 done6
:body5 in=head4
  calc t6 = machine.loadUInt64(ws + ((a) * 128 + 24 + (i5) * 8))
  calc t7 = t6 * t3 + c4
  machine.storeUInt64(ws + (16384 + i5 * 8), t7 & 4294967295)
  calc c4 := t7 >> 32
  calc i5 := i5 + 1
  goto head4
:done6
  machine.storeUInt64(ws + (16384 + 10 * 8), c4)
  calc t8 = getHead(ws, a, 2)
  bfPack(ws, d, 16384, 11, t2, t8)
  return

op bfDivSmall "d = a / k for a whole number k from 1 to 2^31 (the quotient truncated to 320 bits)"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  input k Int64 copied
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let r4 UInt64 0 mut
  let i5 Int64 0 mut
  let l7 UInt64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, a, 0)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, t2)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t3 = convert.int64ToUInt64(k)
  calc r4 := nothing
  calc i5 := 0
  goto head4
:head4 loop=while max=forever
  when i5 < 12 body5 done6
:body5 in=head4
  calc t6 = 9 - i5
  when t6 >= 0 yes7 no8
:yes7 in=head4
  calc l7 := machine.loadUInt64(ws + ((a) * 128 + 24 + (t6) * 8))
  goto join9
:no8 in=head4
  calc l7 := nothing
  goto join9
:join9 in=head4
  calc t8 = (r4 << 32) | l7
  calc t9 = t8 / t3
  calc r4 := t8 % t3
  machine.storeUInt64(ws + (16384 + (11 - i5) * 8), t9)
  calc i5 := i5 + 1
  goto head4
:done6
  calc t10 = getHead(ws, a, 2)
  bfPack(ws, d, 16384, 12, t2, t10 - 64)
  return

op hexAt "Digits of lower-case hexadecimal text read as a number"
  input base machine.Address copied
  input start Int64 copied
  input digits Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let v1 UInt64 0 mut
  let a2 Int64 0 mut
:begin
  calc a2 := start
  calc t3 = start + digits
  goto head1
:head1 loop=while max=forever
  when a2 < t3 body2 done3
:body2 in=head1
  calc t4 = base + a2
  calc t5 = convert.byteToInt64(machine.loadByte(t4))
  calc t6 = (t5 & 15) + 9 * (t5 >> 6)
  calc v1 := (v1 << 4) | convert.int64ToUInt64(t6)
  calc a2 := a2 + 1
  goto head1
:done3
  return v1

op bfConst "Load a constant of the table (ln 2, pi, ...; the Bernoulli coefficients from 16) into a register"
  input ws machine.Address copied
  input d Int64 copied
  input index Int64 copied
  effect use machine.memory
  uses memoryAccess
  let constants String "fffffffffffffec06debac98e7b876208baafa2b8a0d175b7298b62d40f3432603f2f6afc9e3b398d1cf79abb17217f7fffffffffffffec155176cd6de1c43f7d1a132478b25166cdd695a58eb577aa8691d3e88be87fed05c17f0bbb8aa3b29fffffffffffffebf1402f3f375424efaf78ea53c3a3f2d4445c9a2023ee34602ad33dc32355baaaf37287195de5bd8a9fffffffffffffec28e3404de514a08793b139b22020bbea68a67cc7429024e0880dc1cd1c4c6628b2168c234c90fdaa2fffffffffffffec159270f11c0759cf8cce620b039a15830ac3e75171409a0eb6bfec34471d48a7f14db688d906eba82fffffffffffffec059270f11c0759cf8cce620b039a15830ac3e75171409a0eb6bfec34471d48a7f14db688d906eba82fffffffffffffec0e00e86c0212f9d7f3daa155ddec6a31313458b4dcfb08f8d4419202394bc900125f5a534eb3f8e43000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fffffffffffffebdaaaaaaabaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaafffffffffffffeb8b60b60b660b60b600b60b60bb60b60b660b60b600b60b60bb60b60b660b60b600b60b60bb60b60b6fffffffffffffeb6d00d00d000d00d000d00d00dd00d00d000d00d000d00d00dd00d00d000d00d000d00d00dd00d00d0fffffffffffffeb69c09c09cc09c09c009c09c099c09c09cc09c09c009c09c099c09c09cc09c09c009c09c099c09c09cfffffffffffffeb6c5631fe49c0372a391ab87538f158c7f4e700dcafe46ae1d2a3c56317539c037c7f91ab8dca8f158fffffffffffffeb7e40fb55886ccc9e33e40fb55586ccc9ee3e40fb55586ccc99e3e40fbb5586cccc9e3e40ffb5586ccfffffffffffffeb9d20d20d220d20d200d20d20dd20d20d220d20d200d20d20dd20d20d220d20d200d20d20dd20d20d2fffffffffffffebbbee1032536587a9cadcff2142547698b9cbee1031436587a8badcff2032547697a9cbee1f2143658fffffffffffffebeb7f4b1c133ffd0c3f4b1c0f0ffd0c3b7b1c0f033d0c3b7f4c0f033ffc3b7f4b1f033ffd0b7f4b1c0fffffffffffffec1ea60748be7312cc39cf6dedcb3808c0f4aa7022348b14c1fcc3ea607edce7312c0f9cf6db23b3808fffffffffffffec49167002de9ea7221459c00b4a7a9c886167002d39ea7221959c00b4e7a9c886467002d3ad6722191fffffffffffffec82e6660d5db44a9299e07ca39b3f712ebe6660d55b44a9292e07ca39d3f712eb96660d55b9cd9292efffffffffffffecc0da740daa740da7440da740dda740da7740da7400da740daa740da7440da740dda740da78911a740fffffffffffffed0d006a04bebd101b8cbc68b5d8d541cdbd250842c94d92e2fb48ff1b3ff6eec24e255bf598d0cc570fffffffffffffed4e369d34f6967b29ee562c08496093d5e234d582bdcb006984469ccae19ee4fdc3708d1c2a8d1044dfffffffffffffed8bbc40617c406169a06169abb169abbc49abbc406bbc40616c406169a06169abb169abbc4e8844d8afffffffffffffeddbcc486776f31219ddbcc486776f312199dbcc486676f312119dbcc488676f312219dbcc4b694d07bfffffffffffffee23cd10484dbb1324ea521c5cdf3066b7e3f07a1f8da88c07949761634a6024d5cf23376aea2288cecfffffffffffffee7881273518127350b127350b827350b887350b881350b881250b881270b881273ea012735a1bbcde4fffffffffffffeec642a2436581714aff642a2433581714aaf642a24435817144af642a22435817103d4642ab4005bdefffffffffffffef10f9144177d424e933b2dcf5daac0952d8573ed1eeeecac9eeae46d98c3a9e6da78fbaae3de466b7cfffffffffffffef7e7457dec877f79427a8e3a5ccbd56936151661b472037c5ed884644b40509f4f77729bcb977d7628fffffffffffffefcdd6c40124e986e1004c2cb4446ba523ad3226a6f83da65972d4f335c0b6b0a355af0bed9e2e1337fffffffffffffff02a77c3ae39209871f0f4b3a8c1f50a7d3ad45715609d8d88186cdeea2b4f92ff98ad89016b9e09405ffffffffffffff08aad33230d86ba7f95188a0d90b3d95edb08640e9478f4715c8bf3f7c0326ab4ce71ac7c8a5f7eef9ffffffffffffff0e67b1c1dc9b376479c513f899071730f38cb9cebd694deef06c86491ada64925c7954084ca0ef80e5ffffffffffffff14ebcc755032502fffd48231e866ba7710f4826900c758797b0ce0256e9790760bda17dd99a8ebfe48ffffffffffffff1a5ef128b12ef3ba1bc796cbec2409b737128b14783ba1b5ef6cbec2ef24c95ab53556fb17bf582a43ffffffffffffff203de9b8b3837d2bb863368772edfbfdaae86d69d545c0eb7804316dcb7770e6713e6c7d0ee940b372ffffffffffffff27aa6b15cba1e0619acd5cee1bb5c73e81bd60a7d4174b18c9451835e1f8cc3b4f89672663989a1506ffffffffffffff2d202cc3d98d4a245ff202cc3dd8d4a2455f202cc33d8d4a24c39002cc58fbed95e5accfedd5cec8c0ffffffffffffff34c2a22018756d4ccaa22017f76d4ccac22017f7754ccac2a2738f0d8d12e5b9c2a55d946ea00536caffffffffffffff3a9a18c246cc135e5d295f18d9400e7586a18c2463c135e5d95e272cec05399005718d0478ff5ca480ffffffffffffff41209adfa68b970d80b59eb1cc618f693309adfa658970d802a1ac906f51ce652dfd425243d8cacde8ffffffffffffff4804b258bed329c3ce8d0ce9083609112fc515283c7d64c29c4ffdd36d6d260a61bd004bf4c375bbf4ffffffffffffff4fab73d9c5597e8319a9ef67b02f302bb274d04093596254776b37993639d8e8f1bfb252c9bad33621ffffffffffffff56ad012b40d012b404012b404a12b404ad2b404ad0bb0f660172fe906af50fd61de3920b45bcff6120ffffffffffffff5da4c00e90378607bcfd7f341cf6ab93ae230b2674a3fe41e58231cf7ef8dc79dce0d2ad9cca0aafb0ffffffffffffff6419dcd2f4f5ccd914e84561c8e3271a695faac26f767c95d95fbd6df4978134fcceca9d6ae3e6a8d1ffffffffffffff6c979056454c494e5242d32ef2959d1faa41b4d93f87f8b383dcfeff56edba51165a2b432d876f6ffdffffffffffffff73cb83f76b66af2f6e362c32369af73ab482bea2578f69ca66585c9bd4aa3a923a48ea68a8a962fd6bffffffffffffff7a360cd0d045ced89ce4e82b8ebb1cd2ebda81b305df8bbbae9aa900b27a20996bd1913f53dea4869cffffffffffffff826a6a6a6a6a6a6a6a6a6a6a6a1a6a6a6a45572460d263b95aac194c4c343289dc2da52b449997535effffffffffffff89a575cf7dfece9689e3860736e3ed46bac8a73c4a9ce8aea8c7c6df5aae81325446f91174de2f3ba6ffffffffffffff91928b7791a9aeb9c23901274cade36d82ea358ea4dc02a0e75d96fc9f052077f225b82dffa84ff64dffffffffffffff995fe75b0e2a08c13a64a1dd2eef8d69f737e542c7cca2eb69e2b304b594b2505ee3dca55e8565d8f3ffffffffffffffa0993ba43ee64ee90fb993ba433f758a18d3c18fb7a838c2525e912aaba551f8fc199e3afadd021705ffffffffffffffa8d9e504672a20b53424ffd733105f4f94f8e925d1dbe02d2f04e11d65c7929611a7979543bf2b7bc7ffffffffffffffb040384d6a4d6a725ddeae8038096e5201540f7fac7813e4ea8417442d45070c1e9290aae4ac829695ffffffffffffffb809fb1d370a676a0c8ef521ec36a513488da75eacf327a913defbd0285d81e2c0f72ab745a242ac78ffffffffffffffc0fafe0e86d85d8623f64906cec4dc53032a871b9cd9faddc71ad6e842ea2cac05f622168f9ef20a47ffffffffffffffc80219078acdd4dd5581af2b837f1b1b00fc9c09cd4f36642fcce947acba474e3f0be3e995a2054030ffffffffffffffd02eb22bbc4fb0a59cbf4c522d8ec2adb60bed14110ff6fa39252000c6ca5053aa97305882abba57a4ffffffffffffffd86fbabed2580d47a1f51b12493126072271871d5380d77e70db10e1b98c9f1fda3da606f8bd1e97d6ffffffffffffffe0a60c63a8ff51002fbe4f03a7921738b1fd60084cbde3b06614fc5e2b7f59f902aea5faa4d83e7996ffffffffffffffe91eae4d747294e7f10d1a5ddd0d0d9b1bc9b6a1c37171a72846b21b9096787673f301c7098045c413"
  let i4 Int64 0 mut
:begin
  calc t1 = machine.addressOfString(constants)
  calc t2 = index * 96
  calc t3 = hexAt(t1, t2, 16)
  setHead(ws, d, 2, convert.uint64BitsToInt64(t3))
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 1)
  calc i4 := 0
  goto head1
:head1 loop=while max=forever
  when i4 < 10 body2 done3
:body2 in=head1
  calc t5 = hexAt(t1, t2 + 16 + i4 * 8, 8)
  setLimb(ws, d, i4, t5)
  calc i4 := i4 + 1
  goto head1
:done3
  return

op twoOverPiBits "32 bits of 2/pi's binary expansion from a place counted from 1 (0 outside the table)"
  input first Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let bits String "a2f9836e4e441529fc2757d1f534ddc0db6295993c439041fe5163abdebbc561b7246e3a424dd2e006492eea09d1921cfe1deb1cb129a73ee88235f52ebb4484e99c7026b45f7e413991d639835339f49c845f8bbdf9283b1ff897ffde05980fef2f118b5a0a6d1f6d367ecf27cb09b74f463f669e5fea2d7527bac7ebe5f17b3d0739f78a5292ea6bfb5fb11f8d5d0856033046fc7b6babf0cfbc209af4361da9e391615ee61b086599855f14a068408dffd8804d73273106061556ca73a8c960e27bc08c6b47c419c367cddce8092a8359c4768b961ca6ddaf44d15719053ea5ff07053f7e33e832c2de4f98327dbbc33d26ef6b1e5ef89f3a1f35caf27f1d87f121907c7c246afa6ed5772d30433b15c614b59d19c3c2c4ad414d2c5d000c467d862d71e39ac69b0062337cd2b497a7b4d55537f63ed71810a3fc764d2a9d64abd770f87c6357b07ae715175649c0d9d63b3884a7cb2324778ad623545ab91f001b0af1dfce19ff319f6a1e6661579947fbacd87f7eb7652289e83260bfe6cdc4ef09366cd43f5dd7de16de3b58929bde2822d2e886284d58e232cac616e308cb7de050c017a71df35be01834132e6212830148835b8ef57fb0adf2e91e434a48d36710d8ddaa425faece616aa4280ab499d3f2a6067f775c83c2a3883c6178738a5a8cafbdd76f63a62dcbbff4ef818d67c12645ca5536d9cad2a8288d61c277c9121426049b4612c459c444c5c891b24df31700ad43d4e5492910d5fdfcbe00cc941eeece70f53e1380f1ecc3e7b328f8c79405933e71c1b3092ef3450b9c12887b20ab9fb52ec292472f327b6d550c90a7721fe76b96cb314a1679e2794189dff49794e884e6e29731996bed88365f5f0efdbbb49a486ca467427271325d8db8159f09e5bc25318d3974f71c0530010c0d68084b58ee2c90aa4702e77424d6bda67df772486eef169fa6948ef691b45153d1f20acf3398207e4bf56863b25f3edd035d407f8985295255c0643710d86d324832754c5bd4714e6e5445c1090b69f52ad566149d072750045ddb3bb4c576ea17f9877d6b49ba271d296996acccc65414ad6ae29089d98850722cbea4049407777030f327fc00a871ea49c2663de06483dd97973fa3fd94438c860dde41319d39928c70dde7b7173bdf082b3715a0805c93805a921110d8e80faf806c4bffdb0f903876185915a562bbcb61b989c7bd401004f2d2277549f6b6ebbb22dbaa140a2f2689768364333b091a940eaa3a51c2a31daeedaf12265c4dc26d9c7a2d9756c0833f03f6f0098c402b99316d07b43915200c5bc3d8c492f54badc6a5ca4ecd37a736a9e69492ab6842ddde6319ef8c76528b6837dbfcaba1ae3115dfa1ae00dafb0c664d64b705ed306529bf56573aff47b9f96af3be75df93283080abf68c6615cb040622fa1de4d9a4b33d8f1b5709cd36e9424ea4be13b523331aaaf0a8654fa5c1d20f3f0bcd785b76f923048b7b72178953a6c6e26e6f00ebef584a9bb7dac4ba66aacfcf761d02d12df1b1c1998c77adc3da4886a05df7f480c62ff0ac9aecddbc5c3f6dded01fc790b6db2a3a25a39aaf009353ad0457b6b42d297e804ba707da0eaa76a1597b2a12162db7dcfde5fafedb89fdbe896c76e4fca90670803e156e85ff87fd073e2833676186182aeabd4dafe7b36e6d8f3967955bbf3148d78416df30432dc7356125ce70c9b8cb30fd6cbfa200a4e46c05a0dd5a476f21d21262845cb9496170e0566b015299375550b7d51ec4f1335f6e13e4305da92e85c3b21d3632a1a4b708d4b1ea21f716e4698f77ff2780030c2d408da0cd4f99a520d3a2b30a5d2f42f9b4cbda11d0be7dc1db9bbd17ab81a2ca5c6a0817552e550027f0147f8607e1640b148d4196debe872afddab6256b34897bfef3059ebfb94f6a68a82a4a5ac44fbcf82d985ad795c7f48d4d0da63a205f57a4b13f149538800120cc86dd71b6dec9f560bf11654d6b0701acb08cd0c0b24855510efb1ec372953b06a33540c07bdc06cc45e0fa294ec8cad641f3e8de647cd8649b31bed9c397a4d45877c5e36913daf03c3aba4618465f7555f5bdd2c6926e5d2eaced440e423e1c87c461e9fd29f3d6e7ca7c2235916fc5e0088dd7ffe26a6ec6fdb0c10893745d7cb2ad6b9d6ecd7b723e6a11c6a9cff7df7329bac9b55100b70db2e224ba74607de58ad8742c150d0c188194667e162901767a9fbefdfdef4556367ed913d9ecb9ba8bfc97c427a831c36ef136c59456a8d8b5a8b40ecccf2d891234576f89562ce3ce99b920d6aa5e6b9c2a3ecc5f114a0bfdfbf4e16d3b8e2c86e284d4e9a9b4fcd1eeefc9352e61392f442138c8d91b0afc816a4afbd81c2f84b4538c994ecc2254dc552ad6c6c096190bb8701a649569605a26ee523f0f117f11b5f4f5cbfc2dbc34eebc34cc5de8605edd9b8e67ef3392b817c99b5861bc57e1c68351103ed84871dddd1c2da118af462c21d7f359987ad9c0549efa864ffc0656ae79e536228922ad38dc9367aae8553826829be7caa40d51b133990ed7a9480569f0b265a7887f974c8836d1f9b392214a827b21cf98dc9f405547dc3a74e142eb67df9dfe5fd45ea4677b7aacbaa2f65523882b55ba41086e59862a21834739e6e389d49ee540fb49e956ffca0f1c8a59c52bfa94c5c1d3cfc50fae5adb86c5476243853b862194792c8761107b4c2a1a2c8012bf43902688893c78e4c4a87bdbe5c23ac4eaf4268a67f7bf920d2ba365b1933d0b7cbddc51a463dd27dde16919949a9529a828ce68b4ed09209f44ca984e638270237c7e32b90f8ef5a7e7561408f1212a9db54d7e6f5119a5abf9b5d6df8261dd960236169f3ac4a1a2836ded727a8d39a9b8825c326b5b2746ed34007700d255f4fc4d59018071e0e13f89b295f364a8f1aea74b38fc4ceab2bb47270babc3a734ba6052dd34f8563aeb7e8a31bb365895b747f7a994c3aad392251e7f3ed8974ebba94fd8ae01e661b4393d8ea523aa33068e1633b53bb1"
  let v2 UInt64 0 mut
  let nothing UInt64 0
  let i3 Int64 0 mut
  let bit5 UInt64 0 mut
:begin
  calc t1 = machine.addressOfString(bits)
  calc v2 := nothing
  calc i3 := 0
  goto head1
:head1 loop=while max=forever
  when i3 < 32 body2 done3
:body2 in=head1
  calc t4 = first + i3
  calc bit5 := nothing
  when t4 >= 1 && t4 <= 17200 yes4 join6
:yes4 in=head1
  calc t6 = (t4 - 1) >> 2
  calc t7 = t1 + t6
  calc t8 = convert.byteToInt64(machine.loadByte(t7))
  calc t9 = (t8 & 15) + 9 * (t8 >> 6)
  calc t10 = (t9 >> (3 - ((t4 - 1) & 3))) & 1
  calc bit5 := convert.int64ToUInt64(t10)
  goto join6
:join6 in=head1
  calc v2 := (v2 << 1) | bit5
  calc i3 := i3 + 1
  goto head1
:done3
  return v2

op bfFromParts "Load a register from a long double's parts (a zero or a finite value)"
  input ws machine.Address copied
  input d Int64 copied
  input parts machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = clong.getPart(parts, 8)
  calc t2 = clong.getPart(parts, 0)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, t2)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t3 = clong.highOf(parts)
  calc t4 = clong.lowOf(parts)
  calc t5 = clong.getPart(parts, 16)
  machine.storeUInt64(ws + (16384), t4 & 4294967295)
  machine.storeUInt64(ws + (16384 + 8), t4 >> 32)
  machine.storeUInt64(ws + (16384 + 16), t3 & 4294967295)
  machine.storeUInt64(ws + (16384 + 24), t3 >> 32)
  bfPack(ws, d, 16384, 4, t2, t5)
  return

op bfToParts "Round a register to the layout (0 double, 1 x87, 2 binary128) into parts: the top 128 bits and what is below them as the sticky part of the rounding"
  input ws machine.Address copied
  input a Int64 copied
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = getHead(ws, a, 1)
  calc t2 = getHead(ws, a, 0)
  when t1 == 0 yes1 join3
:yes1
  clong.setPart(parts, 0, t2)
  clong.setPart(parts, 8, 0)
  clong.setSignificand(parts, 0, 0)
  return
:join3
  calc t3 = getLimb(ws, a, 0)
  calc t4 = getLimb(ws, a, 1)
  calc t5 = getLimb(ws, a, 2)
  calc t6 = getLimb(ws, a, 3)
  calc t7 = getLimb(ws, a, 4)
  calc t8 = getLimb(ws, a, 5)
  calc t9 = getLimb(ws, a, 6)
  calc t10 = getLimb(ws, a, 7)
  calc t11 = getLimb(ws, a, 8)
  calc t12 = getLimb(ws, a, 9)
  calc t13 = (t12 << 32) | t11
  calc t14 = (t10 << 32) | t9
  calc t15 = t8 | t7 | t6 | t5 | t4 | t3
  calc t16 = getHead(ws, a, 2) + 192
  clong.setPart(parts, 0, t2)
  clong.setPart(parts, 8, 1)
  clong.setPart(parts, 16, t16)
  clong.setSignificand(parts, t13, t14)
  calc t17 = flag(t15 != 0, 1)
  clong.settleAs(parts, t17, layout)
  return

op bfTopDouble "The top 53 bits of a nonzero register as a double from 1 to 2"
  input ws machine.Address copied
  input a Int64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getLimb(ws, a, 9)
  calc t2 = getLimb(ws, a, 8)
  calc t3 = (t1 << 21) | (t2 >> 11)
  calc t4 = convert.int64ToFloat64(convert.uint64ToInt64(t3)) * 0x1p-52
  return t4

op bfRoundInt "A register rounded to the nearest whole number (halves away from zero), as an Int64 (below 2^61)"
  input ws machine.Address copied
  input a Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing Int64 0
  let most Int64 2305843009213693952
  let res9 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 1)
  when t1 == 0 yes1 join3
:yes1
  return nothing
:join3
  calc t2 = getHead(ws, a, 2) + 320
  when t2 < 0 yes4 join6
:yes4
  return nothing
:join6
  when t2 > 61 yes7 join9
:yes7
  return most
:join9
  calc t3 = 320 - t2
  calc t4 = bitsAt(ws, a * 128 + 24, 10, t3)
  calc t5 = bitsAt(ws, a * 128 + 24, 10, t3 + 32)
  calc t6 = bitsAt(ws, a * 128 + 24, 10, t3 - 1) & 1
  calc t7 = convert.uint64ToInt64((t5 << 32) | t4) + convert.uint64ToInt64(t6)
  calc t8 = getHead(ws, a, 0)
  when t8 == 1 yes10 no11
:yes10
  calc res9 := 0 - t7
  goto join12
:no11
  calc res9 := t7
  goto join12
:join12
  return res9

op bfRecip "d = 1 / a for a nonzero register (Newton's iteration from a double's reciprocal, three times)"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i6 Int64 0 mut
:begin
  calc t1 = getHead(ws, a, 0)
  bfCopy(ws, 124, a)
  setHead(ws, 124, 0, 0)
  calc t2 = getHead(ws, 124, 2) + 320
  calc t3 = bfTopDouble(ws, 124)
  calc t4 = 1.0 / t3
  calc t5 = convert.float64ToInt64(t4 * 0x1p53)
  bfSetInt(ws, 120, t5, -52 - t2)
  bfSetInt(ws, 122, 2, 0)
  calc i6 := 0
  goto head1
:head1 loop=while max=forever
  when i6 < 3 body2 done3
:body2 in=head1
  bfMul(ws, 121, 124, 120)
  bfAdd(ws, 121, 122, 121, 1)
  bfMul(ws, 120, 120, 121)
  calc i6 := i6 + 1
  goto head1
:done3
  bfCopy(ws, d, 120)
  setHead(ws, d, 0, t1)
  return

op bfDivide "d = a / b for a nonzero register b"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  input b Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  bfRecip(ws, 125, b)
  bfMul(ws, d, a, 125)
  return

op bfRsqrt "d = 1 / sqrt(a) for a positive register (Newton's iteration from a double's, three times)"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  effect use machine.memory
  uses memoryAccess
  let ef1 Int64 0 mut
  let md2 Float64 0.0 mut
  let i5 Int64 0 mut
:begin
  bfCopy(ws, 124, a)
  setHead(ws, 124, 0, 0)
  calc ef1 := getHead(ws, 124, 2) + 319
  calc md2 := bfTopDouble(ws, 124)
  when (ef1 & 1) != 0 yes1 join3
:yes1
  calc md2 := md2 * 2.0
  calc ef1 := ef1 - 1
  goto join3
:join3
  calc t3 = 1.0 / machine.squareRoot(md2)
  calc t4 = convert.float64ToInt64(t3 * 0x1p53)
  bfSetInt(ws, 120, t4, -53 - ef1 / 2)
  bfSetInt(ws, 123, 3, 0)
  calc i5 := 0
  goto head4
:head4 loop=while max=forever
  when i5 < 3 body5 done6
:body5 in=head4
  bfMul(ws, 121, 120, 120)
  bfMul(ws, 121, 121, 124)
  bfAdd(ws, 121, 123, 121, 1)
  bfMul(ws, 120, 120, 121)
  bfShift(ws, 120, -1)
  calc i5 := i5 + 1
  goto head4
:done6
  bfCopy(ws, d, 120)
  return

op bfSqrt "d = sqrt(a) for a nonnegative register"
  input ws machine.Address copied
  input d Int64 copied
  input a Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, a, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  bfRsqrt(ws, 126, a)
  bfMul(ws, d, 126, a)
  return

op bfExpm1Small "d = e^x - 1 for |x| up to 1: x / 256 by Taylor's series, then eight times p <- 2p + p^2"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i2 Int64 0 mut
  let i5 Int64 0 mut
:begin
  calc t1 = getHead(ws, x, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  bfCopy(ws, 40, x)
  bfShift(ws, 40, -8)
  bfCopy(ws, 41, 40)
  bfCopy(ws, 42, 40)
  calc i2 := 0
  goto head4
:head4 loop=while max=forever
  when i2 < 60 body5 done6
:body5 in=head4
  calc t3 = i2 + 2
  bfMul(ws, 41, 41, 40)
  bfDivSmall(ws, 41, 41, t3)
  bfAdd(ws, 42, 42, 41, 0)
  calc t4 = bfSmall(ws, 41, 42)
  when t4 yes7 join9
:yes7 in=head4
  goto done6
:join9 in=head4
  calc i2 := i2 + 1
  goto head4
:done6
  calc i5 := 0
  goto head10
:head10 loop=while max=forever
  when i5 < 8 body11 done12
:body11 in=head10
  bfMul(ws, 43, 42, 42)
  bfShift(ws, 42, 1)
  bfAdd(ws, 42, 42, 43, 0)
  calc i5 := i5 + 1
  goto head10
:done12
  bfCopy(ws, d, 42)
  return

op bfExp "d = e^x for a register below 2^15 in magnitude: x = n ln 2 + r, e^r - 1 by bfExpm1Small, 2^n scaled in"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  bfConst(ws, 32, 1)
  bfMul(ws, 33, x, 32)
  calc t1 = bfRoundInt(ws, 33)
  bfSetInt(ws, 34, t1, 0)
  bfConst(ws, 35, 0)
  bfMul(ws, 34, 34, 35)
  bfAdd(ws, 32, x, 34, 1)
  bfExpm1Small(ws, 33, 32)
  bfSetInt(ws, 34, 1, 0)
  bfAdd(ws, 33, 33, 34, 0)
  bfShift(ws, 33, t1)
  bfCopy(ws, d, 33)
  return

op bfExpm1 "d = e^x - 1 for any register below 2^15 in magnitude"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, x, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t2 = getHead(ws, x, 2) + 320
  when t2 <= 0 yes4 join6
:yes4
  bfExpm1Small(ws, d, x)
  return
:join6
  bfExp(ws, 36, x)
  bfSetInt(ws, 37, 1, 0)
  bfAdd(ws, d, 36, 37, 1)
  return

op bfAtanhTwice "d = 2 atanh(s) = 2 (s + s^3/3 + s^5/5 + ...) for |s| below 1/2"
  input ws machine.Address copied
  input d Int64 copied
  input s Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i2 Int64 0 mut
:begin
  calc t1 = getHead(ws, s, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  bfMul(ws, 29, s, s)
  bfCopy(ws, 30, s)
  bfCopy(ws, 31, s)
  calc i2 := 0
  goto head4
:head4 loop=while max=forever
  when i2 < 400 body5 done6
:body5 in=head4
  calc t3 = i2 * 2 + 3
  bfMul(ws, 30, 30, 29)
  bfDivSmall(ws, 27, 30, t3)
  bfAdd(ws, 31, 31, 27, 0)
  calc t4 = bfSmall(ws, 27, 31)
  when t4 yes7 join9
:yes7 in=head4
  goto done6
:join9 in=head4
  calc i2 := i2 + 1
  goto head4
:done6
  bfShift(ws, 31, 1)
  bfCopy(ws, d, 31)
  return

op bfLog "d = ln x for a positive register: x = 2^k m with m from 0.707 to 1.414, ln m = 2 atanh((m - 1) / (m + 1))"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
  let k1 Int64 0 mut
:begin
  calc k1 := getHead(ws, x, 2) + 319
  bfCopy(ws, 24, x)
  setHead(ws, 24, 0, 0)
  setHead(ws, 24, 2, -319)
  calc t2 = bfTopDouble(ws, 24)
  when t2 > 1.4142135623730951 yes1 join3
:yes1
  bfShift(ws, 24, -1)
  calc k1 := k1 + 1
  goto join3
:join3
  bfSetInt(ws, 25, 1, 0)
  bfAdd(ws, 26, 24, 25, 1)
  bfAdd(ws, 25, 24, 25, 0)
  bfDivide(ws, 26, 26, 25)
  bfAtanhTwice(ws, 26, 26)
  when k1 != 0 yes4 join6
:yes4
  bfSetInt(ws, 25, k1, 0)
  bfConst(ws, 24, 0)
  bfMul(ws, 25, 25, 24)
  bfAdd(ws, 26, 26, 25, 0)
  goto join6
:join6
  bfCopy(ws, d, 26)
  return

op bfLog1p "d = ln(1 + u) for a register u above -1: 2 atanh(u / (2 + u)) when |u| is below 1/2, else ln(1 + u)"
  input ws machine.Address copied
  input d Int64 copied
  input u Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, u, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  calc t2 = getHead(ws, u, 2) + 320
  when t2 < 0 yes4 no5
:yes4
  bfSetInt(ws, 25, 2, 0)
  bfAdd(ws, 25, 25, u, 0)
  bfDivide(ws, 26, u, 25)
  bfAtanhTwice(ws, d, 26)
  goto join6
:no5
  bfSetInt(ws, 25, 1, 0)
  bfAdd(ws, 25, 25, u, 0)
  bfLog(ws, d, 25)
  goto join6
:join6
  return

op bfSinCos "ds = sin r and dc = cos r for |r| up to 0.8 (Taylor series)"
  input ws machine.Address copied
  input ds Int64 copied
  input dc Int64 copied
  input r Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i1 Int64 0 mut
:begin
  bfMul(ws, 48, r, r)
  bfCopy(ws, 49, r)
  bfCopy(ws, 50, r)
  bfSetInt(ws, 51, 1, 0)
  bfSetInt(ws, 52, 1, 0)
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < 36 body2 done3
:body2 in=head1
  calc t2 = (i1 + 1) * 2
  calc t3 = t2 * (t2 + 1)
  calc t4 = (t2 - 1) * t2
  bfMul(ws, 49, 49, 48)
  bfDivSmall(ws, 49, 49, t3)
  bfNegate(ws, 49)
  bfAdd(ws, 50, 50, 49, 0)
  bfMul(ws, 51, 51, 48)
  bfDivSmall(ws, 51, 51, t4)
  bfNegate(ws, 51)
  bfAdd(ws, 52, 52, 51, 0)
  calc i1 := i1 + 1
  goto head1
:done3
  bfCopy(ws, ds, 50)
  bfCopy(ws, dc, 52)
  return

op bfAtan "d = atan t for a nonnegative register: 1/t above 1, three halvings t / (1 + sqrt(1 + t^2)), then the series"
  input ws machine.Address copied
  input d Int64 copied
  input t Int64 copied
  effect use machine.memory
  uses memoryAccess
  let flag2 Int64 0 mut
  let i4 Int64 0 mut
  let i5 Int64 0 mut
:begin
  calc t1 = getHead(ws, t, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  bfCopy(ws, 56, t)
  bfSetInt(ws, 57, 1, 0)
  calc t3 = bfCompare(ws, 56, 57)
  when t3 > 0 yes4 join6
:yes4
  bfRecip(ws, 56, 56)
  calc flag2 := 1
  goto join6
:join6
  calc i4 := 0
  goto head7
:head7 loop=while max=forever
  when i4 < 3 body8 done9
:body8 in=head7
  bfMul(ws, 57, 56, 56)
  bfSetInt(ws, 58, 1, 0)
  bfAdd(ws, 57, 57, 58, 0)
  bfSqrt(ws, 57, 57)
  bfAdd(ws, 57, 57, 58, 0)
  bfDivide(ws, 56, 56, 57)
  calc i4 := i4 + 1
  goto head7
:done9
  bfMul(ws, 57, 56, 56)
  bfCopy(ws, 58, 56)
  bfCopy(ws, 59, 56)
  calc i5 := 0
  goto head10
:head10 loop=while max=forever
  when i5 < 120 body11 done12
:body11 in=head10
  calc t6 = i5 * 2 + 3
  bfMul(ws, 58, 58, 57)
  bfNegate(ws, 58)
  bfDivSmall(ws, 60, 58, t6)
  bfAdd(ws, 59, 59, 60, 0)
  calc t7 = bfSmall(ws, 60, 59)
  when t7 yes13 join15
:yes13 in=head10
  goto done12
:join15 in=head10
  calc i5 := i5 + 1
  goto head10
:done12
  bfShift(ws, 59, 3)
  when flag2 == 1 yes16 join18
:yes16
  bfConst(ws, 60, 3)
  bfShift(ws, 60, -1)
  bfAdd(ws, 59, 60, 59, 1)
  goto join18
:join18
  bfCopy(ws, d, 59)
  return

op bfTrigReduce "The quadrant (0 to 3) and the remainder r in [-pi/4, pi/4] (register d) of a long double's magnitude by pi/2: Payne and Hanek with 2/pi's bits"
  input ws machine.Address copied
  input d Int64 copied
  input parts machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let oneCell UInt64 1
  let i4 Int64 0 mut
  let i6 Int64 0 mut
  let c7 UInt64 0 mut
  let i9 Int64 0 mut
  let q14 Int64 0 mut
  let n16 Int64 0 mut
  let c17 UInt64 0 mut
  let i18 Int64 0 mut
:begin
  calc t1 = clong.highOf(parts)
  calc t2 = clong.lowOf(parts)
  calc t3 = clong.getPart(parts, 16)
  machine.storeUInt64(ws + (17280), t2 & 4294967295)
  machine.storeUInt64(ws + (17280 + 8), t2 >> 32)
  machine.storeUInt64(ws + (17280 + 16), t1 & 4294967295)
  machine.storeUInt64(ws + (17280 + 24), t1 >> 32)
  calc i4 := 0
  goto head1
:head1 loop=while max=forever
  when i4 < 17 body2 done3
:body2 in=head1
  calc t5 = twoOverPiBits(t3 + 512 - i4 * 32 - 31)
  machine.storeUInt64(ws + (16896 + i4 * 8), t5)
  machine.storeUInt64(ws + (16384 + i4 * 8), nothing)
  calc i4 := i4 + 1
  goto head1
:done3
  machine.storeUInt64(ws + (16384 + 17 * 8), nothing)
  calc i6 := 0
  goto head4
:head4 loop=while max=forever
  when i6 < 4 body5 done6
:body5 in=head4
  calc c7 := nothing
  calc t8 = machine.loadUInt64(ws + (17280 + i6 * 8))
  calc i9 := 0
  goto head7
:head7 loop=while max=forever in=head4
  when i9 < 17 - i6 body8 done9
:body8 in=head7
  calc t10 = machine.loadUInt64(ws + (16896 + i9 * 8))
  calc t11 = machine.loadUInt64(ws + (16384 + (i6 + i9) * 8))
  calc t12 = t8 * t10 + t11 + c7
  machine.storeUInt64(ws + (16384 + (i6 + i9) * 8), t12 & 4294967295)
  calc c7 := t12 >> 32
  calc i9 := i9 + 1
  goto head7
:done9 in=head4
  calc i6 := i6 + 1
  goto head4
:done6
  calc t13 = machine.loadUInt64(ws + (16384 + 16 * 8))
  calc q14 := convert.uint64ToInt64(t13 & 3)
  calc t15 = machine.loadUInt64(ws + (16384 + 15 * 8))
  when (t15 >> 31) == 1 yes10 join12
:yes10
  calc n16 := 1
  calc q14 := (q14 + 1) & 3
  calc c17 := oneCell
  calc i18 := 0
  goto head13
:head13 loop=while max=forever
  when i18 < 16 body14 done15
:body14 in=head13
  calc t19 = machine.loadUInt64(ws + (16384 + i18 * 8))
  calc t20 = (t19 ^ 4294967295) + c17
  machine.storeUInt64(ws + (16384 + i18 * 8), t20 & 4294967295)
  calc c17 := t20 >> 32
  calc i18 := i18 + 1
  goto head13
:done15
  goto join12
:join12
  bfPack(ws, d, 16384, 16, n16, -512)
  bfConst(ws, 64, 3)
  bfShift(ws, 64, -1)
  bfMul(ws, d, d, 64)
  return q14

op bfNearest "dI = the whole number nearest a register (halves up in magnitude), dF = x - dI; gives dI's parity (0 or 1)"
  input ws machine.Address copied
  input dI Int64 copied
  input dF Int64 copied
  input x Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let even Int64 0
  let par5 Int64 0 mut
  let i7 Int64 0 mut
  let oneCell UInt64 1
  let c10 UInt64 0 mut
  let i11 Int64 0 mut
:begin
  calc t1 = getHead(ws, x, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, dI, 0, 0)
  setHead(ws, dI, 1, 0)
  setHead(ws, dF, 0, 0)
  setHead(ws, dF, 1, 0)
  return even
:join3
  calc t2 = getHead(ws, x, 0)
  calc t3 = getHead(ws, x, 2) + 320
  when t3 < 0 yes4 join6
:yes4
  setHead(ws, dI, 0, 0)
  setHead(ws, dI, 1, 0)
  bfCopy(ws, dF, x)
  return even
:join6
  when t3 >= 320 yes7 join9
:yes7
  bfCopy(ws, dI, x)
  setHead(ws, dF, 0, 0)
  setHead(ws, dF, 1, 0)
  calc t4 = 0 - (t3 - 320)
  when t4 == 0 yes10 join12
:yes10
  calc par5 := convert.uint64ToInt64(getLimb(ws, x, 0) & 1)
  goto join12
:join12
  return par5
:join9
  calc t6 = 320 - t3
  calc i7 := 0
  goto head13
:head13 loop=while max=forever
  when i7 < 10 body14 done15
:body14 in=head13
  calc t8 = bitsAt(ws, x * 128 + 24, 10, t6 + i7 * 32)
  machine.storeUInt64(ws + (16896 + i7 * 8), t8)
  calc i7 := i7 + 1
  goto head13
:done15
  calc t9 = bitsAt(ws, x * 128 + 24, 10, t6 - 1) & 1
  when t9 == 1 yes16 join18
:yes16
  calc c10 := oneCell
  calc i11 := 0
  goto head19
:head19 loop=while max=forever
  when i11 < 10 body20 done21
:body20 in=head19
  calc t12 = machine.loadUInt64(ws + (16896 + i11 * 8))
  calc t13 = t12 + c10
  machine.storeUInt64(ws + (16896 + i11 * 8), t13 & 4294967295)
  calc c10 := t13 >> 32
  calc i11 := i11 + 1
  goto head19
:done21
  goto join18
:join18
  bfPack(ws, dI, 16896, 10, t2, 0)
  bfAdd(ws, dF, x, dI, 1)
  calc t14 = convert.uint64ToInt64(machine.loadUInt64(ws + (16896)) & 1)
  return t14

op bfSinPi "d = sin(pi f) for a register with |f| up to 1/2"
  input ws machine.Address copied
  input d Int64 copied
  input f Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  bfCopy(ws, 88, f)
  calc t1 = getHead(ws, f, 0)
  setHead(ws, 88, 0, 0)
  bfSetInt(ws, 89, 1, -2)
  calc t2 = bfCompare(ws, 88, 89)
  when t2 <= 0 yes1 no2
:yes1
  bfConst(ws, 90, 3)
  bfMul(ws, 90, 90, 88)
  bfSinCos(ws, 91, 92, 90)
  bfCopy(ws, d, 91)
  goto join3
:no2
  bfSetInt(ws, 89, 1, -1)
  bfAdd(ws, 89, 89, 88, 1)
  bfConst(ws, 90, 3)
  bfMul(ws, 90, 90, 89)
  bfSinCos(ws, 91, 92, 90)
  bfCopy(ws, d, 92)
  goto join3
:join3
  calc t3 = getHead(ws, d, 1)
  when t3 != 0 yes4 join6
:yes4
  setHead(ws, d, 0, t1)
  goto join6
:join6
  return

op bfStirling "d = ln gamma(z) for a register z of 64 or more: (z - 1/2) ln z - z + ln(2 pi)/2 + sum of B(2k) / (2k (2k - 1) z^(2k-1))"
  input ws machine.Address copied
  input d Int64 copied
  input z Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i1 Int64 0 mut
:begin
  bfLog(ws, 72, z)
  bfSetInt(ws, 73, 1, -1)
  bfAdd(ws, 74, z, 73, 1)
  bfMul(ws, 75, 74, 72)
  bfAdd(ws, 75, 75, z, 1)
  bfConst(ws, 76, 6)
  bfAdd(ws, 75, 75, 76, 0)
  bfRecip(ws, 77, z)
  bfMul(ws, 78, 77, 77)
  bfCopy(ws, 79, 77)
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < 56 body2 done3
:body2 in=head1
  calc t2 = i1 + 16
  bfConst(ws, 80, t2)
  bfMul(ws, 81, 80, 79)
  calc t3 = (i1 & 1) == 1
  when t3 yes4 join6
:yes4 in=head1
  bfNegate(ws, 81)
  goto join6
:join6 in=head1
  bfAdd(ws, 75, 75, 81, 0)
  bfMul(ws, 79, 79, 78)
  calc t4 = bfSmall(ws, 81, 75)
  when t4 yes7 join9
:yes7 in=head1
  goto done3
:join9 in=head1
  calc i1 := i1 + 1
  goto head1
:done3
  bfCopy(ws, d, 75)
  return

op bfGammaShift "z moved up to 64 or more: dz = z + n and dp = z (z + 1) ... (z + n - 1); gives n (0 when z is 64 or more, and dp is then 1)"
  input ws machine.Address copied
  input dz Int64 copied
  input dp Int64 copied
  input z Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing Int64 0
  let i4 Int64 0 mut
:begin
  bfSetInt(ws, 82, 1, 0)
  bfCopy(ws, dz, z)
  calc t1 = getHead(ws, z, 2) + 320
  bfSetInt(ws, dp, 1, 0)
  when t1 <= 6 yes1 join3
:yes1
  calc t2 = bfRoundInt(ws, z)
  calc t3 = 65 - t2
  bfCopy(ws, 83, z)
  bfSetInt(ws, 84, 1, 0)
  calc i4 := 0
  goto head4
:head4 loop=while max=forever
  when i4 < t3 body5 done6
:body5 in=head4
  bfMul(ws, dp, dp, 83)
  bfAdd(ws, 83, 83, 84, 0)
  calc i4 := i4 + 1
  goto head4
:done6
  bfCopy(ws, dz, 83)
  return t3
:join3
  return nothing

op bfErfSeries "d = erf x for a register from 0 to 10: 2/sqrt(pi) e^(-x^2) sum 2^n x^(2n+1) / (1 3 ... (2n+1)) (all terms positive)"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i1 Int64 0 mut
:begin
  bfMul(ws, 89, x, x)
  bfCopy(ws, 90, 89)
  bfShift(ws, 90, 1)
  bfCopy(ws, 91, x)
  bfCopy(ws, 92, x)
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < 2000 body2 done3
:body2 in=head1
  calc t2 = i1 * 2 + 3
  bfMul(ws, 91, 91, 90)
  bfDivSmall(ws, 91, 91, t2)
  bfAdd(ws, 92, 92, 91, 0)
  calc t3 = bfSmall(ws, 91, 92)
  when t3 yes4 join6
:yes4 in=head1
  goto done3
:join6 in=head1
  calc i1 := i1 + 1
  goto head1
:done3
  bfCopy(ws, 93, 89)
  bfNegate(ws, 93)
  bfExp(ws, 94, 93)
  bfMul(ws, 92, 92, 94)
  bfConst(ws, 93, 4)
  bfMul(ws, d, 92, 93)
  return

op bfErfcFraction "d = erfc x for a register of 8 or more: e^(-x^2) / (sqrt(pi) (x + (1/2) / (x + 1 / (x + (3/2) / (x + ...)))))"
  input ws machine.Address copied
  input d Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i1 Int64 0 mut
:begin
  bfCopy(ws, 88, x)
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < 200 body2 done3
:body2 in=head1
  calc t2 = 200 - i1
  bfRecip(ws, 89, 88)
  bfMulSmall(ws, 89, 89, t2)
  bfShift(ws, 89, -1)
  bfAdd(ws, 88, x, 89, 0)
  calc i1 := i1 + 1
  goto head1
:done3
  bfMul(ws, 90, x, x)
  bfNegate(ws, 90)
  bfExp(ws, 91, 90)
  bfConst(ws, 92, 5)
  bfMul(ws, 91, 91, 92)
  bfRecip(ws, 93, 88)
  bfMul(ws, d, 91, 93)
  return

op flag "1 when a condition holds, else 0"
  input condition Bool copied
  input value Int64 copied
  output Int64
  let nothing Int64 0
:begin
  when condition yes1 join3
:yes1
  return value
:join3
  return nothing

op bitSet "Whether bit n (counted from 0) of high * 2^64 + low is set"
  input high UInt64 copied
  input low UInt64 copied
  input n Int64 copied
  output Bool
  let yes Bool true
  let no Bool false
  let v1 UInt64 0 mut
:begin
  when n < 0 || n >= 128 yes1 join3
:yes1
  return no
:join3
  when n >= 64 yes4 no5
:yes4
  calc v1 := (high >> (n - 64)) & 1
  goto join6
:no5
  calc v1 := (low >> n) & 1
  goto join6
:join6
  calc t2 = v1 == 1
  return t2

op bfNew "A zeroed workspace for one function's registers and buffers"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = heap.take(17664)
  return t1

op partsOfLong "A long double's parts, in a new block"
  input value machine.LongDouble copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = heap.take(16)
  machine.storeLongDouble(t1, value)
  calc t2 = clong.partsNew()
  clong.unpack(t1, t2)
  heap.give(t1)
  return t2

op longOfParts "The long double parts stand for, the parts' block given back"
  input parts machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = heap.take(16)
  clong.pack(parts, t1)
  calc t2 = machine.loadLongDouble(t1)
  heap.give(t1)
  heap.give(parts)
  return t2

op setSpecial "Make parts a zero (0), a finite placeholder (1), an infinity (2), or a NaN (3) of a sign"
  input parts machine.Address copied
  input kind Int64 copied
  input sign Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  clong.setPart(parts, 0, sign)
  clong.setPart(parts, 8, kind)
  clong.setSignificand(parts, 0, 0)
  return

op setSmallValue "Make parts a small whole number times a power of two, settled to the layout"
  input parts machine.Address copied
  input sign Int64 copied
  input value UInt64 copied
  input power Int64 copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  clong.setPart(parts, 0, sign)
  clong.setPart(parts, 8, 1)
  clong.setPart(parts, 16, power)
  clong.setSignificand(parts, 0, value)
  clong.settleAs(parts, 0, layout)
  return

op invalidNaN "A NaN for an invalid argument: EDOM, and the default NaN of the platform (sign set on x86_64)"
  input parts machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  clibrary.setErrno(33)
  calc t1 = system.aarch64()
  calc t2 = 1 - flag(t1, 1)
  setSpecial(parts, 3, t2)
  return

op noteRange "ERANGE when a result is an infinity or a zero from finite arguments"
  input parts machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = clong.getPart(parts, 8)
  when t1 == 2 || t1 == 0 yes1 join3
:yes1
  clibrary.setErrno(34)
  goto join3
:join3
  return

op bfFinish "Round a register into parts for the layout"
  input ws machine.Address copied
  input r Int64 copied
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bfToParts(ws, r, parts, layout)
  return

op magnitudeOf "The power of two a finite nonzero value is below and not below half of (E plus its bits)"
  input parts machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = clong.highOf(parts)
  calc t2 = clong.lowOf(parts)
  calc t3 = clong.getPart(parts, 16)
  calc t4 = clong.bitLength(t1, t2)
  calc t5 = t3 + t4
  return t5

op isPowerOfTwo "Whether a finite nonzero value is a power of two"
  input parts machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = clong.highOf(parts)
  calc t2 = clong.lowOf(parts)
  calc t3 = clong.bitLength(t1, t2)
  calc t4 = clong.lowBitsSet(t1, t2, t3 - 1)
  calc t5 = !t4
  return t5

op integerKind "For a finite nonzero value: 0 when it is not a whole number, 1 when it is an odd one, 2 when an even one"
  input parts machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let odd Int64 1
  let even Int64 2
  let notWhole Int64 0
:begin
  calc t1 = clong.highOf(parts)
  calc t2 = clong.lowOf(parts)
  calc t3 = clong.getPart(parts, 16)
  when t3 >= 0 yes1 join3
:yes1
  when t3 == 0 && (t2 & 1) == 1 yes4 join6
:yes4
  return odd
:join6
  return even
:join3
  calc t4 = 0 - t3
  when t4 >= 128 yes7 join9
:yes7
  return notWhole
:join9
  calc t5 = clong.lowBitsSet(t1, t2, t4)
  when t5 yes10 join12
:yes10
  return notWhole
:join12
  when bitSet(t1, t2, t4) yes13 join15
:yes13
  return odd
:join15
  return even

op bfAtanRatio "d = atan(y / x) for nonnegative registers y and x, not both zero"
  input ws machine.Address copied
  input d Int64 copied
  input y Int64 copied
  input x Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, y, 1)
  calc t2 = getHead(ws, x, 1)
  when t1 == 0 yes1 join3
:yes1
  setHead(ws, d, 0, 0)
  setHead(ws, d, 1, 0)
  return
:join3
  when t2 == 0 yes4 join6
:yes4
  bfConst(ws, 96, 3)
  bfShift(ws, 96, -1)
  bfCopy(ws, d, 96)
  return
:join6
  bfDivide(ws, 96, y, x)
  bfAtan(ws, d, 96)
  return

op bfFixSign "Set a register's sign (a zero keeps none)"
  input ws machine.Address copied
  input r Int64 copied
  input sign Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = getHead(ws, r, 1)
  when t1 != 0 yes1 join3
:yes1
  setHead(ws, r, 0, sign)
  goto join3
:join3
  return

op expCore "e^x on parts: the correctly rounded value but for the rarest cases"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  setSpecial(parts, 0, 0)
  goto join9
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join12
  calc t3 = magnitudeOf(parts)
  when t3 > 15 yes13 join15
:yes13
  when sign2 == 0 yes16 no17
:yes16
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  goto join18
:no17
  setSpecial(parts, 0, 0)
  clibrary.setErrno(34)
  goto join18
:join18
  return
:join15
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfExp(ws4, 1, 0)
  bfFinish(ws4, 1, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op exp2Core "2^x on parts: the correctly rounded value but for the rarest cases"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  setSpecial(parts, 0, 0)
  goto join9
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join12
  calc t3 = magnitudeOf(parts)
  when t3 > 15 yes13 join15
:yes13
  when sign2 == 0 yes16 no17
:yes16
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  goto join18
:no17
  setSpecial(parts, 0, 0)
  clibrary.setErrno(34)
  goto join18
:join18
  return
:join15
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfConst(ws4, 2, 0)
  bfMul(ws4, 3, 0, 2)
  bfExp(ws4, 1, 3)
  bfFinish(ws4, 1, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op expm1Core "e^x - 1 on parts: the correctly rounded value but for the rarest cases"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  setSmallValue(parts, 1, 1, 0, layout)
  goto join9
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  return
:join12
  calc t3 = magnitudeOf(parts)
  when t3 > 15 yes13 join15
:yes13
  when sign2 == 0 yes16 no17
:yes16
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  goto join18
:no17
  setSmallValue(parts, 1, 1, 0, layout)
  goto join18
:join18
  return
:join15
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfExpm1(ws4, 1, 0)
  bfFinish(ws4, 1, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op logCore "ln x on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  invalidNaN(parts)
  return
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSpecial(parts, 2, 1)
  clibrary.setErrno(34)
  return
:join12
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  when sign2 == 1 yes13 join15
:yes13
  heap.give(ws3)
  invalidNaN(parts)
  return
:join15
  bfLog(ws3, 1, 0)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return

op log2Core "log2 x on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  invalidNaN(parts)
  return
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSpecial(parts, 2, 1)
  clibrary.setErrno(34)
  return
:join12
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  when sign2 == 1 yes13 join15
:yes13
  heap.give(ws3)
  invalidNaN(parts)
  return
:join15
  bfLog(ws3, 1, 0)
  bfConst(ws3, 2, 1)
  bfMul(ws3, 1, 1, 2)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return

op log10Core "log10 x on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  invalidNaN(parts)
  return
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSpecial(parts, 2, 1)
  clibrary.setErrno(34)
  return
:join12
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  when sign2 == 1 yes13 join15
:yes13
  heap.give(ws3)
  invalidNaN(parts)
  return
:join15
  bfLog(ws3, 1, 0)
  bfConst(ws3, 2, 2)
  bfMul(ws3, 1, 1, 2)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return

op log1pCore "ln (1 + x) on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  invalidNaN(parts)
  return
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  return
:join12
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  when sign2 == 1 yes13 join15
:yes13
  bfSetInt(ws3, 1, 1, 0)
  bfAdd(ws3, 2, 1, 0, 0)
  calc t4 = getHead(ws3, 2, 1)
  calc t5 = getHead(ws3, 2, 0)
  when t4 == 0 yes16 join18
:yes16
  heap.give(ws3)
  setSpecial(parts, 2, 1)
  clibrary.setErrno(34)
  return
:join18
  when t5 == 1 yes19 join21
:yes19
  heap.give(ws3)
  invalidNaN(parts)
  return
:join21
  goto join15
:join15
  bfLog1p(ws3, 1, 0)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return

op powCore "x^y on parts with C99's special cases"
  input parts machine.Address copied
  input py machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cmp7 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  calc ky3 = clong.getPart(py, 8)
  calc sy4 = clong.getPart(py, 0)
  when ky3 == 0 yes1 join3
:yes1
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join3
  when kind1 == 1 && sign2 == 0 yes4 join6
:yes4
  calc t5 = magnitudeOf(parts)
  calc t6 = isPowerOfTwo(parts)
  when t5 == 1 && t6 yes7 join9
:yes7
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join9
  goto join6
:join6
  when kind1 == 3 || ky3 == 3 yes10 join12
:yes10
  setSpecial(parts, 3, 0)
  return
:join12
  when kind1 == 2 yes13 no14
:yes13
  calc cmp7 := 1
  goto join15
:no14
  when kind1 == 0 yes16 no17
:yes16
  calc cmp7 := 0 - 1
  goto join18
:no17
  calc t8 = magnitudeOf(parts)
  calc t9 = isPowerOfTwo(parts)
  when t8 <= 0 yes19 no20
:yes19
  calc cmp7 := 0 - 1
  goto join21
:no20
  when t8 == 1 && t9 yes22 no23
:yes22
  calc cmp7 := 0
  goto join24
:no23
  calc cmp7 := 1
  goto join24
:join24
  goto join21
:join21
  goto join18
:join18
  goto join15
:join15
  when ky3 == 2 yes25 join27
:yes25
  when cmp7 == 0 yes28 join30
:yes28
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join30
  calc t10 = cmp7 > 0
  calc t11 = flag(sy4 == 0, 1) == flag(t10, 1)
  when t11 yes31 no32
:yes31
  setSpecial(parts, 2, 0)
  goto join33
:no32
  setSpecial(parts, 0, 0)
  goto join33
:join33
  return
:join27
  calc iy12 = integerKind(py)
  calc odd13 = iy12 == 1
  when kind1 == 2 yes34 join36
:yes34
  when sign2 == 0 yes37 join39
:yes37
  when sy4 == 0 yes40 no41
:yes40
  setSpecial(parts, 2, 0)
  goto join42
:no41
  setSpecial(parts, 0, 0)
  goto join42
:join42
  return
:join39
  calc t14 = flag(odd13, 1)
  when sy4 == 0 yes43 no44
:yes43
  setSpecial(parts, 2, t14)
  goto join45
:no44
  setSpecial(parts, 0, t14)
  goto join45
:join45
  return
:join36
  when kind1 == 0 yes46 join48
:yes46
  calc t15 = flag(odd13 && sign2 == 1, 1)
  when sy4 == 1 yes49 no50
:yes49
  setSpecial(parts, 2, t15)
  clibrary.setErrno(34)
  goto join51
:no50
  setSpecial(parts, 0, t15)
  goto join51
:join51
  return
:join48
  calc t16 = flag(sign2 == 1 && odd13, 1)
  when sign2 == 1 && iy12 == 0 yes52 join54
:yes52
  invalidNaN(parts)
  return
:join54
  calc ws17 = bfNew()
  bfFromParts(ws17, 0, parts)
  bfFromParts(ws17, 1, py)
  setHead(ws17, 0, 0, 0)
  bfLog(ws17, 2, 0)
  bfMul(ws17, 3, 1, 2)
  calc t18 = getHead(ws17, 3, 1)
  when t18 == 0 yes55 join57
:yes55
  bfSetInt(ws17, 4, 1, 0)
  goto join57
:join57
  when t18 != 0 yes58 join60
:yes58
  calc t19 = bfLog2Of(ws17, 3)
  calc t20 = getHead(ws17, 3, 0)
  when t19 > 15 yes61 join63
:yes61
  heap.give(ws17)
  when t20 == 0 yes64 no65
:yes64
  setSpecial(parts, 2, t16)
  clibrary.setErrno(34)
  goto join66
:no65
  setSpecial(parts, 0, t16)
  clibrary.setErrno(34)
  goto join66
:join66
  return
:join63
  bfExp(ws17, 4, 3)
  goto join60
:join60
  setHead(ws17, 4, 0, t16)
  bfFinish(ws17, 4, parts, layout)
  heap.give(ws17)
  noteRange(parts)
  return

op cbrtCore "The cube root on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 != 1 yes1 join3
:yes1
  return
:join3
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  setHead(ws3, 0, 0, 0)
  bfLog(ws3, 1, 0)
  bfDivSmall(ws3, 1, 1, 3)
  bfExp(ws3, 2, 1)
  setHead(ws3, 2, 0, sign2)
  bfFinish(ws3, 2, parts, layout)
  heap.give(ws3)
  return

op hypotCore "sqrt(x^2 + y^2) on parts"
  input parts machine.Address copied
  input py machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  calc ky3 = clong.getPart(py, 8)
  when kind1 == 2 || ky3 == 2 yes1 join3
:yes1
  setSpecial(parts, 2, 0)
  return
:join3
  when kind1 == 3 || ky3 == 3 yes4 join6
:yes4
  setSpecial(parts, 3, 0)
  return
:join6
  when kind1 == 0 && ky3 == 0 yes7 join9
:yes7
  setSpecial(parts, 0, 0)
  return
:join9
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfFromParts(ws4, 1, py)
  bfMul(ws4, 2, 0, 0)
  bfMul(ws4, 3, 1, 1)
  bfAdd(ws4, 4, 2, 3, 0)
  bfSqrt(ws4, 5, 4)
  bfFinish(ws4, 5, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op sinCore "sin on parts: Payne and Hanek's reduction and Taylor series"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let reg6 Int64 0 mut
  let flip7 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  when kind1 == 0 yes7 join9
:yes7
  return
:join9
  calc t3 = magnitudeOf(parts)
  when t3 < -70 yes10 join12
:yes10
  return
:join12
  calc ws4 = bfNew()
  calc q5 = bfTrigReduce(ws4, 0, parts)
  bfSinCos(ws4, 1, 2, 0)
  when q5 == 0 yes13 no14
:yes13
  calc reg6 := 1
  calc flip7 := 0
  goto join15
:no14
  when q5 == 1 yes16 no17
:yes16
  calc reg6 := 2
  calc flip7 := 0
  goto join18
:no17
  when q5 == 2 yes19 no20
:yes19
  calc reg6 := 1
  calc flip7 := 1
  goto join21
:no20
  calc reg6 := 2
  calc flip7 := 1
  goto join21
:join21
  goto join18
:join18
  goto join15
:join15
  bfCopy(ws4, 3, reg6)
  when flip7 == 1 yes22 join24
:yes22
  bfNegate(ws4, 3)
  goto join24
:join24
  when sign2 == 1 yes25 join27
:yes25
  bfNegate(ws4, 3)
  goto join27
:join27
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  return

op cosCore "cos on parts: Payne and Hanek's reduction and Taylor series"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let reg6 Int64 0 mut
  let flip7 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  when kind1 == 0 yes7 join9
:yes7
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join9
  calc t3 = magnitudeOf(parts)
  when t3 < -70 yes10 join12
:yes10
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join12
  calc ws4 = bfNew()
  calc q5 = bfTrigReduce(ws4, 0, parts)
  bfSinCos(ws4, 1, 2, 0)
  when q5 == 0 yes13 no14
:yes13
  calc reg6 := 2
  calc flip7 := 0
  goto join15
:no14
  when q5 == 1 yes16 no17
:yes16
  calc reg6 := 1
  calc flip7 := 1
  goto join18
:no17
  when q5 == 2 yes19 no20
:yes19
  calc reg6 := 2
  calc flip7 := 1
  goto join21
:no20
  calc reg6 := 1
  calc flip7 := 0
  goto join21
:join21
  goto join18
:join18
  goto join15
:join15
  bfCopy(ws4, 3, reg6)
  when flip7 == 1 yes22 join24
:yes22
  bfNegate(ws4, 3)
  goto join24
:join24
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  return

op tanCore "tan on parts: Payne and Hanek's reduction and Taylor series"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  when kind1 == 0 yes7 join9
:yes7
  return
:join9
  calc t3 = magnitudeOf(parts)
  when t3 < -70 yes10 join12
:yes10
  return
:join12
  calc ws4 = bfNew()
  calc q5 = bfTrigReduce(ws4, 0, parts)
  bfSinCos(ws4, 1, 2, 0)
  calc t6 = (q5 & 1) == 0
  when t6 yes13 no14
:yes13
  bfDivide(ws4, 3, 1, 2)
  goto join15
:no14
  bfDivide(ws4, 3, 2, 1)
  bfNegate(ws4, 3)
  goto join15
:join15
  when sign2 == 1 yes16 join18
:yes16
  bfNegate(ws4, 3)
  goto join18
:join18
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  return

op atanCore "atan on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  calc ws3 = bfNew()
  bfConst(ws3, 1, 3)
  bfShift(ws3, 1, -1)
  bfFixSign(ws3, 1, sign2)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return
:join6
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  setHead(ws4, 0, 0, 0)
  bfAtan(ws4, 1, 0)
  bfFixSign(ws4, 1, sign2)
  bfFinish(ws4, 1, parts, layout)
  heap.give(ws4)
  return

op asinCore "asin on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cmp3 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  calc t4 = magnitudeOf(parts)
  calc t5 = isPowerOfTwo(parts)
  when t4 <= 0 yes7 no8
:yes7
  calc cmp3 := 0 - 1
  goto join9
:no8
  when t4 == 1 && t5 yes10 no11
:yes10
  calc cmp3 := 0
  goto join12
:no11
  calc cmp3 := 1
  goto join12
:join12
  goto join9
:join9
  when cmp3 > 0 yes13 join15
:yes13
  invalidNaN(parts)
  return
:join15
  when cmp3 == 0 yes16 join18
:yes16
  calc ws6 = bfNew()
  bfConst(ws6, 1, 3)
  bfShift(ws6, 1, -1)
  bfFixSign(ws6, 1, sign2)
  bfFinish(ws6, 1, parts, layout)
  heap.give(ws6)
  return
:join18
  calc ws7 = bfNew()
  bfFromParts(ws7, 0, parts)
  setHead(ws7, 0, 0, 0)
  bfSetInt(ws7, 1, 1, 0)
  bfAdd(ws7, 2, 1, 0, 1)
  bfAdd(ws7, 3, 1, 0, 0)
  bfMul(ws7, 2, 2, 3)
  bfSqrt(ws7, 2, 2)
  bfAtanRatio(ws7, 4, 0, 2)
  bfFixSign(ws7, 4, sign2)
  bfFinish(ws7, 4, parts, layout)
  heap.give(ws7)
  return

op acosCore "acos on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cmp4 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  when kind1 == 0 yes7 join9
:yes7
  calc ws3 = bfNew()
  bfConst(ws3, 1, 3)
  bfShift(ws3, 1, -1)
  bfFinish(ws3, 1, parts, layout)
  heap.give(ws3)
  return
:join9
  calc t5 = magnitudeOf(parts)
  calc t6 = isPowerOfTwo(parts)
  when t5 <= 0 yes10 no11
:yes10
  calc cmp4 := 0 - 1
  goto join12
:no11
  when t5 == 1 && t6 yes13 no14
:yes13
  calc cmp4 := 0
  goto join15
:no14
  calc cmp4 := 1
  goto join15
:join15
  goto join12
:join12
  when cmp4 > 0 yes16 join18
:yes16
  invalidNaN(parts)
  return
:join18
  when cmp4 == 0 yes19 join21
:yes19
  when sign2 == 1 yes22 no23
:yes22
  calc ws7 = bfNew()
  bfConst(ws7, 1, 3)
  bfFinish(ws7, 1, parts, layout)
  heap.give(ws7)
  return
:no23
  setSpecial(parts, 0, 0)
  return
:join21
  calc ws8 = bfNew()
  bfFromParts(ws8, 0, parts)
  setHead(ws8, 0, 0, 0)
  bfSetInt(ws8, 1, 1, 0)
  bfAdd(ws8, 2, 1, 0, 1)
  bfAdd(ws8, 3, 1, 0, 0)
  bfMul(ws8, 2, 2, 3)
  bfSqrt(ws8, 2, 2)
  bfAtanRatio(ws8, 4, 2, 0)
  when sign2 == 1 yes25 join27
:yes25
  bfConst(ws8, 5, 3)
  bfAdd(ws8, 4, 5, 4, 1)
  goto join27
:join27
  bfFinish(ws8, 4, parts, layout)
  heap.give(ws8)
  return

op atan2Core "atan2 (y in the parts, x given) on parts, with Annex F's special values"
  input parts machine.Address copied
  input px machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  calc kx3 = clong.getPart(px, 8)
  calc sx4 = clong.getPart(px, 0)
  when kind1 == 3 || kx3 == 3 yes1 join3
:yes1
  setSpecial(parts, 3, 0)
  return
:join3
  when kind1 == 0 yes4 join6
:yes4
  when sx4 == 0 yes7 join9
:yes7
  setSpecial(parts, 0, sign2)
  return
:join9
  calc ws5 = bfNew()
  bfConst(ws5, 1, 3)
  bfFixSign(ws5, 1, sign2)
  bfFinish(ws5, 1, parts, layout)
  heap.give(ws5)
  return
:join6
  when kx3 == 0 yes10 join12
:yes10
  calc ws6 = bfNew()
  bfConst(ws6, 1, 3)
  bfMulSmall(ws6, 1, 1, 2)
  bfShift(ws6, 1, -2)
  bfFixSign(ws6, 1, sign2)
  bfFinish(ws6, 1, parts, layout)
  heap.give(ws6)
  return
:join12
  when kind1 == 2 yes13 join15
:yes13
  when kx3 == 2 yes16 join18
:yes16
  when sx4 == 0 yes19 no20
:yes19
  calc ws7 = bfNew()
  bfConst(ws7, 1, 3)
  bfMulSmall(ws7, 1, 1, 1)
  bfShift(ws7, 1, -2)
  bfFixSign(ws7, 1, sign2)
  bfFinish(ws7, 1, parts, layout)
  heap.give(ws7)
  return
:no20
  calc ws8 = bfNew()
  bfConst(ws8, 1, 3)
  bfMulSmall(ws8, 1, 1, 3)
  bfShift(ws8, 1, -2)
  bfFixSign(ws8, 1, sign2)
  bfFinish(ws8, 1, parts, layout)
  heap.give(ws8)
  return
:join18
  calc ws9 = bfNew()
  bfConst(ws9, 1, 3)
  bfMulSmall(ws9, 1, 1, 2)
  bfShift(ws9, 1, -2)
  bfFixSign(ws9, 1, sign2)
  bfFinish(ws9, 1, parts, layout)
  heap.give(ws9)
  return
:join15
  when kx3 == 2 yes22 join24
:yes22
  when sx4 == 0 yes25 no26
:yes25
  setSpecial(parts, 0, sign2)
  return
:no26
  calc ws10 = bfNew()
  bfConst(ws10, 1, 3)
  bfFixSign(ws10, 1, sign2)
  bfFinish(ws10, 1, parts, layout)
  heap.give(ws10)
  return
:join24
  calc ws11 = bfNew()
  bfFromParts(ws11, 0, parts)
  bfFromParts(ws11, 1, px)
  setHead(ws11, 0, 0, 0)
  setHead(ws11, 1, 0, 0)
  bfAtanRatio(ws11, 2, 0, 1)
  when sx4 == 1 yes28 join30
:yes28
  bfConst(ws11, 3, 3)
  bfAdd(ws11, 2, 3, 2, 1)
  goto join30
:join30
  bfFixSign(ws11, 2, sign2)
  bfFinish(ws11, 2, parts, layout)
  heap.give(ws11)
  return

op sinhCore "sinh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 != 1 yes1 join3
:yes1
  return
:join3
  calc t3 = magnitudeOf(parts)
  when t3 > 14 yes4 join6
:yes4
  setSpecial(parts, 2, sign2)
  clibrary.setErrno(34)
  return
:join6
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  setHead(ws4, 0, 0, 0)
  calc t5 = bfLog2Of(ws4, 0)
  when t5 <= 0 yes7 no8
:yes7
  bfExpm1Small(ws4, 1, 0)
  bfSetInt(ws4, 2, 2, 0)
  bfAdd(ws4, 3, 1, 2, 0)
  bfMul(ws4, 4, 1, 3)
  bfSetInt(ws4, 5, 1, 0)
  bfAdd(ws4, 5, 1, 5, 0)
  bfShift(ws4, 5, 1)
  bfDivide(ws4, 6, 4, 5)
  goto join9
:no8
  bfExp(ws4, 1, 0)
  bfRecip(ws4, 2, 1)
  bfAdd(ws4, 3, 1, 2, 1)
  bfShift(ws4, 3, -1)
  bfCopy(ws4, 6, 3)
  goto join9
:join9
  bfFixSign(ws4, 6, sign2)
  bfFinish(ws4, 6, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op coshCore "cosh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  setSpecial(parts, 2, 0)
  return
:join6
  when kind1 == 0 yes7 join9
:yes7
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join9
  calc t3 = magnitudeOf(parts)
  when t3 > 14 yes10 join12
:yes10
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  return
:join12
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfExp(ws4, 1, 0)
  bfRecip(ws4, 2, 1)
  bfAdd(ws4, 3, 1, 2, 0)
  bfShift(ws4, 3, -1)
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op tanhCore "tanh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  setSmallValue(parts, sign2, 1, 0, layout)
  return
:join6
  calc t3 = magnitudeOf(parts)
  when t3 > 7 yes7 join9
:yes7
  setSmallValue(parts, sign2, 1, 0, layout)
  return
:join9
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  setHead(ws4, 0, 0, 0)
  bfCopy(ws4, 1, 0)
  bfShift(ws4, 1, 1)
  bfExpm1(ws4, 2, 1)
  bfSetInt(ws4, 3, 2, 0)
  bfAdd(ws4, 3, 2, 3, 0)
  bfDivide(ws4, 4, 2, 3)
  bfFixSign(ws4, 4, sign2)
  bfFinish(ws4, 4, parts, layout)
  heap.give(ws4)
  return

op asinhCore "asinh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 || kind1 == 2 yes1 join3
:yes1
  return
:join3
  calc ws3 = bfNew()
  bfFromParts(ws3, 0, parts)
  setHead(ws3, 0, 0, 0)
  bfMul(ws3, 1, 0, 0)
  bfSetInt(ws3, 2, 1, 0)
  bfAdd(ws3, 3, 1, 2, 0)
  bfSqrt(ws3, 3, 3)
  bfAdd(ws3, 3, 3, 2, 0)
  bfDivide(ws3, 4, 1, 3)
  bfAdd(ws3, 4, 4, 0, 0)
  bfLog1p(ws3, 5, 4)
  bfFixSign(ws3, 5, sign2)
  bfFinish(ws3, 5, parts, layout)
  heap.give(ws3)
  return

op acoshCore "acosh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cmp3 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 no8
:yes7
  invalidNaN(parts)
  return
:no8
  return
:join6
  when kind1 == 0 || sign2 == 1 yes10 join12
:yes10
  invalidNaN(parts)
  return
:join12
  calc t4 = magnitudeOf(parts)
  calc t5 = isPowerOfTwo(parts)
  when t4 <= 0 yes13 no14
:yes13
  calc cmp3 := 0 - 1
  goto join15
:no14
  when t4 == 1 && t5 yes16 no17
:yes16
  calc cmp3 := 0
  goto join18
:no17
  calc cmp3 := 1
  goto join18
:join18
  goto join15
:join15
  when cmp3 < 0 yes19 join21
:yes19
  invalidNaN(parts)
  return
:join21
  when cmp3 == 0 yes22 join24
:yes22
  setSpecial(parts, 0, 0)
  return
:join24
  calc ws6 = bfNew()
  bfFromParts(ws6, 0, parts)
  bfSetInt(ws6, 1, 1, 0)
  bfAdd(ws6, 2, 0, 1, 1)
  bfSetInt(ws6, 3, 2, 0)
  bfAdd(ws6, 3, 3, 2, 0)
  bfMul(ws6, 3, 3, 2)
  bfSqrt(ws6, 3, 3)
  bfAdd(ws6, 3, 3, 2, 0)
  bfLog1p(ws6, 4, 3)
  bfFinish(ws6, 4, parts, layout)
  heap.give(ws6)
  return

op atanhCore "atanh on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cmp3 Int64 0 mut
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  invalidNaN(parts)
  return
:join6
  calc t4 = magnitudeOf(parts)
  calc t5 = isPowerOfTwo(parts)
  when t4 <= 0 yes7 no8
:yes7
  calc cmp3 := 0 - 1
  goto join9
:no8
  when t4 == 1 && t5 yes10 no11
:yes10
  calc cmp3 := 0
  goto join12
:no11
  calc cmp3 := 1
  goto join12
:join12
  goto join9
:join9
  when cmp3 > 0 yes13 join15
:yes13
  invalidNaN(parts)
  return
:join15
  when cmp3 == 0 yes16 join18
:yes16
  setSpecial(parts, 2, sign2)
  clibrary.setErrno(34)
  return
:join18
  calc ws6 = bfNew()
  bfFromParts(ws6, 0, parts)
  setHead(ws6, 0, 0, 0)
  bfSetInt(ws6, 1, 1, 0)
  bfAdd(ws6, 2, 1, 0, 1)
  bfCopy(ws6, 3, 0)
  bfShift(ws6, 3, 1)
  bfDivide(ws6, 4, 3, 2)
  bfLog1p(ws6, 5, 4)
  bfShift(ws6, 5, -1)
  bfFixSign(ws6, 5, sign2)
  bfFinish(ws6, 5, parts, layout)
  heap.give(ws6)
  return

op erfCore "erf on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 || kind1 == 0 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  setSmallValue(parts, sign2, 1, 0, layout)
  return
:join6
  calc t3 = magnitudeOf(parts)
  when t3 > 4 yes7 join9
:yes7
  setSmallValue(parts, sign2, 1, 0, layout)
  return
:join9
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  setHead(ws4, 0, 0, 0)
  bfErfSeries(ws4, 1, 0)
  bfFixSign(ws4, 1, sign2)
  bfFinish(ws4, 1, parts, layout)
  heap.give(ws4)
  return

op erfcCore "erfc on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 0 yes7 no8
:yes7
  setSpecial(parts, 0, 0)
  goto join9
:no8
  setSmallValue(parts, 0, 1, 1, layout)
  goto join9
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSmallValue(parts, 0, 1, 0, layout)
  return
:join12
  calc t3 = magnitudeOf(parts)
  when sign2 == 1 && t3 > 3 yes13 join15
:yes13
  setSmallValue(parts, 0, 1, 1, layout)
  return
:join15
  when sign2 == 0 && t3 > 7 yes16 join18
:yes16
  setSpecial(parts, 0, 0)
  clibrary.setErrno(34)
  return
:join18
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  setHead(ws4, 0, 0, 0)
  when t3 > 3 yes19 no20
:yes19
  bfErfcFraction(ws4, 3, 0)
  goto join21
:no20
  bfErfSeries(ws4, 1, 0)
  bfSetInt(ws4, 2, 1, 0)
  when sign2 == 1 yes22 no23
:yes22
  bfAdd(ws4, 3, 2, 1, 0)
  goto join24
:no23
  bfAdd(ws4, 3, 2, 1, 1)
  goto join24
:join24
  goto join21
:join21
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return

op tgammaCore "tgamma on parts"
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return
:join3
  when kind1 == 2 yes4 join6
:yes4
  when sign2 == 1 yes7 join9
:yes7
  invalidNaN(parts)
  goto join9
:join9
  return
:join6
  when kind1 == 0 yes10 join12
:yes10
  setSpecial(parts, 2, sign2)
  clibrary.setErrno(34)
  return
:join12
  calc t3 = integerKind(parts)
  when sign2 == 1 && t3 != 0 yes13 join15
:yes13
  invalidNaN(parts)
  return
:join15
  calc t4 = magnitudeOf(parts)
  when sign2 == 0 yes16 join18
:yes16
  when t4 > 11 yes19 join21
:yes19
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  return
:join21
  calc ws5 = bfNew()
  bfFromParts(ws5, 0, parts)
  calc t6 = bfGammaShift(ws5, 1, 2, 0)
  bfStirling(ws5, 3, 1)
  bfExp(ws5, 4, 3)
  when t6 > 0 yes22 join24
:yes22
  bfDivide(ws5, 4, 4, 2)
  goto join24
:join24
  bfFinish(ws5, 4, parts, layout)
  heap.give(ws5)
  noteRange(parts)
  return
:join18
  calc ws7 = bfNew()
  bfFromParts(ws7, 0, parts)
  calc t8 = bfNearest(ws7, 5, 6, 0)
  bfSetInt(ws7, 1, 1, 0)
  bfAdd(ws7, 1, 1, 0, 1)
  calc t9 = bfGammaShift(ws7, 7, 2, 1)
  bfStirling(ws7, 3, 7)
  calc t10 = bfLog2Of(ws7, 3)
  when t10 > 15 yes25 join27
:yes25
  calc t11 = getHead(ws7, 6, 0)
  calc t12 = (t8 + t11) & 1
  heap.give(ws7)
  setSpecial(parts, 0, t12)
  clibrary.setErrno(34)
  return
:join27
  bfExp(ws7, 4, 3)
  when t9 > 0 yes28 join30
:yes28
  bfDivide(ws7, 4, 4, 2)
  goto join30
:join30
  bfSinPi(ws7, 8, 6)
  calc t13 = getHead(ws7, 6, 0)
  setHead(ws7, 8, 0, 0)
  bfMul(ws7, 9, 8, 4)
  bfConst(ws7, 10, 3)
  bfDivide(ws7, 11, 10, 9)
  calc t14 = (t8 + t13) & 1
  bfFixSign(ws7, 11, t14)
  bfFinish(ws7, 11, parts, layout)
  heap.give(ws7)
  noteRange(parts)
  return

op lgammaCore "lgamma on parts; gives the sign of gamma(x), 1 or -1"
  input parts machine.Address copied
  input layout Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let plus Int64 1
  let minus Int64 -1
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  when kind1 == 3 yes1 join3
:yes1
  return plus
:join3
  when kind1 == 2 yes4 join6
:yes4
  setSpecial(parts, 2, 0)
  return plus
:join6
  when kind1 == 0 yes7 join9
:yes7
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  when sign2 == 1 yes10 no11
:yes10
  return minus
:no11
  return plus
:join9
  calc t3 = integerKind(parts)
  when sign2 == 1 && t3 != 0 yes13 join15
:yes13
  setSpecial(parts, 2, 0)
  clibrary.setErrno(34)
  return plus
:join15
  when sign2 == 0 yes16 join18
:yes16
  calc ws4 = bfNew()
  bfFromParts(ws4, 0, parts)
  bfSetInt(ws4, 1, 1, 0)
  calc t5 = bfCompare(ws4, 0, 1)
  bfSetInt(ws4, 1, 2, 0)
  calc t6 = bfCompare(ws4, 0, 1)
  when t5 == 0 || t6 == 0 yes19 join21
:yes19
  heap.give(ws4)
  setSpecial(parts, 0, 0)
  return plus
:join21
  calc t7 = bfGammaShift(ws4, 1, 2, 0)
  bfStirling(ws4, 3, 1)
  when t7 > 0 yes22 join24
:yes22
  bfLog(ws4, 4, 2)
  bfAdd(ws4, 3, 3, 4, 1)
  goto join24
:join24
  bfFinish(ws4, 3, parts, layout)
  heap.give(ws4)
  noteRange(parts)
  return plus
:join18
  calc ws8 = bfNew()
  bfFromParts(ws8, 0, parts)
  calc t9 = bfNearest(ws8, 5, 6, 0)
  bfSetInt(ws8, 1, 1, 0)
  bfAdd(ws8, 1, 1, 0, 1)
  calc t10 = bfGammaShift(ws8, 7, 2, 1)
  bfStirling(ws8, 3, 7)
  when t10 > 0 yes25 join27
:yes25
  bfLog(ws8, 4, 2)
  bfAdd(ws8, 3, 3, 4, 1)
  goto join27
:join27
  bfSinPi(ws8, 8, 6)
  calc t11 = getHead(ws8, 6, 0)
  setHead(ws8, 8, 0, 0)
  bfLog(ws8, 9, 8)
  bfConst(ws8, 12, 3)
  bfLog(ws8, 10, 12)
  bfAdd(ws8, 10, 10, 9, 1)
  bfAdd(ws8, 10, 10, 3, 1)
  calc t12 = (t9 + t11) & 1
  bfFinish(ws8, 10, parts, layout)
  heap.give(ws8)
  noteRange(parts)
  when t12 == 1 yes28 no29
:yes28
  return minus
:no29
  return plus

op fmaCore "fma on parts: x * y + z with one rounding"
  input parts machine.Address copied
  input py machine.Address copied
  input pz machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc kind1 = clong.getPart(parts, 8)
  calc sign2 = clong.getPart(parts, 0)
  calc ky3 = clong.getPart(py, 8)
  calc sy4 = clong.getPart(py, 0)
  calc kz5 = clong.getPart(pz, 8)
  calc sz6 = clong.getPart(pz, 0)
  calc sp7 = (sign2 + sy4) & 1
  when (kind1 == 2 && ky3 == 0) || (kind1 == 0 && ky3 == 2) yes1 join3
:yes1
  invalidNaN(parts)
  return
:join3
  when kind1 == 3 || ky3 == 3 || kz5 == 3 yes4 join6
:yes4
  setSpecial(parts, 3, 0)
  return
:join6
  when kind1 == 2 || ky3 == 2 yes7 join9
:yes7
  when kz5 == 2 && sz6 != sp7 yes10 join12
:yes10
  invalidNaN(parts)
  return
:join12
  setSpecial(parts, 2, sp7)
  return
:join9
  when kz5 == 2 yes13 join15
:yes13
  setSpecial(parts, 2, sz6)
  return
:join15
  when kind1 == 0 || ky3 == 0 yes16 join18
:yes16
  when kz5 == 0 yes19 join21
:yes19
  setSpecial(parts, 0, sp7 & sz6)
  return
:join21
  clong.setPart(parts, 0, sz6)
  clong.setPart(parts, 8, 1)
  clong.setPart(parts, 16, clong.getPart(pz, 16))
  clong.setSignificand(parts, clong.highOf(pz), clong.lowOf(pz))
  clong.settleAs(parts, 0, layout)
  return
:join18
  calc ws8 = bfNew()
  fmaExact(ws8, parts, py, pz, sp7, sz6, kz5, layout)
  heap.give(ws8)
  noteRange(parts)
  return

op fmaExact "x * y + z exactly in 32-bit limbs, rounded once into parts (x in parts; x and y finite nonzero)"
  input ws machine.Address copied
  input parts machine.Address copied
  input py machine.Address copied
  input pz machine.Address copied
  input sp Int64 copied
  input sz Int64 copied
  input kz Int64 copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nothing UInt64 0
  let oneCell UInt64 1
  let i7 Int64 0 mut
  let i8 Int64 0 mut
  let c9 UInt64 0 mut
  let i11 Int64 0 mut
  let lp19 Int64 0 mut
  let lz20 Int64 0 mut
  let epv23 Int64 0 mut
  let ezv24 Int64 0 mut
  let far Int64 600
  let e028 Int64 0 mut
  let i31 Int64 0 mut
  let rs35 Int64 0 mut
  let cmp36 Int64 0 mut
  let j37 Int64 0 mut
  let i40 Int64 0 mut
  let b43 UInt64 0 mut
  let i44 Int64 0 mut
  let u48 UInt64 0 mut
  let c49 UInt64 0 mut
  let i50 Int64 0 mut
  let sticky60 Int64 0 mut
  let j61 Int64 0 mut
  let m65 UInt64 0 mut
:begin
  calc t1 = clong.highOf(parts)
  calc t2 = clong.lowOf(parts)
  calc t3 = clong.highOf(py)
  calc t4 = clong.lowOf(py)
  calc t5 = clong.getPart(parts, 16)
  calc t6 = clong.getPart(py, 16)
  machine.storeUInt64(ws + (16896), t2 & 4294967295)
  machine.storeUInt64(ws + (16896 + 8), t2 >> 32)
  machine.storeUInt64(ws + (16896 + 16), t1 & 4294967295)
  machine.storeUInt64(ws + (16896 + 24), t1 >> 32)
  machine.storeUInt64(ws + (17280), t4 & 4294967295)
  machine.storeUInt64(ws + (17280 + 8), t4 >> 32)
  machine.storeUInt64(ws + (17280 + 16), t3 & 4294967295)
  machine.storeUInt64(ws + (17280 + 24), t3 >> 32)
  calc i7 := 0
  goto head1
:head1 loop=while max=forever
  when i7 < 10 body2 done3
:body2 in=head1
  machine.storeUInt64(ws + (16384 + i7 * 8), nothing)
  calc i7 := i7 + 1
  goto head1
:done3
  calc i8 := 0
  goto head4
:head4 loop=while max=forever
  when i8 < 4 body5 done6
:body5 in=head4
  calc c9 := nothing
  calc t10 = machine.loadUInt64(ws + (16896 + i8 * 8))
  calc i11 := 0
  goto head7
:head7 loop=while max=forever in=head4
  when i11 < 4 body8 done9
:body8 in=head7
  calc t12 = machine.loadUInt64(ws + (17280 + i11 * 8))
  calc t13 = machine.loadUInt64(ws + (16384 + (i8 + i11) * 8))
  calc t14 = t10 * t12 + t13 + c9
  machine.storeUInt64(ws + (16384 + (i8 + i11) * 8), t14 & 4294967295)
  calc c9 := t14 >> 32
  calc i11 := i11 + 1
  goto head7
:done9 in=head4
  machine.storeUInt64(ws + (16384 + (i8 + 4) * 8), c9)
  calc i8 := i8 + 1
  goto head4
:done6
  calc t15 = t5 + t6
  calc t16 = clong.highOf(pz)
  calc t17 = clong.lowOf(pz)
  calc t18 = clong.getPart(pz, 16)
  machine.storeUInt64(ws + (16640), t17 & 4294967295)
  machine.storeUInt64(ws + (16640 + 8), t17 >> 32)
  machine.storeUInt64(ws + (16640 + 16), t16 & 4294967295)
  machine.storeUInt64(ws + (16640 + 24), t16 >> 32)
  calc lp19 := bitsOf(ws, 16384, 8)
  calc lz20 := bitsOf(ws, 16640, 4)
  calc t21 = t15 + lp19
  calc t22 = t18 + lz20
  calc epv23 := t15
  calc ezv24 := t18
  calc t25 = kz == 0
  when t25 yes10 no11
:yes10
  machine.storeUInt64(ws + (16640 + 0 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 1 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 2 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 3 * 8), nothing)
  calc ezv24 := t21 - far - 1
  calc lz20 := 0
  goto join12
:no11
  when t21 - t22 > far yes13 join15
:yes13
  machine.storeUInt64(ws + (16640), oneCell)
  machine.storeUInt64(ws + (16640 + 1 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 2 * 8), nothing)
  machine.storeUInt64(ws + (16640 + 3 * 8), nothing)
  calc ezv24 := t21 - far - 1
  calc lz20 := 1
  goto join15
:join15
  goto join12
:join12
  calc t26 = ezv24 + lz20
  when t26 - t21 > far && !t25 yes16 join18
:yes16
  machine.storeUInt64(ws + (16384 + 0 * 8), oneCell)
  machine.storeUInt64(ws + (16384 + 1 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 2 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 3 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 4 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 5 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 6 * 8), nothing)
  machine.storeUInt64(ws + (16384 + 7 * 8), nothing)
  calc epv23 := t26 - far - 1
  calc lp19 := 1
  goto join18
:join18
  calc t27 = epv23 < ezv24
  when t27 yes19 no20
:yes19
  calc e028 := epv23
  goto join21
:no20
  calc e028 := ezv24
  goto join21
:join21
  calc t29 = epv23 - e028
  calc t30 = ezv24 - e028
  calc i31 := 0
  goto head22
:head22 loop=while max=forever
  when i31 < 39 body23 done24
:body23 in=head22
  calc t32 = bitsAt(ws, 16384, 8, i31 * 32 - t29)
  machine.storeUInt64(ws + (16896 + i31 * 8), t32)
  calc t33 = bitsAt(ws, 16640, 4, i31 * 32 - t30)
  machine.storeUInt64(ws + (17280 + i31 * 8), t33)
  calc i31 := i31 + 1
  goto head22
:done24
  machine.storeUInt64(ws + (16896 + 39 * 8), nothing)
  machine.storeUInt64(ws + (17280 + 39 * 8), nothing)
  calc t34 = sp != sz
  calc rs35 := sp
  when t34 yes25 no26
:yes25
  calc j37 := 39
  goto head28
:head28 loop=while max=forever
  when j37 >= 0 body29 done30
:body29 in=head28
  calc t38 = machine.loadUInt64(ws + (16896 + j37 * 8))
  calc t39 = machine.loadUInt64(ws + (17280 + j37 * 8))
  when t38 > t39 yes31 join33
:yes31 in=head28
  calc cmp36 := 1
  goto done30
:join33 in=head28
  when t38 < t39 yes34 join36
:yes34 in=head28
  calc cmp36 := 0 - 1
  goto done30
:join36 in=head28
  calc j37 := j37 - 1
  goto head28
:done30
  when cmp36 < 0 yes37 join39
:yes37
  calc i40 := 0
  goto head40
:head40 loop=while max=forever
  when i40 < 40 body41 done42
:body41 in=head40
  calc t41 = machine.loadUInt64(ws + (16896 + i40 * 8))
  calc t42 = machine.loadUInt64(ws + (17280 + i40 * 8))
  machine.storeUInt64(ws + (16896 + i40 * 8), t42)
  machine.storeUInt64(ws + (17280 + i40 * 8), t41)
  calc i40 := i40 + 1
  goto head40
:done42
  calc rs35 := sz
  goto join39
:join39
  calc b43 := nothing
  calc i44 := 0
  goto head43
:head43 loop=while max=forever
  when i44 < 40 body44 done45
:body44 in=head43
  calc t45 = machine.loadUInt64(ws + (16896 + i44 * 8))
  calc t46 = machine.loadUInt64(ws + (17280 + i44 * 8))
  calc t47 = t46 + b43
  when t45 < t47 yes46 no47
:yes46 in=head43
  calc u48 := t45 + 4294967296 - t47
  calc b43 := oneCell
  goto join48
:no47 in=head43
  calc u48 := t45 - t47
  calc b43 := nothing
  goto join48
:join48 in=head43
  machine.storeUInt64(ws + (16896 + i44 * 8), u48)
  calc i44 := i44 + 1
  goto head43
:done45
  goto join27
:no26
  calc c49 := nothing
  calc i50 := 0
  goto head49
:head49 loop=while max=forever
  when i50 < 40 body50 done51
:body50 in=head49
  calc t51 = machine.loadUInt64(ws + (16896 + i50 * 8))
  calc t52 = machine.loadUInt64(ws + (17280 + i50 * 8))
  calc t53 = t51 + t52 + c49
  machine.storeUInt64(ws + (16896 + i50 * 8), t53 & 4294967295)
  calc c49 := t53 >> 32
  calc i50 := i50 + 1
  goto head49
:done51
  goto join27
:join27
  calc t54 = bitsOf(ws, 16896, 40)
  when t54 == 0 yes52 join54
:yes52
  clong.setPart(parts, 0, 0)
  clong.setPart(parts, 8, 0)
  clong.setSignificand(parts, 0, 0)
  return
:join54
  calc t55 = t54 - 128
  calc t56 = bitsAt(ws, 16896, 40, t55)
  calc t57 = bitsAt(ws, 16896, 40, t55 + 32)
  calc t58 = bitsAt(ws, 16896, 40, t55 + 64)
  calc t59 = bitsAt(ws, 16896, 40, t55 + 96)
  when t55 > 0 yes55 join57
:yes55
  calc j61 := 0
  goto head58
:head58 loop=while max=forever
  when j61 * 32 < t55 body59 done60
:body59 in=head58
  calc t62 = j61 * 32
  calc t63 = bitsAt(ws, 16896, 40, t62)
  calc t64 = t62 + 32 > t55
  when t64 yes61 no62
:yes61 in=head58
  calc m65 := t63 & ((oneCell << (t55 - t62)) - oneCell)
  goto join63
:no62 in=head58
  calc m65 := t63
  goto join63
:join63 in=head58
  when m65 != nothing yes64 join66
:yes64 in=head58
  calc sticky60 := 1
  goto done60
:join66 in=head58
  calc j61 := j61 + 1
  goto head58
:done60
  goto join57
:join57
  clong.setPart(parts, 0, rs35)
  clong.setPart(parts, 8, 1)
  clong.setPart(parts, 16, e028 + t55)
  clong.setSignificand(parts, (t59 << 32) | t58, (t57 << 32) | t56)
  clong.settleAs(parts, sticky60, layout)
  return

op bitsOf "The bit length of an array of limbs (0 for zero)"
  input ws machine.Address copied
  input base Int64 copied
  input count Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing UInt64 0
  let empty Int64 0
  let i1 Int64 0 mut
:begin
  calc i1 := count - 1
  goto head1
:head1 loop=while max=forever
  when i1 >= 0 body2 done3
:body2 in=head1
  calc t2 = machine.loadUInt64(ws + (base + i1 * 8))
  when t2 != nothing yes4 join6
:yes4 in=head1
  calc t3 = clong.bitLength(nothing, t2)
  calc t4 = i1 * 32 + t3
  return t4
:join6 in=head1
  calc i1 := i1 - 1
  goto head1
:done3
  return empty

op sinLong "sinl: the sine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant sinlIsAccurate "Gives the sine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "sinl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  sinCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op cosLong "cosl: the cosine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant coslIsAccurate "Gives the cosine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cosl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  cosCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op tanLong "tanl: the tangent of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant tanlIsAccurate "Gives the tangent correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tanl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  tanCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op asinLong "asinl: the arc sine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant asinlIsAccurate "Gives the arc sine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "asinl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  asinCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op acosLong "acosl: the arc cosine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant acoslIsAccurate "Gives the arc cosine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "acosl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  acosCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op atanLong "atanl: the arc tangent of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant atanlIsAccurate "Gives the arc tangent correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "atanl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  atanCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op expLong "expl: the e to the power x of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant explIsAccurate "Gives the e to the power x correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "expl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  expCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op exp2Long "exp2l: the 2 to the power x of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant exp2lIsAccurate "Gives the 2 to the power x correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "exp2l"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  exp2Core(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op expm1Long "expm1l: the e to the power x less 1 of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant expm1lIsAccurate "Gives the e to the power x less 1 correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "expm1l"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  expm1Core(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op logLong "logl: the natural logarithm of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant loglIsAccurate "Gives the natural logarithm correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "logl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  logCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op log2Long "log2l: the base 2 logarithm of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant log2lIsAccurate "Gives the base 2 logarithm correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "log2l"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  log2Core(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op log10Long "log10l: the base 10 logarithm of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant log10lIsAccurate "Gives the base 10 logarithm correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "log10l"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  log10Core(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op log1pLong "log1pl: the natural logarithm of 1 + x of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant log1plIsAccurate "Gives the natural logarithm of 1 + x correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "log1pl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  log1pCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op cbrtLong "cbrtl: the cube root of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant cbrtlIsAccurate "Gives the cube root correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cbrtl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  cbrtCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op sinhLong "sinhl: the hyperbolic sine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant sinhlIsAccurate "Gives the hyperbolic sine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "sinhl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  sinhCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op coshLong "coshl: the hyperbolic cosine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant coshlIsAccurate "Gives the hyperbolic cosine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "coshl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  coshCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op tanhLong "tanhl: the hyperbolic tangent of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant tanhlIsAccurate "Gives the hyperbolic tangent correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tanhl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  tanhCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op asinhLong "asinhl: the inverse hyperbolic sine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant asinhlIsAccurate "Gives the inverse hyperbolic sine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "asinhl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  asinhCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op acoshLong "acoshl: the inverse hyperbolic cosine of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant acoshlIsAccurate "Gives the inverse hyperbolic cosine correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "acoshl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  acoshCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op atanhLong "atanhl: the inverse hyperbolic tangent of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant atanhlIsAccurate "Gives the inverse hyperbolic tangent correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "atanhl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  atanhCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op erfLong "erfl: the error function of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant erflIsAccurate "Gives the error function correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "erfl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  erfCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op erfcLong "erfcl: the complementary error function of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant erfclIsAccurate "Gives the complementary error function correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "erfcl"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  erfcCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op tgammaLong "tgammal: the gamma function of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant tgammalIsAccurate "Gives the gamma function correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tgammal"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  tgammaCore(parts1, layout2)
  calc result3 = longOfParts(parts1)
  return result3

op lgammaLong "lgammal: the natural logarithm of |gamma(x)| of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)"
  invariant lgammalIsAccurate "Gives the natural logarithm of |gamma(x)| correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lgammal"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  calc sign3 = lgammaCore(parts1, layout2)
  calc result4 = longOfParts(parts1)
  return result4

op atan2Long "atan2l: the arc tangent of y / x of long doubles"
  invariant atan2lIsAccurate "Gives the arc tangent of y / x correctly rounded but for the rarest cases"
  input y machine.LongDouble copied
  input x machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "atan2l"
:begin
  calc parts1 = partsOfLong(y)
  calc other2 = partsOfLong(x)
  calc layout3 = clong.format()
  atan2Core(parts1, other2, layout3)
  heap.give(other2)
  calc result4 = longOfParts(parts1)
  return result4

op powLong "powl: the x to the power y of long doubles"
  invariant powlIsAccurate "Gives the x to the power y correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  input y machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "powl"
:begin
  calc parts1 = partsOfLong(x)
  calc other2 = partsOfLong(y)
  calc layout3 = clong.format()
  powCore(parts1, other2, layout3)
  heap.give(other2)
  calc result4 = longOfParts(parts1)
  return result4

op hypotLong "hypotl: the square root of x*x + y*y of long doubles"
  invariant hypotlIsAccurate "Gives the square root of x*x + y*y correctly rounded but for the rarest cases"
  input x machine.LongDouble copied
  input y machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "hypotl"
:begin
  calc parts1 = partsOfLong(x)
  calc other2 = partsOfLong(y)
  calc layout3 = clong.format()
  hypotCore(parts1, other2, layout3)
  heap.give(other2)
  calc result4 = longOfParts(parts1)
  return result4

op fusedMultiplyAddLong "fmal: x * y + z of long doubles with one rounding"
  invariant fmalIsExact "Gives x * y + z correctly rounded, whatever the sizes of the three"
  input x machine.LongDouble copied
  input y machine.LongDouble copied
  input z machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fmal"
:begin
  calc parts1 = partsOfLong(x)
  calc other2 = partsOfLong(y)
  calc third3 = partsOfLong(z)
  calc layout4 = clong.format()
  fmaCore(parts1, other2, third3, layout4)
  heap.give(other2)
  heap.give(third3)
  calc result5 = longOfParts(parts1)
  return result5

op logGammaSignedLong "lgammal_r: lgammal with the sign of gamma(x) stored through a pointer as an int"
  invariant lgammalrIsAccurate "Gives what lgammal gives and stores the sign of gamma(x)"
  input x machine.LongDouble copied
  input signp machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lgammal_r"
:begin
  calc parts1 = partsOfLong(x)
  calc layout2 = clong.format()
  calc sign3 = lgammaCore(parts1, layout2)
  machine.storeInt32(signp, convert.int64ToInt32(sign3))
  calc result4 = longOfParts(parts1)
  return result4

@tests

op caseTable "The address of the table of cases"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let cases String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001eaee8744b05f0000010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001aed548f090cee000011ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001d18f6ead1b446000010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc90000000000000000001210386db6d55b000010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb000000000000000000103425b78c4db8000010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000001f334c7896a4e3000010000000000000002f000000000000000000193e5939a08cea000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc5000000000000000000131c608f10776700001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001a2c16b010e385000010ffffffffffffffc200000000000000000010624dd2f1a9fc000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000000010624da5218a62000010ffffffffffffffbe00000000000000000012599ed7c6fbd2000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbe00000000000000000012599ed7869ea7000010ffffffffffffffcc0000000000000000001921fb54442d18000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000000010ffffffffffffffcd0000000000000000001921fb54442d18000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9700000000000000000011a62633145c07001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000001020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000001021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000001030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000001010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000f57743a2582f7f44001010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000d76aa47848677021001011ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000e8c7b7568da22efd001010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbe00000000000000009081c36db6aada79001010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc0000000000000000081a12dbc626dc038001010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000f99a63c4b5271a6600101000000000000000240000000000000000c9f2c9cd04674edf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000f3644284b6eceaae00101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000b5412e861ddef8ec00101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc0000000000000000090de0837a745738a001010ffffffffffffffb7000000000000000083126e978d4fdf3b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb7000000000000000083126d290c530f71001010ffffffffffffffb3000000000000000092ccf6be37de939f000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb3000000000000000092ccf6bc34f537ce001010ffffffffffffffc10000000000000000c90fdaa22168c183000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000001010ffffffffffffffc20000000000000000c90fdaa22168bde9000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8d0000000000000000897898cc51701b84002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000002020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000002021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000002030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000002010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001eaee8744b05efe8764bc364fd838002010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001aed548f090cee0418dd3d2138a1e002011ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001d18f6ead1b445dfab848188009ca002010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8d0001210386db6d55b4f1c817423418a8002010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f000103425b78c4db80708f6155d083eb002010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001f334c7896a4e34ccb3406df52112002010fffffffffffffff3000193e5939a08ce9dbd480000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8c0001711e6ba878b87f21c4544de200ef002010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001efca9749760d666d0c25320248d400201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00016d83fd6946e241dd929a03bad4bd002010ffffffffffffff8600010624dd2f1a9fbe76c8b439581062000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8600010624da5218a61ee1e64829a1fd09002010ffffffffffffff8200012599ed7c6fbd273d5bab21815a08000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8200012599ed7869ea6f9aee981525f085002010ffffffffffffff900001921fb54442d18306c8336e79acf0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001fffffffffffffffffffffffffffe002010ffffffffffffff910001921fb54442d17bd21b8d78573de5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff5c000112edbfe997f87a67344a409381ee010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000010001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000010020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000010030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000010010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001c1528065b7d50010010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000000114a280fb5068c010011ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000001aa22657537205010010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001fae04be85e5d2010010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001b981dbf665fdf010010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001bf098901c931a01001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000012699022adc4c1010010ffffffffffffffae000000000000000000112e0be826d695000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000010010ffffffffffffffcc0000000000000000001921fb54442d18000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9600000000000000000011a62633145c07011000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000011001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000011020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000011030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000011010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000e0a94032dbea7cee011010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc000000000000000008a51407da8345c92011011ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000d51132ba9b902522011010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000fd7025f42f2e9308011010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000dcc0edfb32fefb20011010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000df84c480e498cc1901101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000b4c8a3d095a9326701101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000d31143593ff9dec5011010ffffffffffffffa3000000000000000089705f4136b4a597000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000fffffffffffffff7011010ffffffffffffffc10000000000000000c90fdaa22168c183000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff890000000000000000b1c4c6628b80dc1d012000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000012001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000012020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000012030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000012010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001c1528065b7d4f9db7bbb3b45f5f6012010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f000114a280fb5068b923848cdb2ed0e3012011ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001aa22657537204a4332f8acbb72b1012010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001fae04be85e5d260fbff05fbed4e1012010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001b981dbf665fdf63f433736617a04012010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001bf098901c931983267f7c313c2a4012010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8d0001ff3b84c806473b58bc98f7f92a6d01201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001de457e6279aa1077024a8b3c7305012010ffffffffffffff72000112e0be826d694b2e62d01511f12a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001ffffffffffffffed8da22e2dbc54012010ffffffffffffff900001921fb54442d18306c8336e79acf0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff58000162c159569d54c839a252049c1114020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000020021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000020010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000000117b4f5bf3474a020010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000018eb245cbee3a6020011ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000117af62e0950f8020010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc9000000000000000000123ef71254b86f020010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000012ca74d62b5d38020010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000011de000f443f5002001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000016be411f37ac77020010ffffffffffffffae000000000000000000112e0be826d695000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffae000000000000000000112e0be826d695020010ffffffffffffffcc0000000000000000001921fb54442d1800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000010000000000000000001d02967c31cdb5021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000021021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000021010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc000000000000000008bda7adf9a3a5219021010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c75922e5f71d2dc5021011ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008bd7b1704a87c1db021010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbe000000000000000091f7b892a5c37866021010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc000000000000000009653a6b15ae9bd7d021010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc000000000000000008ef0007a21fa82f202101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc10000000000000000805558d665b191bc02101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000afb4fff78a51d56b021010ffffffffffffffa3000000000000000089705f4136b4a597000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa3000000000000000089705f4136b4a59a021010ffffffffffffffc10000000000000000c90fdaa22168c183000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffff80000000000000000b854579eb3551760022000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000022001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000022021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000022010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f000117b4f5bf3474a431796480788244022010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000018eb245cbee3a5b8acc7d41323141022011ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000117af62e0950f83b5099087aaf67b022010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8d000123ef71254b86f0ccb0b27dff8543022010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f00012ca74d62b5d37af90cd12bbc847b022010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f00011de000f443f505e3463a5beb7aef022010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001f08923483293c70f2f4ce3c0d46802201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001874ad9b103e843d7f57fb32bc5bc022010ffffffffffffff72000112e0be826d694b2e62d01511f12a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff72000112e0be826d694b34fd037cb8052f022010ffffffffffffff900001921fb54442d18306c8336e79acf0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc700017178bb5475911d8f303d620c3753030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000030010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000030011ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000030020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000030010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000010c152382d7366030011ffffffffffffffca00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca000000000000000000102be9ce0b87cd030010ffffffffffffffcb0000000000000000001ccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000011ea93705fa172030010ffffffffffffffcb0000000000000000001ff7ced916872b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000186ac9ad18f803030010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb030010ffffffffffffffcb00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001b235315c680dc030011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000010c152382d7366031000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000031001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000031010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000031011ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000031020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000031010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000860a91c16b9b2c23031011ffffffffffffffbf00000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000815f4e705c3e68f3031010ffffffffffffffc00000000000000000e666666666666666000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008f549b82fd0b8fa3031010ffffffffffffffc00000000000000000ffbe76c8b4395810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c3564d68c7c01b87031010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf031010ffffffffffffffc00000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000d91a98ae3406e041031011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000860a91c16b9b2c23032000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000032001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000032010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000032011ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000032020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000032010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00010c152382d73658465bb32e0f567b032011ffffffffffffff8e00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e000102be9ce0b87cd1e5d09da2e0f042032010ffffffffffffff8f0001cccccccccccccccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000011ea93705fa171f4745bf745646d7032010ffffffffffffff8f0001ff7ced916872b020c49ba5e353f8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000186ac9ad18f803715d6b525cd80d9032010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d786c101bfce8032010ffffffffffffff8f00018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001b235315c680dc081583db360d5e2032011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f00010c152382d73658465bb32e0f567b040010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000040010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000040021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000040010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010c152382d7366040011ffffffffffffffca00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001d2cf5c7c70f0c040010ffffffffffffffcb0000000000000000001ccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001cdd9f8f922e98040010ffffffffffffffcb0000000000000000001ff7ced916872b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc700000000000000000016e634e566a29e040011ffffffffffffffcb0000000000000000001ff7ced916872b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000018c66280ae928e040010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb543d4de0040010ffffffffffffffcb00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001720a392c1d955040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d18041010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000041010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000041021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000041010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000860a91c16b9b2c23041011ffffffffffffffbf00000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000e967ae3e38785c71041010ffffffffffffffc00000000000000000e666666666666666000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000e6ecfc7c9174ca46041010ffffffffffffffc00000000000000000ffbe76c8b4395810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbc0000000000000000b731a72b3514d5c5041011ffffffffffffffc00000000000000000ffbe76c8b4395810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c633140574946ede041010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa1ea6f0281041010ffffffffffffffc00000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000b9051c960ecaa429041000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235042010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000042010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000042021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000042010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010c152382d73658465bb32e0f567b042011ffffffffffffff8e00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001d2cf5c7c70f0b8e2fdb42dcf3dc9042010ffffffffffffff8f0001cccccccccccccccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001cdd9f8f922e994890f354302eb87042010ffffffffffffff8f0001ff7ced916872b020c49ba5e353f8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8b00016e634e566a29aa765af3e9301bee042011ffffffffffffff8f0001ff7ced916872b020c49ba5e353f8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100018c66280ae928ddbfb020f5724149042010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb543d4de05022a95da37a39d042010ffffffffffffff8f00018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001720a392c1d954851badbd6cd2d8e042000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8050000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000050001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000050020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d18050021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc0000000000000000001921fb54442d18050010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001dac670561bb4f050011ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000011b6e192ebbe44050010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001789bd2c160054050010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb543d4de0050010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb05001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d18050010fffffffffffffbe7000000000000000000156e1fc2f8f359000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbe7000000000000000000156e1fc2f8f359050010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001921fb54442d18050010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000012a73a661eaf06051000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000051001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000051020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235051021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc10000000000000000c90fdaa22168c235051010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000ed63382b0dda7b45051011ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008db70c975df22363051010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000bc4de960b0029c17051010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa1ea6f0281051010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf05101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235051010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca051010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000c90fdaa22168c235051010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf00000000000000009539d330f5782f1905101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235051010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0052000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000052001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000052020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8052021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff900001921fb54442d18469898cc51701b8052010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001dac670561bb4f68adfc88bd97875052011ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000011b6e192ebbe446c6d19aa220a39b052010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001789bd2c16005382eabf0cd4b6aae052010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb543d4de05022a95da37adc1052010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d4fdb781e2563052010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8052010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156052010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001921fb54442d18469898cc51701b8052010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00012a73a661eaf05e31ded6aab2eddf05201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8052010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d06000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006000100000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000011ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001921fb54442d1806000100000000000000000000000000000000000000000000000011ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001921fb54442d18060010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d18060011ffffffffffffffcc00000000000000000010000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc0000000000000000001921fb54442d18060020000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001921fb54442d18060020000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000012d97c7f3321d2060021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd00000000000000000012d97c7f3321d2060010ffffffffffffffcc00000000000000000010000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060011ffffffffffffffcc00000000000000000010000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000060010ffffffffffffffcc00000000000000000010000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001921fb54442d18060011ffffffffffffffcc00000000000000000010000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001921fb54442d1806002000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d1806003000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000060010ffffffffffffffcc00000000000000000010000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001921fb54442d18060010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001dac670561bb4f060011ffffffffffffffcd0000000000000000001800000000000010ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001f730bd281f69b060010ffffffffffffffcd0000000000000000001800000000000011ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001145385fa3af71060011ffffffffffffffcd0000000000000000001800000000000011ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001145385fa3af7106001000000000000003b000000000000000000017e43c8800759c10fffffffffffffbe7000000000000000000156e1fc2f8f3590000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001921fb54442d18060010fffffffffffffbe7000000000000000000156e1fc2f8f3591000000000000003b000000000000000000017e43c8800759c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060010ffffffffffffffcb0000000000000000001000000000000010ffffffffffffffcb000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001921fb54442d18060010ffffffffffffffcf0000000000000000001400000000000010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001789bd2c16005406100000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006100100000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000006100000000000000000000000000000000000000000000000000011ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c90fdaa22168c23506100100000000000000000000000000000000000000000000000011ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000c90fdaa22168c235061010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235061011ffffffffffffffc100000000000000008000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc10000000000000000c90fdaa22168c235061020000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000c90fdaa22168c235061020000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc2000000000000000096cbe3f9990e91a8061021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc2000000000000000096cbe3f9990e91a8061010ffffffffffffffc100000000000000008000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000061011ffffffffffffffc100000000000000008000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000061010ffffffffffffffc100000000000000008000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c90fdaa22168c235061011ffffffffffffffc100000000000000008000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000c90fdaa22168c23506102000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c23506103000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000061010ffffffffffffffc100000000000000008000000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000061000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000061000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c90fdaa22168c235061010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000ed63382b0dda7b45061011ffffffffffffffc20000000000000000c00000000000000010ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000fb985e940fb4d900061010ffffffffffffffc20000000000000000c00000000000000011ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008a29c2fd1d7b8bf5061011ffffffffffffffc20000000000000000c00000000000000011ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc200000000000000008a29c2fd1d7b8bf506101000000000000003a50000000000000000bf21e44003acdd2d10fffffffffffffbdc0000000000000000ab70fe17c79ac6ca0000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c90fdaa22168c235061010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca1000000000000003a50000000000000000bf21e44003acdd2d0000000000000000000000000000000000000000000000000010fffffffffffff7f70000000000000000e5a04aa62b553e99061010ffffffffffffffc00000000000000000800000000000000010ffffffffffffffc0000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000c90fdaa22168c235061010ffffffffffffffc40000000000000000a00000000000000010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000bc4de960b0029c1706200000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006200100000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000006200000000000000000000000000000000000000000000000000011ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001921fb54442d18469898cc51701b806200100000000000000000000000000000000000000000000000011ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff910001921fb54442d18469898cc51701b8062010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8062011ffffffffffffff9000010000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff900001921fb54442d18469898cc51701b8062020000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001921fb54442d18469898cc51701b8062020000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100012d97c7f3321d234f272993d1414a062021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9100012d97c7f3321d234f272993d1414a062010ffffffffffffff9000010000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000062011ffffffffffffff9000010000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000062010ffffffffffffff9000010000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001921fb54442d18469898cc51701b8062011ffffffffffffff9000010000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff910001921fb54442d18469898cc51701b806202000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b806203000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000062010ffffffffffffff9000010000000000000000000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000062000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000062000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001921fb54442d18469898cc51701b8062010ffffffffffffff900001000000000000000000000000000010ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001dac670561bb4f68adfc88bd97875062011ffffffffffffff910001800000000000000000000000000010ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001f730bd281f69b200f10f5e197794062010ffffffffffffff910001800000000000000000000000000011ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001145385fa3af717e94d48ed90a3d3062011ffffffffffffff910001800000000000000000000000000011ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff910001145385fa3af717e94d48ed90a3d3062010000000000000037400017e43c8800759ba59c08e14c7cd7b10fffffffffffffbab000156e1fc2f8f358d94db7ac61491560000000000000000000000000000000000000000000000000010ffffffffffffff900001921fb54442d18469898cc51701b8062010fffffffffffffbab000156e1fc2f8f358d94db7ac614915610000000000000037400017e43c8800759ba59c08e14c7cd7b0000000000000000000000000000000000000000000000000010fffffffffffff7c60001cb40954c56aa7d33ee99c331aca9062010ffffffffffffff8f0001000000000000000000000000000010ffffffffffffff8f000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001921fb54442d18469898cc51701b8062010ffffffffffffff930001400000000000000000000000000010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001789bd2c16005382eabf0cd4b6aae070000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000070001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000070020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000070021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000070010ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000070011ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001a61298e1e069c070011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001368b2fc6f960a070010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000015bf0a8b145769070011ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca000000000000000000178b56362cef38070010ffffffffffffffd9000000000000000000162e428f5c28f6000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000070011ffffffffffffffd9000000000000000000162d8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070011ffffffffffffffd9000000000000000000162e8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070011ffffffffffffffd900000000000000000016548000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070011ffffffffffffffd900000000000000000016550000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffda00000000000000000015829dcf950560070011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbd00000000000000000017cd79b5647c9b070010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000005c00000000000000000013494a9b171bf5070010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000006df38070011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000070010ffffffffffffffd500000000000000000015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003bd0000000000000000001d945df4f8ec8e070011ffffffffffffffd500000000000000000015e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbda000000000000000000114f2b0fb9307f070010ffffffffffffffd9000000000000000000157c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000070011ffffffffffffffd9000000000000000000157c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070010ffffffffffffffd9000000000000000000162e4000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000070011ffffffffffffffd900000000000000000016440000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000070010ffffffffffffffcb000000000000000000162e42fefa39ef000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000010000000000000071000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000071001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000071020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000071021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000071030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000071010ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000071011ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000071010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000d3094c70f034de4c071011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc000000000000000009b4597e37cb04ff4071010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000adf85458a2bb4a9b071011ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000bc5ab1b16779be35071010ffffffffffffffce0000000000000000b172147ae147ae140000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fc00000000000000000ff212516b14a9f13071011ffffffffffffffce0000000000000000b16c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbfc3000000000000000092cf78ab801959c5071011ffffffffffffffce0000000000000000b174000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbfc3000000000000000013de5ea770ff5364071011ffffffffffffffce0000000000000000b2a4000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000071011ffffffffffffffce0000000000000000b2a8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000071010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf0000000000000000ac14ee7ca82afcf8071011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb20000000000000000be6bcdab23e4d4e3071010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000005100000000000000009a4a54d8b8dfa566071010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000036f9bfb4071011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000071010ffffffffffffffca0000000000000000af0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003b20000000000000000eca2efa7c7647118071011ffffffffffffffca0000000000000000af00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbcf00000000000000008a79587dc983f856071010ffffffffffffffce0000000000000000abe00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003dbe0000000000000000c838961a26b2adda071011ffffffffffffffce0000000000000000abe0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc1c30000000000000000a3a8bc537a427c0f071010ffffffffffffffce0000000000000000b1720000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fc00000000000000000fa13dba329dd768d071011ffffffffffffffce0000000000000000b220000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000071010ffffffffffffffc00000000000000000b17217f7d1cf78fe000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000ffffffffffffff52071010ffffffffffffcbdb0000000000000000c34cd067e3060730000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000072000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000072001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000072020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000072021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000072030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000072010ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000072011ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000072010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001a61298e1e069bc972dfefab6df34072011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001368b2fc6f9609fe7aceb46aa619c072010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100015bf0a8b1457695355fb8ac404e7a072011ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e000178b56362cef37c6aeb7b1e0a4154072010ffffffffffffff9d000162e428f5c28f5c28f5c28f5c28f60000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8f0001fe424a2d62957b6135ef99195d71072011ffffffffffffff9d000162d8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf920001259ef1570032b38931df9c2dc574072011ffffffffffffff9d000162e8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf92000027bcbd4ee1fea6c8a51ed68f6082072011ffffffffffffff9d00016548000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf9200000000000000000000000000000001072011ffffffffffffff9d00016550000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000072010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9e00015829dcf95055f9f07ea8c056d135072011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8100017cd79b5647c9a9c5b24755098873072010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000002000013494a9b171bf4acc225093322428072010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001000000006df37f6776938bebf05d072011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001ffffffffffffffffa18d7bcdb6f7072010ffffffffffffff9900015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003810001d945df4f8ec8e2306724d0948dcb072011ffffffffffffff9900015e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffb9e000114f2b0fb9307f0abcb0d2b3ef3ce072010ffffffffffffff9d000157c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003d8d000190712c344d655bb4c68a4e0ad481072011ffffffffffffff9d000157c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc1920001475178a6f484f81d779d989fa7d2072010ffffffffffffff9d000162e40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8f0001f427b74653baed1967480b308def072011ffffffffffffff9d00016440000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf92000000000000000000009b0b43706715072010ffffffffffffff8f000162e42fefa39ef1fc248947fd2745000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001fffffffffffffea490c1e0cd1f60072010ffffffffffffcbaa00018699a0cfc60c0e605bcff8560acc000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000080020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000080021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080010ffffffffffffffdb00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000080011ffffffffffffffdb00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000016a09e667f3bcd080011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000016a09e667f3bcd080010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000010000000000000080010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd600000000000000000010000000000000080011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000000010000000000000080010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000003000000000000000000010000000000000080010ffffffffffffffc80000000000000000001999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001125fbee250664080010ffffffffffffffd90000000000000000001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000080011ffffffffffffffd90000000000000000001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080011ffffffffffffffda00000000000000000010108000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080010ffffffffffffffd90000000000000000001ffffeb851eb85000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000080010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000004c366081000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000081020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000081021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000081010ffffffffffffffd000000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000081011ffffffffffffffd000000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000081010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000b504f333f9de6484081011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000b504f333f9de6484081010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008000000000000000081010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000008000000000000000081011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb700000000000000008000000000000000081010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000002500000000000000008000000000000000081010ffffffffffffffbd0000000000000000cccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000892fdf7128332131081010ffffffffffffffce0000000000000000fa000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003e4100000000000000008000000000000000081011ffffffffffffffce0000000000000000fa00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc14100000000000000008000000000000000081011ffffffffffffffcf00000000000000008084000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000081010ffffffffffffffce0000000000000000fffff5c28f5c28f60000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fc00000000000000000fe3b4f4dce1af8bd081010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000261b2de8082000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000082020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000082021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000082010ffffffffffffff9f00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000082011ffffffffffffff9f00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000082010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000016a09e667f3bcc908b2fb1366ea95082011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00016a09e667f3bcc908b2fb1366ea95082010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100010000000000000000000000000000082010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9a00010000000000000000000000000000082011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8600010000000000000000000000000000082010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffff400010000000000000000000000000000082010ffffffffffffff8c0001999999999999999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001125fbee250664262aa4cabd0b132082010ffffffffffffff9d0001f4000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003e1000010000000000000000000000000000082011ffffffffffffff9d0001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc11000010000000000000000000000000000082011ffffffffffffff9e00010108000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf9200000000000000000000100000000000082010ffffffffffffff9d0001ffffeb851eb851eb851eb851eb850000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8f0001fc769e9b9c35dc548aa37f2b1f51082010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001000000004c365bd0908848ce7456090000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000090001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000090020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000090021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000090010ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000090011ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000090010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000014c2531c3c0d38090011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca000000000000000000192e9a0720d3ec090010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001b7e151628aed3090011ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb000000000000000000143a54e4e98864090010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffda00000000000000000015825dcf950560090010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9dda4e3090011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c924223090010fffffffffffffbe7000000000000000000156e1fc2f8f359000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbe7000000000000000000156e1fc2f8f359090010ffffffffffffffd500000000000000000015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003bd0000000000000000001d945df4f8ec8e090011ffffffffffffffd500000000000000000015e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000090010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000016641632306a56090011ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca00000000000000000010966f2c7907f6091000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000091001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000091020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000091021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000091010ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000091011ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000091010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000a61298e1e069bc97091011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000c974d039069f6018091010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000dbf0a8b145769535091011ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000a1d2a7274c4320e5091010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf0000000000000000ac12ee7ca82afcf8091010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6feceed2717d8091011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb091010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca091010ffffffffffffffca0000000000000000af0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003b20000000000000000eca2efa7c7647118091011ffffffffffffffca0000000000000000af00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000091010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000b320b1918352b48c091011ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf000000000000000084b37963c83fb172091010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0092000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000092001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000092020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000092021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000092010ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000092011ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000092010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00014c2531c3c0d3792e5bfdf56dbe68092011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e000192e9a0720d3ec030a62972ab3cc9092010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001b7e151628aed2a6abf7158809cf5092011ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f000143a54e4e988641ca8a4270fadf56092010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9e00015825dcf95055f9f07ea8c056d135092010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9dda4e2fafc1749d9142d6092011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d4ef1129ea5ecb092010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156092010ffffffffffffff9900015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003810001d945df4f8ec8e2306724d0948dcb092011ffffffffffffff9900015e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000092010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00016641632306a56916ea9f851e4da3092011ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e00010966f2c7907f62e41a5929d1a070092010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d0a0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a0011ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000a00210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a0010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb000000000000000000162e42fefa39ef0a0010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000000162e42fefa39ef0a0010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000126bb1bbb555160a0010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd000000000000000000017069e2aa2aa5b0a0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd000000000000000000017069e2aa2aa5b0a0010ffffffffffffffcc0000000000000000001000001ad7f29b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb40000000000000000001ad7f2847b64920a0010ffffffffffffffcb0000000000000000001fffffca501acb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffb40000000000000000001ad7f2b1049b9f0a0010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001193ea7aad030b0a0010ffffffffffffffcb00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000001269621134db920a1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a10010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a1011ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000a10210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a1010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000b17217f7d1cf79ac0a1010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000b17217f7d1cf79ac0a1010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000935d8dddaaa8ac170a1010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc50000000000000000b834f1551552d71d0a1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc50000000000000000b834f1551552d71d0a1010ffffffffffffffc10000000000000000800000d6bf94d5e5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa90000000000000000d6bf9421c02494740a1010ffffffffffffffc00000000000000000fffffe5280d65435000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffa90000000000000000d6bf958a0a5cfe860a101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce00000000000000008fe95c8a78a8b80e0a1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffce00000000000000008fe95c8a78a8b80e0a1010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008c9f53d5681854bb0a1010ffffffffffffffc00000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000934b1089a6dc93c20a2010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a20010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000a2011ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000a20210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000a2010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f000162e42fefa39ef35793c7673007e60a2010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f000162e42fefa39ef35793c7673007e60a2010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000126bb1bbb5551582dd4adac5705a60a2010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9400017069e2aa2aa5ae3949d9176cc7100a2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9400017069e2aa2aa5ae3949d9176cc7100a2010ffffffffffffff900001000001ad7f29abcaf485787a6521000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff780001ad7f2843813dae5f6a3b2a8bafa80a2010ffffffffffffff8f0001fffffca501aca86a16f50f0b35be000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff780001ad7f2b1414ae8284e19186b18bc80a201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00011fd2b914f151701cc1b19a4cfb840a2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9d00011fd2b914f151701cc1b19a4cfb840a2010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001193ea7aad030a976a4198d55053b0a2010ffffffffffffff8f00018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001269621134db92783beb7676c0aaa0b0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000b0010ffffffffffffffcf00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000180000000000000b0010ffffffffffffffca00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd000000000000000000100000000000000b0011ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000b00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000b0010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc000000000000000000100000000000000b0010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000195c01a39fbd680b0010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001a934f0979a3710b0010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd1000000000000000000109c1165ec06270b0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd1000000000000000000109c1165ec06270b0010ffffffffffffffcc0000000000000000001000001ad7f29b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb5000000000000000000135d0fea5fccb70b1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000b1010ffffffffffffffc400000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c0000000000000000b1010ffffffffffffffbf00000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc2000000000000000080000000000000000b1011ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000b10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000b1010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc1000000000000000080000000000000000b1010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000cae00d1cfdeb43d00b1010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000d49a784bcd1b8afe0b1010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc6000000000000000084e08b2f603136df0b1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc6000000000000000084e08b2f603136df0b1010ffffffffffffffc10000000000000000800000d6bf94d5e5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa00000000000000009ae87f51799752120b101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000cf9ed97a064ce5bc0b1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffce0000000000000000cf9ed97a064ce5bc0b2010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000b2010ffffffffffffff9300010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000180000000000000000000000000000b2010ffffffffffffff8e00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff91000100000000000000000000000000000b2011ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000b20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000b2010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff90000100000000000000000000000000000b2010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000195c01a39fbd6879fa00b120a068c0b2010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001a934f0979a3715fc9257edfe9b600b2010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff95000109c1165ec0626dbddb76f4bf211c0b2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff95000109c1165ec0626dbddb76f4bf211c0b2010ffffffffffffff900001000001ad7f29abcaf485787a6521000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff79000135d0fea2f3df06aa5b94ffc2a4b60b201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00019f3db2f40c99cb78a6e9de6aa3bb0b2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9d00019f3db2f40c99cb78a6e9de6aa3bb0c0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000c0010ffffffffffffffd50000000000000000001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000180000000000000c0011ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000c00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000c0010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca000000000000000000134413509f79ff0c0010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001e8927964fd5fd0c0010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000100000000000000c0010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf000000000000000000140000000000000c0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcf000000000000000000140000000000000c0010ffffffffffffffcc0000000000000000001000001ad7f29b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb30000000000000000001750e5ca0b10980c1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000c10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000c1010ffffffffffffffca0000000000000000fa00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c0000000000000000c1011ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000c10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000c1010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf00000000000000009a209a84fbcff7990c1010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000f4493cb27eafe8460c1010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc2000000000000000080000000000000000c1010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000a0000000000000000c1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc40000000000000000a0000000000000000c1010ffffffffffffffc10000000000000000800000d6bf94d5e5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa80000000000000000ba872e4e8459602e0c101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000fa000000000000000c1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc0000000000000000fa000000000000000c2010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000c20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000c2010ffffffffffffff990001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000180000000000000000000000000000c2011ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000c20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000c2010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e000134413509f79fef311f12b35816f90c2010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001e8927964fd5fd08c30343a821a240c2010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000100000000000000000000000000000c2010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff93000140000000000000000000000000000c2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff93000140000000000000000000000000000c2010ffffffffffffff900001000001ad7f29abcaf485787a6521000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff770001750e5c9d098723d457807be2f78a0c201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9b0001f4000000000000000000000000000c2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9b0001f4000000000000000000000000000d00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000d00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000d0011ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000d0011ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000d00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000d0010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000019f323ecbf984c0d0011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb000000000000000000162e42fefa39ef0d0010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000000162e42fefa39ef0d0011ffffffffffffffcb0000000000000000001ff7ced916872b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffce0000000000000000001ba18a998fff9f0d0010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000132ee3b77f374c0d0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d1d6930d0011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c9242230d0010fffffffffffffbe7000000000000000000156e1fc2f8f359000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbe7000000000000000000156e1fc2f8f3590d0010ffffffffffffffc80000000000000000001999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc800000000000000000018663f793c46c70d0011ffffffffffffffc80000000000000000001999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc80000000000000000001af8e8210a415e0d10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000d10010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000d1011ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000d1011ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000d10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000d1010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000cf991f65fcc25f960d1011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000b17217f7d1cf79ac0d1010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000b17217f7d1cf79ac0d1011ffffffffffffffc00000000000000000ffbe76c8b4395810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc30000000000000000dd0c54cc7ffd01f20d1010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc2000000000000000099771dbbf9ba5dbe0d1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fece8eb493a60d1011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb0d1010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca0d101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce00000000000000008fe95c8a78a8b80e0d1010ffffffffffffffbd0000000000000000cccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbd0000000000000000c331fbc9e23634df0d1011ffffffffffffffbd0000000000000000cccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbd0000000000000000d7c74108520aeb730d1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c00d20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000d20010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000d2011ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000d2011ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000d20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000d2010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00019f323ecbf984bf2b68d766f405220d2011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f000162e42fefa39ef35793c7673007e60d2010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f000162e42fefa39ef35793c7673007e60d2011ffffffffffffff8f0001ff7ced916872b020c49ba5e353f8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff920001ba18a998fffa0444bf04828288910d2010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000132ee3b77f374bb7bc5cbfcca7ed30d2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d1d69274b3ce90aa5f78f0d2011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d534c1c2883c290d2010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbab000156e1fc2f8f358d94db7ac61491560d201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00011fd2b914f151701cc1b19a4cfb840d2010ffffffffffffff8c0001999999999999999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8c00018663f793c46c69be23ca0e6f259d0d2011ffffffffffffff8c0001999999999999999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8c0001af8e8210a415d6e61283e0400d530d2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d0e0010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000e0030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000e0010ffffffffffffffcc00000000000000000010000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000e0011ffffffffffffffcc00000000000000000010000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000e0011ffffffffffffffcc00000000000000000010000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000e000000000000000000000000000000000000000000000000000011ffffffffffffffcc0000000000000000001000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e000100000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001800000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e000100000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001800000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e000100000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcb000000000000000000100000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e0010ffffffffffffffcb000000000000000000100000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcd000000000000000000100000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcd000000000000000000100000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e002100000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001800000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e002100000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001800000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e002100000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e002000000000000000000000000000000000000000000000000011ffffffffffffffcc0000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e002000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0011ffffffffffffffcf0000000000000000001000000000000010ffffffffffffffcb0000000000000000001000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e0011ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcd000000000000000000180000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcf000000000000000000100000000000000e0011ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffce000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd0000000000000000000100000000000000e0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcf000000000000000000140000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd6000000000000000000100000000000000e0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffdc000000000000000000186a000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcd0000000000000000001000000000000011ffffffffffffffdc000000000000000000186a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e003000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcb000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000016a09e667f3bcd0e0010ffffffffffffffcf0000000000000000001400000000000011ffffffffffffffcd000000000000000000180000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000000010624dd2f1a9fc0e0010ffffffffffffffcc0000000000000000001800000000000010ffffffffffffffd20000000000000000001900000000000000000000000000000000000000000000000000000000000000100000000000000006000000000000000000169194f299cdda0e0010ffffffffffffffcb0000000000000000001000000000000010ffffffffffffffd00000000000000000001e8000000000000000000000000000000000000000000000000000000000000010ffffffffffffffad00000000000000000016a09e667f3bcd0e0010ffffffffffffffcd0000000000000000001800000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb0000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000078cb30e0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffd90000000000000000001fff800000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcd0000000000000000001000000000000011ffffffffffffffda000000000000000000100f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e0010ffffffffffffffcf0000000000000000001400000000000010ffffffffffffffd70000000000000000001f40000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e0010ffffffffffffffcb0000000000000000001000000000000011ffffffffffffffd50000000000000000001f400000000000000000000000000000000000000000000000000000000000001000000000000003b4000000000000000000100000000000000e0010ffffffffffffffce0000000000000000001c00000000000010ffffffffffffffce0000000000000000001c0000000000000000000000000000000000000000000000000000000000000010ffffffffffffffdf0000000000000000001921ee000000000e0010ffffffffffffffcc0000000000000000001000001ad7f29b10ffffffffffffffe90000000000000000001dcd65000000000000000000000000000000000000000000000000000000000010000000000000005c0000000000000000001349445c2287920e0010ffffffffffffffd20000000000000000001900000000000010ffffffffffffffc200000000000000000010624dd2f1a9fc0000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001012e801c4a7890e1010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000e1030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000e1010ffffffffffffffc100000000000000008000000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000e1011ffffffffffffffc100000000000000008000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000e1011ffffffffffffffc100000000000000008000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000e100000000000000000000000000000000000000000000000000011ffffffffffffffc10000000000000000800000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e100100000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000c00000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e100100000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c00000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e100000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e100100000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000800000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e1010ffffffffffffffc0000000000000000080000000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e1010ffffffffffffffc0000000000000000080000000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e1010ffffffffffffffc2000000000000000080000000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e1010ffffffffffffffc2000000000000000080000000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e102100000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c00000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e102100000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000c00000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e102100000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000800000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e102000000000000000000000000000000000000000000000000011ffffffffffffffc10000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e102000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000800000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e1011ffffffffffffffc40000000000000000800000000000000010ffffffffffffffc00000000000000000800000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e1011ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc20000000000000000c0000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc4000000000000000080000000000000000e1011ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc3000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc5000000000000000080000000000000000e1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc40000000000000000a0000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000080000000000000000e1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffd10000000000000000c35000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e1010ffffffffffffffc20000000000000000800000000000000011ffffffffffffffd10000000000000000c35000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e103000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc0000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000b504f333f9de64840e1010ffffffffffffffc40000000000000000a00000000000000011ffffffffffffffc20000000000000000c0000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb7000000000000000083126e978d4fdf3b0e1010ffffffffffffffc10000000000000000c00000000000000010ffffffffffffffc70000000000000000c8000000000000000000000000000000000000000000000000000000000000000010fffffffffffffffb0000000000000000b48ca794ce6ed0ad0e1010ffffffffffffffc00000000000000000800000000000000010ffffffffffffffc50000000000000000f4000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa20000000000000000b504f333f9de64840e1010ffffffffffffffc20000000000000000c00000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf0000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000003c6597ea0e1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffce0000000000000000fffc00000000000000000000000000000000000000000000000000000000000000100000000000003fc0000000000000000080000000000000000e1010ffffffffffffffc20000000000000000800000000000000011ffffffffffffffcf0000000000000000807a0000000000000000000000000000000000000000000000000000000000000010ffffffffffffbfc3000000000000000000000000000000010e1010ffffffffffffffc40000000000000000a00000000000000010ffffffffffffffcc0000000000000000fa00000000000000000000000000000000000000000000000000000000000000001000000000000033a80000000000000000d1ba8323fe558c610e1010ffffffffffffffc00000000000000000800000000000000011ffffffffffffffca0000000000000000fa00000000000000000000000000000000000000000000000000000000000000001000000000000003a9000000000000000080000000000000000e1010ffffffffffffffc30000000000000000e00000000000000010ffffffffffffffc30000000000000000e0000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd40000000000000000c90f7000000000000e1010ffffffffffffffc10000000000000000800000d6bf94d5e510ffffffffffffffde0000000000000000ee6b2800000000000000000000000000000000000000000000000000000000000010000000000000005100000000000000009a4a2249cedffbb60e1010ffffffffffffffc70000000000000000c80000000000000010ffffffffffffffb7000000000000000083126e978d4fdf3b0000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008097400e253c45c50e2010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000e2030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000e2010ffffffffffffff9000010000000000000000000000000000300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000e2011ffffffffffffff9000010000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000e2011ffffffffffffff9000010000000000000000000000000000210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000e200000000000000000000000000000000000000000000000000011ffffffffffffff900001000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e200100000000000000000000000000000000000000000000000011ffffffffffffff910001800000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e200100000000000000000000000000000000000000000000000010ffffffffffffff910001800000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e200000000000000000000000000000000000000000000000000010ffffffffffffff910001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e200100000000000000000000000000000000000000000000000011ffffffffffffff910001000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e2010ffffffffffffff8f000100000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e2010ffffffffffffff8f000100000000000000000000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e2010ffffffffffffff91000100000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e2010ffffffffffffff91000100000000000000000000000000002100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e202100000000000000000000000000000000000000000000000010ffffffffffffff910001800000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000e202100000000000000000000000000000000000000000000000011ffffffffffffff910001800000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000e202100000000000000000000000000000000000000000000000010ffffffffffffff910001000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e202000000000000000000000000000000000000000000000000011ffffffffffffff900001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e202000000000000000000000000000000000000000000000000010ffffffffffffff910001000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e2011ffffffffffffff930001000000000000000000000000000010ffffffffffffff8f0001000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e2011ffffffffffffff910001000000000000000000000000000010ffffffffffffff91000180000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff93000100000000000000000000000000000e2011ffffffffffffff910001000000000000000000000000000010ffffffffffffff92000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff94000100000000000000000000000000000e2010ffffffffffffff910001000000000000000000000000000010ffffffffffffff93000140000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9a000100000000000000000000000000000e2010ffffffffffffff910001000000000000000000000000000010ffffffffffffffa0000186a000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000e2010ffffffffffffff910001000000000000000000000000000011ffffffffffffffa0000186a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e203000000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000e2010ffffffffffffff910001000000000000000000000000000010ffffffffffffff8f000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000016a09e667f3bcc908b2fb1366ea950e2010ffffffffffffff930001400000000000000000000000000011ffffffffffffff91000180000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8600010624dd2f1a9fbe76c8b4395810620e2010ffffffffffffff900001800000000000000000000000000010ffffffffffffff96000190000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca000169194f299cdda1596d07ddd75a520e2010ffffffffffffff8f0001000000000000000000000000000010ffffffffffffff940001e8000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff7100016a09e667f3bcc908b2fb1366ea950e2010ffffffffffffff910001800000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb5110000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000078cb2fd4a3ff5e36da390e2010ffffffffffffff910001000000000000000000000000000010ffffffffffffff9d0001fff800000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8f000100000000000000000000000000000e2010ffffffffffffff910001000000000000000000000000000011ffffffffffffff9e000100f40000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffbf92000000000000000000020000000000000e2010ffffffffffffff930001400000000000000000000000000010ffffffffffffff9b0001f400000000000000000000000000000000000000000000000000000000000000000000000000001000000000000033770001a3750647fcab18c21ab905450cc30e2010ffffffffffffff8f0001000000000000000000000000000011ffffffffffffff990001f40000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000378000100000000000000000000000000000e2010ffffffffffffff920001c00000000000000000000000000010ffffffffffffff920001c0000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa30001921ee000000000000000000000000e2010ffffffffffffff900001000001ad7f29abcaf485787a652110ffffffffffffffad0001dcd650000000000000000000000000000000000000000000000000000000000000000000000000100000000000000020000134944493e26003da4fc710859fab0e2010ffffffffffffff960001900000000000000000000000000010ffffffffffffff8600010624dd2f1a9fbe76c8b4395810620000000000000000000000000000000000000000000000000010ffffffffffffff900001012e801c4a788b8a8e6053fe25700f00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000f00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000f00210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000f0010ffffffffffffffd00000000000000000001b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000180000000000000f0011ffffffffffffffcf00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd000000000000000000100000000000000f00300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000f0010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001428a2f98d728b0f0010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd000000000000000000113c484138704f0f0011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd000000000000000000113c484138704f0f0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000001e6b4b396428e80f001000000000000003b000000000000000000017e43c8800759c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000001180000000000000000001249ad2594c37d0f0010ffffffffffffffc200000000000000000010624dd2f1a9fc000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc80000000000000000001999999999999a0f0010ffffffffffffffd50000000000000000001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf000000000000000000140000000000000f0010ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000017137449123ef60f10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f10010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000f10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000f10210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000f1010ffffffffffffffc50000000000000000d800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000c0000000000000000f1011ffffffffffffffc400000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc2000000000000000080000000000000000f10300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000f1010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000a14517cc6b9457110f1010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc2000000000000000089e24209c38276540f1011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc2000000000000000089e24209c38276540f1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb50000000000000000f35a59cb21473f410f101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000010d0000000000000000924d692ca61be7580f101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000110e000000000000000096e6b0cdaffba1cd0f1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffee730000000000000000d926178fa72f3ef00f1010ffffffffffffffb7000000000000000083126e978d4fdf3b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbd0000000000000000cccccccccccccccd0f1010ffffffffffffffca0000000000000000fa00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000a0000000000000000f1010ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000b89ba24891f7b2e70f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f20010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000f20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000f20210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000000f2010ffffffffffffff940001b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000180000000000000000000000000000f2011ffffffffffffff9300010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff91000100000000000000000000000000000f20300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000000f2010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001428a2f98d728ae223ddab715be250f2010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff91000113c484138704eca8a22d724dea090f2011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff91000113c484138704eca8a22d724dea090f2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff840001e6b4b396428e7e82628ac5a779610f2010000000000000037400017e43c8800759ba59c08e14c7cd7b00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000dc0001249ad2594c37ceb0b2784c4ce0bf0f201000000000000033770001a3750647fcab18c21ab905450cc300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000010dd00012dcd619b5ff7439a0cdbb26b82080f2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffee420001b24c2f1f4e5e7de1067db8d5dbf50f2010ffffffffffffff8600010624dd2f1a9fbe76c8b439581062000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8c000199999999999999999999999999990f2010ffffffffffffff990001f400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff93000140000000000000000000000000000f2010ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000017137449123ef65cdde7f16c56e32100010ffffffffffffffcd0000000000000000001800000000000010ffffffffffffffce000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000001400000000000010002000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010003000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010003000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000100010ffffffffffffffce0000000000000000001400000000000010ffffffffffffffcf000000000000000000180000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf0000000000000000001a000000000000100010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000016a09e667f3bcd10001000000000000003b000000000000000000017e43c8800759c1000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000001000000000000003b100000000000000000010e4d50f99b211100010fffffffffffffbe7000000000000000000156e1fc2f8f35910fffffffffffffbe7000000000000000000156e1fc2f8f3590000000000000000000000000000000000000000000000000010fffffffffffffbe70000000000000000001e4e8d12762225100010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffff6800000000000000000014484bfeebc2a00000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000100010ffffffffffffff6800000000000000000014484bfeebc2a010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000100010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcd000000000000000000180000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001cd82b446159f3101010ffffffffffffffc20000000000000000c00000000000000010ffffffffffffffc3000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc30000000000000000a00000000000000010102000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010103000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010103000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000101010ffffffffffffffc30000000000000000a00000000000000010ffffffffffffffc40000000000000000c0000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000d000000000000000101010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000b504f333f9de648410101000000000000003a50000000000000000bf21e44003acdd2d1000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000001000000000000003a600000000000000008726a87ccd9084c4101010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca10fffffffffffffbdc0000000000000000ab70fe17c79ac6ca0000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000f2746893b111293e10101000000000000033aa00000000000000009d4be25afec029491000000000000033aa0000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000001000000000000033ab0000000000000000831491f67ef577bd1010100000000000003fc00000000000000000ecb12aed7f5875e1100000000000003fc00000000000000000ecb12aed7f5875e100000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001010100000000000003fbd0000000000000000ac23c22116cbf8a4100000000000003fbd0000000000000000ac23c22116cbf8a400000000000000000000000000000000000000000000000000100000000000003fbd0000000000000000f37138b2a417f345101010ffffffffffffffc10000000000000000800000000000000010ffffffffffffff5d0000000000000000a2425ff75e14fc320000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000101010ffffffffffffff5d0000000000000000a2425ff75e14fc3210ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000101010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc20000000000000000c0000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000e6c15a230acf9b08102010ffffffffffffff910001800000000000000000000000000010ffffffffffffff92000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff920001400000000000000000000000000010202000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010203000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010203000000000000000000000000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000102010ffffffffffffff920001400000000000000000000000000010ffffffffffffff93000180000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff930001a000000000000000000000000000102010ffffffffffffff900001000000000000000000000000000010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000016a09e667f3bcc908b2fb1366ea95102010000000000000037400017e43c8800759ba59c08e14c7cd7b10000000000000037400017e43c8800759ba59c08e14c7cd7b0000000000000000000000000000000000000000000000000010000000000000037500010e4d50f99b2109888261d8f13685102010fffffffffffffbab000156e1fc2f8f358d94db7ac614915610fffffffffffffbab000156e1fc2f8f358d94db7ac61491560000000000000000000000000000000000000000000000000010fffffffffffffbab0001e4e8d1276222527ca1feac0c663f102010000000000000337900013a97c4b5fd805291940ac3f3c9921000000000000033790001a3750647fcab18c21ab905450cc30000000000000000000000000000000000000000000000000010000000000000337a0001062923ecfdeaef7950b3a34b27fa1020100000000000003f8f0001d96255dafeb0ebc2cb70adcb8634100000000000003f8f0001d96255dafeb0ebc2cb70adcb863400000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001020100000000000003f8c0001584784422d97f147d9c64fd9d5f7100000000000003f8c0001584784422d97f147d9c64fd9d5f700000000000000000000000000000000000000000000000000100000000000003f8c0001e6e27165482fe689bc09e61a26cc102010ffffffffffffff900001000000000000000000000000000010ffffffffffffff2c00014484bfeebc29f863424b06f3529a0000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000102010ffffffffffffff2c00014484bfeebc29f863424b06f3529a10ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000102010ffffffffffffff910001000000000000000000000000000010ffffffffffffff91000180000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001cd82b446159f360fedeccf37f9e5110000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000110001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000110020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000110021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000110010ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000110011ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000110010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000010acd00fe63b97110011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000010acd00fe63b97110010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000012cd9fc44eb982110010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd900000000000000000015829dced69992110011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd900000000000000000015829dced69992110010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb110011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c924223110010ffffffffffffffd500000000000000000015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003bc0000000000000000001d945df4f8ec8e110010ffffffffffffffd9000000000000000000157c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000110010ffffffffffffffd9000000000000000000162e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000110010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca000000000000000000137d42af54b926110010fffffffffffffbe7000000000000000000156e1fc2f8f359000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbe7000000000000000000156e1fc2f8f359111000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000111001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000111020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000111021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000111010ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000111011ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000111010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc000000000000000008566807f31dcb652111011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc000000000000000008566807f31dcb652111010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000966cfe2275cc12d4111010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000ac14ee76b4cc8f9f111011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffce0000000000000000ac14ee76b4cc8f9f111010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf111011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb111010ffffffffffffffca0000000000000000af0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003b10000000000000000eca2efa7c7647118111010ffffffffffffffce0000000000000000abe00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003dbd0000000000000000c838961a26b2adda111010ffffffffffffffce0000000000000000b1700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fbf000000000000000097ae01b5ed4a38fc111010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf00000000000000009bea157aa5c932ff111010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca111010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0112000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000112001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000112020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000112021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000112010ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000112011ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000112010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00010acd00fe63b96ca357895761ae66112011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f00010acd00fe63b96ca357895761ae66112010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000012cd9fc44eb9825a80249487f0650112010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00015829dced69991f3e405b72293efa112011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9d00015829dced69991f3e405b72293efa112010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d786c101bfce8112011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d511e976394d7a112010ffffffffffffff9900015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003800001d945df4f8ec8e2306724d0948dcb112010ffffffffffffff9d000157c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003d8c000190712c344d655bb4c68a4e0ad481112010ffffffffffffff9d000162e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8e00012f5c036bda9471f881247e0e3df7112010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e000137d42af54b9265fd827c5777f709112010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156112010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d120000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000120020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000120021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000120010ffffffffffffffda00000000000000000013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000120010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000120ac1862ae8d0120011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000120ac1862ae8d0120010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000018b07551d9f550120010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd900000000000000000015829dd053712d120011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd900000000000000000015829dd053712d120010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000120010ffffffffffffffd500000000000000000015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003bc0000000000000000001d945df4f8ec8e120010ffffffffffffffd9000000000000000000157c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000120010ffffffffffffffd9000000000000000000162e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000121000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000121020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000121021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000121010ffffffffffffffcf00000000000000009c40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000121010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000090560c3157468323121011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000090560c3157468323121010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c583aa8ecfaa8261121010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000ac14ee829b896a51121011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000ac14ee829b896a51121010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000121010ffffffffffffffca0000000000000000af0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003b10000000000000000eca2efa7c7647118121010ffffffffffffffce0000000000000000abe00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003dbd0000000000000000c838961a26b2adda121010ffffffffffffffce0000000000000000b1700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fbf000000000000000097ae01b5ed4a38fc121010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000122000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000122020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000122021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000122010ffffffffffffff9e00013880000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000122010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000120ac1862ae8d0645823a4f060801122011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000120ac1862ae8d0645823a4f060801122010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000018b07551d9f5504c2bd28100196a5122010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00015829dd053712d4a2bcf60e84636f122011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00015829dd053712d4a2bcf60e84636f122010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000179ca10c9242122010ffffffffffffff9900015e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003800001d945df4f8ec8e2306724d0948dcb122010ffffffffffffff9d000157c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003d8c000190712c344d655bb4c68a4e0ad481122010ffffffffffffff9d000162e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8e00012f5c036bda9471f881247e0e3df7122010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000130000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000130001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000130020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000130021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000130010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000130011ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000130010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001d9353d7568af3130011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000001d9353d7568af3130010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb000000000000000000185efab514f394130010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001ffffffdc96f35130011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001ffffffdc96f35130010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb130011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c924223130010ffffffffffffffd00000000000000000001e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000130010fffffffffffffbe7000000000000000000156e1fc2f8f359000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbe7000000000000000000156e1fc2f8f359130010ffffffffffffffd10000000000000000001f800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000130010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000012a4dda7d914fa131000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000131001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000131020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000131021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000131010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000131011ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000131010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000ec9a9ebab4579b29131011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000ec9a9ebab4579b29131010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000c2f7d5a8a79ca2ac131010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000ffffffee4b79aaa9131011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000ffffffee4b79aaa9131010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf131011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb131010ffffffffffffffc50000000000000000f000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000131010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca131010ffffffffffffffc60000000000000000fc00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000131010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf00000000000000009526ed3ec8a7d089131010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0132000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000132001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000132020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000132021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000132010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000132011ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000132010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001d9353d7568af365128ee21c65b09132011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001d9353d7568af365128ee21c65b09132010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f000185efab514f394558632be293c427132010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001ffffffdc96f355529456c2d12d13132011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001ffffffdc96f355529456c2d12d13132010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d4fdb781e2563132011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d511e976394d7a132010ffffffffffffff940001e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001fffffffffffffffffffff528f373132010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffbab000156e1fc2f8f358d94db7ac6149156132010ffffffffffffff950001f800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000132010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00012a4dda7d914fa110ff29b470ba63132010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d140000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000140001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000140020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000140021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000140010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001ecc2caec5160a140011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000001ecc2caec5160a140010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001c34366179d427140010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000017fc5c506d2bdb140011ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd00000000000000000017fc5c506d2bdb140010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb140011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c92422314001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd5000000000000000000159bbfd8b83e44140010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000012ec4ea565fcc1141000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000141001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000141020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000141021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000141010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000f661657628b04ca6141011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbf0000000000000000f661657628b04ca6141010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000e1a1b30bcea13661141010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000bfe2e283695ed6a9141011ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000bfe2e283695ed6a9141010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf141011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb14101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000acddfec5c1f21d8914101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce00000000000000008fec2252d887ff4c141010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf00000000000000009762752b2fe60796141010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0142000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000142001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000142020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000142021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000142010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001ecc2caec5160994be04204a968c7142011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8e0001ecc2caec5160994be04204a968c7142010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001c34366179d426cc1b1f33d1ba4a3142010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100017fc5c506d2bdad51c1caf4838b87142011ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9100017fc5c506d2bdad51c1caf4838b87142010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d5d61001d6d3a142011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d511e976394d7a142010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff99000159bbfd8b83e43b128b2077cfc6a114201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00011fd844a5b10ffe988f0fe96a9844142010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00012ec4ea565fcc0f2b4710d5ae5b1f142010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d150010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000150010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000150011ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000150020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000150021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000150000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000150010ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001ecc2caec5160a150010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000015124271980435150010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000017f21ed1ce05d4150010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd000000000000000000017b810429a7c2a150010ffffffffffffffcc0000000000000000001000001ad7f29b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000001d4effc065cae4150010ffffffffffffffcc00000000000000000010000000000005000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb3000000000000000000194c583ada5b5215001000000000000003b000000000000000000017e43c8800759c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd5000000000000000000159bbfd8b83e44151010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000151010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000151011ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000151020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000151021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000151000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000151010ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000f661657628b04ca6151010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000a892138cc021a4df151010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000bf90f68e702ea1fe151010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc50000000000000000bdc08214d3e152ea151010ffffffffffffffc10000000000000000800000d6bf94d5e5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb50000000000000000ea77fe0208179a2b151010ffffffffffffffc100000000000000008000000000002407000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa80000000000000000c012a9c275636db415101000000000000003a50000000000000000bf21e44003acdd2d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000acddfec5c1f21d8915101000000000000033a80000000000000000d1ba8323fe558c61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce00000000000000008fec2252d887ff4c152010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000152010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000152011ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000152020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000152021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000152000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000152010ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001ecc2caec5160994be04204a968c7152010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000151242719804349be684bd0188d53152010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100017f21ed1ce05d43fc8395f787b48c152010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9400017b810429a7c2a5d405ba6d9de2bd152010ffffffffffffff900001000001ad7f29abcaf485787a6521000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff840001d4effc0410b4b13be9ba978aa1fc152010ffffffffffffff900001000000000000480ebe7b9d58566d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff77000180274f468e3ce0dc409915cef51d152010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff99000159bbfd8b83e43b128b2077cfc6a115201000000000000033770001a3750647fcab18c21ab905450cc3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00011fd844a5b10ffe988f0fe96a9844160000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000160001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000160010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000160011ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000160010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000160020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000160010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001193ea7aad030b160011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001193ea7aad030b160010ffffffffffffffcb0000000000000000001ccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000178e360604b32d160010ffffffffffffffcb0000000000000000001ff7ced916872b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd0000000000000000001e66cfde9c7c2d160010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb160011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff89000000000000000000179ca10c924223160010ffffffffffffffca00000000000000000013333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000013cf2b50617c95161000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000161001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000161010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000161011ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000161010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000161020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000161010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc000000000000000008c9f53d5681854bb161011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc000000000000000008c9f53d5681854bb161010ffffffffffffffc00000000000000000e666666666666666000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000bc71b0302599638f161010ffffffffffffffc00000000000000000ffbe76c8b4395810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000f3367ef4e3e1730e161010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf161011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000bce5086492111aeb161010ffffffffffffffbf0000000000000000999999999999999a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf00000000000000009e795a830be4aa8a161010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c0162000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000162001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000162010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000162011ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000162010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000162020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000162010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001193ea7aad030a976a4198d55053b162011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001193ea7aad030a976a4198d55053b162010ffffffffffffff8f0001cccccccccccccccccccccccccccd000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000178e360604b32c72007a97137290a162010ffffffffffffff8f0001ff7ced916872b020c49ba5e353f8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff910001e66cfde9c7c2e67bc9a0347e3d43162010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001b7cdfd9d7bdbab7d85f1981b44bf162011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d000179ca10c9242235d511e976394d7a162010ffffffffffffff8e00013333333333333333333333333333000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00013cf2b50617c95513b24a908ab329162010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d170000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000170001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000170020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000170021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000170010ffffffffffffffd000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000170011ffffffffffffffd000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcc00000000000000000010000000000000170010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb00000000000000000010a7ef5c18edd2170011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb00000000000000000010a7ef5c18edd2170010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001af767a741088b170010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001fd9ae142795e3170011ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001fffd1ac4135f9170010ffffffffffffffce00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001fffffffffc9e8170010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffaa0000000000000000001f044332d68161170011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff890000000000000000001aa4a230244ae0170010ffffffffffffffcf00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000170010ffffffffffffffcf00000000000000000013000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000170010ffffffffffffffc5000000000000000000147ae147ae147b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc5000000000000000000171bc266657b66171000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000171001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000171020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000171021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000171010ffffffffffffffc50000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000171011ffffffffffffffc50000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc100000000000000008000000000000000171010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000853f7ae0c76e915f171011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000853f7ae0c76e915f171010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000d7bb3d3a08445637171010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000fecd70a13caf1997171011ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000fffe8d6209afcbdd171010ffffffffffffffc30000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000fffffffffe4f3e59171010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9f0000000000000000f8221996b40b0778171011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7e0000000000000000d5251181225702d8171010ffffffffffffffc400000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000171010ffffffffffffffc400000000000000009800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000171010ffffffffffffffba0000000000000000a3d70a3d70a3d70a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffba0000000000000000b8de13332bdb2bc4171010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcbd90000000000000000b04c4a6e744904f2172000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000172001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000172020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000172021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000172010ffffffffffffff9400014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000172011ffffffffffffff9400014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff9000010000000000000000000000000000172010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00010a7ef5c18edd22bd013e346344f5172011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f00010a7ef5c18edd22bd013e346344f5172010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001af767a741088ac6d0110fdbb0d27172010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001fd9ae142795e332e500320973468172011ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001fffd1ac4135f97babe87b35b3bd6172010ffffffffffffff9200014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001fffffffffc9e7cb14c1118ed942b172010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6e0001f044332d68160eef3eb77ebe0ca9172011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff4d0001aa4a230244ae05ae2c351c31ce73172010ffffffffffffff9300010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001fffffffffffffffffffffffe38b0172010ffffffffffffff9300013000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000172010ffffffffffffff89000147ae147ae147ae147ae147ae147b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff89000171bc266657b65788426d3123363f172010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffcba80001609894dce89209e460bb82793555180000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000180020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000180021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000010000000000000180011ffffffffffffffd000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000010000000000000180010ffffffffffffffd300000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000180010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000001eb02147ce245c180011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001853f7ae0c76e9180010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc900000000000000000014226162fbddd5180010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000001328f5ec350e67180011ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001fffe8d6209afd180010ffffffffffffffce00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa40000000000000000001b0c1a759f7739180010ffffffffffffffce0000000000000000001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff81000000000000000000194a28136fa731180010ffffffffffffffcf00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff6b0000000000000000001c74fc41217dfb180010ffffffffffffffcf00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff3700000000000000000017d8a7f2a8a2d0180010ffffffffffffffd000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffd850000000000000000001b54f244df93df180010ffffffffffffffd100000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000180010ffffffffffffffd200000000000000000019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000180010ffffffffffffffd20000000000000000001a400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000180010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001ffffffff07dde180011ffffffffffffff89000000000000000000179ca10c924223000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000180011ffffffffffffffce0000000000000000001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000010000000000000181000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000181020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000181021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008000000000000000181011ffffffffffffffc50000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008000000000000000181010ffffffffffffffc80000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000181010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf0000000000000000f5810a3e7122dd43181011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000c29fbd7063b748af181010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbe0000000000000000a1130b17deeea726181010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb900000000000000009947af61a873346c181011ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000ffff46b104d7e5ef181010ffffffffffffffc30000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff990000000000000000d860d3acfbb9c49b181010ffffffffffffffc30000000000000000e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff760000000000000000ca51409b7d398a92181010ffffffffffffffc400000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff600000000000000000e3a7e2090befdbb6181010ffffffffffffffc40000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff2c0000000000000000bec53f9545167cea181010ffffffffffffffc50000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffd7a0000000000000000daa79226fc9ef527181010ffffffffffffffc60000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffff1a30000000000000000ddb4c7bd058dd25c181010ffffffffffffffc70000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc75e0000000000000000bf54533bddd43962181010ffffffffffffffc70000000000000000d200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc1970000000000000000d6d6e6e7f02c7454181010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000ffffffff83eef335181011ffffffffffffff7e0000000000000000bce5086492111aeb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000181011ffffffffffffffc30000000000000000e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc200000000000000008000000000000000182000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000182020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000182021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100010000000000000000000000000000182011ffffffffffffff9400014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100010000000000000000000000000000182010ffffffffffffff9700019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000182010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e0001eb02147ce245ba85fd8397397616182011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001853f7ae0c76e915e809f1a31a27b182010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8d00014226162fbddd4e4bfbbc0913cb64182010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff880001328f5ec350e668d7fe6fb465cc11182011ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001fffe8d6209afcbdd5f43d9ad9deb182010ffffffffffffff9200014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff680001b0c1a759f7738935ea5dea8e17aa182010ffffffffffffff920001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff45000194a28136fa7315247e79c160e7e4182010ffffffffffffff9300010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff2f0001c74fc41217dfb76b800fa2d891d1182010ffffffffffffff9300014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffefb00017d8a7f2a8a2cf9d37388c15c764d182010ffffffffffffff9400014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffd490001b54f244df93dea4d2148f7283e4d182010ffffffffffffff9500019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffff1720001bb698f7a0b1ba4b7d4efa35359f9182010ffffffffffffff9600019000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc72d00017ea8a677bba872c483300ff9aee0182010ffffffffffffff960001a400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffc1660001adadcdcfe058e8a893497ef90397182010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001ffffffff07dde6694bf4f88860a4182011ffffffffffffff4d000179ca10c9242235d511e976394d7a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000354944604896182011ffffffffffffff920001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001ffffffffffffffffffcd6bafd921190000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000190011ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000190011ffffffffffffffcd00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000190020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000190010ffffffffffffffcc00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000190010ffffffffffffffcd00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000190010ffffffffffffffce00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd000000000000000000018000000000000190010ffffffffffffffd700000000000000000017700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000190010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001c5bf891b4ef6b190010ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001c5bf891b4ef6b190010ffffffffffffffcd00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001544fa6d47b390190010ffffffffffffffcf00000000000000000015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffe0000000000000000000114ade639225ca190011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcd0000000000000000001c5bf891b4ef6b190011ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcd00000000000000000012e7fb0bcdf4f2190011ffffffffffffffcd00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcb0000000000000000001e3ff812e32183190011ffffffffffffffcf00000000000000000015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffb600000000000000000011b7b1db2e47f1190010ffffffffffffffd20000000000000000001920000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000001d500000000000000000015b98374db8c0b190010ffffffffffffffd60000000000000000001a920000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190011ffffffffffffffd300000000000000000015500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011fffffffffffffbce00000000000000000017d2374dfcda7a190010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffed00000000000000000012a05f1ffb61dd190011ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffed00000000000000000012a05f20049e23190010ffffffffffffffc200000000000000000010624dd2f1a9fc000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd50000000000000000001f3b63e2d41242190010ffffffffffffffd00000000000000000001e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000320000000000000000001be6518687a785190010ffffffffffffffd20000000000000000001020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000f00000000000000000001fd48ab83e8085190011ffffffffffffffd60000000000000000001b820000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000190011ffffffffffffffbb00000000000000000014f8b588e368f1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffdc000000000000000000186a093c50dd38190010ffffffffffffffd60000000000000000001b6c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190010ffffffffffffffd60000000000000000001b6e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190010ffffffffffffffd60000000000000000001b700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000190011ffffffffffffffd60000000000000000001b5a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000190011ffffffffffffffd50000000000000000001f440000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000190010ffffffffffffffd30000000000000000001548000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003c10000000000000000001c1530ea2b9f39191000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000191001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000191011ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000191011ffffffffffffffc20000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000191020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000191021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000191010ffffffffffffffc100000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000191010ffffffffffffffc200000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000191010ffffffffffffffc30000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc50000000000000000c000000000000000191010ffffffffffffffcc0000000000000000bb80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000191030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000191010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000e2dfc48da77b553d191010ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000e2dfc48da77b553d191010ffffffffffffffc20000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000aa27d36a3d9c7fee191010ffffffffffffffc40000000000000000a800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd500000000000000008a56f31c912e4ea5191011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc20000000000000000e2dfc48da77b553d191011ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc20000000000000000973fd85e6fa78e29191011ffffffffffffffc20000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc00000000000000000f1ffc097190c16a7191011ffffffffffffffc40000000000000000a800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffab00000000000000008dbd8ed9723f8be6191010ffffffffffffffc70000000000000000c90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000001ca0000000000000000adcc1ba6dc605a15191010ffffffffffffffcb0000000000000000d4900000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003d700000000000000000fd9d6cd772bf604e191011ffffffffffffffc80000000000000000aa80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011fffffffffffffbc30000000000000000be91ba6fe6d3ce39191010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffe200000000000000009502f8ffdb0ee607191011ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffe200000000000000009502f90024f119f9191010ffffffffffffffb7000000000000000083126e978d4fdf3b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca0000000000000000f9db1f16a0920f6b191010ffffffffffffffc50000000000000000f00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000270000000000000000df328c343d3c2866191010ffffffffffffffc70000000000000000810000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000e50000000000000000fea455c1f4042a3e191011ffffffffffffffcb0000000000000000dc10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000191011ffffffffffffffb00000000000000000a7c5ac471b478423000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd10000000000000000c35049e286e9c192191010ffffffffffffbfc300000000000000000000000663278e62000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000191010ffffffffffffffcb0000000000000000db600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fbb00000000000000008848a7629507cc6f191010ffffffffffffffcb0000000000000000db700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003fc00000000000000000b267241c8b492cb4191010ffffffffffffffcb0000000000000000db80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000191011ffffffffffffffcb0000000000000000dad0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffbfee00000000000000009adf760dac385b78191011ffffffffffffffca0000000000000000fa20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffde6c00000000000000009a598686084a8725191010ffffffffffffffc80000000000000000aa4000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003b60000000000000000e0a987515cf9c79d192000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000192001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000021000000000000000000000000000000000000000000000000192011ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000192011ffffffffffffff9100018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000192020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000192021000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000192010ffffffffffffff9000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000192010ffffffffffffff9100010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000192010ffffffffffffff9200014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9400018000000000000000000000000000192010ffffffffffffff9b00017700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000192030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000192010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001c5bf891b4ef6aa79c3b0520d5db9192010ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001c5bf891b4ef6aa79c3b0520d5db9192010ffffffffffffff9100014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff900001544fa6d47b38ffdb52c43d8a064b192010ffffffffffffff9300015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa4000114ade639225c9d4a36f0dbcd30fd192011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff910001c5bf891b4ef6aa79c3b0520d5db9192011ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9100012e7fb0bcdf4f1c512d2036b393d1192011ffffffffffffff9100014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8f0001e3ff812e32182d4eae99f11f52e8192011ffffffffffffff9300015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff7a00011b7b1db2e47f17cc101cbec7ae7f192010ffffffffffffff9600019200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000019900015b98374db8c0b42ad366ee06b2c9192010ffffffffffffff9a0001a9200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003d3f0001fb3ad9aee57ec09ba5b03b2f9d4c192011ffffffffffffff9700015500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011fffffffffffffb9200017d2374dfcda79c72e0b94041001b192010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb100012a05f1ffb61dcc0e778755f2869b192011ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffb100012a05f20049e233f1f5381d978334192010ffffffffffffff8600010624dd2f1a9fbe76c8b439581062000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff990001f3b63e2d41241ed39d3d9b72d34c192010ffffffffffffff940001e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffff60001be6518687a7850cb72d800000000192010ffffffffffffff960001020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000b40001fd48ab83e808547cf0239a70bc9f192011ffffffffffffff9a0001b820000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffbf9200000000000000000000b44aaa5f4f8d192011ffffffffffffff7f00014f8b588e368f08461f9f01b866e4000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffa0000186a093c50dd38324d37d5af809e3192010ffffffffffffbf9200000000000cc64f1cc4376f7da08f39000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000192010ffffffffffffff9a0001b6c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8a000110914ec52a0f98def5cbae9e2388192010ffffffffffffff9a0001b6e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f8f000164ce4839169259677e0aaeff5316192010ffffffffffffff9a0001b700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000192011ffffffffffffff9a0001b5a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffbfbd000135beec1b5870b6efa85062ff188c192011ffffffffffffff990001f440000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffde3b000134b30d0c10950e4a1c8e1bc6c589192010ffffffffffffff970001548000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003850001c1530ea2b9f38f39e1366408ac6d1a0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a0010ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a0011ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a0011ffffffffffffffce000000000000000000140000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a00210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a00300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001a0010ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001250d048e7a1bd1a0010ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc80000000000000000001eeb95b094c1911a0010ffffffffffffffcd00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffca00000000000000000012383e809a67e81a0010ffffffffffffffcf00000000000000000015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf0000000000000000001be199a0f643941a0011ffffffffffffffcb00000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc000000000000000000143f89a3f0edd61a0011ffffffffffffffcc00000000000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001b858151820f861a0011ffffffffffffffcd00000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc70000000000000000001ccbf9f5ed0f161a0011ffffffffffffffcf00000000000000000015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffcf0000000000000000001e4b670d05976a1a0010ffffffffffffffd200000000000000000019200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd40000000000000000001696f7f94813081a0010ffffffffffffffed00000000000000000012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010fffffffffffffff100000000000000000019a43710f467c11a001000000000000003b000000000000000000017e43c8800759c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003ba0000000000000000001017f38e7a1ab51a0011ffffffffffffffd300000000000000000015500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd5000000000000000000161ffcca844ad91a0010ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd000000000000000000017069e2aa26ae41a0011ffffffffffffffaa0000000000000000001b7cdfd9d7bdbb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd000000000000000000017069e2aa2e9d21a0010ffffffffffffffc200000000000000000010624dd2f1a9fc000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000001ba0f3807161ac1a0010ffffffffffffffcc0000000000000000001000001ad7f29b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffb30000000000000000001efd30c8e518b91a0010ffffffffffffffcd0000000000000000001000000d6bf94d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb300000000000000000016b2b43f3939391a0010ffffffffffffffcb0000000000000000001fffffca501acb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb30000000000000000001efd315c7aed331a0011ffffffffffffffcd00000000000000000013a7fc9600f86b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff990000000000000000001a4630d45350781a0011ffffffffffffffdc000000000000000000186a0800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffe0000000000000000000100aa7d56926841a0010ffffffffffffffcd0000000000000000001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000013373018970a361a0010ffffffffffffff6800000000000000000014484bfeebc2a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffd20000000000000000001144f69ff9ffc41a0011ffffffffffffffcd0000000000000000001800000d6bf94d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcf0000000000000000001ca715850f209c1a0010ffffffffffffffcb00000000000000000010000035afe535000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcb0000000000000000001250cfdf7d5be01a0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a0010ffffffffffffffcc000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a0010ffffffffffffffcd000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a1010ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a10010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a1011ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a1011ffffffffffffffc30000000000000000a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a10210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a10300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001a1010ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000928682473d0de85f1a1010ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbd0000000000000000f75cad84a60c8a691a1010ffffffffffffffc20000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffbf000000000000000091c1f404d33f3cfc1a1010ffffffffffffffc40000000000000000a800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000df0ccd07b21ca0f11a1011ffffffffffffffc000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000a1fc4d1f876eb1051a1011ffffffffffffffc10000000000000000c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc00000000000000000dc2c0a8c107c32401a1011ffffffffffffffc20000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffbc0000000000000000e65fcfaf6878ac471a1011ffffffffffffffc40000000000000000a800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffc40000000000000000f25b38682cbb4e361a1010ffffffffffffffc70000000000000000c900000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc90000000000000000b4b7bfca40983f201a1010ffffffffffffffe200000000000000009502f90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffe60000000000000000cd21b887a33e09121a101000000000000003a50000000000000000bf21e44003acdd2d00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000003af000000000000000080bf9c73d0d5a6041a1011ffffffffffffffc80000000000000000aa80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffca0000000000000000b0ffe6542256c9871a1010ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc50000000000000000b834f15513571db31a1011ffffffffffffff9f0000000000000000dbe6fecebdedd5bf000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc50000000000000000b834f155174e90861a1010ffffffffffffffb7000000000000000083126e978d4fdf3b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc30000000000000000dd079c038b0d62b11a1010ffffffffffffffc10000000000000000800000d6bf94d5e5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffa80000000000000000f7e98644ba88c6d91a1010ffffffffffffffc200000000000000008000006b5fca6af3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa80000000000000000b595a1fec698d9421a1010ffffffffffffffc00000000000000000fffffe5280d65435000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffa80000000000000000f7e98ae607e395021a1011ffffffffffffffc200000000000000009d3fe4b007c35572000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f00000000000000008812667377357c031a101000000000000033a80000000000000000d1ba8323fe558c6100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000033b50000000000000000ebc62dd1c59326cf1a1010ffffffffffffcbd900000000000000009c3d73864f3805c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffce00000000000000008fe95c8a78a8b80e1a10100000000000003f560000000000000000ae9204275937a4c10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f630000000000000000f06926ba638c1b461a1011ffffffffffffffd10000000000000000c350400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffd5000000000000000080553eab49341d7b1a1010ffffffffffffffc20000000000000000e000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc1000000000000000099b980c4b851adc11a1010ffffffffffffff5d0000000000000000a2425ff75e14fc32000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc700000000000000008a27b4ffcffe21551a1011ffffffffffffffc20000000000000000c000006b5fca6af3000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc40000000000000000e538ac280883e56d1a1010ffffffffffffffc00000000000000000800001ad7f29abcb000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc0000000000000000092867efbeadef7e01a1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a1010ffffffffffffffc1000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a1010ffffffffffffffc2000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a2010ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a2010ffffffffffffff91000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001a20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a20010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a2011ffffffffffffff90000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a2011ffffffffffffff92000140000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a20210000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000001a20300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001a2010ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001250d048e7a1bd0bd5f956c6a843f1a2010ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8c0001eeb95b094c1914d1a18fd62c1d351a2010ffffffffffffff9100014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8e00012383e809a67e79f700737168fdd51a2010ffffffffffffff9300015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff930001be199a0f643941e24c6d015877261a2011ffffffffffffff8f00010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff90000143f89a3f0edd620a79ae69cd46131a2011ffffffffffffff9000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001b858151820f8647f3ef1202089941a2011ffffffffffffff9100014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff8b0001ccbf9f5ed0f1588ec36c2db7d3851a2011ffffffffffffff9300015000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff930001e4b670d059769c6cda93a1dcab8a1a2010ffffffffffffff9600019200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff980001696f7f9481307e3f4d2011b159a01a2010ffffffffffffffb100012a05f20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffb500019a43710f467c12234496dcec396c1a2010000000000000037400017e43c8800759ba59c08e14c7cd7b000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000037e0001017f38e7a1ab4c08b0f0ae917f821a2011ffffffffffffff9700015500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff99000161ffcca844ad930d2a4e18aa340b1a2010ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9400017069e2aa26ae3b66030939ad582d1a2011ffffffffffffff6e0001b7cdfd9d7bdbab7d6ae6881cb511000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9400017069e2aa2e9d210c9583d5b1f1b41a2010ffffffffffffff8600010624dd2f1a9fbe76c8b439581062000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff920001ba0f3807161ac560fa2d37ed26721a2010ffffffffffffff900001000001ad7f29abcaf485787a6521000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff770001efd30c89762bd627ba68c9f9ed8f1a2010ffffffffffffff910001000000d6bf94d5e57a42bc3d3290000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff7700016b2b43fd8c4f86971a0d8a44fa8f1a2010ffffffffffffff8f0001fffffca501aca86a16f50f0b35be000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff770001efd315cc0fb9e9af87d1fcec5de51a2011ffffffffffffff9100013a7fc9600f86aae36ffe37b33997000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff5e0001102b9ef62fdb09492e61445d60281a201000000000000033770001a3750647fcab18c21ab905450cc300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000033840001d78c5ba38b264d9d99ef24b491101a2010ffffffffffffcba80001387ae70c9e700b8049732d11a23d000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9d00011fd2b914f151701cc1b19a4cfb841a20100000000000003f2500015d24084eb26f498151922505cb5f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000003f320001e0d24d74c718368b2a10b3c117a71a2011ffffffffffffffa0000186a0800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffffa4000100aa7d5692683af556dcf32158d31a2010ffffffffffffff910001c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000013373018970a35b81d5b0cdd842db1a2010ffffffffffffff2c00014484bfeebc29f863424b06f3529a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff960001144f69ff9ffc42aaf762d191951d1a2011ffffffffffffff910001800000d6bf94d5e57a42bc3d3290000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff930001ca715850111bb89aea0eea0d68e61a2010ffffffffffffff8f00010000035afe535795e90af0f4ca42000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff8f0001250cfdf7d5bdefbf9b2d7b29ae2a1a2010ffffffffffffff9000010000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000011ffffffffffffff1f00012788cfc6fb618f49a37c7f0202a41a2010ffffffffffffff8f0001fffffffffffffffffffffffffffe000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff1f00012788cfc6fb618f49a37c7f0202a71a2010ffffffffffffff9100010000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff1f0001b0ee6072093ce16cb90701fbfab71b00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000300000000000000000000000000000000000000000000000001b00000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010ffffffffffffffcc00000000000000000010000000000000300000000000000000000000000000000000000000000000001b002000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000021000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001b002000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc00000000000000000010000000000000200000000000000000000000000000000000000000000000001b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000001b000000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b000100000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000001000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000001b000100000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcd0000000000000000001800000000000011ffffffffffffffce00000000000000000018000000000000000000000000000000000000000000000000000000000000001b0010ffffffffffffffcd0000000000000000001000000000000010ffffffffffffffcd0000000000000000001800000000000010ffffffffffffffce0000000000000000001000000000000010ffffffffffffffcf000000000000000000140000000000001b003000000000000000000000000000000000000000000000000010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc00000000000000000010000000000000300000000000000000000000000000000000000000000000001b0010ffffffffffffffcc000000000000000000180000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b000000000000000000000000000000000000000000000000000010ffffffffffffffce0000000000000000001400000000000010ffffffffffffffce0000000000000000001c00000000000010ffffffffffffffce0000000000000000001c0000000000001b0010ffffffffffffffcc0000000000000000001800000000000010ffffffffffffffcd0000000000000000001400000000000011ffffffffffffffcd0000000000000000001e000000000000000000000000000000000000000000000000000000000000001b0010ffffffffffffffc80000000000000000001999999999999a10ffffffffffffffc80000000000000000001999999999999a11ffffffffffffffc5000000000000000000147ae147ae147b10ffffffffffffff9000000000000000000010a3d70a3d70a41b001000000000000003b000000000000000000017e43c8800759c1000000000000003b000000000000000000017e43c8800759c1100000000000003b000000000000000000017e43c8800759c200000000000000000000000000000000000000000000000001b0010fffffffffffffbe7000000000000000000156e1fc2f8f35910fffffffffffffbe7000000000000000000156e1fc2f8f35910ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc000000000000000000100000000000001b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffff6800000000000000000014484bfeebc2a010ffffffffffffffcc000000000000000000100000000000001b0010ffffffffffffffca0000000000000000001333333333333310ffffffffffffffcd0000000000000000001800000000000011ffffffffffffffcb0000000000000000001ccccccccccccd11ffffffffffffff96000000000000000000100000000000001b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000011ffffffffffffff6800000000000000000014484bfeebc2a010ffffffffffffffcc000000000000000000100000000000001b0010ffffffffffffffe60000000000000000001d6f345400000010ffffffffffffffe90000000000000000001d6f34588000001100000000000000040000000000000000001b13114fbff53810ffffffffffffffce000000000000000000140000000000001b10200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000300000000000000000000000000000000000000000000000001b10000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010ffffffffffffffc100000000000000008000000000000000300000000000000000000000000000000000000000000000001b102000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000021000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001b102000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc100000000000000008000000000000000200000000000000000000000000000000000000000000000001b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000001b100000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b100100000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000001000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000001b100100000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc20000000000000000c00000000000000011ffffffffffffffc30000000000000000c000000000000000000000000000000000000000000000000000000000000000001b1010ffffffffffffffc20000000000000000800000000000000010ffffffffffffffc20000000000000000c00000000000000010ffffffffffffffc30000000000000000800000000000000010ffffffffffffffc40000000000000000a0000000000000001b103000000000000000000000000000000000000000000000000010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc100000000000000008000000000000000300000000000000000000000000000000000000000000000001b1010ffffffffffffffc10000000000000000c0000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b100000000000000000000000000000000000000000000000000010ffffffffffffffc30000000000000000a00000000000000010ffffffffffffffc30000000000000000e00000000000000010ffffffffffffffc30000000000000000e0000000000000001b1010ffffffffffffffc10000000000000000c00000000000000010ffffffffffffffc20000000000000000a00000000000000011ffffffffffffffc20000000000000000f000000000000000000000000000000000000000000000000000000000000000001b1010ffffffffffffffbd0000000000000000cccccccccccccccd10ffffffffffffffbd0000000000000000cccccccccccccccd11ffffffffffffffba0000000000000000a3d70a3d70a3d70a10ffffffffffffff7a00000000000000008f5c28f5c28f5c291b101000000000000003a50000000000000000bf21e44003acdd2d1000000000000003a50000000000000000bf21e44003acdd2d1100000000000003a50000000000000000bf21e44003acdd2d10000000000000078a00000000000000008eb39714297efb281b1010fffffffffffffbdc0000000000000000ab70fe17c79ac6ca10fffffffffffffbdc0000000000000000ab70fe17c79ac6ca10ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc1000000000000000080000000000000001b1010ffffffffffffffc20000000000000000c00000000000000010ffffffffffffffc30000000000000000a00000000000000010ffffffffffffcbd900000000000000009c3d73864f3805c010ffffffffffffffc40000000000000000f0000000000000001b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000010ffffffffffffff5d0000000000000000a2425ff75e14fc3210ffffffffffffffc1000000000000000080000000000000001b1010ffffffffffffffbf0000000000000000999999999999999a10ffffffffffffffc20000000000000000c00000000000000011ffffffffffffffc00000000000000000e66666666666666610ffffffffffffff81000000000000000080000000000000001b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000011ffffffffffffff5d0000000000000000a2425ff75e14fc3210ffffffffffffffc1000000000000000080000000000000001b1010ffffffffffffffdb0000000000000000eb79a2a00000000010ffffffffffffffde0000000000000000eb79a2c40000000011fffffffffffffff90000000000000000d8988a7dffa9c280000000000000000000000000000000000000000000000000001b20200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000300000000000000000000000000000000000000000000000001b20000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000300000000000000000000000000000000000000000000000001b202000000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000021000000000000000000000000000000000000000000000000300000000000000000000000000000000000000000000000001b202000000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000200000000000000000000000000000000000000000000000001b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000021000000000000000000000000000000000000000000000000210000000000000000000000000000000000000000000000001b200000000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b200100000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000001000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000001b200100000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b2010ffffffffffffff910001000000000000000000000000000010ffffffffffffff910001800000000000000000000000000011ffffffffffffff9200018000000000000000000000000000000000000000000000000000000000000000000000000000001b2010ffffffffffffff910001000000000000000000000000000010ffffffffffffff910001800000000000000000000000000010ffffffffffffff920001000000000000000000000000000010ffffffffffffff93000140000000000000000000000000001b203000000000000000000000000000000000000000000000000010ffffffffffffff900001000000000000000000000000000010ffffffffffffff9000010000000000000000000000000000300000000000000000000000000000000000000000000000001b2010ffffffffffffff90000180000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b200000000000000000000000000000000000000000000000000010ffffffffffffff920001400000000000000000000000000010ffffffffffffff920001c00000000000000000000000000010ffffffffffffff920001c0000000000000000000000000001b2010ffffffffffffff900001800000000000000000000000000010ffffffffffffff910001400000000000000000000000000011ffffffffffffff910001e000000000000000000000000000000000000000000000000000000000000000000000000000001b2010ffffffffffffff8c0001999999999999999999999999999a10ffffffffffffff8c0001999999999999999999999999999a11ffffffffffffff89000147ae147ae147ae147ae147ae147b10ffffffffffffff1800010a3d70a3d70a3d70a3d70a3d70a41b2010000000000000037400017e43c8800759ba59c08e14c7cd7b10000000000000037400017e43c8800759ba59c08e14c7cd7b11000000000000037400017e43c8800759ba59c08e14c7cd7b10000000000000075900011d672e2852fdf64f795fb752dd7a1b2010fffffffffffffbab000156e1fc2f8f358d94db7ac614915610fffffffffffffbab000156e1fc2f8f358d94db7ac614915610ffffffffffffff900001000000000000000000000000000010ffffffffffffff90000100000000000000000000000000001b2010ffffffffffffff910001800000000000000000000000000010ffffffffffffff920001400000000000000000000000000010ffffffffffffcba80001387ae70c9e700b8049732d11a23d10ffffffffffffff930001e0000000000000000000000000001b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000010ffffffffffffff2c00014484bfeebc29f863424b06f3529a10ffffffffffffff90000100000000000000000000000014481b2010ffffffffffffff8e0001333333333333333333333333333310ffffffffffffff910001800000000000000000000000000011ffffffffffffff8f0001cccccccccccccccccccccccccccd11ffffffffffffff1e000100000000000000000000000000001b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000011ffffffffffffff2c00014484bfeebc29f863424b06f3529a10ffffffffffffff8f0001ffffffffffffffffffffffffd76f1b2010ffffffffffffffaa0001d6f345400000000000000000000010ffffffffffffffad0001d6f345880000000000000000000011ffffffffffffffc80001b13114fbff538500000000000000000000000000000000000000000000000000000000000000001b0010ffffffffffffffcc0000000000000000001000000000000110ffffffffffffffcc0000000000000000001000000000000111ffffffffffffffcc0000000000000000001000000000000210ffffffffffffff64000000000000000000100000000000001b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffff970000000000000000001000000000000010ffffffffffffffcc000000000000000000100000000000001b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffff970000000000000000001000000000000110ffffffffffffffcc000000000000000000100000000000011b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000011ffffffffffffff970000000000000000001000000000000010ffffffffffffffcb0000000000000000001fffffffffffff1b0010ffffffffffffffcc0000000000000000001000000000000010ffffffffffffffcc0000000000000000001000000000000011ffffffffffffff970000000000000000001000000000000110ffffffffffffffcb0000000000000000001fffffffffffff1b0010ffffffffffffffcc0000000000000000001000000000000110ffffffffffffffcb0000000000000000001fffffffffffff11ffffffffffffffcc0000000000000000001000000000000010ffffffffffffff960000000000000000001ffffffffffffe1b0010ffffffffffffffcc0000000000000000001000000000000110ffffffffffffffcc0000000000000000001000000000000110ffffffffffffff2d0000000000000000001000000000000010ffffffffffffffcc000000000000000000100000000000021b0011ffffffffffffffcc0000000000000000001000000000000110ffffffffffffffcc0000000000000000001000000000000110ffffffffffffffcc0000000000000000001000000000000211ffffffffffffff64000000000000000000100000000000001b1010ffffffffffffffc10000000000000000800000000000000110ffffffffffffffc10000000000000000800000000000000111ffffffffffffffc10000000000000000800000000000000210ffffffffffffff43000000000000000080000000000000001b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000010ffffffffffffff810000000000000000800000000000000010ffffffffffffffc1000000000000000080000000000000001b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000010ffffffffffffff810000000000000000800000000000000110ffffffffffffffc1000000000000000080000000000000011b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000011ffffffffffffff810000000000000000800000000000000010ffffffffffffffc00000000000000000ffffffffffffffff1b1010ffffffffffffffc10000000000000000800000000000000010ffffffffffffffc10000000000000000800000000000000011ffffffffffffff810000000000000000800000000000000110ffffffffffffffc00000000000000000ffffffffffffffff1b1010ffffffffffffffc10000000000000000800000000000000110ffffffffffffffc00000000000000000ffffffffffffffff11ffffffffffffffc10000000000000000800000000000000010ffffffffffffff800000000000000000fffffffffffffffe1b1010ffffffffffffffc10000000000000000800000000000000110ffffffffffffffc10000000000000000800000000000000110ffffffffffffff010000000000000000800000000000000010ffffffffffffffc1000000000000000080000000000000021b1011ffffffffffffffc10000000000000000800000000000000110ffffffffffffffc10000000000000000800000000000000110ffffffffffffffc10000000000000000800000000000000211ffffffffffffff43000000000000000080000000000000001b2010ffffffffffffff900001000000000000000000000000000110ffffffffffffff900001000000000000000000000000000111ffffffffffffff900001000000000000000000000000000210fffffffffffffeb0000100000000000000000000000000001b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000010ffffffffffffff1f0001000000000000000000000000000010ffffffffffffff90000100000000000000000000000000001b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000010ffffffffffffff1f0001000000000000000000000000000110ffffffffffffff90000100000000000000000000000000011b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000011ffffffffffffff1f0001000000000000000000000000000010ffffffffffffff8f0001ffffffffffffffffffffffffffff1b2010ffffffffffffff900001000000000000000000000000000010ffffffffffffff900001000000000000000000000000000011ffffffffffffff1f0001000000000000000000000000000110ffffffffffffff8f0001ffffffffffffffffffffffffffff1b2010ffffffffffffff900001000000000000000000000000000110ffffffffffffff8f0001ffffffffffffffffffffffffffff11ffffffffffffff900001000000000000000000000000000010ffffffffffffff1e0001fffffffffffffffffffffffffffe1b2010ffffffffffffff900001000000000000000000000000000110ffffffffffffff900001000000000000000000000000000110fffffffffffffe3d0001000000000000000000000000000010ffffffffffffff90000100000000000000000000000000021b2011ffffffffffffff900001000000000000000000000000000110ffffffffffffff900001000000000000000000000000000110ffffffffffffff900001000000000000000000000000000211fffffffffffffeb000010000000000000000000000000000"
:begin
  calc t1 = machine.addressOfString(cases)
  return t1

op loadRecord "Read a record of the table into parts: kind, sign, power, and the significand's two words"
  input parts machine.Address copied
  input base machine.Address copied
  input at Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = hexAt(base, at, 1)
  calc t2 = hexAt(base, at + 1, 1)
  calc t3 = hexAt(base, at + 2, 16)
  calc t4 = hexAt(base, at + 18, 16)
  calc t5 = hexAt(base, at + 34, 16)
  clong.setPart(parts, 8, convert.uint64ToInt64(t1))
  clong.setPart(parts, 0, convert.uint64ToInt64(t2))
  clong.setPart(parts, 16, convert.uint64BitsToInt64(t3))
  clong.setSignificand(parts, t4, t5)
  return

op runCase "Run function number fn of the table on parts (x in px, y in py, z in pz)"
  input fn Int64 copied
  input layout Int64 copied
  input px machine.Address copied
  input py machine.Address copied
  input pz machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when fn == 0 yes1 join3
:yes1
  sinCore(px, layout)
  return
:join3
  when fn == 1 yes4 join6
:yes4
  cosCore(px, layout)
  return
:join6
  when fn == 2 yes7 join9
:yes7
  tanCore(px, layout)
  return
:join9
  when fn == 3 yes10 join12
:yes10
  asinCore(px, layout)
  return
:join12
  when fn == 4 yes13 join15
:yes13
  acosCore(px, layout)
  return
:join15
  when fn == 5 yes16 join18
:yes16
  atanCore(px, layout)
  return
:join18
  when fn == 6 yes19 join21
:yes19
  atan2Core(px, py, layout)
  return
:join21
  when fn == 7 yes22 join24
:yes22
  expCore(px, layout)
  return
:join24
  when fn == 8 yes25 join27
:yes25
  exp2Core(px, layout)
  return
:join27
  when fn == 9 yes28 join30
:yes28
  expm1Core(px, layout)
  return
:join30
  when fn == 10 yes31 join33
:yes31
  logCore(px, layout)
  return
:join33
  when fn == 11 yes34 join36
:yes34
  log2Core(px, layout)
  return
:join36
  when fn == 12 yes37 join39
:yes37
  log10Core(px, layout)
  return
:join39
  when fn == 13 yes40 join42
:yes40
  log1pCore(px, layout)
  return
:join42
  when fn == 14 yes43 join45
:yes43
  powCore(px, py, layout)
  return
:join45
  when fn == 15 yes46 join48
:yes46
  cbrtCore(px, layout)
  return
:join48
  when fn == 16 yes49 join51
:yes49
  hypotCore(px, py, layout)
  return
:join51
  when fn == 17 yes52 join54
:yes52
  sinhCore(px, layout)
  return
:join54
  when fn == 18 yes55 join57
:yes55
  coshCore(px, layout)
  return
:join57
  when fn == 19 yes58 join60
:yes58
  tanhCore(px, layout)
  return
:join60
  when fn == 20 yes61 join63
:yes61
  asinhCore(px, layout)
  return
:join63
  when fn == 21 yes64 join66
:yes64
  acoshCore(px, layout)
  return
:join66
  when fn == 22 yes67 join69
:yes67
  atanhCore(px, layout)
  return
:join69
  when fn == 23 yes70 join72
:yes70
  erfCore(px, layout)
  return
:join72
  when fn == 24 yes73 join75
:yes73
  erfcCore(px, layout)
  return
:join75
  when fn == 25 yes76 join78
:yes76
  tgammaCore(px, layout)
  return
:join78
  when fn == 26 yes79 join81
:yes79
  calc sign1 = lgammaCore(px, layout)
  return
:join81
  when fn == 27 yes82 join84
:yes82
  fmaCore(px, py, pz, layout)
  return
:join84
  return

op sameWithin "How far a result's parts are from the expected ones: 0 when the same, the distance in units of the last place when the power and the sign agree, 99 otherwise"
  input a machine.Address copied
  input b machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let far Int64 99
  let same Int64 0
  let d11 UInt64 0 mut
:begin
  calc t1 = clong.getPart(a, 8)
  calc t2 = clong.getPart(b, 8)
  when t1 != t2 yes1 join3
:yes1
  return far
:join3
  when t1 == 3 yes4 join6
:yes4
  return same
:join6
  calc t3 = clong.getPart(a, 0)
  calc t4 = clong.getPart(b, 0)
  when t3 != t4 yes7 join9
:yes7
  return far
:join9
  when t1 != 1 yes10 join12
:yes10
  return same
:join12
  calc t5 = clong.getPart(a, 16)
  calc t6 = clong.getPart(b, 16)
  when t5 != t6 yes13 join15
:yes13
  return far
:join15
  calc t7 = clong.highOf(a)
  calc t8 = clong.highOf(b)
  when t7 != t8 yes16 join18
:yes16
  return far
:join18
  calc t9 = clong.lowOf(a)
  calc t10 = clong.lowOf(b)
  when t9 >= t10 yes19 no20
:yes19
  calc d11 := t9 - t10
  goto join21
:no20
  calc d11 := t10 - t9
  goto join21
:join21
  when d11 > 90 yes22 join24
:yes22
  return far
:join24
  calc t12 = convert.uint64ToInt64(d11)
  return t12

op prepareCase "Load the first case of the table for a function and layout into parts, with the expected result; its tolerance, or -1 when there is none"
  input base machine.Address copied
  input count Int64 copied
  input fn Int64 copied
  input layout Int64 copied
  input px machine.Address copied
  input py machine.Address copied
  input pz machine.Address copied
  input want machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let missing Int64 -1
  let i1 Int64 0 mut
:begin
  calc i1 := 0
  goto head1
:head1 loop=while max=forever
  when i1 < count body2 done3
:body2 in=head1
  calc t2 = i1 * 204
  calc t3 = convert.uint64ToInt64(hexAt(base, t2, 2))
  calc t4 = convert.uint64ToInt64(hexAt(base, t2 + 2, 1))
  when t3 == fn && t4 == layout yes4 join6
:yes4 in=head1
  calc t5 = convert.uint64ToInt64(hexAt(base, t2 + 3, 1))
  loadRecord(px, base, t2 + 4)
  loadRecord(py, base, t2 + 54)
  loadRecord(pz, base, t2 + 104)
  loadRecord(want, base, t2 + 154)
  return t5
:join6 in=head1
  calc i1 := i1 + 1
  goto head1
:done3
  return missing

op checkResult "Assert a long double is within a tolerance of the expected parts (which are given back)"
  input result machine.LongDouble copied
  input want machine.Address copied
  input tolerance Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = partsOfLong(result)
  calc t2 = sameWithin(t1, want)
  heap.give(t1)
  heap.give(want)
  test.assertTrue(t2 <= tolerance)
  return

op makeLong "A long double of this system from a whole number times a power of two"
  input sign Int64 copied
  input value UInt64 copied
  input power Int64 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc t1 = clong.partsNew()
  calc t2 = clong.format()
  setSmallValue(t1, sign, value, power, t2)
  calc t3 = longOfParts(t1)
  return t3

op checkTable "The functions of cmathlong on the table of cases, on the double, x87, and binary128 layouts: every result within its tolerance of the correctly rounded value"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let bad6 Int64 0 mut
  let i7 Int64 0 mut
:begin
  calc t1 = caseTable()
  calc t2 = clong.partsNew()
  calc t3 = clong.partsNew()
  calc t4 = clong.partsNew()
  calc t5 = clong.partsNew()
  calc bad6 := 0 - 1
  calc i7 := 0
  goto head1
:head1 loop=while max=forever
  when i7 < 1596 body2 done3
:body2 in=head1
  calc t8 = i7 * 204
  calc t9 = convert.uint64ToInt64(hexAt(t1, t8, 2))
  calc t10 = convert.uint64ToInt64(hexAt(t1, t8 + 2, 1))
  calc t11 = convert.uint64ToInt64(hexAt(t1, t8 + 3, 1))
  loadRecord(t2, t1, t8 + 4)
  loadRecord(t3, t1, t8 + 54)
  loadRecord(t4, t1, t8 + 104)
  loadRecord(t5, t1, t8 + 154)
  runCase(t9, t10, t2, t3, t4)
  calc t12 = sameWithin(t2, t5)
  when t12 > t11 yes4 join6
:yes4 in=head1
  when bad6 < 0 yes7 join9
:yes7 in=head1
  calc bad6 := i7
  goto join9
:join9 in=head1
  goto join6
:join6 in=head1
  calc i7 := i7 + 1
  goto head1
:done3
  test.assertEqualInt64(0 - 1, bad6)
  return

test abiTest "Each `abi library` operation on this system's own long double against the table's expected result for its layout, and lgammal_r's sign"
  verifies sinLong sinlIsAccurate
  verifies cosLong coslIsAccurate
  verifies tanLong tanlIsAccurate
  verifies asinLong asinlIsAccurate
  verifies acosLong acoslIsAccurate
  verifies atanLong atanlIsAccurate
  verifies expLong explIsAccurate
  verifies exp2Long exp2lIsAccurate
  verifies expm1Long expm1lIsAccurate
  verifies logLong loglIsAccurate
  verifies log2Long log2lIsAccurate
  verifies log10Long log10lIsAccurate
  verifies log1pLong log1plIsAccurate
  verifies cbrtLong cbrtlIsAccurate
  verifies sinhLong sinhlIsAccurate
  verifies coshLong coshlIsAccurate
  verifies tanhLong tanhlIsAccurate
  verifies asinhLong asinhlIsAccurate
  verifies acoshLong acoshlIsAccurate
  verifies atanhLong atanhlIsAccurate
  verifies erfLong erflIsAccurate
  verifies erfcLong erfclIsAccurate
  verifies tgammaLong tgammalIsAccurate
  verifies lgammaLong lgammalIsAccurate
  verifies atan2Long atan2lIsAccurate
  verifies powLong powlIsAccurate
  verifies hypotLong hypotlIsAccurate
  verifies fusedMultiplyAddLong fmalIsExact
  verifies logGammaSignedLong lgammalrIsAccurate
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  checkTable()
  calc t1 = caseTable()
  calc t2 = clong.format()
  calc px3 = clong.partsNew()
  calc py4 = clong.partsNew()
  calc pz5 = clong.partsNew()
  calc want6 = clong.partsNew()
  calc tol7 = prepareCase(t1, 1596, 0, t2, px3, py4, pz5, want6)
  when tol7 >= 0 yes1 no2
:yes1
  calc lx8 = longOfParts(px3)
  heap.give(py4)
  heap.give(pz5)
  calc r9 = sinLong(lx8)
  checkResult(r9, want6, tol7)
  goto join3
:no2
  heap.give(px3)
  heap.give(py4)
  heap.give(pz5)
  heap.give(want6)
  goto join3
:join3
  calc px10 = clong.partsNew()
  calc py11 = clong.partsNew()
  calc pz12 = clong.partsNew()
  calc want13 = clong.partsNew()
  calc tol14 = prepareCase(t1, 1596, 1, t2, px10, py11, pz12, want13)
  when tol14 >= 0 yes4 no5
:yes4
  calc lx15 = longOfParts(px10)
  heap.give(py11)
  heap.give(pz12)
  calc r16 = cosLong(lx15)
  checkResult(r16, want13, tol14)
  goto join6
:no5
  heap.give(px10)
  heap.give(py11)
  heap.give(pz12)
  heap.give(want13)
  goto join6
:join6
  calc px17 = clong.partsNew()
  calc py18 = clong.partsNew()
  calc pz19 = clong.partsNew()
  calc want20 = clong.partsNew()
  calc tol21 = prepareCase(t1, 1596, 2, t2, px17, py18, pz19, want20)
  when tol21 >= 0 yes7 no8
:yes7
  calc lx22 = longOfParts(px17)
  heap.give(py18)
  heap.give(pz19)
  calc r23 = tanLong(lx22)
  checkResult(r23, want20, tol21)
  goto join9
:no8
  heap.give(px17)
  heap.give(py18)
  heap.give(pz19)
  heap.give(want20)
  goto join9
:join9
  calc px24 = clong.partsNew()
  calc py25 = clong.partsNew()
  calc pz26 = clong.partsNew()
  calc want27 = clong.partsNew()
  calc tol28 = prepareCase(t1, 1596, 3, t2, px24, py25, pz26, want27)
  when tol28 >= 0 yes10 no11
:yes10
  calc lx29 = longOfParts(px24)
  heap.give(py25)
  heap.give(pz26)
  calc r30 = asinLong(lx29)
  checkResult(r30, want27, tol28)
  goto join12
:no11
  heap.give(px24)
  heap.give(py25)
  heap.give(pz26)
  heap.give(want27)
  goto join12
:join12
  calc px31 = clong.partsNew()
  calc py32 = clong.partsNew()
  calc pz33 = clong.partsNew()
  calc want34 = clong.partsNew()
  calc tol35 = prepareCase(t1, 1596, 4, t2, px31, py32, pz33, want34)
  when tol35 >= 0 yes13 no14
:yes13
  calc lx36 = longOfParts(px31)
  heap.give(py32)
  heap.give(pz33)
  calc r37 = acosLong(lx36)
  checkResult(r37, want34, tol35)
  goto join15
:no14
  heap.give(px31)
  heap.give(py32)
  heap.give(pz33)
  heap.give(want34)
  goto join15
:join15
  calc px38 = clong.partsNew()
  calc py39 = clong.partsNew()
  calc pz40 = clong.partsNew()
  calc want41 = clong.partsNew()
  calc tol42 = prepareCase(t1, 1596, 5, t2, px38, py39, pz40, want41)
  when tol42 >= 0 yes16 no17
:yes16
  calc lx43 = longOfParts(px38)
  heap.give(py39)
  heap.give(pz40)
  calc r44 = atanLong(lx43)
  checkResult(r44, want41, tol42)
  goto join18
:no17
  heap.give(px38)
  heap.give(py39)
  heap.give(pz40)
  heap.give(want41)
  goto join18
:join18
  calc px45 = clong.partsNew()
  calc py46 = clong.partsNew()
  calc pz47 = clong.partsNew()
  calc want48 = clong.partsNew()
  calc tol49 = prepareCase(t1, 1596, 6, t2, px45, py46, pz47, want48)
  when tol49 >= 0 yes19 no20
:yes19
  calc lx50 = longOfParts(px45)
  calc ly51 = longOfParts(py46)
  heap.give(pz47)
  calc r52 = atan2Long(lx50, ly51)
  checkResult(r52, want48, tol49)
  goto join21
:no20
  heap.give(px45)
  heap.give(py46)
  heap.give(pz47)
  heap.give(want48)
  goto join21
:join21
  calc px53 = clong.partsNew()
  calc py54 = clong.partsNew()
  calc pz55 = clong.partsNew()
  calc want56 = clong.partsNew()
  calc tol57 = prepareCase(t1, 1596, 7, t2, px53, py54, pz55, want56)
  when tol57 >= 0 yes22 no23
:yes22
  calc lx58 = longOfParts(px53)
  heap.give(py54)
  heap.give(pz55)
  calc r59 = expLong(lx58)
  checkResult(r59, want56, tol57)
  goto join24
:no23
  heap.give(px53)
  heap.give(py54)
  heap.give(pz55)
  heap.give(want56)
  goto join24
:join24
  calc px60 = clong.partsNew()
  calc py61 = clong.partsNew()
  calc pz62 = clong.partsNew()
  calc want63 = clong.partsNew()
  calc tol64 = prepareCase(t1, 1596, 8, t2, px60, py61, pz62, want63)
  when tol64 >= 0 yes25 no26
:yes25
  calc lx65 = longOfParts(px60)
  heap.give(py61)
  heap.give(pz62)
  calc r66 = exp2Long(lx65)
  checkResult(r66, want63, tol64)
  goto join27
:no26
  heap.give(px60)
  heap.give(py61)
  heap.give(pz62)
  heap.give(want63)
  goto join27
:join27
  calc px67 = clong.partsNew()
  calc py68 = clong.partsNew()
  calc pz69 = clong.partsNew()
  calc want70 = clong.partsNew()
  calc tol71 = prepareCase(t1, 1596, 9, t2, px67, py68, pz69, want70)
  when tol71 >= 0 yes28 no29
:yes28
  calc lx72 = longOfParts(px67)
  heap.give(py68)
  heap.give(pz69)
  calc r73 = expm1Long(lx72)
  checkResult(r73, want70, tol71)
  goto join30
:no29
  heap.give(px67)
  heap.give(py68)
  heap.give(pz69)
  heap.give(want70)
  goto join30
:join30
  calc px74 = clong.partsNew()
  calc py75 = clong.partsNew()
  calc pz76 = clong.partsNew()
  calc want77 = clong.partsNew()
  calc tol78 = prepareCase(t1, 1596, 10, t2, px74, py75, pz76, want77)
  when tol78 >= 0 yes31 no32
:yes31
  calc lx79 = longOfParts(px74)
  heap.give(py75)
  heap.give(pz76)
  calc r80 = logLong(lx79)
  checkResult(r80, want77, tol78)
  goto join33
:no32
  heap.give(px74)
  heap.give(py75)
  heap.give(pz76)
  heap.give(want77)
  goto join33
:join33
  calc px81 = clong.partsNew()
  calc py82 = clong.partsNew()
  calc pz83 = clong.partsNew()
  calc want84 = clong.partsNew()
  calc tol85 = prepareCase(t1, 1596, 11, t2, px81, py82, pz83, want84)
  when tol85 >= 0 yes34 no35
:yes34
  calc lx86 = longOfParts(px81)
  heap.give(py82)
  heap.give(pz83)
  calc r87 = log2Long(lx86)
  checkResult(r87, want84, tol85)
  goto join36
:no35
  heap.give(px81)
  heap.give(py82)
  heap.give(pz83)
  heap.give(want84)
  goto join36
:join36
  calc px88 = clong.partsNew()
  calc py89 = clong.partsNew()
  calc pz90 = clong.partsNew()
  calc want91 = clong.partsNew()
  calc tol92 = prepareCase(t1, 1596, 12, t2, px88, py89, pz90, want91)
  when tol92 >= 0 yes37 no38
:yes37
  calc lx93 = longOfParts(px88)
  heap.give(py89)
  heap.give(pz90)
  calc r94 = log10Long(lx93)
  checkResult(r94, want91, tol92)
  goto join39
:no38
  heap.give(px88)
  heap.give(py89)
  heap.give(pz90)
  heap.give(want91)
  goto join39
:join39
  calc px95 = clong.partsNew()
  calc py96 = clong.partsNew()
  calc pz97 = clong.partsNew()
  calc want98 = clong.partsNew()
  calc tol99 = prepareCase(t1, 1596, 13, t2, px95, py96, pz97, want98)
  when tol99 >= 0 yes40 no41
:yes40
  calc lx100 = longOfParts(px95)
  heap.give(py96)
  heap.give(pz97)
  calc r101 = log1pLong(lx100)
  checkResult(r101, want98, tol99)
  goto join42
:no41
  heap.give(px95)
  heap.give(py96)
  heap.give(pz97)
  heap.give(want98)
  goto join42
:join42
  calc px102 = clong.partsNew()
  calc py103 = clong.partsNew()
  calc pz104 = clong.partsNew()
  calc want105 = clong.partsNew()
  calc tol106 = prepareCase(t1, 1596, 14, t2, px102, py103, pz104, want105)
  when tol106 >= 0 yes43 no44
:yes43
  calc lx107 = longOfParts(px102)
  calc ly108 = longOfParts(py103)
  heap.give(pz104)
  calc r109 = powLong(lx107, ly108)
  checkResult(r109, want105, tol106)
  goto join45
:no44
  heap.give(px102)
  heap.give(py103)
  heap.give(pz104)
  heap.give(want105)
  goto join45
:join45
  calc px110 = clong.partsNew()
  calc py111 = clong.partsNew()
  calc pz112 = clong.partsNew()
  calc want113 = clong.partsNew()
  calc tol114 = prepareCase(t1, 1596, 15, t2, px110, py111, pz112, want113)
  when tol114 >= 0 yes46 no47
:yes46
  calc lx115 = longOfParts(px110)
  heap.give(py111)
  heap.give(pz112)
  calc r116 = cbrtLong(lx115)
  checkResult(r116, want113, tol114)
  goto join48
:no47
  heap.give(px110)
  heap.give(py111)
  heap.give(pz112)
  heap.give(want113)
  goto join48
:join48
  calc px117 = clong.partsNew()
  calc py118 = clong.partsNew()
  calc pz119 = clong.partsNew()
  calc want120 = clong.partsNew()
  calc tol121 = prepareCase(t1, 1596, 16, t2, px117, py118, pz119, want120)
  when tol121 >= 0 yes49 no50
:yes49
  calc lx122 = longOfParts(px117)
  calc ly123 = longOfParts(py118)
  heap.give(pz119)
  calc r124 = hypotLong(lx122, ly123)
  checkResult(r124, want120, tol121)
  goto join51
:no50
  heap.give(px117)
  heap.give(py118)
  heap.give(pz119)
  heap.give(want120)
  goto join51
:join51
  calc px125 = clong.partsNew()
  calc py126 = clong.partsNew()
  calc pz127 = clong.partsNew()
  calc want128 = clong.partsNew()
  calc tol129 = prepareCase(t1, 1596, 17, t2, px125, py126, pz127, want128)
  when tol129 >= 0 yes52 no53
:yes52
  calc lx130 = longOfParts(px125)
  heap.give(py126)
  heap.give(pz127)
  calc r131 = sinhLong(lx130)
  checkResult(r131, want128, tol129)
  goto join54
:no53
  heap.give(px125)
  heap.give(py126)
  heap.give(pz127)
  heap.give(want128)
  goto join54
:join54
  calc px132 = clong.partsNew()
  calc py133 = clong.partsNew()
  calc pz134 = clong.partsNew()
  calc want135 = clong.partsNew()
  calc tol136 = prepareCase(t1, 1596, 18, t2, px132, py133, pz134, want135)
  when tol136 >= 0 yes55 no56
:yes55
  calc lx137 = longOfParts(px132)
  heap.give(py133)
  heap.give(pz134)
  calc r138 = coshLong(lx137)
  checkResult(r138, want135, tol136)
  goto join57
:no56
  heap.give(px132)
  heap.give(py133)
  heap.give(pz134)
  heap.give(want135)
  goto join57
:join57
  calc px139 = clong.partsNew()
  calc py140 = clong.partsNew()
  calc pz141 = clong.partsNew()
  calc want142 = clong.partsNew()
  calc tol143 = prepareCase(t1, 1596, 19, t2, px139, py140, pz141, want142)
  when tol143 >= 0 yes58 no59
:yes58
  calc lx144 = longOfParts(px139)
  heap.give(py140)
  heap.give(pz141)
  calc r145 = tanhLong(lx144)
  checkResult(r145, want142, tol143)
  goto join60
:no59
  heap.give(px139)
  heap.give(py140)
  heap.give(pz141)
  heap.give(want142)
  goto join60
:join60
  calc px146 = clong.partsNew()
  calc py147 = clong.partsNew()
  calc pz148 = clong.partsNew()
  calc want149 = clong.partsNew()
  calc tol150 = prepareCase(t1, 1596, 20, t2, px146, py147, pz148, want149)
  when tol150 >= 0 yes61 no62
:yes61
  calc lx151 = longOfParts(px146)
  heap.give(py147)
  heap.give(pz148)
  calc r152 = asinhLong(lx151)
  checkResult(r152, want149, tol150)
  goto join63
:no62
  heap.give(px146)
  heap.give(py147)
  heap.give(pz148)
  heap.give(want149)
  goto join63
:join63
  calc px153 = clong.partsNew()
  calc py154 = clong.partsNew()
  calc pz155 = clong.partsNew()
  calc want156 = clong.partsNew()
  calc tol157 = prepareCase(t1, 1596, 21, t2, px153, py154, pz155, want156)
  when tol157 >= 0 yes64 no65
:yes64
  calc lx158 = longOfParts(px153)
  heap.give(py154)
  heap.give(pz155)
  calc r159 = acoshLong(lx158)
  checkResult(r159, want156, tol157)
  goto join66
:no65
  heap.give(px153)
  heap.give(py154)
  heap.give(pz155)
  heap.give(want156)
  goto join66
:join66
  calc px160 = clong.partsNew()
  calc py161 = clong.partsNew()
  calc pz162 = clong.partsNew()
  calc want163 = clong.partsNew()
  calc tol164 = prepareCase(t1, 1596, 22, t2, px160, py161, pz162, want163)
  when tol164 >= 0 yes67 no68
:yes67
  calc lx165 = longOfParts(px160)
  heap.give(py161)
  heap.give(pz162)
  calc r166 = atanhLong(lx165)
  checkResult(r166, want163, tol164)
  goto join69
:no68
  heap.give(px160)
  heap.give(py161)
  heap.give(pz162)
  heap.give(want163)
  goto join69
:join69
  calc px167 = clong.partsNew()
  calc py168 = clong.partsNew()
  calc pz169 = clong.partsNew()
  calc want170 = clong.partsNew()
  calc tol171 = prepareCase(t1, 1596, 23, t2, px167, py168, pz169, want170)
  when tol171 >= 0 yes70 no71
:yes70
  calc lx172 = longOfParts(px167)
  heap.give(py168)
  heap.give(pz169)
  calc r173 = erfLong(lx172)
  checkResult(r173, want170, tol171)
  goto join72
:no71
  heap.give(px167)
  heap.give(py168)
  heap.give(pz169)
  heap.give(want170)
  goto join72
:join72
  calc px174 = clong.partsNew()
  calc py175 = clong.partsNew()
  calc pz176 = clong.partsNew()
  calc want177 = clong.partsNew()
  calc tol178 = prepareCase(t1, 1596, 24, t2, px174, py175, pz176, want177)
  when tol178 >= 0 yes73 no74
:yes73
  calc lx179 = longOfParts(px174)
  heap.give(py175)
  heap.give(pz176)
  calc r180 = erfcLong(lx179)
  checkResult(r180, want177, tol178)
  goto join75
:no74
  heap.give(px174)
  heap.give(py175)
  heap.give(pz176)
  heap.give(want177)
  goto join75
:join75
  calc px181 = clong.partsNew()
  calc py182 = clong.partsNew()
  calc pz183 = clong.partsNew()
  calc want184 = clong.partsNew()
  calc tol185 = prepareCase(t1, 1596, 25, t2, px181, py182, pz183, want184)
  when tol185 >= 0 yes76 no77
:yes76
  calc lx186 = longOfParts(px181)
  heap.give(py182)
  heap.give(pz183)
  calc r187 = tgammaLong(lx186)
  checkResult(r187, want184, tol185)
  goto join78
:no77
  heap.give(px181)
  heap.give(py182)
  heap.give(pz183)
  heap.give(want184)
  goto join78
:join78
  calc px188 = clong.partsNew()
  calc py189 = clong.partsNew()
  calc pz190 = clong.partsNew()
  calc want191 = clong.partsNew()
  calc tol192 = prepareCase(t1, 1596, 26, t2, px188, py189, pz190, want191)
  when tol192 >= 0 yes79 no80
:yes79
  calc lx193 = longOfParts(px188)
  heap.give(py189)
  heap.give(pz190)
  calc r194 = lgammaLong(lx193)
  checkResult(r194, want191, tol192)
  goto join81
:no80
  heap.give(px188)
  heap.give(py189)
  heap.give(pz190)
  heap.give(want191)
  goto join81
:join81
  calc px195 = clong.partsNew()
  calc py196 = clong.partsNew()
  calc pz197 = clong.partsNew()
  calc want198 = clong.partsNew()
  calc tol199 = prepareCase(t1, 1596, 27, t2, px195, py196, pz197, want198)
  when tol199 >= 0 yes82 no83
:yes82
  calc lx200 = longOfParts(px195)
  calc ly201 = longOfParts(py196)
  calc lz202 = longOfParts(pz197)
  calc r203 = fusedMultiplyAddLong(lx200, ly201, lz202)
  checkResult(r203, want198, tol199)
  goto join84
:no83
  heap.give(px195)
  heap.give(py196)
  heap.give(pz197)
  heap.give(want198)
  goto join84
:join84
  calc cell204 = heap.take(16)
  calc half205 = makeLong(0, 5, -1)
  calc value206 = logGammaSignedLong(half205, cell204)
  calc sign207 = machine.loadInt32(cell204)
  test.assertTrue(sign207 == 1)
  calc negative208 = makeLong(1, 1, -1)
  calc value209 = logGammaSignedLong(negative208, cell204)
  calc sign210 = machine.loadInt32(cell204)
  test.assertTrue(sign210 == convert.int64ToInt32(0 - 1))
  heap.give(cell204)
  return
