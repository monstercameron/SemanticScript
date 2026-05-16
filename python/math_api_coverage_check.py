import math


# This file keeps the benchmark honest: every public math API in the local
# Python runtime should be represented in one of the grouped example scripts.
EXAMPLE_API_COVERAGE = {
    "acos",
    "acosh",
    "asin",
    "asinh",
    "atan",
    "atan2",
    "atanh",
    "ceil",
    "comb",
    "copysign",
    "cos",
    "cosh",
    "degrees",
    "dist",
    "e",
    "erf",
    "erfc",
    "exp",
    "expm1",
    "fabs",
    "factorial",
    "floor",
    "fmod",
    "frexp",
    "fsum",
    "gamma",
    "gcd",
    "hypot",
    "inf",
    "isclose",
    "isfinite",
    "isinf",
    "isnan",
    "isqrt",
    "lcm",
    "ldexp",
    "lgamma",
    "log",
    "log10",
    "log1p",
    "log2",
    "modf",
    "nan",
    "nextafter",
    "perm",
    "pi",
    "pow",
    "prod",
    "radians",
    "remainder",
    "sin",
    "sinh",
    "sqrt",
    "tan",
    "tanh",
    "tau",
    "trunc",
    "ulp",
}


def main():
    public_math_apis = {
        api_name
        for api_name in dir(math)
        if not api_name.startswith("_")
    }
    missing_from_examples = sorted(public_math_apis - EXAMPLE_API_COVERAGE)
    unavailable_in_runtime = sorted(EXAMPLE_API_COVERAGE - public_math_apis)

    print("Math API Coverage Check")
    print("=======================")
    print("runtimePublicApiCount={}".format(len(public_math_apis)))
    print("exampleCoveredApiCount={}".format(len(EXAMPLE_API_COVERAGE)))
    print("missingFromExamples={}".format(",".join(missing_from_examples) or "none"))
    print("unavailableInRuntime={}".format(",".join(unavailable_in_runtime) or "none"))

    if missing_from_examples or unavailable_in_runtime:
        raise RuntimeError("math API coverage is incomplete for this runtime")


if __name__ == "__main__":
    main()
