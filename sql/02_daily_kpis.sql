-- Daily operational KPIs for both scenarios: alerts raised, alerts needing a person,
-- review hours, backlog at 6pm, and share decided within the SLA.
CREATE OR REPLACE TABLE daily_kpis AS
WITH long AS (
    SELECT alert_id, raised_at, period, is_fraud, triage_band, qa_sampled, handling_minutes,
           'Baseline' AS scenario, decided_baseline AS decided_at,
           TRUE AS needs_person, handling_minutes AS review_minutes
    FROM alerts_scored
    UNION ALL
    SELECT alert_id, raised_at, period, is_fraud, triage_band, qa_sampled, handling_minutes,
           'Optimised', decided_optimised,
           NOT (period = 'test' AND triage_band = 'Auto-close' AND NOT qa_sampled),
           CASE WHEN period = 'test' AND triage_band = 'Auto-close' THEN
                    CASE WHEN qa_sampled THEN {{QA_MINUTES}} ELSE 0 END
                ELSE handling_minutes END
    FROM alerts_scored
),
days AS (SELECT DISTINCT CAST(raised_at AS DATE) AS day FROM alerts_scored)
SELECT
    d.day,
    l.scenario,
    count(*) FILTER (WHERE CAST(l.raised_at AS DATE) = d.day)                         AS alerts_raised,
    count(*) FILTER (WHERE CAST(l.raised_at AS DATE) = d.day AND l.needs_person)      AS alerts_needing_person,
    round(sum(l.review_minutes) FILTER (WHERE CAST(l.raised_at AS DATE) = d.day) / 60, 1) AS review_hours,
    count(*) FILTER (WHERE l.raised_at <= d.day + INTERVAL 18 HOUR
                       AND l.decided_at > d.day + INTERVAL 18 HOUR)                    AS backlog_at_6pm,
    round(100.0 * avg(CASE WHEN date_diff('minute', l.raised_at, l.decided_at) <= {{SLA_HOURS}} * 60 THEN 1 ELSE 0 END)
          FILTER (WHERE CAST(l.raised_at AS DATE) = d.day), 1)                         AS pct_within_sla
FROM days d
CROSS JOIN (SELECT DISTINCT scenario FROM long) s
JOIN long l ON l.scenario = s.scenario
GROUP BY d.day, l.scenario
ORDER BY d.day, l.scenario;
