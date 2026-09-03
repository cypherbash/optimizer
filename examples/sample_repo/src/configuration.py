from .calendar import Calendar


class Configuration:
    def __init__(self, calendar: Calendar) -> None:
        self.calendar = calendar

    def calendar_for(self, location: str, periods: list[str]) -> list[str]:
        """Return effective periods for one location."""
        return self.calendar.resolve(location, periods)
