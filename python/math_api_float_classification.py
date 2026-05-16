import math


# Floating-point classification, decomposition, and IEEE-adjacent helpers.
def main():
    fractional_part, integer_part = math.modf(-3.75)
    mantissa, exponent = math.frexp(96.0)
    rebuilt_value = math.ldexp(mantissa, exponent)

    next_after_one = math.nextafter(1.0, 2.0)
    one_unit_in_last_place = math.ulp(1.0)

    print("Math API Float Classification")
    print("=============================")
    print("fabs(-15.75)={}".format(math.fabs(-15.75)))
    print("fmod(7.5, 2.0)={}".format(math.fmod(7.5, 2.0)))
    print("remainder(7.5, 2.0)={}".format(math.remainder(7.5, 2.0)))
    print("modf(-3.75)=fractional:{} integer:{}".format(fractional_part, integer_part))
    print("copysign(12.0, -0.0)={}".format(math.copysign(12.0, -0.0)))
    print("frexp(96.0)=mantissa:{} exponent:{}".format(mantissa, exponent))
    print("ldexp(mantissa, exponent)={}".format(rebuilt_value))
    print("isclose(0.1 + 0.2, 0.3)={}".format(math.isclose(0.1 + 0.2, 0.3)))
    print("isfinite(42.0)={}".format(math.isfinite(42.0)))
    print("isinf(inf)={}".format(math.isinf(math.inf)))
    print("isnan(nan)={}".format(math.isnan(math.nan)))
    print("nextafter(1.0, 2.0)={}".format(next_after_one))
    print("ulp(1.0)={}".format(one_unit_in_last_place))

    assert math.fabs(-15.75) == 15.75
    assert math.fmod(7.5, 2.0) == 1.5
    assert math.remainder(7.5, 2.0) == -0.5
    assert fractional_part == -0.75
    assert integer_part == -3.0
    assert math.copysign(12.0, -0.0) == -12.0
    assert mantissa == 0.75
    assert exponent == 7
    assert rebuilt_value == 96.0
    assert math.isclose(0.1 + 0.2, 0.3)
    assert math.isfinite(42.0)
    assert math.isinf(math.inf)
    assert math.isnan(math.nan)
    assert next_after_one > 1.0
    assert one_unit_in_last_place > 0.0


if __name__ == "__main__":
    main()
