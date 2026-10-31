import asyncpg

from legal_api.calc.sources import states_length
from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.locale import deadline_rules


async def test_every_preset_period_is_stated_by_its_own_article():
    conn = await asyncpg.connect(asyncpg_dsn())
    try:
        for p in deadline_rules()["presets"]:
            text = await conn.fetchval(
                "SELECT text FROM statute_articles WHERE law_number = $1 AND label = $2",
                p["law"], p["article"])
            assert text is not None, p["citation"]
            assert states_length(text, p["amount"], p["unit"]), p["citation"]
    finally:
        await conn.close()
