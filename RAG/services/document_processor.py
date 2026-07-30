from ..utils.file_parser import extract_text
from ..utils.text_cleaner import clean_text
from ..utils.chunking import create_chunks


def process_document(
    file_path,
    chunk_size=500
):
    """
    Complete document processing pipeline.

    Steps:
        1. Extract text
        2. Clean text
        3. Create chunks

    Returns:
        List[str]
    """

    text = extract_text(
        file_path
    )

    cleaned_text = clean_text(
        text
    )

    chunks = create_chunks(
        cleaned_text,
        chunk_size
    )

    return chunks