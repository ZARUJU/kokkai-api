"""文字列整形や日付変換に関する補助関数。"""

import re
from datetime import date


ERA_OFFSETS = {
    "明治": 1867,
    "大正": 1911,
    "昭和": 1925,
    "平成": 1988,
    "令和": 2018,
}

EMPTY_VALUES = {"", "-", "－", "―", "未定", "なし", "無し"}


def normalize_text(value: str) -> str:
    """空白やノーブレークスペースを正規化する。"""

    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_int(value: str) -> int | None:
    """文字列中の最初の整数を抽出する。"""

    match = re.search(r"\d+", value)
    if not match:
        return None
    return int(match.group())


def parse_japanese_date(value: str) -> date | None:
    """和暦または西暦の日本語日付を `date` に変換する。"""

    text = normalize_text(value)
    if text in EMPTY_VALUES:
        return None

    western = re.search(r"(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日", text)
    if western:
        return date(
            int(western.group("year")),
            int(western.group("month")),
            int(western.group("day")),
        )

    era = re.search(
        r"(?P<era>明治|大正|昭和|平成|令和)(?P<year>元|\d+)年(?P<month>\d{1,2})月(?P<day>\d{1,2})日",
        text,
    )
    if not era:
        return None

    era_year = 1 if era.group("year") == "元" else int(era.group("year"))
    year = ERA_OFFSETS[era.group("era")] + era_year
    return date(year, int(era.group("month")), int(era.group("day")))
