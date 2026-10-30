# Snowflake + Databricks Lakehouse: Supply Chain Analytics

The same supply chain dataset, modeled as a star schema on **Snowflake (SQL + dbt)** and on **Databricks (PySpark + Delta Lake)**, connected by a hand-off between the two platforms and reconciled row by row.

I built this to learn both platforms side by side, using only free tiers, and to practice SQL on realistic operations and finance questions.

## Business questions answered

- Which product categories earn the most profit in each market?
- How does profit change month to month?
- Which shipping modes deliver late most often, and by how much?
- Do bigger discounts lead to more loss-making order items?
- Can the data be trusted? (data quality checks)

One result stands out: **First Class shipping is late on 95.3% of items**, while Standard Class is late on 38.1%. The most expensive option performs worst on punctuality.

## Architecture

```mermaid
flowchart LR
    CSV["DataCo CSV<br/>(Kaggle)"] --> SFRAW[("Snowflake<br/>RAW")]
    CSV --> BRONZE[("Databricks<br/>Bronze")]

    subgraph Snowflake
        SFRAW --> STG["STAGING<br/>dbt view"]
        STG --> MARTS["MARTS<br/>dbt star schema"]
    end

    subgraph Databricks
        BRONZE --> SILVER[("Silver<br/>typed and cleaned")]
        SILVER --> GOLD[("Gold<br/>star schema")]
    end

    GOLD -- "Parquet file" --> BRIDGE[("Snowflake<br/>BRIDGE")]
    BRIDGE <-->|"reconcile"| MARTS
```

## Dataset

[DataCo Smart Supply Chain for Big Data Analysis](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis) (Kaggle): about 180,000 order items with 53 columns covering customers, products, shipping, delivery status, sales, discounts, and profit. Originally published on Mendeley Data. The data is not included in this repo, so download it from Kaggle.

Notes on handling it:
- The CSV is encoded in ISO-8859-1, not UTF-8, which needed an explicit encoding setting on both platforms.
- Customer email, customer password, and product image columns are dropped in the staging layer.

## Stack

| Layer | Tools |
|---|---|
| Warehouse | Snowflake (trial) |
| Transformation | dbt Core 1.12 with the Snowflake adapter |
| Lakehouse | Databricks Free Edition: serverless compute, Unity Catalog, Delta Lake |
| Visualization | Tableau Desktop (free edition), connected to the Databricks gold tables |
| Languages | SQL (Snowflake and Spark SQL), Python / PySpark |
| Tooling | Git and GitHub, VS Code, SQLFluff |

## Repository layout

```
databricks/        Notebooks: bronze, silver, gold, Delta demos, export, SQL analysis
dbt_project/       dbt models (staging, marts), tests, macros
snowflake/         Setup, load, feature demos, bridge scripts (run in numeric order)
sql/analysis/      Five business-question queries for Snowflake
docs/              Dialect differences doc and screenshots
requirements.txt   Python packages
```

## Snowflake and dbt

- **Load:** CSV to an internal stage, then `COPY INTO` a raw table, with the schema inferred from the file header (`snowflake/01` to `03`).
- **Staging (dbt):** one model that renames the 53 columns to snake_case, drops sensitive columns, converts the date columns to timestamps, and casts money columns to `NUMBER(18,2)`.
- **Marts (dbt):** star schema with `fct_order_items` (one row per order item) and the dimensions `dim_customer`, `dim_product`, `dim_geography`, `dim_shipping_mode`, and `dim_date`.
- **Tests:** 22 dbt data tests (unique, not null, and relationships from the fact table to every dimension), all passing.
- **Authentication:** key pair authentication for dbt instead of a password.

![dbt lineage graph](docs/images/dbt_lineage.jpeg)

## Databricks: medallion architecture and Delta Lake

| Layer | Notebook | What it does |
|---|---|---|
| Bronze | [`01_bronze_load`](databricks/01_bronze_load.ipynb) | Raw CSV loaded as Delta, all text, columns renamed to snake_case |
| Silver | [`02_silver_clean`](databricks/02_silver_clean.ipynb) | Typed columns (`try_cast`, `try_to_timestamp`), sensitive columns dropped |
| Gold | [`03_gold_star_schema`](databricks/03_gold_star_schema.ipynb) | The same star schema as the dbt marts, with identical column names and `md5` keys |
| Delta demos | [`04_delta_lake_demo`](databricks/04_delta_lake_demo.ipynb) | Time travel and `RESTORE`, `MERGE`, `OPTIMIZE` |

Delta time travel on a copy of the fact table: damage it on purpose, then restore it.

![Delta time travel](docs/images/delta_time_travel.png)

`MERGE` updating 3 rows and inserting 2 in one statement:

![Delta MERGE](docs/images/delta_merge.png)

## SQL analysis

Five queries in [`sql/analysis/`](sql/analysis), each with a header describing the business question and the SQL skills it shows. The same analysis runs on Databricks in [`06_sql_analysis`](databricks/06_sql_analysis.ipynb).

| Query | Skills shown |
|---|---|
| [`01_top_categories_per_market`](sql/analysis/01_top_categories_per_market.sql) | Multi-table joins, `RANK()`, `QUALIFY` |
| [`02_monthly_profit_trend`](sql/analysis/02_monthly_profit_trend.sql) | CTEs, `LAG()`, moving average window frame |
| [`03_delivery_performance`](sql/analysis/03_delivery_performance.sql) | Conditional aggregation, percentiles |
| [`04_loss_making_items_by_discount`](sql/analysis/04_loss_making_items_by_discount.sql) | CTEs, `CASE` bucketing |
| [`05_data_quality_checks`](sql/analysis/05_data_quality_checks.sql) | `UNION ALL` validation checks, anti-join |

Delivery performance by shipping mode on both platforms:

| Snowflake | Databricks |
|---|---|
| ![Snowflake delivery performance](docs/images/snowflake_delivery_performance.png) | ![Databricks delivery performance](docs/images/databricks_delivery_performance.png) |

See [`docs/dialect_differences.md`](docs/dialect_differences.md) for the syntax differences I ran into (`IFF` vs `CASE`, `QUALIFY`, date parsing, time travel, and more).

## Tableau dashboard

![Supply Chain Performance dashboard](docs/images/tableau_dashboard.png)

A one-page dashboard on the same star schema. Tableau connects to the Databricks gold tables through the Databricks connector (ODBC driver, personal access token) and works from an extract, so it doesn't depend on the warehouse being awake.

**The totals match the other two platforms:** 180,519 order items, 3,966,903 profit and 36,784,734 sales.

### What it shows

| View | Result |
|---|---|
| Late % by shipping mode | First Class 95.3%, Second Class 76.6%, Same Day 45.7%, Standard Class 38.1%, against a global average of 54.8% |
| Loss % by discount band | 18.6%, 18.6% and 18.9%: about one item in five loses money at every discount level, so discounts do not explain the losses |
| Profit by market | Europe 29.48% and LATAM 28.32% of total profit; Pacific Asia 21.62%, USCA 14.23%, Africa 6.35% |
| Profit by month | Monthly profit with a 3-month moving average |

The sharp drop at the end of the monthly series should be read with care: it may simply be the end of the data, and I confirm it against order counts before attributing it to anything.

### Tableau techniques used

| Technique | Where |
|---|---|
| Relationships on the star schema | One fact table related to five dimensions on the `*_key` fields, so measures are not duplicated |
| Parameter and calculated field | A `Metric` parameter feeds `Selected Metric` (`CASE`), so the market chart switches between profit, sales and items, with a dynamic title |
| `FIXED` LOD expression | `Overall Late %` drives the reference line; the year filter is added to context so the LOD respects it |
| Table calculations | Percent of total in the market labels; 3-month moving average on monthly profit |
| Color with purpose | One highlight color for First Class, gray for the rest |
| Dashboard action | Clicking a market filters the other views |
| Extract | A local copy of the data, instead of a live connection |

### Notes

- The workbook is not published: Tableau Desktop Free Edition cannot save to Tableau Public, and the Public edition accepts a limited set of data sources.
- The data and the workbook file are not in this repo; the screenshot is the evidence.

## Snowflake features

Script: [`snowflake/04_features_demo.sql`](snowflake/04_features_demo.sql)

**Zero-copy clone and time travel.** A clone of the fact table is damaged on purpose, then restored from the moment before the damage. The restored table matches the original exactly. dbt builds transient tables, so the clones had to be transient as well.

![Snowflake time travel](docs/images/time_travel.png)

**Role-based access.** A read-only `analyst_role` can query the marts but is blocked from the raw data and from writes. The test needs `USE SECONDARY ROLES NONE`, otherwise privileges from the user's other roles still apply and the test proves nothing.

| Allowed | Blocked on raw data | Blocked on write |
|---|---|---|
| ![Analyst select](docs/images/analyst_select_ok.png) | ![Analyst raw blocked](docs/images/analyst_raw_blocked.png) | ![Analyst update blocked](docs/images/analyst_update_blocked.png) |

**Streams and tasks.** A stream on a cloned table tracks newly added rows, and a task consumes them incrementally, so the same rows are never processed twice. Script: [`snowflake/05_streams_tasks_demo.sql`](snowflake/05_streams_tasks_demo.sql).

![Streams and tasks](docs/images/streams_tasks.png)

## Bridge: Snowflake and Databricks together

Databricks Free Edition blocks outbound internet access, so a live connection to Snowflake isn't possible. The hand-off is a file instead, which is a common real-world pattern:

1. Databricks writes the gold fact table as a single Parquet file ([`05_export_for_snowflake`](databricks/05_export_for_snowflake.ipynb)).
2. The file is downloaded and uploaded to a Snowflake stage.
3. `COPY INTO` loads it into `dataco.bridge.fct_order_items_dbx` ([`snowflake/06_load_from_databricks.sql`](snowflake/06_load_from_databricks.sql)).
4. The table is reconciled against the dbt-built fact table.

| Check | Snowflake (dbt) | Databricks (via bridge) |
|---|---|---|
| Rows | 180,519 | 180,519 |
| Total profit | 3,966,902.97 | 3,966,902.97 |
| Total sales | 36,784,734.31 | 36,784,734.31 |
| Row-by-row mismatches | 0 | |

**The first reconciliation found a discrepancy.** Total sales differed by 0.70 (36,784,735.01 vs 36,784,734.31) while rows and profit matched.

![Reconciliation before the fix](docs/images/bridge_reconciliation.png)

The cause was decimal precision: Databricks stored money as exact cents (`decimal(18,2)`), while Snowflake kept the extra decimals inferred from the CSV. Casting the money columns to `NUMBER(18,2)` in the dbt staging model fixed it.

![Reconciliation after the fix](docs/images/bridge_reconciliation_after_fix.png)

![Row-by-row mismatch check](docs/images/bridge_mismatches.png)

## Snowflake vs Databricks: what I observed

Observations from this project on a small dataset and free tiers, not a benchmark. With 180K rows, timing differences are not meaningful.

| Topic | Snowflake | Databricks |
|---|---|---|
| Getting started | SQL-first, and the web editor was enough to build the whole warehouse | Notebook-first, with Python and SQL side by side |
| Transformation | dbt models with tests and lineage | PySpark and Spark SQL in notebooks |
| Undo / history | Time travel with `BEFORE(STATEMENT => ...)`, plus clones | `DESCRIBE HISTORY`, `VERSION AS OF`, `RESTORE TABLE` |
| Incremental loading | Streams and tasks | `MERGE` into Delta tables |
| Strictness | Lenient type conversion | ANSI mode on serverless, so `try_cast` was needed |
| Governance | Roles and grants | Unity Catalog catalogs, schemas, and volumes |

Both platforms produced identical results from the same logic, which is the main takeaway: the modeling matters more than the engine.

## Python validation and Excel report

`python/validate_and_report.py` validates the flattened gold fact table (grain
duplicates, nulls, value ranges, profit/sales anomalies) and builds a 9-sheet Excel
report with pandas and openpyxl:

- KPI summary with live cross-sheet formulas and automatic key findings
- Market and shipping-mode analysis (margin, late %, loss %, profit rank)
- Market x shipping-mode late-rate heatmap
- Monthly trend with month-over-month change and a 3-month moving average
- Discount-band loss analysis
- Data quality checks and an exceptions list

Totals, ratios, ranks and moving averages are Excel formulas, so the report can be
audited and recalculated in Excel. I first tested the checks on synthetic data with
injected defects (duplicate key, null market, negative sales) before running it on the
real data.

The fact table is joined to its dimensions in Databricks (LEFT JOINs, row count
verified at 180,519 before and after) and exported to CSV.

```bash
pip install -r requirements.txt
python python/validate_and_report.py --input data/fact_order_items_flat.csv \
    --output reports/supply_chain_report.xlsx
```

Sample outputs: [`reports/supply_chain_report.xlsx`](reports/supply_chain_report.xlsx)
(real data) and [`reports/demo_report.xlsx`](reports/demo_report.xlsx) (synthetic data with
injected defects, used to test the validations). Open in Excel or Google Sheets.

![Excel summary](docs/images/excel_summary.png)
![Excel by market](docs/images/excel_by_market.png)
![Late rate heatmap](docs/images/excel_late_heatmap.png)
![Monthly trend](docs/images/excel_monthly_trend.png)

## Lessons learned

- **Type inference differs between platforms.** I now enforce explicit types instead of trusting inference.
- **Check file encodings early.** The CSV needed ISO-8859-1 on both platforms.
- **dbt creates transient tables in Snowflake by default**, and clones of them must be transient too.
- **Test access control with secondary roles off**, or the test can pass for the wrong reason.
- **Prefer key pair authentication** over passwords for tools like dbt.
- **Reconcile across platforms instead of assuming they agree.** Doing so exposed a precision gap I would not have noticed.
- **Dashboards on a warehouse need an extract.** The sign-in token expired mid-session, so I used a personal access token and an extract.
- **A `FIXED` LOD ignores ordinary dimension filters.** Add the filter to context so the calculation respects it.
- **Check the edition before planning to publish.** Tableau Desktop Free Edition cannot save to Tableau Public.

## Limitations and next steps

- Small dataset and free tiers, so no performance conclusions.
- The bridge is a manual file hand-off. In production I would use a native connector or a shared open table format such as Apache Iceberg (not tested here), with an orchestrator.
- No scheduled pipeline or CI yet. A GitHub Action that lints the SQL is a planned next step.
- The Tableau dashboard is a screenshot, not a live link, and it uses an extract from Databricks.

## How to reproduce

1. Download the dataset from Kaggle (link above).
2. Create a Python virtual environment and run `pip install -r requirements.txt`.
3. Snowflake: run `snowflake/01` to `03` in order, upload the CSV to the stage as described in the scripts, then configure dbt (a `profiles.yml` with key pair authentication, kept outside the repo) and run `dbt build` inside `dbt_project/`.
4. Databricks: upload the CSV to a Unity Catalog volume and run notebooks `01` to `04`.
5. Bridge: run `05_export_for_snowflake`, upload the Parquet file to the Snowflake stage, then run `snowflake/06_load_from_databricks.sql`.
6. Tableau: connect to a Databricks SQL warehouse (server hostname, HTTP path and a personal access token), choose catalog `workspace` and schema `gold`, relate `fct_order_items` to the five dimensions on the `*_key` fields, and create an extract.

No credentials are stored in this repo.

## Author

Leopoldo Lugo ([@PoloLugoR](https://github.com/PoloLugoR))