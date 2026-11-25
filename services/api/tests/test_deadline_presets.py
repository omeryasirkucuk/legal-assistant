import json
from pathlib import Path

from legal_api.calc.sources import states_length
from legal_api.locale import deadline_rules

ARTICLES = Path(__file__).parent / "fixtures" / "tr" / "deadline_preset_articles.json"


def test_every_preset_period_is_stated_by_its_own_article():
    articles = {(row["law"], row["article"]): row["excerpt"]
                for row in json.loads(ARTICLES.read_text(encoding="utf-8"))}
    for preset in deadline_rules()["presets"]:
        text = articles[preset["law"], preset["article"]]
        assert states_length(text, preset["amount"], preset["unit"]), preset["citation"]
