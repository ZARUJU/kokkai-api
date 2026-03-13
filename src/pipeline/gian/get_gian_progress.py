"""衆議院サイトの議案進捗情報ページを取得して raw HTML を保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先HTMLが既にある場合は取得をスキップ

入力:
    - tmp/gian/list/{session}.json
    - 各議案の progress_url

出力:
    - tmp/gian/detail/{bill_id}/progress/{session}.html

主な内容:
    - bill_id
    - progress_url に対応する raw HTML
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import GianListDataset
from src.utils import build_gian_bill_id, remember_fetched_output, should_skip_fetch_output

INPUT_DIR = Path("tmp/gian/list")
OUTPUT_ROOT = Path("tmp/gian/detail")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
logger = logging.getLogger(__name__)
FETCHED_HTML_CACHE: dict[str, str] = {}
EXISTING_PROGRESS_HTML_BY_URL: dict[str, Path] | None = None


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案進捗情報を取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="保存先HTMLが既にある場合は取得をスキップする",
    )
    return parser.parse_args()


def load_gian_list(session: int, input_dir: Path = INPUT_DIR) -> GianListDataset:
    """議案一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return GianListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def fetch_html(url: str) -> str:
    """進捗ページの raw HTML を取得する。"""

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def build_existing_progress_html_index(output_root: Path = OUTPUT_ROOT) -> dict[str, Path]:
    """保存済み進捗JSONから source_url と raw HTML の対応表を作る。"""

    index: dict[str, Path] = {}
    for json_path in output_root.glob("*/progress/*.json"):
        html_path = json_path.with_suffix(".html")
        if not html_path.exists():
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        source_url = payload.get("source_url")
        if isinstance(source_url, str) and source_url not in index:
            index[source_url] = html_path
    return index


def save_progress_html(
    bill_id: str,
    session: int,
    html: str,
    output_root: Path = OUTPUT_ROOT,
) -> Path:
    """進捗ページの raw HTML を議案単位に保存する。"""

    output_path = output_root / bill_id / "progress" / f"{session}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return remember_fetched_output(output_path)


def process_session(session: int, skip_existing: bool = False) -> list[Path]:
    """指定回次の進捗ページ raw HTML を一括取得して保存する。"""

    global EXISTING_PROGRESS_HTML_BY_URL

    gian_list = load_gian_list(session)
    logger.info("進捗HTML取得開始: session=%s items=%s", session, len(gian_list.items))
    saved_paths: list[Path] = []
    if skip_existing and EXISTING_PROGRESS_HTML_BY_URL is None:
        EXISTING_PROGRESS_HTML_BY_URL = build_existing_progress_html_index()
    for item in gian_list.items:
        if item.progress_url is None:
            logger.info("スキップ: progress_urlなし title=%s", item.title)
            continue
        bill_id = build_gian_bill_id(
            category=item.category,
            submitted_session=item.submitted_session,
            bill_number=item.bill_number,
            title=item.title,
            subcategory=item.subcategory,
        )
        output_path = OUTPUT_ROOT / bill_id / "progress" / f"{session}.html"
        if should_skip_fetch_output(output_path, skip_existing):
            logger.info("スキップ: 既存ファイルあり bill_id=%s path=%s", bill_id, output_path)
            saved_paths.append(output_path)
            continue
        progress_url = str(item.progress_url)
        if progress_url in FETCHED_HTML_CACHE:
            html = FETCHED_HTML_CACHE[progress_url]
            logger.info("再利用: 同一URLの取得結果を使用 bill_id=%s url=%s", bill_id, progress_url)
        elif skip_existing and EXISTING_PROGRESS_HTML_BY_URL and progress_url in EXISTING_PROGRESS_HTML_BY_URL:
            source_path = EXISTING_PROGRESS_HTML_BY_URL[progress_url]
            html = source_path.read_text(encoding="utf-8")
            FETCHED_HTML_CACHE[progress_url] = html
            logger.info("再利用: 保存済み進捗HTMLを使用 bill_id=%s source=%s", bill_id, source_path)
        else:
            html = fetch_html(progress_url)
            FETCHED_HTML_CACHE[progress_url] = html
        output_path = save_progress_html(bill_id=bill_id, session=session, html=html)
        logger.info("保存: bill_id=%s path=%s", bill_id, output_path)
        saved_paths.append(output_path)
    logger.info("進捗HTML取得完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の進捗ページ raw HTML を取得して保存する。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
