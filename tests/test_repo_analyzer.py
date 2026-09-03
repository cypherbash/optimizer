from pathlib import Path

from token_optimizer.repo_analyzer import analyze_repository


def test_python_structure_and_line_numbers(tmp_path: Path) -> None:
    package = tmp_path / "src"
    tests = tmp_path / "tests"
    package.mkdir()
    tests.mkdir()
    (package / "service.py").write_text(
        "import json\nfrom pathlib import Path\n\n"
        "class Service:\n"
        "    def run(self) -> str:\n"
        "        return json.dumps({})\n\n"
        "def helper() -> int:\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (tests / "test_service.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")

    analysis = analyze_repository(tmp_path)
    service = analysis.files["src/service.py"]
    symbols = {symbol.qualified_name: symbol for symbol in service.symbols}
    assert service.imports == ["json", "pathlib"]
    assert symbols["Service"].line_start == 4
    assert symbols["Service.run"].line_start == 5
    assert symbols["helper"].line_end == 9
    assert analysis.files["tests/test_service.py"].is_test
