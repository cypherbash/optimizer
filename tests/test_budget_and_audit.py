from token_optimizer.audit import audit_context
from token_optimizer.budget import apply_budget
from token_optimizer.models import ContextChunk, ContextState, EvidenceItem, Importance
from token_optimizer.tokenizer import EstimatingTokenCounter


def _chunk(identifier: str, tokens: int, score: float, mandatory: bool = False) -> ContextChunk:
    return ContextChunk(
        identifier, "source_code", identifier, identifier, tokens, score=score, mandatory=mandatory
    )


def test_mandatory_chunks_survive_and_low_score_drops_first() -> None:
    counter = EstimatingTokenCounter()
    mandatory = _chunk("task", 20, 1.0, True)
    high = _chunk("high", 30, 0.9)
    low = _chunk("low", 30, 0.1)
    result = apply_budget([low, mandatory, high], 50, counter)
    assert {item.id for item in result.selected} == {"task", "high"}
    assert [item.id for item in result.dropped] == ["low"]


def test_mandatory_overflow_is_reported_without_silent_loss() -> None:
    counter = EstimatingTokenCounter()
    chunks = [_chunk("task", 80, 1.0, True), _chunk("constraint", 40, 1.0, True)]
    result = apply_budget(chunks, 50, counter)
    assert len(result.selected) == 2
    assert result.selected_tokens == 120
    assert result.warnings


def test_audit_fails_when_hard_constraint_is_removed() -> None:
    state = ContextState(
        goal="Change the loader.",
        hard_constraints=[EvidenceItem("Preserve the public API.", "task", Importance.CRITICAL)],
    )
    result = audit_context(state, "# TASK\n\nChange the loader.\n")
    assert not result.passed
    assert "hard_constraints" in result.missing_categories
