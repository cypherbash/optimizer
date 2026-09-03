from src.calendar import Calendar
from src.configuration import Configuration


def test_calendar_for_includes_inherited_periods() -> None:
    configuration = Configuration(Calendar())
    assert configuration.calendar_for("office", ["weekend"]) == ["weekday", "weekend"]
