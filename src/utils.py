"""文字列整形や日付変換に関する補助関数。"""

import hashlib
import re
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlparse


ERA_OFFSETS = {
    "明治": 1867,
    "大正": 1911,
    "昭和": 1925,
    "平成": 1988,
    "令和": 2018,
}

EMPTY_VALUES = {"", "-", "－", "―", "未定", "なし", "無し"}
GIAN_CATEGORY_CODES = {
    "衆法": "shu_law",
    "参法": "san_law",
    "閣法": "cab_law",
    "予算": "budget",
    "承認": "approval",
    "決算その他": "settlement",
    "決算": "settlement",
}


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

    western = re.search(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日", text)
    if western:
        return date(
            int(western.group("year")),
            int(western.group("month")),
            int(western.group("day")),
        )

    era = re.search(
        r"(?P<era>明治|大正|昭和|平成|令和)\s*(?P<year>元|\d+)\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日",
        text,
    )
    if not era:
        return None

    era_year = 1 if era.group("year") == "元" else int(era.group("year"))
    year = ERA_OFFSETS[era.group("era")] + era_year
    return date(year, int(era.group("month")), int(era.group("day")))


def slugify_japanese_label(value: str) -> str:
    """日本語ラベルを保存パス向けの簡易 slug に変換する。"""

    text = normalize_text(value).lower()
    replacements = {
        "決算": "kessan",
        "国有財産": "kokuyu_zaisan",
        "国庫債務": "kokko_saimu",
        "ｎｈｋ決算": "nhk_kessan",
        "nhk決算": "nhk_kessan",
    }
    if text in replacements:
        return replacements[text]

    ascii_text = re.sub(r"[^a-z0-9]+", "_", text)
    ascii_text = ascii_text.strip("_")
    if ascii_text:
        return ascii_text

    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"label_{digest}"


def build_gian_bill_id(
    category: str,
    submitted_session: int | None,
    bill_number: int | None,
    title: str,
    subcategory: str | None = None,
) -> str:
    """議案一覧の1件から安定した議案 ID を生成する。"""

    category_code = GIAN_CATEGORY_CODES.get(category, slugify_japanese_label(category))
    session_label = str(submitted_session) if submitted_session is not None else "unknown"
    if bill_number is not None:
        return f"{session_label}-{category_code}-{bill_number}"

    subcategory_slug = slugify_japanese_label(subcategory or "unknown")
    title_hash = hashlib.sha1(normalize_text(title).encode("utf-8")).hexdigest()[:8]
    return f"{session_label}-{category_code}-{subcategory_slug}-{title_hash}"


def build_text_document_filename(url: str) -> str:
    """本文ページ配下の文書 URL から保存用ファイル名を生成する。"""

    path = PurePosixPath(urlparse(url).path)
    parent = slugify_japanese_label(path.parent.name or "document")
    stem = slugify_japanese_label(path.stem or "item")
    return f"{parent}_{stem}.html"
