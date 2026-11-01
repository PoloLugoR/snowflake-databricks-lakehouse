"""Validate the DataCo order-items data and build a multi-sheet Excel report.

Examples
--------
    # 1) See which columns your file has (and how they are matched)
    python python/validate_and_report.py --input data/fact_order_items.parquet --show-columns

    # 2) Build the report from your data (.parquet or .csv)
    python python/validate_and_report.py --input data/fact_order_items.parquet \
        --output reports/supply_chain_report.xlsx

    # 3) Try it with synthetic data (no input file needed)
    python python/validate_and_report.py --demo --output reports/demo_report.xlsx

Required columns (matched case-insensitively, with common aliases):
    order_item_key, market, shipping_mode, is_late, sales, profit
Optional columns (extra sheets appear when they exist):
    order_id, order_date, discount_rate, category_name

Sheets: Summary, By market, By shipping mode, Market x Shipping, Monthly trend,
Discount bands, Top categories, Data quality, Exceptions.
Totals, ratios, ranks, moving averages and cross-sheet KPIs are live Excel formulas.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import (CellIsRule, ColorScaleRule, DataBarRule,
                                      FormulaRule, IconSetRule)
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# --------------------------------------------------------------------------
# Column matching
# --------------------------------------------------------------------------
ALIASES = {
    "order_item_key": ["order_item_key", "order_item_id", "order_item_sk"],
    "order_id": ["order_id"],
    "order_date": ["order_date", "order_date_dateorders", "order_datetime", "date"],
    "market": ["market"],
    "shipping_mode": ["shipping_mode"],
    "is_late": ["is_late", "late_delivery_risk", "late_risk", "late_flag"],
    "sales": ["sales", "order_item_total"],
    "profit": ["profit", "order_profit_per_order", "benefit_per_order"],
    "discount_rate": ["discount_rate", "order_item_discount_rate"],
    "category_name": ["category_name", "category"],
}
REQUIRED = ["order_item_key", "market", "shipping_mode", "is_late", "sales", "profit"]

log = logging.getLogger("validate_and_report")
EXIT_OK, EXIT_ISSUES, EXIT_BAD_INPUT = 0, 1, 2

NAVY = "1F3864"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF")
GREEN, YELLOW, RED = "63BE7B", "FFEB84", "F8696B"



def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def read_raw(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="ISO-8859-1")
    sys.exit(f"Unsupported file type: {path.suffix} (use .parquet or .csv)")


def resolve_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    df.columns = [norm(c) for c in df.columns]
    mapping, rename = {}, {}
    for canon, options in ALIASES.items():
        for opt in options:
            if opt in df.columns:
                mapping[canon] = opt
                if opt != canon:
                    rename[opt] = canon
                break
    df = df.rename(columns=rename)
    return df, mapping


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    s = df["is_late"]
    if s.dtype == bool:
        df["is_late"] = s.astype(int)
    else:
        df["is_late"] = pd.to_numeric(
            s.replace({"true": 1, "false": 0, "True": 1, "False": 0}), errors="coerce")
    for c in ("sales", "profit", "discount_rate"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    for c in ("market", "shipping_mode", "category_name"):
        if c in df.columns:
            df[c] = df[c].astype("object").where(df[c].notna(), "(Unknown)")
    return df



# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def build_masks(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    masks = [
        ("Duplicate order_item_key (grain)", df["order_item_key"].duplicated(keep="first")),
        ("Null order_item_key", df["order_item_key"].isna()),
        ("Unknown market (null)", df["market"].eq("(Unknown)")),
        ("Unknown shipping_mode (null)", df["shipping_mode"].eq("(Unknown)")),
        ("Null or non-numeric sales", df["sales"].isna()),
        ("Null or non-numeric profit", df["profit"].isna()),
        ("Negative sales", df["sales"] < 0),
        ("Profit greater than sales", df["profit"] > df["sales"]),
        ("is_late not in (0, 1)", ~df["is_late"].isin([0, 1])),
    ]
    if "order_date" in df.columns:
        masks.append(("Null or invalid order_date", df["order_date"].isna()))
    if "discount_rate" in df.columns:
        masks.append(("discount_rate outside 0-1",
                      (df["discount_rate"] < 0) | (df["discount_rate"] > 1)))
    return masks



# --------------------------------------------------------------------------
# Excel helpers
# --------------------------------------------------------------------------
def style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def set_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def new_chart(kind: str, title: str, ytitle: str, pct: bool = False):
    ch = BarChart() if kind == "bar" else LineChart()
    if kind == "bar":
        ch.type = "col"
    ch.title, ch.height, ch.width = title, 8.5, 17
    ch.y_axis.title = ytitle
    ch.y_axis.number_format = "0%" if pct else "#,##0"
    ch.x_axis.delete = False        # make axes visible in Excel
    ch.y_axis.delete = False
    return ch


def metric_sheet(wb: Workbook, title: str, g: pd.DataFrame, key_label: str,
                 note: str | None = None, late_chart: bool = True):
    """One row per group with live formulas. Returns (last_row, total_row)."""
    ws = wb.create_sheet(title)
    headers = [key_label, "Items", "Sales", "Profit", "Late items", "Loss items",
               "Margin %", "Late %", "Loss %", "Profit share", "Profit rank"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    style_header(ws, 1, len(headers))
    n = len(g)
    last, total = n + 1, n + 2
    for i, r in enumerate(g.itertuples(index=False), start=2):
        ws.cell(i, 1, str(r[0]))
        ws.cell(i, 2, int(r.items))
        ws.cell(i, 3, round(float(r.sales), 2))
        ws.cell(i, 4, round(float(r.profit), 2))
        ws.cell(i, 5, int(r.late_items))
        ws.cell(i, 6, int(r.loss_items))
        ws.cell(i, 7, f"=IF(C{i}=0,0,D{i}/C{i})")
        ws.cell(i, 8, f"=IF(B{i}=0,0,E{i}/B{i})")
        ws.cell(i, 9, f"=IF(B{i}=0,0,F{i}/B{i})")
        ws.cell(i, 10, f"=IF(D${total}=0,0,D{i}/D${total})")
        ws.cell(i, 11, f"=RANK(D{i},$D$2:$D${last})")
    ws.cell(total, 1, "Total" if note is None else "Total (rows shown)")
    for col in "BCDEF":
        ws[f"{col}{total}"] = f"=SUM({col}2:{col}{last})"
    ws[f"G{total}"] = f"=IF(C{total}=0,0,D{total}/C{total})"
    ws[f"H{total}"] = f"=IF(B{total}=0,0,E{total}/B{total})"
    ws[f"I{total}"] = f"=IF(B{total}=0,0,F{total}/B{total})"
    ws[f"J{total}"] = f"=SUM(J2:J{last})"
    for c in range(1, 12):
        ws.cell(total, c).font = Font(bold=True)
    for r in range(2, total + 1):
        ws[f"B{r}"].number_format = "#,##0"
        ws[f"C{r}"].number_format = "#,##0.00"
        ws[f"D{r}"].number_format = "#,##0.00"
        ws[f"E{r}"].number_format = "#,##0"
        ws[f"F{r}"].number_format = "#,##0"
        for col in "GHIJ":
            ws[f"{col}{r}"].number_format = "0.0%"
    rng = f"A2:K{last}"
    ws.conditional_formatting.add(
        rng, FormulaRule(formula=["$K2=1"], fill=PatternFill("solid", bgColor="E2EFDA")))
    ws.conditional_formatting.add(
        f"D2:D{last}", CellIsRule(operator="lessThan", formula=["0"],
                                  font=Font(color="C00000", bold=True)))
    ws.conditional_formatting.add(f"C2:C{last}", DataBarRule(
        start_type="min", end_type="max", color="5B9BD5"))
    ws.conditional_formatting.add(f"H2:H{last}", ColorScaleRule(
        start_type="min", start_color=GREEN, mid_type="percentile", mid_value=50,
        mid_color=YELLOW, end_type="max", end_color=RED))
    ws.conditional_formatting.add(f"G2:G{last}", ColorScaleRule(
        start_type="min", start_color=RED, mid_type="percentile", mid_value=50,
        mid_color=YELLOW, end_type="max", end_color=GREEN))
    ws.conditional_formatting.add(f"I2:I{last}", DataBarRule(
        start_type="num", start_value=0, end_type="max", color="F4B183"))
    set_widths(ws, [24, 11, 16, 16, 11, 11, 10, 9, 9, 12, 11])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:K{last}"
    ch = new_chart("bar", f"Profit by {key_label.lower()}", "Profit")
    ch.add_data(Reference(ws, min_col=4, min_row=1, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
    ch.legend = None
    ws.add_chart(ch, "M2")
    if late_chart:
        ch2 = new_chart("bar", f"Late % by {key_label.lower()}", "Late %", pct=True)
        ch2.add_data(Reference(ws, min_col=8, min_row=1, max_row=last), titles_from_data=True)
        ch2.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
        ch2.legend = None
        ws.add_chart(ch2, "M20")
    if note:
        ws.cell(total + 2, 1, note).font = Font(italic=True, color="595959")
    return last, total



def matrix_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    ws = wb.create_sheet("Market x Shipping")
    markets = sorted(df["market"].unique())
    modes = sorted(df["shipping_mode"].unique())
    ncol = len(modes) + 2
    last_col = get_column_letter(len(modes) + 1)

    def pivot(values, agg):
        return pd.pivot_table(df, index="market", columns="shipping_mode", values=values,
                              aggfunc=agg, fill_value=0).reindex(index=markets, columns=modes, fill_value=0)

    def put_block(row0, title, data, fmt):
        ws.cell(row0, 1, title).font = Font(bold=True, size=12)
        hdr = row0 + 1
        ws.cell(hdr, 1, "Market")
        for j, m in enumerate(modes, start=2):
            ws.cell(hdr, j, m)
        ws.cell(hdr, ncol, "Total")
        style_header(ws, hdr, ncol)
        for i, mk in enumerate(markets):
            r = hdr + 1 + i
            ws.cell(r, 1, mk)
            for j, m in enumerate(modes, start=2):
                ws.cell(r, j, float(data.loc[mk, m]))
            ws.cell(r, ncol, f"=SUM(B{r}:{last_col}{r})")
        tr = hdr + 1 + len(markets)
        ws.cell(tr, 1, "Total").font = Font(bold=True)
        for j in range(2, ncol + 1):
            col = get_column_letter(j)
            ws.cell(tr, j, f"=SUM({col}{hdr + 1}:{col}{tr - 1})").font = Font(bold=True)
        for r in range(hdr + 1, tr + 1):
            for j in range(2, ncol + 1):
                ws.cell(r, j).number_format = fmt
        return hdr + 1, tr

    r0 = 1
    items_first, items_tr = put_block(r0, "Items", pivot("order_item_key", "count"), "#,##0")
    r0 = items_tr + 2
    late_first, late_tr = put_block(r0, "Late items", pivot("is_late", "sum"), "#,##0")
    r0 = late_tr + 2
    ws.cell(r0, 1, "Late % (live formula = late items / items)").font = Font(bold=True, size=12)
    hdr = r0 + 1
    ws.cell(hdr, 1, "Market")
    for j, m in enumerate(modes, start=2):
        ws.cell(hdr, j, m)
    ws.cell(hdr, ncol, "Total")
    style_header(ws, hdr, ncol)
    for k in range(len(markets) + 1):
        r = hdr + 1 + k
        ws.cell(r, 1, markets[k] if k < len(markets) else "Total")
        for j in range(2, ncol + 1):
            col = get_column_letter(j)
            ws.cell(r, j, f"=IF({col}{items_first + k}=0,0,{col}{late_first + k}/{col}{items_first + k})")
            ws.cell(r, j).number_format = "0.0%"
    ws.conditional_formatting.add(
        f"B{hdr + 1}:{last_col}{hdr + len(markets)}", ColorScaleRule(
            start_type="min", start_color=GREEN, mid_type="percentile", mid_value=50,
            mid_color=YELLOW, end_type="max", end_color=RED))
    r0 = hdr + len(markets) + 3
    p_first, p_tr = put_block(r0, "Profit", pivot("profit", "sum"), "#,##0")
    ws.conditional_formatting.add(
        f"B{p_first}:{last_col}{p_tr - 1}", ColorScaleRule(
            start_type="min", start_color=RED, mid_type="percentile", mid_value=50,
            mid_color=YELLOW, end_type="max", end_color=GREEN))
    set_widths(ws, [20] + [15] * (len(modes) + 1))



def monthly_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    d = df.dropna(subset=["order_date"]).copy()
    d["month"] = d["order_date"].dt.to_period("M").dt.to_timestamp()
    g = d.groupby("month").agg(
        items=("order_item_key", "count"), sales=("sales", "sum"),
        profit=("profit", "sum"), late=("is_late", "sum")).reset_index()
    ws = wb.create_sheet("Monthly trend")
    headers = ["Month", "Items", "Sales", "Profit", "Late items", "Margin %", "Late %",
               "Profit MoM %", "Profit 3-mo avg"]
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h)
    style_header(ws, 1, len(headers))
    for i, r in enumerate(g.itertuples(index=False), start=2):
        ws.cell(i, 1, r.month.to_pydatetime()).number_format = "yyyy-mm"
        ws.cell(i, 2, int(r.items)).number_format = "#,##0"
        ws.cell(i, 3, round(float(r.sales), 2)).number_format = "#,##0.00"
        ws.cell(i, 4, round(float(r.profit), 2)).number_format = "#,##0.00"
        ws.cell(i, 5, int(r.late)).number_format = "#,##0"
        ws.cell(i, 6, f"=IF(C{i}=0,0,D{i}/C{i})").number_format = "0.0%"
        ws.cell(i, 7, f"=IF(B{i}=0,0,E{i}/B{i})").number_format = "0.0%"
        ws.cell(i, 8, "" if i == 2 else f'=IF(D{i - 1}=0,"",D{i}/D{i - 1}-1)').number_format = "0.0%"
        ws.cell(i, 9, "" if i < 4 else f"=AVERAGE(D{i - 2}:D{i})").number_format = "#,##0"
    last = len(g) + 1
    ws.conditional_formatting.add(f"H3:H{last}", IconSetRule(
        "3Arrows", "num", [-1, -0.0001, 0.0001], showValue=True))
    ws.conditional_formatting.add(f"D2:D{last}", DataBarRule(
        start_type="min", end_type="max", color="70AD47"))
    set_widths(ws, [11, 10, 16, 16, 11, 10, 9, 13, 16])
    ws.freeze_panes = "B2"
    ch = new_chart("line", "Monthly profit and 3-month average", "Profit")
    ch.add_data(Reference(ws, min_col=4, min_row=1, max_row=last), titles_from_data=True)
    ch.add_data(Reference(ws, min_col=9, min_row=1, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
    ws.add_chart(ch, "K2")


def add_group_agg(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by).agg(
        items=("order_item_key", "count"), sales=("sales", "sum"),
        profit=("profit", "sum"), late_items=("is_late", "sum"),
        loss_items=("profit", lambda s: int((s < 0).sum()))).reset_index()
    return g


def quality_sheets(wb: Workbook, df: pd.DataFrame, masks) -> int:
    ws = wb.create_sheet("Data quality")
    for c, h in enumerate(["Check", "Issues", "Status", "% of rows"], start=1):
        ws.cell(1, c, h)
    style_header(ws, 1, 4)
    n = len(df)
    for i, (name, m) in enumerate(masks, start=2):
        ws.cell(i, 1, name)
        ws.cell(i, 2, int(m.sum())).number_format = "#,##0"
        ws.cell(i, 3, f'=IF(B{i}=0,"OK","REVIEW")')
        ws.cell(i, 4, f"=B{i}/$B${len(masks) + 3}").number_format = "0.000%"
    last = len(masks) + 1
    ws.cell(last + 2, 1, "Rows validated").font = Font(bold=True)
    ws.cell(last + 2, 2, n).number_format = "#,##0"
    ws.conditional_formatting.add(f"C2:C{last}", CellIsRule(
        operator="equal", formula=['"OK"'], fill=PatternFill("solid", bgColor="C6EFCE")))
    ws.conditional_formatting.add(f"C2:C{last}", CellIsRule(
        operator="equal", formula=['"REVIEW"'], fill=PatternFill("solid", bgColor="FFC7CE")))
    set_widths(ws, [38, 12, 12, 12])
    # Exceptions: first rows that break any rule
    ex = wb.create_sheet("Exceptions")
    cols = [c for c in ["order_item_key", "market", "shipping_mode", "sales", "profit",
                        "discount_rate", "order_date"] if c in df.columns]
    parts = []
    for name, m in masks:
        if m.any():
            part = df.loc[m, cols].copy()
            part.insert(1, "reason", name)
            parts.append(part)
    if parts:
        out = pd.concat(parts).head(1000)
        ex.append(list(out.columns))
        style_header(ex, 1, len(out.columns))
        for row in out.itertuples(index=False):
            ex.append([None if pd.isna(v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v)
                       for v in row])
        set_widths(ex, [22, 34, 16, 16, 12, 12, 14, 14][:len(out.columns)])
        ex.freeze_panes = "A2"
        ex.auto_filter.ref = ex.dimensions
        ex.cell(1, len(out.columns) + 2, "Showing the first 1,000 exceptions").font = Font(italic=True)
    else:
        ex["A1"] = "No exceptions found."
    return last



def summary_sheet(ws, df, masks, source, mk_total, sm_total, q_last, findings):
    ws.title = "Summary"
    ws["A1"] = "Supply chain report"
    ws["A1"].font = Font(size=18, bold=True, color=NAVY)
    ws["A2"] = f"Source: {source}  |  Generated: {datetime.now():%Y-%m-%d %H:%M}"
    ws["A2"].font = Font(italic=True, color="595959")
    kpis = [
        ("Order items", f"='By market'!B{mk_total}", "#,##0"),
        ("Total sales", f"='By market'!C{mk_total}", "#,##0.00"),
        ("Total profit", f"='By market'!D{mk_total}", "#,##0.00"),
        ("Profit margin", f"='By market'!G{mk_total}", "0.0%"),
        ("Late delivery %", f"='By shipping mode'!H{sm_total}", "0.0%"),
        ("Loss-making items %", f"='By market'!I{mk_total}", "0.0%"),
        ("Data quality", f'=IF(COUNTIF(\'Data quality\'!C2:C{q_last},"REVIEW")=0,'
                         f'"All checks passed",COUNTIF(\'Data quality\'!C2:C{q_last},"REVIEW")&" check(s) to review")', "@"),
    ]
    ws["A4"], ws["B4"] = "KPI", "Value"
    style_header(ws, 4, 2)
    for i, (label, formula, fmt) in enumerate(kpis, start=5):
        ws.cell(i, 1, label).font = Font(bold=True)
        c = ws.cell(i, 2, formula)
        c.number_format = fmt
        c.alignment = Alignment(horizontal="right")
    qrow = 5 + len(kpis) - 1
    ws.conditional_formatting.add(f"B{qrow}", FormulaRule(
        formula=[f'LEFT($B${qrow},3)="All"'], fill=PatternFill("solid", bgColor="C6EFCE")))
    ws.conditional_formatting.add(f"B{qrow}", FormulaRule(
        formula=[f'LEFT($B${qrow},3)<>"All"'], fill=PatternFill("solid", bgColor="FFC7CE")))
    r = qrow + 2
    ws.cell(r, 1, "Key findings").font = Font(bold=True, size=12, color=NAVY)
    for k, text in enumerate(findings, start=1):
        ws.cell(r + k, 1, f"{k}. {text}").alignment = Alignment(wrap_text=False)
    r = r + len(findings) + 2
    ws.cell(r, 1, "Sheets").font = Font(bold=True, size=12, color=NAVY)
    for k, name in enumerate([s for s in ws.parent.sheetnames if s != "Summary"], start=1):
        c = ws.cell(r + k, 1, name)
        c.hyperlink = f"#'{name}'!A1"
        c.font = Font(color="0563C1", underline="single")
    set_widths(ws, [30, 22])


def make_findings(df: pd.DataFrame) -> list[str]:
    out = []
    by_m = df[df["market"] != "(Unknown)"].groupby("market")["profit"].sum().sort_values(ascending=False)
    tot = df["profit"].sum()
    if len(by_m) > 1 and tot:
        out.append(f"{by_m.index[0]} leads profit ({by_m.iloc[0]:,.0f}, {by_m.iloc[0] / tot:.0%} of total); "
                   f"{by_m.index[-1]} is lowest ({by_m.iloc[-1]:,.0f}).")
    late = df[df["shipping_mode"] != "(Unknown)"].groupby("shipping_mode")["is_late"].mean().sort_values(ascending=False)
    if len(late) > 1:
        out.append(f"{late.index[0]} has the highest late rate ({late.iloc[0]:.1%}); "
                   f"{late.index[-1]} the lowest ({late.iloc[-1]:.1%}).")
    out.append(f"{(df['profit'] < 0).mean():.1%} of order items lose money.")
    if "discount_rate" in df.columns:
        d = df.dropna(subset=["discount_rate"])
        if len(d):
            hi = d[d["discount_rate"] >= d["discount_rate"].quantile(0.75)]
            lo = d[d["discount_rate"] <= d["discount_rate"].quantile(0.25)]
            out.append(f"Loss rate is {(hi['profit'] < 0).mean():.1%} in the top discount quartile vs "
                       f"{(lo['profit'] < 0).mean():.1%} in the bottom quartile.")
    return out



# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------
def build_report(df: pd.DataFrame, masks, output: Path, source: str) -> None:
    wb = Workbook()
    ws_summary = wb.active
    _, mk_total = metric_sheet(wb, "By market", add_group_agg(df, "market").sort_values(
        "profit", ascending=False), "Market")
    _, sm_total = metric_sheet(wb, "By shipping mode", add_group_agg(df, "shipping_mode").sort_values(
        "late_items", ascending=False), "Shipping mode")
    matrix_sheet(wb, df)
    if "order_date" in df.columns and df["order_date"].notna().any():
        monthly_sheet(wb, df)
    if "discount_rate" in df.columns and df["discount_rate"].notna().any():
        d = df.dropna(subset=["discount_rate"]).copy()
        d["discount_band"] = pd.cut(d["discount_rate"], [-0.0001, 0.05, 0.10, 0.15, 0.20, 1.0],
                                    labels=["0-5%", "5-10%", "10-15%", "15-20%", "20%+"])
        g = add_group_agg(d, "discount_band")
        metric_sheet(wb, "Discount bands", g, "Discount band", late_chart=False)
        wb["Discount bands"].cell(len(g) + 4, 1,
                                  "Read: if Loss % rises with the band, deeper discounts erode profit.").font = Font(italic=True, color="595959")
    if "category_name" in df.columns:
        g = add_group_agg(df, "category_name").sort_values("profit", ascending=False)
        top = pd.concat([g.head(10), g.tail(5)]).drop_duplicates("category_name") if len(g) > 10 else g
        metric_sheet(wb, "Top categories", top, "Category",
                     note="Top 10 and bottom 5 categories by profit. Share is vs. the rows shown.",
                     late_chart=False)
    q_last = quality_sheets(wb, df, masks)
    summary_sheet(ws_summary, df, masks, source, mk_total, sm_total, q_last, make_findings(df))
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)


# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------
def make_demo(n: int = 30000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    modes = ["Standard Class", "Second Class", "First Class", "Same Day"]
    late_p = {"Standard Class": 0.38, "Second Class": 0.77, "First Class": 0.95, "Same Day": 0.46}
    mode = rng.choice(modes, n, p=[0.6, 0.2, 0.15, 0.05])
    disc = rng.choice([0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25], n)
    sales = rng.gamma(4, 50, n).round(2)
    profit = (sales * (0.3 - disc * 1.2 + rng.normal(0, 0.15, n))).round(2)
    df = pd.DataFrame({
        "order_item_key": [f"k{i}" for i in range(n)],
        "order_id": rng.integers(1, n // 3, n),
        "order_date": pd.to_datetime("2015-01-01") + pd.to_timedelta(rng.integers(0, 1100, n), unit="D"),
        "market": rng.choice(["Europe", "LATAM", "Pacific Asia", "USCA", "Africa"], n, p=[.28, .27, .22, .16, .07]),
        "shipping_mode": mode,
        "is_late": [int(rng.random() < late_p[m]) for m in mode],
        "sales": sales, "profit": profit, "discount_rate": disc,
        "category_name": rng.choice([f"Category {i:02d}" for i in range(1, 19)], n),
    })
    df.loc[3, "order_item_key"] = df.loc[2, "order_item_key"]   # injected duplicate
    df.loc[10, "market"] = None                                  # injected null
    df.loc[20, "sales"] = -5.0                                   # injected negative
    return df

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, help=".parquet or .csv with the fact table")
    p.add_argument("--output", default=Path("reports/supply_chain_report.xlsx"), type=Path)
    p.add_argument("--show-columns", action="store_true", help="print columns and matches, then exit")
    p.add_argument("--demo", action="store_true", help="use synthetic data (no input file)")
    p.add_argument("--fail-on-issues", action="store_true",
                   help="exit with code 1 if any validation check finds issues (for schedulers/CI)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if a.demo:
        raw, source = make_demo(), "synthetic demo data"
    elif a.input:
        if not a.input.exists():
            log.error("Input file not found: %s", a.input)
            return EXIT_BAD_INPUT
        raw, source = read_raw(a.input), a.input.name
    else:
        p.error("provide --input FILE or --demo")

    df, mapping = resolve_columns(raw)
    if a.show_columns:
        print("Columns in file :", list(df.columns))
        print("Matched         :", mapping)
        print("Missing required:", [c for c in REQUIRED if c not in mapping] or "none")
        print("Optional found  :", [c for c in ALIASES if c not in REQUIRED and c in mapping])
        return EXIT_OK
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        log.error("Missing required columns: %s. Run with --show-columns and add your "
                  "column names to ALIASES at the top of the script.", missing)
        return EXIT_BAD_INPUT
    df = prepare(df)
    masks = build_masks(df)
    log.info("%s rows loaded from %s", f"{len(df):,}", source)
    failed = []
    for name, m in masks:
        if m.any():
            failed.append(name)
            log.warning("REVIEW %s: %s", name, f"{int(m.sum()):,}")
        else:
            log.info("OK     %s", name)
    build_report(df, masks, a.output, source)
    log.info("Report written to %s", a.output)
    if failed and a.fail_on_issues:
        log.error("%d check(s) found issues: %s", len(failed), "; ".join(failed))
        return EXIT_ISSUES
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())