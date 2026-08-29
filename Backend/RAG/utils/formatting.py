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


def mask_email(email):
    """
    Partially hides an email address for display on the OTP
    verification screen, e.g. "johndoe@example.com" -> "j*****e@example.com".
    Never used for anything security-sensitive (the real address is
    still what the OTP was sent to) - purely a "yes, this is the right
    inbox" confirmation without fully exposing it on screen.
    """

    if not email or "@" not in email:
        return email or ""

    local, _, domain = email.partition("@")

    if len(local) <= 2:
        masked_local = local[0] + "*" * max(len(local) - 1, 1)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

    return f"{masked_local}@{domain}"
