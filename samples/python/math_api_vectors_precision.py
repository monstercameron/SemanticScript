import math


# Vector distance helpers and precision-preserving summation.
def main():
    precise_decimal_sum = math.fsum([0.1] * 10)
    naive_decimal_sum = sum([0.1] * 10)

    point_a = (1.0, 2.0, 3.0)
    point_b = (4.0, 6.0, 15.0)
    euclidean_distance = math.dist(point_a, point_b)
    hypotenuse_value = math.hypot(3.0, 4.0, 12.0)

    print("Math API Vectors Precision")
    print("==========================")
    print("sum([0.1] * 10)={:.17f}".format(naive_decimal_sum))
    print("fsum([0.1] * 10)={:.17f}".format(precise_decimal_sum))
    print("dist((1,2,3), (4,6,15))={:.12f}".format(euclidean_distance))
    print("hypot(3,4,12)={:.12f}".format(hypotenuse_value))

    assert precise_decimal_sum == 1.0
    assert naive_decimal_sum != precise_decimal_sum
    assert math.isclose(euclidean_distance, 13.0)
    assert math.isclose(hypotenuse_value, 13.0)


if __name__ == "__main__":
    main()
