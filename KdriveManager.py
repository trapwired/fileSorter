import logging
from pathlib import Path
from typing import Optional

import requests

from ConfigReader import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def upload_file(
    file_path: str,
    original_filename: str,
    new_filename: str,
    directory: str,
    config: Optional[Config] = None
) -> Optional[str]:
    """
    Upload a file to Infomaniak kDrive.

    Args:
        file_path: Directory path containing the file
        original_filename: Original name of the file to upload
        new_filename: New name for the file on kDrive
        directory: Target directory/category name
        config: Optional Config object. If None, will load from secrets.json

    Returns:
        The new filename if upload succeeded, None otherwise

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If directory is not configured
        requests.exceptions.RequestException: If upload request fails
    """
    # Load config if not provided
    if config is None:
        try:
            config = Config('secrets.json')
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    # Validate directory exists in config
    if directory not in config.CATEGORIES:
        error_msg = f"Directory '{directory}' not found in the configuration file."
        logger.error(error_msg)
        raise ValueError(error_msg)

    directory_id = config.CATEGORIES[directory]
    if not directory_id:
        error_msg = f"Directory ID for '{directory}' is empty in configuration."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Construct file path and validate file exists
    full_filepath = Path(file_path) / original_filename
    if not full_filepath.exists():
        error_msg = f"File not found: {full_filepath}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    if not full_filepath.is_file():
        error_msg = f"Path is not a file: {full_filepath}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get file size and read file data
    try:
        total_size = full_filepath.stat().st_size
        with open(full_filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        logger.error(f"Failed to read file {full_filepath}: {e}")
        raise

    # Prepare API request
    api_token = config.KDRIVE_API_TOKEN
    drive_id = config.KDRIVE_DRIVE_ID
    api_url = (
        f"https://api.infomaniak.com/3/drive/{drive_id}/upload"
        f"?total_size={total_size}&directory_id={directory_id}&file_name={new_filename}"
    )

    headers = {
        "Authorization": f"Bearer {api_token}",
        'Content-Type': 'application/octet-stream',
    }

    # Make upload request
    try:
        logger.info(f"Uploading {original_filename} as {new_filename} to directory '{directory}'")
        response = requests.post(url=api_url, data=data, headers=headers)
        response.raise_for_status()

        result = response.json()
        logger.debug(f"Upload response: {result}")

        if result.get('result') == 'success':
            logger.info(f"Successfully uploaded {new_filename}")
            return new_filename
        else:
            logger.error(f"Upload failed with response: {result}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Upload request failed for {original_filename}: {e}")
        raise
    except ValueError as e:
        logger.error(f"Failed to parse upload response: {e}")
        raise


def main() -> None:
    """Example usage and testing function."""
    try:
        result = upload_file(
            'output/Rechnungen',
            'CaDo_hotel_bergfrieden-preisliste_fuer_und-Jul_24.pdf',
            'Test.pdf',
            'Rechnungen'
        )
        if result:
            logger.info(f"Upload successful: {result}")
        else:
            logger.error("Upload failed")
    except Exception as e:
        logger.error(f"Error during upload: {e}")


if __name__ == '__main__':
    main()
