from cv_search.search.processor import SearchProcessor


def test_compute_lex_fanin_is_bounded_and_not_gate_size():
    lex_fanin = SearchProcessor._compute_lex_fanin(
        top_k=10,
        sem_fanin=25,
        gate_count=50_000,
        multiplier=10,
        max_cap=250,
    )

    assert lex_fanin == 250


def test_compute_lex_fanin_never_below_top_k_even_if_cap_smaller():
    lex_fanin = SearchProcessor._compute_lex_fanin(
        top_k=10,
        sem_fanin=0,
        gate_count=50_000,
        multiplier=1,
        max_cap=5,
    )

    assert lex_fanin == 10
