"""Mapping the words documents use onto the metrics we store.

A CIM says "Turnover", a workbook says "Revenue", another says "Total
revenue". All three are `revenue`. Keeping this in one place means the
mapping can be audited, extended and argued with — and the original words
are always stored alongside the mapped metric, so a wrong mapping is
recoverable rather than permanent.

Two things this deliberately does not do.

It does not guess. A label it does not recognise returns None and the row
is flagged for review rather than being dropped or assigned to the
nearest-looking metric.

It does not decide the breakdown axis. "Personnel" is a cost by nature in
one company's reporting and sits in a functional breakdown in another's.
That is a property of the sheet it appears on, not of the word.
"""

from __future__ import annotations

import re

# Canonical metric -> the labels documents actually print.
# Lower-cased and stripped of punctuation before matching.
LABEL_TO_METRIC: dict[str, str] = {}

_SYNONYMS: dict[str, list[str]] = {
    "arr": ["arr", "arr year end", "annual recurring revenue",
            "arr as at date"],
    "carr": ["carr", "contracted arr", "contracted annual recurring revenue"],
    "revenue": ["revenue", "total revenue", "turnover", "net revenues",
                "net revenue", "sales"],
    "recurring_revenue": ["recurring revenue", "subscription revenue",
                          "subscription and support", "recurring revenues"],
    "non_recurring_revenue": ["non recurring revenue", "nonrecurring revenue",
                              "services and other", "professional services",
                              "implementation and services",
                              "non recurring revenues"],
    "other_revenue": ["other revenue"],
    "cogs": ["cogs", "cost of sales", "cost of revenue", "cost of goods sold"],
    "gross_profit": ["gross profit", "gross margin gbp", "gross profit loss"],
    "personnel_expenses": ["personnel", "personnel expenses", "staff costs",
                           "employee costs"],
    "non_personnel_expenses": ["non personnel", "non personnel expenses"],
    "product_and_engineering": ["product", "product and engineering",
                                "research and development", "r d"],
    "sales_and_marketing": ["s m", "sales and marketing", "marketing"],
    "general_and_admin": ["g a", "general and administrative",
                          "administrative expenses", "general and admin"],
    "implementation": ["implementation", "consulting"],
    "other_opex": ["other"],
    "total_opex": ["total opex", "total overheads", "total operating expenses",
                   "overheads"],
    "ebitda_adjustments": ["adjustments", "exceptional items",
                           "non recurring items", "transaction and other items"],
    "ebitda": ["ebitda"],
    "adjusted_ebitda": ["adj ebitda", "adjusted ebitda", "adj ebitdac"],
    "operating_cash_flow": ["operating cash flow", "ocf"],
    "capex": ["capex", "capital expenditure"],
    "free_cash_flow": ["free cash flow", "fcf"],
}

for _metric, _labels in _SYNONYMS.items():
    for _label in _labels:
        LABEL_TO_METRIC[_label] = _metric


def normalise(label: str) -> str:
    """Lower-case, strip punctuation and footnote markers, collapse spaces.

    Footnote markers matter: real templates print "Gross retention %5"
    where the 5 is a superscript reference, and a mapping that fails on
    that would flag half a workbook for review.
    """
    text = label.lower().strip()
    text = re.sub(r"[¹²³⁰-₟]", " ", text)  # superscripts
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s*\d+\s*$", " ", text)      # trailing footnote digits
    return re.sub(r"\s+", " ", text).strip()


def map_label(label: str | None) -> str | None:
    """Return the canonical metric for a printed label, or None.

    None means "not recognised", which is a review flag — never a guess.
    """
    if not label:
        return None
    return LABEL_TO_METRIC.get(normalise(label))


def is_cost_metric(metric: str) -> bool:
    """Whether this metric is normally printed as a negative in a model."""
    return metric in {
        "cogs", "personnel_expenses", "non_personnel_expenses",
        "product_and_engineering", "sales_and_marketing",
        "general_and_admin", "implementation", "other_opex", "total_opex",
        "capex",
    }
