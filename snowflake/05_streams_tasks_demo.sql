-- 05_streams_tasks_demo.sql
-- Incremental loading with a stream and a task, on a clone of the raw table
-- (the real raw table is never modified). Run one statement at a time.

-- STEP 1
USE ROLE ACCOUNTADMIN;
-- STEP 2
USE WAREHOUSE wh_dev;

-- STEP 3: demo copy of the raw table (instant, no extra storage)
CREATE OR REPLACE TABLE dataco.raw.feed_demo CLONE dataco.raw.supply_chain_orders;

-- STEP 4: the stream is a bookmark that tracks rows added since it was last consumed
CREATE OR REPLACE STREAM dataco.raw.feed_demo_stream
  ON TABLE dataco.raw.feed_demo
  APPEND_ONLY = TRUE;

-- STEP 5: should return 0
SELECT COUNT(*) AS new_rows_waiting FROM dataco.raw.feed_demo_stream;

-- STEP 6: log table
CREATE OR REPLACE TABLE dataco.raw.feed_load_log (loaded_at TIMESTAMP, new_rows NUMBER);

-- STEP 7: tasks are created suspended; EXECUTE TASK triggers a run by hand
CREATE OR REPLACE TASK dataco.raw.load_new_rows_task
  WAREHOUSE = wh_dev
  SCHEDULE = '60 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('dataco.raw.feed_demo_stream')
AS
  INSERT INTO dataco.raw.feed_load_log
  SELECT CURRENT_TIMESTAMP(), COUNT(*) FROM dataco.raw.feed_demo_stream;

-- STEP 8: simulate a new batch of 100 rows
INSERT INTO dataco.raw.feed_demo
SELECT * FROM dataco.raw.feed_demo LIMIT 100;

-- STEP 9: should return 100
SELECT COUNT(*) AS new_rows_waiting FROM dataco.raw.feed_demo_stream;

-- STEP 10: run the task, then wait about 15 seconds
EXECUTE TASK dataco.raw.load_new_rows_task;

-- STEP 11: the proof; expect 100 processed and 0 left in the stream
SELECT
  (SELECT SUM(new_rows) FROM dataco.raw.feed_load_log) AS rows_processed_by_task,
  (SELECT COUNT(*) FROM dataco.raw.feed_demo_stream) AS rows_left_in_stream;

-- STEP 12: clean up
DROP TASK IF EXISTS dataco.raw.load_new_rows_task;
DROP STREAM IF EXISTS dataco.raw.feed_demo_stream;
DROP TABLE IF EXISTS dataco.raw.feed_load_log;
DROP TABLE IF EXISTS dataco.raw.feed_demo;