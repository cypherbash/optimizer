from pathlib import Path

from token_optimizer.context_builder import BuildOptions, build_context
from token_optimizer.evaluation import evaluate_result
from token_optimizer.tokenizer import EstimatingTokenCounter


def test_vertical_slice_selects_relevant_code_and_tests() -> None:
    examples = Path(__file__).parents[1] / "examples"
    result = build_context(
        (examples / "sample_task.txt").read_text(encoding="utf-8"),
        (examples / "sample_conversation.md").read_text(encoding="utf-8"),
        examples / "sample_repo",
        options=BuildOptions(budget=6000, tokenizer="estimate"),
        counter=EstimatingTokenCounter(),
    )
    metrics = evaluate_result(
        result,
        expected_relevant_files=[
            "src/configuration.py",
            "src/calendar.py",
            "tests/test_configuration.py",
        ],
        expected_irrelevant_files=["src/unrelated.py", "tests/test_unrelated.py"],
    )
    assert result.audit.passed
    assert "# TASK" in result.context
    assert "# RELEVANT CODE" in result.context
    assert "# RELEVANT TESTS" in result.context
    assert metrics.relevant_file_recall == 1.0
    assert metrics.irrelevant_file_rejection == 1.0
    recent = result.context.split("# RECENT CONVERSATION", 1)[1]
    first_user = recent.index("The configuration file format MUST NOT change")
    assistant = recent.index("We decided to keep materialized locations internal")
    last_user = recent.index("Do not use field projection")
    assert first_user < assistant < last_user
