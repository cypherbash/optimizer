from token_optimizer.state_extractor import extract_state


def test_deterministic_extraction_preserves_exact_evidence() -> None:
    task = "Configuration.calendar_for() MUST preserve backwards compatibility in Python 3.12."
    conversation = """
Do not edit src/configuration.py without running tests.
The adapter is required. `load_runtime` remains public.
$ pytest tests/test_configuration.py
ValueError: invalid period
See https://example.test/design
"""
    state = extract_state(task, conversation)
    assert any("MUST" in item.text for item in state.hard_constraints)
    assert any("Do not" in item.text for item in state.hard_constraints)
    assert any(item.text == "src/configuration.py" for item in state.relevant_files)
    assert any(item.text == "Configuration.calendar_for" for item in state.important_identifiers)
    assert any(item.text == "load_runtime" for item in state.important_identifiers)
    assert any("pytest" in item.text for item in state.recent_actions)
    assert any("ValueError" in item.text for item in state.current_errors)
    assert any("3.12" in item.text for item in state.relevant_facts)
    assert not any(
        "adapter is required" in item.approach.lower() for item in state.rejected_approaches
    )


def test_deduplication_is_exact_and_preserves_scope_variants() -> None:
    state = extract_state("Use TypeScript.\nUse TypeScript.\nUse TypeScript in the CLI.")
    assert len(state.decisions) == 2
