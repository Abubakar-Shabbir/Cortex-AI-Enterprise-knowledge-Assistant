import os

import fitz
from docx import Document


def extract_text(file_path):
    """
    Extract text from PDF, DOCX and TXT files.
    """

    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":
        return extract_pdf(file_path)

    elif extension == ".docx":
        return extract_docx(file_path)

    elif extension == ".txt":
        return extract_txt(file_path)

    else:
        raise ValueError(
            "Unsupported document format."
        )


def extract_pdf(file_path):

    document = fitz.open(file_path)

    text = ""

    for page in document:

        text += page.get_text()

    document.close()

    return text


def extract_docx(file_path):

    document = Document(file_path)

    return "\n".join(

        paragraph.text

        for paragraph in document.paragraphs

    )


def extract_txt(file_path):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read()