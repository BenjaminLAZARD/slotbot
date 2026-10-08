class ConfigError(Exception):
    """Setup is incomplete (no Google key, calendar not shared, ...). Shown to the user as is."""


class AbortRace(Exception):
    """Retrying cannot help (not signed in, account suspended...): stop the race and report why."""
