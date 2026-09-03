from token_optimizer.tokenizer import EstimatingTokenCounter


def test_empty_text_has_zero_tokens() -> None:
    assert EstimatingTokenCounter().count("") == 0


def test_prose_code_and_unicode_are_counted_deterministically() -> None:
    counter = EstimatingTokenCounter()
    samples = [
        "A normal sentence with several words.",
        "def answer(value: int) -> int:\n    return value + 1\n",
        "Grüezi 世界 👋",
    ]
    for sample in samples:
        assert counter.count(sample) > 0
        assert counter.count(sample) == counter.count(sample)
