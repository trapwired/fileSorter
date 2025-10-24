import email
import imaplib
import logging
import random
from pathlib import Path
from typing import Tuple

from ConfigReader import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_new_scanned_emails(
    email_user: str,
    email_pass: str,
    email_server: str,
    subject: str,
    storage_dir: Path
) -> int:
    """
    Download email attachments with a specific subject and delete the emails.

    Args:
        email_user: Email account username
        email_pass: Email account password
        email_server: IMAP server address
        subject: Subject line to search for
        storage_dir: Directory to save attachments

    Returns:
        Number of attachments downloaded

    Raises:
        imaplib.IMAP4.error: If IMAP operations fail
        Exception: For other email processing errors
    """
    download_count = 0
    mail = None

    try:
        # Connect and login
        logger.info(f"Connecting to {email_server} as {email_user}")
        mail = imaplib.IMAP4_SSL(email_server)
        mail.login(email_user, email_pass)
        mail.select("inbox")

        # Search for emails with specific subject
        logger.info(f"Searching for emails with subject: {subject}")
        result, data = mail.uid('search', None, f'(HEADER Subject "{subject}")')

        if result != 'OK':
            logger.warning(f"Search failed for subject '{subject}'")
            return 0

        email_ids = data[0].split()
        if not email_ids:
            logger.info(f"No emails found with subject '{subject}'")
            return 0

        email_ids = [e_id.decode() for e_id in email_ids]
        logger.info(f"Found {len(email_ids)} email(s) with subject '{subject}'")

        # Process each email
        for e_id in email_ids:
            try:
                _, response = mail.uid('fetch', e_id, '(BODY.PEEK[])')
                if not response or not response[0]:
                    logger.warning(f"Failed to fetch email {e_id}")
                    continue

                raw_email = response[0][1].decode('utf-8', errors='ignore')
                email_message = email.message_from_string(raw_email)

                # Process attachments
                attachment_count = 0
                for part in email_message.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue

                    # Generate unique filename
                    filename = part.get_filename()
                    if not filename:
                        filename = f'{subject}_{random.randint(1, 10000000)}.pdf'

                    file_path = storage_dir / filename

                    # Save attachment if it doesn't exist
                    if not file_path.exists():
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                file_path.write_bytes(payload)
                                download_count += 1
                                attachment_count += 1
                                logger.info(f"Saved attachment: {filename}")
                        except Exception as e:
                            logger.error(f"Failed to save attachment {filename}: {e}")

                if attachment_count > 0:
                    logger.info(f"Downloaded {attachment_count} attachment(s) from email {e_id}")

                # Delete the email
                result = mail.uid('STORE', e_id, '+FLAGS', r'(\Deleted)')
                if result[0] == 'OK':
                    mail.expunge()
                    logger.debug(f"Deleted email {e_id}")
                else:
                    logger.warning(f"Failed to delete email {e_id}")

            except Exception as e:
                logger.error(f"Error processing email {e_id}: {e}")
                continue

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during email download: {e}")
        raise
    finally:
        # Ensure connection is closed
        if mail:
            try:
                mail.logout()
                logger.debug("Logged out from email server")
            except Exception as e:
                logger.warning(f"Error during logout: {e}")

    return download_count


def init_and_download(config: Config) -> Tuple[int, int, int]:
    """
    Initialize storage directories and download emails from configured subjects.

    Args:
        config: Configuration object with email credentials

    Returns:
        Tuple of (ablegen_count, steuern_count, business_count)

    Raises:
        Exception: If email download fails
    """
    try:
        username = config.EMAIL_USER
        server = config.EMAIL_SERVER
        password = config.EMAIL_PASSWORD
    except AttributeError as e:
        logger.error(f"Missing email configuration: {e}")
        raise ValueError("Email configuration incomplete") from e

    # Create storage directories
    base_dir = Path('input')
    storage_dirs = {
        'Ablegen': base_dir / 'Ablegen',
        'Steuern': base_dir / 'Steuern',
        '1und1macht3': base_dir / '1und1macht3'
    }

    for dir_name, dir_path in storage_dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {dir_path}")

    # Download emails for each category
    download_counts = {}
    email_subjects = {
        'Ablegen': 'Scan-Ablegen',
        'Steuern': 'Scan-Steuern',
        '1und1macht3': 'Scan-1und1macht3'
    }

    for category, subject in email_subjects.items():
        try:
            logger.info(f"Processing category: {category}")
            count = download_new_scanned_emails(
                username, password, server, subject, storage_dirs[category]
            )
            download_counts[category] = count
            logger.info(f"Downloaded {count} file(s) for {category}")
        except Exception as e:
            logger.error(f"Failed to download emails for {category}: {e}")
            download_counts[category] = 0

    total = sum(download_counts.values())
    logger.info(
        f"Download completed: Total={total}, "
        f"Ablegen={download_counts['Ablegen']}, "
        f"Steuern={download_counts['Steuern']}, "
        f"1und1macht3={download_counts['1und1macht3']}"
    )

    return (
        download_counts['Ablegen'],
        download_counts['Steuern'],
        download_counts['1und1macht3']
    )


def main() -> None:
    """Main execution function for testing."""
    try:
        config = Config('secrets.json')
        ablegen, steuern, business = init_and_download(config)
        logger.info(f"Successfully downloaded files: Ablegen={ablegen}, Steuern={steuern}, Business={business}")
    except Exception as e:
        logger.error(f"Email download failed: {e}")
        raise


if __name__ == '__main__':
    main()
