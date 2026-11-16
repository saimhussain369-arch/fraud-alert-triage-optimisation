"""Simulate the investigation queue against a working-hours calendar.

Investigators work 08:00-18:00 on weekdays and 09:00-17:00 at weekends with 40%
of the team, so alerts raised overnight or at the weekend wait. Each alert needs its
handling time from the team. Alerts are worked in queue order:
  - Baseline: first in, first out.
  - Optimised (switched on for days 31-60 only): Priority first, then Standard and QA
    checks, each first in, first out. Auto-close alerts that are not QA-sampled are
    closed by the automation as soon as they are raised.

The queue runs in "team capacity minutes": each arrival time is converted to the
amount of team capacity available up to that moment, so one priority queue handles
the whole calendar, and decisions are converted back to clock time at the end.
"""
from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

import config


def capacity_calendar(start: pd.Timestamp, days: int) -> np.ndarray:
    """Team review minutes available in each clock hour."""
    daily = config.INVESTIGATORS * config.PRODUCTIVE_HOURS_PER_DAY * 60
    cap = np.zeros(days * 24)
    for d in range(days):
        weekend = (start + pd.Timedelta(days=d)).weekday() >= 5
        hours = range(9, 17) if weekend else range(8, 18)
        per_hour = (0.4 * daily if weekend else daily) / len(hours)
        for h in hours:
            cap[d * 24 + h] = per_hour
    return cap


def simulate(df: pd.DataFrame, policy: str) -> pd.Series:
    """Return the decision timestamp for every alert under 'baseline' or 'optimised'."""
    order = df.sort_values("raised_at")
    decided: dict = {}
    if policy == "baseline":
        work = order.handling_minutes.to_numpy()
        rank = np.ones(len(order))
    else:
        live = order.period == "test"
        auto = live & (order.triage_band == "Auto-close") & ~order.qa_sampled
        decided.update(dict(zip(order.index[auto], order.raised_at[auto])))  # closed by the flow straight away
        order = order[~auto]
        live = (order.period == "test").to_numpy()
        band = order.triage_band.to_numpy()
        work = np.where(live & (band == "Auto-close"), config.QA_MINUTES, order.handling_minutes)
        rank = np.where(live & (band == "Priority"), 0, 1)

    start = order.raised_at.min().floor("D")
    span_days = int((order.raised_at.max() - start).days) + 40           # room to clear any backlog
    cap = capacity_calendar(start, span_days)
    cum = np.concatenate([[0.0], np.cumsum(cap)])                       # capacity used up to the start of each hour

    def to_capacity(hours: np.ndarray) -> np.ndarray:
        h = np.floor(hours).astype(int)
        return cum[h] + (hours - h) * cap[h]

    def to_clock(c: float) -> pd.Timestamp:
        h = int(np.searchsorted(cum, c, side="right") - 1)
        frac = (c - cum[h]) / cap[h] if cap[h] > 0 else 0.0
        return start + pd.Timedelta(hours=h + frac)

    arr_c = to_capacity(((order.raised_at - start).dt.total_seconds() / 3600).to_numpy())
    arrivals = list(zip(arr_c, rank, order.index, work))
    queue: list = []
    t = 0.0
    i, n = 0, len(arrivals)
    while i < n or queue:
        if not queue:
            t = max(t, arrivals[i][0])
        while i < n and arrivals[i][0] <= t:
            a, r, idx, w = arrivals[i]
            heapq.heappush(queue, (r, a, idx, w))
            i += 1
        r, a, idx, w = heapq.heappop(queue)
        t += w
        decided[idx] = to_clock(t)
    return pd.Series(decided).reindex(df.index)
