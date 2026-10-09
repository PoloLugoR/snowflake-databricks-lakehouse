-- 04_features_demo.sql
-- Snowflake feature demos: zero-copy clone with time travel, and role-based access.
-- Run each statement one at a time in a single worksheet.
-- Note: dbt creates tables as TRANSIENT, so clones of them must be TRANSIENT too.

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;

-- PART 1: clone and time travel --------------------------------------------
CREATE OR REPLACE TRANSIENT TABLE dataco.marts.fct_order_items_clone
  CLONE dataco.marts.fct_order_items;

-- Break the clone on purpose, then remember which statement did it
UPDATE dataco.marts.fct_order_items_clone
SET profit = 0
WHERE shipping_delay_days > 2;

SET bad_update_id = LAST_QUERY_ID();

-- Restore the table as it was just before the bad update
CREATE OR REPLACE TRANSIENT TABLE dataco.marts.fct_order_items_restored
  CLONE dataco.marts.fct_order_items_clone
  BEFORE(STATEMENT => $bad_update_id);

-- Proof: original and restored match, the damaged copy does not
SELECT 'original table' AS stage, COUNT(*) AS items, ROUND(SUM(profit), 0) AS total_profit
FROM dataco.marts.fct_order_items
UNION ALL
SELECT 'copy after damage', COUNT(*), ROUND(SUM(profit), 0)
FROM dataco.marts.fct_order_items_clone
UNION ALL
SELECT 'restored with time travel', COUNT(*), ROUND(SUM(profit), 0)
FROM dataco.marts.fct_order_items_restored;

DROP TABLE IF EXISTS dataco.marts.fct_order_items_clone;
DROP TABLE IF EXISTS dataco.marts.fct_order_items_restored;

-- PART 2: read-only analyst role -------------------------------------------
CREATE ROLE IF NOT EXISTS analyst_role;
GRANT USAGE ON WAREHOUSE wh_dev TO ROLE analyst_role;
GRANT USAGE ON DATABASE dataco TO ROLE analyst_role;
GRANT USAGE ON SCHEMA dataco.marts TO ROLE analyst_role;
GRANT SELECT ON ALL TABLES IN SCHEMA dataco.marts TO ROLE analyst_role;
GRANT SELECT ON FUTURE TABLES IN SCHEMA dataco.marts TO ROLE analyst_role;
GRANT ROLE analyst_role TO USER "polo.lugor";

-- Tests, run as the analyst:
USE ROLE analyst_role;
-- Without the next line, privileges from the user's other roles still apply
-- and the access tests below prove nothing.
USE SECONDARY ROLES NONE;
USE WAREHOUSE wh_dev;

SELECT COUNT(*) FROM dataco.marts.fct_order_items;            -- works
-- SELECT COUNT(*) FROM dataco.raw.supply_chain_orders;       -- expected to fail: not authorized
-- UPDATE dataco.marts.fct_order_items
--   SET profit = profit WHERE 1 = 0;                         -- expected to fail: read-only

-- Back to admin and restore the default
USE ROLE ACCOUNTADMIN;
USE SECONDARY ROLES ALL;
