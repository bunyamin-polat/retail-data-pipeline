import pandas as pd
import pytest

from retail_pipeline.analytics import RFM_COLUMNS, build_basket, rfm_table


def test_build_basket_is_one_hot():
    df = pd.DataFrame(
        {
            "InvoiceNo": ["1", "1", "2"],
            "Description": ["A", "B", "A"],
            "Quantity": [2, 3, 5],
        }
    )
    basket = build_basket(df)
    assert all(pd.api.types.is_bool_dtype(dtype) for dtype in basket.dtypes)
    assert list(basket.loc["2"]) == [True, False]


def sales(n_customers: int) -> pd.DataFrame:
    """One invoice per customer; customer i buys i+1 days later and spends more."""
    return pd.DataFrame(
        {
            "CustomerID": range(n_customers),
            "InvoiceNo": [str(i) for i in range(n_customers)],
            "InvoiceDate": pd.date_range("2011-01-01", periods=n_customers),
            "Quantity": [1] * n_customers,
            "UnitPrice": [10.0 * (i + 1) for i in range(n_customers)],
        }
    )


def test_rfm_empty_input_returns_empty_table():
    rfm = rfm_table(sales(0))
    assert rfm.empty
    assert list(rfm.columns) == RFM_COLUMNS


@pytest.mark.parametrize("n_customers", [1, 2, 3, 8])
def test_rfm_scores_any_number_of_customers(n_customers):
    rfm = rfm_table(sales(n_customers))
    assert len(rfm) == n_customers
    for score in ["R", "F", "M"]:
        assert rfm[score].between(1, 4).all()
    assert rfm["Segment"].notna().all()


def test_rfm_best_customer_scores_highest():
    rfm = rfm_table(sales(8))
    best = rfm.loc[7]  # most recent purchase and highest spend
    assert (best["R"], best["M"]) == (4, 4)
    assert rfm.loc[0, "R"] == 1
