import os
import requests

from dotenv import load_dotenv

if __name__ == '__main__':
    load_dotenv()
    api_token = os.getenv('KDRIVE_API_TOKEN')
    drive_id = os.getenv('KDRIVE_DRIVE_ID')

    file_path = os.path.join('input', 'Faktenblatt Typischer Haushalt.pdf')
    total_size = os.path.getsize(file_path)
    with open(file_path, 'rb') as f:
        data = f.read()

    URL = f"https://api.infomaniak.com/3/drive/{drive_id}/upload?total_size={total_size}"
    URL = f"https://api.infomaniak.com/2/drive/{drive_id}/activities/reports"

    headers = {
        "Authorization": f"Bearer {api_token}",
        'Content-Type': 'application/octet-stream',
    }
    # req = requests.request("POST", url=URL, data=data, headers=headers)
    req = requests.request("GET", url=URL, headers=headers)

    res = req.json()
    print(res)
