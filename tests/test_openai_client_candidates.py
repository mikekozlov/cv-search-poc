from cv_search.clients.openai_client import _lexicon_fingerprint, _select_candidates


def test_select_candidates_prefers_text_hits():
    lexicon = ["python", "javascript", "golang"]
    text = "Strong experience with Python and async frameworks."
    candidates = _select_candidates(lexicon, text, role_hint="", max_candidates=3, fallback=3)
    assert candidates[0] == "python"
    assert set(candidates) <= set(lexicon)


def test_select_candidates_falls_back_deterministically():
    lexicon = ["java", "python", "rust"]
    candidates = _select_candidates(lexicon, "no matches here", role_hint="", max_candidates=2, fallback=2)
    assert candidates == ["java", "python"]


def test_lexicon_fingerprint_is_stable_and_short():
    fp1 = _lexicon_fingerprint(["b", "a"], ["x"])
    fp2 = _lexicon_fingerprint(["a", "b"], ["x"])
    assert fp1 == fp2
    assert len(fp1) == 12
