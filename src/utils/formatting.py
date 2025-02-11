def format_time_remaining(seconds: float) -> str:
    """Format remaining time in a human-readable way."""
    if seconds < 60:
        return f"{seconds:.0f} Sekunden"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f} Minuten"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} Stunden"
