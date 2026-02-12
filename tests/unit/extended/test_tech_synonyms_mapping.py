from pathlib import Path
import json

from cv_search.lexicon.loader import load_tech_synonym_map, build_tech_reverse_index


def test_reverse_index_maps_synonyms(tmp_path: Path):
    payload = {
        "python": ["python", "py"],
        "dotnet": ["dotnet", ".net", "c#"],
    }
    lex_path = tmp_path / "tech_synonyms.json"
    lex_path.write_text(json.dumps(payload), encoding="utf-8")

    mapping = load_tech_synonym_map(tmp_path)
    reverse = build_tech_reverse_index(mapping)

    assert reverse[".net"] == "dotnet"
    assert reverse["c#"] == "dotnet"
    assert reverse["python"] == "python"
