"""Extract step: read raw invoice data from a URL or a local CSV/Excel file."""

from pathlib import Path

import pandas as pd

from retail_pipeline.config import COLUMNS

TEXT_COLUMNS = {"InvoiceNo": str, "StockCode": str}


def extract(source: str | Path) -> pd.DataFrame:
    """Read invoice records, keeping InvoiceNo and StockCode as text."""
    if str(source).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(source, dtype=TEXT_COLUMNS)
    else:
        df = pd.read_csv(source, dtype=TEXT_COLUMNS)

    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Source is missing columns: {sorted(missing)}")
    return df[COLUMNS]
