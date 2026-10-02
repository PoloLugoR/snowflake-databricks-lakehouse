-- 01_top_categories_per_market.sql
-- Business question: Which 3 product categories earn the most profit in each market?
-- Skills: multi-table joins, aggregation, RANK() window function, QUALIFY

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.marts;

SELECT
    g.market,
    p.category_name,
    ROUND(SUM(f.profit), 0) AS total_profit,
    RANK() OVER (PARTITION BY g.market ORDER BY SUM(f.profit) DESC) AS profit_rank
FROM fct_order_items AS f
INNER JOIN dim_geography AS g ON f.geography_key = g.geography_key
INNER JOIN dim_product AS p ON f.product_key = p.product_key
GROUP BY g.market, p.category_name
QUALIFY profit_rank <= 3
ORDER BY g.market, profit_rank;
