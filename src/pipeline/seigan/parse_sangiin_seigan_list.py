"""保存済みの参議院請願一覧 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/seigan/sangiin/list/{session}.html

出力:
    - tmp/seigan/sangiin/list/{session}.json

主な内容:
    - 新件番号
    - 件名
    - 委員会名
    - 請願要旨 URL
    - 同趣旨一覧 URL
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

SOURCE_URL_TEMPLATE = "https://www.sangiin.go.jp/japanese/joho1/kousei/seigan/{session}/seigan.htm"
INPUT_DIR = Path("tmp/seigan/sangiin/list")
OUTPUT_DIR = Path("tmp/seigan/sangiin/list")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の参議院請願一覧 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """一覧ページ URL を返す。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def load_html(session: int, input_dir: Path = INPUT_DIR) -> str:
    """保存済み HTML を読み込む。"""

    return (input_dir / f"{session}.html").read_text(encoding="utf-8")


def parse_table_items(table: Tag, committee_name: str, committee_code: str | None, base_url: str) -> list[SeiganListItem]:
    """一覧テーブルを請願一覧項目配列へ変換する。"""

    items: list[SeiganListItem] = []
    for row in table.find_all("tr", recursive=False):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        petition_number = parse_int(cells[0].get_text(" ", strip=True) or "")
        title = normalize_text(cells[1].get_text(" ", strip=True))
        if petition_number is None or not title:
            continue
        detail_link = cells[1].find("a", href=True)
        similar_link = cells[2].find("a", href=True)
        items.append(
            SeiganListItem(
                house="sangiin",
                petition_number=petition_number,
                title=title,
                committee_name=committee_name,
                committee_code=committee_code,
                detail_url=urljoin(base_url, detail_link["href"]) if detail_link is not None else None,
                similar_petitions_url=urljoin(base_url, similar_link["href"]) if similar_link is not None else None,
                is_referred=committee_name != "付託に至らなかった請願",
            )
        )
    return items


def build_dataset(session: int, html: str) -> SeiganListDataset:
    """HTML 全体から指定回次の請願一覧データセットを構築する。"""

    source_url = build_source_url(session)
    soup = BeautifulSoup(html, "html.parser")
    items: list[SeiganListItem] = []
    for header in soup.find_all("h4"):
        committee_name = normalize_text(header.get_text(" ", strip=True))
        committee_name = committee_name.removeprefix(f"第{session}回国会").strip()
        if not committee_name.endswith("請願") and "委員会" not in committee_name and "審査会" not in committee_name:
            continue
        anchor = header.find_previous("a")
        committee_code = normalize_text(anchor.get("name", "")) if anchor is not None else None
        table = header.find_next("table", class_="list_c")
        if table is None:
            continue
        items.extend(parse_table_items(table=table, committee_name=committee_name, committee_code=committee_code, base_url=source_url))

    if not items:
        raise ValueError("参議院請願一覧データを抽出できませんでした。")

    return SeiganListDataset(
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
        house="sangiin",
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

    logger.info("参議院請願一覧JSONパース開始: session=%s", session)
    dataset = build_dataset(session=session, html=load_html(session=session, input_dir=input_dir))
    output_path = save_dataset(dataset=dataset, session=session, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("参議院請願一覧JSONパース完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の保存済み一覧 HTML をパースして JSON 保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
