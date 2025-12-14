from cv_search.core.criteria import SeniorityEnum
from cv_search.retrieval.embedder_stub import DeterministicEmbedder
from cv_search.retrieval.pgvector import PgVectorSemanticRetriever


def test_build_vs_query_uses_seniority_value_not_enum_repr():
    retriever = PgVectorSemanticRetriever(db=None, settings=None, embedder=DeterministicEmbedder())
    seat = {
        "role": "backend_engineer",
        "seniority": SeniorityEnum.senior,
        "domains": [],
        "must_have": ["dotnet", "devops"],
        "nice_to_have": [],
    }

    query = retriever._build_vs_query(seat)

    assert "SeniorityEnum." not in query
    assert query.startswith("senior backend engineer")
