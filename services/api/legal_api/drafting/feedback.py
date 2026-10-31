"""How the lawyer's corrections move their style preferences.

Two signals: the adjustment buttons on a draft (shorter, longer, plainer, more formal) and the
lawyer's own edits, read when they save a draft. Each moves the preferences part of the way,
so one correction shifts the next draft without overturning what the samples show.
"""

from __future__ import annotations

from dataclasses import replace

from legal_api.drafting.profile import Preferences, register_of
from legal_api.drafting.style import measure, petition_part

ACTIONS = ("shorter", "longer", "plainer", "formal")
STEP = {"shorter": 0.8, "longer": 1.25}
EDIT_WEIGHT = 0.5          # how far one saved edit moves the length preference
MIN_CHANGE = 0.1           # length changes below 10% are not a preference


def apply_action(prefs: Preferences, action: str) -> Preferences:
    if action in STEP:
        return replace(prefs, length_factor=prefs.length_factor * STEP[action])
    if action == "plainer":
        return replace(prefs, register_shift=max(-2, prefs.register_shift - 1))
    if action == "formal":
        return replace(prefs, register_shift=min(2, prefs.register_shift + 1))
    raise ValueError(f"unknown action {action}")


def learn_from_edit(prefs: Preferences, drafted: str, saved: str) -> Preferences:
    """The length and register the lawyer moved the draft to."""
    before, after = measure(petition_part(drafted)), measure(petition_part(saved))
    factor = prefs.length_factor
    if before.words and after.words:
        ratio = after.words / before.words
        if abs(ratio - 1) >= MIN_CHANGE:
            factor *= ratio ** EDIT_WEIGHT
    shift = prefs.register_shift + (register_of(after.formal_per_1000)
                                    - register_of(before.formal_per_1000))
    return replace(prefs, length_factor=factor, register_shift=max(-2, min(2, shift)))
