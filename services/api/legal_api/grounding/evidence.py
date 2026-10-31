"""Evidence ledger: every source the model may cite during one answer.

The model only ever sees and writes evidence keys (E1, E2, ...). Citation strings are built
here from the sources' structured fields, so the model cannot alter a case number or date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from legal_api.grounding.normalize import tr_title
from legal_api.locale import citation_template
from legal_api.sources.types import Article, Court, DecisionRef

EvidenceKind = Literal["decision", "article", "calculation"]


@dataclass(frozen=True)
class Evidence:
    key: str
    kind: EvidenceKind
    citation: str
    url: str
    text: str
    case_numbers: frozenset[str] = frozenset()   # esas / karar / application numbers
    article_number: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _tr_date(value: date | str | None) -> str:
    if value is None:
        return "-"
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return d.strftime("%d.%m.%Y")


def decision_citation(chamber: str, case_no: str | None, decision_no: str | None,
                      decision_date: date | str | None, court: Court | None = None) -> str:
    if court is Court.AYM_BIREYSEL:
        return citation_template("decision_aym_individual").format(
            chamber=chamber, case_no=case_no or "-", date=_tr_date(decision_date))
    return citation_template("decision").format(
        chamber=chamber, case_no=case_no or "-", decision_no=decision_no or "-",
        date=_tr_date(decision_date))


def _lowercase_words() -> frozenset[str]:
    return frozenset(citation_template("title_lowercase_words").split())


def article_citation(article: Article) -> str:
    statute = article.statute
    key = "article" if statute.number and statute.number.isdigit() and len(statute.number) <= 5 \
        else "article_no_number"
    title = tr_title(statute.title, _lowercase_words())
    return citation_template(key).format(number=statute.number, title=title,
                                         article=article.number)


class EvidenceLedger:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._by_source: dict[str, str] = {}

    def __iter__(self):
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: str) -> Evidence | None:
        return self._items.get(key)

    def _add(self, source_id: str, **fields) -> Evidence:
        if source_id in self._by_source:
            return self._items[self._by_source[source_id]]
        key = f"E{len(self._items) + 1}"
        evidence = Evidence(key=key, **fields)
        self._items[key] = evidence
        self._by_source[source_id] = key
        return evidence

    def add_decision(self, *, source_id: str, chamber: str, case_no: str | None,
                     decision_no: str | None, decision_date: date | str | None, url: str,
                     text: str, court: Court | None = None) -> Evidence:
        return self._add(
            source_id, kind="decision",
            citation=decision_citation(chamber, case_no, decision_no, decision_date, court),
            url=url, text=text,
            case_numbers=frozenset(n for n in (case_no, decision_no) if n),
        )

    def add_decision_ref(self, ref: DecisionRef, text: str) -> Evidence:
        return self.add_decision(source_id=ref.source_id, chamber=ref.chamber,
                                 case_no=ref.case_no, decision_no=ref.decision_no,
                                 decision_date=ref.decision_date, url=ref.url, text=text,
                                 court=ref.court)

    def add_article(self, article: Article) -> Evidence:
        return self._add(
            f"article:{article.article_id}", kind="article",
            citation=article_citation(article), url=article.url, text=article.text,
            article_number=article.number,
        )

    def add_calculation(self, *, source_id: str, citation: str, text: str) -> Evidence:
        """A result computed in code (calc/), shown and cited like any source."""
        return self._add(source_id, kind="calculation", citation=citation, url="", text=text)
