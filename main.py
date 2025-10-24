import datetime
import json
import random
import shutil
import time

import requests
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

# Statistics for prompt effectiveness
prompt_stats = {
    'name': [0, 0, 0],  # One counter per prompt template in get_document_name
    'category': [0, 0, 0],  # One counter per prompt template in get_document_category
}


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


def get_document_name(url, input_text, names, extra_context=None):
    prompt_templates = [
        ("""Analysiere den folgenden Text aus einem PDF-Dokument und erstelle einen präzisen deutschen Dateinamen.

    REGELN:
    - Format: Dokumenttyp_Firma_Thema_Datum.pdf
    - Verwende Unterstriche statt Leerzeichen
    - Inkludiere: Dokumenttyp (z.B. Rechnung, Vertrag, Angebot), Firmennamen, relevante Details, Datum falls vorhanden
    - Maximal 60 Zeichen
    - Keine Sonderzeichen außer Unterstriche und Bindestriche
    - Antworte NUR mit dem Dateinamen, keine Erklärungen

    Text des Dokuments:
    {content}

    Dateiname:"""),

        ("""Erstelle einen strukturierten Dateinamen für dieses PDF-Dokument.

    FORMAT: [Typ]_[Firma]_[Details]_[YYYY-MM-DD].pdf

    BEISPIELE:
    - Rechnung_TelekomAG_Mobilfunk_2024-03-15.pdf
    - Arbeitsvertrag_MusterGmbH_Schmidt_2023-01-10.pdf
    - Kontoauszug_Sparkasse_Dezember2023.pdf

    Gib NUR den Dateinamen aus, nichts anderes.

    Dokumentinhalt:
    {content}"""),

        ("""Du bist ein Dokumenten-Management-System. Erstelle einen eindeutigen, präzisen Dateinamen.

    WICHTIG:
    1. Identifiziere Dokumenttyp (Rechnung, Brief, Vertrag, etc.)
    2. Extrahiere Firmennamen oder Absender
    3. Finde Datum falls vorhanden (Format: YYYY-MM-DD)
    4. Füge relevante Details hinzu
    5. Verwende Format: Typ_Firma_Details_Datum.pdf

    NUR DEN DATEINAMEN AUSGEBEN!

    Text:
    {content}"""),
    ]
    if extra_context:
        prompt_templates = [p + f"\nKontext: {extra_context}" for p in prompt_templates]

    for idx, prompt in enumerate(prompt_templates):
        for _ in range(RETRIES):
            full_text = prompt.format(content=input_text)
            llm_output = ask_infomaniak_ai(full_text, url)
            llm_output = llm_output.replace("\n", " ").replace('\\', '').replace('\\', '')
            match = find_match(llm_output)
            if is_valid(match):
                match = tidy_match(match, names)
                prompt_stats['name'][idx] += 1
                return append_date_to_filename(match)
    return None


def get_document_category(url, input_text, categories_list, extra_context=None):
    prompt_templates = [
        (f"""Analysiere den folgenden Dokumententext und ordne ihn EXAKT EINER Kategorie zu.

    ERLAUBTE KATEGORIEN:
    {chr(10).join(f'- {cat}' for cat in categories_list)}

    REGELN:
    1. Antworte NUR mit einer Kategorie aus der obigen Liste
    2. Keine Erklärungen, keine zusätzlichen Worte
    3. Wähle "Unsicher" nur wenn wirklich keine Kategorie passt
    4. Achte auf Schlüsselwörter: Rechnungsnummer → Rechnung, Vertragslaufzeit → Vertrag, etc.

    BEISPIELE:
    - Text enthält "Rechnung Nr." → Antwort: Rechnung
    - Text enthält "Arbeitsvertrag" → Antwort: Vertrag
    - Text über Stromrechnung → Antwort: Rechnung

    Dokumententext:
    {{content}}

    Kategorie:"""),

        (f"""Du bist ein Dokumenten-Klassifizierungssystem. Klassifiziere dieses Dokument.

    VERFÜGBARE KATEGORIEN:
    {chr(10).join(f'{i + 1}. {cat}' for i, cat in enumerate(categories_list))}

    WICHTIG: Gib NUR die exakte Kategorie aus der Liste aus, sonst nichts!

    Text:
    {{content}}

    Zugewiesene Kategorie:"""),

        (f"""Klassifiziere diesen Dokumententext in genau eine Kategorie.

    Kategorien: {' | '.join(categories_list)}

    Hinweise zur Zuordnung:
    - Rechnungen: enthalten Rechnungsnummer, Zahlungsbetrag, Fälligkeit
    - Verträge: enthalten Vertragslaufzeit, Unterschriften, rechtliche Klauseln
    - Briefe: persönliche/geschäftliche Korrespondenz ohne Rechnung
    - Kontoauszüge: Transaktionsübersichten, IBAN, Kontobewegungen
    - Wähle "Unsicher" nur wenn gar keine Kategorie passt (< 50% Sicherheit)

    ANTWORTE NUR MIT EINER KATEGORIE!

    Text:
    {{content}}"""),
    ]
    if extra_context:
        prompt_templates = [p + f"\nKontext: {extra_context}" for p in prompt_templates]

    category_counts = {}
    for idx, prompt in enumerate(prompt_templates):
        for _ in range(RETRIES):
            full_text = prompt.format(content=input_text)
            llm_output = ask_infomaniak_ai(full_text, url)
            llm_output = llm_output.replace("\n", " ").replace('\\', '').replace('\\', '')
            category = find_category(llm_output, categories_list)
            if category:
                if category in category_counts:
                    category_counts[category] += 1
                else:
                    category_counts[category] = 1
                highest_category = highest_count_by_two(category_counts)
                if highest_category:
                    prompt_stats['category'][idx] += 1
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
    model = "llama3"

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

    response = requests.request("POST", url=url, data=data, headers=headers)
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
                try_upload(input_directory, file, filename, 'Dokumente für Steuern 2025')

            if directory == '1und1macht3':
                try_upload(input_directory, file, filename, '1und1macht3')

            res = try_upload(input_directory, file, filename, category)
            if res:
                shutil.move(input_file, os.path.join('Archive', filename))

            end_time = time.time()
            time_taken = end_time - start_time

            print(f"Time taken: {time_taken} seconds")
            print(f"\n")

    # Output prompt statistics at the end
    print("Prompt statistics for document name:")
    for i, count in enumerate(prompt_stats['name']):
        print(f"  Prompt {i + 1}: {count} valid results")
    print("Prompt statistics for document category:")
    for i, count in enumerate(prompt_stats['category']):
        print(f"  Prompt {i + 1}: {count} valid results")
