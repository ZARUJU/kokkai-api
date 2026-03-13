"""衆議院サイトの請願一覧ページを取得して raw HTML を保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先HTMLが既にある場合は取得をスキップ

入力:
    - 請願一覧ページ
      https://www.shugiin.go.jp/internet/itdb_seigan.nsf/html/seigan/{session}_l.htm

出力:
    - tmp/seigan/shugiin/list/{session}.html

主な内容:
    - 指定回次の請願一覧ページ raw HTML
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import should_skip_existing

SOURCE_URL_TEMPLATE = "https://www.shugiin.go.jp/internet/itdb_seigan.nsf/html/seigan/{session}_l.htm"
OUTPUT_DIR = Path("tmp/seigan/shugiin/list")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院請願一覧 HTML を取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument("--skip-existing", action="store_true", help="保存先HTMLが既にある場合は取得をスキップする")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """請願一覧ページ URL を返す。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def fetch_html(url: str) -> str:
    """請願一覧ページの raw HTML を取得する。"""

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def save_html(session: int, html: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """取得した HTML を保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def process_session(session: int, output_dir: Path = OUTPUT_DIR, skip_existing: bool = False) -> Path:
    """指定回次の請願一覧ページ raw HTML を取得して保存する。"""

    output_path = output_dir / f"{session}.html"
    if should_skip_existing(output_path, skip_existing):
        logger.info("スキップ: 既存ファイルあり session=%s path=%s", session, output_path)
        return output_path

    source_url = build_source_url(session)
    logger.info("衆議院請願一覧HTML取得開始: session=%s url=%s", session, source_url)
    html = fetch_html(source_url)
    output_path = save_html(session=session, html=html, output_dir=output_dir)
    logger.info("保存: session=%s path=%s", session, output_path)
    logger.info("衆議院請願一覧HTML取得完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の請願一覧ページ raw HTML を取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
