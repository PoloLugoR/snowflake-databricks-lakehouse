-- 05_data_quality_checks.sql
-- Business question: Can we trust the data? Each row shows how many records break a rule.
-- Skills: UNION ALL, validation logic, anti-join. Every issue_rows value should be 0.

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.marts;

SELECT 'duplicate order items' AS check_name,
       COUNT(*) - COUNT(DISTINCT order_item_key) AS issue_rows
FROM fct_order_items
UNION ALL
SELECT 'negative shipping days', COUNT(*)
FROM fct_order_items
WHERE shipping_days_real < 0
UNION ALL
SELECT 'shipped before ordered', COUNT(*)
FROM fct_order_items
WHERE shipping_date_key < date_key
UNION ALL
SELECT 'quantity zero or negative', COUNT(*)
FROM fct_order_items
WHERE quantity <= 0
UNION ALL
SELECT 'customers with no orders', COUNT(*)
FROM dim_customer AS c
LEFT JOIN fct_order_items AS f ON c.customer_key = f.customer_key
WHERE f.customer_key IS NULL;
