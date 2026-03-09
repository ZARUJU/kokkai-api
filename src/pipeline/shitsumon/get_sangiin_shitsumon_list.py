"""参議院サイトの質問主意書一覧ページを取得して raw HTML を保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - 質問主意書一覧ページ
      https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm

出力:
    - tmp/shitsumon/sangiin/list/{session}.html

主な内容:
    - 指定回次の質問主意書一覧ページ raw HTML
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

SOURCE_URL_TEMPLATE = "https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm"
OUTPUT_DIR = Path("tmp/shitsumon/sangiin/list")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.sangiin.go.jp/)",
}
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の参議院質問主意書一覧HTMLを取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def build_source_url(session: int) -> str:
    """国会回次から一覧ページ URL を生成する。"""

    return SOURCE_URL_TEMPLATE.format(session=session)


def fetch_html(url: str) -> str:
    """質問主意書一覧ページの raw HTML を取得する。"""

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def save_html(session: int, html: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """取得した質問主意書一覧ページ HTML を保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def process_session(session: int, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の質問主意書一覧ページ raw HTML を取得して保存する。"""

    source_url = build_source_url(session)
    logger.info("参議院質問主意書一覧HTML取得開始: session=%s url=%s", session, source_url)
    html = fetch_html(source_url)
    output_path = save_html(session=session, html=html, output_dir=output_dir)
    logger.info("保存: session=%s path=%s", session, output_path)
    logger.info("参議院質問主意書一覧HTML取得完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の質問主意書一覧ページ raw HTML を取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
