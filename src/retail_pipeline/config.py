"""Project paths and pipeline settings."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SOURCE_PATH = RAW_DIR / "invoice_records.csv"
DB_PATH = PROCESSED_DIR / "Invoice_Records.db"
TABLE_NAME = "Purchase_transactions"
REJECTED_TABLE_NAME = "Rejected_transactions"  # rows rejected by the latest run

COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]
# Carriage, Discount, Manual and Postage entries are not products
NON_PRODUCT_CODES = ["C2", "D", "M", "POST"]
