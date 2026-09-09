"""Deterministic filler prose for synthetic CIMs.

Two jobs.

First, length: a real CIM runs to 80-100 pages, and a fixture short
enough to fit in one model call would let us build a pipeline that never
exercises chunking — which would work in a demo against a hosted model
and fail on exactly the deals that require the local one.

Second, and more important: **distraction**. Eighty pages of obviously
irrelevant boilerplate is easier to retrieve from than twenty pages where
several sections all plausibly discuss revenue. The paragraph pools below
are written to be near-misses, and the DECOY_FIGURES are currency amounts
that an extractor must NOT mistake for the financial summary.

Everything here is deterministic: the same seed produces the same
document, so a fixture never changes underneath a stored answer key.
"""

from __future__ import annotations

import random

# Currency amounts that appear in the narrative and are NOT company
# revenue. An extractor that grabs the nearest plausible figure to the
# word "revenue" fails on these.
DECOY_FIGURES: list[tuple[str, str]] = [
    ("largest_account_arr", "£2.1m"),
    ("market_size", "£4.2bn"),
    ("series_a", "£6.5m"),
    ("series_b", "£14.0m"),
    ("emea_pipeline", "£9.7m"),
    ("rd_tax_credit", "£0.4m"),
    ("deferred_income", "£5.8m"),
    ("largest_contract_tcv", "£3.4m"),
]

_COMMERCIAL = [
    "Contracts are typically written on three-year terms with annual "
    "uplift provisions linked to a published inflation index, subject to "
    "a stated cap. Renewal is by default rather than by re-tender.",
    "The company sells directly in its home market and through two "
    "referral partners in continental Europe. Partner-originated business "
    "carries a commission recognised over the life of the contract.",
    "Pricing is per seat with a platform fee that scales in bands by "
    "gross written premium. Management notes that the banding has not "
    "been revised since 2021 and considers this an area of opportunity.",
    "The largest single account contributes £2.1m of annual recurring "
    "revenue and has been a customer since 2018. No other account exceeds "
    "six per cent of the total.",
    "Sales cycles average four to seven months for new logos and under "
    "sixty days for expansion within an existing group.",
    "A land-and-expand motion is evident across the broker groups, where "
    "an initial deployment in one trading division typically extends to "
    "two or three further divisions within eighteen months.",
]

_MARKET = [
    "Management sizes the addressable market at £4.2bn, comprising "
    "commercial broking technology spend across the United Kingdom, "
    "Ireland and the Benelux region.",
    "Regulatory attention on pricing practices has increased the "
    "willingness of brokers to invest in documented, auditable rating "
    "processes rather than spreadsheet-based methods.",
    "The competitive set divides between incumbent policy administration "
    "vendors extending into analytics, and smaller specialists. The "
    "company positions itself in the latter group.",
    "Industry consolidation among brokers has produced larger groups with "
    "more complex portfolios, which management identifies as the primary "
    "structural driver of demand.",
    "Adoption in the Benelux region is judged to lag the United Kingdom "
    "by approximately three years, which management presents as a timing "
    "opportunity rather than a structural difference.",
]

_OPERATIONS = [
    "Engineering, product and customer success functions are organised "
    "into cross-functional teams aligned to customer segments rather than "
    "to components of the platform.",
    "Release cadence is fortnightly, with feature flags used to stage "
    "changes across the customer base. Rollback is automated.",
    "Support operates during business hours in the home market with an "
    "on-call rotation covering out-of-hours incidents affecting "
    "production availability.",
    "Onboarding a new customer takes six to ten weeks, of which the "
    "majority is spent on data mapping rather than on configuration.",
    "Staff turnover has averaged eleven per cent over the last three "
    "years, below the sector benchmark cited by management.",
]

_FINANCE_ADJACENT = [
    "The company raised £6.5m in a Series A round in 2019 and a further "
    "£14.0m in 2022. Both rounds were led by institutional investors who "
    "remain on the register.",
    "Deferred income at the most recent year end stood at £5.8m, "
    "reflecting the annual-in-advance billing convention applied to the "
    "majority of subscription contracts.",
    "Research and development tax credits of £0.4m were recognised in the "
    "most recent financial year and are presented within other income.",
    "Working capital is modestly negative on a normalised basis, "
    "reflecting the billing convention described above.",
    "The qualified pipeline across the EMEA region stands at £9.7m of "
    "annual contract value, weighted by management's own probability "
    "assessment.",
    "The largest contract signed to date carried total contract value of "
    "£3.4m across a five-year term.",
]

_GOVERNANCE = [
    "The board comprises the two founders, the chief financial officer, "
    "two investor directors and one independent non-executive appointed "
    "in the prior year.",
    "Board meetings are held monthly against a standing agenda. Committee "
    "structures are limited to an audit committee.",
    "The company maintains a delegated authority matrix reviewed annually "
    "by the board.",
    "No related party transactions have been identified beyond directors' "
    "remuneration disclosed in the statutory accounts.",
]

POOLS = {
    "commercial": _COMMERCIAL,
    "market": _MARKET,
    "operations": _OPERATIONS,
    "finance_adjacent": _FINANCE_ADJACENT,
    "governance": _GOVERNANCE,
}

APPENDIX_TITLES = [
    "Appendix A — Customer Contract Summary",
    "Appendix B — Technology Architecture",
    "Appendix C — Information Security and Compliance",
    "Appendix D — Intellectual Property Register",
    "Appendix E — Employee Census and Remuneration",
    "Appendix F — Property and Lease Obligations",
    "Appendix G — Insurance Cover",
    "Appendix H — Environmental, Social and Governance",
    "Appendix I — Litigation and Contingencies",
    "Appendix J — Regulatory Correspondence",
    "Appendix K — Historical Funding History",
    "Appendix L — Glossary of Terms",
]


def paragraphs(count: int, seed: int = 20260909) -> list[str]:
    """Deterministic sequence of filler paragraphs drawn across all pools.

    Cycling across pools rather than exhausting one at a time keeps
    finance-adjacent text scattered through the document, so a retrieval
    step cannot succeed simply by finding the one place money is
    discussed.
    """
    rng = random.Random(seed)
    keys = sorted(POOLS)
    out: list[str] = []
    while len(out) < count:
        for key in keys:
            pool = POOLS[key]
            out.append(pool[rng.randrange(len(pool))])
            if len(out) >= count:
                break
    return out
