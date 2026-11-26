"""Export a formatted Excel workbook with openpyxl.

Sheets:
  * KPI by channel - aggregated KPIs per channel, with a NATIVE Excel bar chart of spend.
  * Segments       - K-Means segment profiles.
  * A/B test       - the two-proportion z-test result, laid out as a mini scorecard.

"Native" chart means a real editable Excel chart object (not a pasted image), so a
stakeholder can restyle it in Excel.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)


def _write_df(ws, df: pd.DataFrame, start_row: int = 1) -> int:
    """Write a DataFrame with a styled header row. Returns the last row written."""
    for r_off, row in enumerate(dataframe_to_rows(df, index=False, header=True)):
        for c_off, value in enumerate(row, start=1):
            cell = ws.cell(row=start_row + r_off, column=c_off, value=value)
            if r_off == 0:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal="center")
    # auto-ish column widths
    for c_off, col in enumerate(df.columns, start=1):
        width = max(len(str(col)), *(len(str(v)) for v in df[col].head(50))) + 2
        ws.column_dimensions[ws.cell(row=1, column=c_off).column_letter].width = min(width, 32)
    return start_row + len(df)


def build_workbook(
    kpi_by_channel: pd.DataFrame,
    segment_profiles: pd.DataFrame,
    ab_result: dict,
    path: Path,
) -> Path:
    """Build and save the workbook. Returns the output path."""
    wb = Workbook()

    # --- Sheet 1: KPI by channel + native bar chart ---
    ws = wb.active
    ws.title = "KPI by channel"
    ws["A1"] = "AdPulse - KPIs by channel (synthetic data)"
    ws["A1"].font = TITLE_FONT
    last = _write_df(ws, kpi_by_channel, start_row=3)

    chart = BarChart()
    chart.title = "Spend by channel"
    chart.type = "col"
    chart.y_axis.title = "Spend ($)"
    chart.x_axis.title = "Channel"
    spend_col = list(kpi_by_channel.columns).index("spend") + 1
    data = Reference(ws, min_col=spend_col, min_row=3, max_row=last)
    cats = Reference(ws, min_col=1, min_row=4, max_row=last)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height, chart.width = 8, 15
    ws.add_chart(chart, f"A{last + 3}")

    # --- Sheet 2: segment profiles ---
    ws2 = wb.create_sheet("Segments")
    ws2["A1"] = "Customer segments (RFM + K-Means)"
    ws2["A1"].font = TITLE_FONT
    _write_df(ws2, segment_profiles, start_row=3)

    # --- Sheet 3: A/B scorecard ---
    ws3 = wb.create_sheet("A-B test")
    ws3["A1"] = "A/B test: creative_A (control) vs creative_B (variant)"
    ws3["A1"].font = TITLE_FONT
    scorecard = pd.DataFrame(
        {
            "metric": [
                "conversion rate A", "conversion rate B", "relative lift",
                "z-statistic", "p-value", "95% CI (abs lift)", "significant?",
            ],
            "value": [
                f"{ab_result['rate_a']:.3%}",
                f"{ab_result['rate_b']:.3%}",
                f"{ab_result['rel_lift']:+.1%}",
                f"{ab_result['z_stat']:.3f}",
                f"{ab_result['p_value']:.4g}",
                f"[{ab_result['ci_low']:+.4f}, {ab_result['ci_high']:+.4f}]",
                "YES" if ab_result["significant"] else "NO",
            ],
        }
    )
    _write_df(ws3, scorecard, start_row=3)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
