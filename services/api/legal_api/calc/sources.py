"""Calculations as sources of an answer: computed in code, written out step by step, and
cited like an article or a decision, so the writer copies dates instead of computing them.

The understanding step names each period (where it starts, how long, under which article);
the length is the one thing the model supplies, so it is checked against the article's own
text, and a length the article does not state is flagged in the calculation. Whether the
judicial recess applies is not taken from the model: when it changes the last day, both
days are given with the articles on the recess.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from legal_api.agent.sources import Source, SourceFinder
from legal_api.calc.deadlines import UNITS, Deadline, compute
from legal_api.calc.interest import KINDS as INTEREST_KINDS
from legal_api.calc.interest import compute as compute_interest
from legal_api.calc.interest_text import render as render_interest
from legal_api.calc.severance import Severance, compute_months
from legal_api.calc.severance import compute as compute_severance
from legal_api.calc.severance_text import ceiling_text
from legal_api.calc.severance_text import render as render_severance
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.grounding.normalize import tr_fold
from legal_api.locale import calculation_terms, number_words, severance_data

CIVIL_PROCEDURE = "6100"
RECESS_ARTICLES = ("103", "104")   # matters handled in the recess; periods it extends


def _day(d: date) -> tuple[str, str]:
    return d.strftime("%d.%m.%Y"), calculation_terms()["weekdays"][d.weekday()]


def states_length(article_text: str, amount: int, unit: str) -> bool:
    """Whether the article's text states the period (in words or digits, e.g. two weeks, 7 days)."""
    terms = calculation_terms()
    words = [w for w, n in number_words().items() if n == amount] + [str(amount)]
    if amount == 1:
        words.append(terms["one"])
    numbers = "|".join(map(re.escape, words))
    pattern = rf"(?<!\w)(?:{numbers})\s+{re.escape(terms['units'][unit])}"
    return re.search(pattern, tr_fold(article_text)) is not None


def render(label: str, d: Deadline, law_article: str, verified: bool | None,
           without_recess: Deadline | None = None) -> str:
    t = calculation_terms()
    unit = t["units"][d.unit]
    start, start_day = _day(d.start)
    lines = [t["title"].format(label=label),
             t["start"].format(start=start, weekday=start_day),
             t["length"].format(amount=d.amount, unit=unit, law_article=law_article)]
    if verified is not None:
        lines.append(t["length_verified"] if verified else
                     t["length_unverified"].format(amount=d.amount, unit=unit,
                                                   law_article=law_article))
    for code, values in d.steps:
        end, end_day = _day(values["end"])
        day = _day(values["day"])[0] if "day" in values else ""
        lines.append(t[code].format(end=end, weekday=end_day, day=day,
                                    name=values.get("name", "")))
    for code, values in d.warnings:
        day = _day(values["day"])[0] if "day" in values else ""
        lines.append(t[code].format(day=day, name=values.get("name", ""),
                                    year=values.get("year", "")))
    end, end_day = _day(d.end)
    if without_recess is not None and without_recess.end != d.end:
        other, other_day = _day(without_recess.end)
        lines.append(t["recess_unknown"].format(end=end, weekday=end_day, end_without=other,
                                                weekday_without=other_day))
    else:
        lines.append(t["result"].format(end=end, weekday=end_day))
    return "\n".join(lines)


async def deadline_sources(specs: list[dict], finder: SourceFinder, ledger: EvidenceLedger,
                           computed: list[dict] | None = None) -> list[Source]:
    """Each named period computed; its article fetched (so it is also a source) and its
    length checked against the article's text. `computed` receives each period's label and
    last day, so the lawyer can put it in a case file's deadlines with one click."""
    out: list[Source] = []
    for spec in specs:
        try:
            start = date.fromisoformat(spec["start_date"])
        except (KeyError, ValueError):
            continue
        if spec.get("unit") not in UNITS or int(spec.get("amount", 0)) <= 0:
            continue
        amount, unit = int(spec["amount"]), spec["unit"]
        article = await finder.article(spec["law"], spec["article"]) \
            if spec.get("law") and spec.get("article") else None
        verified = states_length(article.document, amount, unit) if article else None
        law_article = article.evidence.citation if article else \
            f"{spec.get('law', '')} m. {spec.get('article', '')}".strip()
        # Whether the recess applies is not left to the model (it called a money claim exempt):
        # when it changes the result both are given, with the articles that decide it.
        result = compute(start, amount, unit, True)
        other = compute(start, amount, unit, False)
        recess_matters = other.end != result.end
        text = render(spec.get("label", ""), result, law_article, verified,
                      other if recess_matters else None)
        if computed is not None:
            computed.append({"label": spec.get("label", ""), "due": result.end.isoformat(),
                             "without_recess": other.end.isoformat() if recess_matters else None})
        if recess_matters:
            for label in RECESS_ARTICLES:
                rule = await finder.article(CIVIL_PROCEDURE, label)
                if rule:
                    out.append(rule)
        evidence = ledger.add_calculation(
            source_id=f"calc:{spec.get('label')}:{start}:{amount}{unit}:{law_article}",
            citation=calculation_terms()["citation"].format(label=spec.get("label", "")),
            text=text)
        if article:
            out.append(article)
        out.append(Source(evidence, text))
    return out


SEVERANCE_ARTICLES = (("1475", "14"), ("4857", "17"))


async def severance_sources(spec: dict, finder: SourceFinder,
                            ledger: EvidenceLedger) -> list[Source]:
    """Return the calculation and legal sources for the model-extracted inputs."""
    calculated = severance_from_spec(spec)
    if calculated is None:
        return []
    result, assumed_end = calculated
    computation = severance_calculation(result, ledger, assumed_end=assumed_end)
    ceiling = severance_ceiling_source(result, ledger)
    out = [a for law, label in SEVERANCE_ARTICLES if (a := await finder.article(law, label))]
    return [computation, *([ceiling] if ceiling else []), *out]


def severance_from_spec(spec: dict) -> tuple[Severance, bool] | None:
    try:
        start = date.fromisoformat(spec["start_date"]) if spec.get("start_date") else None
        end = date.fromisoformat(spec["end_date"]) if spec.get("end_date") else None
        gross = Decimal(str(spec["gross_monthly"]))
        extras = Decimal(str(spec.get("extras_monthly") or 0))
        months = spec.get("service_months")
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return None
    if not gross.is_finite() or not extras.is_finite() or gross <= 0 or extras < 0:
        return None
    monthly = gross + extras
    if start and end:
        return (compute_severance(start, end, monthly), False) if start <= end else None
    if start or type(months) is not int or months <= 0:
        return None
    if end is None and spec.get("estimate_current_period") is not True:
        return None
    day = end or datetime.now(ZoneInfo("Europe/Istanbul")).date()
    return compute_months(months, day, monthly), end is None


def severance_calculation(result: Severance, ledger: EvidenceLedger, *,
                          assumed_end: bool) -> Source:
    text = render_severance(result, assumed_end=assumed_end)
    service = result.start or result.service.total_months
    evidence = ledger.add_calculation(
        source_id=f"calc:severance:{service}:{result.end}:{result.monthly}:{assumed_end}",
        citation=calculation_terms()["severance"]["citation"], text=text)
    return Source(evidence, text)


def severance_ceiling_source(result: Severance, ledger: EvidenceLedger) -> Source | None:
    if result.ceiling_period is None:
        return None
    text = ceiling_text(result)
    evidence = ledger.add_record(
        kind="official", source_id=f"severance-ceiling:{result.ceiling_period[0]}",
        citation=calculation_terms()["severance"]["ceiling_source"],
        url=severance_data()["ceiling_source_url"], text=text)
    return Source(evidence, text)


async def interest_sources(spec: dict, ledger: EvidenceLedger) -> list[Source]:
    """Interest on a principal over a span; both kinds when the answer cannot tell which
    applies (statutory interest, or the advance rate in commercial matters)."""
    try:
        principal = Decimal(str(spec["principal"]))
        start = date.fromisoformat(spec["start_date"])
        end = date.fromisoformat(spec["end_date"]) if spec.get("end_date") else date.today()
    except (KeyError, ValueError, ArithmeticError):
        return []
    if principal <= 0 or end <= start:
        return []
    kinds = INTEREST_KINDS if spec.get("kind") not in INTEREST_KINDS else (spec["kind"],)
    text = render_interest([compute_interest(principal, start, end, k) for k in kinds])
    evidence = ledger.add_calculation(
        source_id=f"calc:interest:{principal}:{start}:{end}:{'/'.join(kinds)}",
        citation=calculation_terms()["interest"]["citation"], text=text)
    return [Source(evidence, text)]
