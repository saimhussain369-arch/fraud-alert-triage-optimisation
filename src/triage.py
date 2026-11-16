"""Risk score and triage bands.

A logistic regression is trained on days 1-30 only. The auto-close and priority
thresholds are also chosen on days 1-30, then applied unchanged to days 31-60,
so the results on the test period are an honest estimate of what would happen
if the policy were switched on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

import config

FEATURES = {
    "log_amount": lambda d: np.log1p(d.amount_gbp),
    "new_payee": lambda d: d.new_payee.astype(int),
    "new_device": lambda d: d.new_device.astype(int),
    "payments_last_24h": lambda d: np.minimum(d.payments_last_24h, 15),
    "high_risk_country": lambda d: d.high_risk_country.astype(int),
    "failed_logins_3plus": lambda d: (d.failed_logins_24h >= 3).astype(int),
    "new_account": lambda d: (d.account_age_days < 120).astype(int),
    "quick_in_out": lambda d: ((d.inbound_then_out_mins >= 0) & (d.inbound_then_out_mins < 60)).astype(int),
    "dormant_over_1y": lambda d: (d.dormant_days > 365).astype(int),
    "prior_alerts_90d": lambda d: np.minimum(d.prior_alerts_90d, 5),
    "telephone_channel": lambda d: (d.channel == "Telephone banking").astype(int),
}
# Plain-English reasons shown to investigators in the workbench
REASONS = {
    "log_amount": "High payment value", "new_payee": "New payee", "new_device": "New device",
    "payments_last_24h": "Many payments in 24 hours", "high_risk_country": "High-risk country",
    "failed_logins_3plus": "Failed logins before payment", "new_account": "Account under 4 months old",
    "quick_in_out": "Money in and out within an hour", "dormant_over_1y": "Dormant over a year",
    "prior_alerts_90d": "Previous alerts on customer", "telephone_channel": "Telephone banking",
}


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({k: f(df) for k, f in FEATURES.items()})
    return pd.concat([X, pd.get_dummies(df.rule_id, prefix="rule", dtype=int)], axis=1)


def score(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    X = feature_matrix(df)
    train = df.period == "train"
    scaler = StandardScaler().fit(X[train])
    model = LogisticRegression(max_iter=2000, C=1.0).fit(scaler.transform(X[train]), df.is_fraud[train])
    out = df.copy()
    out["risk_score"] = np.round(model.predict_proba(scaler.transform(X))[:, 1], 5)

    # top three reasons per alert: largest positive contributions to the score
    contrib = scaler.transform(X) * model.coef_[0]
    names = list(X.columns)
    top = np.argsort(-contrib, axis=1)[:, :3]
    out["top_reasons"] = [
        "; ".join(REASONS.get(names[j], f"Rule {names[j][5:]} fired") for j in row if contrib[i, j] > 0)
        for i, row in enumerate(top)
    ]

    # thresholds from the training period only
    tr = out[train]
    fraud_scores = np.sort(tr.loc[tr.is_fraud, "risk_score"].to_numpy())
    k = int(np.floor(config.MAX_FRAUD_IN_AUTO_CLOSE * len(fraud_scores)))
    auto_close_below = float(fraud_scores[k]) if k < len(fraud_scores) else 0.0
    priority_from = float(np.quantile(tr.risk_score, 1 - config.PRIORITY_SHARE))

    out["triage_band"] = np.select(
        [out.risk_score < auto_close_below, out.risk_score >= priority_from],
        ["Auto-close", "Priority"], "Standard")
    rng = np.random.default_rng(config.SEED + 1)
    out["qa_sampled"] = (out.triage_band == "Auto-close") & (rng.random(len(out)) < config.QA_SAMPLE_RATE)

    te = out[~train]
    info = {
        "auto_close_below": auto_close_below,
        "priority_from": priority_from,
        "auc_test": float(roc_auc_score(te.is_fraud, te.risk_score)),
        "coefficients": dict(zip(names, np.round(model.coef_[0], 3))),
    }
    return out, info
