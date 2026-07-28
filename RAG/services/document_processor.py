import os

from pypdf import PdfReader
from docx import Document as DocxDocument



def extract_text(file_path):

    extension = os.path.splitext(file_path)[1]


    text = ""


    if extension == ".pdf":

        reader = PdfReader(file_path)


        for page in reader.pages:

            text += page.extract_text()



    elif extension == ".docx":

        doc = DocxDocument(file_path)


        for paragraph in doc.paragraphs:

            text += paragraph.text + "\n"



    elif extension == ".txt":

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            text = file.read()



    return text


def clean_text(text):

    text = text.replace(
        "\n",
        " "
    )


    text = " ".join(
        text.split()
    )


    return text

def create_chunks(
        text,
        chunk_size=500
):

    words = text.split()


    chunks=[]


    for i in range(
        0,
        len(words),
        chunk_size
    ):

        chunk = " ".join(
            words[i:i+chunk_size]
        )


        chunks.append(chunk)



    return chunks