import math


# Trigonometric angle conversion, circular functions, and hyperbolic functions.
def main():
    right_angle_radians = math.radians(90.0)
    straight_angle_degrees = math.degrees(math.pi)
    sine_value = math.sin(math.pi / 2.0)
    cosine_value = math.cos(math.tau)
    tangent_value = math.tan(math.pi / 4.0)
    arcsine_value = math.asin(1.0)
    arccosine_value = math.acos(0.0)
    arctangent_value = math.atan(1.0)
    arctangent_quadrant_value = math.atan2(1.0, -1.0)

    hyperbolic_sine = math.sinh(1.0)
    hyperbolic_cosine = math.cosh(1.0)
    hyperbolic_tangent = math.tanh(0.5)
    inverse_hyperbolic_sine = math.asinh(hyperbolic_sine)
    inverse_hyperbolic_cosine = math.acosh(hyperbolic_cosine)
    inverse_hyperbolic_tangent = math.atanh(hyperbolic_tangent)

    print("Math API Trig Hyperbolic")
    print("========================")
    print("pi={:.12f}".format(math.pi))
    print("tau={:.12f}".format(math.tau))
    print("radians(90.0)={:.12f}".format(right_angle_radians))
    print("degrees(pi)={:.12f}".format(straight_angle_degrees))
    print("sin(pi / 2)={:.12f}".format(sine_value))
    print("cos(tau)={:.12f}".format(cosine_value))
    print("tan(pi / 4)={:.12f}".format(tangent_value))
    print("asin(1.0)={:.12f}".format(arcsine_value))
    print("acos(0.0)={:.12f}".format(arccosine_value))
    print("atan(1.0)={:.12f}".format(arctangent_value))
    print("atan2(1.0, -1.0)={:.12f}".format(arctangent_quadrant_value))
    print("sinh(1.0)={:.12f}".format(hyperbolic_sine))
    print("cosh(1.0)={:.12f}".format(hyperbolic_cosine))
    print("tanh(0.5)={:.12f}".format(hyperbolic_tangent))
    print("asinh(sinh(1.0))={:.12f}".format(inverse_hyperbolic_sine))
    print("acosh(cosh(1.0))={:.12f}".format(inverse_hyperbolic_cosine))
    print("atanh(tanh(0.5))={:.12f}".format(inverse_hyperbolic_tangent))

    assert math.isclose(right_angle_radians, math.pi / 2.0)
    assert math.isclose(straight_angle_degrees, 180.0)
    assert math.isclose(sine_value, 1.0)
    assert math.isclose(cosine_value, 1.0)
    assert math.isclose(tangent_value, 1.0)
    assert math.isclose(arcsine_value, math.pi / 2.0)
    assert math.isclose(arccosine_value, math.pi / 2.0)
    assert math.isclose(arctangent_value, math.pi / 4.0)
    assert math.isclose(arctangent_quadrant_value, 3.0 * math.pi / 4.0)
    assert math.isclose(inverse_hyperbolic_sine, 1.0)
    assert math.isclose(inverse_hyperbolic_cosine, 1.0)
    assert math.isclose(inverse_hyperbolic_tangent, 0.5)


if __name__ == "__main__":
    main()
