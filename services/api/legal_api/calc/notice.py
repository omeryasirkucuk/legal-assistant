"""A period counted from a notice, as a lawyer enters it: when and how the notice came, the
period, and the branch of law, which decides whether and how the judicial recess extends it
(locales/tr/deadline_rules.json, each rule with its source).

- service at a hearing (tefhim) or by hand: the period runs from that day;
- electronic service: the notice counts as served at the end of the fifth day after it
  reached the address, and the period runs from then;
- the recess extends a period by the branch's days, or not at all (enforcement); for
  arbitration it depends on the rules agreed, so the lawyer is told to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from legal_api.calc.deadlines import Deadline, Unit, compute
from legal_api.locale import deadline_rules

Service = Literal["electronic", "hearing", "physical"]
Branch = Literal["civil", "criminal", "enforcement", "administrative", "arbitration"]


@dataclass
class FromNotice:
    received: date
    served: date             # the day the period counts from
    service: Service
    branch: Branch
    law: str                 # the recess rule's article, empty when none
    deadline: Deadline
    notes: list[str]         # codes: "arbitration_rules", "detention"


def from_notice(received: date, service: Service, amount: int, unit: Unit,
                branch: Branch) -> FromNotice:
    rules = deadline_rules()
    served = received
    if service == "electronic":
        served = received + timedelta(days=rules["electronic_service_days"])
    rule = rules["branches"][branch]
    extension = rule["recess_extension"]
    deadline = compute(served, amount, unit, recess=extension is not None, extension=extension)
    notes = {"arbitration": ["arbitration_rules"], "criminal": ["detention"]}.get(branch, [])
    return FromNotice(received, served, service, branch, rule["law"], deadline, notes)
