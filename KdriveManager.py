import os
import requests

from ConfigReader import Config


def upload_file(file_path, original_filename, new_filename, directory):
    config = Config('secrets.json')
    api_token = config.KDRIVE_API_TOKEN
    drive_id = config.KDRIVE_DRIVE_ID
    directory_id = config.CATEGORIES[directory]
    if not directory_id:
        # raise ValueError(f"Directory '{directory}' not found in the configuration file.")
        print(f"Directory '{directory}' not found in the configuration file.")
        return

    full_filepath = os.path.join(file_path, original_filename)
    total_size = os.path.getsize(full_filepath)
    with open(full_filepath, 'rb') as f:
        data = f.read()

    URL = f"https://api.infomaniak.com/3/drive/{drive_id}/upload?total_size={total_size}&directory_id={directory_id}&file_name={new_filename}"

    headers = {
        "Authorization": f"Bearer {api_token}",
        'Content-Type': 'application/octet-stream',
    }
    req = requests.request("POST", url=URL, data=data, headers=headers)

    res = req.json()
    print(res)

    if 'result' in res and res['result'] == 'success':
        return new_filename


if __name__ == '__main__':
    upload_file('output/Rechnungen', 'CaDo_hotel_bergfrieden-preisliste_fuer_und-Jul_24.pdf', 'Test')
