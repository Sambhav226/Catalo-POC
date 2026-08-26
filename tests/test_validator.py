from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models import SchemaField
from src.agents.validator_agent import _validate


def test_int_coercion():
    f = SchemaField(name="hdmi_ports", dtype="int", min=1, max=6)
    ok, v, _ = _validate(f, "3")
    assert ok and v == 3


def test_float_coercion_with_unit_strip():
    f = SchemaField(name="screen_size_inches", dtype="float", min=10, max=120)
    ok, v, _ = _validate(f, "55 inches")
    assert ok and v == 55.0


def test_range_violation():
    f = SchemaField(name="screen_size_inches", dtype="float", min=10, max=120)
    ok, v, reason = _validate(f, "5")
    assert not ok
    assert "below_min" in reason


def test_enum_membership():
    f = SchemaField(name="resolution", dtype="enum", enum_values=["4K UHD", "8K UHD"])
    ok, v, _ = _validate(f, "4K UHD")
    assert ok
    ok, _, reason = _validate(f, "Full HD")
    assert not ok and reason == "enum_mismatch"


def test_bool_coercion():
    f = SchemaField(name="smart_tv", dtype="bool")
    for v in ["yes", "Yes", "true", "1"]:
        ok, coerced, _ = _validate(f, v)
        assert ok and coerced is True
    for v in ["no", "false", "0"]:
        ok, coerced, _ = _validate(f, v)
        assert ok and coerced is False
