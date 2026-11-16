"""Run end to end: generate -> score and triage -> simulate both processes -> report."""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent / "src"))

import generate_data  # noqa: E402
import pipeline  # noqa: E402
import report  # noqa: E402


def main() -> None:
    print("1/3 generating 60 days of synthetic alerts")
    alerts = generate_data.main()
    print("2/3 scoring, triaging and simulating the investigation queue")
    con, info = pipeline.run(alerts)
    print(f"    test-period AUC {info['auc_test']:.3f}")
    print("3/3 writing charts, benefits summary, Power BI extracts and prototype")
    report.charts(con)
    report.powerbi_extracts(con)
    report.prototype_data(con)
    f = report.summary(con, info)
    print(con.sql("SELECT measure, round(baseline, 1) AS before, round(optimised, 1) AS after FROM benefits"))
    print(f"    auto-closed {f['auto_pct']:.1f}%, {f['missed']} fraud missed, {f['fte']:.1f} FTE released")


if __name__ == "__main__":
    main()
