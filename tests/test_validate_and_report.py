import openpyxl
import pandas as pd
import pytest

import validate_and_report as vr


@pytest.fixture
def clean_df():
    """Small, valid fact table: every validation should pass."""
    df = pd.DataFrame({
        "order_item_key": ["a", "b", "c", "d"],
        "order_id": [1, 1, 2, 3],
        "order_date": pd.to_datetime(["2017-01-05", "2017-01-20", "2017-02-03", "2017-03-09"]),
        "market": ["Europe", "Europe", "LATAM", "USCA"],
        "shipping_mode": ["Standard Class", "First Class", "Standard Class", "Same Day"],
        "is_late": [1, 0, 1, 0],
        "sales": [100.0, 50.0, 80.0, 20.0],
        "profit": [10.0, 5.0, -3.0, 4.0],
        "discount_rate": [0.0, 0.05, 0.1, 0.25],
        "category_name": ["Fishing", "Fishing", "Cleats", "Cleats"],
    })
    return vr.prepare(df)


def issues(df):
    return {name: int(mask.sum()) for name, mask in vr.build_masks(df)}


def test_aliases_are_resolved():
    raw = pd.DataFrame({
        "Order Item Id": [1], "Market": ["EU"], "Shipping Mode": ["x"],
        "Late_Delivery_Risk": [1], "Sales": [10.0], "Order Profit Per Order": [2.0],
    })
    df, mapping = vr.resolve_columns(raw)
    assert mapping["order_item_key"] == "order_item_id"
    assert mapping["is_late"] == "late_delivery_risk"
    assert mapping["profit"] == "order_profit_per_order"
    assert all(c in df.columns for c in vr.REQUIRED)


def test_boolean_is_late_becomes_integer(clean_df):
    df = clean_df.copy()
    df["is_late"] = [True, False, True, False]
    out = vr.prepare(df)
    assert out["is_late"].tolist() == [1, 0, 1, 0]


def test_clean_data_has_no_issues(clean_df):
    assert sum(issues(clean_df).values()) == 0


def test_detects_duplicate_grain(clean_df):
    clean_df.loc[1, "order_item_key"] = "a"
    assert issues(clean_df)["Duplicate order_item_key (grain)"] == 1


def test_detects_negative_sales(clean_df):
    clean_df.loc[0, "sales"] = -5.0
    assert issues(clean_df)["Negative sales"] == 1


def test_null_market_is_flagged_and_kept(clean_df):
    clean_df.loc[2, "market"] = None
    df = vr.prepare(clean_df)
    assert issues(df)["Unknown market (null)"] == 1
    assert (df["market"] == "(Unknown)").sum() == 1


def test_discount_outside_range(clean_df):
    clean_df.loc[3, "discount_rate"] = 25  # percent stored as 0-100
    assert issues(clean_df)["discount_rate outside 0-1"] == 1


def test_report_totals_reconcile_with_rows(clean_df, tmp_path):
    out = tmp_path / "report.xlsx"
    vr.build_report(clean_df, vr.build_masks(clean_df), out, "test")
    wb = openpyxl.load_workbook(out)
    assert {"Summary", "By market", "By shipping mode", "Data quality"} <= set(wb.sheetnames)
    ws = wb["By market"]
    items = sum(ws.cell(r, 2).value for r in range(2, 2 + clean_df["market"].nunique()))
    assert items == len(clean_df)
    assert ws.cell(2 + clean_df["market"].nunique(), 2).value.startswith("=SUM(")


def test_demo_defects_are_detected():
    df = vr.prepare(vr.make_demo(2000))
    found = issues(df)
    assert found["Duplicate order_item_key (grain)"] >= 1
    assert found["Negative sales"] >= 1


def test_exit_codes(tmp_path):
    out = str(tmp_path / "demo.xlsx")
    assert vr.main(["--demo", "--output", out]) == vr.EXIT_OK
    assert vr.main(["--demo", "--output", out, "--fail-on-issues"]) == vr.EXIT_ISSUES
    assert vr.main(["--input", str(tmp_path / "missing.csv")]) == vr.EXIT_BAD_INPUT