# fileSorter
An automated way to archive your files, with OCR and a LLM

## The idea
1. Scan a document to email
2. Download attachements (+ Delete Mail)
3. convert to text via OCR
4. Use a LLM to generate a suitable filename
5. Use a LLM to sort the file into a set of categories
6. Upload the file to kDrive into the respective folder

# .env file
To work, a .env file has to be present in the root directory, containing some additional information. It should have the following structure:
```
EMAIL_USER=username@server.ch
EMAIL_PASSWORD=password
EMAIL_SERVER=email.server.com

KDRIVE_API_TOKEN=123456APITOKEN123456
KDRIVE_DRIVE_ID=123456

NAMES=Rick, John, Louise
CATEGORIES=Bills, Living, Unsure, Other Category
```