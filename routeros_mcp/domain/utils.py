"""Utility functions for domain services.

Common helper functions used across multiple domain services.
"""


def parse_routeros_uptime(uptime_str: str) -> int:
    """Parse RouterOS uptime string to seconds.

    Args:
        uptime_str: Uptime string (e.g., "1w2d3h4m5s")

    Returns:
        Uptime in seconds

    Example:
        >>> parse_routeros_uptime("1w2d3h4m5s")
        788645
        >>> parse_routeros_uptime("5h30m")
        19800
    """
    if not uptime_str:
        return 0

    # Parse uptime format: 1w2d3h4m5s
    seconds = 0
    current_num = ""

    for char in uptime_str:
        if char.isdigit():
            current_num += char
        elif char == "w":
            if current_num:
                seconds += int(current_num) * 7 * 24 * 3600
            current_num = ""
        elif char == "d":
            if current_num:
                seconds += int(current_num) * 24 * 3600
            current_num = ""
        elif char == "h":
            if current_num:
                seconds += int(current_num) * 3600
            current_num = ""
        elif char == "m":
            if current_num:
                seconds += int(current_num) * 60
            current_num = ""
        elif char == "s":
            if current_num:
                seconds += int(current_num)
            current_num = ""

    return seconds
