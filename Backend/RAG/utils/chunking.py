def create_chunks(
    text,
    chunk_size=500
):
    """
    Split text into fixed-size chunks.
    """

    words = text.split()

    chunks = []

    for index in range(
        0,
        len(words),
        chunk_size
    ):

        chunk = " ".join(
            words[index:index + chunk_size]
        )

        chunks.append(chunk)

    return chunks