"""衆議院サイトの議案本文情報ページと関連文書HTMLを取得して保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先HTMLが既にある場合は取得をスキップ

入力:
    - tmp/gian/list/{session}.json
    - 各議案の text_url

出力:
    - tmp/gian/detail/{bill_id}/honbun/index.html
    - tmp/gian/detail/{bill_id}/honbun/documents/*.html
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import GianListDataset
from src.utils import build_gian_bill_id, build_text_document_filename, should_skip_existing

INPUT_DIR = Path("tmp/gian/list")
DETAIL_ROOT = Path("tmp/gian/detail")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
logger = logging.getLogger(__name__)
FETCHED_HTML_CACHE: dict[str, str] = {}
EXISTING_TEXT_HTML_BY_URL: dict[str, Path] | None = None
EXISTING_DOCUMENT_HTML_BY_FILENAME: dict[str, Path] | None = None


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案本文情報を取得する")
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
    """本文ページまたは関連文書ページの raw HTML を取得する。"""

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def build_existing_text_html_index(detail_root: Path = DETAIL_ROOT) -> dict[str, Path]:
    """保存済み本文JSONから source_url と raw HTML の対応表を作る。"""

    index: dict[str, Path] = {}
    for json_path in detail_root.glob("*/honbun/index.json"):
        html_path = json_path.with_name("index.html")
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


def build_existing_document_html_index(detail_root: Path = DETAIL_ROOT) -> dict[str, Path]:
    """保存済み関連文書 HTML のファイル名とパスの対応表を作る。"""

    index: dict[str, Path] = {}
    for path in detail_root.glob("*/honbun/documents/*.html"):
        if path.name not in index:
            index[path.name] = path
    return index


def extract_document_urls(html: str, base_url: str) -> list[str]:
    """本文一覧ページから関連文書 URL を抽出する。"""

    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("./"):
            continue
        urls.append(urljoin(base_url, href))
    return urls


def save_text_html(bill_id: str, html: str, detail_root: Path = DETAIL_ROOT) -> Path:
    """本文一覧ページの raw HTML を保存する。"""

    output_path = detail_root / bill_id / "honbun" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def save_document_html(bill_id: str, url: str, html: str, detail_root: Path = DETAIL_ROOT) -> Path:
    """本文ページ配下の関連文書 HTML を保存する。"""

    filename = build_text_document_filename(url)
    output_path = detail_root / bill_id / "honbun" / "documents" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def process_session(session: int, skip_existing: bool = False) -> list[Path]:
    """指定回次の本文ページと関連文書 HTML を取得して保存する。"""

    global EXISTING_DOCUMENT_HTML_BY_FILENAME
    global EXISTING_TEXT_HTML_BY_URL

    gian_list = load_gian_list(session)
    logger.info("本文HTML取得開始: session=%s items=%s", session, len(gian_list.items))
    saved_paths: list[Path] = []
    if skip_existing and EXISTING_TEXT_HTML_BY_URL is None:
        EXISTING_TEXT_HTML_BY_URL = build_existing_text_html_index()
    if skip_existing and EXISTING_DOCUMENT_HTML_BY_FILENAME is None:
        EXISTING_DOCUMENT_HTML_BY_FILENAME = build_existing_document_html_index()
    for item in gian_list.items:
        if item.text_url is None:
            logger.info("スキップ: text_urlなし title=%s", item.title)
            continue

        bill_id = build_gian_bill_id(
            category=item.category,
            submitted_session=item.submitted_session,
            bill_number=item.bill_number,
            title=item.title,
            subcategory=item.subcategory,
        )

        text_path = DETAIL_ROOT / bill_id / "honbun" / "index.html"
        if should_skip_existing(text_path, skip_existing):
            text_html = text_path.read_text(encoding="utf-8")
            logger.info("スキップ: 既存ファイルあり bill_id=%s path=%s", bill_id, text_path)
            saved_paths.append(text_path)
        else:
            text_url = str(item.text_url)
            if text_url in FETCHED_HTML_CACHE:
                text_html = FETCHED_HTML_CACHE[text_url]
                logger.info("再利用: 同一URLの取得結果を使用 bill_id=%s url=%s", bill_id, text_url)
            elif skip_existing and EXISTING_TEXT_HTML_BY_URL and text_url in EXISTING_TEXT_HTML_BY_URL:
                source_path = EXISTING_TEXT_HTML_BY_URL[text_url]
                text_html = source_path.read_text(encoding="utf-8")
                FETCHED_HTML_CACHE[text_url] = text_html
                logger.info("再利用: 保存済み本文HTMLを使用 bill_id=%s source=%s", bill_id, source_path)
            else:
                text_html = fetch_html(text_url)
                FETCHED_HTML_CACHE[text_url] = text_html
            text_path = save_text_html(bill_id=bill_id, html=text_html)
            saved_paths.append(text_path)
            logger.info("保存: bill_id=%s path=%s", bill_id, text_path)

        for document_url in extract_document_urls(text_html, str(item.text_url)):
            filename = build_text_document_filename(document_url)
            document_path = DETAIL_ROOT / bill_id / "honbun" / "documents" / filename
            if should_skip_existing(document_path, skip_existing):
                logger.info("スキップ: 既存ファイルあり bill_id=%s path=%s", bill_id, document_path)
                saved_paths.append(document_path)
                continue
            if document_url in FETCHED_HTML_CACHE:
                document_html = FETCHED_HTML_CACHE[document_url]
                logger.info("再利用: 同一URLの取得結果を使用 bill_id=%s url=%s", bill_id, document_url)
            elif (
                skip_existing
                and EXISTING_DOCUMENT_HTML_BY_FILENAME
                and filename in EXISTING_DOCUMENT_HTML_BY_FILENAME
            ):
                source_path = EXISTING_DOCUMENT_HTML_BY_FILENAME[filename]
                document_html = source_path.read_text(encoding="utf-8")
                FETCHED_HTML_CACHE[document_url] = document_html
                logger.info("再利用: 保存済み関連文書HTMLを使用 bill_id=%s source=%s", bill_id, source_path)
            else:
                document_html = fetch_html(document_url)
                FETCHED_HTML_CACHE[document_url] = document_html
            document_path = save_document_html(bill_id=bill_id, url=document_url, html=document_html)
            saved_paths.append(document_path)
            logger.info("保存: bill_id=%s path=%s", bill_id, document_path)

    logger.info("本文HTML取得完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の本文ページと関連文書HTMLを取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
