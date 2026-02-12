import io
import zipfile

from cv_search.utils.archive import zip_directory


def test_zip_directory_includes_nested_files(tmp_path):
    (tmp_path / "criteria.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "seat_01_backend_engineer").mkdir()
    (tmp_path / "seat_01_backend_engineer" / "results.json").write_text(
        '{"results": []}', encoding="utf-8"
    )

    blob = zip_directory(tmp_path)

    with zipfile.ZipFile(io.BytesIO(blob), mode="r") as zf:
        names = set(zf.namelist())

    assert "criteria.json" in names
    assert "seat_01_backend_engineer/results.json" in names
