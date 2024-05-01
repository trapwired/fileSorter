import os
import email
import imaplib
import random

from dotenv import load_dotenv


def download_new_scanned_emails(email_user, email_pass, email_server, subject):
    mail = imaplib.IMAP4_SSL(email_server)
    mail.login(email_user, email_pass)
    mail.select("inbox")

    result, data = mail.uid('search', None, f'(HEADER Subject "{subject}")')

    email_ids = data[0].split()
    email_ids = [e_id.decode() for e_id in email_ids]

    for e_id in email_ids:
        _, response = mail.uid('fetch', e_id, '(BODY.PEEK[])')
        raw_email = response[0][1].decode()
        email_message = email.message_from_string(raw_email)

        # Downloading attachments
        for part in email_message.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            fileName = f'{subject}_{random.randint(1, 10000000)}.pdf'

            if bool(fileName):
                filePath = os.path.join('input', fileName)
                if not os.path.isfile(filePath):
                    with open(filePath, 'wb') as f:
                        f.write(part.get_payload(decode=True))

        # Moving the mail to 'Trash'
        result = mail.uid('STORE', e_id, '+FLAGS', r'(\Deleted)')
        mail.expunge()

    # Close the connection
    mail.logout()


if __name__ == '__main__':
    load_dotenv()
    username = os.getenv('EMAIL_USER')
    server = os.getenv('EMAIL_SERVER')
    password = os.getenv('EMAIL_PASSWORD')
    download_new_scanned_emails(username, password, server, 'Scan-Ablegen')
    download_new_scanned_emails(username, password, server, 'Scan-Steuern')
