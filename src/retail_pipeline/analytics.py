"""Data mining: market basket analysis (Apriori) and RFM segmentation."""

import math

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules


def build_basket(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot basket table: invoices as rows, items as columns."""
    quantities = df.groupby(["InvoiceNo", "Description"])["Quantity"].sum()
    basket: pd.DataFrame = quantities.unstack(fill_value=0)
    return basket.gt(0)


def mine_rules(
    basket: pd.DataFrame, min_support: float = 0.05, min_lift: float = 1.0
) -> pd.DataFrame:
    """Apriori frequent itemsets -> association rules sorted by lift."""
    itemsets = apriori(basket, min_support=min_support, use_colnames=True)
    rules = association_rules(itemsets, metric="lift", min_threshold=min_lift)
    rules = rules.sort_values(["lift", "confidence"], ascending=False)
    for side in ["antecedents", "consequents"]:
        rules[side] = rules[side].apply(lambda items: ", ".join(sorted(items)))
    return rules[["antecedents", "consequents", "support", "confidence", "lift"]]


RFM_COLUMNS = ["Recency", "Frequency", "Monetary", "R", "F", "M", "Segment"]


def rfm_table(df: pd.DataFrame) -> pd.DataFrame:
    """Recency, Frequency, Monetary per customer with 1-4 quartile scores.

    Works for any number of customers: an empty input gives an empty table,
    and with fewer than four customers some score levels are simply unused.
    """
    if df.empty:
        empty = pd.DataFrame(columns=RFM_COLUMNS)
        empty.index.name = "CustomerID"
        return empty

    df = df.assign(LineTotal=df["Quantity"] * df["UnitPrice"])
    snapshot = df["InvoiceDate"].max() + pd.Timedelta(days=1)
    rfm = df.groupby("CustomerID").agg(
        Recency=("InvoiceDate", lambda d: (snapshot - d.max()).days),
        Frequency=("InvoiceNo", "nunique"),
        Monetary=("LineTotal", "sum"),
    )
    rfm["R"] = _quartile_score(rfm["Recency"], higher_is_better=False)
    rfm["F"] = _quartile_score(rfm["Frequency"])
    rfm["M"] = _quartile_score(rfm["Monetary"])
    rfm["Segment"] = (rfm["R"] + rfm["F"] + rfm["M"]).map(_segment)
    return rfm


def _quartile_score(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Score 1-4 by percentile rank; ties broken by order, so bins stay even."""
    pct = values.rank(method="first", ascending=higher_is_better, pct=True)
    return (pct * 4).apply(math.ceil).astype(int)


def _segment(score: int) -> str:
    if score >= 10:
        return "Champions"
    if score >= 8:
        return "Loyal"
    if score >= 6:
        return "Potential"
    return "At risk"
