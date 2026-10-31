"""The lawyer's style: targets for a draft from their own petitions and their corrections.

Targets are the median of the lawyer's samples (of the same petition type when there are
some, else all), then moved by the preferences that feedback changes: a length factor and a
register shift. Without samples a draft uses house defaults, so the first draft is usable
before anything is learnt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from legal_api.drafting.style import WORDS_PER_PAGE, Style, measure
from legal_api.locale import style_terms
from legal_api.prompts import prompt

REGISTERS = ("plain", "balanced", "formal")
# Formal or archaic words per 1,000 words at the borders between the registers.
REGISTER_BORDERS = (8.0, 25.0)
DEFAULT = Style(words=900, words_per_sentence=22.0, formal_per_1000=15.0,
                closing="arz ve talep ederiz")
SAMPLE_EXCERPT_CHARS = 4000
# Lengths the lawyer can pick in plain words, as the words of the petition.
LENGTHS = {"short": 450, "medium": 900, "long": 1600}
MIN_FACTOR, MAX_FACTOR = 0.4, 2.5


@dataclass
class Sample:
    petition_type: str | None
    style: dict
    text: str
    description: str = ""
    closeness: float | None = None     # similarity in meaning to the case being drafted
    area: str = "other"                # area of law, as the model read it (sample_profile)
    case_kind: str | None = None       # drafting.cases id when the case is one of those kinds
    matter: str = ""                   # the matter in a few words ("uncontested divorce")


@dataclass
class Preferences:
    length_factor: float = 1.0
    register_shift: int = 0          # steps toward formal (+) or plain (-)
    # Chosen by the lawyer in plain words; replaces what the samples show, and the buttons
    # and edits move on from it.
    length: str | None = None        # LENGTHS key
    register: str | None = None      # REGISTERS item

    @classmethod
    def of(cls, data: dict | None) -> Preferences:
        data = data or {}
        length = data.get("length") if data.get("length") in LENGTHS else None
        register = data.get("register") if data.get("register") in REGISTERS else None
        return cls(float(data.get("length_factor", 1.0)), int(data.get("register_shift", 0)),
                   length, register)

    def as_dict(self) -> dict:
        return {"length_factor": round(self.length_factor, 3),
                "register_shift": self.register_shift,
                "length": self.length, "register": self.register}


@dataclass
class Targets:
    words: int
    words_per_sentence: float
    register: str
    headings: list[str] = field(default_factory=list)
    closing: str = DEFAULT.closing or ""
    learnt_from: int = 0              # samples behind these targets


def register_of(formal_per_1000: float) -> int:
    return sum(formal_per_1000 >= b for b in REGISTER_BORDERS)


def _common_headings(styles: list[dict]) -> list[str]:
    """Headings used in at least half of the samples, in the order the first one uses them."""
    counts = Counter(h for s in styles for h in dict.fromkeys(s.get("headings", [])))
    keep = {h for h, n in counts.items() if n * 2 >= len(styles)}
    order = next((s["headings"] for s in styles if s.get("headings")), [])
    return [h for h in order if h in keep]


def targets(samples: list[Sample], prefs: Preferences, petition_type: str | None,
            default_words: int | None = None) -> Targets:
    """`default_words`: the usual length of this kind of case, used when the lawyer has no
    samples (a contested divorce petition runs far longer than a payment-order objection)."""
    same = [s for s in samples if s.petition_type == petition_type]
    pool = [s.style for s in (same or samples) if s.style.get("words")]
    if pool:
        words = median(s["words"] for s in pool)
        wps = median(s["words_per_sentence"] for s in pool)
        register = register_of(median(s["formal_per_1000"] for s in pool))
        closings = Counter(s["closing"] for s in pool if s.get("closing"))
        closing = closings.most_common(1)[0][0] if closings else DEFAULT.closing
        headings = _common_headings(pool)
    else:
        words, wps = default_words or DEFAULT.words, DEFAULT.words_per_sentence
        register, closing, headings = register_of(DEFAULT.formal_per_1000), DEFAULT.closing, []
    if prefs.length:
        words = LENGTHS[prefs.length]
    if prefs.register:
        register = REGISTERS.index(prefs.register)
    factor = min(MAX_FACTOR, max(MIN_FACTOR, prefs.length_factor))
    register = min(len(REGISTERS) - 1, max(0, register + prefs.register_shift))
    return Targets(int(round(words * factor, -1)), round(wps, 0), REGISTERS[register],
                   headings, closing or "", len(pool))


def style_instruction(t: Targets, rules: list[str]) -> str:
    registers = style_terms()["registers"]
    return (prompt("draft_style")
            .replace("{words}", str(t.words))
            .replace("{pages}", f"{max(0.5, t.words / WORDS_PER_PAGE):.1f}")
            .replace("{words_per_sentence}", f"{t.words_per_sentence:g}")
            .replace("{register}", registers[t.register])
            .replace("{headings}", ", ".join(t.headings) if t.headings else "-")
            .replace("{closing}", t.closing)
            .replace("{rules}", "\n".join(f"- {r}" for r in rules)))


def closest_sample(samples: list[Sample], petition_type: str | None, area: str = "other",
                   case_kind: str | None = None) -> tuple[Sample | None, bool]:
    """A sample of the same petition type to imitate (its style and structure, not its
    facts), and whether it is about the same kind of matter as the case.

    The narrowest match decides first: samples of the case's kind (a contested divorce, not
    an agreed one: the two are written very differently), else of its area of law; among
    them the closest in meaning to the case, else the longest, as it shows the most habits.
    Meaning alone told a dismissal case from a divorce sample by 0.01, and with no sample of
    the case's matter it handed over another matter's petition; such a sample is returned
    marked, and the writer takes only its language from it."""
    same = [s for s in samples if s.petition_type == petition_type]
    of_kind = [s for s in same if case_kind and s.case_kind == case_kind]
    if of_kind:
        return max(of_kind, key=_rank), True
    of_area = [s for s in same if area != "other" and s.area == area]
    if of_area:
        # Same area, other kind (an agreed divorce for a contested one): language only.
        return max(of_area, key=_rank), case_kind is None
    if same and (case_kind or area != "other"):
        return max(same, key=_rank), False
    return max(same, key=_rank, default=None), True


def _rank(s: Sample) -> tuple[float, int]:
    return s.closeness or 0.0, len(s.text)


def excerpt(sample: Sample) -> str:
    return sample.text[:SAMPLE_EXCERPT_CHARS]


def sample_of(petition_type: str | None, text: str, description: str = "") -> Sample:
    return Sample(petition_type, measure(text).as_dict(), text, description)
