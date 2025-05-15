import datetime
import json
import random
import shutil
import time

import requests
from dotenv import load_dotenv
from gpt4all import GPT4All
from pathlib import Path
import os
import re

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

import EmailManager
import KdriveManager
from ConfigReader import Config

MIN_LENGTH = 15
PATTERN = r'["\']?\s*([^"\'>\s]*\.pdf)\s*["\']?'
RETRIES = 3


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


def get_replacements(names):
    firstnames, lastname = names
    replacements = [lastname]
    # append all firstnames to replacements
    replacements += firstnames
    # append all firstnames_lastname to replacements
    replacements += [f"{f}_{lastname}" for f in firstnames]
    replacements += [f"{f}{lastname}" for f in firstnames]
    # prepend _ to each element in replacements
    replacements = [f"_{r}" for r in replacements]
    replacements += [lastname]
    return replacements


def tidy_match(match, names):
    tidied = match.replace("__", "_")
    tidied = tidied.replace('"', "")
    tidied = tidied.replace("'", "")
    tidied = tidied.strip()

    replacements = get_replacements(names)

    # replace all elements in replacements with _ in tidied, ignoring case
    for r in replacements:
        tidied = re.sub(r, "", tidied, flags=re.IGNORECASE)

    # TODO remove dates?
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


def find_category(text, categories_list):
    found_words = find_words(text, categories_list)

    if len(found_words) == 1:
        return found_words[0]

    print(f"CATEGORY: input not matched: '{text}' Found: {found_words}")
    # TODO match' Dieses Dokument passt am besten in die Kategorie "Rechnung".....'
    return None


def highest_count_by_two(data_dict):
    # Sort the dictionary items by count in descending order
    sorted_items = sorted(data_dict.items(), key=lambda item: item[1], reverse=True)

    # If there's only one item, return its category
    if len(sorted_items) == 1:
        return sorted_items[0][0]

    # Check if the highest count is at least 2 greater than the next one
    if sorted_items[0][1] - sorted_items[1][1] >= 2:
        return sorted_items[0][0]  # Return the category with the highest count
    else:
        return None  # Return None otherwise


def get_document_name(url, input_text, names):
    description = ("Ich habe ein pdf Dokument, welches folgenden Text enthält. Was ist ein passender und präziser "
                   "deutscher Dateiname für dieses Dokument? Sei so präzise wie möglich: Ergänze Namen erwähnter "
                   "Firmen im Dateinamen und bitte hänge ans Ende des Dateinamens .pdf an. Denk daran: "
                   "der Output ist ein einziger Dateiname, welcher mit .pdf endet ohne Erklärung oder Leerzeichen!\n")
    full_text = f"{description}Hier ist der Text-Inhalt des Dokuments: {input_text}"

    for i in range(RETRIES):
        llm_output = ask_infomaniak_ai(full_text, url)
        llm_output = llm_output.replace("\n", " ")
        llm_output = llm_output.replace('\\\\', '')
        llm_output = llm_output.replace('\\', '')
        match = find_match(llm_output)
        if is_valid(match):
            match = tidy_match(match, names)
            return append_date_to_filename(match)
    return None


def get_document_category(url, input_text, categories_list):
    description = (f"Ich habe ein Dokument gescannt mit folgendem Text - kannst du für den folgenden Text bestimmen, "
                   f"in welche der folgenden Kategorien er am besten passt? Antworte nur mit einer Kategorie, "
                   f"oder wähle 'Unsicher' als Kategorie, wenn du dir nicht zu 100% sicher bist.\n")
    categories = f"Hier sind die einzig erlaubten Kategorien: ({', '.join(categories_list)})\n"
    full_text = (f"{description}{categories}Hier ist der Text-Inhalt des Dokuments: {input_text}. Wichtig: Deine "
                 f"Antwort ist genau ein Wort!")

    category_counts = {}
    for i in range(RETRIES):
        llm_output = ask_infomaniak_ai(full_text, url)
        llm_output = llm_output.replace("\n", " ")
        llm_output = llm_output.replace('\\\\', '')
        llm_output = llm_output.replace('\\', '')

        category = find_category(llm_output, categories_list)
        if category:
            if category in category_counts:
                category_counts[category] += 1
            else:
                category_counts[category] = 1

            highest_category = highest_count_by_two(category_counts)
            if highest_category:
                return highest_category
    return None

def get_filename_and_category(new_filename, category, name):
    if not category:
        category = 'Unsicher'

    if not new_filename:
        new_filename = f'Unsicher_{random.randint(1, 10000000)}.pdf'
        category = 'Unsicher'

    if len(name) > 0:
        new_filename = f'{name}_{new_filename}'

    return new_filename, category


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

def ask_infomaniak_ai(question, url):
  model = "mixtral"

  data_dict = {
    "messages": [
      {
        "content": question,
        "role": "user"
      }
    ],
    "model": model
  }

  data = json.dumps(data_dict)
  headers = {
    'Authorization': f'Bearer {api_token}',
    'Content-Type': 'application/json',
  }

  response = requests.request("POST", url = url , data = data, headers = headers)
  response_dict = json.loads(response.text)
  if 'choices' in response_dict:
    return response_dict['choices'][0]['message']['content']

  raise Exception(response_dict['error'])

def try_upload(input_dir, orig_filename, new_filename, folder):
    result = KdriveManager.upload_file(input_dir, orig_filename, new_filename, folder)
    if result:
        print(f"File '{orig_filename}' uploaded successfully as '{new_filename}' in directory '{folder}'.")
    else:
        print(f"File '{orig_filename}' upload failed to directory '{folder}'.")
    return result


if __name__ == '__main__':
    INPUT_DIRECTORY = 'input'
    config = Config('secrets.json')

    EmailManager.init_and_download(config)

    names = config.NAMES
    lastname = config.LASTNAME
    names_tuple = (names, lastname)
    categories = config.CATEGORIES

    api_token = config.KDRIVE_API_TOKEN
    product_id = config.AI_PRODUCT_ID
    URL = f"https://api.infomaniak.com/1/ai/{product_id}/openai/chat/completions"

    folders = os.listdir(INPUT_DIRECTORY)
    directories = [entry for entry in folders if os.path.isdir(os.path.join(INPUT_DIRECTORY, entry))]
    for directory in directories:
        input_directory = os.path.join(INPUT_DIRECTORY, directory)
        print("Processing directory: ", input_directory)

        files = list_files(input_directory)

        for file in files:
            start_time = time.time()
            input_file = os.path.join(input_directory, file)

            # read pdf file
            content = ocr_file(input_file)
            content = content[:2000]

            # get names in content
            name_part = get_name_part(content, names)

            # get filename and category
            doc_name = get_document_name(URL, content, names_tuple)
            doc_category = get_document_category(URL, content, list(categories.keys()))
            filename, category = get_filename_and_category(doc_name, doc_category, name_part)

            if directory == 'Steuern':
                try_upload(input_directory, file, filename, 'Dokumente für Steuern 2024')

            if directory == '1und1macht3':
                try_upload(input_directory, file, filename, '1und1macht3')

            res = try_upload(input_directory, file, filename, category)
            if res:
                shutil.move(input_file, os.path.join('Archive', filename))

            end_time = time.time()
            time_taken = end_time - start_time

            print(f"Time taken: {time_taken} seconds")
            print(f"\n")
