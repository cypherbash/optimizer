from src.unrelated import render_weather


def test_render_weather() -> None:
    assert render_weather() == "sunny"
