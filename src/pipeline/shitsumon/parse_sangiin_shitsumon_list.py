"""保存済みの参議院質問主意書一覧 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/shitsumon/sangiin/list/{session}.html

出力:
    - tmp/shitsumon/sangiin/list/{session}.json

主な内容:
    - 質問番号
    - 質問件名
    - 提出者氏名
    - 詳細ページ URL
    - 質問本文 URL
    - 質問本文 PDF URL
    - 答弁本文 URL
    - 答弁本文 PDF URL
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

from src.models import SangiinShitsumonItem, SangiinShitsumonListDataset
from src.utils import normalize_text, parse_int

SOURCE_URL_TEMPLATE = "https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session:03d}/syuisyo.htm"
INPUT_DIR = Path("tmp/shitsumon/sangiin/list")
OUTPUT_DIR = Path("tmp/shitsumon/sangiin/list")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の参議院質問主意書一覧HTMLをパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """国会回次から一覧ページ URL を生成する。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def load_html(session: int, input_dir: Path = INPUT_DIR) -> str:
    """保存済みの一覧 HTML を読み込む。"""

    input_path = input_dir / f"{session}.html"
    return input_path.read_text(encoding="utf-8")


def find_list_table(soup: BeautifulSoup) -> Tag:
    """質問主意書一覧テーブルを取得する。"""

    tables = soup.find_all("table", class_="list_c")
    if not tables:
        raise ValueError("参議院質問主意書一覧テーブルを特定できませんでした。")
    return tables[-1]


def extract_link_url(cell: Tag, base_url: str, pattern: str | None = None) -> str | None:
    """セル内リンクを絶対 URL に変換して返す。"""

    for link in cell.find_all("a", href=True):
        href = link["href"]
        if pattern is not None and pattern not in href:
            continue
        return urljoin(base_url, href)
    return None


def parse_items(table: Tag, base_url: str) -> list[SangiinShitsumonItem]:
    """一覧テーブルを `SangiinShitsumonItem` 配列へ変換する。"""

    rows = table.find_all("tr", recursive=False)
    items: list[SangiinShitsumonItem] = []
    idx = 0
    while idx < len(rows):
        first_cells = rows[idx].find_all(["th", "td"], recursive=False)
        if len(first_cells) < 3:
            idx += 1
            continue

        first_texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in first_cells]
        title = first_texts[-1]
        detail_url = extract_link_url(rows[idx], base_url, "meisai/")
        if not title:
            idx += 1
            continue

        submitter_name = None
        question_number = None
        question_html_url = None
        answer_html_url = None
        question_pdf_url = None
        answer_pdf_url = None

        if idx + 1 < len(rows):
            second_cells = rows[idx + 1].find_all(["th", "td"], recursive=False)
            second_texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in second_cells]
            if second_texts:
                question_number = parse_int(second_texts[0])
            if len(second_texts) >= 3:
                submitter_name = second_texts[2] or None
            question_html_url = extract_link_url(rows[idx + 1], base_url, "syuh/")
            answer_html_url = extract_link_url(rows[idx + 1], base_url, "touh/")

        if question_number is None:
            idx += 1
            continue

        if idx + 2 < len(rows):
            question_pdf_url = extract_link_url(rows[idx + 2], base_url, "syup/")
            answer_pdf_url = extract_link_url(rows[idx + 2], base_url, "toup/")

        items.append(
            SangiinShitsumonItem(
                question_number=question_number,
                title=title,
                submitter_name=submitter_name,
                detail_url=detail_url,
                question_html_url=question_html_url,
                question_pdf_url=question_pdf_url,
                answer_html_url=answer_html_url,
                answer_pdf_url=answer_pdf_url,
            )
        )
        idx += 3
    return items


def build_dataset(session: int, html: str, source_url: str) -> SangiinShitsumonListDataset:
    """HTML 全体から指定回次の一覧データセットを構築する。"""

    soup = BeautifulSoup(html, "html.parser")
    table = find_list_table(soup)
    session_label = None
    session_node = soup.find("p", class_="exp")
    if session_node is not None:
        session_label = normalize_text(session_node.get_text(" ", strip=True)) or None
    items = parse_items(table=table, base_url=source_url)
    if not items:
        raise ValueError("参議院質問主意書一覧データを抽出できませんでした。")
    return SangiinShitsumonListDataset(
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
        session_number=session,
        session_label=session_label,
        items=items,
    )


def save_dataset(dataset: SangiinShitsumonListDataset, session: int, output_dir: Path = OUTPUT_DIR) -> Path:
    """パース済み一覧を JSON に保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.json"
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の保存済み一覧 HTML をパースして JSON 保存する。"""

    input_path = input_dir / f"{session}.html"
    logger.info("参議院質問主意書一覧JSONパース開始: session=%s path=%s", session, input_path)
    html = load_html(session=session, input_dir=input_dir)
    dataset = build_dataset(session=session, html=html, source_url=build_source_url(session))
    output_path = save_dataset(dataset=dataset, session=session, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("参議院質問主意書一覧JSONパース完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の保存済み一覧 HTML をパースして JSON 保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
