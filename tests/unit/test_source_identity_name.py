from cv_search.ingestion.source_identity import (
    candidate_name_from_source_gdrive_path,
    is_probably_full_name,
)


def test_candidate_name_from_source_gdrive_path_uses_parent_folder() -> None:
    path = "EMPLOYEES/Angular/Anton Okhrimenko/Anton_Senior_CV.pptx"
    assert candidate_name_from_source_gdrive_path(path) == "Anton Okhrimenko"


def test_candidate_name_from_source_gdrive_path_normalizes_underscores() -> None:
    path = "EMPLOYEES/React/Valeriia_Ryabokon/Valeriia_Ryabokon_CV.pptx"
    assert candidate_name_from_source_gdrive_path(path) == "Valeriia Ryabokon"


def test_candidate_name_from_source_gdrive_path_requires_full_name() -> None:
    assert candidate_name_from_source_gdrive_path("resume.pptx") is None
    assert not is_probably_full_name("Anton")
    assert is_probably_full_name("Anton Okhrimenko")
