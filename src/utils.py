"""文字列整形や日付変換に関する補助関数。"""

import hashlib
import re
from datetime import date, time
from pathlib import Path, PurePosixPath
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
KANJI_DIGITS = {
    "〇": 0,
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
KANJI_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
}


def build_shugiin_shitsumon_id(session_number: int, question_number: int) -> str:
    """衆議院質問主意書の安定した ID を生成する。"""

    return f"shu-{session_number}-{question_number:03d}"


def build_sangiin_shitsumon_id(session_number: int, question_number: int) -> str:
    """参議院質問主意書の安定した ID を生成する。"""

    return f"san-{session_number}-{question_number:03d}"


def build_shugiin_seigan_id(session_number: int, petition_number: int) -> str:
    """衆議院請願の安定した ID を生成する。"""

    return f"shu-seigan-{session_number}-{petition_number:04d}"


def build_sangiin_seigan_id(session_number: int, petition_number: int) -> str:
    """参議院請願の安定した ID を生成する。"""

    return f"san-seigan-{session_number}-{petition_number:04d}"


def normalize_text(value: str) -> str:
    """空白やノーブレークスペースを正規化する。"""

    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def detect_html_charset(content: bytes, content_type: str | None = None) -> str | None:
    """HTTP ヘッダや HTML 先頭から文字コード名を推定する。"""

    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    head = content[:4096]
    meta_patterns = (
        rb"<meta[^>]+charset=['\"]?\s*([A-Za-z0-9._-]+)",
        rb"<meta[^>]+content=['\"][^'\"]*charset=([A-Za-z0-9._-]+)",
    )
    for pattern in meta_patterns:
        match = re.search(pattern, head, flags=re.IGNORECASE)
        if match:
            return match.group(1).decode("ascii", errors="ignore")
    return None


def normalize_html_encoding_name(encoding: str | None) -> str | None:
    """HTML デコード向けにエンコーディング名を正規化する。"""

    if not encoding:
        return None

    normalized = encoding.strip().lower().replace("-", "_")
    if normalized in {"shift_jis", "shiftjis", "sjis", "ms_kanji", "x_sjis"}:
        return "cp932"
    if normalized in {"windows_31j", "ms932", "cp943c"}:
        return "cp932"
    if normalized == "utf8":
        return "utf-8"
    if normalized in {"eucjp", "euc_jp"}:
        return "euc_jp"
    return encoding.strip()


def decode_html_bytes(content: bytes, content_type: str | None = None, fallback_encoding: str | None = None) -> str:
    """HTML bytes を推定した文字コードで文字列へ変換する。"""

    candidates: list[str] = []
    for encoding in (
        "cp932",
        detect_html_charset(content=content, content_type=content_type),
        fallback_encoding,
        "utf-8",
        "shift_jis",
        "euc_jp",
    ):
        normalized = normalize_html_encoding_name(encoding)
        if normalized and normalized.lower() not in {candidate.lower() for candidate in candidates}:
            candidates.append(normalized)

    for encoding in candidates:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def strip_agenda_item_prefix(value: str) -> str:
    """案件見出し先頭の番号や日程ラベルを除去する。"""

    text = normalize_text(value).lstrip("○")
    text = re.sub(r"^[一二三四五六七八九十百千]+、", "", text)
    text = re.sub(r"^日程第[一二三四五六七八九十百千\d]+(?:及び第[一二三四五六七八九十百千\d]+)*\s*", "", text)
    return text.strip()


def normalize_bill_match_text(value: str) -> str:
    """議案名照合向けに案件文を正規化する。"""

    text = strip_agenda_item_prefix(value)
    text = re.sub(r"（[^）]*提出[^）]*）", "", text)
    text = re.sub(r"（[^）]*衆法[^）]*）", "", text)
    text = re.sub(r"（[^）]*参法[^）]*）", "", text)
    text = re.sub(r"（[^）]*閣法[^）]*）", "", text)
    text = re.sub(r"（趣旨説明）", "", text)
    text = re.sub(r"（予）", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def normalize_petition_match_text(value: str) -> str:
    """請願名照合向けに案件文を正規化する。"""

    text = strip_agenda_item_prefix(value)
    text = re.sub(r"外[〇零一二三四五六七八九十百千\d]+件の請願$", "請願", text)
    text = re.sub(r"（第[^）]*号[^）]*）", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def strip_name_honorific(value: str) -> str:
    """人名末尾の敬称 `君` を除去する。"""

    text = normalize_text(value)
    text = re.sub(r"君(?=外)", "", text)
    text = re.sub(r"君$", "", text)
    return text.strip()


def normalize_person_name(value: str) -> str:
    """人物名の体裁差を吸収し、氏名中の空白を除去する。"""

    text = strip_name_honorific(value)
    return re.sub(r"\s+", "", text)


def split_person_and_count(value: str) -> tuple[str, int | None, bool]:
    """`山田太郎君外一名` のような表記を代表者名と人数情報に分解する。"""

    text = normalize_text(value)
    if not text:
        return "", None, False

    match = re.fullmatch(r"(?P<name>.+?)君?\s*外(?P<count>元|\d+|[〇零一二三四五六七八九十百千]+)名", text)
    if not match:
        return strip_name_honorific(text), None, False

    name = strip_name_honorific(match.group("name"))
    additional_count = parse_japanese_number(match.group("count"))
    if additional_count is None:
        return name, None, True
    return name, additional_count + 1, True


def parse_int(value: str) -> int | None:
    """文字列中の最初の整数を抽出する。"""

    match = re.search(r"\d+", value)
    if not match:
        return None
    return int(match.group())


def parse_japanese_number(value: str) -> int | None:
    """漢数字または算用数字を整数に変換する。"""

    text = normalize_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    if text == "元":
        return 1
    if all(char in KANJI_DIGITS for char in text):
        return int("".join(str(KANJI_DIGITS[char]) for char in text))

    total = 0
    current = 0
    for char in text:
        if char in KANJI_DIGITS:
            current = KANJI_DIGITS[char]
            continue
        if char in KANJI_UNITS:
            unit = KANJI_UNITS[char]
            total += (current or 1) * unit
            current = 0
            continue
        return None
    return total + current


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
        (
            r"(?P<era>明治|大正|昭和|平成|令和)\s*"
            r"(?P<year>元|\d+|[〇零一二三四五六七八九十百千]+)\s*年\s*"
            r"(?P<month>\d{1,2}|[〇零一二三四五六七八九十]+)\s*月\s*"
            r"(?P<day>\d{1,2}|[〇零一二三四五六七八九十]+)\s*日"
        ),
        text,
    )
    if not era:
        return None

    era_year = parse_japanese_number(era.group("year"))
    month = parse_japanese_number(era.group("month"))
    day = parse_japanese_number(era.group("day"))
    if era_year is None or month is None or day is None:
        return None
    year = ERA_OFFSETS[era.group("era")] + era_year
    return date(year, month, day)


def parse_japanese_date_with_default_year(value: str, default_year: int) -> date | None:
    """年が省略された `十二月十六日` のような表記を既定年つきで解釈する。"""

    text = normalize_text(value)
    parsed = parse_japanese_date(text)
    if parsed is not None:
        return parsed

    match = re.search(
        r"(?P<month>\d{1,2}|[〇零一二三四五六七八九十]+)\s*月\s*(?P<day>\d{1,2}|[〇零一二三四五六七八九十]+)\s*日",
        text,
    )
    if not match:
        return None

    month = parse_japanese_number(match.group("month"))
    day = parse_japanese_number(match.group("day"))
    if month is None or day is None:
        return None
    return date(default_year, month, day)


def parse_japanese_time(value: str) -> time | None:
    """`午前十時四分` や `午後一時三十分` のような表記を `time` に変換する。"""

    text = normalize_text(value)
    if "正午" in text:
        return time(hour=12, minute=0)

    match = re.search(
        (
            r"(?P<ampm>午前|午後)\s*"
            r"(?P<hour>\d{1,2}|[〇零一二三四五六七八九十]+)\s*時"
            r"(?:\s*(?P<minute>\d{1,2}|[〇零一二三四五六七八九十]+)\s*分)?"
        ),
        text,
    )
    if not match:
        return None

    hour = parse_japanese_number(match.group("hour"))
    minute = parse_japanese_number(match.group("minute") or "0")
    if hour is None or minute is None:
        return None
    if match.group("ampm") == "午後" and hour < 12:
        hour += 12
    if match.group("ampm") == "午前" and hour == 12:
        hour = 0
    return time(hour=hour, minute=minute)


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


def should_skip_existing(path: Path, skip_existing: bool) -> bool:
    """`--skip-existing` 指定時に既存ファイルをスキップするか判定する。"""

    return skip_existing and path.exists()
