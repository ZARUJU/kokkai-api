"""衆議院サイトの議案本文情報ページと関連文書HTMLを取得して保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/gian/list/{session}.json
    - 各議案の text_url

出力:
    - tmp/gian/detail/{bill_id}/honbun/index.html
    - tmp/gian/detail/{bill_id}/honbun/documents/*.html
"""

from __future__ import annotations

import argparse
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
from src.utils import build_gian_bill_id, build_text_document_filename

INPUT_DIR = Path("tmp/gian/list")
DETAIL_ROOT = Path("tmp/gian/detail")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案本文情報を取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
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


def process_session(session: int) -> list[Path]:
    """指定回次の本文ページと関連文書 HTML を取得して保存する。"""

    gian_list = load_gian_list(session)
    logger.info("本文HTML取得開始: session=%s items=%s", session, len(gian_list.items))
    saved_paths: list[Path] = []
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

        text_html = fetch_html(str(item.text_url))
        text_path = save_text_html(bill_id=bill_id, html=text_html)
        saved_paths.append(text_path)
        logger.info("保存: bill_id=%s path=%s", bill_id, text_path)

        for document_url in extract_document_urls(text_html, str(item.text_url)):
            document_html = fetch_html(document_url)
            document_path = save_document_html(bill_id=bill_id, url=document_url, html=document_html)
            saved_paths.append(document_path)
            logger.info("保存: bill_id=%s path=%s", bill_id, document_path)

    logger.info("本文HTML取得完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の本文ページと関連文書HTMLを取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
