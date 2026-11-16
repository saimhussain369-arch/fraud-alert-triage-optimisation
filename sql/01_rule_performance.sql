-- How well does each monitoring rule perform today? Training period only (days 1-30).
CREATE OR REPLACE TABLE rule_performance AS
SELECT
    a.rule_id,
    r.rule_name,
    count(*)                                                  AS alerts,
    sum(a.is_fraud::INT)                                      AS fraud_cases,
    round(100.0 * avg(a.is_fraud::INT), 2)                    AS precision_pct,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)        AS share_of_alerts_pct,
    round(100.0 * sum(a.is_fraud::INT) / sum(sum(a.is_fraud::INT)) OVER (), 1) AS share_of_fraud_pct,
    round(sum(a.handling_minutes) / 60, 0)                    AS investigator_hours,
    round(sum(a.handling_minutes) / 60 / nullif(sum(a.is_fraud::INT), 0), 1) AS hours_per_fraud_found
FROM alerts a
JOIN rules r USING (rule_id)
WHERE a.period = 'train'
GROUP BY ALL
ORDER BY precision_pct;
