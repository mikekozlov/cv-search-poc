from __future__ import annotations

from cv_search.ingestion.cv_parser import CVParser


def test_extract_text_from_txt(tmp_path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\nworld", encoding="utf-8")

    parser = CVParser()

    assert parser.extract_text(sample_path) == "hello\nworld"
