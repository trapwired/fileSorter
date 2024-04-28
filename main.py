import datetime
import random
import shutil
import time

from gpt4all import GPT4All
from pathlib import Path
import os
import re

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

MIN_LENGTH = 15
PATTERN = r'["\']?\s*([^"\'>\s]*\.pdf)\s*["\']?'
CATEGORIES = ['Rechnungen', 'Sonstiges', 'Dokumente', 'Wohnung', 'Verträge', 'Vorsorge', 'Bank', 'Unsicher',
              'Rückforderungsbelege']


def list_files(directory):
    return os.listdir(directory)


def ocr_file(filename):
    tempdir = os.path.join('Temp')
    pdf_file = Path(filename)
    pdf_pages = convert_from_path(pdf_file, 500)

    # store as jpeg
    image_file_list = []
    for page_enumeration, page in enumerate(pdf_pages, start=1):
        filename = f"page_{page_enumeration:03}.jpg"
        filename = os.path.join(tempdir, filename)
        page.save(filename, "JPEG")
        image_file_list.append(filename)

    # ocr the images
    output_string = ""
    for image_file in image_file_list:
        text = str((pytesseract.image_to_string(Image.open(image_file))))
        text = text.replace("-\n", "")

        output_string += text
        os.remove(image_file)

    output_string = output_string.replace("\n", " ")
    return output_string


def longest_string(strings):
    longest = ""
    for s in strings:
        if len(s) > 13 and len(s) > len(longest):
            longest = s
    return longest


def find_match(string):
    match = re.search(PATTERN, string)
    if match:
        matched_string = match.group(0)
        return matched_string
    print("FILENAME: input not matched: '{}'".format(string))
    return None


def append_date_to_filename(filename):
    now = datetime.datetime.now()
    date_str = now.strftime('%b_%y')
    name, extension = filename.rsplit('.', 1)
    new_filename = f"{name}-{date_str}.{extension}"
    return new_filename


def tidy_match(match):
    tidied = match.replace("__", "_")
    tidied = tidied.replace('"', "")
    tidied = tidied.replace("'", "")
    tidied = tidied.strip()
    return tidied


def is_valid(match):
    if not match:
        return False
    if len(match) < MIN_LENGTH:
        return False
    if len(match.split(".")) != 2:
        return False
    return True


def find_words(text):
    pattern = '|'.join(CATEGORIES)  # create a pattern that matches any word in the list
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches


def find_categories(text):
    found_words = find_words(text)

    if len(found_words) == 1:
        return found_words[0]

    # TODO maybe just use first?

    print(f"CATEGORY: input not matched: '{text}' Found: {found_words}")
    return None


def get_document_name(llm_model, input_text):
    description = ("Ich habe ein pdf Dokument, welches folgenden Text enthält. Was ist ein passender und präziser "
                   "deutscher Dateiname für dieses Dokument? Sei so präzise wie möglich: ergänze Namen erwähnter "
                   "Personen oder Firmen im Dateinamen und bitte hänge ans Ende des Dateinamens .pdf an")

    for i in range(10):
        llm_output = llm_model.generate(
            f"{description} Inhalt der Dokuments: {input_text}", temp=2.5, max_tokens=200)
        llm_output = llm_output.replace("\n", " ")
        match = find_match(llm_output)
        if is_valid(match):
            match = tidy_match(match)
            return append_date_to_filename(match)
    return None


def get_document_category(llm_model, input_text):
    categories = f"({', '.join(CATEGORIES)})"
    description = (f"Kannst du für den folgenden Text bestimmen, in welche der folgenden Kategorien er am besten passt?"
                   f" Bitte gib nur eine Kategorie zurück, und wähle 'Unsicher' wenn du dir nicht sicher bist.")

    for i in range(10):
        llm_output = llm_model.generate(
            f"{description} Kategorien: {categories} Text: {input_text}", temp=2)
        llm_output = llm_output.replace("\n", " ")

        category = find_categories(llm_output)
        if category:
            return category
    return None


def copy_and_rename(original_file, new_filename, new_folder):
    output_dir = 'output'

    if not new_folder:
        new_folder = 'Unsicher'

    if not new_filename:
        new_filename = f'Unsicher_{random.randint(1, 10000000)}.pdf'

    dst_folder = os.path.join(output_dir, new_folder)
    os.makedirs(dst_folder, exist_ok=True)

    # Construct the destination file path
    dst_file_path = os.path.join(dst_folder, new_filename)

    # Copy and rename the file
    shutil.copy2(original_file, dst_file_path)


if __name__ == '__main__':
    input_directory = 'input'
    files = list_files(input_directory)
    model = GPT4All("mistral-7b-openorca.gguf2.Q4_0.gguf", allow_download=False)  # Set to true for initial download
    for file in files:
        with model.chat_session():
            start_time = time.time()
            input_file = os.path.join(input_directory, file)

            # read pdf file
            content = ocr_file(input_file)
            content = content[:2000]

            # get filename and category
            doc_name = get_document_name(model, content)
            doc_category = get_document_category(model, content)

            # copy to correct folder and rename
            copy_and_rename(input_file, doc_name, doc_category)

            end_time = time.time()
            time_taken = end_time - start_time

            print(f"{file}: '{doc_name}' ({doc_category})")
            print(f"Time taken: {time_taken} seconds")
