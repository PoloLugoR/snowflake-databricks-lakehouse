-- 02_monthly_profit_trend.sql
-- Business question: How does profit change month to month, and what is the trend?
-- Skills: CTE, LAG(), moving average with a window frame, NULLIF to avoid divide-by-zero

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.marts;

WITH monthly AS (
    SELECT
        d.year_month,
        SUM(f.profit) AS profit
    FROM fct_order_items AS f
    INNER JOIN dim_date AS d ON f.date_key = d.date_key
    GROUP BY d.year_month
)

SELECT
    year_month,
    ROUND(profit, 0) AS profit,
    ROUND(profit - LAG(profit) OVER (ORDER BY year_month), 0) AS mom_change,
    ROUND(100 * (profit / NULLIF(LAG(profit) OVER (ORDER BY year_month), 0) - 1), 1) AS mom_pct,
    ROUND(AVG(profit) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS profit_3m_avg
FROM monthly
ORDER BY year_month;
