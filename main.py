import datetime
import json
import logging
import os
import random
import re
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import pytesseract
import requests
from pdf2image import convert_from_path
from PIL import Image

import EmailManager
import KdriveManager
from ConfigReader import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MIN_LENGTH = 15
PATTERN = r'["\']?\s*([^"\'>\s]*\.pdf)\s*["\']?'
RETRIES = 3

# Statistics for prompt effectiveness
prompt_stats = {
    'name': [0, 0, 0],  # One counter per prompt template in get_document_name
    'category': [0, 0, 0],  # One counter per prompt template in get_document_category
}


def list_files(directory: str) -> List[str]:
    """List all files in a directory."""
    return os.listdir(directory)


def ocr_file(pdf_path: str) -> str:
    """
    Extract text from a PDF file using OCR.

    Args:
        pdf_path: Path to the PDF file to process

    Returns:
        Extracted text with newlines replaced by spaces
    """
    temp_dir = Path('Temp')
    temp_dir.mkdir(exist_ok=True)  # Ensure temp directory exists

    pdf_file = Path(pdf_path)
    pdf_pages = convert_from_path(pdf_file, 500)

    # Store pages as JPEG images
    image_file_list = []
    for page_num, page in enumerate(pdf_pages, start=1):
        image_path = temp_dir / f"page_{page_num:03}.jpg"
        page.save(str(image_path), "JPEG")
        image_file_list.append(image_path)

    # OCR the images
    output_text = ""
    for image_path in image_file_list:
        try:
            text = pytesseract.image_to_string(Image.open(image_path))
            text = text.replace("-\n", "")
            output_text += text
        finally:
            # Ensure cleanup even if OCR fails
            image_path.unlink(missing_ok=True)

    return output_text.replace("\n", " ")


def longest_string(strings: List[str]) -> str:
    """
    Find the longest string in a list that is longer than 13 characters.

    Args:
        strings: List of strings to search

    Returns:
        The longest string, or empty string if none found
    """
    longest = ""
    for s in strings:
        if len(s) > 13 and len(s) > len(longest):
            longest = s
    return longest


def clean_llm_output(text: str) -> str:
    """
    Clean LLM output by removing newlines and backslashes.

    Args:
        text: Raw text from LLM

    Returns:
        Cleaned text
    """
    return text.replace("\n", " ").replace("\\", "")


def find_match(string: str) -> Optional[str]:
    """
    Extract PDF filename from a string using regex pattern.

    Args:
        string: String to search for filename

    Returns:
        Matched filename or None if not found
    """
    match = re.search(PATTERN, string)
    if match:
        return match.group(0)
    logger.warning(f"FILENAME: input not matched: '{string}'")
    return None


def append_date_to_filename(file_name: str) -> str:
    """
    Append current date (Mon_YY format) to filename.

    Args:
        file_name: Original filename

    Returns:
        Filename with date appended
    """
    now = datetime.datetime.now()
    date_str = now.strftime('%b_%y')
    name, extension = file_name.rsplit('.', 1)
    return f"{name}-{date_str}.{extension}"


def get_replacements(names: Tuple[List[str], str]) -> List[str]:
    """
    Generate replacement patterns for removing names from filenames.

    Args:
        names: Tuple of (firstnames, lastname)

    Returns:
        List of replacement patterns
    """
    first_names, last_name = names
    replacements = [last_name]
    replacements += first_names
    replacements += [f"{f}_{last_name}" for f in first_names]
    replacements += [f"{f}{last_name}" for f in first_names]
    replacements = [f"_{r}" for r in replacements]
    replacements += [last_name]
    return replacements


def tidy_match(match: str, names: Tuple[List[str], str]) -> str:
    """
    Clean up a matched filename by removing names and formatting.

    Args:
        match: The matched filename string
        names: Tuple of (firstnames, lastname)

    Returns:
        Cleaned filename
    """
    tidied = match.replace("__", "_")
    tidied = tidied.replace('"', "")
    tidied = tidied.replace("'", "")
    tidied = tidied.strip()

    replacements = get_replacements(names)

    # Replace all elements in replacements with empty string in tidied, ignoring case
    for r in replacements:
        tidied = re.sub(r, "", tidied, flags=re.IGNORECASE)

    return tidied


def is_valid(match: Optional[str]) -> bool:
    """
    Validate if a filename match is acceptable.

    Args:
        match: The filename match to validate

    Returns:
        True if valid, False otherwise
    """
    if not match:
        return False
    if len(match) < MIN_LENGTH:
        return False
    if len(match.split(".")) != 2:
        return False
    return True


def find_words(text: str, words: List[str]) -> List[str]:
    """
    Find all occurrences of words from a list in text (case-insensitive).

    Args:
        text: Text to search in
        words: List of words to find

    Returns:
        List of found words
    """
    pattern = '|'.join(words)
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches


def find_category(text: str, categories_list: List[str]) -> Optional[str]:
    """
    Find a document category from text.

    Args:
        text: Text containing category information
        categories_list: List of valid categories

    Returns:
        Found category or None if not found uniquely
    """
    found_words = find_words(text, categories_list)

    if len(found_words) == 1:
        return found_words[0]

    logger.warning(f"CATEGORY: input not matched: '{text}' Found: {found_words}")
    return None


def highest_count_by_two(data_dict: Dict[str, int]) -> Optional[str]:
    """
    Return the category with highest count if it leads by at least 2.

    Args:
        data_dict: Dictionary mapping categories to counts

    Returns:
        Category with highest count if it leads by 2+, else None
    """
    sorted_items = sorted(data_dict.items(), key=lambda item: item[1], reverse=True)

    if len(sorted_items) == 1:
        return sorted_items[0][0]

    # Check if the highest count is at least 2 greater than the next one
    if sorted_items[0][1] - sorted_items[1][1] >= 2:
        return sorted_items[0][0]

    return None


def get_document_name(url: str, input_text: str, names: Tuple[List[str], str],
                      api_token: str, extra_context: Optional[str] = None) -> Optional[str]:
    """
    Generate a document filename using LLM based on document text.

    Args:
        url: API endpoint URL
        input_text: Extracted text from document
        names: Tuple of (firstnames, lastname)
        api_token: API authentication token
        extra_context: Optional additional context for LLM

    Returns:
        Generated filename with date appended, or None if unsuccessful
    """
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
            llm_output = ask_infomaniak_ai(full_text, url, api_token)
            llm_output = clean_llm_output(llm_output)
            match = find_match(llm_output)
            if is_valid(match):
                match = tidy_match(match, names)
                prompt_stats['name'][idx] += 1
                return append_date_to_filename(match)
    return None


def get_document_category(url: str, input_text: str, categories_list: List[str],
                         api_token: str, extra_context: Optional[str] = None) -> Optional[str]:
    """
    Determine document category using LLM based on document text.

    Args:
        url: API endpoint URL
        input_text: Extracted text from document
        categories_list: List of valid category names
        api_token: API authentication token
        extra_context: Optional additional context for LLM

    Returns:
        Determined category or None if unsuccessful
    """
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
    {chr(10).join(f'{idx + 1}. {cat}' for idx, cat in enumerate(categories_list))}

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

    category_counts: Dict[str, int] = {}
    for idx, prompt in enumerate(prompt_templates):
        for _ in range(RETRIES):
            full_text = prompt.format(content=input_text)
            llm_output = ask_infomaniak_ai(full_text, url, api_token)
            llm_output = clean_llm_output(llm_output)
            cat = find_category(llm_output, categories_list)
            if cat:
                category_counts[cat] = category_counts.get(cat, 0) + 1
                highest_category = highest_count_by_two(category_counts)
                if highest_category:
                    prompt_stats['category'][idx] += 1
                    return highest_category
    return None


def get_filename_and_category(new_filename: Optional[str], category: Optional[str],
                              name: str) -> Tuple[str, str]:
    """
    Construct final filename and category with fallbacks.

    Args:
        new_filename: Generated filename or None
        category: Determined category or None
        name: Name part to prepend

    Returns:
        Tuple of (final_filename, final_category)
    """
    final_category = category if category else 'Unsicher'

    if not new_filename:
        new_filename = f'Unsicher_{random.randint(1, 10000000)}.pdf'
        final_category = 'Unsicher'

    if len(name) > 0:
        new_filename = f'{name}_{new_filename}'

    return new_filename, final_category


def get_name_part(text: str, name_list: List[str]) -> str:
    """
    Extract and format name part from document text.

    Args:
        text: Document text to search
        name_list: List of names to look for

    Returns:
        Formatted name abbreviation
    """
    matches = find_words(text, name_list)
    names_set = set(matches)
    if len(names_set) == 1:
        return list(names_set)[0]
    result = ""
    sorted_list = sorted(list(names_set))
    for match in sorted_list:
        result += match[:2].lower().capitalize()
    return result


def ask_infomaniak_ai(question: str, url: str, api_token: str) -> str:
    """
    Query Infomaniak AI API with a question.

    Args:
        question: The prompt/question to send
        url: API endpoint URL
        api_token: API authentication token

    Returns:
        LLM response content

    Raises:
        Exception: If API request fails
    """
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

    try:
        response = requests.post(url=url, data=data, headers=headers)
        response.raise_for_status()
        response_dict = json.loads(response.text)
        if 'choices' in response_dict:
            return response_dict['choices'][0]['message']['content']
        raise Exception(f"Unexpected API response: {response_dict.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise


def try_upload(input_dir: str, orig_filename: str, new_filename: str, folder: str,
               config: Config) -> bool:
    """
    Attempt to upload a file to KDrive.

    Args:
        input_dir: Source directory
        orig_filename: Original filename
        new_filename: New filename to use
        folder: Destination folder
        config: Config object to use for upload

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
        result = KdriveManager.upload_file(input_dir, orig_filename, new_filename, folder, config)
        return result is not None
    except Exception as e:
        logger.error(f"Upload failed for '{orig_filename}': {e}")
        return False


def process_document(file_path: str, names_tuple: Tuple[List[str], str],
                     categories_dict: Dict, api_url: str, token: str) -> Tuple[str, str]:
    """
    Process a single document file.

    Args:
        file_path: Path to the PDF file
        names_tuple: Tuple of (firstnames, lastname)
        categories_dict: Dictionary of categories
        api_url: API endpoint URL
        token: API authentication token

    Returns:
        Tuple of (final_filename, category)
    """
    content = ocr_file(file_path)
    content = content[:2000]  # Limit to first 2000 characters

    name_part = get_name_part(content, names_tuple[0])
    doc_name = get_document_name(api_url, content, names_tuple, token)
    doc_category = get_document_category(api_url, content, list(categories_dict.keys()), token)

    return get_filename_and_category(doc_name, doc_category, name_part)


def main() -> None:
    """Main execution function."""
    input_directory = Path('input')
    archive_directory = Path('Archive')
    archive_directory.mkdir(exist_ok=True)

    try:
        config = Config('secrets.json')
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    EmailManager.init_and_download(config)

    names = config.NAMES
    lastname = config.LASTNAME
    names_tuple = (names, lastname)
    categories = config.CATEGORIES

    api_token = config.KDRIVE_API_TOKEN
    product_id = config.AI_PRODUCT_ID
    api_url = f"https://api.infomaniak.com/1/ai/{product_id}/openai/chat/completions"

    # Process each subdirectory in input
    for directory in input_directory.iterdir():
        if not directory.is_dir():
            continue

        logger.info(f"Processing directory: {directory}")

        files = list(directory.iterdir())
        for file_path in files:
            if not file_path.is_file():
                continue

            start_time = time.time()

            try:
                filename, category = process_document(
                    str(file_path), names_tuple, categories, api_url, api_token
                )

                # Special handling for specific directories
                if directory.name == 'Steuern':
                    try_upload(str(directory), file_path.name, filename,
                             'Dokumente für Steuern 2025', config)

                if directory.name == '1und1macht3':
                    try_upload(str(directory), file_path.name, filename, '1und1macht3', config)

                # Upload to category folder
                if try_upload(str(directory), file_path.name, filename, category, config):
                    # Move to archive on successful upload
                    shutil.move(str(file_path), str(archive_directory / filename))
                    logger.info(f"Archived {file_path.name} as {filename}")

            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                continue

            elapsed = time.time() - start_time
            logger.info(f"Processing time: {elapsed:.2f} seconds\n")

    # Output prompt statistics
    logger.info("Prompt statistics for document name:")
    for i, count in enumerate(prompt_stats['name']):
        logger.info(f"  Prompt {i + 1}: {count} valid results")
    logger.info("Prompt statistics for document category:")
    for i, count in enumerate(prompt_stats['category']):
        logger.info(f"  Prompt {i + 1}: {count} valid results")


if __name__ == '__main__':
    main()
