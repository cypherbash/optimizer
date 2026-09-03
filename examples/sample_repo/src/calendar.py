class Calendar:
    def resolve(self, location: str, periods: list[str]) -> list[str]:
        inherited = ["weekday"] if location == "office" else []
        return [*inherited, *periods]
