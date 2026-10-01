-- 02_stage_and_format.sql
-- Creates the file format and internal stage used to load the DataCo CSV.
-- ENCODING is ISO-8859-1 because the DataCo file is not UTF-8
-- (accented characters like "ú" otherwise cause an "Invalid UTF8" error).

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE wh_dev;
USE SCHEMA dataco.raw;

CREATE OR REPLACE FILE FORMAT csv_ff
  TYPE = CSV
  PARSE_HEADER = TRUE
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  ENCODING = 'ISO-8859-1';

CREATE STAGE IF NOT EXISTS landing
  FILE_FORMAT = csv_ff;