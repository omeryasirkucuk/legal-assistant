"""What the writer is told when it drafts a petition: the type's outline, the articles that
set its required contents, the lawyer's style and one of their own petitions to imitate."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_api.drafting.cases import CaseKind
from legal_api.drafting.profile import (
    Preferences,
    Sample,
    closest_sample,
    excerpt,
    style_instruction,
    targets,
)
from legal_api.drafting.types import PetitionType
from legal_api.prompts import prompt

PASSAGE_CHARS = 900     # of each decision's passage shown beside its ground


@dataclass
class StyleBook:
    """A lawyer's samples, preferences and stated rules, loaded before an answer runs."""
    samples: list[Sample] = field(default_factory=list)
    preferences: Preferences = field(default_factory=Preferences)
    rules: list[str] = field(default_factory=list)
    learnt: list[str] = field(default_factory=list)   # preferences relevant to this case
    asking: dict = field(default_factory=dict)  # how often the lawyer answered or skipped questions
    area: str = "other"        # the case's area of law and kind (set from the understanding),
    case_kind: str | None = None   # to choose a sample of the same matter


def brief(ptype: PetitionType | None, book: StyleBook, required_keys: list[str],
          kind: CaseKind | None = None, precedents: dict | None = None,
          requests: list[str] | None = None) -> str:
    """`kind`: the kind of case, when it is one with its own guide; `precedents`: the court
    decisions found for each ground of the case (ground -> sources). Each is given with its
    citation and the passage that bears on the ground: a smaller writer given only the keys
    cited no decision at all."""
    type_id = ptype.id if ptype else None
    t = targets(book.samples, book.preferences, type_id, kind.words if kind else None)
    parts = [prompt("draft_brief")]
    if ptype:
        parts.append(f"<petition_type>{ptype.name}</petition_type>\n<outline>\n{ptype.outline}"
                     f"\n</outline>")
        if ptype.practice:
            parts.append(f"<practice_notes>\n{ptype.practice}\n</practice_notes>")
    if kind:
        parts.append(kind.guide())
    if requests:
        parts.append("<requests_to_make>\n" + "\n".join(f"- {r}" for r in requests)
                     + "\n</requests_to_make>")
    if precedents:
        parts.append("<ground_precedents>\n" + "\n".join(
            f'<ground name="{ground}">\n' + "\n".join(
                f"[[{s.evidence.key}]] {s.evidence.citation}\n{s.document[:PASSAGE_CHARS]}"
                for s in sources) + "\n</ground>"
            for ground, sources in precedents.items()) + "\n</ground_precedents>")
    if required_keys:
        parts.append("<required_contents_sources>" + ", ".join(required_keys)
                     + "</required_contents_sources>")
    parts.append(style_instruction(t, book.rules))
    if book.learnt:
        parts.append("<learned_preferences>\n" + "\n".join(f"- {p}" for p in book.learnt)
                     + "\n</learned_preferences>")
    sample, same_area = closest_sample(book.samples, type_id, book.area, book.case_kind)
    if sample:
        kind = "" if same_area else ' kind="other_area"'
        parts.append(f"<own_petition_example{kind}>\n{excerpt(sample)}\n</own_petition_example>")
    return "\n".join(parts)
