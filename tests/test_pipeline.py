import pandas as pd
from conftest import make_rows

from retail_pipeline.load import query
from retail_pipeline.pipeline import run


def write_csv(path, df: pd.DataFrame):
    df.to_csv(path, index=False)
    return path


def test_incremental_run_replaces_fully_rejected_invoice(tmp_path):
    db = tmp_path / "Invoice_Records.db"
    first = write_csv(
        tmp_path / "day1.csv", make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "2"})
    )
    second = write_csv(
        tmp_path / "day2.csv", make_rows({"InvoiceNo": "1", "UnitPrice": 0})
    )

    run(first, db, "full")
    run(second, db, "incremental")

    stored = query("SELECT InvoiceNo FROM Purchase_transactions", db_path=db)
    assert stored["InvoiceNo"].tolist() == ["2"]
    rejected = query("SELECT RejectReason FROM Rejected_transactions", db_path=db)
    assert rejected["RejectReason"].tolist() == ["non_positive_price"]


def test_run_survives_malformed_source_values(tmp_path):
    db = tmp_path / "Invoice_Records.db"
    source = write_csv(
        tmp_path / "bad.csv",
        make_rows(
            {"InvoiceNo": "1", "Quantity": "bad"},
            {"InvoiceNo": "2", "CustomerID": "12.5"},
            {"InvoiceNo": "3"},
        ),
    )

    assert run(source, db) == 1
    rejected = query(
        "SELECT InvoiceNo, Quantity, RejectReason FROM Rejected_transactions "
        "ORDER BY InvoiceNo",
        db_path=db,
    )
    assert rejected.to_dict("records") == [
        {"InvoiceNo": "1", "Quantity": "bad", "RejectReason": "invalid_numeric_value"},
        {"InvoiceNo": "2", "Quantity": "6", "RejectReason": "invalid_numeric_value"},
    ]


def test_csv_export_matches_whole_table_in_incremental_mode(tmp_path):
    db = tmp_path / "Invoice_Records.db"
    run(write_csv(tmp_path / "day1.csv", make_rows({"InvoiceNo": "1"})), db, "full")
    run(
        write_csv(tmp_path / "day2.csv", make_rows({"InvoiceNo": "2"})),
        db,
        "incremental",
    )

    exported = pd.read_csv(tmp_path / "purchase_transactions.csv", dtype=str)
    assert sorted(exported["InvoiceNo"]) == ["1", "2"]
