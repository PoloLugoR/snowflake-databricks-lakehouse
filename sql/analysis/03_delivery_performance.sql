-- 03_delivery_performance.sql
-- Business question: Which shipping modes deliver late most often, and by how much?
-- Skills: conditional aggregation (IFF), MEDIAN, PERCENTILE_CONT

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.marts;

SELECT
    sm.shipping_mode,
    COUNT(*) AS items,
    ROUND(100 * AVG(IFF(f.is_late, 1, 0)), 1) AS late_pct,
    MEDIAN(f.shipping_delay_days) AS median_delay_days,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY f.shipping_delay_days) AS p90_delay_days
FROM fct_order_items AS f
INNER JOIN dim_shipping_mode AS sm ON f.shipping_mode_key = sm.shipping_mode_key
GROUP BY sm.shipping_mode
ORDER BY late_pct DESC;
