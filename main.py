import datetime
import random
import shutil
import time

from dotenv import load_dotenv
from gpt4all import GPT4All
from pathlib import Path
import os
import re

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

MIN_LENGTH = 15
PATTERN = r'["\']?\s*([^"\'>\s]*\.pdf)\s*["\']?'


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


def find_words(text, words):
    pattern = '|'.join(words)  # create a pattern that matches any word in the list
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches


def find_categories(text):
    categories = getenv_list('CATEGORIES')
    found_words = find_words(text, categories)

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
            f"{description} Inhalt der Dokuments: {input_text}", temp=2, max_tokens=200)
        llm_output = llm_output.replace("\n", " ")
        match = find_match(llm_output)
        if is_valid(match):
            match = tidy_match(match)
            return append_date_to_filename(match)
    return None


def get_document_category(llm_model, input_text):
    categories = f"({', '.join(getenv_list('CATEGORIES'))})"
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


def copy_and_rename(original_file, new_filename, new_folder, name):
    output_dir = 'output'

    if not new_folder:
        new_folder = 'Unsicher'

    if not new_filename:
        new_filename = f'Unsicher_{random.randint(1, 10000000)}.pdf'
        new_folder = 'Unsicher'

    if len(name) > 0:
        new_filename = f'{name}_{new_filename}'

    dst_folder = os.path.join(output_dir, new_folder)
    os.makedirs(dst_folder, exist_ok=True)

    # Construct the destination file path
    dst_file_path = os.path.join(dst_folder, new_filename)

    # Copy and rename the file
    shutil.copy2(original_file, dst_file_path)

    return new_filename


def get_name_part(content, names):
    matches = find_words(content, names)
    names_set = set(matches)
    if len(names_set) == 1:
        return list(names_set)[0]
    result = ""
    sorted_list = sorted(list(names_set))
    for match in sorted_list:
        result += match[:2].lower().capitalize()
    return result


def getenv_list(param_name):
    return [i.strip() for i in os.environ.get(param_name).split(",")]


if __name__ == '__main__':
    load_dotenv()
    names = getenv_list('NAMES')

    input_directory = 'input'
    files = list_files(input_directory)
    model = GPT4All("mistral-7b-openorca.gguf2.Q4_0.gguf", allow_download=False)  # Set to true for initial download
    for file in files:
        if not file == 'Nebenkosten2024CaDo.pdf':
            continue
        with model.chat_session():
            start_time = time.time()
            input_file = os.path.join(input_directory, file)

            # read pdf file
            content = ocr_file(input_file)
            content = content[:2000]

            # get names in content
            name_part = get_name_part(content, names)

            # get filename and category
            doc_name = get_document_name(model, content)
            doc_category = get_document_category(model, content)

            # Steuern
            if 'Scan-Steuern' in file:
                copy_and_rename(input_file, doc_name, 'Steuern Scans', name_part)

            # copy to correct folder and rename
            filename = copy_and_rename(input_file, doc_name, doc_category, name_part)

            end_time = time.time()
            time_taken = end_time - start_time

            print(f"{file}: '{filename}' ({doc_category})")
            print(f"Time taken: {time_taken} seconds")
