"""Transform step: validate rows and apply the business cleaning rules."""

from dataclasses import dataclass

import pandas as pd

from retail_pipeline.config import NON_PRODUCT_CODES

SOURCE_DATE_FORMAT = "%d-%m-%Y %H:%M"
REQUIRED_COLUMNS = ["InvoiceNo", "StockCode", "Quantity", "InvoiceDate", "UnitPrice"]
INTEGER_COLUMNS = ["Quantity", "CustomerID"]
NUMERIC_COLUMNS = [*INTEGER_COLUMNS, "UnitPrice"]


@dataclass
class TransformResult:
    clean: pd.DataFrame
    rejected: pd.DataFrame  # source rows as received, plus a RejectReason column

    def reject_counts(self) -> dict[str, int]:
        counts = self.rejected["RejectReason"].value_counts()
        return {str(reason): int(n) for reason, n in counts.items()}


def _parse_dates(dates: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(dates):
        return dates
    return pd.to_datetime(dates, format=SOURCE_DATE_FORMAT, errors="coerce")


def _parse_number(values: pd.Series, integer: bool) -> tuple[pd.Series, pd.Series]:
    """Convert to numbers; flag present values that are not valid numbers.

    Returns (parsed values, invalid mask). Missing values are not flagged here;
    they are handled by the missing-field rules.
    """
    parsed = pd.to_numeric(values, errors="coerce")
    invalid = values.notna() & parsed.isna()
    invalid |= parsed.abs().eq(float("inf"))
    if integer:
        invalid |= parsed.notna() & parsed.mod(1).ne(0)
    return parsed.mask(invalid), invalid


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def transform(df: pd.DataFrame) -> TransformResult:
    """Split rows into clean and rejected; each rejected row gets one reason.

    Rules are checked in order and the first one that matches is reported.
    Malformed values never raise: they reject the row instead.
    """
    parsed = df.copy()
    parsed["Description"] = parsed["Description"].map(_strip)
    parsed["InvoiceDate"] = _parse_dates(df["InvoiceDate"])

    invalid_number = pd.Series(False, index=df.index)
    for column in NUMERIC_COLUMNS:
        values, invalid = _parse_number(df[column], column in INTEGER_COLUMNS)
        parsed[column] = values
        invalid_number |= invalid

    invoice_no = df["InvoiceNo"].astype("string").fillna("")
    rules = {
        "missing_required_field": df[REQUIRED_COLUMNS].isna().any(axis=1),
        "invalid_invoice_date": parsed["InvoiceDate"].isna(),
        "invalid_numeric_value": invalid_number,
        "credit_invoice": invoice_no.str.startswith("C"),
        "non_product_code": df["StockCode"].isin(NON_PRODUCT_CODES),
        "missing_customer_id": df["CustomerID"].isna(),
        "non_positive_quantity": parsed["Quantity"] <= 0,
        "non_positive_price": parsed["UnitPrice"] <= 0,
    }
    reason = pd.Series(pd.NA, index=df.index, dtype="string")
    for name, mask in rules.items():
        reason = reason.mask(reason.isna() & mask.fillna(False).astype(bool), name)

    # exact duplicates among otherwise valid rows: keep the first occurrence
    duplicate = parsed[reason.isna()].duplicated()
    reason[duplicate[duplicate].index] = "duplicate_row"

    clean = parsed[reason.isna()].copy()
    for column in INTEGER_COLUMNS:
        clean[column] = clean[column].astype(int)
    clean["UnitPrice"] = clean["UnitPrice"].astype(float)
    rejected = df[reason.notna()].assign(RejectReason=reason[reason.notna()])
    return TransformResult(
        clean=clean.reset_index(drop=True), rejected=rejected.reset_index(drop=True)
    )
