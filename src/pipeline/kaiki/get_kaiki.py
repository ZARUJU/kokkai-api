"""衆議院サイトの国会会期一覧を取得して JSON に保存する。

引数:
    - --skip-existing: 保存先JSONが既にある場合は取得をスキップ

入力:
    - 会期一覧ページ
      https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiki.htm

出力:
    - data/kaiki.json

主な内容:
    - 国会回次
    - 会期種別
    - 召集日
    - 会期終了日
    - 会期日数
    - 当初会期
    - 延長日数
    - 解散などの注記
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import Kaiki, KaikiDataset
from src.utils import (
    normalize_text,
    parse_int,
    parse_japanese_date,
    polite_get,
    remember_fetched_output,
    should_skip_fetch_output,
)

SOURCE_URL = "https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiki.htm"
OUTPUT_PATH = Path("data/kaiki.json")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="国会会期一覧を取得して JSON として保存する")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="保存先JSONが既にある場合は取得をスキップする",
    )
    return parser.parse_args()


def fetch_html(url: str = SOURCE_URL) -> str:
    """会期一覧ページの HTML を取得する。"""

    response = polite_get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def _consume_span(spans: dict[int, tuple[int, str]], row: list[str], col_idx: int) -> int:
    """rowspan で持ち越されたセルを現在行に展開する。"""

    while col_idx in spans:
        remaining, value = spans[col_idx]
        row.append(value)
        if remaining <= 1:
            spans.pop(col_idx)
        else:
            spans[col_idx] = (remaining - 1, value)
        col_idx += 1
    return col_idx


def extract_table_rows(table: Tag) -> list[list[str]]:
    """rowspan と colspan を考慮してテーブルを2次元配列に展開する。"""

    rows: list[list[str]] = []
    spans: dict[int, tuple[int, str]] = {}

    for tr in table.find_all("tr"):
        row: list[str] = []
        col_idx = 0
        col_idx = _consume_span(spans, row, col_idx)

        for cell in tr.find_all(["th", "td"], recursive=False):
            col_idx = _consume_span(spans, row, col_idx)

            text = normalize_text(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))

            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[col_idx] = (rowspan - 1, text)
                col_idx += 1

        _consume_span(spans, row, col_idx)
        if any(row):
            rows.append(row)

    return rows


def find_kaiki_table(soup: BeautifulSoup) -> Tag:
    """HTML から会期一覧のテーブル要素を特定する。"""

    for table in soup.find_all("table"):
        rows = extract_table_rows(table)
        if not rows:
            continue
        header_text = " ".join(rows[0])
        if "回次" in header_text and "召集日" in header_text and "会期終了日" in header_text:
            return table
    raise ValueError("会期テーブルが見つかりませんでした。HTML構造を確認してください。")


def build_header_map(headers: list[str]) -> dict[str, int]:
    """ヘッダー行から各列の意味を表すインデックス辞書を作る。"""

    header_map: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if "回次" in header:
            header_map["number"] = idx
        elif "召集日" in header:
            header_map["convocation_date"] = idx
        elif "会期終了日" in header or "閉会日" in header:
            header_map["closing_date"] = idx
        elif header == "会期" or ("会期" in header and "当初" not in header):
            header_map["duration_days"] = idx
        elif "当初会期" in header:
            header_map["initial_duration_days"] = idx
        elif "延長" in header:
            header_map["extension_days"] = idx
    if "number" not in header_map:
        raise ValueError(f"回次列を特定できませんでした: {headers}")
    return header_map


def parse_number_and_type(value: str) -> tuple[int | None, str | None]:
    """`第221回（特別会）` のような文字列から回次と種別を抽出する。"""

    text = normalize_text(value)
    match = re.search(r"第\s*(\d+)\s*回(?:\s*[（(]\s*(.+?)\s*[）)])?", text)
    if not match:
        return parse_int(text), None
    return int(match.group(1)), match.group(2)


def parse_closing_note(value: str) -> str | None:
    """会期終了日セルから日付以外の注記を取り出す。"""

    text = normalize_text(value)
    if not text:
        return None

    note = re.sub(
        r"[（(]?\s*((?:明治|大正|昭和|平成|令和)(?:元|\d+)|\d{4})年\d{1,2}月\d{1,2}日",
        "",
        text,
    )
    note = note.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    note = normalize_text(note)
    return note or None


def parse_kaiki_table(table: Tag) -> list[Kaiki]:
    """会期一覧テーブルを `Kaiki` の配列に変換する。"""

    rows = extract_table_rows(table)
    if not rows:
        return []

    header_map = build_header_map(rows[0])
    items: list[Kaiki] = []

    for row in rows[1:]:
        if len(row) <= header_map["number"]:
            continue

        number, session_type = parse_number_and_type(row[header_map["number"]])
        if number is None:
            continue

        convocation_date = None
        if "convocation_date" in header_map and len(row) > header_map["convocation_date"]:
            convocation_date = parse_japanese_date(row[header_map["convocation_date"]])

        closing_date = None
        closing_note = None
        if "closing_date" in header_map and len(row) > header_map["closing_date"]:
            closing_raw = row[header_map["closing_date"]]
            closing_date = parse_japanese_date(closing_raw)
            closing_note = parse_closing_note(closing_raw)

        duration_days = None
        if "duration_days" in header_map and len(row) > header_map["duration_days"]:
            duration_days = parse_int(row[header_map["duration_days"]])

        initial_duration_days = None
        if "initial_duration_days" in header_map and len(row) > header_map["initial_duration_days"]:
            initial_duration_days = parse_int(row[header_map["initial_duration_days"]])

        extension_days = None
        if "extension_days" in header_map and len(row) > header_map["extension_days"]:
            extension_days = parse_int(row[header_map["extension_days"]])

        items.append(
            Kaiki(
                number=number,
                session_type=session_type,
                convocation_date=convocation_date,
                closing_date=closing_date,
                closing_note=closing_note,
                duration_days=duration_days,
                initial_duration_days=initial_duration_days,
                extension_days=extension_days,
            )
        )

    return items


def build_dataset(html: str) -> KaikiDataset:
    """HTML 全体から会期データセットを構築する。"""

    soup = BeautifulSoup(html, "html.parser")
    table = find_kaiki_table(soup)
    items = parse_kaiki_table(table)
    if not items:
        raise ValueError("会期データを抽出できませんでした。")
    return KaikiDataset(
        source_url=SOURCE_URL,
        fetched_at=datetime.now(timezone.utc),
        items=items,
    )


def save_dataset(dataset: KaikiDataset, output_path: Path = OUTPUT_PATH) -> None:
    """データセットを整形済み JSON として保存する。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    remember_fetched_output(output_path)


def main() -> None:
    """会期一覧の取得から保存までを実行する。"""

    args = parse_args()
    if should_skip_fetch_output(OUTPUT_PATH, args.skip_existing):
        return

    html = fetch_html()
    dataset = build_dataset(html)
    save_dataset(dataset)


if __name__ == "__main__":
    main()
