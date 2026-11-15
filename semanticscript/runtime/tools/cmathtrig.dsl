module cmathtrig "The trigonometric functions of math.h written in SemanticScript: sin, cos, tan, asin, acos, atan, atan2 and their f forms, with Payne-Hanek reduction (D-153)"
  path cmathtrig
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel clibrary
  exports sineOf cosineOf tangentOf arcSineOf arcCosineOf arcTangentOf arcTangent2Of

capability memoryAccess "Authority to keep a reduced argument and a pair of doubles in machine.state" use machine.memory none

## atan of a magnitude above 2^64 is pi/2 to the last place (1/x is below 2^-64, the double pi/2 is 6.1e-17 from it and half a unit in
## the last place is 1.1e-16).
## machine.state bytes 25344 to 25599 belong to this module (the coordinator's allotment): 25344 the high double of a
## reduced argument, 25352 its low double, 25360 its quadrant, 25368 and 25376 the two doubles an arctangent step
## gives, and from 25408 thirteen 64-bit words that hold a Payne-Hanek product (32 bits of each).
##
## The method. Every function works in doubles and double-doubles (an unevaluated sum of two doubles, about 106 bits)
## and rounds once at the end, so a result is within 0.51 ulp of the exact one for sin, cos, tan, asin, acos, atan,
## and atan2, apart from the last-place effects of the kernels (measured in tests/test_c_cmathtrig.py: 0.64 ulp at
## most, 1 ulp promised). The float forms compute the double and narrow it, which is correct to 0.5 ulp and a
## rounding that double rounding could in theory spoil only in 1 case in 2^29.
## - Argument reduction. A double up to pi/4 needs none. Up to 1.6 million it is Cody and Waite's: n is x*(2/pi)
##   rounded with the 1.5*2^52 trick, and x - n*pi/2 is summed in pieces of pi/2 whose first three have 33 bits each
##   (so that n times a piece is exact) and whose fourth has 53, with every rounding error of the sums caught
##   (Knuth's two-sum) and added in last. Above that it is Payne and Hanek's: the bits of 2/pi (computed by
##   tools/cmathtriggen.py with Python integers, from pi by Machin's formula) are multiplied by the 53-bit
##   significand in 32-bit limbs, 288 bits of window, which gives the quadrant and a fraction to about 2^-170 absolute;
##   the fraction is cut to 106 bits and multiplied by pi/2 in three doubles. The same code serves every double up to
##   1.8e308 and every float.
## - Kernels. sin and cos are Taylor polynomials in r*r on |r| <= pi/4 (the coefficients are the exact 1/k! rounded
##   to doubles), with the first terms and the reduction's low part treated in double-double arithmetic; tan is the
##   same with a 32-term polynomial, and in an odd quadrant -1/tan is taken with a correction for the division's
##   rounding. Dekker's splitting (the constant 2^27+1) gives exact products.
## - Inverse functions. atan(u) for u up to 8 subtracts the nearest of the 65 tabulated atan(k/8) (each a
##   double-double): atan(u) = atan(k/8) + atan(w), w = (u - k/8)/(1 + u*k/8) a double-double of at most 1/16, and
##   atan(w) is a short Taylor series; above 8 it is pi/2 - atan(1/u). asin(x) = atan(x/sqrt(1-x*x)) and
##   acos(x) = atan(sqrt(1-x*x)/x), both with the square root in double-double; atan2 divides in double-double, so
##   it is atan(|y|/|x|) rounded once and put in its quadrant (Annex F's cases first, exactly).
## The method follows the published ones (Payne and Hanek 1983; Cody and Waite; Dekker 1971 and Knuth for the
## double-double pieces; the shape of the kernels is musl's and the FreeBSD msun's, which are MIT licensed), with
## its own coefficients and bookkeeping.

constant scratchAt "Where this module's scratch starts, in machine.state" Int64 25344

constant slotHigh "The high double of a reduced argument" Int64 0

constant slotLow "The low double of a reduced argument" Int64 8

constant slotQuadrant "The quadrant of a reduced argument" Int64 16

constant slotPairHigh "The high double of the pair a step gives" Int64 24

constant slotPairLow "The low double of the pair a step gives" Int64 32

constant slotProduct "The first word of the Payne-Hanek product" Int64 64

constant domainError "EDOM: an argument outside the function's domain" Int32 33

## ---------------------------------------------------------------- scratch

op storeReal "Keep a double in the scratch"
  input offset Int64 copied
  input value Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + offset)
  storeIt: machine.storeFloat64(place, value)
  return

op loadReal "The double kept in the scratch"
  input offset Int64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + offset)
  calc value = machine.loadFloat64(place)
  return value

op storeWord "Keep a 64-bit word in the scratch"
  input offset Int64 copied
  input value UInt64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + offset)
  storeIt: machine.storeUInt64(place, value)
  return

op loadWord "The 64-bit word kept in the scratch"
  input offset Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + offset)
  calc value = machine.loadUInt64(place)
  return value

op storePair "Keep the two doubles a step gives"
  input high Float64 copied
  input low Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  keepHigh: storeReal(slotPairHigh, high)
  keepLow: storeReal(slotPairLow, low)
  return

op storeReduction "Keep a reduced argument: its quadrant and its two doubles"
  input quadrant Int64 copied
  input high Float64 copied
  input low Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + slotQuadrant)
  keepQuadrant: machine.storeInt64(place, quadrant)
  keepHigh: storeReal(slotHigh, high)
  keepLow: storeReal(slotLow, low)
  return

op loadQuadrant "The quadrant of the reduced argument"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = kernel.stateAt(scratchAt + slotQuadrant)
  calc value = machine.loadInt64(place)
  return value

## ---------------------------------------------------------------- double-double pieces

op sumError "The error of s = a + b in doubles, exactly (Knuth's two-sum): a + b = s + error"
  input a Float64 copied
  input b Float64 copied
  input s Float64 copied
  output Float64
:begin
  calc virtual = s - a
  calc error = (a - (s - virtual)) + (b - virtual)
  return error

op quickSumError "The error of s = a + b when a is not smaller in magnitude than b (Dekker's fast two-sum)"
  input a Float64 copied
  input b Float64 copied
  input s Float64 copied
  output Float64
:begin
  calc error = b - (s - a)
  return error

op highPart "The top 26 bits of a double (Dekker's split by 2^27 + 1)"
  input a Float64 copied
  output Float64
:begin
  calc scaled = 134217729.0 * a
  calc high = scaled - (scaled - a)
  return high

op productError "The error of p = a * b, exactly (Dekker's product): a * b = p + error"
  input a Float64 copied
  input b Float64 copied
  input p Float64 copied
  output Float64
:begin
  calc aHigh = highPart(a)
  calc aLow = a - aHigh
  calc bHigh = highPart(b)
  calc bLow = b - bHigh
  calc error = (((aHigh * bHigh - p) + aHigh * bLow) + aLow * bHigh) + aLow * bLow
  return error

op powerOfTwo "2 to a power from -1022 to 1023"
  input power Int64 copied
  output Float64
:begin
  calc field = convert.int64ToUInt64((power + 1023) << 52)
  calc value = convert.uint64BitsToFloat64(field)
  return value

op plusOrMinus "1.0, or -1.0 when asked for the negative"
  input negative Bool copied
  output Float64
  let oneReal Float64 1.0
  let minusOne Float64 -1.0
:begin
  if negative minus plus
:minus
  return minusOne
:plus
  return oneReal

## ---------------------------------------------------------------- tables and polynomials (tools/cmathtriggen.py writes these)

## @generated polynomials
op sinPoly "The Taylor coefficients of sin past x, in z = x*x: c3 + c5 z + ... to x^19 (exact 1/k! rounded to doubles)"
  input z Float64 copied
  output Float64
:begin
  calc value = ((((((((-0x1.2f49b46814157p-57) * z + 0x1.952c77030ad4ap-49) * z + -0x1.ae7f3e733b81fp-41) * z + 0x1.6124613a86d09p-33) * z + -0x1.ae64567f544e4p-26) * z + 0x1.71de3a556c734p-19) * z + -0x1.a01a01a01a01ap-13) * z + 0x1.1111111111111p-7) * z + -0x1.5555555555555p-3
  return value

op cosPoly "The Taylor coefficients of cos from x^4, in z = x*x: c4 + c6 z + ... to x^18"
  input z Float64 copied
  output Float64
:begin
  calc value = (((((((-0x1.6827863b97d97p-53) * z + 0x1.ae7f3e733b81fp-45) * z + -0x1.93974a8c07c9dp-37) * z + 0x1.1eed8eff8d898p-29) * z + -0x1.27e4fb7789f5cp-22) * z + 0x1.a01a01a01a01ap-16) * z + -0x1.6c16c16c16c17p-10) * z + 0x1.5555555555555p-5
  return value

op tanPoly "The series of tan from x^5, in z = x*x, to x^63 (exact, from the division of the series of sin by cos's)"
  input z Float64 copied
  output Float64
:begin
  calc value = (((((((((((((((((((((((((((((0x1.3c1a3035e663dp-41) * z + 0x1.85f9bf8d6b2b2p-40) * z + 0x1.e11cf33c632a8p-39) * z + 0x1.28c65557ea2a5p-37) * z + 0x1.6e2193ae496d5p-36) * z + 0x1.c3b23b05e39f9p-35) * z + 0x1.16a101c5fde96p-33) * z + 0x1.57bea2950f11ep-32) * z + 0x1.a813f6eaa7058p-31) * z + 0x1.0597b61cb3092p-29) * z + 0x1.42ba1a349b490p-28) * z + 0x1.8e25ff9327e2cp-27) * z + 0x1.eb3229047434cp-26) * z + 0x1.2efe8db3aff1fp-24) * z + 0x1.75cde6563fed9p-23) * z + 0x1.cd299de4ae6bbp-22) * z + 0x1.1c77df95c1c0dp-20) * z + 0x1.5ef2da474e5b7p-19) * z + 0x1.b0f72d3ee24e9p-18) * z + 0x1.0b132d39a6050p-16) * z + 0x1.497d8eea25259p-15) * z + 0x1.967e18afcafadp-14) * z + 0x1.f57d7734d1664p-13) * z + 0x1.3558248036744p-11) * z + 0x1.7da36452b75e3p-10) * z + 0x1.d6d3d0e157de0p-9) * z + 0x1.226e355e6c23dp-7) * z + 0x1.664f4882c10fap-6) * z + 0x1.ba1ba1ba1ba1cp-5) * z + 0x1.1111111111111p-3
  return value

op atanPoly "The Taylor coefficients of atan from x^3, in z = x*x: -1/3 + z/5 - ... to x^21"
  input z Float64 copied
  output Float64
:begin
  calc value = (((((((((0x1.8618618618618p-5) * z + -0x1.af286bca1af28p-5) * z + 0x1.e1e1e1e1e1e1ep-5) * z + -0x1.1111111111111p-4) * z + 0x1.3b13b13b13b14p-4) * z + -0x1.745d1745d1746p-4) * z + 0x1.c71c71c71c71cp-4) * z + -0x1.2492492492492p-3) * z + 0x1.999999999999ap-3) * z + -0x1.5555555555555p-2
  return value
## @end polynomials

## @generated tables
## 2/pi: 41 limbs of 32 bits after two limbs of zeros (so that an index never goes below 0)
op twoOverPiLimb "A 32-bit limb of the bits of 2/pi, after two limbs of zeros"
  input index Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let text String "0000000000000000a2f9836e4e441529fc2757d1f534ddc0db6295993c439041fe5163abdebbc561b7246e3a424dd2e006492eea09d1921cfe1deb1cb129a73ee88235f52ebb4484e99c7026b45f7e413991d639835339f49c845f8bbdf9283b1ff897ffde05980fef2f118b5a0a6d1f6d367ecf27cb09b74f463f669e5fea2d7527bac7ebe5f17b3d0739f78a5292ea6bfb5fb11f8d5d0856033046fc7b6babf0cfbc209af4361da9e39161"
:begin
  calc base = machine.addressOfString(text)
  calc value = hexWord(base, index * 8, 8)
  return value

## the bits of the 65 pairs (high, low) of doubles that sum to atan(k/8)
op atanEntry "A double of the arctangent table: entry 2k is the high part of atan(k/8) and 2k+1 its low part"
  input index Int64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let text String "000000000000000000000000000000003fbfd5ba9aac2f6ebc4cd37686760c173fcf5b75f92c80dd3c68ab6e3cf7afbd3fd6f61941e4def1bc7c63aae6f6e9183fddac670561bb4f3c7a2b7f222f65e23fe1e00babdefeb4bc5928df287a668f3fe4978fa3269ee13c72419a87f2a4583fe700a7c5784634bc78c34d25aadef63fe921fb54442d183c81a62633145c073feb034f38649c88bc8be88d6936f8333fecac7c57846f9e3c80dae13ad18a6b3fee24dd44c855d13c8f7ac612ab33d83fef730bd281f69b3c7007887af0cbbd3ff04e67277a01d73c67115496c13eb63ff0d38f2c5ba09fbc9bd0dc231bfd703ff14b1dd5f90ce1bc7212d570a63fa23ff1b6e192ebbe443c9b1b466a88828e3ff21862f3fade363c94887628d687483ff270ef55a53a25bc9a66b1af5f84fb3ff2c1a241d66dc33c982b2d58b6a8e93ff30b6d796a4da83c96254cb03bb1993ff34f1fbb19eb093c880d79b4cf61d53ff38d6a6ce13353bc812c77e8a80f5c3ff3c6e650b380473c96b63b358e746d3ff3fc176b7a8560bc4441a3bd3f10833ff42d70411f9ec13c82b08db7f108963ff45b54837351a03c79e4a72eedacc43ff4861b4cfbe710bc6567d3d25932d13ff4ae10fc6589a5bc93b03e8a27f5553ff4d378c1999a0dbc6c857a639541c83ff4f68dea6726173c9934f9f2b0020e3ff51784fa1544babc9236e3c857c0193ff5368c951e9cfdbc996f47948a99f13ff553ce48a04765bc8fb2a15b01af763ff56f6f33a3e6a7bc7df6edd6f1ec3b3ff58990974dfc9bbc938724877fdf563ff5a25052114e603c78c2d0c89de2183ff5b9c9494c0d73bc7dbb3cb11f72ae3ff5d013c41adabd3c9f82bba194dd5d3ff5e545b9b1a4c8bc9b1f8afb3dd31d3ff5f97315254857bc831151a43b51ca3ff60cadf03e444dbc91cafc7209e76b3ff61f06c6a92b89bc8487d50bceb1a53ff6308ca2a1ee293c869afbaa88c2dc3ff6414d44094c7cbc9c5f60a65c73973ff6515542adf35b3c91abca6117c6553ff660b02c736a06bc7acb6afb332a0f3ff66f689fe6ecd73c7296b3ad3ab6da3ff67d8863bc99bdbc99b7bd2e1e8c9c3ff68b187b9d2c61bc9e65414ed76ae63ff698213a9d5053bc9b9839085189e33ff6a4aa53aac449bc84371a18cdc2a73ff6b0bae830c070bc97d1ab82ffb70b3ff6bc59952bf3b13c7977d7c13d209c3ff6c78c7edeb1953c99239ad620ffe23ff6d2595b4f59433c96d3e45139467e3ff6dcc57bb565fdbc929c86447928e73ff6e6d5d4f4d24b3c5bc3dadd1ee93f3ff6f08f07435fecbc8957a7170df0163ff6f9f5650fd3ef3c99b070ed3f43e43ff7030cf9403197bc7cbe18962216083ff70bd98cd964333c5a965f981024a83ff7145eac2088a4bc9fda5797b32a0b3ff71c9fab4414b23c9ed22abd9c91bc3ff7249faa996a213c9a8cc1e7480c68"
:begin
  calc base = machine.addressOfString(text)
  calc field = hexWord(base, index * 16, 16)
  calc value = convert.uint64BitsToFloat64(field)
  return value
## @end tables

op hexWord "Read digits of lower-case hexadecimal text as a number"
  input base machine.Address copied
  input start Int64 copied
  input digits Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let value UInt64 0 mut
  let at Int64 0 mut
  let sixteen Int64 16
:begin
  calc at := start
  calc stop = start + digits
  goto eachDigit
:eachDigit loop=while max=sixteen
  when at < stop digit finish
:digit in=eachDigit
  calc place = base + at
  calc letter = convert.byteToInt64(machine.loadByte(place))
  calc nibble = (letter & 15) + 9 * (letter >> 6)
  calc value := (value << 4) | convert.int64ToUInt64(nibble)
  calc at := at + 1
  goto eachDigit
:finish
  return value

## ---------------------------------------------------------------- Payne-Hanek reduction

op clampBits "A number of bits held to 0 to 32"
  input value Int64 copied
  output Int64
  let zero Int64 0
  let thirtyTwo Int64 32
:begin
  when value < 0 floor checkTop
:floor
  return zero
:checkTop
  when value > 32 all some
:all
  return thirtyTwo
:some
  return value

op floorLog2 "The place of the top set bit of a positive number below 2^32"
  input value UInt64 copied
  output Int64
:begin
  calc approx = convert.int64ToFloat64(convert.uint64ToInt64(value))
  calc field = convert.float64BitsToUInt64(approx)
  calc place = convert.uint64ToInt64(field >> 52) - 1023
  return place

op fieldBits "Up to 64 bits of the product from a bit place, as a number"
  input place Int64 copied
  input count Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let field UInt64 0 mut
  let bitOne UInt64 1
:begin
  calc index = place >> 5
  calc shift = place & 31
  calc base = slotProduct + index * 8
  calc first = loadWord(base)
  calc second = loadWord(base + 8)
  calc third = loadWord(base + 16)
  calc joined = (first | (second << 32)) >> shift
  when shift == 0 aligned unaligned
:aligned
  calc field := joined
  goto limit
:unaligned
  calc extra = third << (64 - shift)
  calc field := joined | extra
  goto limit
:limit
  when count < 64 narrow whole
:narrow
  calc mask = (bitOne << count) - 1
  calc narrowed = field & mask
  return narrowed
:whole
  return field

## @generated rows
op multiplyWindow "Multiply the significand by nine limbs of 2/pi from limb `start` on, into the product words of the scratch (32 bits each)"
  input mantissa UInt64 copied
  input start Int64 copied
  effect use machine.memory
  uses memoryAccess
  let carry UInt64 0 mut
:begin
  calc low = mantissa & 4294967295
  calc high = mantissa >> 32
  calc limb0 = twoOverPiLimb(start + 8)
  calc total0 = low * limb0 + carry
  keep0: storeWord(slotProduct + 0, total0 & 4294967295)
  calc carry := total0 >> 32
  calc limb1 = twoOverPiLimb(start + 7)
  calc total1 = low * limb1 + carry
  keep1: storeWord(slotProduct + 8, total1 & 4294967295)
  calc carry := total1 >> 32
  calc limb2 = twoOverPiLimb(start + 6)
  calc total2 = low * limb2 + carry
  keep2: storeWord(slotProduct + 16, total2 & 4294967295)
  calc carry := total2 >> 32
  calc limb3 = twoOverPiLimb(start + 5)
  calc total3 = low * limb3 + carry
  keep3: storeWord(slotProduct + 24, total3 & 4294967295)
  calc carry := total3 >> 32
  calc limb4 = twoOverPiLimb(start + 4)
  calc total4 = low * limb4 + carry
  keep4: storeWord(slotProduct + 32, total4 & 4294967295)
  calc carry := total4 >> 32
  calc limb5 = twoOverPiLimb(start + 3)
  calc total5 = low * limb5 + carry
  keep5: storeWord(slotProduct + 40, total5 & 4294967295)
  calc carry := total5 >> 32
  calc limb6 = twoOverPiLimb(start + 2)
  calc total6 = low * limb6 + carry
  keep6: storeWord(slotProduct + 48, total6 & 4294967295)
  calc carry := total6 >> 32
  calc limb7 = twoOverPiLimb(start + 1)
  calc total7 = low * limb7 + carry
  keep7: storeWord(slotProduct + 56, total7 & 4294967295)
  calc carry := total7 >> 32
  calc limb8 = twoOverPiLimb(start + 0)
  calc total8 = low * limb8 + carry
  keep8: storeWord(slotProduct + 64, total8 & 4294967295)
  calc carry := total8 >> 32
  keepCarry: storeWord(slotProduct + 72, carry)
  calc carry := 0
  calc limbB0 = twoOverPiLimb(start + 8)
  calc totalB0 = high * limbB0 + loadWord(slotProduct + 8) + carry
  keepB0: storeWord(slotProduct + 8, totalB0 & 4294967295)
  calc carry := totalB0 >> 32
  calc limbB1 = twoOverPiLimb(start + 7)
  calc totalB1 = high * limbB1 + loadWord(slotProduct + 16) + carry
  keepB1: storeWord(slotProduct + 16, totalB1 & 4294967295)
  calc carry := totalB1 >> 32
  calc limbB2 = twoOverPiLimb(start + 6)
  calc totalB2 = high * limbB2 + loadWord(slotProduct + 24) + carry
  keepB2: storeWord(slotProduct + 24, totalB2 & 4294967295)
  calc carry := totalB2 >> 32
  calc limbB3 = twoOverPiLimb(start + 5)
  calc totalB3 = high * limbB3 + loadWord(slotProduct + 32) + carry
  keepB3: storeWord(slotProduct + 32, totalB3 & 4294967295)
  calc carry := totalB3 >> 32
  calc limbB4 = twoOverPiLimb(start + 4)
  calc totalB4 = high * limbB4 + loadWord(slotProduct + 40) + carry
  keepB4: storeWord(slotProduct + 40, totalB4 & 4294967295)
  calc carry := totalB4 >> 32
  calc limbB5 = twoOverPiLimb(start + 3)
  calc totalB5 = high * limbB5 + loadWord(slotProduct + 48) + carry
  keepB5: storeWord(slotProduct + 48, totalB5 & 4294967295)
  calc carry := totalB5 >> 32
  calc limbB6 = twoOverPiLimb(start + 2)
  calc totalB6 = high * limbB6 + loadWord(slotProduct + 56) + carry
  keepB6: storeWord(slotProduct + 56, totalB6 & 4294967295)
  calc carry := totalB6 >> 32
  calc limbB7 = twoOverPiLimb(start + 1)
  calc totalB7 = high * limbB7 + loadWord(slotProduct + 64) + carry
  keepB7: storeWord(slotProduct + 64, totalB7 & 4294967295)
  calc carry := totalB7 >> 32
  calc limbB8 = twoOverPiLimb(start + 0)
  calc totalB8 = high * limbB8 + loadWord(slotProduct + 72) + carry
  keepB8: storeWord(slotProduct + 72, totalB8 & 4294967295)
  calc carry := totalB8 >> 32
  keepCarryB: storeWord(slotProduct + 80, carry)
  clearA: storeWord(slotProduct + 88, 0)
  clearB: storeWord(slotProduct + 96, 0)
  return

op maskFraction "Clear the product's bits from place `fractionBits` up, keeping the fraction"
  input fractionBits Int64 copied
  effect use machine.memory
  uses memoryAccess
  let bitOne UInt64 1
:begin
  calc kept0 = clampBits(fractionBits - 0)
  calc mask0 = (bitOne << kept0) - 1
  mask0Word: storeWord(slotProduct + 0, loadWord(slotProduct + 0) & mask0)
  calc kept1 = clampBits(fractionBits - 32)
  calc mask1 = (bitOne << kept1) - 1
  mask1Word: storeWord(slotProduct + 8, loadWord(slotProduct + 8) & mask1)
  calc kept2 = clampBits(fractionBits - 64)
  calc mask2 = (bitOne << kept2) - 1
  mask2Word: storeWord(slotProduct + 16, loadWord(slotProduct + 16) & mask2)
  calc kept3 = clampBits(fractionBits - 96)
  calc mask3 = (bitOne << kept3) - 1
  mask3Word: storeWord(slotProduct + 24, loadWord(slotProduct + 24) & mask3)
  calc kept4 = clampBits(fractionBits - 128)
  calc mask4 = (bitOne << kept4) - 1
  mask4Word: storeWord(slotProduct + 32, loadWord(slotProduct + 32) & mask4)
  calc kept5 = clampBits(fractionBits - 160)
  calc mask5 = (bitOne << kept5) - 1
  mask5Word: storeWord(slotProduct + 40, loadWord(slotProduct + 40) & mask5)
  calc kept6 = clampBits(fractionBits - 192)
  calc mask6 = (bitOne << kept6) - 1
  mask6Word: storeWord(slotProduct + 48, loadWord(slotProduct + 48) & mask6)
  calc kept7 = clampBits(fractionBits - 224)
  calc mask7 = (bitOne << kept7) - 1
  mask7Word: storeWord(slotProduct + 56, loadWord(slotProduct + 56) & mask7)
  calc kept8 = clampBits(fractionBits - 256)
  calc mask8 = (bitOne << kept8) - 1
  mask8Word: storeWord(slotProduct + 64, loadWord(slotProduct + 64) & mask8)
  return

op negateFraction "Replace the product's nine low limbs by their two's complement"
  effect use machine.memory
  uses memoryAccess
  let carry UInt64 1 mut
:begin
  calc word0 = loadWord(slotProduct + 0)
  calc total0 = ((~word0) & 4294967295) + carry
  keep0: storeWord(slotProduct + 0, total0 & 4294967295)
  calc carry := total0 >> 32
  calc word1 = loadWord(slotProduct + 8)
  calc total1 = ((~word1) & 4294967295) + carry
  keep1: storeWord(slotProduct + 8, total1 & 4294967295)
  calc carry := total1 >> 32
  calc word2 = loadWord(slotProduct + 16)
  calc total2 = ((~word2) & 4294967295) + carry
  keep2: storeWord(slotProduct + 16, total2 & 4294967295)
  calc carry := total2 >> 32
  calc word3 = loadWord(slotProduct + 24)
  calc total3 = ((~word3) & 4294967295) + carry
  keep3: storeWord(slotProduct + 24, total3 & 4294967295)
  calc carry := total3 >> 32
  calc word4 = loadWord(slotProduct + 32)
  calc total4 = ((~word4) & 4294967295) + carry
  keep4: storeWord(slotProduct + 32, total4 & 4294967295)
  calc carry := total4 >> 32
  calc word5 = loadWord(slotProduct + 40)
  calc total5 = ((~word5) & 4294967295) + carry
  keep5: storeWord(slotProduct + 40, total5 & 4294967295)
  calc carry := total5 >> 32
  calc word6 = loadWord(slotProduct + 48)
  calc total6 = ((~word6) & 4294967295) + carry
  keep6: storeWord(slotProduct + 48, total6 & 4294967295)
  calc carry := total6 >> 32
  calc word7 = loadWord(slotProduct + 56)
  calc total7 = ((~word7) & 4294967295) + carry
  keep7: storeWord(slotProduct + 56, total7 & 4294967295)
  calc carry := total7 >> 32
  calc word8 = loadWord(slotProduct + 64)
  calc total8 = ((~word8) & 4294967295) + carry
  keep8: storeWord(slotProduct + 64, total8 & 4294967295)
  calc carry := total8 >> 32
  return

op highestBit "The place of the highest set bit of the product's nine low limbs, or -1 when they are all 0"
  output Int64
  effect use machine.memory
  uses memoryAccess
  let minusOne Int64 -1
:begin
  calc word8 = loadWord(slotProduct + 64)
  when word8 != 0 found8 next8
:found8
  calc place8 = floorLog2(word8) + 256
  return place8
:next8
  calc word7 = loadWord(slotProduct + 56)
  when word7 != 0 found7 next7
:found7
  calc place7 = floorLog2(word7) + 224
  return place7
:next7
  calc word6 = loadWord(slotProduct + 48)
  when word6 != 0 found6 next6
:found6
  calc place6 = floorLog2(word6) + 192
  return place6
:next6
  calc word5 = loadWord(slotProduct + 40)
  when word5 != 0 found5 next5
:found5
  calc place5 = floorLog2(word5) + 160
  return place5
:next5
  calc word4 = loadWord(slotProduct + 32)
  when word4 != 0 found4 next4
:found4
  calc place4 = floorLog2(word4) + 128
  return place4
:next4
  calc word3 = loadWord(slotProduct + 24)
  when word3 != 0 found3 next3
:found3
  calc place3 = floorLog2(word3) + 96
  return place3
:next3
  calc word2 = loadWord(slotProduct + 16)
  when word2 != 0 found2 next2
:found2
  calc place2 = floorLog2(word2) + 64
  return place2
:next2
  calc word1 = loadWord(slotProduct + 8)
  when word1 != 0 found1 next1
:found1
  calc place1 = floorLog2(word1) + 32
  return place1
:next1
  calc word0 = loadWord(slotProduct + 0)
  when word0 != 0 found0 next0
:found0
  calc place0 = floorLog2(word0) + 0
  return place0
:next0
  return minusOne
## @end rows

op reduceHuge "Payne and Hanek: a finite double of 1.6e6 or more reduced to a quadrant and a double-double in [-pi/4, pi/4]"
  input a Float64 copied
  effect use machine.memory
  uses memoryAccess
  let zeroReal Float64 0.0
:begin
  calc bitsOfA = convert.float64BitsToUInt64(a)
  calc exponentField = convert.uint64ToInt64((bitsOfA >> 52) & 2047)
  calc mantissa = (bitsOfA & 4503599627370495) | 4503599627370496
  calc exponent = exponentField - 1075
  calc start = (exponent + 62) >> 5
  calc shiftBits = exponent - ((start - 2) << 5)
  multiplyIt: multiplyWindow(mantissa, start)
  calc fractionBits = 288 - shiftBits
  calc integerPart = fieldBits(fractionBits, 2)
  calc topBit = fieldBits(fractionBits - 1, 1)
  calc negative = topBit != 0
  when negative complement keep
:complement
  negateIt: negateFraction()
  goto masked
:keep
  goto masked
:masked
  maskIt: maskFraction(fractionBits)
  calc quadrant = convert.uint64ToInt64((integerPart + topBit) & 3)
  calc position = highestBit()
  when position < 0 nothing found
:nothing
  storeNothing: storeReduction(quadrant, zeroReal, zeroReal)
  return
:found
  calc top = fieldBits(position - 63, 64)
  calc next = fieldBits(position - 127, 64)
  calc highInt = top >> 11
  calc lowInt = ((top & 2047) << 42) | (next >> 22)
  calc scaleExponent = position - 52 - fractionBits
  calc scaledHigh = convert.int64ToFloat64(convert.uint64ToInt64(highInt)) * powerOfTwo(scaleExponent)
  calc scaledLow = convert.int64ToFloat64(convert.uint64ToInt64(lowInt)) * powerOfTwo(scaleExponent - 53)
  calc product = scaledHigh * 0x1.921fb54442d18p+0
  calc productLow = productError(scaledHigh, 0x1.921fb54442d18p+0, product)
  calc cross = (scaledHigh * 0x1.1a62633145c07p-54 + scaledLow * 0x1.921fb54442d18p+0) + scaledHigh * -0x1.f1976b7ed8fbcp-110
  calc rest = productLow + cross
  calc reducedHigh = product + rest
  calc reducedLow = quickSumError(product, rest, reducedHigh)
  when negative flipped plain
:flipped
  calc highMinus = -reducedHigh
  calc lowMinus = -reducedLow
  storeMinus: storeReduction(quadrant, highMinus, lowMinus)
  return
:plain
  storePlus: storeReduction(quadrant, reducedHigh, reducedLow)
  return

## ---------------------------------------------------------------- Cody-Waite reduction and the dispatch

op reduceMedium "Cody and Waite: a double from pi/4 up to 1.6e6 reduced to a quadrant and a double-double"
  input a Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc multiple = (a * 0x1.45f306dc9c883p-1 + 6755399441055744.0) - 6755399441055744.0
  calc count = convert.float64ToInt64(multiple)
  calc first = a - multiple * 0x1.921fb54400000p+0
  calc minusSecond = -(multiple * 0x1.0b4611a600000p-34)
  calc sum1 = first + minusSecond
  calc error1 = sumError(first, minusSecond, sum1)
  calc minusThird = -(multiple * 0x1.3198a2e000000p-69)
  calc sum2 = sum1 + minusThird
  calc error2 = sumError(sum1, minusThird, sum2)
  calc minusFourth = -(multiple * 0x1.b839a252049c1p-104)
  calc sum3 = sum2 + minusFourth
  calc error3 = sumError(sum2, minusFourth, sum3)
  calc errors = (error1 + error2) + error3
  calc reducedHigh = sum3 + errors
  calc reducedLow = quickSumError(sum3, errors, reducedHigh)
  storeIt: storeReduction(count & 3, reducedHigh, reducedLow)
  return

op reduceArgument "Reduce a finite non-negative double to a quadrant and a double-double in [-pi/4, pi/4], kept in the scratch"
  input a Float64 copied
  effect use machine.memory
  uses memoryAccess
  let zeroReal Float64 0.0
:begin
  when a <= 0x1.921fb54442d18p-1 near notNear
:near
  storeNear: storeReduction(noQuadrant=0, a, zeroReal)
  return
:notNear
  when a < 1600000.0 medium huge
:medium
  doMedium: reduceMedium(a)
  return
:huge
  doHuge: reduceHuge(a)
  return

## ---------------------------------------------------------------- sin, cos, tan kernels

op sineKernel "sin of the double-double (high, low), high within pi/4"
  input high Float64 copied
  input low Float64 copied
  output Float64
:begin
  calc z = high * high
  calc poly = sinPoly(z)
  calc cosish = 1.0 + z * (-0.5 + z * (0.041666666666666664 + z * -0.001388888888888889))
  calc tail = high * z * poly + low * cosish
  calc result = high + tail
  return result

op cosineKernel "cos of the double-double (high, low), high within pi/4"
  input high Float64 copied
  input low Float64 copied
  output Float64
:begin
  calc z = high * high
  calc zLow = productError(high, high, z)
  calc halfZ = 0.5 * z
  calc minusHalfZ = -halfZ
  calc whole = 1.0 + minusHalfZ
  calc wholeError = sumError(1.0, minusHalfZ, whole)
  calc poly = cosPoly(z)
  calc tail = (wholeError - 0.5 * zLow) + (z * z * poly - low * high)
  calc result = whole + tail
  return result

op tangentKernel "tan of the double-double (high, low), high within pi/4, as a double-double kept in the pair"
  input high Float64 copied
  input low Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc z = high * high
  calc zLow = productError(high, high, z)
  calc series = tanPoly(z)
  calc rest = (z * z) * (high * series)
  calc cube = high * z
  calc cubeLow = productError(high, z, cube)
  calc third = cube * 0x1.5555555555555p-2
  calc thirdLow0 = productError(cube, 0x1.5555555555555p-2, third)
  calc thirdLow = ((thirdLow0 + cube * 0x1.5555555555555p-56) + cubeLow * 0x1.5555555555555p-2) + (high * zLow) * 0x1.5555555555555p-2
  calc sum = high + third
  calc sumError1 = sumError(high, third, sum)
  calc tail = ((sumError1 + thirdLow) + rest) + low * (1.0 + z)
  calc result = sum + tail
  calc resultLow = quickSumError(sum, tail, result)
  storeIt: storePair(result, resultLow)
  return

## ---------------------------------------------------------------- sin, cos, tan

op signedByInput "A result with the sign of x flipped in when asked"
  input value Float64 copied
  input negative Bool copied
  output Float64
:begin
  calc sign = plusOrMinus(negative)
  calc result = value * sign
  return result

op domainFailure "EDOM, and the NaN glibc gives for a value outside a function's domain (x - x for an infinity)"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  setIt: clibrary.setErrno(domainError)
  calc difference = x - x
  calc nan = difference / difference
  return nan



op absoluteOf "The magnitude of a double: its sign bit cleared"
  input x Float64 copied
  output Float64
:begin
  calc field = convert.float64BitsToUInt64(x)
  calc cleared = field & 9223372036854775807
  calc value = convert.uint64BitsToFloat64(cleared)
  return value

op signedLike "The magnitude of a double with the sign bit of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
:begin
  calc magnitudeBits = convert.float64BitsToUInt64(magnitude)
  calc signBits = convert.float64BitsToUInt64(sign)
  calc joined = (magnitudeBits & 9223372036854775807) | (signBits & 9223372036854775808)
  calc value = convert.uint64BitsToFloat64(joined)
  return value

op squareRootOf "The correctly rounded square root of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc root = machine.squareRoot(x)
  return root

op largerOf "The larger of two doubles"
  input a Float64 copied
  input b Float64 copied
  output Float64
:begin
  when a > b giveA giveB
:giveA
  return a
:giveB
  return b

op sineDouble "sin of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let kernelValue Float64 0.0 mut
:begin
  calc a = absoluteOf(x)
  when a < 0x1p-27 tiny notTiny
:tiny
  return x
:notTiny
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 0x1.fffffffffffffp+1023 infinite finite
:infinite
  calc nan = domainFailure(x)
  return nan
:finite
  reduceIt: reduceArgument(a)
  calc quadrant = loadQuadrant()
  calc high = loadReal(slotHigh)
  calc low = loadReal(slotLow)
  calc odd = quadrant & 1
  when odd == 0 evenQuadrant oddQuadrant
:evenQuadrant
  calc sine = sineKernel(high, low)
  calc kernelValue := sine
  goto signIt
:oddQuadrant
  calc cosine = cosineKernel(high, low)
  calc kernelValue := cosine
  goto signIt
:signIt
  calc negative = logic.xor((quadrant & 2) != 0, x < 0.0)
  calc result = signedByInput(kernelValue, negative)
  return result

op cosineDouble "cos of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let kernelValue Float64 0.0 mut
  let oneReal Float64 1.0
:begin
  calc a = absoluteOf(x)
  when a < 0x1p-27 tiny notTiny
:tiny
  return oneReal
:notTiny
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 0x1.fffffffffffffp+1023 infinite finite
:infinite
  calc nan = domainFailure(x)
  return nan
:finite
  reduceIt: reduceArgument(a)
  calc quadrant = loadQuadrant()
  calc high = loadReal(slotHigh)
  calc low = loadReal(slotLow)
  calc odd = quadrant & 1
  when odd == 0 evenQuadrant oddQuadrant
:evenQuadrant
  calc cosine = cosineKernel(high, low)
  calc kernelValue := cosine
  goto signIt
:oddQuadrant
  calc sine = sineKernel(high, low)
  calc kernelValue := sine
  goto signIt
:signIt
  calc negative = ((quadrant + 1) & 2) != 0
  calc result = signedByInput(kernelValue, negative)
  return result

op tangentDouble "tan of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let kernelValue Float64 0.0 mut
:begin
  calc a = absoluteOf(x)
  when a < 0x1p-27 tiny notTiny
:tiny
  return x
:notTiny
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 0x1.fffffffffffffp+1023 infinite finite
:infinite
  calc nan = domainFailure(x)
  return nan
:finite
  reduceIt: reduceArgument(a)
  calc quadrant = loadQuadrant()
  calc high = loadReal(slotHigh)
  calc low = loadReal(slotLow)
  kernelIt: tangentKernel(high, low)
  calc tanHigh = loadReal(slotPairHigh)
  calc tanLow = loadReal(slotPairLow)
  calc odd = quadrant & 1
  when odd == 0 evenQuadrant oddQuadrant
:evenQuadrant
  calc direct = tanHigh + tanLow
  calc kernelValue := direct
  goto signIt
:oddQuadrant
  calc reciprocal = 1.0 / tanHigh
  calc product = reciprocal * tanHigh
  calc productLow = productError(reciprocal, tanHigh, product)
  calc remainder = ((1.0 - product) - productLow) - reciprocal * tanLow
  calc cotangent = -(reciprocal + reciprocal * remainder)
  calc kernelValue := cotangent
  goto signIt
:signIt
  calc negative = x < 0.0
  calc result = signedByInput(kernelValue, negative)
  return result

## ---------------------------------------------------------------- the inverse functions

op divideDouble "A double-double quotient of two double-doubles, kept in the pair (the divisor's high part is not 0)"
  input aHigh Float64 copied
  input aLow Float64 copied
  input bHigh Float64 copied
  input bLow Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc first = aHigh / bHigh
  calc product = first * bHigh
  calc productLow = productError(first, bHigh, product)
  calc remainder = (((aHigh - product) - productLow) + aLow) - first * bLow
  calc second = remainder / bHigh
  calc high = first + second
  calc low = quickSumError(first, second, high)
  storeIt: storePair(high, low)
  return

op arctangentSmall "atan of a double-double from 0 to 8, kept in the pair: the tabulated atan(k/8) plus a series in w = (u - k/8)/(1 + u k/8)"
  input uHigh Float64 copied
  input uLow Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc scaled = 8.0 * uHigh + 0.5
  calc k = convert.float64ToInt64(scaled)
  calc c = convert.int64ToFloat64(k) / 8.0
  calc tableHigh = atanEntry(2 * k)
  calc tableLow = atanEntry(2 * k + 1)
  calc numerator = uHigh - c
  calc product = uHigh * c
  calc productLow = productError(uHigh, c, product)
  calc denominator0 = 1.0 + product
  calc denominatorError = sumError(1.0, product, denominator0)
  calc denominatorLow0 = denominatorError + (productLow + uLow * c)
  calc denominatorHigh = denominator0 + denominatorLow0
  calc denominatorLow = quickSumError(denominator0, denominatorLow0, denominatorHigh)
  divideIt: divideDouble(numerator, uLow, denominatorHigh, denominatorLow)
  calc wHigh = loadReal(slotPairHigh)
  calc wLow = loadReal(slotPairLow)
  calc z = wHigh * wHigh
  calc tail = (wHigh * z) * atanPoly(z)
  calc sum = tableHigh + wHigh
  calc sumError1 = sumError(tableHigh, wHigh, sum)
  calc rest = (sumError1 + tableLow) + (wLow + tail)
  calc high = sum + rest
  calc low = quickSumError(sum, rest, high)
  storeIt: storePair(high, low)
  return

op arctangentCore "atan(a/b) of two non-negative double-doubles (b is not 0), kept in the pair"
  input aHigh Float64 copied
  input aLow Float64 copied
  input bHigh Float64 copied
  input bLow Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc limit = 8.0 * bHigh
  when aHigh > limit flipped direct
:direct
  divideIt: divideDouble(aHigh, aLow, bHigh, bLow)
  calc uHigh = loadReal(slotPairHigh)
  calc uLow = loadReal(slotPairLow)
  smallIt: arctangentSmall(uHigh, uLow)
  return
:flipped
  divideFlipped: divideDouble(bHigh, bLow, aHigh, aLow)
  calc vHigh = loadReal(slotPairHigh)
  calc vLow = loadReal(slotPairLow)
  smallFlipped: arctangentSmall(vHigh, vLow)
  calc tHigh = loadReal(slotPairHigh)
  calc tLow = loadReal(slotPairLow)
  calc minusT = -tHigh
  calc sum = 0x1.921fb54442d18p+0 + minusT
  calc sumError1 = sumError(0x1.921fb54442d18p+0, minusT, sum)
  calc rest = (sumError1 + 0x1.1a62633145c07p-54) - tLow
  calc high = sum + rest
  calc low = quickSumError(sum, rest, high)
  keepIt: storePair(high, low)
  return

op complementRoot "sqrt(1 - x*x) for x from 0 to 1, a double-double kept in the pair"
  input x Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc square = x * x
  calc squareLow = productError(x, x, square)
  calc minusSquare = -square
  calc difference0 = 1.0 + minusSquare
  calc differenceError = sumError(1.0, minusSquare, difference0)
  calc differenceLow0 = differenceError - squareLow
  calc difference = difference0 + differenceLow0
  calc differenceLow = quickSumError(difference0, differenceLow0, difference)
  calc root = squareRootOf(difference)
  calc rootSquare = root * root
  calc rootSquareLow = productError(root, root, rootSquare)
  calc remainder = ((difference - rootSquare) - rootSquareLow) + differenceLow
  calc correction = remainder / (2.0 * root)
  calc high = root + correction
  calc low = quickSumError(root, correction, high)
  storeIt: storePair(high, low)
  return

op arcTangentDouble "atan of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let zeroReal Float64 0.0
  let oneReal Float64 1.0
:begin
  calc a = absoluteOf(x)
  when a < 0x1p-27 tiny notTiny
:tiny
  return x
:notTiny
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 0x1p+64 infinite finite
:infinite
  calc quarterTurns = signedLike(0x1.921fb54442d18p+0, x)
  return quarterTurns
:finite
  coreIt: arctangentCore(a, zeroReal, oneReal, zeroReal)
  calc high = loadReal(slotPairHigh)
  calc low = loadReal(slotPairLow)
  calc sum = high + low
  calc result = signedLike(sum, x)
  return result

op arcSineDouble "asin of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let zeroReal Float64 0.0
:begin
  calc a = absoluteOf(x)
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 1.0 outside inside
:outside
  calc nan = domainFailure(x)
  return nan
:inside
  when a < 0x1p-27 tiny notTiny
:tiny
  return x
:notTiny
  when a == 1.0 quarter general
:quarter
  calc quarterTurns = signedLike(0x1.921fb54442d18p+0, x)
  return quarterTurns
:general
  rootIt: complementRoot(a)
  calc rootHigh = loadReal(slotPairHigh)
  calc rootLow = loadReal(slotPairLow)
  coreIt: arctangentCore(a, zeroReal, rootHigh, rootLow)
  calc high = loadReal(slotPairHigh)
  calc low = loadReal(slotPairLow)
  calc sum = high + low
  calc result = signedLike(sum, x)
  return result

op arcCosineDouble "acos of a double"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let zeroReal Float64 0.0
  let halfTurn Float64 3.141592653589793
  let quarterTurn Float64 1.5707963267948966
:begin
  calc a = absoluteOf(x)
  calc isNan = !(x == x)
  when isNan giveNan notNan
:giveNan
  return x
:notNan
  when a > 1.0 outside inside
:outside
  calc nan = domainFailure(x)
  return nan
:inside
  when x == 1.0 giveZero notOne
:giveZero
  return zeroReal
:notOne
  when a == 1.0 giveHalfTurn notMinusOne
:giveHalfTurn
  return halfTurn
:notMinusOne
  when a == 0.0 giveQuarter general
:giveQuarter
  return quarterTurn
:general
  rootIt: complementRoot(a)
  calc rootHigh = loadReal(slotPairHigh)
  calc rootLow = loadReal(slotPairLow)
  coreIt: arctangentCore(rootHigh, rootLow, a, zeroReal)
  calc high = loadReal(slotPairHigh)
  calc low = loadReal(slotPairLow)
  when x > 0.0 positive negative
:positive
  calc direct = high + low
  return direct
:negative
  calc minusHigh = -high
  calc sum = 0x1.921fb54442d18p+1 + minusHigh
  calc sumError1 = sumError(0x1.921fb54442d18p+1, minusHigh, sum)
  calc rest = (sumError1 + 0x1.1a62633145c07p-53) - low
  calc turned = sum + rest
  return turned

op arcTangent2Double "atan2 of two doubles: Annex F's cases first, then atan(|y|/|x|) rounded once and placed in its quadrant"
  input y Float64 copied
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let scale Float64 1.0 mut
  let zeroReal Float64 0.0
:begin
  calc yNan = !(y == y)
  calc xNan = !(x == x)
  calc anyNan = logic.or(yNan, xNan)
  when anyNan giveNan numbers
:giveNan
  calc nan = y + x
  return nan
:numbers
  calc ay = absoluteOf(y)
  calc ax = absoluteOf(x)
  calc xNegative = signedLike(1.0, x) < 0.0
  when ay == 0.0 yZero yNonZero
:yZero
  when xNegative zeroLeft zeroRight
:zeroLeft
  calc halfTurn = signedLike(0x1.921fb54442d18p+1, y)
  return halfTurn
:zeroRight
  return y
:yNonZero
  when ax == 0.0 xZero xNonZero
:xZero
  calc quarterTurn = signedLike(0x1.921fb54442d18p+0, y)
  return quarterTurn
:xNonZero
  calc yInfinite = ay > 0x1.fffffffffffffp+1023
  calc xInfinite = ax > 0x1.fffffffffffffp+1023
  when yInfinite yIsInfinite yFinite
:yIsInfinite
  when xInfinite bothInfinite onlyYInfinite
:bothInfinite
  when xNegative threeEighths oneEighth
:threeEighths
  calc threeEighthsTurn = signedLike(0x1.2d97c7f3321d2p+1, y)
  return threeEighthsTurn
:oneEighth
  calc oneEighthTurn = signedLike(0x1.921fb54442d18p-1, y)
  return oneEighthTurn
:onlyYInfinite
  calc yQuarter = signedLike(0x1.921fb54442d18p+0, y)
  return yQuarter
:yFinite
  when xInfinite xIsInfinite bothFinite
:xIsInfinite
  when xNegative infiniteLeft infiniteRight
:infiniteLeft
  calc infiniteHalf = signedLike(0x1.921fb54442d18p+1, y)
  return infiniteHalf
:infiniteRight
  calc infiniteZero = signedLike(0.0, y)
  return infiniteZero
:bothFinite
  calc hugeLimit = ax * 0x1p+64
  when ay > hugeLimit hugeRatio notHuge
:hugeRatio
  calc hugeQuarter = signedLike(0x1.921fb54442d18p+0, y)
  return hugeQuarter
:notHuge
  calc tinyLimit = ay * 0x1p+64
  when ax > tinyLimit tinyRatio moderate
:tinyRatio
  when xNegative tinyLeft tinyRight
:tinyLeft
  calc tinyHalf = signedLike(0x1.921fb54442d18p+1, y)
  return tinyHalf
:tinyRight
  calc quotient = y / x
  return quotient
:moderate
  calc larger = largerOf(ay, ax)
  when larger > 0x1p+500 scaleDown checkUp
:scaleDown
  calc scale := 0x1p-600
  goto scaled
:checkUp
  when larger < 0x1p-500 scaleUp scaled
:scaleUp
  calc scale := 0x1p+600
  goto scaled
:scaled
  calc scaledY = ay * scale
  calc scaledX = ax * scale
  coreIt: arctangentCore(scaledY, zeroReal, scaledX, zeroReal)
  calc high = loadReal(slotPairHigh)
  calc low = loadReal(slotPairLow)
  when xNegative leftHalf rightHalf
:rightHalf
  calc rightSum = high + low
  calc rightResult = signedLike(rightSum, y)
  return rightResult
:leftHalf
  calc minusHigh = -high
  calc sum = 0x1.921fb54442d18p+1 + minusHigh
  calc sumError1 = sumError(0x1.921fb54442d18p+1, minusHigh, sum)
  calc rest = (sumError1 + 0x1.1a62633145c07p-53) - low
  calc turned = sum + rest
  calc leftResult = signedLike(turned, y)
  return leftResult

## ---------------------------------------------------------------- math.h

op sineOf "sin: the sine of x radians, within 1 ulp (0.7 measured); NaN with EDOM for an infinity; x for |x| below 2^-27"
  invariant sineWithin "Gives sin(x) within 1 ulp; -0.0 for -0.0"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "sin"
:begin
  calc value = sineDouble(x)
  return value

op cosineOf "cos: the cosine of x radians, within 1 ulp; NaN with EDOM for an infinity"
  invariant cosineWithin "Gives cos(x) within 1 ulp; 1.0 for 0.0"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cos"
:begin
  calc value = cosineDouble(x)
  return value

op tangentOf "tan: the tangent of x radians, within 1 ulp; NaN with EDOM for an infinity"
  invariant tangentWithin "Gives tan(x) within 1 ulp; -0.0 for -0.0"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "tan"
:begin
  calc value = tangentDouble(x)
  return value

op arcSineOf "asin: the arc sine, within 1 ulp; NaN with EDOM outside -1 to 1"
  invariant arcSineWithin "Gives asin(x) within 1 ulp"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "asin"
:begin
  calc value = arcSineDouble(x)
  return value

op arcCosineOf "acos: the arc cosine, within 1 ulp; NaN with EDOM outside -1 to 1"
  invariant arcCosineWithin "Gives acos(x) within 1 ulp; +0.0 for 1.0"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "acos"
:begin
  calc value = arcCosineDouble(x)
  return value

op arcTangentOf "atan: the arc tangent, within 1 ulp"
  invariant arcTangentWithin "Gives atan(x) within 1 ulp; +-pi/2 for an infinity"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "atan"
:begin
  calc value = arcTangentDouble(x)
  return value

op arcTangent2Of "atan2: the angle of the point (x, y), within 1 ulp, with Annex F's 16 zero and infinity cases exact"
  invariant arcTangent2Within "Gives atan2(y, x) within 1 ulp"
  input y Float64 copied
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "atan2"
:begin
  calc value = arcTangent2Double(y, x)
  return value

op sineFloat "sinf: sin of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "sinf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = sineDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op cosineFloat "cosf: cos of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "cosf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = cosineDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op tangentFloat "tanf: tan of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "tanf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = tangentDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op arcSineFloat "asinf: asin of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "asinf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = arcSineDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op arcCosineFloat "acosf: acos of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "acosf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = arcCosineDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op arcTangentFloat "atanf: atan of a float, the double result rounded once to a float"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "atanf"
:begin
  calc wide = convert.float32ToFloat64(x)
  calc value = arcTangentDouble(wide)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

op arcTangent2Float "atan2f: atan2 of two floats, the double result rounded once to a float"
  input y Float32 copied
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "atan2f"
:begin
  calc wideY = convert.float32ToFloat64(y)
  calc wideX = convert.float32ToFloat64(x)
  calc value = arcTangent2Double(wideY, wideX)
  calc narrow = convert.float64ToFloat32(value)
  return narrow

@tests

op sameBits "Whether a double has the expected bits"
  input expectedBits UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  calc actualBits = convert.float64BitsToUInt64(actual)
  calc same = expectedBits == actualBits
  return same

op closeBits "Whether a double is the expected one or the neighbor of it (the bits of two positive or two negative doubles differ by 1)"
  input expectedBits UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  calc actualBits = convert.float64BitsToUInt64(actual)
  when actualBits >= expectedBits above below
:above
  calc aboveClose = actualBits - expectedBits <= 1
  return aboveClose
:below
  calc belowClose = expectedBits - actualBits <= 1
  return belowClose

## @generated tests
test sineTest "sineOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies sineOf sineWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = sineOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4602308182625945072, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = sineOf(convert.uint64BitsToFloat64(4607182418800017408))
  calc ok1 = closeBits(4605754516372524270, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = sineOf(convert.uint64BitsToFloat64(13837309855095848960))
  calc ok2 = closeBits(13817624441271014747, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = sineOf(convert.uint64BitsToFloat64(4636737291354636288))
  calc ok3 = closeBits(13826108192625282488, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = sineOf(convert.uint64BitsToFloat64(4609753056924675352))
  calc ok4 = closeBits(4607182418800017408, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = sineOf(convert.uint64BitsToFloat64(4614256656552045848))
  calc ok5 = closeBits(4368955796522032135, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = sineOf(convert.uint64BitsToFloat64(4936209963552724370))
  calc ok6 = closeBits(13829223199258964887, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = sineOf(convert.uint64BitsToFloat64(9218868437227405311))
  calc ok7 = closeBits(4572370766535020183, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = sineOf(convert.uint64BitsToFloat64(0))
  calc ok8 = sameBits(0, r8)
  expect8: test.assertTrue(ok8)
  calc r9 = sineOf(convert.uint64BitsToFloat64(9223372036854775808))
  calc ok9 = sameBits(9223372036854775808, r9)
  expect9: test.assertTrue(ok9)
  calc r10 = sineOf(convert.uint64BitsToFloat64(9218868437227405312))
  calc ok10 = !(r10 == r10)
  expect10: test.assertTrue(ok10)
  calc r11 = sineOf(convert.uint64BitsToFloat64(18442240474082181120))
  calc ok11 = !(r11 == r11)
  expect11: test.assertTrue(ok11)
  return

test cosineTest "cosineOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies cosineOf cosineWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = cosineOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4606079780542709072, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = cosineOf(convert.uint64BitsToFloat64(4607182418800017408))
  calc ok1 = closeBits(4603041830072026764, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = cosineOf(convert.uint64BitsToFloat64(13837309855095848960))
  calc ok2 = closeBits(13830464316077630930, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = cosineOf(convert.uint64BitsToFloat64(4636737291354636288))
  calc ok3 = closeBits(4605942297449095135, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = cosineOf(convert.uint64BitsToFloat64(4609753056924675352))
  calc ok4 = closeBits(4364452196894661639, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = cosineOf(convert.uint64BitsToFloat64(4614256656552045848))
  calc ok5 = closeBits(13830554455654793216, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = cosineOf(convert.uint64BitsToFloat64(4936209963552724370))
  calc ok6 = closeBits(4602887919370356980, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = cosineOf(convert.uint64BitsToFloat64(9218868437227405311))
  calc ok7 = closeBits(13830554344771005301, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = cosineOf(convert.uint64BitsToFloat64(9223372036854775808))
  calc ok8 = sameBits(4607182418800017408, r8)
  expect8: test.assertTrue(ok8)
  calc r9 = cosineOf(convert.uint64BitsToFloat64(18442240474082181120))
  calc ok9 = !(r9 == r9)
  expect9: test.assertTrue(ok9)
  return

test tangentTest "tangentOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies tangentOf tangentWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = tangentOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4603095874924660554, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = tangentOf(convert.uint64BitsToFloat64(4607182418800017408))
  calc ok1 = closeBits(4609692760021066662, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = tangentOf(convert.uint64BitsToFloat64(13837309855095848960))
  calc ok2 = closeBits(4594303800756713583, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = tangentOf(convert.uint64BitsToFloat64(4636737291354636288))
  calc ok3 = closeBits(13826836409139027256, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = tangentOf(convert.uint64BitsToFloat64(4609753056924675352))
  calc ok4 = closeBits(4849535219099880885, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = tangentOf(convert.uint64BitsToFloat64(4936209963552724370))
  calc ok5 = closeBits(13833386221037335127, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = tangentOf(convert.uint64BitsToFloat64(9218868437227405311))
  calc ok6 = closeBits(13795742873816306820, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = tangentOf(convert.uint64BitsToFloat64(9223372036854775808))
  calc ok7 = sameBits(9223372036854775808, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = tangentOf(convert.uint64BitsToFloat64(9218868437227405312))
  calc ok8 = !(r8 == r8)
  expect8: test.assertTrue(ok8)
  return

test arcSineTest "arcSineOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies arcSineOf arcSineWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = arcSineOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4602891378046628710, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = arcSineOf(convert.uint64BitsToFloat64(13821547256400052224))
  calc ok1 = closeBits(13821595539584288717, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = arcSineOf(convert.uint64BitsToFloat64(4607182418800017407))
  calc ok2 = closeBits(4609753056857566488, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = arcSineOf(convert.uint64BitsToFloat64(13755392620465711345))
  calc ok3 = closeBits(13755392620465809728, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = arcSineOf(convert.uint64BitsToFloat64(9223372036854775808))
  calc ok4 = sameBits(9223372036854775808, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = arcSineOf(convert.uint64BitsToFloat64(4607182418800017408))
  calc ok5 = sameBits(4609753056924675352, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = arcSineOf(convert.uint64BitsToFloat64(13830554455654793216))
  calc ok6 = sameBits(13833125093779451160, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = arcSineOf(convert.uint64BitsToFloat64(4609434218613702656))
  calc ok7 = !(r7 == r7)
  expect7: test.assertTrue(ok7)
  calc r8 = arcSineOf(convert.uint64BitsToFloat64(9221120237041090560))
  calc ok8 = !(r8 == r8)
  expect8: test.assertTrue(ok8)
  return

test arcCosineTest "arcCosineOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies arcCosineOf arcCosineWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = arcCosineOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4607394977673999206, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = arcCosineOf(convert.uint64BitsToFloat64(13826050856027422720))
  calc ok1 = closeBits(4611898577301369702, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = arcCosineOf(convert.uint64BitsToFloat64(4607182418800017407))
  calc ok2 = closeBits(4490088828488384512, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = arcCosineOf(convert.uint64BitsToFloat64(13830554455654793215))
  calc ok3 = closeBits(4614256656518491416, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = arcCosineOf(convert.uint64BitsToFloat64(4472406533629990549))
  calc ok4 = closeBits(4609753056920171753, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = arcCosineOf(convert.uint64BitsToFloat64(4607182418800017408))
  calc ok5 = sameBits(0, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = arcCosineOf(convert.uint64BitsToFloat64(13830554455654793216))
  calc ok6 = sameBits(4614256656552045848, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = arcCosineOf(convert.uint64BitsToFloat64(0))
  calc ok7 = sameBits(4609753056924675352, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = arcCosineOf(convert.uint64BitsToFloat64(18442240474082181120))
  calc ok8 = !(r8 == r8)
  expect8: test.assertTrue(ok8)
  return

test arcTangentTest "arcTangentOf: the correctly rounded result or a neighbor of it, and exact special values"
  verifies arcTangentOf arcTangentWithin
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = arcTangentOf(convert.uint64BitsToFloat64(4602678819172646912))
  calc ok0 = closeBits(4602023952714414927, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = arcTangentOf(convert.uint64BitsToFloat64(13835058055282163712))
  calc ok1 = closeBits(13831037010580323908, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = arcTangentOf(convert.uint64BitsToFloat64(4621819117588971520))
  calc ok2 = closeBits(4609304189218455636, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = arcTangentOf(convert.uint64BitsToFloat64(4756540486875873280))
  calc ok3 = closeBits(4609753056924224992, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = arcTangentOf(convert.uint64BitsToFloat64(9094988921128908188))
  calc ok4 = closeBits(4609753056924675352, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = arcTangentOf(convert.uint64BitsToFloat64(4593671619917905920))
  calc ok5 = closeBits(4593625142376804206, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = arcTangentOf(convert.uint64BitsToFloat64(9218868437227405312))
  calc ok6 = sameBits(4609753056924675352, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = arcTangentOf(convert.uint64BitsToFloat64(18442240474082181120))
  calc ok7 = sameBits(13833125093779451160, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = arcTangentOf(convert.uint64BitsToFloat64(9223372036854775808))
  calc ok8 = sameBits(9223372036854775808, r8)
  expect8: test.assertTrue(ok8)
  return

test arcTangent2Test "arcTangent2Of: the correctly rounded result or a neighbor of it, and exact special values"
  verifies arcTangent2Of arcTangent2Within
  effect use machine.memory
  uses memoryAccess
:begin
  calc r0 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4611686018427387904))
  calc ok0 = closeBits(4602023952714414927, r0)
  expect0: test.assertTrue(ok0)
  calc r1 = arcTangent2Of(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(13835058055282163712))
  calc ok1 = closeBits(13836584651807258030, r1)
  expect1: test.assertTrue(ok1)
  calc r2 = arcTangent2Of(convert.uint64BitsToFloat64(4611686018427387904), convert.uint64BitsToFloat64(13830554455654793216))
  calc ok2 = closeBits(4611763579275595254, r2)
  expect2: test.assertTrue(ok2)
  calc r3 = arcTangent2Of(convert.uint64BitsToFloat64(13837309855095848960), convert.uint64BitsToFloat64(4616189618054758400))
  calc ok3 = closeBits(13827343399107600097, r3)
  expect3: test.assertTrue(ok3)
  calc r4 = arcTangent2Of(convert.uint64BitsToFloat64(118622047889322841), convert.uint64BitsToFloat64(126121232842798723))
  calc ok4 = closeBits(4599467762625453793, r4)
  expect4: test.assertTrue(ok4)
  calc r5 = arcTangent2Of(convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(4607182418800017408))
  calc ok5 = closeBits(1, r5)
  expect5: test.assertTrue(ok5)
  calc r6 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9094988921128908188))
  calc ok6 = closeBits(118622047889322841, r6)
  expect6: test.assertTrue(ok6)
  calc r7 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(0))
  calc ok7 = sameBits(0, r7)
  expect7: test.assertTrue(ok7)
  calc r8 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok8 = sameBits(4614256656552045848, r8)
  expect8: test.assertTrue(ok8)
  calc r9 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(4607182418800017408))
  calc ok9 = sameBits(0, r9)
  expect9: test.assertTrue(ok9)
  calc r10 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(13830554455654793216))
  calc ok10 = sameBits(4614256656552045848, r10)
  expect10: test.assertTrue(ok10)
  calc r11 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok11 = sameBits(0, r11)
  expect11: test.assertTrue(ok11)
  calc r12 = arcTangent2Of(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok12 = sameBits(4614256656552045848, r12)
  expect12: test.assertTrue(ok12)
  calc r13 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(0))
  calc ok13 = sameBits(9223372036854775808, r13)
  expect13: test.assertTrue(ok13)
  calc r14 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok14 = sameBits(13837628693406821656, r14)
  expect14: test.assertTrue(ok14)
  calc r15 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(4607182418800017408))
  calc ok15 = sameBits(9223372036854775808, r15)
  expect15: test.assertTrue(ok15)
  calc r16 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(13830554455654793216))
  calc ok16 = sameBits(13837628693406821656, r16)
  expect16: test.assertTrue(ok16)
  calc r17 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok17 = sameBits(9223372036854775808, r17)
  expect17: test.assertTrue(ok17)
  calc r18 = arcTangent2Of(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok18 = sameBits(13837628693406821656, r18)
  expect18: test.assertTrue(ok18)
  calc r19 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(0))
  calc ok19 = sameBits(4609753056924675352, r19)
  expect19: test.assertTrue(ok19)
  calc r20 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok20 = sameBits(4609753056924675352, r20)
  expect20: test.assertTrue(ok20)
  calc r21 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok21 = sameBits(0, r21)
  expect21: test.assertTrue(ok21)
  calc r22 = arcTangent2Of(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok22 = sameBits(4614256656552045848, r22)
  expect22: test.assertTrue(ok22)
  calc r23 = arcTangent2Of(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(0))
  calc ok23 = sameBits(13833125093779451160, r23)
  expect23: test.assertTrue(ok23)
  calc r24 = arcTangent2Of(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok24 = sameBits(13833125093779451160, r24)
  expect24: test.assertTrue(ok24)
  calc r25 = arcTangent2Of(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok25 = sameBits(9223372036854775808, r25)
  expect25: test.assertTrue(ok25)
  calc r26 = arcTangent2Of(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok26 = sameBits(13837628693406821656, r26)
  expect26: test.assertTrue(ok26)
  calc r27 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(0))
  calc ok27 = sameBits(4609753056924675352, r27)
  expect27: test.assertTrue(ok27)
  calc r28 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok28 = sameBits(4609753056924675352, r28)
  expect28: test.assertTrue(ok28)
  calc r29 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(4607182418800017408))
  calc ok29 = sameBits(4609753056924675352, r29)
  expect29: test.assertTrue(ok29)
  calc r30 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(13830554455654793216))
  calc ok30 = sameBits(4609753056924675352, r30)
  expect30: test.assertTrue(ok30)
  calc r31 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok31 = sameBits(4605249457297304856, r31)
  expect31: test.assertTrue(ok31)
  calc r32 = arcTangent2Of(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok32 = sameBits(4612488097114038738, r32)
  expect32: test.assertTrue(ok32)
  calc r33 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(0))
  calc ok33 = sameBits(13833125093779451160, r33)
  expect33: test.assertTrue(ok33)
  calc r34 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(9223372036854775808))
  calc ok34 = sameBits(13833125093779451160, r34)
  expect34: test.assertTrue(ok34)
  calc r35 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(4607182418800017408))
  calc ok35 = sameBits(13833125093779451160, r35)
  expect35: test.assertTrue(ok35)
  calc r36 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(13830554455654793216))
  calc ok36 = sameBits(13833125093779451160, r36)
  expect36: test.assertTrue(ok36)
  calc r37 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(9218868437227405312))
  calc ok37 = sameBits(13828621494152080664, r37)
  expect37: test.assertTrue(ok37)
  calc r38 = arcTangent2Of(convert.uint64BitsToFloat64(18442240474082181120), convert.uint64BitsToFloat64(18442240474082181120))
  calc ok38 = sameBits(13835860133968814546, r38)
  expect38: test.assertTrue(ok38)
  return
## @end tests
