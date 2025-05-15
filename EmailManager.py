import os
import email
import imaplib
import random

from ConfigReader import Config


def download_new_scanned_emails(email_user, email_pass, email_server, subject, storage_dir):
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
                filePath = os.path.join(storage_dir, fileName)
                if not os.path.isfile(filePath):
                    with open(filePath, 'wb') as f:
                        f.write(part.get_payload(decode=True))

        # Moving the mail to 'Trash'
        result = mail.uid('STORE', e_id, '+FLAGS', r'(\Deleted)')
        mail.expunge()

    # Close the connection
    mail.logout()


if __name__ == '__main__':
    config = Config('secrets.json')
    username = config.EMAIL_USER
    server = config.EMAIL_SERVER
    password = config.EMAIL_PASSWORD

    storage_dir_ablegen = os.path.join('input', 'Ablegen')
    os.makedirs(storage_dir_ablegen, exist_ok=True)
    storage_dir_steuern = os.path.join('input', 'Steuern')
    os.makedirs(storage_dir_steuern, exist_ok=True)
    storage_dir_1und1macht3 = os.path.join('input', '1und1macht3')
    os.makedirs(storage_dir_1und1macht3, exist_ok=True)

    download_new_scanned_emails(username, password, server, 'Scan-Ablegen', storage_dir_ablegen)
    download_new_scanned_emails(username, password, server, 'Scan-Steuern', storage_dir_steuern)
    download_new_scanned_emails(username, password, server, 'Scan-1und1macht3', storage_dir_1und1macht3)
