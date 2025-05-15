# fileSorter
An automated way to archive your files, with OCR and a LLM

## The idea
1. Scan a document to email
2. Download attachements (+ Delete Mail)
3. convert to text via OCR
4. Use a LLM (Llama 3.3 via infomaniak) to generate a suitable filename
5. Use a LLM (Llama 3.3 via infomaniak) to sort the file into a set of categories
6. Upload the file to kDrive into the respective folder

# secrets.json file
To work, a secret.json file has to be present in the root directory, containing some additional information. You can find an example in the repository.