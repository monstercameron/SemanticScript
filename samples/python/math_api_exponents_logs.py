import math


# Exponential, logarithmic, power, and root APIs.
def main():
    exp_one = math.exp(1.0)
    expm1_small = math.expm1(0.001)
    natural_log = math.log(math.e)
    base_three_log = math.log(81.0, 3.0)
    log_ten = math.log10(100000.0)
    log_one_plus_small = math.log1p(0.001)
    log_two = math.log2(1024.0)
    power_value = math.pow(9.0, 0.5)
    square_root = math.sqrt(144.0)

    print("Math API Exponents Logs")
    print("=======================")
    print("e={:.12f}".format(math.e))
    print("exp(1.0)={:.12f}".format(exp_one))
    print("expm1(0.001)={:.12f}".format(expm1_small))
    print("log(e)={:.12f}".format(natural_log))
    print("log(81.0, 3.0)={:.12f}".format(base_three_log))
    print("log10(100000.0)={:.12f}".format(log_ten))
    print("log1p(0.001)={:.12f}".format(log_one_plus_small))
    print("log2(1024.0)={:.12f}".format(log_two))
    print("pow(9.0, 0.5)={:.12f}".format(power_value))
    print("sqrt(144.0)={:.12f}".format(square_root))

    assert math.isclose(exp_one, math.e)
    assert math.isclose(expm1_small, math.exp(0.001) - 1.0)
    assert math.isclose(natural_log, 1.0)
    assert math.isclose(base_three_log, 4.0)
    assert math.isclose(log_ten, 5.0)
    assert math.isclose(log_one_plus_small, math.log(1.001))
    assert math.isclose(log_two, 10.0)
    assert math.isclose(power_value, 3.0)
    assert math.isclose(square_root, 12.0)


if __name__ == "__main__":
    main()
