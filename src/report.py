"""Charts, benefits summary, Power BI extracts and prototype data."""
from __future__ import annotations

import json

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

import config

INK, MUTED, GRID = "#1f2d33", "#5b6b70", "#e3e8ea"
BASE, OPT, FLAG = "#8aa0a6", "#006a4d", "#c8553d"


def _style(ax, axis="y"):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def charts(con: duckdb.DuckDBPyConnection) -> None:
    config.IMAGES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titlesize": 12, "axes.titleweight": "bold"})

    # 1. backlog at 6pm, both scenarios
    d = con.sql("SELECT * FROM daily_kpis ORDER BY day").df()
    d["day"] = pd.to_datetime(d.day)
    switch = pd.Timestamp(config.START_DATE) + pd.Timedelta(days=config.TRAIN_DAYS)
    fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=150)
    base = d[d.scenario == "Baseline"]
    opt = d[(d.scenario == "Optimised") & (d.day >= switch - pd.Timedelta(days=1))]
    ax.plot(base.day, base.backlog_at_6pm, color=BASE, lw=2, label="Current process")
    ax.plot(opt.day, opt.backlog_at_6pm, color=OPT, lw=2.4, label="With new triage (from day 31)")
    ax.axvline(switch, color=INK, ls=(0, (4, 3)), lw=1)
    ax.text(switch + pd.Timedelta(hours=12), ax.get_ylim()[1] * 0.93, "New triage switched on", fontsize=8, color=INK)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_ylabel("Alerts waiting at 6pm", color=MUTED, fontsize=9)
    ax.set_title("Investigation backlog at the end of each working day", loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    _style(ax)
    fig.tight_layout()
    fig.savefig(config.IMAGES / "backlog_before_after.png")
    plt.close(fig)

    # 2. rule performance: share of alerts vs share of fraud found
    r = con.sql("SELECT * FROM rule_performance ORDER BY precision_pct").df()
    fig, ax = plt.subplots(figsize=(8.5, 3.9), dpi=150)
    y = range(len(r))
    labels = [f"{a}  {b}" for a, b in zip(r.rule_id, r.rule_name)]
    ax.set_xlim(0, max(r.share_of_alerts_pct.max(), r.share_of_fraud_pct.max()) * 1.6)
    ax.barh([i + 0.2 for i in y], r.share_of_alerts_pct, height=0.38, color=BASE, label="Share of all alerts")
    ax.barh([i - 0.2 for i in y], r.share_of_fraud_pct, height=0.38, color=OPT, label="Share of fraud found")
    for i, (a, p) in enumerate(zip(r.share_of_alerts_pct, r.precision_pct)):
        ax.text(a + 0.5, i + 0.2, f"{p:.1f}% of its alerts are fraud", va="center", fontsize=7.5, color=MUTED)
    ax.set_yticks(list(y), labels, fontsize=8)
    ax.set_xlabel("% of total", color=MUTED, fontsize=9)
    ax.set_title("Rules: workload created vs fraud found (days 1-30)", loc="left", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    _style(ax, "x")
    fig.tight_layout()
    fig.savefig(config.IMAGES / "rule_performance.png")
    plt.close(fig)

    # 3. benefits: before vs after
    b = con.sql("SELECT * FROM benefits").df().set_index("measure")
    show = ["Alerts decided within 24 hours", "Median hours to decision (alerts a person reviews)",
            "Median hours to decision: genuine fraud", "Investigator hours per week"]
    fig, axes = plt.subplots(1, 4, figsize=(10, 3.2), dpi=150)
    for ax, m in zip(axes, show):
        v = b.loc[m]
        ax.bar(["Before", "After"], [v.baseline, v.optimised], color=[BASE, OPT], width=0.6)
        for x, val in enumerate([v.baseline, v.optimised]):
            ax.text(x, val, f"{val:,.1f}{'%' if v.unit == '%' else ''}", ha="center", va="bottom", fontsize=9, color=INK)
        ax.set_title(m.replace(" (alerts a person reviews)", "\n(reviewed alerts)").replace(": genuine fraud", "\n(genuine fraud)")
                     .replace("Investigator hours per week", "Investigator\nhours per week").replace("Alerts decided within 24 hours", "Decided within\n24 hours (%)"),
                     fontsize=9, color=INK)
        ax.set_yticks([])
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=9)
    fig.suptitle("Days 31-60: same alerts, current process vs new triage", x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(config.IMAGES / "benefits_before_after.png")
    plt.close(fig)


def powerbi_extracts(con: duckdb.DuckDBPyConnection) -> None:
    config.POWERBI.mkdir(parents=True, exist_ok=True)
    con.sql("""SELECT alert_id, customer_id, rule_id, CAST(raised_at AS DATE) AS date_key, raised_at, period,
                      amount_gbp, channel, is_fraud, handling_minutes, risk_score, triage_band, qa_sampled,
                      top_reasons, decided_baseline, decided_optimised,
                      hours_to_decision_baseline, hours_to_decision_optimised
               FROM alerts_scored""").df().to_csv(config.POWERBI / "fact_alert.csv", index=False)
    con.sql("SELECT * FROM rules").df().to_csv(config.POWERBI / "dim_rule.csv", index=False)
    con.sql("""SELECT DISTINCT CAST(raised_at AS DATE) AS date_key, dayname(raised_at) AS weekday,
                      period FROM alerts_scored ORDER BY 1""").df().to_csv(config.POWERBI / "dim_date.csv", index=False)
    con.sql("SELECT * FROM daily_kpis").df().to_csv(config.POWERBI / "fact_daily_kpi.csv", index=False)
    for t in ("benefits", "rule_performance"):
        con.sql(f"SELECT * FROM {t}").df().to_csv(config.OUTPUTS / f"{t}.csv", index=False)


def prototype_data(con: duckdb.DuckDBPyConnection) -> None:
    """A small, realistic queue for the clickable workbench prototype."""
    q = con.sql("""
        SELECT alert_id, rule_id, r.rule_name, strftime(raised_at, '%d %b %H:%M') AS raised,
               amount_gbp, channel, round(risk_score * 100, 1) AS risk, triage_band, qa_sampled, top_reasons,
               new_payee, new_device, payments_last_24h, high_risk_country, account_age_days
        FROM alerts_scored JOIN rules r USING (rule_id)
        WHERE period = 'test' AND CAST(raised_at AS DATE) = (SELECT min(CAST(raised_at AS DATE)) + 7 FROM alerts_scored WHERE period = 'test')
          AND (triage_band <> 'Auto-close' OR qa_sampled)
        ORDER BY CASE triage_band WHEN 'Priority' THEN 0 ELSE 1 END, raised_at
        LIMIT 60
    """).df()
    auto = con.sql("""SELECT count(*) FROM alerts_scored WHERE period = 'test' AND triage_band = 'Auto-close' AND NOT qa_sampled
                      AND CAST(raised_at AS DATE) = (SELECT min(CAST(raised_at AS DATE)) + 7 FROM alerts_scored WHERE period = 'test')""").fetchone()[0]
    payload = {"auto_closed_today": int(auto), "rules": config.RULES, "alerts": q.to_dict(orient="records")}
    (config.PROTOTYPE / "sample_queue.json").write_text(json.dumps(payload, indent=1, default=str))
    html = (config.PROTOTYPE / "workbench_template.html").read_text()
    (config.PROTOTYPE / "workbench.html").write_text(html.replace("/*__DATA__*/null", json.dumps(payload, default=str)))


def summary(con: duckdb.DuckDBPyConnection, info: dict) -> dict:
    b = con.sql("SELECT * FROM benefits").df().set_index("measure")
    bands = con.sql("""SELECT triage_band, count(*) n, sum(is_fraud::INT) f FROM alerts_scored
                       WHERE period = 'test' GROUP BY 1""").df().set_index("triage_band")
    qa_caught = con.sql("""SELECT sum(is_fraud::INT) FROM alerts_scored
                           WHERE period = 'test' AND triage_band = 'Auto-close' AND qa_sampled""").fetchone()[0] or 0
    total_test = int(bands.n.sum())
    total_fraud = int(bands.f.sum())
    auto_n, auto_f = int(bands.loc["Auto-close", "n"]), int(bands.loc["Auto-close", "f"])
    missed = auto_f - int(qa_caught)
    pr = bands.loc["Priority"]
    hrs = b.loc["Investigator hours per week"]
    saved_week = hrs.baseline - hrs.optimised
    fte = saved_week / (config.PRODUCTIVE_HOURS_PER_DAY * 5)
    rp = con.sql("SELECT * FROM rule_performance ORDER BY precision_pct").df()
    worst = rp.iloc[0]

    facts = dict(total_test=total_test, total_fraud=total_fraud, auto_n=auto_n, auto_f=auto_f, missed=missed,
                 auto_pct=100 * auto_n / total_test, recall=100 * (total_fraud - missed) / total_fraud,
                 pr_n=int(pr.n), pr_f=int(pr.f), pr_share_fraud=100 * pr.f / total_fraud,
                 saved_week=saved_week, fte=fte, sla_b=b.loc["Alerts decided within 24 hours"].baseline,
                 sla_o=b.loc["Alerts decided within 24 hours"].optimised,
                 fraud_h_b=b.loc["Median hours to decision: genuine fraud"].baseline,
                 fraud_h_o=b.loc["Median hours to decision: genuine fraud"].optimised,
                 auc=info["auc_test"], worst=worst)
    f = facts
    lines = [
        "# Benefits summary - fraud alert triage",
        "",
        "*Synthetic data for a fictional UK retail bank. Generated by `src/report.py` - do not edit by hand.*",
        "",
        "## Headline (days 31-60, same alerts under both processes)",
        "",
        f"- **{f['auto_pct']:.1f}% of alerts ({f['auto_n']:,} of {f['total_test']:,}) closed automatically** with a logged reason; "
        f"{config.QA_SAMPLE_RATE:.0%} of them still go to a person as a quality check.",
        f"- **{f['saved_week']:,.0f} investigator hours a week released**, about **{f['fte']:.1f} full-time investigators** "
        f"(at {config.PRODUCTIVE_HOURS_PER_DAY * 5:.1f} productive hours a week).",
        f"- **Alerts decided within 24 hours: {f['sla_b']:.1f}% → {f['sla_o']:.1f}%.**",
        f"- **Median time to a decision on genuine fraud: {f['fraud_h_b']:.1f} → {f['fraud_h_o']:.1f} hours.** "
        f"The priority queue holds 5% of alerts but **{f['pr_share_fraud']:.0f}%** of the fraud.",
        "",
        "## The trade-off",
        "",
        f"- {f['auto_f']} genuine fraud cases ({100 * f['auto_f'] / f['total_fraud']:.1f}% of {f['total_fraud']}) scored low enough to be auto-closed; "
        f"the QA sample caught {f['auto_f'] - f['missed']}, so **{f['missed']} would be missed** ({f['recall']:.1f}% of fraud still reaches a person).",
        "- Before going live, the risk owner would need to agree that trade-off, or lower the auto-close threshold or raise the QA sample.",
        "  Both are single settings in `src/config.py`.",
        "",
        "## Rule tuning opportunity",
        "",
        f"- **{worst.rule_id} {worst.rule_name}** creates **{worst.share_of_alerts_pct:.0f}%** of all alerts but finds "
        f"**{worst.share_of_fraud_pct:.0f}%** of the fraud: only {worst.precision_pct:.1f}% of its alerts are genuine, and each case found costs "
        f"**{worst.hours_per_fraud_found:.0f} investigator hours**. It is the first candidate for re-tuning with the rule owner.",
        "",
        "## Benefits tracking table",
        "",
        "| Measure | Before | After | Change |",
        "|---|---:|---:|---:|",
    ]
    for m, r in b.iterrows():
        fmt = (lambda v: f"{v:,.1f}%") if r.unit == "%" else (lambda v: f"{v:,.1f}") if r.unit == "hours" else (lambda v: f"{v:,.0f}")
        lines.append(f"| {m} | {fmt(r.baseline)} | {fmt(r.optimised)} | {r.optimised - r.baseline:+,.1f} |")
    lines += [
        "",
        "## Model",
        "",
        f"Logistic regression on 11 alert features plus the rule that fired, trained on days 1-30 only. "
        f"AUC on days 31-60: **{f['auc']:.2f}**. Thresholds were set on days 1-30 and not changed afterwards.",
        "",
    ]
    (config.DOCS / "benefits_summary.md").write_text("\n".join(lines))
    return facts
