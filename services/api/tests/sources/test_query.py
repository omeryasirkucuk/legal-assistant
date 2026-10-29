import pytest

from legal_api.sources.query import to_and_query


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("kira tahliye", "+kira +tahliye"),
        ("TMK'nin 166. maddesi", "+TMK +166 +maddesi"),
        ('"kira bedeli" -ticari', '+"kira bedeli" -ticari'),
        ("kira OR tahliye", "kira OR tahliye"),
        ("tapuya not", "+tapuya +not"),
        ("a+b", "+a +b"),
    ],
)
def test_to_and_query(raw, expected):
    assert to_and_query(raw) == expected


def test_to_and_query_rejects_empty():
    with pytest.raises(ValueError):
        to_and_query("*** ...")
