import pandas as pd
import pytest
from conftest import make_rows

from retail_pipeline.transform import transform


def test_removes_credit_non_product_and_anonymous_rows(raw):
    result = transform(raw)
    assert result.clean["InvoiceNo"].tolist() == ["536365", "536382"]
    assert result.reject_counts() == {
        "credit_invoice": 1,
        "non_product_code": 1,
        "missing_customer_id": 1,
    }


def test_normalises_types(raw):
    clean = transform(raw).clean
    assert clean["CustomerID"].dtype == "int64"
    assert pd.api.types.is_datetime64_any_dtype(clean["InvoiceDate"])
    assert clean.loc[0, "InvoiceDate"] == pd.Timestamp("2010-12-01 08:26")
    assert clean.loc[0, "Description"] == "WHITE HEART"


def test_rejects_non_positive_price_and_quantity():
    result = transform(
        make_rows(
            {"InvoiceNo": "1", "UnitPrice": 0.0},
            {"InvoiceNo": "2", "UnitPrice": -11062.06},
            {"InvoiceNo": "3", "Quantity": 0},
            {"InvoiceNo": "4"},
        )
    )
    assert result.clean["InvoiceNo"].tolist() == ["4"]
    assert result.reject_counts() == {
        "non_positive_price": 2,
        "non_positive_quantity": 1,
    }


def test_keeps_first_of_exact_duplicates():
    result = transform(make_rows({}, {}, {}, {"Quantity": 7}))
    assert result.clean["Quantity"].tolist() == [6, 7]
    assert result.reject_counts() == {"duplicate_row": 2}


def test_rejects_missing_invoice_no_without_crashing():
    result = transform(make_rows({"InvoiceNo": None}, {"InvoiceNo": "2"}))
    assert result.clean["InvoiceNo"].tolist() == ["2"]
    assert result.reject_counts() == {"missing_required_field": 1}


def test_rejects_unparseable_date():
    result = transform(make_rows({"InvoiceDate": "2010/13/45"}, {}))
    assert len(result.clean) == 1
    assert result.reject_counts() == {"invalid_invoice_date": 1}


@pytest.mark.parametrize(
    "bad",
    [
        {"Quantity": "bad"},
        {"Quantity": "1.5"},
        {"UnitPrice": "bad"},
        {"UnitPrice": "inf"},
        {"CustomerID": "12.5"},
        {"CustomerID": "abc"},
    ],
)
def test_rejects_malformed_numbers_without_crashing(bad):
    result = transform(make_rows(bad, {"InvoiceNo": "2"}))
    assert result.clean["InvoiceNo"].tolist() == ["2"]
    assert result.reject_counts() == {"invalid_numeric_value": 1}


def test_numeric_strings_are_accepted_and_typed():
    result = transform(
        make_rows({"Quantity": "6", "UnitPrice": "2.55", "CustomerID": "17850.0"})
    )
    clean = result.clean
    assert (clean.loc[0, "Quantity"], clean.loc[0, "CustomerID"]) == (6, 17850)
    assert clean.loc[0, "UnitPrice"] == 2.55
    assert clean["Quantity"].dtype == "int64"
    assert clean["UnitPrice"].dtype == "float64"


def test_rejected_rows_keep_original_source_values():
    rejected = transform(
        make_rows({"Quantity": "bad"}, {"InvoiceDate": "2010/13/45"})
    ).rejected
    assert rejected.loc[0, "Quantity"] == "bad"
    assert rejected.loc[1, "InvoiceDate"] == "2010/13/45"


def test_every_row_is_either_clean_or_rejected(raw):
    result = transform(raw)
    assert len(result.clean) + len(result.rejected) == len(raw)
    assert result.rejected["RejectReason"].notna().all()


def test_accepts_datetime_input_from_excel():
    df = make_rows({}).assign(InvoiceDate=pd.Timestamp("2011-12-09 12:50"))
    clean = transform(df).clean
    assert clean.loc[0, "InvoiceDate"] == pd.Timestamp("2011-12-09 12:50")
