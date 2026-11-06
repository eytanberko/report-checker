"""Files to download from the app: a CSV as an Excel workbook."""
import io
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

MAX_WIDTH = 60  # characters; a very long text column should not push the rest off screen


def csv_to_xlsx(path: Path) -> bytes:
    """One sheet named after the file, header row bold, each column as wide as its longest value."""
    df = pd.read_csv(path)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=path.stem[:31])  # Excel caps sheet names at 31 characters
        ws = xw.sheets[path.stem[:31]]
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for i, col in enumerate(df.columns, start=1):
            width = max([len(str(col))] + [len(str(v)) for v in df[col].dropna()])
            ws.column_dimensions[get_column_letter(i)].width = min(width + 2, MAX_WIDTH)
        ws.freeze_panes = "A2"
    return buf.getvalue()
