"""保存済みの衆議院質問主意書一覧 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/shitsumon/shugiin/list/{session}.html

出力:
    - tmp/shitsumon/shugiin/list/{session}.json

主な内容:
    - 質問番号
    - 質問件名
    - 提出者氏名
    - 経過状況
    - 経過情報 URL
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

from src.models import ShugiinShitsumonItem, ShugiinShitsumonListDataset
from src.utils import normalize_text, parse_int

SOURCE_URL_TEMPLATES = (
    "https://www.shugiin.go.jp/internet/itdb_shitsumon.nsf/html/shitsumon/kaiji{session:03d}_l.htm",
    "https://www.shugiin.go.jp/internet/itdb_shitsumona.nsf/html/shitsumon/kaiji{session:03d}_l.htm",
)
INPUT_DIR = Path("tmp/shitsumon/shugiin/list")
OUTPUT_DIR = Path("tmp/shitsumon/shugiin/list")
TABLE_ID = "shitsumontable"
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院質問主意書一覧HTMLをパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_preferred_source_urls(session: int) -> list[str]:
    """国会回次から候補となる一覧ページ URL を返す。"""

    preferred_order = SOURCE_URL_TEMPLATES if session > 147 else SOURCE_URL_TEMPLATES[::-1]
    return [template.format(session=session) for template in preferred_order]


def infer_source_metadata(session: int, html: str) -> tuple[str, str]:
    """HTML 内容から実際の一覧ページ URL と系列名を推定する。"""

    if session <= 147:
        return SOURCE_URL_TEMPLATES[1].format(session=session), "itdb_shitsumona"
    return SOURCE_URL_TEMPLATES[0].format(session=session), "itdb_shitsumon"


def load_html(session: int, input_dir: Path = INPUT_DIR) -> str:
    """保存済みの質問主意書一覧 HTML を読み込む。"""

    input_path = input_dir / f"{session}.html"
    return input_path.read_text(encoding="utf-8")


def find_table(soup: BeautifulSoup) -> Tag:
    """質問主意書一覧テーブルを取得する。"""

    table = soup.find("table", id=TABLE_ID)
    if table is None:
        raise ValueError("質問主意書一覧テーブルを特定できませんでした。")
    return table


def extract_link_url(cell: Tag, base_url: str) -> str | None:
    """セル内リンクを絶対 URL に変換して返す。"""

    link = cell.find("a", href=True)
    if link is None:
        return None
    return urljoin(base_url, link["href"])


def parse_item_row(row: Tag, base_url: str) -> ShugiinShitsumonItem | None:
    """一覧テーブルの1行を `ShugiinShitsumonItem` に変換する。"""

    cells = row.find_all("td", recursive=False)
    if len(cells) < 9:
        return None

    texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
    question_number = parse_int(texts[0])
    title = texts[1]
    if question_number is None or not title:
        return None

    return ShugiinShitsumonItem(
        question_number=question_number,
        title=title,
        submitter_name=texts[2] or None,
        status=texts[3] or None,
        progress_url=extract_link_url(cells[4], base_url),
        question_html_url=extract_link_url(cells[5], base_url),
        question_pdf_url=extract_link_url(cells[6], base_url),
        answer_html_url=extract_link_url(cells[7], base_url),
        answer_pdf_url=extract_link_url(cells[8], base_url),
    )


def build_dataset(session: int, html: str) -> ShugiinShitsumonListDataset:
    """HTML 全体から指定回次の質問主意書一覧データセットを構築する。"""

    soup = BeautifulSoup(html, "html.parser")
    source_url, source_series = infer_source_metadata(session=session, html=html)
    table = find_table(soup)

    items: list[ShugiinShitsumonItem] = []
    for row in table.find_all("tr"):
        item = parse_item_row(row=row, base_url=source_url)
        if item is not None:
            items.append(item)

    if not items:
        raise ValueError("質問主意書一覧データを抽出できませんでした。")

    return ShugiinShitsumonListDataset(
        source_url=source_url,
        source_series=source_series,
        fetched_at=datetime.now(timezone.utc),
        session_number=session,
        items=items,
    )


def save_dataset(
    dataset: ShugiinShitsumonListDataset,
    session: int,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """パース済み質問主意書一覧を JSON に保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.json"
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の保存済み質問主意書一覧 HTML をパースして JSON 保存する。"""

    input_path = input_dir / f"{session}.html"
    logger.info("質問主意書一覧JSONパース開始: session=%s path=%s", session, input_path)
    html = load_html(session=session, input_dir=input_dir)
    dataset = build_dataset(session=session, html=html)
    output_path = save_dataset(dataset=dataset, session=session, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("質問主意書一覧JSONパース完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の保存済み質問主意書一覧 HTML をパースして JSON 保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
