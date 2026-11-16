-- Before and after on the same 30 test days (days 31-60).
CREATE OR REPLACE TABLE benefits AS
WITH t AS (SELECT * FROM alerts_scored WHERE period = 'test'),
span AS (SELECT count(DISTINCT CAST(raised_at AS DATE)) AS n_days FROM t),
base AS (
    SELECT
        count(*)                                                                AS alerts_needing_person,
        sum(handling_minutes) / 60                                              AS review_hours,
        100.0 * avg(CASE WHEN hours_to_decision_baseline <= {{SLA_HOURS}} THEN 1 ELSE 0 END) AS pct_within_sla,
        median(hours_to_decision_baseline)                                      AS median_hours_to_decision,
        median(hours_to_decision_baseline) FILTER (WHERE is_fraud)              AS median_hours_fraud,
        sum(is_fraud::INT)                                                      AS fraud_reviewed_by_person,
        count(*) FILTER (WHERE NOT is_fraud)                                    AS false_alarms_reviewed
    FROM t
),
opt AS (
    SELECT
        count(*) FILTER (WHERE NOT (triage_band = 'Auto-close' AND NOT qa_sampled))       AS alerts_needing_person,
        (sum(handling_minutes) FILTER (WHERE triage_band <> 'Auto-close')
         + {{QA_MINUTES}} * count(*) FILTER (WHERE qa_sampled)) / 60                      AS review_hours,
        100.0 * avg(CASE WHEN hours_to_decision_optimised <= {{SLA_HOURS}} THEN 1 ELSE 0 END) AS pct_within_sla,
        median(hours_to_decision_optimised) FILTER (WHERE NOT (triage_band = 'Auto-close' AND NOT qa_sampled)) AS median_hours_to_decision,
        median(hours_to_decision_optimised) FILTER (WHERE is_fraud)                       AS median_hours_fraud,
        sum(is_fraud::INT) FILTER (WHERE triage_band <> 'Auto-close' OR qa_sampled)       AS fraud_reviewed_by_person,
        count(*) FILTER (WHERE NOT is_fraud AND (triage_band <> 'Auto-close' OR qa_sampled)) AS false_alarms_reviewed
    FROM t
)
SELECT * FROM (VALUES
    ('Alerts needing an investigator', (SELECT alerts_needing_person FROM base), (SELECT alerts_needing_person FROM opt), 'count'),
    ('Investigator hours',            (SELECT review_hours FROM base),          (SELECT review_hours FROM opt), 'hours'),
    ('Investigator hours per week',   (SELECT review_hours FROM base) * 7.0 / (SELECT n_days FROM span),
                                       (SELECT review_hours FROM opt) * 7.0 / (SELECT n_days FROM span), 'hours'),
    ('Alerts decided within 24 hours', (SELECT pct_within_sla FROM base),       (SELECT pct_within_sla FROM opt), '%'),
    ('Median hours to decision (alerts a person reviews)', (SELECT median_hours_to_decision FROM base), (SELECT median_hours_to_decision FROM opt), 'hours'),
    ('Median hours to decision: genuine fraud', (SELECT median_hours_fraud FROM base), (SELECT median_hours_fraud FROM opt), 'hours'),
    ('False alarms reviewed by a person', (SELECT false_alarms_reviewed FROM base), (SELECT false_alarms_reviewed FROM opt), 'count'),
    ('Genuine fraud reviewed by a person', (SELECT fraud_reviewed_by_person FROM base), (SELECT fraud_reviewed_by_person FROM opt), 'count')
) AS b(measure, baseline, optimised, unit);
