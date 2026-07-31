def format_bytes(num_bytes):
    """
    Human-readable file size, e.g. 1536 -> "1.5 KB".
    """

    size = float(num_bytes or 0)

    for unit in ["B", "KB", "MB", "GB", "TB"]:

        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"

        size /= 1024


def format_ms(ms):
    """
    Human-readable duration, e.g. 1450 -> "1.45s".
    """

    ms = ms or 0

    if ms < 1000:
        return f"{ms} ms"

    return f"{ms / 1000:.2f} s"
