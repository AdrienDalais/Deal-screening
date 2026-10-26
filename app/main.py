"""Deal Screening Workbench — review interface.

    streamlit run app/main.py

Pages only. Every figure shown is produced by core/pipeline.py, which is
covered by the test suite; this file formats and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit puts the *script's* directory on sys.path, not the project
# root, so sibling packages are not importable without this. Required
# both locally and when deployed.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import data
from core.reconciliation import Severity

st.set_page_config(page_title="Deal Screening Workbench",
                   page_icon="◆", layout="wide")

SEVERITY_LABEL = {
    Severity.ERROR: "Error",
    Severity.DISAGREE: "Sources disagree",
    Severity.WARNING: "Warning",
}
SEVERITY_COLOUR = {
    Severity.ERROR: "#B3261E",
    Severity.DISAGREE: "#9A6700",
    Severity.WARNING: "#5A6270",
}


def pct(value):
    return "—" if value is None else f"{value * 100:,.1f}%"


def money(value, currency):
    return "—" if value is None else f"{value / 1e6:,.1f}"


# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------

st.sidebar.title("Deal Screening Workbench")
slug = st.sidebar.radio(
    "Deal", list(data.DEALS), format_func=lambda s: data.truth(s).name)

truth = data.truth(slug)
report = data.load(slug)

st.sidebar.markdown("---")
st.sidebar.caption(
    f"**{truth.sector}**  \n{truth.subsector}  \n\n"
    f"{truth.country} · {truth.currency} · year end "
    f"{['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][truth.fiscal_year_end_month]}"
)
st.sidebar.markdown("---")
st.sidebar.caption(
    "Every company here is **invented**. No figure derives from a real "
    "deal. Synthetic fixtures carry deliberate defects so that the "
    "checks can be shown to catch them."
)

# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------

errors = [i for i in report.issues if i.severity == Severity.ERROR]
disagreements = [i for i in report.issues if i.severity == Severity.DISAGREE]

st.title(truth.name)
head = st.columns(4)
head[0].metric("Observations", len(report.observations))
head[1].metric("Documents", len(report.documents))
head[2].metric("Errors", len(errors))
head[3].metric("Disagreements", len(disagreements))

tabs = st.tabs(["Snapshot", "Scorecard", f"Findings ({len(report.issues)})",
                "Evidence", "Comparison"])

# ---------------------------------------------------------------------
# Snapshot — the screening view
# ---------------------------------------------------------------------

with tabs[0]:
    briefing, staleness = data.load_briefing(slug)
    kpis = data.load_kpis(slug)

    left, right = st.columns([3, 2])

    with left:
        st.markdown("#### What this company is")
        if briefing is None:
            st.info("No briefing has been generated for this deal yet. "
                    "Run `python -m tools.summarise_deal` to write one.")
        else:
            if staleness:
                st.warning("This briefing may be out of date: "
                           + "; ".join(staleness) + ".")
            for summary in briefing.summaries:
                if summary.text == "NOT STATED":
                    continue
                st.markdown(f"**{summary.question}**")
                st.write(summary.text)
                st.caption(f"From {summary.citation} of the CIM.")
            for key, why in briefing.failures:
                st.caption(f"*{key}: not shown — {why}*")

            st.caption(
                f"Written by {briefing.key.model_name} using prompt "
                f"v{briefing.key.prompt_version} on "
                f"{briefing.generated_at[:10]}.")

    with right:
        st.markdown("#### Identification")
        st.dataframe(pd.DataFrame([
            {"": "Sector", " ": truth.sector},
            {"": "Subsector", " ": truth.subsector},
            {"": "Country", " ": truth.country},
            {"": "Currency", " ": truth.currency},
            {"": "Year end", " ": [
                "", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December"][truth.fiscal_year_end_month]},
            {"": "Documents", " ": str(len(report.documents))},
        ]), use_container_width=True, hide_index=True)

        st.markdown("#### Stated in the CIM")
        st.caption("Found by searching the document's own prose. These are "
                   "claims the company makes, not figures we have checked.")

        labels = {
            "market_size": "Market size",
            "customer_count": "Customers",
            "average_contract_value": "Average contract value",
            "top_10_concentration": "Top 10 concentration",
            "gross_retention": "Gross retention",
            "net_retention": "Net retention",
            "employees": "Employees",
        }
        rows = []
        for key, label in labels.items():
            finding = kpis.get(key)
            if finding is None:
                rows.append({"Metric": label, "Stated": "—", "Source": ""})
                continue
            value = finding.value
            if key in ("market_size", "average_contract_value"):
                shown = (f"{truth.currency} {value/1e9:,.1f}bn"
                         if value and value >= 1e9 else
                         f"{truth.currency} {value/1e6:,.1f}m"
                         if value and value >= 1e6 else
                         f"{truth.currency} {value:,.0f}")
            elif key in ("customer_count", "employees"):
                shown = f"{value:,.0f}"
            else:
                shown = f"{value:,.0f}%"
            rows.append({"Metric": label, "Stated": shown,
                         "Source": f"p.{finding.page}"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True)

    st.markdown("---")
    st.markdown("#### Where this page gets its words and its numbers")
    st.markdown(
        "The prose on the left is **written by a model** from the CIM "
        "pages cited beneath each answer. It is checked before it is "
        "shown: a summary containing a figure is rejected outright, "
        "because a plausible invented number is the one failure of an "
        "LLM summary that a reader cannot catch.\n\n"
        "Every number on this page is **read from a document** and "
        "carries the page or cell it came from. The figures on the right "
        "are what the company *states*; the Scorecard tab holds what the "
        "accounts *show*, and the Findings tab holds every place the two "
        "disagree."
    )


# ---------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------

with tabs[1]:
    periods = sorted(report.metrics["revenue"])
    actual = {o.period_label for o in report.observations
              if o.basis.value == "actual"}

    rows = {
        f"Revenue ({report.currency}m)": [
            money(report.metrics["revenue"].get(p), report.currency)
            for p in periods],
        "Revenue growth": [pct(report.metrics["revenue_growth"].get(p))
                           for p in periods],
        "Recurring share": [pct(report.metrics["recurring_share"].get(p))
                            for p in periods],
        "Gross margin": [pct(report.metrics["gross_margin"].get(p))
                         for p in periods],
        "EBITDA margin": [pct(report.metrics["ebitda_margin"].get(p))
                          for p in periods],
        "Rule of 40": [pct(report.metrics["rule_of_40"].get(p))
                       for p in periods],
    }
    columns = [f"{p} {'A' if p in actual else 'E'}" for p in periods]
    st.dataframe(pd.DataFrame(rows, index=columns).T,
                 use_container_width=True)

    st.caption(
        f"Rule of 40 variant: **{report.variant.value}**. The variant is "
        f"recorded on the deal and printed wherever the metric appears, "
        f"because the same company scores differently under each one."
    )

    st.markdown("#### Why some cells are blank")
    st.markdown(
        "A dash is never a zero and never a rounding. It means the figure "
        "**cannot honestly be shown**, for one of three reasons:\n\n"
        "- the figure is absent from every document\n"
        "- two sources state it differently and neither has been chosen\n"
        "- the calculation would have spanned a change of basis — an "
        "actual divided by a forecast is a plan, not a growth rate\n\n"
        "In each case the reason appears under **Findings**."
    )

# ---------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------

with tabs[2]:
    if not report.issues:
        st.success("No findings.")
    for issue in report.issues:
        colour = SEVERITY_COLOUR[issue.severity]
        st.markdown(
            f"<span style='background:{colour};color:white;padding:2px 8px;"
            f"border-radius:3px;font-size:0.75rem'>"
            f"{SEVERITY_LABEL[issue.severity]}</span> &nbsp; "
            f"<code>{issue.check}</code>",
            unsafe_allow_html=True)
        st.write(issue.message)
        if issue.observations:
            cited = sorted({f"{o.document} · {o.source_ref}"
                            for o in issue.observations if o.source_ref})
            st.caption("Evidence: " + " | ".join(cited))
        st.caption(f"Fingerprint `{issue.fingerprint}` — an explanation "
                   f"recorded against this identifier stops the finding "
                   f"being raised again, and is invalidated automatically "
                   f"if any of the figures above change.")
        st.markdown("---")

    unevaluable = [c for c in report.checks if not c.evaluable]
    st.markdown("#### Controls inside the source workbook")
    st.caption(
        f"{len(report.checks)} found, {len(unevaluable)} that cannot be "
        f"evaluated. A control that cannot run is reported in words: "
        f"rendered blank, as a dash or as an error code, it reads as "
        f"'fine' to a tired reader.")
    for check in report.checks:
        if check.evaluable:
            st.markdown(f"- ✓ {check.label}")
        else:
            st.markdown(f"- ✗ **{check.label}** — {check.reason}")

# ---------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------

with tabs[3]:
    st.caption(
        "Every figure as it was printed, with the cell it came from. "
        "Nothing here is corrected: a mis-keyed value is transcribed "
        "faithfully, because destroying the evidence that a document was "
        "wrong is not a service."
    )

    flagged_only = st.checkbox("Only figures flagged during extraction")
    search = st.text_input("Filter by metric or label", "")

    frame = pd.DataFrame([{
        "Metric": o.metric,
        "Label in document": o.original_label,
        "Period": o.period_label,
        "Basis": o.basis.value,
        "Standardised": o.value_standardised,
        "Currency": o.currency,
        "Axis": o.breakdown_axis.value,
        "Document": o.document,
        "Source": o.source_ref,
        "Flagged": "yes" if o.needs_review else "",
    } for o in report.observations])

    if flagged_only:
        frame = frame[frame["Flagged"] == "yes"]
    if search:
        mask = (frame["Metric"].str.contains(search, case=False, na=False)
                | frame["Label in document"].str.contains(
                    search, case=False, na=False))
        frame = frame[mask]

    st.dataframe(frame, use_container_width=True, hide_index=True,
                 height=460)

    reasons = sorted({o.ambiguity_reason for o in report.observations
                      if o.ambiguity_reason})
    for reason in reasons:
        st.warning(reason)

# ---------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------

with tabs[4]:
    st.caption(
        "Actuals only, latest reported period per company. Currencies are "
        "shown and never converted. There is deliberately no overall "
        "score: the figures are comparable, the companies are not "
        "reducible to one number."
    )

    rows = []
    for other_slug in data.DEALS:
        other = data.load(other_slug)
        other_truth = data.truth(other_slug)
        actuals = [p for p in sorted(other.metrics["revenue"])
                   if any(o.period_label == p and o.basis.value == "actual"
                          for o in other.observations)]
        latest = actuals[-1] if actuals else None
        issues = other.issues
        rows.append({
            "Company": other_truth.name,
            "Sector": other_truth.subsector.split("/")[0].strip(),
            "Currency": other_truth.currency,
            "Latest actual": latest or "—",
            "Revenue (m)": money(other.metrics["revenue"].get(latest),
                                 other_truth.currency),
            "Growth": pct(other.metrics["revenue_growth"].get(latest)),
            "Recurring": pct(other.metrics["recurring_share"].get(latest)),
            "Gross margin": pct(other.metrics["gross_margin"].get(latest)),
            "EBITDA margin": pct(other.metrics["ebitda_margin"].get(latest)),
            "Rule of 40": pct(other.metrics["rule_of_40"].get(latest)),
            "Errors": sum(1 for i in issues
                          if i.severity == Severity.ERROR),
            "Disagreements": sum(1 for i in issues
                                 if i.severity == Severity.DISAGREE),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True)

    st.markdown(
        "Three different year ends sit in that table. Larkspur's FY24 runs "
        "July 2023 to June 2024 and Calderwood's April 2023 to March 2024, "
        "so the periods are labelled identically and cover different "
        "twelve-month windows. Every observation stores real start and end "
        "dates for that reason."
    )
