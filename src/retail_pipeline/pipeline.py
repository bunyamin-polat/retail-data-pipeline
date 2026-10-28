"""Run the full ETL pipeline: extract -> transform -> load."""

import argparse
import logging
from pathlib import Path
from typing import get_args

from retail_pipeline.config import (
    DB_PATH,
    REJECTED_TABLE_NAME,
    SOURCE_PATH,
    TABLE_NAME,
)
from retail_pipeline.extract import extract
from retail_pipeline.load import LoadMode, load, query
from retail_pipeline.transform import transform

log = logging.getLogger("retail_pipeline")


def run(
    source: str | Path = SOURCE_PATH,
    db_path: Path = DB_PATH,
    mode: LoadMode = "full",
) -> int:
    """Run the pipeline and return the number of loaded rows."""
    raw = extract(source)
    log.info("Rows read:     %d", len(raw))

    result = transform(raw)
    log.info("Rows clean:    %d", len(result.clean))
    log.info("Rows rejected: %d", len(result.rejected))
    for reason, count in result.reject_counts().items():
        log.info("  %-24s %d", reason, count)

    # the raw batch decides which invoices are replaced, so an invoice whose
    # lines were all rejected still loses its outdated stored lines
    load(result.clean, db_path, TABLE_NAME, mode, batch_invoices=raw["InvoiceNo"])
    # rejected rows of this run, for inspection and data-quality reporting
    load(result.rejected, db_path, REJECTED_TABLE_NAME, "full")

    # CSV export is always a snapshot of the whole table, in both load modes
    table = query(f"SELECT * FROM {TABLE_NAME}", db_path=db_path)
    table.to_csv(db_path.with_name(f"{TABLE_NAME.lower()}.csv"), index=False)
    log.info(
        "Loaded %d rows into %s:%s (%s load)",
        len(result.clean),
        db_path.name,
        TABLE_NAME,
        mode,
    )
    return len(result.clean)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=SOURCE_PATH,
        help="CSV/Excel file path or URL (default: data/raw/invoice_records.csv)",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH, help="SQLite DB path")
    parser.add_argument(
        "--mode",
        choices=get_args(LoadMode),
        default="full",
        help="full: source is a complete snapshot (replace table); "
        "incremental: source holds new/changed invoices (replace those invoices)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.source, args.db, args.mode)

    sample = query(f"SELECT * FROM {TABLE_NAME} LIMIT 5", db_path=args.db)
    print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
