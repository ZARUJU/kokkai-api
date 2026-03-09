"""保存済みの議案一覧 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/gian/list/{session}.html

出力:
    - tmp/gian/list/{session}.json

主な内容:
    - 議案カテゴリ
    - 決算その他の下位種類
    - 提出回次
    - 番号
    - 議案件名
    - 審議状況
    - 経過情報 URL
    - 本文情報 URL
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import GianItem, GianListDataset
from src.utils import normalize_text, parse_int

SOURCE_URL_TEMPLATE = "https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{session}.htm"
INPUT_DIR = Path("tmp/gian/list")
OUTPUT_DIR = Path("tmp/gian/list")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案一覧HTMLをパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """国会回次から議案一覧ページ URL を生成する。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def load_html(session: int, input_dir: Path = INPUT_DIR) -> str:
    """保存済みの議案一覧 HTML を読み込む。"""

    input_path = input_dir / f"{session}.html"
    return input_path.read_text(encoding="utf-8")


def extract_table_rows(table: Tag) -> list[list[Tag]]:
    """テーブルを行単位・セル単位の配列として取り出す。"""

    rows: list[list[Tag]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if cells:
            rows.append(cells)
    return rows


def iter_gian_tables(soup: BeautifulSoup) -> list[tuple[str, Tag]]:
    """議案一覧の各カテゴリテーブルを列挙する。"""

    tables: list[tuple[str, Tag]] = []
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption is None:
            continue
        category = normalize_text(caption.get_text(" ", strip=True))
        if category.endswith("の一覧") or category == "決算その他":
            tables.append((category.replace("の一覧", ""), table))
    return tables


def extract_link_url(cell: Tag, base_url: str) -> str | None:
    """セル内リンクを絶対 URL に変換して返す。"""

    link = cell.find("a", href=True)
    if link is None:
        return None
    return urljoin(base_url, link["href"])


def build_header_map(headers: list[str]) -> dict[str, int]:
    """ヘッダー行から列の意味を表すインデックス辞書を作る。"""

    header_map: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if "種類" in header:
            header_map["subcategory"] = idx
        elif "提出回次" in header:
            header_map["submitted_session"] = idx
        elif "番号" in header:
            header_map["bill_number"] = idx
        elif "議案件名" in header:
            header_map["title"] = idx
        elif "審議状況" in header:
            header_map["status"] = idx
        elif "経過情報" in header:
            header_map["progress_url"] = idx
        elif "本文情報" in header:
            header_map["text_url"] = idx
    if "title" not in header_map:
        raise ValueError(f"議案件名列を特定できませんでした: {headers}")
    return header_map


def split_header_and_rows(table: Tag, rows: list[list[Tag]]) -> tuple[list[str], list[list[Tag]]]:
    """テーブルからヘッダー行とデータ行を切り分ける。"""

    direct_headers = table.find_all("th", recursive=False)
    if direct_headers:
        headers = [normalize_text(cell.get_text(" ", strip=True)) for cell in direct_headers]
        return headers, rows

    if not rows:
        return [], []

    headers = [normalize_text(cell.get_text(" ", strip=True)) for cell in rows[0]]
    return headers, rows[1:]


def parse_gian_table(category: str, table: Tag, base_url: str) -> list[GianItem]:
    """カテゴリごとの議案テーブルを `GianItem` 配列へ変換する。"""

    rows = extract_table_rows(table)
    if not rows:
        return []

    headers, data_rows = split_header_and_rows(table, rows)
    header_map = build_header_map(headers)
    items: list[GianItem] = []

    for row in data_rows:
        texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in row]
        if len(texts) <= header_map["title"]:
            continue

        title = texts[header_map["title"]]
        if not title:
            continue

        subcategory = None
        if "subcategory" in header_map and len(texts) > header_map["subcategory"]:
            subcategory = texts[header_map["subcategory"]] or None

        submitted_session = None
        if "submitted_session" in header_map and len(texts) > header_map["submitted_session"]:
            submitted_session = parse_int(texts[header_map["submitted_session"]])

        bill_number = None
        if "bill_number" in header_map and len(texts) > header_map["bill_number"]:
            bill_number = parse_int(texts[header_map["bill_number"]])

        status = None
        if "status" in header_map and len(texts) > header_map["status"]:
            status = texts[header_map["status"]] or None

        progress_url = None
        if "progress_url" in header_map and len(row) > header_map["progress_url"]:
            progress_url = extract_link_url(row[header_map["progress_url"]], base_url)

        text_url = None
        if "text_url" in header_map and len(row) > header_map["text_url"]:
            text_url = extract_link_url(row[header_map["text_url"]], base_url)

        items.append(
            GianItem(
                category=category,
                subcategory=subcategory,
                submitted_session=submitted_session,
                bill_number=bill_number,
                title=title,
                status=status,
                progress_url=progress_url,
                text_url=text_url,
            )
        )

    return items


def build_dataset(session: int, html: str, source_url: str) -> GianListDataset:
    """HTML 全体から指定回次の議案一覧データセットを構築する。"""

    soup = BeautifulSoup(html, "html.parser")
    items: list[GianItem] = []
    for category, table in iter_gian_tables(soup):
        items.extend(parse_gian_table(category=category, table=table, base_url=source_url))

    if not items:
        raise ValueError("議案一覧データを抽出できませんでした。")

    return GianListDataset(
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
        session_number=session,
        items=items,
    )


def save_dataset(dataset: GianListDataset, session: int, output_dir: Path = OUTPUT_DIR) -> Path:
    """パース済み議案一覧を JSON に保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.json"
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の保存済み議案一覧 HTML をパースして JSON 保存する。"""

    input_path = input_dir / f"{session}.html"
    logger.info("議案一覧JSONパース開始: session=%s path=%s", session, input_path)
    html = load_html(session=session, input_dir=input_dir)
    dataset = build_dataset(session=session, html=html, source_url=build_source_url(session))
    output_path = save_dataset(dataset=dataset, session=session, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("議案一覧JSONパース完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の保存済み議案一覧 HTML をパースして JSON 保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
