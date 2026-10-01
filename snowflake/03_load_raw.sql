-- 03_load_raw.sql
-- Loads the DataCo supply chain CSV into dataco.raw.supply_chain_orders.
--
-- Before running: download the dataset from Kaggle, unzip it, and upload
-- DataCoSupplyChainDataset.csv to the @dataco.raw.landing stage
-- (Snowsight: Catalog > DATACO > RAW > Stages > LANDING).

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.raw;

-- Build the table from the file's own header (53 columns)
CREATE OR REPLACE TABLE supply_chain_orders
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    FROM TABLE(
      INFER_SCHEMA(
        LOCATION => '@dataco.raw.landing/DataCoSupplyChainDataset.csv',
        FILE_FORMAT => 'dataco.raw.csv_ff'
      )
    )
  );

COPY INTO supply_chain_orders
  FROM @dataco.raw.landing/DataCoSupplyChainDataset.csv
  FILE_FORMAT = (FORMAT_NAME = 'dataco.raw.csv_ff')
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

-- Quick check: expect roughly 180,000 rows
SELECT COUNT(*) AS row_count FROM supply_chain_orders;