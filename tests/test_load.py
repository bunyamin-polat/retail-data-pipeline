import sqlite3

import pandas as pd
import pytest
from conftest import make_rows

from retail_pipeline.load import load, query, transactions_by_country
from retail_pipeline.transform import transform

TABLE = "Purchase_transactions"


def stored(db) -> list[tuple[str, int]]:
    rows = query(
        f"SELECT InvoiceNo, Quantity FROM {TABLE} ORDER BY InvoiceNo, Quantity",
        db_path=db,
    )
    return list(rows.itertuples(index=False, name=None))


def test_load_and_query_by_country(raw, tmp_path):
    db = tmp_path / "test.db"
    load(transform(raw).clean, db)
    germany = transactions_by_country("Germany", db)
    assert germany["InvoiceNo"].tolist() == ["536382"]


def test_full_load_replaces_table(tmp_path):
    db = tmp_path / "test.db"
    load(make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "2"}), db)
    load(make_rows({"InvoiceNo": "3"}), db, mode="full")
    assert stored(db) == [("3", 6)]


def test_incremental_load_keeps_history_and_adds_new_invoices(tmp_path):
    db = tmp_path / "test.db"
    load(make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "2"}), db)
    load(make_rows({"InvoiceNo": "3"}), db, mode="incremental")
    assert stored(db) == [("1", 6), ("2", 6), ("3", 6)]


def test_incremental_load_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    batch = make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "1", "Quantity": 2})
    load(batch, db, mode="incremental")
    load(batch, db, mode="incremental")
    assert stored(db) == [("1", 2), ("1", 6)]


def test_incremental_load_replaces_changed_invoice(tmp_path):
    db = tmp_path / "test.db"
    load(make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "1"}, {"InvoiceNo": "2"}), db)
    load(make_rows({"InvoiceNo": "1", "Quantity": 9}), db, mode="incremental")
    assert stored(db) == [("1", 9), ("2", 6)]


def test_incremental_load_removes_invoice_whose_new_lines_were_all_rejected(tmp_path):
    db = tmp_path / "test.db"
    load(make_rows({"InvoiceNo": "1"}, {"InvoiceNo": "2"}), db)
    raw_batch = make_rows({"InvoiceNo": "1", "UnitPrice": 0.0}, {"InvoiceNo": None})
    result = transform(raw_batch)
    assert result.clean.empty
    load(result.clean, db, mode="incremental", batch_invoices=raw_batch["InvoiceNo"])
    assert stored(db) == [("2", 6)]


def test_failed_incremental_load_leaves_table_unchanged(tmp_path):
    db = tmp_path / "test.db"
    load(make_rows({"InvoiceNo": "1"}), db)
    bad_batch = pd.DataFrame({"InvoiceNo": ["1"], "UnknownColumn": [1]})
    with pytest.raises(sqlite3.OperationalError):
        load(bad_batch, db, mode="incremental")
    assert stored(db) == [("1", 6)]
    tables = query("SELECT name FROM sqlite_master WHERE type = 'table'", db_path=db)
    assert tables["name"].tolist() == [TABLE]  # staging table cleaned up


def test_unknown_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown load mode"):
        load(make_rows({}), tmp_path / "test.db", mode="upsert")  # type: ignore[arg-type]
