import subprocess
from pathlib import Path

from token_optimizer.models import ContextState
from token_optimizer.relevance import build_candidates, rank_chunks
from token_optimizer.repo_analyzer import analyze_repository
from token_optimizer.tokenizer import EstimatingTokenCounter


def test_exact_symbol_test_and_changed_file_receive_boost(tmp_path: Path) -> None:
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    docs = tmp_path / "docs"
    src.mkdir()
    tests.mkdir()
    docs.mkdir()
    (src / "configuration.py").write_text(
        "class Configuration:\n    def calendar_for(self):\n        return []\n", encoding="utf-8"
    )
    (tests / "test_configuration.py").write_text(
        "def test_calendar_for():\n    assert True\n", encoding="utf-8"
    )
    (docs / "deployment.md").write_text("Remote deployment notes.\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    with (src / "configuration.py").open("a", encoding="utf-8") as handle:
        handle.write("\n# active change\n")

    analysis = analyze_repository(tmp_path)
    task = "Change Configuration.calendar_for() behavior"
    state = ContextState(goal=task)
    ranked = rank_chunks(
        build_candidates(task, "", state, analysis, EstimatingTokenCounter(), context_lines=0),
        task,
        state,
        analysis,
    )
    code = next(
        chunk for chunk in ranked if chunk.metadata.get("symbol") == "Configuration.calendar_for"
    )
    test = next(chunk for chunk in ranked if chunk.metadata.get("is_test"))
    docs_chunk = next(chunk for chunk in ranked if chunk.source == "docs/deployment.md")
    assert code.score > docs_chunk.score
    assert test.score > docs_chunk.score
    assert any("task-referenced symbol" in reason for reason in code.reasons)
    assert any("modified" in reason for reason in code.reasons)
