"""Unit-conversion helpers and the CSV formula-injection guard."""

import math

import app


def test_scale_multiplies():
    double = app._scale(2.0)
    assert double(1.5) == 3.0


def test_scale_rounds_to_4dp():
    triple = app._scale(3.0)
    assert triple(1.23456) == 3.7037


def test_scale_negative():
    half = app._scale(0.5)
    assert half(-2.0) == -1.0


def test_passthrough_returns_raw():
    assert app._passthrough(52.123456789) == 52.123456789
    assert app._passthrough(-0.0) == -0.0


def test_identity_is_scale_one():
    assert app._IDENTITY(2.5) == 2.5


def test_mps_to_kts():
    # 1 m/s = 1.94384 kt
    assert app._scale(app._MPS_TO_KTS)(10.0) == 19.4384


def test_rad_to_deg():
    assert app._scale(app._RAD_TO_DEG)(math.pi) == 180.0


def test_rads_to_degmin():
    # pi rad/s = 180 deg/s = 10800 deg/min
    assert app._scale(app._RADS_TO_DEGMIN)(math.pi) == 10800.0


def test_m_to_ft():
    assert app._scale(app._M_TO_FT)(1.0) == 3.2808


def test_m_to_nm():
    # 1852 m = 1 nm exactly
    assert app._scale(app._M_TO_NM)(1852.0) == 1.0


# --- _csv_safe formula-injection guard ------------------------------------


def test_csv_safe_passes_plain_values():
    assert app._csv_safe("") == ""
    assert app._csv_safe("hello") == "hello"
    assert app._csv_safe("52.123") == "52.123"


def test_csv_safe_keeps_negative_numbers():
    # A leading '-' is legitimate for negative values — must not be escaped.
    assert app._csv_safe("-1.5") == "-1.5"


def test_csv_safe_neutralizes_formulas():
    assert app._csv_safe("=HYPERLINK(\"http://evil\")") == "'=HYPERLINK(\"http://evil\")"
    assert app._csv_safe("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert app._csv_safe("@SUM(A1:A9)") == "'@SUM(A1:A9)"
    assert app._csv_safe("\t=1+1") == "'\t=1+1"
    assert app._csv_safe("\r=1+1") == "'\r=1+1"
