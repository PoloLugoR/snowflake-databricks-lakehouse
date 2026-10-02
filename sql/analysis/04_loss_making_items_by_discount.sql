-- 04_loss_making_items_by_discount.sql
-- Business question: Do bigger discounts lead to more loss-making order items?
-- Skills: CTE, CASE bucketing, conditional aggregation

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.marts;

WITH bucketed AS (
    SELECT
        CASE
            WHEN discount_rate < 0.05 THEN '1) under 5%'
            WHEN discount_rate < 0.15 THEN '2) 5% to 15%'
            ELSE '3) 15% or more'
        END AS discount_band,
        profit
    FROM fct_order_items
)

SELECT
    discount_band,
    COUNT(*) AS items,
    SUM(IFF(profit < 0, 1, 0)) AS loss_items,
    ROUND(100 * AVG(IFF(profit < 0, 1, 0)), 1) AS loss_pct,
    ROUND(SUM(profit), 0) AS total_profit
FROM bucketed
GROUP BY discount_band
ORDER BY discount_band;
