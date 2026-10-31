"""Penalty calculations as sources: the base provision and each increase or decrease are
fetched (so they are sources too), their words read in calc/penalty.py, and the resulting
range written out with the phrases it came from. A provision whose words cannot be read is
named in a warning instead of being guessed.

The model names the provisions, and names them unreliably (the same question gave the weapon
increase twice, an unrelated article, the plain threat paragraph instead of the armed one, or
no increase at all). So the case's label decides: its words that the base provision lacks
("with a weapon" for injury) must be found in a provision of the same article, which then
becomes the base (a paragraph with its own range) or an increase (an item with a ratio); a
named provision without those words is left out, and a case whose words are found nowhere is
not computed."""

from __future__ import annotations

from fractions import Fraction

from legal_api.agent.sources import TITLE_PREFIX, Source, SourceFinder
from legal_api.calc.penalty import (
    Range,
    Ratio,
    apply,
    distinctive,
    duration_text,
    items,
    paragraph,
    paragraph_numbers,
    read_range,
    read_ratio,
    stems,
)
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import penalty_terms

MAX_MODIFIERS = 4


def _where(source: Source | None, spec: dict) -> str:
    """The article's citation with its paragraph and item ("... m. 86/3-e")."""
    name = source.evidence.citation if source else f"{spec.get('law', '')} m. {spec.get('article', '')}"
    if spec.get("paragraph"):
        name += f"/{spec['paragraph']}"
    if spec.get("item"):
        name += f"-{spec['item']}"
    return name


def _fraction(f: Fraction) -> str:
    return f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)


def _ratio_line(r: Ratio, where: str) -> str:
    w = penalty_terms()["words"]
    key = f"{r.kind}_{r.shape}"
    return w[key].format(law_article=where, phrase=r.phrase.strip(), fraction=_fraction(r.high),
                         low_fraction=_fraction(r.low), high_fraction=_fraction(r.high))


def render(label: str, bases: list[tuple[Range, str]], ratios: list[tuple[Ratio, str]],
           notes: list[str]) -> str:
    """The ratios once, then each base range with its result."""
    w = penalty_terms()["words"]
    lines = [w["title"].format(label=label), *(_ratio_line(r, at) for r, at in ratios)]
    for base, at in bases:
        lines.append(w["base"].format(law_article=at, phrase=base.phrase,
                                      low=duration_text(base.low), high=duration_text(base.high)))
        if base.fine:
            lines.append(w["base_fine"])
        low, high = apply(base, [r for r, _ in ratios])
        lines.append(w["result"].format(low=duration_text(low), high=duration_text(high)))
    return "\n".join([*lines, *notes, w["method"]])


class _Case:
    """One offence or variant being assembled: its base range(s) and the ratios applied."""

    def __init__(self, label: str):
        self.label = label
        self.bases: list[tuple[Range, str]] = []
        self.ratios: list[tuple[Ratio, str]] = []
        self.keys: set[tuple] = set()       # provisions already applied
        self.words: set[str] = set()       # the label's distinctive words still to be found
        self.sought: set[str] = set()      # all of them, as first found missing from the base
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.raised = False                 # a ratio carrying the label's words applies

    def add_ratio(self, ratio: Ratio, at: str, key: tuple) -> None:
        if key not in self.keys:
            self.keys.add(key)
            self.ratios.append((ratio, at))


def _start(case: _Case, src: Source, spec: dict) -> None:
    """The base range of a spec; a ratio paragraph named as the base (86/3 for a weapon) is
    applied to each earlier paragraph with a range (86/1 and the lighter 86/2)."""
    text = paragraph(src.document, spec.get("paragraph"))
    at = _where(src, spec)
    title = next((ln[len(TITLE_PREFIX):] for ln in src.document.splitlines()
                  if ln.startswith(TITLE_PREFIX)), "")
    case.words = distinctive(case.label, f"{title}\n{text}")
    case.sought = set(case.words)
    if own := read_range(text):
        case.bases = [(own, at)]
        return
    ratio = read_ratio(text, spec.get("item"))
    number = str(spec.get("paragraph") or "")
    if ratio is None or not number.isdigit():
        return
    for n in range(1, int(number)):
        if rng := read_range(paragraph(src.document, n)):
            case.bases.append((rng, _where(src, {**spec, "paragraph": str(n), "item": ""})))
    if case.bases:
        case.add_ratio(ratio, at, (spec["law"], spec["article"], number))
        case.raised = True


def _fit(case: _Case, src: Source, spec: dict) -> None:
    """The provisions of the base article that carry the label's distinctive words. An item
    with a ratio is an increase. A paragraph with its own range is the case's base: in place
    of the named one when nothing raises it (the armed threat paragraph), beside it when a
    ratio does (the weapon raises both the ordinary and the lighter injury), so both results
    are given."""
    if not case.words:
        return
    found: list[tuple[Range, str]] = []
    for n in paragraph_numbers(src.document):
        text = paragraph(src.document, n)
        parts = items(text) or [("", text)]
        for letter, words in parts:
            if not stems(words) & case.words:
                continue
            at = _where(src, {**spec, "paragraph": n, "item": letter})
            ratio, own = read_ratio(text, letter or None), read_range(text)
            if own and not ratio:
                found.append((own, at))
            elif ratio:
                case.add_ratio(ratio, at, (spec["law"], spec["article"], n))
                case.raised = True
            else:
                continue
            case.words -= stems(words)
    if found and case.raised:
        case.bases += [b for b in found if b[1] not in {at for _, at in case.bases}]
    elif found:
        case.bases = found[-1:]


async def _modifier(case: _Case, mod: dict, finder: SourceFinder, out: list[Source]) -> None:
    """A provision the model named: applied only if it carries the label's words."""
    w = penalty_terms()["words"]
    src = await finder.article(mod["law"], mod["article"])
    at = _where(src, mod)
    text = paragraph(src.document, mod.get("paragraph")) if src else ""
    words = next((ws for letter, ws in items(text) if letter == mod.get("item")), text) \
        if mod.get("item") else text
    if case.words and not stems(words) & case.words:
        case.notes.append(w["ignored"].format(law_article=at, label=case.label))
        return
    if src and src not in out:
        out.append(src)
    key = (mod["law"], mod["article"], str(mod.get("paragraph") or ""))
    if ratio := read_ratio(text, mod.get("item")):
        case.add_ratio(ratio, at, key)
        case.raised = case.raised or bool(stems(words) & case.sought)
    elif own := read_range(text):
        # A qualified form with a range of its own (threat with a weapon) replaces the base.
        case.bases = [(own, at)]
    else:
        case.warnings.append(w["not_read"].format(law_article=at, what=w["what_ratio"]))
        return
    case.words -= stems(words)


async def penalty_sources(specs: list[dict], finder: SourceFinder,
                          ledger: EvidenceLedger) -> list[Source]:
    """Each named offence or variant: {label, law, article, paragraph, modifiers: [{law,
    article, paragraph, item}]}."""
    w = penalty_terms()["words"]
    out: list[Source] = []
    for spec in specs:
        if not (spec.get("law") and spec.get("article")):
            continue
        case = _Case(spec.get("label", ""))
        base_src = await finder.article(spec["law"], spec["article"])
        if base_src:
            _start(case, base_src, spec)
            for mod in (spec.get("modifiers") or [])[:MAX_MODIFIERS]:
                if mod.get("law") and mod.get("article"):
                    await _modifier(case, mod, finder, out)
            _fit(case, base_src, spec)
            if base_src not in out:
                out.append(base_src)
        base_at = _where(base_src, {**spec, "paragraph": "", "item": ""})
        if not case.bases:
            case.warnings.insert(0, w["not_read"].format(law_article=_where(base_src, spec),
                                                         what=w["what_range"]))
        elif case.sought and case.words == case.sought:
            # None of what makes this case special was found: the result would be the plain
            # offence's range under the special case's name.
            case.warnings.append(w["not_found"].format(label=case.label, law_article=base_at))
        text = "\n".join([w["title"].format(label=case.label), *case.warnings]) if case.warnings \
            else render(case.label, case.bases, case.ratios, case.notes)
        key = "|".join([*(at for _, at in case.bases), *(at for _, at in case.ratios)])
        evidence = ledger.add_calculation(source_id=f"calc:penalty:{case.label}:{key}",
                                          citation=w["citation"].format(label=case.label), text=text)
        out.append(Source(evidence, text))
    return out
