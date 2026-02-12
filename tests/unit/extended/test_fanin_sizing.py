from cv_search.search.processor import SearchProcessor


def test_compute_lex_fanin_is_bounded_and_not_gate_size():
    lex_fanin = SearchProcessor._compute_lex_fanin(
        top_k=10,
        gate_count=50_000,
        multiplier=10,
        max_cap=250,
    )

    # desired = top_k * multiplier = 100, cap = max(250, 10) = 250
    # result = min(50_000, min(250, 100)) = 100
    assert lex_fanin == 100


def test_compute_lex_fanin_never_below_top_k_even_if_cap_smaller():
    lex_fanin = SearchProcessor._compute_lex_fanin(
        top_k=10,
        gate_count=50_000,
        multiplier=1,
        max_cap=5,
    )

    assert lex_fanin == 10
