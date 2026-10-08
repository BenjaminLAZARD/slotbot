class ConfigError(Exception):
    """Setup is incomplete (no Google key, calendar not shared, ...). Shown to the user as is."""
