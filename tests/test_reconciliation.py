from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.reconciliation_agent import _pick_winner
from src.models import FieldObservation


def _obs(value, source_type, ic=0.9, url="http://x") -> FieldObservation:
    return FieldObservation(
        field="x", value=value, source_url=url, source_type=source_type, intrinsic_confidence=ic,
    )


def test_manufacturer_beats_marketplace():
    obs = [
        _obs("55", "marketplace"),
        _obs("55.0", "manufacturer"),
    ]
    winner, conf = _pick_winner(obs)
    assert winner.source_type == "manufacturer"
    assert conf > 0.0


def test_confidence_scales_with_agreement():
    all_agree = [_obs("55", "manufacturer"), _obs("55", "manufacturer"), _obs("55", "marketplace")]
    disagree = [_obs("55", "manufacturer"), _obs("50", "marketplace"), _obs("60", "retailer")]

    w1, c1 = _pick_winner(all_agree)
    w2, c2 = _pick_winner(disagree)
    assert c1 > c2


def test_single_observation():
    obs = [_obs("55", "retailer")]
    winner, conf = _pick_winner(obs)
    assert winner.value == "55"
    assert 0.0 <= conf <= 1.0
