import math


# Integer, rounding, and combinatorics APIs from the math module.
def main():
    rounded_positive = {
        "ceil": math.ceil(3.2),
        "floor": math.floor(3.8),
        "trunc": math.trunc(3.8),
    }
    rounded_negative = {
        "ceil": math.ceil(-3.8),
        "floor": math.floor(-3.2),
        "trunc": math.trunc(-3.8),
    }

    factorial_value = math.factorial(6)
    combination_count = math.comb(8, 3)
    permutation_count = math.perm(8, 3)
    greatest_common_divisor = math.gcd(84, 126, 210)
    least_common_multiple = math.lcm(6, 10, 15)
    square_root_floor = math.isqrt(999)
    product_value = math.prod([2, 3, 5, 7])

    print("Math API Integer Combinatorics")
    print("==============================")
    print("roundedPositive={}".format(rounded_positive))
    print("roundedNegative={}".format(rounded_negative))
    print("factorial6={}".format(factorial_value))
    print("comb8Choose3={}".format(combination_count))
    print("perm8Take3={}".format(permutation_count))
    print("gcd84_126_210={}".format(greatest_common_divisor))
    print("lcm6_10_15={}".format(least_common_multiple))
    print("isqrt999={}".format(square_root_floor))
    print("prod2_3_5_7={}".format(product_value))

    assert rounded_positive == {"ceil": 4, "floor": 3, "trunc": 3}
    assert rounded_negative == {"ceil": -3, "floor": -4, "trunc": -3}
    assert factorial_value == 720
    assert combination_count == 56
    assert permutation_count == 336
    assert greatest_common_divisor == 42
    assert least_common_multiple == 30
    assert square_root_floor == 31
    assert product_value == 210


if __name__ == "__main__":
    main()
