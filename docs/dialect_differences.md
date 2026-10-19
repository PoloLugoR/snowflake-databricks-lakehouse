# Snowflake vs Databricks: syntax and behavior differences

Differences hit while building the same pipeline and analysis queries on both platforms.

| Area | Snowflake | Databricks (Spark SQL / Delta) |
|---|---|---|
| Object naming | `database.schema.table` (`dataco.marts.fct_order_items`) | `catalog.schema.table` (`workspace.gold.fct_order_items`) |
| Column names with spaces | Allowed when double-quoted (`"Order Id"`), so the raw layer mirrors the CSV header | Rejected by Delta, so columns are renamed to snake_case when writing bronze |
| Date parsing | `TRY_TO_TIMESTAMP(col, 'MM/DD/YYYY HH24:MI')` | `try_to_timestamp(col, 'M/d/yyyy H:mm')`; format tokens differ |
| Strict casting | Lenient by default | Serverless runs in ANSI mode, so bad values error unless `try_cast` is used |
| Conditional expression | `IFF(cond, a, b)` | `CASE WHEN cond THEN a ELSE b END` (works on both) |
| Median | `MEDIAN(x)` | `percentile_cont(0.5) WITHIN GROUP (ORDER BY x)` (works on both) |
| Filtering on window results | `QUALIFY profit_rank <= 3` | A CTE plus `WHERE profit_rank <= 3` (works on both) |
| Date spine | `TABLE(GENERATOR(ROWCOUNT => 5000))` with `DATEADD(day, SEQ4(), start)` | `explode(sequence(start, end, INTERVAL 1 DAY))` |
| Day and month names | `DAYNAME()`, `MONTHNAME()` | `date_format(d, 'EEE')`, `date_format(d, 'MMM')` |
| Type inference from CSV | `INFER_SCHEMA` guessed types, dates stayed text | Everything read as text in bronze, typed in silver |
| Time travel | `BEFORE(STATEMENT => query_id)` | `VERSION AS OF n`, plus `DESCRIBE HISTORY` |
| Undo a bad change | `CREATE TABLE ... CLONE ... BEFORE(...)` | `RESTORE TABLE ... TO VERSION AS OF n` |
| Table type created by dbt | Transient by default, so clones must be transient too | Not applicable (Delta tables) |
| File encoding | `ENCODING = 'ISO-8859-1'` on the file format | `.option("encoding", "ISO-8859-1")` on the CSV reader |
| Outbound internet (free tiers) | Normal | Free Edition blocks it, so the bridge between platforms uses a Parquet file |
