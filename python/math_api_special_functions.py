import math


# Special functions often used for probability, statistics, and scientific code.
def main():
    error_function_value = math.erf(1.0)
    complementary_error_value = math.erfc(1.0)
    gamma_value = math.gamma(6.0)
    log_gamma_value = math.lgamma(6.0)

    print("Math API Special Functions")
    print("==========================")
    print("erf(1.0)={:.12f}".format(error_function_value))
    print("erfc(1.0)={:.12f}".format(complementary_error_value))
    print("erf(1.0) + erfc(1.0)={:.12f}".format(error_function_value + complementary_error_value))
    print("gamma(6.0)={:.12f}".format(gamma_value))
    print("lgamma(6.0)={:.12f}".format(log_gamma_value))

    assert math.isclose(error_function_value + complementary_error_value, 1.0)
    assert math.isclose(gamma_value, 120.0)
    assert math.isclose(log_gamma_value, math.log(120.0))


if __name__ == "__main__":
    main()
