def clean_text(text):
    """
    Clean extracted text.
    """

    text = text.replace(
        "\n",
        " "
    )

    text = " ".join(
        text.split()
    )

    return text