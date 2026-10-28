"""Load step: write cleaned data to SQLite and query it back.

Two load modes:

- ``full``: the source is a complete snapshot; the table is replaced so it
  always equals the latest snapshot.
- ``incremental``: the source holds only new or changed invoices. Every invoice
  in the batch replaces all stored lines of that invoice; other invoices are
  kept. Re-running the same batch is therefore safe and never duplicates rows.
  Pass the invoice numbers of the *raw* batch as ``batch_invoices``: an invoice
  whose new lines were all rejected must still have its old lines removed.

The batch is first written to a staging table, then swapped or merged into
the target inside one explicit transaction: a failed run leaves the target
table unchanged.
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import pandas as pd

from retail_pipeline.config import DB_PATH, TABLE_NAME

LoadMode = Literal["full", "incremental"]


def load(
    df: pd.DataFrame,
    db_path: Path = DB_PATH,
    table: str = TABLE_NAME,
    mode: LoadMode = "full",
    batch_invoices: Iterable[str | None] | None = None,
) -> None:
    """Write `df` to `table` using the given load mode.

    `batch_invoices` (incremental only) are the invoices this batch replaces;
    defaults to the invoices present in `df`.
    """
    if mode not in ("full", "incremental"):
        raise ValueError(f"Unknown load mode: {mode!r}")
    numbers = (
        df["InvoiceNo"]
        if batch_invoices is None
        else pd.Series(list(batch_invoices), dtype="object")
    )
    invoices = [(str(no),) for no in numbers.dropna().unique()]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    staging = f"{table}__staging"
    conn = sqlite3.connect(db_path)
    try:
        # default mode: pandas writes the whole staging table in one commit
        df.to_sql(staging, conn, if_exists="replace", index=False)
        cols = ", ".join(f'"{c}"' for c in df.columns)

        # manual mode, so the swap/merge below is one explicit transaction
        conn.isolation_level = None
        conn.execute("BEGIN")
        try:
            if mode == "full" or not _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                conn.execute(f'ALTER TABLE "{staging}" RENAME TO "{table}"')
            else:
                conn.execute("CREATE TEMP TABLE batch_invoices (InvoiceNo TEXT)")
                conn.executemany("INSERT INTO batch_invoices VALUES (?)", invoices)
                conn.execute(
                    f'DELETE FROM "{table}" WHERE InvoiceNo IN '
                    "(SELECT InvoiceNo FROM batch_invoices)"
                )
                conn.execute("DROP TABLE batch_invoices")
                conn.execute(
                    f'INSERT INTO "{table}" ({cols}) SELECT {cols} FROM "{staging}"'
                )
                conn.execute(f'DROP TABLE "{staging}"')
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "ix_{table}_invoice" '
                f'ON "{table}" (InvoiceNo)'
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            conn.execute(f'DROP TABLE IF EXISTS "{staging}"')
            raise
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def query(sql: str, params: tuple = (), db_path: Path = DB_PATH) -> pd.DataFrame:
    """Run a read query against the SQLite database."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql(sql, conn, params=params)


def transactions_by_country(country: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    """All purchase transactions for one country."""
    return query(f"SELECT * FROM {TABLE_NAME} WHERE Country = ?", (country,), db_path)
