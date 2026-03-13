"""保存済みの衆議院請願一覧 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/seigan/shugiin/list/{session}.html

出力:
    - tmp/seigan/shugiin/list/{session}.json

主な内容:
    - 新件番号
    - 件名
    - 付託委員会名
    - 請願個票 URL
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

from src.models import SeiganListDataset, SeiganListItem
from src.utils import normalize_text, parse_int

SOURCE_URL_TEMPLATE = "https://www.shugiin.go.jp/internet/itdb_seigan.nsf/html/seigan/{session}_l.htm"
INPUT_DIR = Path("tmp/seigan/shugiin/list")
OUTPUT_DIR = Path("tmp/seigan/shugiin/list")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院請願一覧 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """一覧ページ URL を返す。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def load_html(session: int, input_dir: Path = INPUT_DIR) -> str:
    """保存済みの一覧 HTML を読み込む。"""

    return (input_dir / f"{session}.html").read_text(encoding="utf-8")


def find_committee_anchor(table: Tag) -> str | None:
    """テーブル直前のアンカー名を返す。"""

    for node in table.previous_siblings:
        if isinstance(node, Tag) and node.name == "a":
            anchor_name = normalize_text(node.get("name", ""))
            if anchor_name:
                return anchor_name
    return None


def build_items(table: Tag, committee_name: str, committee_code: str | None, source_url: str) -> list[SeiganListItem]:
    """一覧テーブルから請願一覧項目を抽出する。"""

    items: list[SeiganListItem] = []
    for row in table.find_all("tr", recursive=False):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        petition_number = parse_int(cells[0].get_text(" ", strip=True) or "")
        title = normalize_text(cells[1].get_text(" ", strip=True))
        link = cells[0].find("a", href=True)
        if petition_number is None or not title or link is None:
            continue
        items.append(
            SeiganListItem(
                house="shugiin",
                petition_number=petition_number,
                title=title,
                committee_name=committee_name,
                committee_code=committee_code,
                detail_url=urljoin(source_url, link["href"]),
                is_referred=True,
            )
        )
    return items


def build_dataset(session: int, html: str) -> SeiganListDataset:
    """HTML 全体から指定回次の請願一覧データセットを構築する。"""

    source_url = build_source_url(session)
    soup = BeautifulSoup(html, "html.parser")
    items: list[SeiganListItem] = []
    for table in soup.find_all("table", class_="table"):
        caption = table.find("caption")
        if caption is None:
            continue
        caption_text = normalize_text(caption.get_text(" ", strip=True))
        if not caption_text.endswith("一覧"):
            continue
        committee_name = caption_text.removesuffix("の一覧").removesuffix("一覧").strip() or None
        if not committee_name:
            continue
        committee_code = find_committee_anchor(table)
        items.extend(build_items(table=table, committee_name=committee_name, committee_code=committee_code, source_url=source_url))

    if not items:
        raise ValueError("衆議院請願一覧データを抽出できませんでした。")

    return SeiganListDataset(
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
        house="shugiin",
        session_number=session,
        items=items,
    )


def save_dataset(dataset: SeiganListDataset, session: int, output_dir: Path = OUTPUT_DIR) -> Path:
    """パース済み一覧 JSON を保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.json"
    output_path.write_text(json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def process_session(session: int, input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の保存済み一覧 HTML をパースして JSON 保存する。"""

    logger.info("衆議院請願一覧JSONパース開始: session=%s", session)
    dataset = build_dataset(session=session, html=load_html(session=session, input_dir=input_dir))
    output_path = save_dataset(dataset=dataset, session=session, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("衆議院請願一覧JSONパース完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の保存済み一覧 HTML をパースして JSON 保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
