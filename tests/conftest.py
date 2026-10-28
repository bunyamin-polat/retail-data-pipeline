import pandas as pd
import pytest


def make_rows(*rows: dict) -> pd.DataFrame:
    """Build a source-like DataFrame; every row overrides a valid default."""
    default = {
        "InvoiceNo": "536365",
        "StockCode": "85123A",
        "Description": "WHITE HEART",
        "Quantity": 6,
        "InvoiceDate": "01-12-2010 08:26",
        "UnitPrice": 2.55,
        "CustomerID": 17850.0,
        "Country": "United Kingdom",
    }
    return pd.DataFrame([{**default, **row} for row in rows])


@pytest.fixture
def raw() -> pd.DataFrame:
    return make_rows(
        {"InvoiceNo": "536365", "Description": " WHITE HEART "},
        {"InvoiceNo": "C536379", "Quantity": -1},
        {"InvoiceNo": "536380", "StockCode": "POST"},
        {"InvoiceNo": "536381", "CustomerID": None},
        {"InvoiceNo": "536382", "StockCode": "22727", "Country": "Germany"},
    )
