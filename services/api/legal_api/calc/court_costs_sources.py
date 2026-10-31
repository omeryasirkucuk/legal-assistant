"""A fee and appeal calculation as a source: what is due when filing, the decision fee, and
whether the decision can be appealed, with the articles that set them fetched as sources."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from legal_api.agent.sources import Source, SourceFinder
from legal_api.calc.court_costs import MEASURES, appeal, fees
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import court_costs

ARTICLES = (("492", "28"), ("6100", "ek 1"), ("6100", "341"), ("6100", "362"))


def _tl(x: Decimal | int) -> str:
    """Turkish money format: 1.234,50."""
    text = f"{Decimal(x):,.2f}" if isinstance(x, Decimal) else f"{x:,}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def render(value: Decimal | None, court: str, measure: str, bodily_harm: bool,
           filed: date | None, today: date) -> str:
    data = court_costs()
    w, year = data["words"], data["fees_year"]
    f = fees(value, court, measure, bodily_harm)
    lines = [w["title"]]
    if value:
        lines.append(w["value"].format(value=_tl(value)))
    lines.append(w["application"].format(court=w["courts"].get(court, w["courts"]["asliye"]),
                                         amount=_tl(f.application), year=year))
    if measure == "unknown" and f.proportional and f.fixed:
        lines.append(w["unknown_measure"])
    if f.proportional is not None:
        lines.append(w["proportional"].format(rate=data["fees"]["decision_rate_per_mille"].replace(".", ","),
                                              total=_tl(f.proportional),
                                              minimum=_tl(Decimal(data["fees"]["decision_minimum"]))))
        lines.append(w["advance_harm" if bodily_harm else "advance"].format(
            amount=_tl(f.advance), rest=_tl(f.proportional - f.advance)))
        lines.append(w["filing_total"].format(amount=_tl(f.application + f.advance)))
    if f.fixed is not None:
        lines.append(w["fixed"].format(amount=_tl(f.fixed)))
        if f.proportional is None:
            lines.append(w["filing_total"].format(amount=_tl(f.application + f.fixed)))
    if today.year != year:
        lines.append(w["fees_old"].format(fees_year=year, year=today.year))
    if value:
        lines += _appeal_lines(value, filed or today, filed is None)
    lines.append(w["appeal_fees"].format(year=year, istinaf=_tl(Decimal(data["fees"]["appeal_istinaf"])),
                                         temyiz=_tl(Decimal(data["fees"]["appeal_temyiz"])),
                                         upper=_tl(Decimal(data["fees"]["application"]["upper"]))))
    return "\n".join(lines)


def _appeal_lines(value: Decimal, filed: date, guessed: bool) -> list[str]:
    w = court_costs()["words"]
    a = appeal(value, filed)
    if a is None:
        return [w["year_not_covered"].format(year=filed.year)]
    args = {"value": _tl(value), "year": a.year}
    lines = [w["appeal_year"].format(year=a.year)]
    if guessed:
        lines.append(w["year_unknown"].format(year=a.year))
    lines.append(w["istinaf_open" if a.istinaf else "istinaf_closed"].format(**args, limit=_tl(a.istinaf_limit)))
    lines.append(w["temyiz_open" if a.temyiz else "temyiz_closed"].format(**args, limit=_tl(a.temyiz_limit)))
    if a.hearing:
        lines.append(w["hearing_open"].format(**args, limit=_tl(a.hearing_limit)))
    lines.append(w["partial"])
    return lines


async def court_cost_sources(spec: dict, finder: SourceFinder,
                             ledger: EvidenceLedger) -> list[Source]:
    """`spec`: {value, court, measure, bodily_harm, filed_on} from the understanding step."""
    try:
        value = Decimal(str(spec.get("value") or 0)) or None
        filed = date.fromisoformat(spec["filed_on"]) if spec.get("filed_on") else None
    except (InvalidOperation, ValueError):
        return []
    measure = spec.get("measure") if spec.get("measure") in MEASURES else "unknown"
    text = render(value, spec.get("court") or "asliye", measure, bool(spec.get("bodily_harm")),
                  filed, date.today())
    out = [a for law, label in ARTICLES if (a := await finder.article(law, label))]
    evidence = ledger.add_calculation(
        source_id=f"calc:court:{value}:{spec.get('court')}:{measure}:{filed}",
        citation=court_costs()["words"]["citation"], text=text)
    return [*out, Source(evidence, text)]
