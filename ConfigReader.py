import json


class Config:
    def __init__(self, filename):
        with open(filename, 'r') as f:
            data = json.load(f)

        for key, value in data.items():
            if key == 'NAMES':
                if not isinstance(value, list):
                    value = [value]
            elif isinstance(value, dict):
                setattr(self, key, value)
            else:
                setattr(self, key, str(value))
            setattr(self, key, value)
