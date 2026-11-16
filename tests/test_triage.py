"""Tests for the scoring, triage policy, queue simulation and benefits figures."""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402
import generate_data  # noqa: E402
import pipeline  # noqa: E402
import queue_sim  # noqa: E402
import triage  # noqa: E402


@pytest.fixture(scope="module")
def alerts():
    return generate_data.generate()


@pytest.fixture(scope="module")
def scored(alerts):
    return triage.score(alerts)


def test_thresholds_use_training_period_only(alerts, scored):
    _, info = scored
    tampered = alerts.copy()
    tampered.loc[tampered.period == "test", "is_fraud"] = ~tampered.loc[tampered.period == "test", "is_fraud"]
    _, info2 = triage.score(tampered)
    assert info["auto_close_below"] == info2["auto_close_below"]
    assert info["priority_from"] == info2["priority_from"]


def test_auto_close_band_respects_fraud_limit_on_training(scored):
    s, _ = scored
    tr = s[s.period == "train"]
    share = tr.loc[tr.triage_band == "Auto-close", "is_fraud"].sum() / tr.is_fraud.sum()
    assert share <= config.MAX_FRAUD_IN_AUTO_CLOSE + 1e-9


def test_priority_band_is_about_five_percent(scored):
    s, _ = scored
    share = (s[s.period == "train"].triage_band == "Priority").mean()
    assert abs(share - config.PRIORITY_SHARE) < 0.005


def test_model_beats_chance(scored):
    assert scored[1]["auc_test"] > 0.7


def test_capacity_calendar_matches_team_size():
    cap = queue_sim.capacity_calendar(pd.Timestamp("2026-07-06"), 7)  # Monday
    daily = config.INVESTIGATORS * config.PRODUCTIVE_HOURS_PER_DAY * 60
    assert cap[:24].sum() == pytest.approx(daily)
    assert cap[5 * 24:6 * 24].sum() == pytest.approx(0.4 * daily)        # Saturday
    assert cap[:8].sum() == 0                                               # nobody on shift before 08:00


def test_every_alert_gets_a_decision_after_it_is_raised(scored):
    s, _ = scored
    for policy in ("baseline", "optimised"):
        d = queue_sim.simulate(s, policy)
        assert d.notna().all()
        assert (d >= s.raised_at).all()


def test_baseline_is_first_in_first_out(scored):
    s, _ = scored
    d = queue_sim.simulate(s, "baseline")
    order = s.assign(d=d).sort_values("raised_at").d
    assert order.is_monotonic_increasing


def test_days_1_to_30_are_identical_in_both_scenarios(scored):
    s, _ = scored
    b, o = queue_sim.simulate(s, "baseline"), queue_sim.simulate(s, "optimised")
    early = s.raised_at < pd.Timestamp(config.START_DATE) + pd.Timedelta(days=config.TRAIN_DAYS - 2)
    assert (b[early] == o[early]).all()


def test_benefits_direction_and_fraud_kept(alerts, tmp_path):
    con, _ = pipeline.run(alerts, tmp_path / "t.duckdb")
    b = con.sql("SELECT * FROM benefits").df().set_index("measure")
    assert b.loc["Investigator hours", "optimised"] < b.loc["Investigator hours", "baseline"]
    assert b.loc["Alerts decided within 24 hours", "optimised"] >= b.loc["Alerts decided within 24 hours", "baseline"]
    kept = b.loc["Genuine fraud reviewed by a person"]
    assert kept.optimised / kept.baseline >= 0.97
