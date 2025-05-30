import json
from pathlib import Path


def write_to_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def read_from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def file_exists(path: str) -> bool:
    return Path(path).is_file()
