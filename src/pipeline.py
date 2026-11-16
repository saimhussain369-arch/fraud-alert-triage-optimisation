"""Score alerts, simulate both scenarios and build the reporting tables in DuckDB."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
from jinja2 import Template

import config
import queue_sim
import triage

SQL = config.ROOT / "sql"


def _render(name: str) -> str:
    return Template((SQL / name).read_text()).render(
        QA_MINUTES=config.QA_MINUTES, SLA_HOURS=config.SLA_HOURS, HOURS_PER_DAY=config.PRODUCTIVE_HOURS_PER_DAY)


def run(alerts: pd.DataFrame, db_path: Path = config.DB_PATH) -> tuple[duckdb.DuckDBPyConnection, dict]:
    scored, info = triage.score(alerts)
    for policy in ("baseline", "optimised"):
        decided = queue_sim.simulate(scored, policy)
        scored[f"decided_{policy}"] = decided
        scored[f"hours_to_decision_{policy}"] = ((decided - scored.raised_at).dt.total_seconds() / 3600).round(2)

    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    rules = pd.DataFrame({"rule_id": list(config.RULES), "rule_name": list(config.RULES.values())})
    con.register("alerts_df", alerts)
    con.register("scored_df", scored)
    con.register("rules_df", rules)
    con.execute("CREATE TABLE alerts AS SELECT * FROM alerts_df")
    con.execute("CREATE TABLE alerts_scored AS SELECT * FROM scored_df")
    con.execute("CREATE TABLE rules AS SELECT * FROM rules_df")
    for name in ("01_rule_performance.sql", "02_daily_kpis.sql", "03_benefits.sql"):
        con.execute(_render(name))
    return con, info
