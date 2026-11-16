"""Generate 60 days of synthetic fraud alerts for a fictional UK retail bank.

Each alert is raised by one of eight transaction-monitoring rules and carries the
features an investigator would look at. Whether the alert is genuine fraud is drawn
from a known probability, and how long it takes to work is drawn from a realistic
distribution, so the before-and-after comparison has a known ground truth.
No real bank, customer or transaction data is used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config

rng = np.random.default_rng(config.SEED)

# rule -> (share of alerts, extra fraud log-odds for this rule)
RULE_MIX = {
    "R01": (0.18, 0.4), "R02": (0.16, 0.2), "R03": (0.10, 0.9), "R04": (0.07, 0.6),
    "R05": (0.08, 0.1), "R06": (0.22, -1.2), "R07": (0.07, 0.8), "R08": (0.12, 0.5),
}
CHANNELS = ["Mobile app", "Online banking", "Telephone banking", "Branch"]


def _features(n: int, rule: str) -> pd.DataFrame:
    amount = np.round(rng.lognormal(6.4, 1.0, n), 2)
    if rule in ("R01", "R03"):
        amount = np.round(amount * rng.uniform(2.5, 5, n), 2)
    if rule == "R06":
        amount = np.round(rng.choice([500, 1000, 1500, 2000, 2500, 5000], n) * 1.0, 2)
    df = pd.DataFrame({
        "rule_id": rule,
        "amount_gbp": amount,
        "new_payee": rng.random(n) < (0.85 if rule == "R01" else 0.35),
        "new_device": rng.random(n) < (0.9 if rule == "R03" else 0.12),
        "payments_last_24h": rng.poisson(9 if rule == "R02" else 2, n),
        "high_risk_country": rng.random(n) < (0.95 if rule == "R04" else 0.03),
        "dormant_days": np.where(rng.random(n) < (0.9 if rule == "R05" else 0.05), rng.integers(180, 900, n), 0),
        "failed_logins_24h": np.where(rng.random(n) < (0.9 if rule == "R07" else 0.08), rng.integers(2, 9, n), 0),
        "account_age_days": rng.integers(20, 6000, n),
        "inbound_then_out_mins": np.where(rng.random(n) < (0.9 if rule == "R08" else 0.04), rng.integers(2, 240, n), -1),
        "prior_alerts_90d": rng.poisson(0.6, n),
        "channel": rng.choice(CHANNELS, n, p=[0.55, 0.30, 0.10, 0.05]),
    })
    return df


def _fraud_probability(df: pd.DataFrame) -> np.ndarray:
    z = (
        -6.6
        + df.rule_id.map({k: v[1] for k, v in RULE_MIX.items()}).to_numpy()
        + 1.1 * df.new_payee
        + 1.5 * df.new_device
        + 0.18 * np.minimum(df.payments_last_24h, 12)
        + 0.55 * np.log1p(df.amount_gbp / 500)
        + 1.4 * df.high_risk_country
        + 0.9 * (df.failed_logins_24h >= 3)
        + 0.8 * (df.account_age_days < 120)
        + 0.9 * ((df.inbound_then_out_mins >= 0) & (df.inbound_then_out_mins < 60))
        + 0.5 * (df.dormant_days > 365)
        - 0.25 * np.minimum(df.prior_alerts_90d, 4)            # repeat false alarms on the same customer
        + 0.4 * (df.channel == "Telephone banking")
        + rng.normal(0, 0.6, len(df))                            # what the data cannot see
    )
    return 1 / (1 + np.exp(-z))


def generate() -> pd.DataFrame:
    start = pd.Timestamp(config.START_DATE)
    frames = []
    for d in range(config.DAYS):
        day = start + pd.Timedelta(days=d)
        n_day = int(rng.poisson(config.ALERTS_PER_DAY * (1.15 if day.weekday() == 0 else 0.8 if day.weekday() >= 5 else 1.0)))
        counts = rng.multinomial(n_day, [v[0] for v in RULE_MIX.values()])
        for rule, n in zip(RULE_MIX, counts):
            f = _features(int(n), rule)
            f["raised_at"] = day + pd.to_timedelta(rng.uniform(0, 24 * 3600, int(n)), unit="s")
            frames.append(f)
    df = pd.concat(frames, ignore_index=True).sort_values("raised_at").reset_index(drop=True)
    df.insert(0, "alert_id", [f"ALR-{i:06d}" for i in range(1, len(df) + 1)])
    df["customer_id"] = [f"CUS-{x:06d}" for x in rng.integers(1, 250_000, len(df))]
    p = _fraud_probability(df)
    df["is_fraud"] = rng.random(len(df)) < p
    # minutes an investigator needs: genuine fraud takes longer (customer contact, blocking, referral)
    df["handling_minutes"] = np.round(np.where(
        df.is_fraud, rng.lognormal(np.log(38), 0.35, len(df)), rng.lognormal(np.log(10.5), 0.45, len(df))), 1)
    df["period"] = np.where(df.raised_at < start + pd.Timedelta(days=config.TRAIN_DAYS), "train", "test")
    return df


def main() -> pd.DataFrame:
    config.DATA.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(config.DATA / "alerts.csv", index=False)
    print(f"{len(df):,} alerts, {df.is_fraud.mean():.2%} genuine fraud")
    return df


if __name__ == "__main__":
    main()
