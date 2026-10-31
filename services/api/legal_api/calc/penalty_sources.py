"""Penalty calculations as sources: the base provision and each increase or decrease are
fetched (so they are sources too), their words read in calc/penalty.py, and the resulting
range written out with the phrases it came from. A provision whose words cannot be read is
named in a warning instead of being guessed."""

from __future__ import annotations

from fractions import Fraction

from legal_api.agent.sources import Source, SourceFinder
from legal_api.calc.penalty import (
    Range,
    Ratio,
    apply,
    duration_text,
    paragraph,
    read_range,
    read_ratio,
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


def render(label: str, bases: list[tuple[Range, str]], ratios: list[tuple[Ratio, str]]) -> str:
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
    return "\n".join([*lines, w["method"]])


def _bases(src: Source, spec: dict) -> tuple[list[tuple[Range, str]], list[tuple[Ratio, str]]]:
    """The base range(s) of a spec, and a ratio when the paragraph named is itself one.

    Named a paragraph that raises "the penalty" of the ones before it (TCK 86/3 for a
    weapon), the ratio applies to each earlier paragraph with a range of its own (86/1 and the
    lighter 86/2), which is the comparison a lawyer needs."""
    text = paragraph(src.document, spec.get("paragraph"))
    at = _where(src, spec)
    if own := read_range(text):
        return [(own, at)], []
    ratio = read_ratio(text, spec.get("item"))
    number = str(spec.get("paragraph") or "")
    if ratio is None or not number.isdigit():
        return [], []
    earlier = []
    for n in range(1, int(number)):
        if rng := read_range(paragraph(src.document, n)):
            earlier.append((rng, _where(src, {**spec, "paragraph": str(n), "item": ""})))
    return earlier, [(ratio, at)] if earlier else []


async def penalty_sources(specs: list[dict], finder: SourceFinder,
                          ledger: EvidenceLedger) -> list[Source]:
    """Each named offence or variant: {label, law, article, paragraph, modifiers: [{law,
    article, paragraph, item}]}."""
    w = penalty_terms()["words"]
    out: list[Source] = []
    for spec in specs:
        if not (spec.get("law") and spec.get("article")):
            continue
        base_src = await finder.article(spec["law"], spec["article"])
        bases, ratios = _bases(base_src, spec) if base_src else ([], [])
        warnings: list[str] = []
        for mod in (spec.get("modifiers") or [])[:MAX_MODIFIERS]:
            if not (mod.get("law") and mod.get("article")):
                continue
            src = await finder.article(mod["law"], mod["article"])
            at = _where(src, mod)
            text = paragraph(src.document, mod.get("paragraph")) if src else ""
            if src and src not in out:
                out.append(src)
            if ratio := read_ratio(text, mod.get("item")):
                ratios.append((ratio, at))
            elif own := read_range(text):
                # A qualified form with a range of its own (threat with a weapon) replaces
                # the base instead of raising it; the model sometimes names it as a modifier.
                bases = [(own, at)]
            else:
                warnings.append(w["not_read"].format(law_article=at, what=w["what_ratio"]))
        if base_src and base_src not in out:
            out.append(base_src)
        if not bases:
            warnings.insert(0, w["not_read"].format(law_article=_where(base_src, spec),
                                                    what=w["what_range"]))
        label = spec.get("label", "")
        if warnings:
            text = "\n".join([w["title"].format(label=label), *warnings])
        else:
            text = render(label, bases, ratios)
        key = "|".join([*(at for _, at in bases), *(at for _, at in ratios)])
        evidence = ledger.add_calculation(source_id=f"calc:penalty:{label}:{key}",
                                          citation=w["citation"].format(label=label), text=text)
        out.append(Source(evidence, text))
    return out
