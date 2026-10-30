from legal_api.corpus.chunking import MAX_CHARS, chunk_text
from legal_api.retrieval.hybrid import fuse


def test_chunks_keep_exact_offsets_into_the_original_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(12))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert text[chunk.start:chunk.start + len(chunk.text)] == chunk.text
        assert len(chunk.text) <= MAX_CHARS
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_overlong_paragraph_is_split_at_sentence_ends():
    text = " ".join(f"Sentence number {i} ends here." for i in range(300))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(c.text.endswith(".") for c in chunks[:-1])
    assert all(len(c.text) <= MAX_CHARS for c in chunks)


def test_short_text_is_one_chunk():
    assert [c.text for c in chunk_text("  Short decision.  ")] == ["Short decision."]


def test_rrf_rewards_items_ranked_by_both_retrievers():
    scores = fuse([[1, 2, 3], [3, 4, 1]])
    assert max(scores, key=scores.get) in (1, 3)
    assert scores[1] > scores[2] and scores[3] > scores[4]


def test_status_message_accepts_any_keyword_including_name():
    from legal_api.agent.answer import status_event as _status

    assert "3" in _status("answering", count=3, name="ignored").data["message"]
