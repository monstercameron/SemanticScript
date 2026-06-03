#!/usr/bin/env python3
"""X-209 (stdlib, decimal slice): exact money arithmetic via Decimal.

Decimal/Money is a scaled Int64 (scale 2: raw = amount * 100), so money adds and
subtracts EXACTLY with no binary-float rounding error (X-093, the accepted exact
form; float money is gate-rejected). These run the decimal examples through the
real `run` lane and assert each self-asserts green.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

# example -> the golden raw decimal value (amount * 100) it reaches
_DECIMAL = {
    "decimal_exact_money": "1575",        # 10.50 + 5.25 = 15.75
    "decimal_subtract_refund": "1050",    # 15.75 - 5.25 = 10.50
    "decimal_multiply_scaled": "1000",    # 2.50 * 4.00 = 10.00  (250*400/100)
    "decimal_divide_per_unit": "300",     # 12.00 / 4.00 = 3.00  (1200*100/400)
    "decimal_equal_compare": "1",         # 10.00 == 10.00 -> true
    "decimal_list_total": "3075",         # 10.50+5.25+12.00+3.00, folded over a list
}


@pytest.mark.parametrize("name,expected", sorted(_DECIMAL.items()))
def test_decimal_example_runs_green(name, expected):
    path = os.path.join(EXAMPLES, name + ".sem")
    assert os.path.isfile(path), path
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
    assert expected in proc.stdout
