"""Settings for the fraud alert triage optimisation project. All data is synthetic."""
from pathlib import Path

import pandas as pd

try:  # classic object strings so DuckDB can read pandas frames on pandas 2.x and 3.x
    pd.set_option("future.infer_string", False)
except (KeyError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
POWERBI = OUTPUTS / "powerbi"
DOCS = ROOT / "docs"
IMAGES = DOCS / "images"
PROTOTYPE = ROOT / "prototype"
DB_PATH = DATA / "alerts.duckdb"

SEED = 7
START_DATE = "2026-07-01"
DAYS = 60                    # days 1-30 train the score, days 31-60 measure the change
TRAIN_DAYS = 30
ALERTS_PER_DAY = 620          # average, varies by weekday

# Operations team
INVESTIGATORS = 24
PRODUCTIVE_HOURS_PER_DAY = 6.5
SLA_HOURS = 24               # alert must have a decision within 24 hours of being raised

# Triage policy (chosen on the training period only)
MAX_FRAUD_IN_AUTO_CLOSE = 0.01   # at most 1% of training fraud may fall in the auto-close band
PRIORITY_SHARE = 0.05            # top 5% of scores go to the priority queue
QA_SAMPLE_RATE = 0.05            # 5% of auto-closed alerts are still checked by a person
QA_MINUTES = 4                   # a QA check is quicker than a full review

RULES = {
    "R01": "High-value payment to a new payee",
    "R02": "Payment velocity: many payments in 24 hours",
    "R03": "New device followed by a high-value payment",
    "R04": "Payment to a high-risk country",
    "R05": "Dormant account suddenly active",
    "R06": "Round-amount transfers",
    "R07": "Failed logins followed by a payment",
    "R08": "Money in and straight out (possible mule)",
}
