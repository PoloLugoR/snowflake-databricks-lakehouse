-- 06_load_from_databricks.sql
-- Bridge: loads the Databricks gold fact table (exported as Parquet) into Snowflake
-- and reconciles it against the dbt-built dataco.marts.fct_order_items.
-- Databricks Free Edition blocks outbound internet, so the hand-off is a file:
-- Databricks gold -> Parquet in a volume -> download -> upload to this stage -> COPY INTO.

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;

CREATE SCHEMA IF NOT EXISTS dataco.bridge;
CREATE STAGE IF NOT EXISTS dataco.bridge.dbx_landing;

CREATE OR REPLACE TABLE dataco.bridge.fct_order_items_dbx (
  order_item_key NUMBER, order_id NUMBER, customer_key NUMBER, product_key NUMBER,
  geography_key VARCHAR, shipping_mode_key VARCHAR, date_key NUMBER, shipping_date_key NUMBER,
  payment_type VARCHAR, order_status VARCHAR, delivery_status VARCHAR,
  quantity NUMBER, unit_price NUMBER(18,2), sales NUMBER(18,2), discount NUMBER(18,2),
  discount_rate FLOAT, order_item_total NUMBER(18,2), profit NUMBER(18,2), profit_ratio FLOAT,
  shipping_days_real NUMBER, shipping_days_scheduled NUMBER, shipping_delay_days NUMBER,
  is_late BOOLEAN
);

-- Upload fct_order_items_dbx.parquet to @dataco.bridge.dbx_landing in Snowsight, then:
COPY INTO dataco.bridge.fct_order_items_dbx
  FROM @dataco.bridge.dbx_landing
  FILE_FORMAT = (TYPE = PARQUET)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

-- Reconciliation: every value should match; mismatched_rows should be 0
SELECT COUNT(*) AS mismatched_rows
FROM dataco.marts.fct_order_items AS s
FULL OUTER JOIN dataco.bridge.fct_order_items_dbx AS d
  ON s.order_item_key = d.order_item_key
WHERE s.order_item_key IS NULL
   OR d.order_item_key IS NULL
   OR ABS(COALESCE(s.profit, 0) - COALESCE(d.profit, 0)) > 0.01
   OR ABS(COALESCE(s.sales, 0) - COALESCE(d.sales, 0)) > 0.01
   OR s.is_late IS DISTINCT FROM d.is_late
   OR s.shipping_delay_days IS DISTINCT FROM d.shipping_delay_days;
