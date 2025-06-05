import json
from pathlib import Path
import re
from datetime import date

from typing import Optional


def write_to_json(data, path: str):
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)  # フォルダがなければ作成
    with open(path_obj, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def read_from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def file_exists(path: str) -> bool:
    return Path(path).is_file()


# 元号と西暦開始年の対応表
ERA_MAPPING = {
    "明治": 1868,
    "大正": 1912,
    "昭和": 1926,
    "平成": 1989,
    "令和": 2019,
}


def convert_japanese_date(japanese_date: Optional[str]) -> Optional[str]:
    """
    「令和7年1月24日」や「令和元年1月24日」などの和暦日付を
    「yyyy-mm-dd」形式に変換（明治以降対応）
    """
    if not japanese_date:
        return None

    # 「元年」にも対応する正規表現
    pattern = r"(明治|大正|昭和|平成|令和)\s*(\d+|元)年\s*(\d+)月\s*(\d+)日"
    match = re.match(pattern, japanese_date)
    if not match:
        raise ValueError(f"不正な日付形式: {japanese_date}")

    era, year_str, month_str, day_str = match.groups()

    # 「元」を数値に変換
    year = 1 if year_str == "元" else int(year_str)
    month = int(month_str)
    day = int(day_str)

    if era not in ERA_MAPPING:
        raise ValueError(f"未対応の元号: {era}")

    western_year = ERA_MAPPING[era] + year - 1  # 元年は +0
    return date(western_year, month, day).isoformat()


def delete_md_files_with_message(directory: str, target_phrase: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_phrase in content:
                md_file.unlink()
                print(f"[削除] {md_file}")
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")


def remove_text_from_md_files(directory: str, target_text: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_text in content:
                new_content = content.replace(target_text, "")
                md_file.write_text(new_content, encoding="utf-8")
                print(f"[修正] {md_file}")
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")


def clean_texts(session: int):
    base_dir = f"data/qa_shu/complete/{session}/a"
    delete_md_files_with_message(
        base_dir,
        "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
    )
    remove_text_from_md_files(
        base_dir,
        """経過へ\n|\n質問本文(PDF)へ\n|\n答弁本文(HTML)へ\n|\n答弁本文(PDF)へ\n""",
    )
    remove_text_from_md_files(base_dir, """経過へ\n|\n質問本文(PDF)へ\n""")
    remove_text_from_md_files(base_dir, """経過へ\n|\n質問本文(PDF)へ""")
