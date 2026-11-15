module cmathexp "math.h's exponentials, logarithms, pow, cbrt and hypot written in SemanticScript, double and float forms, as glibc gives them to within one unit in the last place"
  path cmathexp
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test clibrary
  exports exponential naturalLogarithm power

capability memoryAccess "Authority to set errno and to take a square root" use machine.memory none

## cmathexp: written by tools/cmathexpgen.py, which computes every constant (ln 2 in parts, series coefficients)
## with Decimal and Fraction. Do not edit by hand. The algorithms are double-double (Dekker, Knuth); see the generator.

op infinityValue "Positive infinity"
  output Float64
:begin
  calc t1 = convert.uint64BitsToFloat64(9218868437227405312)
  return t1

op invalidValue "The quiet NaN the hardware gives for an invalid operation (the sign bit set, as glibc's x86_64 results print)"
  output Float64
:begin
  calc t1 = convert.uint64BitsToFloat64(18444492273895866368)
  return t1

op absoluteOf "The magnitude of a double"
  input value Float64 copied
  output Float64
:begin
  calc t1 = convert.float64BitsToUInt64(value)
  calc t2 = t1 & 9223372036854775807
  calc t3 = convert.uint64BitsToFloat64(t2)
  return t3

op signedLike "The magnitude of one double with the sign of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
:begin
  calc t1 = convert.float64BitsToUInt64(magnitude)
  calc t2 = t1 & 9223372036854775807
  calc t3 = convert.float64BitsToUInt64(sign)
  calc t4 = t3 & 9223372036854775808
  calc t5 = t2 | t4
  calc t6 = convert.uint64BitsToFloat64(t5)
  return t6

op powerOfTwo "2 to a power from -1022 to 1023, exactly"
  input steps Int64 copied
  output Float64
:begin
  calc t1 = steps + 1023
  calc t2 = convert.int64BitsToUInt64(t1)
  calc t3 = t2 << 52
  calc t4 = convert.uint64BitsToFloat64(t3)
  return t4

op scaleBy "A double times 2 to a power from -2044 to 2044 in two exact steps, so only the last rounds"
  input value Float64 copied
  input steps Int64 copied
  output Float64
:begin
  calc t1 = steps / 2
  calc t2 = steps - t1
  calc t3 = powerOfTwo(t1)
  calc t4 = powerOfTwo(t2)
  calc t5 = value * t3
  calc t6 = t5 * t4
  return t6

op integerKind "For a finite double: 0 when it is not a whole number, 1 when it is an odd one, 2 when an even one"
  input value Float64 copied
  output Int64
  let k1 Int64 2
  let k2 Int64 0
  let k3 Int64 1
:begin
  calc t4 = absoluteOf(value)
  when t4 >= 9007199254740992.0 yes1 no2
:yes1
  return k1
:no2
  calc t5 = convert.float64ToInt64(value)
  calc t6 = convert.int64ToFloat64(t5)
  when t6 != value yes3 no4
:yes3
  return k2
:no4
  calc t7 = t5 & 1
  when t7 == 1 yes5 no6
:yes5
  return k3
:no6
  return k1

op narrowOf "A double as a float, rounded once; a magnitude that rounds past the largest float is an infinity"
  input value Float64 copied
  output Float32
:begin
  calc t1 = absoluteOf(value)
  when t1 >= 0x1.ffffff0000000p+127 big1 small2
:big1
  calc t2 = infinityValue()
  calc t3 = signedLike(t2, value)
  calc t4 = convert.float64ToFloat32(t3)
  return t4
:small2
  calc t5 = convert.float64ToFloat32(value)
  return t5

op noteRange "Set errno to ERANGE when a result is an infinity from finite arguments, or a zero from a computation that underflowed"
  input value Float64 copied
  input overflows Bool copied
  input underflows Bool copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc t1 = absoluteOf(value)
  when t1 > 0x1.fffffffffffffp+1023 yes1 no2
:yes1
  when overflows setIt skipIt
:setIt
  clibrary.setErrno(34)
  return
:skipIt
  return
:no2
  when value == 0.0 yes3 no4
:yes3
  when underflows setZero skipZero
:setZero
  clibrary.setErrno(34)
  return
:skipZero
  return
:no4
  return

op noteDomain "Set errno for log: ERANGE at the pole, EDOM below it (a NaN argument sets nothing)"
  input value Float64 copied
  input pole Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  when value == pole yes1 no2
:yes1
  clibrary.setErrno(34)
  return
:no2
  when value < pole yes3 no4
:yes3
  clibrary.setErrno(33)
  return
:no4
  return

op noteInvalid "Set errno to EDOM when a result is a NaN though no argument was"
  input value Float64 copied
  input fromArguments Bool copied
  effect use machine.memory
  uses memoryAccess
:begin
  when !(value == value) yes1 no2
:yes1
  when fromArguments keepIt setIt
:setIt
  clibrary.setErrno(33)
  return
:keepIt
  return
:no2
  return

op expScaled "2 to the power k times e to the power r, r = rh + rl with |r| up to 0.35, rounded once"
  input rh Float64 copied
  input rl Float64 copied
  input k Int64 copied
  output Float64
:begin
  calc t1 = rh * 0.125
  calc t2 = rl * 0.125
  calc t3 = t1 * t1
  calc t4 = t1 * 134217729.0
  calc t5 = t4 - (t4 - t1)
  calc t6 = t1 - t5
  calc t7 = t1 * 134217729.0
  calc t8 = t7 - (t7 - t1)
  calc t9 = t1 - t8
  calc t10 = ((((t5 * t8) - t3) + (t5 * t9)) + (t6 * t8)) + (t6 * t9)
  calc t11 = t10 + ((t1 * t2) + (t2 * t1))
  calc t12 = t3 + t11
  calc t13 = t11 - (t12 - t3)
  calc t14 = t12 * 0.5
  calc t15 = t13 * 0.5
  calc t16 = t1 * t1
  calc t17 = t16 * t1
  calc t18 = 0x1.27e4fb7789f5cp-22 + (t1 * 0x1.ae64567f544e4p-26)
  calc t19 = 0x1.71de3a556c734p-19 + (t1 * t18)
  calc t20 = 0x1.a01a01a01a01ap-16 + (t1 * t19)
  calc t21 = 0x1.a01a01a01a01ap-13 + (t1 * t20)
  calc t22 = 0x1.6c16c16c16c17p-10 + (t1 * t21)
  calc t23 = 0x1.1111111111111p-7 + (t1 * t22)
  calc t24 = 0x1.5555555555555p-5 + (t1 * t23)
  calc t25 = 0x1.5555555555555p-3 + (t1 * t24)
  calc t26 = t17 * t25
  calc t27 = t14 + t26
  calc t28 = t27 - t14
  calc t29 = (t14 - (t27 - t28)) + (t26 - t28)
  calc t30 = t29 + t15
  calc t31 = t27 + t30
  calc t32 = t31 - t27
  calc t33 = (t27 - (t31 - t32)) + (t30 - t32)
  calc t34 = t1 + t31
  calc t35 = t34 - t1
  calc t36 = (t1 - (t34 - t35)) + (t31 - t35)
  calc t37 = t36 + (t2 + t33)
  calc t38 = t34 + t37
  calc t39 = t38 - t34
  calc t40 = (t34 - (t38 - t39)) + (t37 - t39)
  calc t41 = t38 * t38
  calc t42 = t38 * 134217729.0
  calc t43 = t42 - (t42 - t38)
  calc t44 = t38 - t43
  calc t45 = t38 * 134217729.0
  calc t46 = t45 - (t45 - t38)
  calc t47 = t38 - t46
  calc t48 = ((((t43 * t46) - t41) + (t43 * t47)) + (t44 * t46)) + (t44 * t47)
  calc t49 = t48 + ((t38 * t40) + (t40 * t38))
  calc t50 = t41 + t49
  calc t51 = t49 - (t50 - t41)
  calc t52 = t38 * 2.0
  calc t53 = t40 * 2.0
  calc t54 = t52 + t50
  calc t55 = t54 - t52
  calc t56 = (t52 - (t54 - t55)) + (t50 - t55)
  calc t57 = t56 + (t53 + t51)
  calc t58 = t54 + t57
  calc t59 = t58 - t54
  calc t60 = (t54 - (t58 - t59)) + (t57 - t59)
  calc t61 = t58 * t58
  calc t62 = t58 * 134217729.0
  calc t63 = t62 - (t62 - t58)
  calc t64 = t58 - t63
  calc t65 = t58 * 134217729.0
  calc t66 = t65 - (t65 - t58)
  calc t67 = t58 - t66
  calc t68 = ((((t63 * t66) - t61) + (t63 * t67)) + (t64 * t66)) + (t64 * t67)
  calc t69 = t68 + ((t58 * t60) + (t60 * t58))
  calc t70 = t61 + t69
  calc t71 = t69 - (t70 - t61)
  calc t72 = t58 * 2.0
  calc t73 = t60 * 2.0
  calc t74 = t72 + t70
  calc t75 = t74 - t72
  calc t76 = (t72 - (t74 - t75)) + (t70 - t75)
  calc t77 = t76 + (t73 + t71)
  calc t78 = t74 + t77
  calc t79 = t78 - t74
  calc t80 = (t74 - (t78 - t79)) + (t77 - t79)
  calc t81 = t78 * t78
  calc t82 = t78 * 134217729.0
  calc t83 = t82 - (t82 - t78)
  calc t84 = t78 - t83
  calc t85 = t78 * 134217729.0
  calc t86 = t85 - (t85 - t78)
  calc t87 = t78 - t86
  calc t88 = ((((t83 * t86) - t81) + (t83 * t87)) + (t84 * t86)) + (t84 * t87)
  calc t89 = t88 + ((t78 * t80) + (t80 * t78))
  calc t90 = t81 + t89
  calc t91 = t89 - (t90 - t81)
  calc t92 = t78 * 2.0
  calc t93 = t80 * 2.0
  calc t94 = t92 + t90
  calc t95 = t94 - t92
  calc t96 = (t92 - (t94 - t95)) + (t90 - t95)
  calc t97 = t96 + (t93 + t91)
  calc t98 = t94 + t97
  calc t99 = t98 - t94
  calc t100 = (t94 - (t98 - t99)) + (t97 - t99)
  calc t101 = 1.0 + t98
  calc t102 = t101 - 1.0
  calc t103 = (1.0 - (t101 - t102)) + (t98 - t102)
  calc t104 = t103 + t100
  calc t105 = t101 + t104
  calc t106 = t104 - (t105 - t101)
  calc t107 = scaleBy(t105, k)
  return t107

op expm1Scaled "2 to the power k times e to the power r, less 1, r = rh + rl with |r| up to 0.35, rounded once"
  input rh Float64 copied
  input rl Float64 copied
  input k Int64 copied
  output Float64
  let k109 Float64 -1.0
:begin
  calc t1 = rh * 0.125
  calc t2 = rl * 0.125
  calc t3 = t1 * t1
  calc t4 = t1 * 134217729.0
  calc t5 = t4 - (t4 - t1)
  calc t6 = t1 - t5
  calc t7 = t1 * 134217729.0
  calc t8 = t7 - (t7 - t1)
  calc t9 = t1 - t8
  calc t10 = ((((t5 * t8) - t3) + (t5 * t9)) + (t6 * t8)) + (t6 * t9)
  calc t11 = t10 + ((t1 * t2) + (t2 * t1))
  calc t12 = t3 + t11
  calc t13 = t11 - (t12 - t3)
  calc t14 = t12 * 0.5
  calc t15 = t13 * 0.5
  calc t16 = t1 * t1
  calc t17 = t16 * t1
  calc t18 = 0x1.27e4fb7789f5cp-22 + (t1 * 0x1.ae64567f544e4p-26)
  calc t19 = 0x1.71de3a556c734p-19 + (t1 * t18)
  calc t20 = 0x1.a01a01a01a01ap-16 + (t1 * t19)
  calc t21 = 0x1.a01a01a01a01ap-13 + (t1 * t20)
  calc t22 = 0x1.6c16c16c16c17p-10 + (t1 * t21)
  calc t23 = 0x1.1111111111111p-7 + (t1 * t22)
  calc t24 = 0x1.5555555555555p-5 + (t1 * t23)
  calc t25 = 0x1.5555555555555p-3 + (t1 * t24)
  calc t26 = t17 * t25
  calc t27 = t14 + t26
  calc t28 = t27 - t14
  calc t29 = (t14 - (t27 - t28)) + (t26 - t28)
  calc t30 = t29 + t15
  calc t31 = t27 + t30
  calc t32 = t31 - t27
  calc t33 = (t27 - (t31 - t32)) + (t30 - t32)
  calc t34 = t1 + t31
  calc t35 = t34 - t1
  calc t36 = (t1 - (t34 - t35)) + (t31 - t35)
  calc t37 = t36 + (t2 + t33)
  calc t38 = t34 + t37
  calc t39 = t38 - t34
  calc t40 = (t34 - (t38 - t39)) + (t37 - t39)
  calc t41 = t38 * t38
  calc t42 = t38 * 134217729.0
  calc t43 = t42 - (t42 - t38)
  calc t44 = t38 - t43
  calc t45 = t38 * 134217729.0
  calc t46 = t45 - (t45 - t38)
  calc t47 = t38 - t46
  calc t48 = ((((t43 * t46) - t41) + (t43 * t47)) + (t44 * t46)) + (t44 * t47)
  calc t49 = t48 + ((t38 * t40) + (t40 * t38))
  calc t50 = t41 + t49
  calc t51 = t49 - (t50 - t41)
  calc t52 = t38 * 2.0
  calc t53 = t40 * 2.0
  calc t54 = t52 + t50
  calc t55 = t54 - t52
  calc t56 = (t52 - (t54 - t55)) + (t50 - t55)
  calc t57 = t56 + (t53 + t51)
  calc t58 = t54 + t57
  calc t59 = t58 - t54
  calc t60 = (t54 - (t58 - t59)) + (t57 - t59)
  calc t61 = t58 * t58
  calc t62 = t58 * 134217729.0
  calc t63 = t62 - (t62 - t58)
  calc t64 = t58 - t63
  calc t65 = t58 * 134217729.0
  calc t66 = t65 - (t65 - t58)
  calc t67 = t58 - t66
  calc t68 = ((((t63 * t66) - t61) + (t63 * t67)) + (t64 * t66)) + (t64 * t67)
  calc t69 = t68 + ((t58 * t60) + (t60 * t58))
  calc t70 = t61 + t69
  calc t71 = t69 - (t70 - t61)
  calc t72 = t58 * 2.0
  calc t73 = t60 * 2.0
  calc t74 = t72 + t70
  calc t75 = t74 - t72
  calc t76 = (t72 - (t74 - t75)) + (t70 - t75)
  calc t77 = t76 + (t73 + t71)
  calc t78 = t74 + t77
  calc t79 = t78 - t74
  calc t80 = (t74 - (t78 - t79)) + (t77 - t79)
  calc t81 = t78 * t78
  calc t82 = t78 * 134217729.0
  calc t83 = t82 - (t82 - t78)
  calc t84 = t78 - t83
  calc t85 = t78 * 134217729.0
  calc t86 = t85 - (t85 - t78)
  calc t87 = t78 - t86
  calc t88 = ((((t83 * t86) - t81) + (t83 * t87)) + (t84 * t86)) + (t84 * t87)
  calc t89 = t88 + ((t78 * t80) + (t80 * t78))
  calc t90 = t81 + t89
  calc t91 = t89 - (t90 - t81)
  calc t92 = t78 * 2.0
  calc t93 = t80 * 2.0
  calc t94 = t92 + t90
  calc t95 = t94 - t92
  calc t96 = (t92 - (t94 - t95)) + (t90 - t95)
  calc t97 = t96 + (t93 + t91)
  calc t98 = t94 + t97
  calc t99 = t98 - t94
  calc t100 = (t94 - (t98 - t99)) + (t97 - t99)
  calc t101 = t98 + t100
  when k == 0 yes1 no2
:yes1
  return t101
:no2
  calc t102 = 1.0 + t98
  calc t103 = t102 - 1.0
  calc t104 = (1.0 - (t102 - t103)) + (t98 - t103)
  calc t105 = t104 + t100
  calc t106 = t102 + t105
  calc t107 = t105 - (t106 - t102)
  calc t108 = scaleBy(t106, k)
  when k >= 60 yes3 no4
:yes3
  return t108
:no4
  when k <= -60 yes5 no6
:yes5
  return k109
:no6
  calc t110 = powerOfTwo(k)
  calc t111 = t106 * t110
  calc t112 = t107 * t110
  calc t113 = t111 + (0.0 - 1.0)
  calc t114 = t113 - t111
  calc t115 = (t111 - (t113 - t114)) + ((0.0 - 1.0) - t114)
  calc t116 = t115 + t112
  calc t117 = t113 + t116
  return t117

op logParts "For u = uh + ul > 0: which 0 gives the exponent e (plus extra) with u = 2^e m, m from 0.7 to 1.4; 1 and 2 give the high and low parts of ln m as a double-double"
  input uh Float64 copied
  input ul Float64 copied
  input extra Float64 copied
  input which Int64 copied
  output Float64
  let v8 Int64 0 mut
:begin
  calc t1 = convert.float64BitsToUInt64(uh)
  calc t2 = (t1 >> 52) & 2047
  calc t3 = convert.uint64BitsToInt64(t2)
  calc t4 = t3 - 1023
  calc t5 = t1 & 4503599627370495
  calc t6 = t5 | 4607182418800017408
  calc t7 = convert.uint64BitsToFloat64(t6)
  when t7 > 0x1.6a09e667f3bcdp+0 big1 small2
:big1
  calc v8 := t4 + 1
  goto join3
:small2
  set v8 t4
  goto join3
:join3
  calc t9 = convert.int64ToFloat64(v8)
  calc t10 = t9 + extra
  when which == 0 e4 go5
:e4
  return t10
:go5
  calc t11 = 0 - v8
  calc t12 = scaleBy(uh, t11)
  calc t13 = scaleBy(ul, t11)
  calc t14 = t12 - 1.0
  calc t15 = t14 + t13
  calc t16 = t15 - t14
  calc t17 = (t14 - (t15 - t16)) + (t13 - t16)
  calc t18 = t12 + 1.0
  calc t19 = t18 - t12
  calc t20 = (t12 - (t18 - t19)) + (1.0 - t19)
  calc t21 = t20 + t13
  calc t22 = t15 / t18
  calc t23 = t22 * t18
  calc t24 = t22 * 134217729.0
  calc t25 = t24 - (t24 - t22)
  calc t26 = t22 - t25
  calc t27 = t18 * 134217729.0
  calc t28 = t27 - (t27 - t18)
  calc t29 = t18 - t28
  calc t30 = ((((t25 * t28) - t23) + (t25 * t29)) + (t26 * t28)) + (t26 * t29)
  calc t31 = (((t15 - t23) - t30) + t17) - (t22 * t21)
  calc t32 = t31 / t18
  calc t33 = t22 + t32
  calc t34 = t32 - (t33 - t22)
  calc t35 = t33 * t33
  calc t36 = t33 * 134217729.0
  calc t37 = t36 - (t36 - t33)
  calc t38 = t33 - t37
  calc t39 = t33 * 134217729.0
  calc t40 = t39 - (t39 - t33)
  calc t41 = t33 - t40
  calc t42 = ((((t37 * t40) - t35) + (t37 * t41)) + (t38 * t40)) + (t38 * t41)
  calc t43 = t42 + ((t33 * t34) + (t34 * t33))
  calc t44 = t35 + t43
  calc t45 = t43 - (t44 - t35)
  calc t46 = 0x1.1a7b9611a7b96p-5 + (t44 * 0x1.0842108421084p-5)
  calc t47 = 0x1.2f684bda12f68p-5 + (t44 * t46)
  calc t48 = 0x1.47ae147ae147bp-5 + (t44 * t47)
  calc t49 = 0x1.642c8590b2164p-5 + (t44 * t48)
  calc t50 = 0x1.8618618618618p-5 + (t44 * t49)
  calc t51 = 0x1.af286bca1af28p-5 + (t44 * t50)
  calc t52 = 0x1.e1e1e1e1e1e1ep-5 + (t44 * t51)
  calc t53 = 0x1.1111111111111p-4 + (t44 * t52)
  calc t54 = 0x1.3b13b13b13b14p-4 + (t44 * t53)
  calc t55 = 0x1.745d1745d1746p-4 + (t44 * t54)
  calc t56 = 0x1.c71c71c71c71cp-4 + (t44 * t55)
  calc t57 = t44 * t56
  calc t58 = 0x1.2492492492492p-3 + t57
  calc t59 = t58 - 0x1.2492492492492p-3
  calc t60 = (0x1.2492492492492p-3 - (t58 - t59)) + (t57 - t59)
  calc t61 = t60 + 0x1.2492492492492p-57
  calc t62 = t58 + t61
  calc t63 = t62 - t58
  calc t64 = (t58 - (t62 - t63)) + (t61 - t63)
  calc t65 = t44 * t62
  calc t66 = t44 * 134217729.0
  calc t67 = t66 - (t66 - t44)
  calc t68 = t44 - t67
  calc t69 = t62 * 134217729.0
  calc t70 = t69 - (t69 - t62)
  calc t71 = t62 - t70
  calc t72 = ((((t67 * t70) - t65) + (t67 * t71)) + (t68 * t70)) + (t68 * t71)
  calc t73 = t72 + ((t44 * t64) + (t45 * t62))
  calc t74 = t65 + t73
  calc t75 = t73 - (t74 - t65)
  calc t76 = 0x1.999999999999ap-3 + t74
  calc t77 = t76 - 0x1.999999999999ap-3
  calc t78 = (0x1.999999999999ap-3 - (t76 - t77)) + (t74 - t77)
  calc t79 = t78 + (-0x1.999999999999ap-57 + t75)
  calc t80 = t76 + t79
  calc t81 = t80 - t76
  calc t82 = (t76 - (t80 - t81)) + (t79 - t81)
  calc t83 = t44 * t80
  calc t84 = t44 * 134217729.0
  calc t85 = t84 - (t84 - t44)
  calc t86 = t44 - t85
  calc t87 = t80 * 134217729.0
  calc t88 = t87 - (t87 - t80)
  calc t89 = t80 - t88
  calc t90 = ((((t85 * t88) - t83) + (t85 * t89)) + (t86 * t88)) + (t86 * t89)
  calc t91 = t90 + ((t44 * t82) + (t45 * t80))
  calc t92 = t83 + t91
  calc t93 = t91 - (t92 - t83)
  calc t94 = 0x1.5555555555555p-2 + t92
  calc t95 = t94 - 0x1.5555555555555p-2
  calc t96 = (0x1.5555555555555p-2 - (t94 - t95)) + (t92 - t95)
  calc t97 = t96 + (0x1.5555555555555p-56 + t93)
  calc t98 = t94 + t97
  calc t99 = t98 - t94
  calc t100 = (t94 - (t98 - t99)) + (t97 - t99)
  calc t101 = t44 * t98
  calc t102 = t44 * 134217729.0
  calc t103 = t102 - (t102 - t44)
  calc t104 = t44 - t103
  calc t105 = t98 * 134217729.0
  calc t106 = t105 - (t105 - t98)
  calc t107 = t98 - t106
  calc t108 = ((((t103 * t106) - t101) + (t103 * t107)) + (t104 * t106)) + (t104 * t107)
  calc t109 = t108 + ((t44 * t100) + (t45 * t98))
  calc t110 = t101 + t109
  calc t111 = t109 - (t110 - t101)
  calc t112 = t33 * t110
  calc t113 = t33 * 134217729.0
  calc t114 = t113 - (t113 - t33)
  calc t115 = t33 - t114
  calc t116 = t110 * 134217729.0
  calc t117 = t116 - (t116 - t110)
  calc t118 = t110 - t117
  calc t119 = ((((t114 * t117) - t112) + (t114 * t118)) + (t115 * t117)) + (t115 * t118)
  calc t120 = t119 + ((t33 * t111) + (t34 * t110))
  calc t121 = t112 + t120
  calc t122 = t120 - (t121 - t112)
  calc t123 = t33 + t121
  calc t124 = t123 - t33
  calc t125 = (t33 - (t123 - t124)) + (t121 - t124)
  calc t126 = t125 + (t34 + t122)
  calc t127 = t123 + t126
  calc t128 = t127 - t123
  calc t129 = (t123 - (t127 - t128)) + (t126 - t128)
  calc t130 = t127 * 2.0
  calc t131 = t129 * 2.0
  when which == 1 one6 two7
:one6
  return t130
:two7
  return t131

op expValue "e to the power x, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x > 710.0 yes3 no4
:yes3
  calc t2 = infinityValue()
  return t2
:no4
  when x < -746.0 yes5 no6
:yes5
  return k3
:no6
  calc t4 = x * 0x1.71547652b82fep+0
  calc t5 = t4 + 0x1.8000000000000p+52
  calc t6 = t5 - 0x1.8000000000000p+52
  calc k7 = convert.float64ToInt64(t6)
  calc t8 = t6 * 0x1.62e42ff000000p-1
  calc t9 = t6 * -0x1.718432a200000p-35
  calc t10 = t6 * 0x1.3c7673007e5edp-69
  calc t11 = x + (0.0 - t8)
  calc t12 = t11 - x
  calc t13 = (x - (t11 - t12)) + ((0.0 - t8) - t12)
  calc t14 = t11 + (0.0 - t9)
  calc t15 = t14 - t11
  calc t16 = (t11 - (t14 - t15)) + ((0.0 - t9) - t15)
  calc t17 = ((t13 + t16) - t10)
  calc t18 = t14 + t17
  calc t19 = t17 - (t18 - t14)
  calc t20 = expScaled(t18, t19, k7)
  return t20

op exp2Value "2 to the power x, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x >= 1024.0 yes3 no4
:yes3
  calc t2 = infinityValue()
  return t2
:no4
  when x < -1080.0 yes5 no6
:yes5
  return k3
:no6
  calc t4 = x + 0x1.8000000000000p+52
  calc t5 = t4 - 0x1.8000000000000p+52
  calc t6 = convert.float64ToInt64(t5)
  calc t7 = x - t5
  calc t8 = t7 * 0x1.62e42fefa39efp-1
  calc t9 = t7 * 134217729.0
  calc t10 = t9 - (t9 - t7)
  calc t11 = t7 - t10
  calc t12 = 0x1.62e42fefa39efp-1 * 134217729.0
  calc t13 = t12 - (t12 - 0x1.62e42fefa39efp-1)
  calc t14 = 0x1.62e42fefa39efp-1 - t13
  calc t15 = ((((t10 * t13) - t8) + (t10 * t14)) + (t11 * t13)) + (t11 * t14)
  calc t16 = t15 + (t7 * 0x1.abc9e3b39803fp-56)
  calc t17 = t8 + t16
  calc t18 = t16 - (t17 - t8)
  calc t19 = expScaled(t17, t18, t6)
  return t19

op expm1Value "e to the power x less 1, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 -1.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x > 710.0 yes3 no4
:yes3
  calc t2 = infinityValue()
  return t2
:no4
  when x < -40.0 yes5 no6
:yes5
  return k3
:no6
  calc t4 = absoluteOf(x)
  when t4 < 0x1.0000000000000p-54 yes7 no8
:yes7
  return x
:no8
  calc t5 = x * 0x1.71547652b82fep+0
  calc t6 = t5 + 0x1.8000000000000p+52
  calc t7 = t6 - 0x1.8000000000000p+52
  calc k8 = convert.float64ToInt64(t7)
  calc t9 = t7 * 0x1.62e42ff000000p-1
  calc t10 = t7 * -0x1.718432a200000p-35
  calc t11 = t7 * 0x1.3c7673007e5edp-69
  calc t12 = x + (0.0 - t9)
  calc t13 = t12 - x
  calc t14 = (x - (t12 - t13)) + ((0.0 - t9) - t13)
  calc t15 = t12 + (0.0 - t10)
  calc t16 = t15 - t12
  calc t17 = (t12 - (t15 - t16)) + ((0.0 - t10) - t16)
  calc t18 = ((t14 + t17) - t11)
  calc t19 = t15 + t18
  calc t20 = t18 - (t19 - t15)
  calc t21 = expm1Scaled(t19, t20, k8)
  return t21

op logValue "The natural logarithm of x, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 -1.0
  let k6 Float64 0.0
  let v7 Float64 1.0 mut
  let v8 Float64 0.0 mut
  let k9 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x < 0.0 yes3 no4
:yes3
  calc t2 = invalidValue()
  return t2
:no4
  when x == 0.0 yes5 no6
:yes5
  calc t4 = k3 / 0.0
  return t4
:no6
  when x > 0x1.fffffffffffffp+1023 yes7 no8
:yes7
  calc t5 = infinityValue()
  return t5
:no8
  when x == 1.0 yes9 no10
:yes9
  return k6
:no10
  set v7 x
  when x < 0x1.0000000000000p-1022 sub11 norm12
:sub11
  calc v7 := x * 0x1.0000000000000p+54
  calc v8 := 0.0 - 54.0
  goto norm12
:norm12
  calc t10 = logParts(v7, k9, v8, 0)
  calc t11 = logParts(v7, k9, v8, 1)
  calc t12 = logParts(v7, k9, v8, 2)
  calc t13 = t10 * 0x1.62e42fefa39efp-1
  calc t14 = t10 * 134217729.0
  calc t15 = t14 - (t14 - t10)
  calc t16 = t10 - t15
  calc t17 = 0x1.62e42fefa39efp-1 * 134217729.0
  calc t18 = t17 - (t17 - 0x1.62e42fefa39efp-1)
  calc t19 = 0x1.62e42fefa39efp-1 - t18
  calc t20 = ((((t15 * t18) - t13) + (t15 * t19)) + (t16 * t18)) + (t16 * t19)
  calc t21 = t20 + (t10 * 0x1.abc9e3b39803fp-56)
  calc t22 = t13 + t11
  calc t23 = t22 - t13
  calc t24 = (t13 - (t22 - t23)) + (t11 - t23)
  calc t25 = t24 + (t21 + t12)
  calc t26 = t22 + t25
  calc t27 = t26 - t22
  calc t28 = (t22 - (t26 - t27)) + (t25 - t27)
  return t26

op log2Value "The base 2 logarithm of x, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 -1.0
  let k6 Float64 0.0
  let v7 Float64 1.0 mut
  let v8 Float64 0.0 mut
  let k9 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x < 0.0 yes3 no4
:yes3
  calc t2 = invalidValue()
  return t2
:no4
  when x == 0.0 yes5 no6
:yes5
  calc t4 = k3 / 0.0
  return t4
:no6
  when x > 0x1.fffffffffffffp+1023 yes7 no8
:yes7
  calc t5 = infinityValue()
  return t5
:no8
  when x == 1.0 yes9 no10
:yes9
  return k6
:no10
  set v7 x
  when x < 0x1.0000000000000p-1022 sub11 norm12
:sub11
  calc v7 := x * 0x1.0000000000000p+54
  calc v8 := 0.0 - 54.0
  goto norm12
:norm12
  calc t10 = logParts(v7, k9, v8, 0)
  calc t11 = logParts(v7, k9, v8, 1)
  calc t12 = logParts(v7, k9, v8, 2)
  calc t13 = t11 * 0x1.71547652b82fep+0
  calc t14 = t11 * 134217729.0
  calc t15 = t14 - (t14 - t11)
  calc t16 = t11 - t15
  calc t17 = 0x1.71547652b82fep+0 * 134217729.0
  calc t18 = t17 - (t17 - 0x1.71547652b82fep+0)
  calc t19 = 0x1.71547652b82fep+0 - t18
  calc t20 = ((((t15 * t18) - t13) + (t15 * t19)) + (t16 * t18)) + (t16 * t19)
  calc t21 = t20 + ((t11 * 0x1.777d0ffda0d24p-56) + (t12 * 0x1.71547652b82fep+0))
  calc t22 = t13 + t21
  calc t23 = t21 - (t22 - t13)
  calc t24 = t10 + t22
  calc t25 = t24 - t10
  calc t26 = (t10 - (t24 - t25)) + (t22 - t25)
  calc t27 = t26 + t23
  calc t28 = t24 + t27
  return t28

op log10Value "The base 10 logarithm of x, as a double"
  input x Float64 copied
  output Float64
  let k3 Float64 -1.0
  let k6 Float64 0.0
  let v7 Float64 1.0 mut
  let v8 Float64 0.0 mut
  let k9 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x < 0.0 yes3 no4
:yes3
  calc t2 = invalidValue()
  return t2
:no4
  when x == 0.0 yes5 no6
:yes5
  calc t4 = k3 / 0.0
  return t4
:no6
  when x > 0x1.fffffffffffffp+1023 yes7 no8
:yes7
  calc t5 = infinityValue()
  return t5
:no8
  when x == 1.0 yes9 no10
:yes9
  return k6
:no10
  set v7 x
  when x < 0x1.0000000000000p-1022 sub11 norm12
:sub11
  calc v7 := x * 0x1.0000000000000p+54
  calc v8 := 0.0 - 54.0
  goto norm12
:norm12
  calc t10 = logParts(v7, k9, v8, 0)
  calc t11 = logParts(v7, k9, v8, 1)
  calc t12 = logParts(v7, k9, v8, 2)
  calc t13 = t10 * 0x1.34413509f79ffp-2
  calc t14 = t10 * 134217729.0
  calc t15 = t14 - (t14 - t10)
  calc t16 = t10 - t15
  calc t17 = 0x1.34413509f79ffp-2 * 134217729.0
  calc t18 = t17 - (t17 - 0x1.34413509f79ffp-2)
  calc t19 = 0x1.34413509f79ffp-2 - t18
  calc t20 = ((((t15 * t18) - t13) + (t15 * t19)) + (t16 * t18)) + (t16 * t19)
  calc t21 = t20 + (t10 * -0x1.9dc1da994fd21p-59)
  calc t22 = t11 * 0x1.bcb7b1526e50ep-2
  calc t23 = t11 * 134217729.0
  calc t24 = t23 - (t23 - t11)
  calc t25 = t11 - t24
  calc t26 = 0x1.bcb7b1526e50ep-2 * 134217729.0
  calc t27 = t26 - (t26 - 0x1.bcb7b1526e50ep-2)
  calc t28 = 0x1.bcb7b1526e50ep-2 - t27
  calc t29 = ((((t24 * t27) - t22) + (t24 * t28)) + (t25 * t27)) + (t25 * t28)
  calc t30 = t29 + ((t11 * 0x1.95355baaafad3p-57) + (t12 * 0x1.bcb7b1526e50ep-2))
  calc t31 = t22 + t30
  calc t32 = t30 - (t31 - t22)
  calc t33 = t13 + t31
  calc t34 = t33 - t13
  calc t35 = (t13 - (t33 - t34)) + (t31 - t34)
  calc t36 = t35 + (t21 + t32)
  calc t37 = t33 + t36
  calc t38 = t37 - t33
  calc t39 = (t33 - (t37 - t38)) + (t36 - t38)
  return t37

op log1pValue "The natural logarithm of 1 + x, as a double"
  input x Float64 copied
  output Float64
  let k2 Float64 -1.0
  let k10 Float64 0.0
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x == -1.0 yes3 no4
:yes3
  calc t3 = k2 / 0.0
  return t3
:no4
  when x < -1.0 yes5 no6
:yes5
  calc t4 = invalidValue()
  return t4
:no6
  when x > 0x1.fffffffffffffp+1023 yes7 no8
:yes7
  calc t5 = infinityValue()
  return t5
:no8
  calc t6 = absoluteOf(x)
  when t6 < 0x1.0000000000000p-54 yes9 no10
:yes9
  return x
:no10
  calc t7 = 1.0 + x
  calc t8 = t7 - 1.0
  calc t9 = (1.0 - (t7 - t8)) + (x - t8)
  calc t11 = logParts(t7, t9, k10, 0)
  calc t12 = logParts(t7, t9, k10, 1)
  calc t13 = logParts(t7, t9, k10, 2)
  calc t14 = t11 * 0x1.62e42fefa39efp-1
  calc t15 = t11 * 134217729.0
  calc t16 = t15 - (t15 - t11)
  calc t17 = t11 - t16
  calc t18 = 0x1.62e42fefa39efp-1 * 134217729.0
  calc t19 = t18 - (t18 - 0x1.62e42fefa39efp-1)
  calc t20 = 0x1.62e42fefa39efp-1 - t19
  calc t21 = ((((t16 * t19) - t14) + (t16 * t20)) + (t17 * t19)) + (t17 * t20)
  calc t22 = t21 + (t11 * 0x1.abc9e3b39803fp-56)
  calc t23 = t14 + t12
  calc t24 = t23 - t14
  calc t25 = (t14 - (t23 - t24)) + (t12 - t24)
  calc t26 = t25 + (t22 + t13)
  calc t27 = t23 + t26
  calc t28 = t27 - t23
  calc t29 = (t23 - (t27 - t28)) + (t26 - t28)
  return t27

op powValue "x to the power y, as a double, with C99's special values"
  input x Float64 copied
  input y Float64 copied
  output Float64
  let k1 Float64 1.0
  let k2 Float64 0.0
  let v16 Float64 1.0 mut
  let v17 Float64 0.0 mut
  let k18 Float64 0.0
  let v38 Float64 0.0 mut
  let v50 Float64 0.0 mut
:begin
  when y == 0.0 yes1 no2
:yes1
  return k1
:no2
  when x == 1.0 yes3 no4
:yes3
  return k1
:no4
  when (!(x == x)) || (!(y == y)) yes5 no6
:yes5
  calc t3 = x + y
  return t3
:no6
  calc t4 = absoluteOf(x)
  calc t5 = absoluteOf(y)
  when t5 > 0x1.fffffffffffffp+1023 yes7 no8
:yes7
  when t4 == 1.0 yes9 no10
:yes9
  return k1
:no10
  when y > 0.0 up11 down12
:up11
  when t4 > 1.0 yes13 no14
:yes13
  calc t6 = infinityValue()
  return t6
:no14
  return k2
:down12
  when t4 > 1.0 yes15 no16
:yes15
  return k2
:no16
  calc t7 = infinityValue()
  return t7
:no8
  calc t8 = integerKind(y)
  when x == 0.0 yes17 no18
:yes17
  when y < 0.0 neg19 pos20
:neg19
  when t8 == 1 yes21 no22
:yes21
  calc t9 = signedLike(infinityValue(), x)
  return t9
:no22
  calc t10 = infinityValue()
  return t10
:pos20
  when t8 == 1 yes23 no24
:yes23
  return x
:no24
  return k2
:no18
  when t4 > 0x1.fffffffffffffp+1023 yes25 no26
:yes25
  when x > 0.0 pinf27 ninf28
:pinf27
  when y < 0.0 yes29 no30
:yes29
  return k2
:no30
  calc t11 = infinityValue()
  return t11
:ninf28
  when y < 0.0 yn31 yp32
:yn31
  when t8 == 1 yes33 no34
:yes33
  calc t12 = signedLike(0.0, x)
  return t12
:no34
  return k2
:yp32
  when t8 == 1 yes35 no36
:yes35
  return x
:no36
  calc t13 = infinityValue()
  return t13
:no26
  when (x < 0.0) && (t8 == 0) yes37 no38
:yes37
  calc t14 = invalidValue()
  return t14
:no38
  calc t15 = (x < 0.0) && (t8 == 1)
  set v16 t4
  when t4 < 0x1.0000000000000p-1022 sub39 norm40
:sub39
  calc v16 := t4 * 0x1.0000000000000p+54
  calc v17 := 0.0 - 54.0
  goto norm40
:norm40
  calc t19 = logParts(v16, k18, v17, 0)
  calc t20 = logParts(v16, k18, v17, 1)
  calc t21 = logParts(v16, k18, v17, 2)
  calc t22 = t19 * 0x1.62e42fefa39efp-1
  calc t23 = t19 * 134217729.0
  calc t24 = t23 - (t23 - t19)
  calc t25 = t19 - t24
  calc t26 = 0x1.62e42fefa39efp-1 * 134217729.0
  calc t27 = t26 - (t26 - 0x1.62e42fefa39efp-1)
  calc t28 = 0x1.62e42fefa39efp-1 - t27
  calc t29 = ((((t24 * t27) - t22) + (t24 * t28)) + (t25 * t27)) + (t25 * t28)
  calc t30 = t29 + (t19 * 0x1.abc9e3b39803fp-56)
  calc t31 = t22 + t20
  calc t32 = t31 - t22
  calc t33 = (t22 - (t31 - t32)) + (t20 - t32)
  calc t34 = t33 + (t30 + t21)
  calc t35 = t31 + t34
  calc t36 = t35 - t31
  calc t37 = (t31 - (t35 - t36)) + (t34 - t36)
  set v38 y
  when t5 > 0x1.0000000000000p+100 big41 keep42
:big41
  calc v38 := signedLike(0x1.0000000000000p+100, y)
  goto keep42
:keep42
  calc t39 = t35 * v38
  calc t40 = t35 * 134217729.0
  calc t41 = t40 - (t40 - t35)
  calc t42 = t35 - t41
  calc t43 = v38 * 134217729.0
  calc t44 = t43 - (t43 - v38)
  calc t45 = v38 - t44
  calc t46 = ((((t41 * t44) - t39) + (t41 * t45)) + (t42 * t44)) + (t42 * t45)
  calc t47 = t46 + (t37 * v38)
  calc t48 = t39 + t47
  calc t49 = t47 - (t48 - t39)
  when t48 > 710.0 over44 nover45
:over44
  calc v50 := infinityValue()
  goto sign43
:nover45
  when t48 < -746.0 under46 nunder47
:under46
  set v50 k2
  goto sign43
:nunder47
  calc t51 = t48 * 0x1.71547652b82fep+0
  calc t52 = t51 + 0x1.8000000000000p+52
  calc t53 = t52 - 0x1.8000000000000p+52
  calc k54 = convert.float64ToInt64(t53)
  calc t55 = t53 * 0x1.62e42ff000000p-1
  calc t56 = t53 * -0x1.718432a200000p-35
  calc t57 = t53 * 0x1.3c7673007e5edp-69
  calc t58 = t48 + (0.0 - t55)
  calc t59 = t58 - t48
  calc t60 = (t48 - (t58 - t59)) + ((0.0 - t55) - t59)
  calc t61 = t58 + (0.0 - t56)
  calc t62 = t61 - t58
  calc t63 = (t58 - (t61 - t62)) + ((0.0 - t56) - t62)
  calc t64 = (((t60 + t63) - t57) + t49)
  calc t65 = t61 + t64
  calc t66 = t64 - (t65 - t61)
  calc t67 = expScaled(t65, t66, k54)
  set v50 t67
  goto sign43
:sign43
  when t15 flip48 keepit49
:flip48
  calc t68 = v50 * -1.0
  return t68
:keepit49
  return v50

op cbrtValue "The cube root of x, as a double"
  input x Float64 copied
  output Float64
  let v3 Float64 1.0 mut
  let v4 Int64 0 mut
  let v15 Float64 1.5 mut
:begin
  when !(x == x) yes1 no2
:yes1
  calc t1 = x + x
  return t1
:no2
  when x == 0.0 yes3 no4
:yes3
  return x
:no4
  when (x > 0x1.fffffffffffffp+1023) || (x < -0x1.fffffffffffffp+1023) yes5 no6
:yes5
  return x
:no6
  calc t2 = absoluteOf(x)
  set v3 t2
  when t2 < 0x1.0000000000000p-1022 sub7 norm8
:sub7
  calc v3 := t2 * 0x1.0000000000000p+54
  calc v4 := 0 - 18
  goto norm8
:norm8
  calc t5 = convert.float64BitsToUInt64(v3)
  calc t6 = (t5 >> 52) & 2047
  calc t7 = convert.uint64BitsToInt64(t6)
  calc t8 = (t7 - 1023) + 3000
  calc t9 = t8 / 3
  calc t10 = t8 - (3 * t9)
  calc t11 = (t9 - 1000) + v4
  calc t12 = 3 * (t9 - 1000)
  calc t13 = 0 - t12
  calc t14 = scaleBy(v3, t13)
  calc t16 = v15 * v15
  calc t17 = t14 / t16
  calc t18 = ((v15 * 2.0) + t17) / 3.0
  set v15 t18
  calc t19 = v15 * v15
  calc t20 = t14 / t19
  calc t21 = ((v15 * 2.0) + t20) / 3.0
  set v15 t21
  calc t22 = v15 * v15
  calc t23 = t14 / t22
  calc t24 = ((v15 * 2.0) + t23) / 3.0
  set v15 t24
  calc t25 = v15 * v15
  calc t26 = t14 / t25
  calc t27 = ((v15 * 2.0) + t26) / 3.0
  set v15 t27
  calc t28 = v15 * v15
  calc t29 = t14 / t28
  calc t30 = ((v15 * 2.0) + t29) / 3.0
  set v15 t30
  calc t31 = v15 * v15
  calc t32 = t14 / t31
  calc t33 = ((v15 * 2.0) + t32) / 3.0
  set v15 t33
  calc t34 = v15 * v15
  calc t35 = t14 / t34
  calc t36 = ((v15 * 2.0) + t35) / 3.0
  set v15 t36
  calc t37 = v15 * v15
  calc t38 = t14 / t37
  calc t39 = ((v15 * 2.0) + t38) / 3.0
  set v15 t39
  calc t40 = v15 * v15
  calc t41 = t14 / t40
  calc t42 = ((v15 * 2.0) + t41) / 3.0
  set v15 t42
  calc t43 = v15 * v15
  calc t44 = v15 * 134217729.0
  calc t45 = t44 - (t44 - v15)
  calc t46 = v15 - t45
  calc t47 = v15 * 134217729.0
  calc t48 = t47 - (t47 - v15)
  calc t49 = v15 - t48
  calc t50 = ((((t45 * t48) - t43) + (t45 * t49)) + (t46 * t48)) + (t46 * t49)
  calc t51 = t43 * v15
  calc t52 = t43 * 134217729.0
  calc t53 = t52 - (t52 - t43)
  calc t54 = t43 - t53
  calc t55 = v15 * 134217729.0
  calc t56 = t55 - (t55 - v15)
  calc t57 = v15 - t56
  calc t58 = ((((t53 * t56) - t51) + (t53 * t57)) + (t54 * t56)) + (t54 * t57)
  calc t59 = t58 + (t50 * v15)
  calc t60 = t51 + t59
  calc t61 = t59 - (t60 - t51)
  calc t62 = ((t14 - t60) - t61)
  calc t63 = (v15 * v15) * 3.0
  calc t64 = t62 / t63
  calc t65 = v15 + t64
  calc t66 = scaleBy(t65, t11)
  calc t67 = signedLike(t66, x)
  return t67

op hypotValue "The square root of x*x + y*y without undue overflow or underflow, as a double"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let v5 Float64 0.0 mut
  let v6 Float64 0.0 mut
  let v10 Int64 0 mut
  let v11 Float64 0.0 mut
  let v12 Float64 0.0 mut
  let v13 Int64 0 mut
:begin
  calc t1 = absoluteOf(x)
  calc t2 = absoluteOf(y)
  when (t1 > 0x1.fffffffffffffp+1023) || (t2 > 0x1.fffffffffffffp+1023) yes1 no2
:yes1
  calc t3 = infinityValue()
  return t3
:no2
  when (!(x == x)) || (!(y == y)) yes3 no4
:yes3
  calc t4 = x + y
  return t4
:no4
  set v5 t1
  set v6 t2
  when t2 > t1 sw5 nsw6
:sw5
  set v5 t2
  set v6 t1
  goto nsw6
:nsw6
  when v6 <= (v5 * 0x1.0000000000000p-30) yes7 no8
:yes7
  return v5
:no8
  calc t7 = convert.float64BitsToUInt64(v5)
  calc t8 = (t7 >> 52) & 2047
  calc t9 = convert.uint64BitsToInt64(t8)
  calc v10 := t9 - 1023
  set v11 v5
  set v12 v6
  when t9 == 0 sub9 norm10
:sub9
  calc v11 := v5 * 0x1.0000000000000p+200
  calc v12 := v6 * 0x1.0000000000000p+200
  calc v13 := 0 - 200
  goto norm10
:norm10
  calc t14 = convert.float64BitsToUInt64(v11)
  calc t15 = (t14 >> 52) & 2047
  calc t16 = convert.uint64BitsToInt64(t15)
  calc t17 = t16 - 1023
  calc t18 = 0 - t17
  calc t19 = scaleBy(v11, t18)
  calc t20 = scaleBy(v12, t18)
  calc t21 = t19 * t19
  calc t22 = t19 * 134217729.0
  calc t23 = t22 - (t22 - t19)
  calc t24 = t19 - t23
  calc t25 = t19 * 134217729.0
  calc t26 = t25 - (t25 - t19)
  calc t27 = t19 - t26
  calc t28 = ((((t23 * t26) - t21) + (t23 * t27)) + (t24 * t26)) + (t24 * t27)
  calc t29 = t20 * t20
  calc t30 = t20 * 134217729.0
  calc t31 = t30 - (t30 - t20)
  calc t32 = t20 - t31
  calc t33 = t20 * 134217729.0
  calc t34 = t33 - (t33 - t20)
  calc t35 = t20 - t34
  calc t36 = ((((t31 * t34) - t29) + (t31 * t35)) + (t32 * t34)) + (t32 * t35)
  calc t37 = t21 + t29
  calc t38 = t37 - t21
  calc t39 = (t21 - (t37 - t38)) + (t29 - t38)
  calc t40 = t39 + (t28 + t36)
  calc t41 = t37 + t40
  calc t42 = t41 - t37
  calc t43 = (t37 - (t41 - t42)) + (t40 - t42)
  calc t44 = machine.squareRoot(t41)
  calc t45 = t44 * t44
  calc t46 = t44 * 134217729.0
  calc t47 = t46 - (t46 - t44)
  calc t48 = t44 - t47
  calc t49 = t44 * 134217729.0
  calc t50 = t49 - (t49 - t44)
  calc t51 = t44 - t50
  calc t52 = ((((t47 * t50) - t45) + (t47 * t51)) + (t48 * t50)) + (t48 * t51)
  calc t53 = (((t41 - t45) - t52) + t43)
  calc t54 = t53 / (t44 * 2.0)
  calc t55 = t44 + t54
  calc t56 = t17 + v13
  calc t57 = scaleBy(t55, t56)
  return t57

op exponential "exp: e to the power x, as a double"
  invariant givesExp "Gives e^x correctly rounded but for the rarest cases: 1 at 0, infinity past 709.78, 0 below -745.13"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "exp"
:begin
  calc t1 = expValue(x)
  calc t2 = absoluteOf(x) <= 0x1.fffffffffffffp+1023
  noteRange(t1, t2, t2)
  return t1

op exponentialSingle "exp: e to the power x for floats"
  invariant givesExp "Gives e^x correctly rounded but for the rarest cases: 1 at 0, infinity past 709.78, 0 below -745.13"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "expf"
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = expValue(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  calc t5 = absoluteOf(w1) <= 0x1.fffffffffffffp+1023
  noteRange(t4, t5, t5)
  return t3

op exponentialBase2 "exp2: 2 to the power x, as a double"
  invariant givesExp2 "Gives 2^x, exact for whole x, infinity from 1024, 0 below -1075"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "exp2"
:begin
  calc t1 = exp2Value(x)
  calc t2 = absoluteOf(x) <= 0x1.fffffffffffffp+1023
  noteRange(t1, t2, t2)
  return t1

op exponentialBase2Single "exp2: 2 to the power x for floats"
  invariant givesExp2 "Gives 2^x, exact for whole x, infinity from 1024, 0 below -1075"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "exp2f"
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = exp2Value(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  calc t5 = absoluteOf(w1) <= 0x1.fffffffffffffp+1023
  noteRange(t4, t5, t5)
  return t3

op exponentialMinusOne "expm1: e to the power x less 1, as a double"
  invariant givesExpm1 "Gives e^x - 1 accurately for small x, -1 below -40, x itself for tiny x and for -0"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "expm1"
  let k3 Bool false
:begin
  calc t1 = expm1Value(x)
  calc t2 = absoluteOf(x) <= 0x1.fffffffffffffp+1023
  noteRange(t1, t2, k3)
  return t1

op exponentialMinusOneSingle "expm1: e to the power x less 1 for floats"
  invariant givesExpm1 "Gives e^x - 1 accurately for small x, -1 below -40, x itself for tiny x and for -0"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "expm1f"
  let k6 Bool false
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = expm1Value(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  calc t5 = absoluteOf(w1) <= 0x1.fffffffffffffp+1023
  noteRange(t4, t5, k6)
  return t3

op naturalLogarithm "log: the natural logarithm, as a double"
  invariant givesLog "Gives ln x: -infinity at 0, NaN below 0, 0 at 1"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "log"
  let k2 Float64 0.0
:begin
  calc t1 = logValue(x)
  noteDomain(x, k2)
  return t1

op naturalLogarithmSingle "log: the natural logarithm for floats"
  invariant givesLog "Gives ln x: -infinity at 0, NaN below 0, 0 at 1"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "logf"
  let k5 Float64 0.0
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = logValue(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  noteDomain(w1, k5)
  return t3

op logarithmBase2 "log2: the base 2 logarithm, as a double"
  invariant givesLog2 "Gives log2 x, exact at powers of 2"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "log2"
  let k2 Float64 0.0
:begin
  calc t1 = log2Value(x)
  noteDomain(x, k2)
  return t1

op logarithmBase2Single "log2: the base 2 logarithm for floats"
  invariant givesLog2 "Gives log2 x, exact at powers of 2"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "log2f"
  let k5 Float64 0.0
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = log2Value(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  noteDomain(w1, k5)
  return t3

op logarithmBase10 "log10: the base 10 logarithm, as a double"
  invariant givesLog10 "Gives log10 x, exact at powers of 10"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "log10"
  let k2 Float64 0.0
:begin
  calc t1 = log10Value(x)
  noteDomain(x, k2)
  return t1

op logarithmBase10Single "log10: the base 10 logarithm for floats"
  invariant givesLog10 "Gives log10 x, exact at powers of 10"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "log10f"
  let k5 Float64 0.0
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = log10Value(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  noteDomain(w1, k5)
  return t3

op logarithmOnePlus "log1p: the natural logarithm of 1 + x, as a double"
  invariant givesLog1p "Gives ln(1 + x) accurately for small x, -infinity at -1, NaN below"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "log1p"
  let k2 Float64 -1.0
:begin
  calc t1 = log1pValue(x)
  noteDomain(x, k2)
  return t1

op logarithmOnePlusSingle "log1p: the natural logarithm of 1 + x for floats"
  invariant givesLog1p "Gives ln(1 + x) accurately for small x, -infinity at -1, NaN below"
  input x Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "log1pf"
  let k5 Float64 -1.0
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = log1pValue(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  noteDomain(w1, k5)
  return t3

op power "pow: x to the power y, as a double"
  invariant givesPow "Gives x^y with C99's special values: 1 for y 0 and for x 1, NaN for a negative x and a fractional y"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "pow"
:begin
  calc t1 = powValue(x, y)
  calc t2 = absoluteOf(x) <= 0x1.fffffffffffffp+1023
  calc t3 = absoluteOf(y) <= 0x1.fffffffffffffp+1023
  calc t4 = t2 && t3
  calc t5 = t4 && (x != 0.0)
  noteRange(t1, t4, t5)
  calc t6 = (x == x) && (y == y)
  noteInvalid(t1, t6)
  return t1

op powerSingle "pow: x to the power y for floats"
  invariant givesPow "Gives x^y with C99's special values: 1 for y 0 and for x 1, NaN for a negative x and a fractional y"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "powf"
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc w2 = convert.float32ToFloat64(y)
  calc t3 = powValue(w1, w2)
  calc t4 = narrowOf(t3)
  calc t5 = convert.float32ToFloat64(t4)
  calc t6 = absoluteOf(w1) <= 0x1.fffffffffffffp+1023
  calc t7 = absoluteOf(w2) <= 0x1.fffffffffffffp+1023
  calc t8 = t6 && t7
  calc t9 = t8 && (w1 != 0.0)
  noteRange(t5, t8, t9)
  calc t10 = (w1 == w1) && (w2 == w2)
  noteInvalid(t5, t10)
  return t4

op cubeRoot "cbrt: the cube root, as a double"
  invariant givesCbrt "Gives the cube root of any sign, exact at cubes"
  input x Float64 copied
  output Float64
  abi library "cbrt"
:begin
  calc t1 = cbrtValue(x)
  return t1

op cubeRootSingle "cbrt: the cube root for floats"
  invariant givesCbrt "Gives the cube root of any sign, exact at cubes"
  input x Float32 copied
  output Float32
  abi library "cbrtf"
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc t2 = cbrtValue(w1)
  calc t3 = narrowOf(t2)
  calc t4 = convert.float32ToFloat64(t3)
  return t3

op hypotenuse "hypot: the square root of x*x + y*y, as a double"
  invariant givesHypot "Gives sqrt(x*x + y*y) without overflow in the squares, infinity if either is infinite"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "hypot"
  let k5 Bool false
:begin
  calc t1 = hypotValue(x, y)
  calc t2 = absoluteOf(x) <= 0x1.fffffffffffffp+1023
  calc t3 = absoluteOf(y) <= 0x1.fffffffffffffp+1023
  calc t4 = t2 && t3
  noteRange(t1, t4, k5)
  return t1

op hypotenuseSingle "hypot: the square root of x*x + y*y for floats"
  invariant givesHypot "Gives sqrt(x*x + y*y) without overflow in the squares, infinity if either is infinite"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "hypotf"
  let k9 Bool false
:begin
  calc w1 = convert.float32ToFloat64(x)
  calc w2 = convert.float32ToFloat64(y)
  calc t3 = hypotValue(w1, w2)
  calc t4 = narrowOf(t3)
  calc t5 = convert.float32ToFloat64(t4)
  calc t6 = absoluteOf(w1) <= 0x1.fffffffffffffp+1023
  calc t7 = absoluteOf(w2) <= 0x1.fffffffffffffp+1023
  calc t8 = t6 && t7
  noteRange(t5, t8, k9)
  return t4

@tests

op withinUlps "Whether a double is the expected one or a neighbour of it"
  input expected Float64 copied
  input actual Float64 copied
  input limit Int64 copied
  output Bool
:begin
  calc same = expected == actual
  when same yes check
:yes
  return same
:check
  calc eb = convert.float64BitsToUInt64(absoluteOf(expected))
  calc ab = convert.float64BitsToUInt64(absoluteOf(actual))
  calc ei = convert.uint64BitsToInt64(eb)
  calc ai = convert.uint64BitsToInt64(ab)
  calc gap = ei - ai
  calc distance = ai - ei
  calc negative = (expected < 0.0) && (actual < 0.0)
  calc positive = (expected >= 0.0) && (actual >= 0.0)
  calc sameSign = negative || positive
  calc near1 = (gap <= limit) && (distance <= limit)
  calc result = sameSign && near1
  return result

op closeSingle "Whether a float is within a float's last place of an expected double"
  input expected Float64 copied
  input actual Float32 copied
  output Bool
:begin
  calc wide = convert.float32ToFloat64(actual)
  calc diff = absoluteOf(wide - expected)
  calc bound = absoluteOf(expected) * 1.1920929e-7
  calc near = diff <= bound
  return near

test expTest "exp, exp2, expm1 give the correctly rounded value within one last place at sample points, in double and float forms"
  verifies exponential givesExp
  verifies exponentialSingle givesExp
  verifies exponentialBase2 givesExp2
  verifies exponentialBase2Single givesExp2
  verifies exponentialMinusOne givesExpm1
  verifies exponentialMinusOneSingle givesExpm1
  effect use machine.memory
  uses memoryAccess
:begin
  calc expd0 = exponential(0x0.0p+0)
  calc expdok0 = withinUlps(0x1.0000000000000p+0, expd0, 1)
  test.assertTrue(expdok0)
  calc expf0 = exponentialSingle(convert.float64ToFloat32(0x0.0p+0))
  calc expfok0 = closeSingle(0x1.0000000000000p+0, expf0)
  test.assertTrue(expfok0)
  calc expd1 = exponential(0x1.0000000000000p+0)
  calc expdok1 = withinUlps(0x1.5bf0a8b145769p+1, expd1, 1)
  test.assertTrue(expdok1)
  calc expf1 = exponentialSingle(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc expfok1 = closeSingle(0x1.5bf0a8b145769p+1, expf1)
  test.assertTrue(expfok1)
  calc expd2 = exponential(-0x1.0000000000000p+0)
  calc expdok2 = withinUlps(0x1.78b56362cef38p-2, expd2, 1)
  test.assertTrue(expdok2)
  calc expf2 = exponentialSingle(convert.float64ToFloat32(-0x1.0000000000000p+0))
  calc expfok2 = closeSingle(0x1.78b56362cef38p-2, expf2)
  test.assertTrue(expfok2)
  calc expd3 = exponential(0x1.0000000000000p-1)
  calc expdok3 = withinUlps(0x1.a61298e1e069cp+0, expd3, 1)
  test.assertTrue(expdok3)
  calc expf3 = exponentialSingle(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc expfok3 = closeSingle(0x1.a61298e1e069cp+0, expf3)
  test.assertTrue(expfok3)
  calc expd4 = exponential(0x1.4000000000000p+3)
  calc expdok4 = withinUlps(0x1.5829dcf950560p+14, expd4, 1)
  test.assertTrue(expdok4)
  calc expf4 = exponentialSingle(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc expfok4 = closeSingle(0x1.5829dcf950560p+14, expf4)
  test.assertTrue(expfok4)
  calc expd5 = exponential(-0x1.4000000000000p+3)
  calc expdok5 = withinUlps(0x1.7cd79b5647c9bp-15, expd5, 1)
  test.assertTrue(expdok5)
  calc expf5 = exponentialSingle(convert.float64ToFloat32(-0x1.4000000000000p+3))
  calc expfok5 = closeSingle(0x1.7cd79b5647c9bp-15, expf5)
  test.assertTrue(expfok5)
  calc expd6 = exponential(0x1.9000000000000p+6)
  calc expdok6 = withinUlps(0x1.3494a9b171bf5p+144, expd6, 1)
  test.assertTrue(expdok6)
  calc expd7 = exponential(0x1.6280000000000p+9)
  calc expdok7 = withinUlps(0x1.d422d2be5dc9bp+1022, expd7, 1)
  test.assertTrue(expdok7)
  calc expd8 = exponential(-0x1.5e00000000000p+9)
  calc expdok8 = withinUlps(0x1.14f2b0fb9307fp-1010, expd8, 1)
  test.assertTrue(expdok8)
  calc expd9 = exponential(0x1.b7cdfd9d7bdbbp-34)
  calc expdok9 = withinUlps(0x1.000000006df38p+0, expd9, 1)
  test.assertTrue(expdok9)
  calc expd10 = exponential(0x1.3333333333333p-2)
  calc expdok10 = withinUlps(0x1.599058c8c1a96p+0, expd10, 1)
  test.assertTrue(expdok10)
  calc expd11 = exponential(-0x1.7200000000000p+9)
  calc expdok11 = withinUlps(0x0.0000000000055p-1022, expd11, 1)
  test.assertTrue(expdok11)
  calc expd12 = exponential(-0x1.7480000000000p+9)
  calc expdok12 = withinUlps(0x0.0000000000001p-1022, expd12, 1)
  test.assertTrue(expdok12)
  calc expd13 = exponential(0x1.4800000000000p+4)
  calc expdok13 = withinUlps(0x1.7d6c4f0bcdd5cp+29, expd13, 1)
  test.assertTrue(expdok13)
  calc expf13 = exponentialSingle(convert.float64ToFloat32(0x1.4800000000000p+4))
  calc expfok13 = closeSingle(0x1.7d6c4f0bcdd5cp+29, expf13)
  test.assertTrue(expfok13)
  calc expd14 = exponential(-0x1.a36e2eb1c432dp-14)
  calc expdok14 = withinUlps(0x1.fff2e4b97d31dp-1, expd14, 1)
  test.assertTrue(expdok14)
  calc exp2d0 = exponentialBase2(0x0.0p+0)
  calc exp2dok0 = withinUlps(0x1.0000000000000p+0, exp2d0, 1)
  test.assertTrue(exp2dok0)
  calc exp2f0 = exponentialBase2Single(convert.float64ToFloat32(0x0.0p+0))
  calc exp2fok0 = closeSingle(0x1.0000000000000p+0, exp2f0)
  test.assertTrue(exp2fok0)
  calc exp2d1 = exponentialBase2(0x1.0000000000000p+0)
  calc exp2dok1 = withinUlps(0x1.0000000000000p+1, exp2d1, 1)
  test.assertTrue(exp2dok1)
  calc exp2f1 = exponentialBase2Single(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc exp2fok1 = closeSingle(0x1.0000000000000p+1, exp2f1)
  test.assertTrue(exp2fok1)
  calc exp2d2 = exponentialBase2(-0x1.0000000000000p+0)
  calc exp2dok2 = withinUlps(0x1.0000000000000p-1, exp2d2, 1)
  test.assertTrue(exp2dok2)
  calc exp2f2 = exponentialBase2Single(convert.float64ToFloat32(-0x1.0000000000000p+0))
  calc exp2fok2 = closeSingle(0x1.0000000000000p-1, exp2f2)
  test.assertTrue(exp2fok2)
  calc exp2d3 = exponentialBase2(0x1.0000000000000p-1)
  calc exp2dok3 = withinUlps(0x1.6a09e667f3bcdp+0, exp2d3, 1)
  test.assertTrue(exp2dok3)
  calc exp2f3 = exponentialBase2Single(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc exp2fok3 = closeSingle(0x1.6a09e667f3bcdp+0, exp2f3)
  test.assertTrue(exp2fok3)
  calc exp2d4 = exponentialBase2(0x1.4000000000000p+3)
  calc exp2dok4 = withinUlps(0x1.0000000000000p+10, exp2d4, 1)
  test.assertTrue(exp2dok4)
  calc exp2f4 = exponentialBase2Single(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc exp2fok4 = closeSingle(0x1.0000000000000p+10, exp2f4)
  test.assertTrue(exp2fok4)
  calc exp2d5 = exponentialBase2(-0x1.5000000000000p+3)
  calc exp2dok5 = withinUlps(0x1.6a09e667f3bcdp-11, exp2d5, 1)
  test.assertTrue(exp2dok5)
  calc exp2f5 = exponentialBase2Single(convert.float64ToFloat32(-0x1.5000000000000p+3))
  calc exp2fok5 = closeSingle(0x1.6a09e667f3bcdp-11, exp2f5)
  test.assertTrue(exp2fok5)
  calc exp2d6 = exponentialBase2(0x1.9100000000000p+6)
  calc exp2dok6 = withinUlps(0x1.306fe0a31b715p+100, exp2d6, 1)
  test.assertTrue(exp2dok6)
  calc exp2f6 = exponentialBase2Single(convert.float64ToFloat32(0x1.9100000000000p+6))
  calc exp2fok6 = closeSingle(0x1.306fe0a31b715p+100, exp2f6)
  test.assertTrue(exp2fok6)
  calc exp2d7 = exponentialBase2(0x1.ffc0000000000p+9)
  calc exp2dok7 = withinUlps(0x1.6a09e667f3bcdp+1023, exp2d7, 1)
  test.assertTrue(exp2dok7)
  calc exp2d8 = exponentialBase2(-0x1.0900000000000p+10)
  calc exp2dok8 = withinUlps(0x0.0000000004000p-1022, exp2d8, 1)
  test.assertTrue(exp2dok8)
  calc exp2d9 = exponentialBase2(0x1.b7cdfd9d7bdbbp-34)
  calc exp2dok9 = withinUlps(0x1.000000004c366p+0, exp2d9, 1)
  test.assertTrue(exp2dok9)
  calc exp2d10 = exponentialBase2(0x1.3333333333333p-2)
  calc exp2dok10 = withinUlps(0x1.3b2c47bff8329p+0, exp2d10, 1)
  test.assertTrue(exp2dok10)
  calc exp2d11 = exponentialBase2(-0x1.0c80000000000p+10)
  calc exp2dok11 = withinUlps(0x0.0000000000001p-1022, exp2d11, 1)
  test.assertTrue(exp2dok11)
  calc exp2d12 = exponentialBase2(0x1.8000000000000p+1)
  calc exp2dok12 = withinUlps(0x1.0000000000000p+3, exp2d12, 1)
  test.assertTrue(exp2dok12)
  calc exp2f12 = exponentialBase2Single(convert.float64ToFloat32(0x1.8000000000000p+1))
  calc exp2fok12 = closeSingle(0x1.0000000000000p+3, exp2f12)
  test.assertTrue(exp2fok12)
  calc expm1d0 = exponentialMinusOne(0x1.0000000000000p+0)
  calc expm1dok0 = withinUlps(0x1.b7e151628aed3p+0, expm1d0, 1)
  test.assertTrue(expm1dok0)
  calc expm1f0 = exponentialMinusOneSingle(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc expm1fok0 = closeSingle(0x1.b7e151628aed3p+0, expm1f0)
  test.assertTrue(expm1fok0)
  calc expm1d1 = exponentialMinusOne(-0x1.0000000000000p+0)
  calc expm1dok1 = withinUlps(-0x1.43a54e4e98864p-1, expm1d1, 1)
  test.assertTrue(expm1dok1)
  calc expm1f1 = exponentialMinusOneSingle(convert.float64ToFloat32(-0x1.0000000000000p+0))
  calc expm1fok1 = closeSingle(-0x1.43a54e4e98864p-1, expm1f1)
  test.assertTrue(expm1fok1)
  calc expm1d2 = exponentialMinusOne(0x1.0000000000000p-1)
  calc expm1dok2 = withinUlps(0x1.4c2531c3c0d38p-1, expm1d2, 1)
  test.assertTrue(expm1dok2)
  calc expm1f2 = exponentialMinusOneSingle(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc expm1fok2 = closeSingle(0x1.4c2531c3c0d38p-1, expm1f2)
  test.assertTrue(expm1fok2)
  calc expm1d3 = exponentialMinusOne(0x1.4000000000000p+3)
  calc expm1dok3 = withinUlps(0x1.5825dcf950560p+14, expm1d3, 1)
  test.assertTrue(expm1dok3)
  calc expm1f3 = exponentialMinusOneSingle(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc expm1fok3 = closeSingle(0x1.5825dcf950560p+14, expm1f3)
  test.assertTrue(expm1fok3)
  calc expm1d4 = exponentialMinusOne(-0x1.4000000000000p+3)
  calc expm1dok4 = withinUlps(-0x1.fffa0ca192a6ep-1, expm1d4, 1)
  test.assertTrue(expm1dok4)
  calc expm1f4 = exponentialMinusOneSingle(convert.float64ToFloat32(-0x1.4000000000000p+3))
  calc expm1fok4 = closeSingle(-0x1.fffa0ca192a6ep-1, expm1f4)
  test.assertTrue(expm1fok4)
  calc expm1d5 = exponentialMinusOne(0x1.b7cdfd9d7bdbbp-34)
  calc expm1dok5 = withinUlps(0x1.b7cdfd9dda4e3p-34, expm1d5, 1)
  test.assertTrue(expm1dok5)
  calc expm1d6 = exponentialMinusOne(-0x1.b7cdfd9d7bdbbp-34)
  calc expm1dok6 = withinUlps(-0x1.b7cdfd9d1d693p-34, expm1d6, 1)
  test.assertTrue(expm1dok6)
  calc expm1d7 = exponentialMinusOne(0x1.3333333333333p-2)
  calc expm1dok7 = withinUlps(0x1.6641632306a56p-2, expm1d7, 1)
  test.assertTrue(expm1dok7)
  calc expm1d8 = exponentialMinusOne(-0x1.3333333333333p-2)
  calc expm1dok8 = withinUlps(-0x1.0966f2c7907f6p-2, expm1d8, 1)
  test.assertTrue(expm1dok8)
  calc expm1d9 = exponentialMinusOne(0x1.5e00000000000p+9)
  calc expm1dok9 = withinUlps(0x1.d945df4f8ec8ep+1009, expm1d9, 1)
  test.assertTrue(expm1dok9)
  calc expm1d10 = exponentialMinusOne(-0x1.e000000000000p+4)
  calc expm1dok10 = withinUlps(-0x1.ffffffffffcb5p-1, expm1d10, 1)
  test.assertTrue(expm1dok10)
  calc expm1f10 = exponentialMinusOneSingle(convert.float64ToFloat32(-0x1.e000000000000p+4))
  calc expm1fok10 = closeSingle(-0x1.ffffffffffcb5p-1, expm1f10)
  test.assertTrue(expm1fok10)
  calc expm1d11 = exponentialMinusOne(0x1.0624dd2f1a9fcp-10)
  calc expm1dok11 = withinUlps(0x1.06466dfb8cf3ap-10, expm1d11, 1)
  test.assertTrue(expm1dok11)
  calc expm1d12 = exponentialMinusOne(0x1.62e42fefa39efp-2)
  calc expm1dok12 = withinUlps(0x1.a827999fcef32p-2, expm1d12, 1)
  test.assertTrue(expm1dok12)
  return

test logTest "log, log2, log10, log1p give the correctly rounded value within one last place at sample points, in double and float forms"
  verifies naturalLogarithm givesLog
  verifies naturalLogarithmSingle givesLog
  verifies logarithmBase2 givesLog2
  verifies logarithmBase2Single givesLog2
  verifies logarithmBase10 givesLog10
  verifies logarithmBase10Single givesLog10
  verifies logarithmOnePlus givesLog1p
  verifies logarithmOnePlusSingle givesLog1p
  effect use machine.memory
  uses memoryAccess
:begin
  calc logd0 = naturalLogarithm(0x1.000001ad7f29bp+0)
  calc logdok0 = withinUlps(0x1.ad7f2847b6492p-24, logd0, 1)
  test.assertTrue(logdok0)
  calc logd1 = naturalLogarithm(0x1.0000000000000p+1)
  calc logdok1 = withinUlps(0x1.62e42fefa39efp-1, logd1, 1)
  test.assertTrue(logdok1)
  calc logf1 = naturalLogarithmSingle(convert.float64ToFloat32(0x1.0000000000000p+1))
  calc logfok1 = closeSingle(0x1.62e42fefa39efp-1, logf1)
  test.assertTrue(logfok1)
  calc logd2 = naturalLogarithm(0x1.0000000000000p-1)
  calc logdok2 = withinUlps(-0x1.62e42fefa39efp-1, logd2, 1)
  test.assertTrue(logdok2)
  calc logf2 = naturalLogarithmSingle(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc logfok2 = closeSingle(-0x1.62e42fefa39efp-1, logf2)
  test.assertTrue(logfok2)
  calc logd3 = naturalLogarithm(0x1.4000000000000p+3)
  calc logdok3 = withinUlps(0x1.26bb1bbb55516p+1, logd3, 1)
  test.assertTrue(logdok3)
  calc logf3 = naturalLogarithmSingle(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc logfok3 = closeSingle(0x1.26bb1bbb55516p+1, logf3)
  test.assertTrue(logfok3)
  calc logd4 = naturalLogarithm(0x1.56e1fc2f8f359p-997)
  calc logdok4 = withinUlps(-0x1.5963447f87fb5p+9, logd4, 1)
  test.assertTrue(logdok4)
  calc logd5 = naturalLogarithm(0x0.0000000000001p-1022)
  calc logdok5 = withinUlps(-0x1.74385446d71c3p+9, logd5, 1)
  test.assertTrue(logdok5)
  calc logd6 = naturalLogarithm(0x1.fffffffffffffp+1023)
  calc logdok6 = withinUlps(0x1.62e42fefa39efp+9, logd6, 1)
  test.assertTrue(logdok6)
  calc logd7 = naturalLogarithm(0x1.fffffca501acbp-1)
  calc logdok7 = withinUlps(-0x1.ad7f2b1049b9fp-24, logd7, 1)
  test.assertTrue(logdok7)
  calc logd8 = naturalLogarithm(0x1.8000000000000p+1)
  calc logdok8 = withinUlps(0x1.193ea7aad030bp+0, logd8, 1)
  test.assertTrue(logdok8)
  calc logf8 = naturalLogarithmSingle(convert.float64ToFloat32(0x1.8000000000000p+1))
  calc logfok8 = closeSingle(0x1.193ea7aad030bp+0, logf8)
  test.assertTrue(logfok8)
  calc logd9 = naturalLogarithm(0x1.9000000000000p+6)
  calc logdok9 = withinUlps(0x1.26bb1bbb55516p+2, logd9, 1)
  test.assertTrue(logdok9)
  calc logf9 = naturalLogarithmSingle(convert.float64ToFloat32(0x1.9000000000000p+6))
  calc logfok9 = closeSingle(0x1.26bb1bbb55516p+2, logf9)
  test.assertTrue(logfok9)
  calc logd10 = naturalLogarithm(0x1.5bf0a8b145769p+1)
  calc logdok10 = withinUlps(0x1.0000000000000p+0, logd10, 1)
  test.assertTrue(logdok10)
  calc log2d0 = logarithmBase2(0x1.0000000000000p+3)
  calc log2dok0 = withinUlps(0x1.8000000000000p+1, log2d0, 1)
  test.assertTrue(log2dok0)
  calc log2f0 = logarithmBase2Single(convert.float64ToFloat32(0x1.0000000000000p+3))
  calc log2fok0 = closeSingle(0x1.8000000000000p+1, log2f0)
  test.assertTrue(log2fok0)
  calc log2d1 = logarithmBase2(0x1.000001ad7f29bp+0)
  calc log2dok1 = withinUlps(0x1.35d0fea5fccb7p-23, log2d1, 1)
  test.assertTrue(log2dok1)
  calc log2d2 = logarithmBase2(0x1.999999999999ap-4)
  calc log2dok2 = withinUlps(-0x1.a934f0979a371p+1, log2d2, 1)
  test.assertTrue(log2dok2)
  calc log2d3 = logarithmBase2(0x1.4000000000000p+3)
  calc log2dok3 = withinUlps(0x1.a934f0979a371p+1, log2d3, 1)
  test.assertTrue(log2dok3)
  calc log2f3 = logarithmBase2Single(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc log2fok3 = closeSingle(0x1.a934f0979a371p+1, log2f3)
  test.assertTrue(log2fok3)
  calc log2d4 = logarithmBase2(0x1.56e1fc2f8f359p-997)
  calc log2dok4 = withinUlps(-0x1.f24a09f1a8b89p+9, log2d4, 1)
  test.assertTrue(log2dok4)
  calc log2d5 = logarithmBase2(0x0.0000000000001p-1022)
  calc log2dok5 = withinUlps(-0x1.0c80000000000p+10, log2d5, 1)
  test.assertTrue(log2dok5)
  calc log2d6 = logarithmBase2(0x1.0000000000000p+10)
  calc log2dok6 = withinUlps(0x1.4000000000000p+3, log2d6, 1)
  test.assertTrue(log2dok6)
  calc log2f6 = logarithmBase2Single(convert.float64ToFloat32(0x1.0000000000000p+10))
  calc log2fok6 = closeSingle(0x1.4000000000000p+3, log2f6)
  test.assertTrue(log2fok6)
  calc log2d7 = logarithmBase2(0x1.8000000000000p+1)
  calc log2dok7 = withinUlps(0x1.95c01a39fbd68p+0, log2d7, 1)
  test.assertTrue(log2dok7)
  calc log2f7 = logarithmBase2Single(convert.float64ToFloat32(0x1.8000000000000p+1))
  calc log2fok7 = closeSingle(0x1.95c01a39fbd68p+0, log2f7)
  test.assertTrue(log2fok7)
  calc log2d8 = logarithmBase2(0x1.8000000000000p-1)
  calc log2dok8 = withinUlps(-0x1.a8ff971810a5ep-2, log2d8, 1)
  test.assertTrue(log2dok8)
  calc log2f8 = logarithmBase2Single(convert.float64ToFloat32(0x1.8000000000000p-1))
  calc log2fok8 = closeSingle(-0x1.a8ff971810a5ep-2, log2f8)
  test.assertTrue(log2fok8)
  calc log2d9 = logarithmBase2(0x1.fffffffffffffp+1023)
  calc log2dok9 = withinUlps(0x1.0000000000000p+10, log2d9, 1)
  test.assertTrue(log2dok9)
  calc log10d0 = logarithmBase10(0x1.f400000000000p+9)
  calc log10dok0 = withinUlps(0x1.8000000000000p+1, log10d0, 1)
  test.assertTrue(log10dok0)
  calc log10f0 = logarithmBase10Single(convert.float64ToFloat32(0x1.f400000000000p+9))
  calc log10fok0 = closeSingle(0x1.8000000000000p+1, log10f0)
  test.assertTrue(log10fok0)
  calc log10d1 = logarithmBase10(0x1.4f8b588e368f1p-17)
  calc log10dok1 = withinUlps(-0x1.4000000000000p+2, log10d1, 1)
  test.assertTrue(log10dok1)
  calc log10d2 = logarithmBase10(0x1.0000000000000p+1)
  calc log10dok2 = withinUlps(0x1.34413509f79ffp-2, log10d2, 1)
  test.assertTrue(log10dok2)
  calc log10f2 = logarithmBase10Single(convert.float64ToFloat32(0x1.0000000000000p+1))
  calc log10fok2 = closeSingle(0x1.34413509f79ffp-2, log10f2)
  test.assertTrue(log10fok2)
  calc log10d3 = logarithmBase10(0x1.0624dd2f1a9fcp-10)
  calc log10dok3 = withinUlps(-0x1.8000000000000p+1, log10d3, 1)
  test.assertTrue(log10dok3)
  calc log10d4 = logarithmBase10(0x1.000001ad7f29bp+0)
  calc log10dok4 = withinUlps(0x1.750e5ca0b1098p-25, log10d4, 1)
  test.assertTrue(log10dok4)
  calc log10d5 = logarithmBase10(0x0.0000000000001p-1022)
  calc log10dok5 = withinUlps(-0x1.434e6420f4374p+8, log10d5, 1)
  test.assertTrue(log10dok5)
  calc log10d6 = logarithmBase10(0x1.81cd6c8b43958p+13)
  calc log10dok6 = withinUlps(0x1.05db618083a9ep+2, log10d6, 1)
  test.assertTrue(log10dok6)
  calc log10d7 = logarithmBase10(0x1.0f0cf064dd592p+73)
  calc log10dok7 = withinUlps(0x1.6000000000000p+4, log10d7, 1)
  test.assertTrue(log10dok7)
  calc log1pd0 = logarithmOnePlus(0x1.b7cdfd9d7bdbbp-34)
  calc log1pdok0 = withinUlps(0x1.b7cdfd9d1d693p-34, log1pd0, 1)
  test.assertTrue(log1pdok0)
  calc log1pd1 = logarithmOnePlus(-0x1.b7cdfd9d7bdbbp-34)
  calc log1pdok1 = withinUlps(-0x1.b7cdfd9dda4e3p-34, log1pd1, 1)
  test.assertTrue(log1pdok1)
  calc log1pd2 = logarithmOnePlus(0x1.0000000000000p-1)
  calc log1pdok2 = withinUlps(0x1.9f323ecbf984cp-2, log1pd2, 1)
  test.assertTrue(log1pdok2)
  calc log1pf2 = logarithmOnePlusSingle(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc log1pfok2 = closeSingle(0x1.9f323ecbf984cp-2, log1pf2)
  test.assertTrue(log1pfok2)
  calc log1pd3 = logarithmOnePlus(-0x1.0000000000000p-1)
  calc log1pdok3 = withinUlps(-0x1.62e42fefa39efp-1, log1pd3, 1)
  test.assertTrue(log1pdok3)
  calc log1pf3 = logarithmOnePlusSingle(convert.float64ToFloat32(-0x1.0000000000000p-1))
  calc log1pfok3 = closeSingle(-0x1.62e42fefa39efp-1, log1pf3)
  test.assertTrue(log1pfok3)
  calc log1pd4 = logarithmOnePlus(0x1.0000000000000p+0)
  calc log1pdok4 = withinUlps(0x1.62e42fefa39efp-1, log1pd4, 1)
  test.assertTrue(log1pdok4)
  calc log1pf4 = logarithmOnePlusSingle(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc log1pfok4 = closeSingle(0x1.62e42fefa39efp-1, log1pf4)
  test.assertTrue(log1pfok4)
  calc log1pd5 = logarithmOnePlus(0x1.2a05f20000000p+33)
  calc log1pdok5 = withinUlps(0x1.7069e2aa3184ep+4, log1pd5, 1)
  test.assertTrue(log1pdok5)
  calc log1pf5 = logarithmOnePlusSingle(convert.float64ToFloat32(0x1.2a05f20000000p+33))
  calc log1pfok5 = closeSingle(0x1.7069e2aa3184ep+4, log1pf5)
  test.assertTrue(log1pfok5)
  calc log1pd6 = logarithmOnePlus(-0x1.fffffca501acbp-1)
  calc log1pdok6 = withinUlps(-0x1.01e3b8440ed2fp+4, log1pd6, 1)
  test.assertTrue(log1pdok6)
  calc log1pd7 = logarithmOnePlus(0x1.56e1fc2f8f359p-997)
  calc log1pdok7 = withinUlps(0x1.56e1fc2f8f359p-997, log1pd7, 1)
  test.assertTrue(log1pdok7)
  calc log1pd8 = logarithmOnePlus(0x1.8000000000000p+1)
  calc log1pdok8 = withinUlps(0x1.62e42fefa39efp+0, log1pd8, 1)
  test.assertTrue(log1pdok8)
  calc log1pf8 = logarithmOnePlusSingle(convert.float64ToFloat32(0x1.8000000000000p+1))
  calc log1pfok8 = closeSingle(0x1.62e42fefa39efp+0, log1pf8)
  test.assertTrue(log1pfok8)
  calc log1pd9 = logarithmOnePlus(-0x1.fae147ae147aep-1)
  calc log1pdok9 = withinUlps(-0x1.26bb1bbb55515p+2, log1pd9, 1)
  test.assertTrue(log1pdok9)
  return

test powTest "pow give the correctly rounded value within one last place at sample points, in double and float forms"
  verifies power givesPow
  verifies powerSingle givesPow
  effect use machine.memory
  uses memoryAccess
:begin
  calc powd0 = power(0x1.0000000000000p+1, 0x1.4000000000000p+3)
  calc powdok0 = withinUlps(0x1.0000000000000p+10, powd0, 1)
  test.assertTrue(powdok0)
  calc powf0 = powerSingle(convert.float64ToFloat32(0x1.0000000000000p+1), convert.float64ToFloat32(0x1.4000000000000p+3))
  calc powfok0 = closeSingle(0x1.0000000000000p+10, powf0)
  test.assertTrue(powfok0)
  calc powd1 = power(0x1.0000000000000p+1, 0x1.0000000000000p-1)
  calc powdok1 = withinUlps(0x1.6a09e667f3bcdp+0, powd1, 1)
  test.assertTrue(powdok1)
  calc powf1 = powerSingle(convert.float64ToFloat32(0x1.0000000000000p+1), convert.float64ToFloat32(0x1.0000000000000p-1))
  calc powfok1 = closeSingle(0x1.6a09e667f3bcdp+0, powf1)
  test.assertTrue(powfok1)
  calc powd2 = power(0x1.4000000000000p+3, -0x1.8000000000000p+1)
  calc powdok2 = withinUlps(0x1.0624dd2f1a9fcp-10, powd2, 1)
  test.assertTrue(powdok2)
  calc powf2 = powerSingle(convert.float64ToFloat32(0x1.4000000000000p+3), convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc powfok2 = closeSingle(0x1.0624dd2f1a9fcp-10, powf2)
  test.assertTrue(powfok2)
  calc powd3 = power(-0x1.0000000000000p+1, 0x1.8000000000000p+1)
  calc powdok3 = withinUlps(-0x1.0000000000000p+3, powd3, 1)
  test.assertTrue(powdok3)
  calc powf3 = powerSingle(convert.float64ToFloat32(-0x1.0000000000000p+1), convert.float64ToFloat32(0x1.8000000000000p+1))
  calc powfok3 = closeSingle(-0x1.0000000000000p+3, powf3)
  test.assertTrue(powfok3)
  calc powd4 = power(-0x1.0000000000000p+1, 0x1.0000000000000p+2)
  calc powdok4 = withinUlps(0x1.0000000000000p+4, powd4, 1)
  test.assertTrue(powdok4)
  calc powf4 = powerSingle(convert.float64ToFloat32(-0x1.0000000000000p+1), convert.float64ToFloat32(0x1.0000000000000p+2))
  calc powfok4 = closeSingle(0x1.0000000000000p+4, powf4)
  test.assertTrue(powfok4)
  calc powd5 = power(0x1.000001ad7f29bp+0, 0x1.312d000000000p+23)
  calc powdok5 = withinUlps(0x1.5bf0a790ce6f2p+1, powd5, 1)
  test.assertTrue(powdok5)
  calc powd6 = power(0x1.0000000000000p-1, 0x1.0c80000000000p+10)
  calc powdok6 = withinUlps(0x0.0000000000001p-1022, powd6, 1)
  test.assertTrue(powdok6)
  calc powd7 = power(0x1.8000000000000p+0, 0x1.9000000000000p+6)
  calc powdok7 = withinUlps(0x1.69194f299cddap+58, powd7, 1)
  test.assertTrue(powdok7)
  calc powf7 = powerSingle(convert.float64ToFloat32(0x1.8000000000000p+0), convert.float64ToFloat32(0x1.9000000000000p+6))
  calc powfok7 = closeSingle(0x1.69194f299cddap+58, powf7)
  test.assertTrue(powfok7)
  calc powd8 = power(0x1.4000000000000p+3, 0x1.3400000000000p+8)
  calc powdok8 = withinUlps(0x1.1ccf385ebc8a0p+1023, powd8, 1)
  test.assertTrue(powdok8)
  calc powd9 = power(0x1.0000000000000p+1, -0x1.0c80000000000p+10)
  calc powdok9 = withinUlps(0x0.0000000000001p-1022, powd9, 1)
  test.assertTrue(powdok9)
  calc powd10 = power(0x1.8000000000000p+1, 0x1.5555555555555p-2)
  calc powdok10 = withinUlps(0x1.7137449123ef6p+0, powd10, 1)
  test.assertTrue(powdok10)
  calc powd11 = power(0x1.c000000000000p+2, 0x1.0000000000000p+1)
  calc powdok11 = withinUlps(0x1.8800000000000p+5, powd11, 1)
  test.assertTrue(powdok11)
  calc powf11 = powerSingle(convert.float64ToFloat32(0x1.c000000000000p+2), convert.float64ToFloat32(0x1.0000000000000p+1))
  calc powfok11 = closeSingle(0x1.8800000000000p+5, powf11)
  test.assertTrue(powfok11)
  calc powd12 = power(0x1.9000000000000p+6, 0x1.0000000000000p-1)
  calc powdok12 = withinUlps(0x1.4000000000000p+3, powd12, 1)
  test.assertTrue(powdok12)
  calc powf12 = powerSingle(convert.float64ToFloat32(0x1.9000000000000p+6), convert.float64ToFloat32(0x1.0000000000000p-1))
  calc powfok12 = closeSingle(0x1.4000000000000p+3, powf12)
  test.assertTrue(powfok12)
  calc powd13 = power(0x1.999999999999ap-4, 0x1.4000000000000p+4)
  calc powdok13 = withinUlps(0x1.79ca10c92422bp-67, powd13, 1)
  test.assertTrue(powdok13)
  return

test rootTest "cbrt, hypot give the correctly rounded value within one last place at sample points, in double and float forms"
  verifies cubeRoot givesCbrt
  verifies cubeRootSingle givesCbrt
  verifies hypotenuse givesHypot
  verifies hypotenuseSingle givesHypot
  effect use machine.memory
  uses memoryAccess
:begin
  calc cbrtd0 = cubeRoot(0x1.b000000000000p+4)
  calc cbrtdok0 = withinUlps(0x1.8000000000000p+1, cbrtd0, 1)
  test.assertTrue(cbrtdok0)
  calc cbrtf0 = cubeRootSingle(convert.float64ToFloat32(0x1.b000000000000p+4))
  calc cbrtfok0 = closeSingle(0x1.8000000000000p+1, cbrtf0)
  test.assertTrue(cbrtfok0)
  calc cbrtd1 = cubeRoot(-0x1.b000000000000p+4)
  calc cbrtdok1 = withinUlps(-0x1.8000000000000p+1, cbrtd1, 1)
  test.assertTrue(cbrtdok1)
  calc cbrtf1 = cubeRootSingle(convert.float64ToFloat32(-0x1.b000000000000p+4))
  calc cbrtfok1 = closeSingle(-0x1.8000000000000p+1, cbrtf1)
  test.assertTrue(cbrtfok1)
  calc cbrtd2 = cubeRoot(0x1.0000000000000p+1)
  calc cbrtdok2 = withinUlps(0x1.428a2f98d728bp+0, cbrtd2, 1)
  test.assertTrue(cbrtdok2)
  calc cbrtf2 = cubeRootSingle(convert.float64ToFloat32(0x1.0000000000000p+1))
  calc cbrtfok2 = closeSingle(0x1.428a2f98d728bp+0, cbrtf2)
  test.assertTrue(cbrtfok2)
  calc cbrtd3 = cubeRoot(0x1.0624dd2f1a9fcp-10)
  calc cbrtdok3 = withinUlps(0x1.999999999999ap-4, cbrtd3, 1)
  test.assertTrue(cbrtdok3)
  calc cbrtd4 = cubeRoot(0x1.7e43c8800759cp+996)
  calc cbrtdok4 = withinUlps(0x1.249ad2594c37dp+332, cbrtd4, 1)
  test.assertTrue(cbrtdok4)
  calc cbrtd5 = cubeRoot(0x0.0000000000001p-1022)
  calc cbrtdok5 = withinUlps(0x1.0000000000000p-358, cbrtd5, 1)
  test.assertTrue(cbrtdok5)
  calc cbrtd6 = cubeRoot(-0x1.0000000000000p+3)
  calc cbrtdok6 = withinUlps(-0x1.0000000000000p+1, cbrtd6, 1)
  test.assertTrue(cbrtdok6)
  calc cbrtf6 = cubeRootSingle(convert.float64ToFloat32(-0x1.0000000000000p+3))
  calc cbrtfok6 = closeSingle(-0x1.0000000000000p+1, cbrtf6)
  test.assertTrue(cbrtfok6)
  calc cbrtd7 = cubeRoot(0x1.fffffffffffffp+1023)
  calc cbrtdok7 = withinUlps(0x1.428a2f98d728bp+341, cbrtd7, 1)
  test.assertTrue(cbrtdok7)
  calc cbrtd8 = cubeRoot(0x1.4000000000000p+3)
  calc cbrtdok8 = withinUlps(0x1.13c484138704fp+1, cbrtd8, 1)
  test.assertTrue(cbrtdok8)
  calc cbrtf8 = cubeRootSingle(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc cbrtfok8 = closeSingle(0x1.13c484138704fp+1, cbrtf8)
  test.assertTrue(cbrtfok8)
  calc cbrtd9 = cubeRoot(0x1.0000000000000p-3)
  calc cbrtdok9 = withinUlps(0x1.0000000000000p-1, cbrtd9, 1)
  test.assertTrue(cbrtdok9)
  calc cbrtf9 = cubeRootSingle(convert.float64ToFloat32(0x1.0000000000000p-3))
  calc cbrtfok9 = closeSingle(0x1.0000000000000p-1, cbrtf9)
  test.assertTrue(cbrtfok9)
  calc hypotd0 = hypotenuse(0x1.8000000000000p+1, 0x1.0000000000000p+2)
  calc hypotdok0 = withinUlps(0x1.4000000000000p+2, hypotd0, 1)
  test.assertTrue(hypotdok0)
  calc hypotf0 = hypotenuseSingle(convert.float64ToFloat32(0x1.8000000000000p+1), convert.float64ToFloat32(0x1.0000000000000p+2))
  calc hypotfok0 = closeSingle(0x1.4000000000000p+2, hypotf0)
  test.assertTrue(hypotfok0)
  calc hypotd1 = hypotenuse(0x1.7e43c8800759cp+996, 0x1.7e43c8800759cp+996)
  calc hypotdok1 = withinUlps(0x1.0e4d50f99b211p+997, hypotd1, 1)
  test.assertTrue(hypotdok1)
  calc hypotd2 = hypotenuse(0x1.56e1fc2f8f359p-997, 0x1.56e1fc2f8f359p-997)
  calc hypotdok2 = withinUlps(0x1.e4e8d12762225p-997, hypotd2, 1)
  test.assertTrue(hypotdok2)
  calc hypotd3 = hypotenuse(0x0.0000000000001p-1022, 0x0.0000000000001p-1022)
  calc hypotdok3 = withinUlps(0x0.0000000000001p-1022, hypotd3, 1)
  test.assertTrue(hypotdok3)
  calc hypotd4 = hypotenuse(0x1.0000000000000p+0, 0x1.79ca10c924223p-67)
  calc hypotdok4 = withinUlps(0x1.0000000000000p+0, hypotd4, 1)
  test.assertTrue(hypotdok4)
  calc hypotd5 = hypotenuse(0x1.999999999999ap-4, 0x1.999999999999ap-3)
  calc hypotdok5 = withinUlps(0x1.c9f25c5bfeddap-3, hypotd5, 1)
  test.assertTrue(hypotdok5)
  calc hypotd6 = hypotenuse(-0x1.4000000000000p+2, 0x1.8000000000000p+3)
  calc hypotdok6 = withinUlps(0x1.a000000000000p+3, hypotd6, 1)
  test.assertTrue(hypotdok6)
  calc hypotf6 = hypotenuseSingle(convert.float64ToFloat32(-0x1.4000000000000p+2), convert.float64ToFloat32(0x1.8000000000000p+3))
  calc hypotfok6 = closeSingle(0x1.a000000000000p+3, hypotf6)
  test.assertTrue(hypotfok6)
  calc hypotd7 = hypotenuse(0x1.c7b1f3cac7433p+1019, 0x1.c7b1f3cac7433p+1019)
  calc hypotdok7 = withinUlps(0x1.4239a1109db2ap+1020, hypotd7, 1)
  test.assertTrue(hypotdok7)
  return

test specialTest "Infinities, zeros, NaNs, overflow and underflow, and the whole-number cases of pow, as C99 Annex F gives them"
  verifies power givesPow
  effect use machine.memory
  uses memoryAccess
:begin
  calc inf = convert.uint64BitsToFloat64(9218868437227405312)
  calc ninf = convert.uint64BitsToFloat64(18442240474082181120)
  calc nan = convert.uint64BitsToFloat64(9221120237041090560)
  calc sp1 = exponential(inf) == inf
  test.assertTrue(sp1)
  calc sp2 = exponential(ninf) == 0.0
  test.assertTrue(sp2)
  calc sp3 = exponential(800.0) == inf
  test.assertTrue(sp3)
  calc sp4 = exponential(-800.0) == 0.0
  test.assertTrue(sp4)
  calc sp5 = !(exponential(nan) == exponential(nan))
  test.assertTrue(sp5)
  calc sp6 = exponentialMinusOne(ninf) == -1.0
  test.assertTrue(sp6)
  calc sp7 = exponentialMinusOne(-0.0) == 0.0
  test.assertTrue(sp7)
  calc sp8 = exponentialBase2(1024.0) == inf
  test.assertTrue(sp8)
  calc sp9 = exponentialBase2(-1075.0) == 0.0
  test.assertTrue(sp9)
  calc sp10 = exponentialBase2(-1074.0) == 5e-324
  test.assertTrue(sp10)
  calc sp11 = naturalLogarithm(0.0) == ninf
  test.assertTrue(sp11)
  calc sp12 = !(naturalLogarithm(-1.0) == naturalLogarithm(-1.0))
  test.assertTrue(sp12)
  calc sp13 = naturalLogarithm(inf) == inf
  test.assertTrue(sp13)
  calc sp14 = naturalLogarithm(1.0) == 0.0
  test.assertTrue(sp14)
  calc sp15 = logarithmOnePlus(-1.0) == ninf
  test.assertTrue(sp15)
  calc sp16 = logarithmBase2(8.0) == 3.0
  test.assertTrue(sp16)
  calc sp17 = logarithmBase10(1000.0) == 3.0
  test.assertTrue(sp17)
  calc sp18 = power(5.0, 0.0) == 1.0
  test.assertTrue(sp18)
  calc sp19 = power(nan, 0.0) == 1.0
  test.assertTrue(sp19)
  calc sp20 = power(1.0, nan) == 1.0
  test.assertTrue(sp20)
  calc sp21 = !(power(nan, 2.0) == power(nan, 2.0))
  test.assertTrue(sp21)
  calc sp22 = power(0.0, -1.0) == inf
  test.assertTrue(sp22)
  calc sp23 = power(-0.0, -3.0) == ninf
  test.assertTrue(sp23)
  calc sp24 = power(0.0, 3.0) == 0.0
  test.assertTrue(sp24)
  calc sp25 = power(-1.0, inf) == 1.0
  test.assertTrue(sp25)
  calc sp26 = power(0.5, inf) == 0.0
  test.assertTrue(sp26)
  calc sp27 = power(2.0, ninf) == 0.0
  test.assertTrue(sp27)
  calc sp28 = power(2.0, inf) == inf
  test.assertTrue(sp28)
  calc sp29 = power(ninf, 3.0) == ninf
  test.assertTrue(sp29)
  calc sp30 = power(ninf, -3.0) == 0.0
  test.assertTrue(sp30)
  calc sp31 = power(ninf, 2.0) == inf
  test.assertTrue(sp31)
  calc sp32 = !(power(-2.0, 0.5) == power(-2.0, 0.5))
  test.assertTrue(sp32)
  calc sp33 = power(10.0, 2.0) == 100.0
  test.assertTrue(sp33)
  calc sp34 = power(2.0, 1024.0) == inf
  test.assertTrue(sp34)
  calc sp35 = power(-2.0, 1025.0) == ninf
  test.assertTrue(sp35)
  calc sp36 = power(2.0, -1080.0) == 0.0
  test.assertTrue(sp36)
  calc sp37 = cubeRoot(27.0) == 3.0
  test.assertTrue(sp37)
  calc sp38 = cubeRoot(-8.0) == -2.0
  test.assertTrue(sp38)
  calc sp39 = cubeRoot(inf) == inf
  test.assertTrue(sp39)
  calc sp40 = hypotenuse(3.0, 4.0) == 5.0
  test.assertTrue(sp40)
  calc sp41 = hypotenuse(nan, inf) == inf
  test.assertTrue(sp41)
  calc sp42 = hypotenuse(ninf, 1.0) == inf
  test.assertTrue(sp42)
  calc sp43 = hypotenuse(0.0, -0.0) == 0.0
  test.assertTrue(sp43)
  return
