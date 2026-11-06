"""The example data as an Excel download: one sheet, bold header, columns sized to fit, same values as the CSV."""
import io
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from checker.export import csv_to_xlsx

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("csv", ["examples/cafes/cafes.csv", "data/energy.csv"])
def test_example_data_as_xlsx(csv):
    path = ROOT / csv
    data = csv_to_xlsx(path)
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == [path.stem]
    ws = wb.active
    df = pd.read_csv(path)
    assert [c.value for c in ws[1]] == list(df.columns) and all(c.font.bold for c in ws[1])
    for i, col in enumerate(df.columns, start=1):
        letter = ws.cell(row=1, column=i).column_letter
        assert ws.column_dimensions[letter].width >= len(col) + 2           # header fits
    assert ws.max_row == len(df) + 1
    pd.testing.assert_frame_equal(pd.read_excel(io.BytesIO(data)), df, check_dtype=False)
