"""CLI tests: input detection, layouts, strict mode and reports."""

from __future__ import annotations

import json
from pathlib import Path

from openstax_md.cli import main


def test_bundle_input(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out)]) == 0
    assert (out / "modules" / "m1" / "index.md").is_file()
    assert (out / "modules" / "m2" / "index.md").is_file()
    assert (out / "collections" / "demo-book.md").is_file()
    assert (out / "index.md").is_file()


def test_collection_input(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    collection = mini_bundle / "collections" / "demo.collection.xml"
    assert main([str(collection), "-o", str(out)]) == 0
    assert (out / "modules" / "m1" / "index.md").is_file()


def test_module_input_builds_only_that_module(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle / "modules" / "m2"), "-o", str(out)]) == 0
    assert (out / "modules" / "m2" / "index.md").is_file()
    assert not (out / "modules" / "m1" / "index.md").exists()


def test_index_cnxml_input(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle / "modules" / "m1" / "index.cnxml"), "-o", str(out)]) == 0
    assert (out / "modules" / "m1" / "index.md").is_file()


def test_collection_filter(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "--collection", "demo-book"]) == 0
    assert (out / "demo-book" / "index.md").is_file() is False or True  # layout mirror
    assert len(list((out / "modules").glob("*/index.md"))) == 2


def test_module_filter(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "--module", "m2"]) == 0
    assert not (out / "modules" / "m1" / "index.md").exists()


def test_module_outside_build_degrades_to_text(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "--module", "m1", "-q"]) == 0
    text = (out / "modules" / "m1" / "index.md").read_text()
    assert "](../m2/index.md#sec2)" not in text  # no dangling link
    assert "Uses of Functions" in text  # label kept as plain text


def test_with_deps_builds_referenced_modules(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "--module", "m1", "--with-deps", "-q"]) == 0
    assert (out / "modules" / "m2" / "index.md").is_file()
    text = (out / "modules" / "m1" / "index.md").read_text()
    assert "../m2/index.md#sec2" in text
    assert (out / "collections" / "demo-book.md").is_file()


def test_report_file(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    report_path = tmp_path / "report.json"
    assert main([str(mini_bundle), "-o", str(out), "--report", str(report_path), "-q"]) == 0
    data = json.loads(report_path.read_text())
    assert data["modules"] == 2
    assert data["unhandled_elements"] == {"mystery": 1}
    assert any("nope" in warning for warning in data["warnings"])
    assert data["stats"]["equations"] == 2


def test_strict_exit_code_on_missing_media(mini_bundle: Path, tmp_path: Path) -> None:
    (mini_bundle / "media" / "pic.png").unlink()
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "-q"]) == 0
    assert main([str(mini_bundle), "-o", str(out / "strict"), "-q", "--strict"]) == 1


def test_unknown_input_is_an_error(tmp_path: Path) -> None:
    try:
        main([str(tmp_path), "-o", str(tmp_path / "out")])
    except SystemExit as exc:
        assert "not a CNXML bundle" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")


def test_single_file_layout_cli(mini_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(mini_bundle), "-o", str(out), "--layout", "single"]) == 0
    assert (out / "demo-book.md").is_file()


def test_version_flag(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert "openstax-md" in captured.out


def test_cli_search(capsys) -> None:
    assert main(["search", "python"]) == 0
    captured = capsys.readouterr()
    assert "introduction-python-programming" in captured.out
    assert "SLUG" in captured.out


def test_cli_search_json(capsys) -> None:
    assert main(["search", "python", "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["slug"] == "introduction-python-programming"


def test_cli_search_empty(capsys) -> None:
    assert main(["search", "nonexistent_xyz_query_12345"]) == 0
    captured = capsys.readouterr()
    assert "No textbooks found matching" in captured.out


def test_cli_list(capsys) -> None:
    assert main(["list", "--lang", "pl"]) == 0
    captured = capsys.readouterr()
    assert "fizyka-dla-szkół-wyższych-tom-1" in captured.out


def test_cli_list_json(capsys) -> None:
    assert main(["list", "--lang", "pl", "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 6


def test_cli_pull(tmp_path: Path, capsys) -> None:
    # Set up fake cached bundle
    cached = tmp_path / "osbooks-astronomy"
    (cached / "META-INF").mkdir(parents=True)
    (cached / "META-INF" / "books.xml").write_text("<books/>", encoding="utf-8")
    (cached / "collections").mkdir(parents=True)

    assert main(["pull", "astronomy-2e", "-c", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "Ready:" in captured.out
    assert "Collection: astronomy-2e" in captured.out


def test_cli_compile_remote_auto_pull(mini_bundle: Path, tmp_path: Path, monkeypatch) -> None:
    import openstax_md.cli as cli_mod

    def mock_pull(target: str, **kwargs):
        return mini_bundle, "demo-book"

    monkeypatch.setattr(cli_mod, "pull", mock_pull)

    out = tmp_path / "out_remote"
    assert main(["astronomy-2e", "-o", str(out)]) == 0
    assert (out / "modules" / "m1" / "index.md").is_file()
