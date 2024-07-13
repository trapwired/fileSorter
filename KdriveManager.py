import os
import requests

from ConfigReader import Config

if __name__ == '__main__':
    config = Config('secrets.json')
    username = config.EMAIL_USER
    api_token = config.KDRIVE_API_TOKEN
    drive_id = config.KDRIVE_DRIVE_ID
    directory_id = config.ABLEGEN_FOLDER_ID

    file_name = 'Kündigung_Lucina_Abo.pdf'

    file_path = os.path.join('input', file_name)
    total_size = os.path.getsize(file_path)
    with open(file_path, 'rb') as f:
        data = f.read()

    URL = f"https://api.infomaniak.com/3/drive/{drive_id}/upload?total_size={total_size}&directory_id={directory_id}&file_name={file_name}"

    headers = {
        "Authorization": f"Bearer {api_token}",
        'Content-Type': 'application/octet-stream',
    }
    req = requests.request("POST", url=URL, data=data, headers=headers)

    res = req.json()
    print(res)
