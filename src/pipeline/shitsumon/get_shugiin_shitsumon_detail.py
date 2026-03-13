"""衆議院サイトの質問主意書個別ページを取得して raw HTML を保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先HTMLが既にある場合は取得をスキップ

入力:
    - tmp/shitsumon/shugiin/list/{session}.json
    - 各質問主意書の progress_url
    - 各質問主意書の question_html_url
    - 各質問主意書の answer_html_url

出力:
    - tmp/shitsumon/shugiin/detail/{question_id}/progress.html
    - tmp/shitsumon/shugiin/detail/{question_id}/question.html
    - tmp/shitsumon/shugiin/detail/{question_id}/answer.html

主な内容:
    - question_id
    - 経過ページ raw HTML
    - 質問本文ページ raw HTML
    - 答弁本文ページ raw HTML
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

from src.models import ShugiinShitsumonListDataset
from src.utils import (
    build_shugiin_shitsumon_id,
    decode_html_bytes,
    has_complete_answer_received_shitsumon_detail,
    polite_get,
    remember_fetched_output,
    should_skip_fetch_output,
)

INPUT_DIR = Path("tmp/shitsumon/shugiin/list")
DETAIL_ROOT = Path("tmp/shitsumon/shugiin/detail")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
COMPLETE_DETAIL_HTML_NAMES = ("progress.html", "question.html", "answer.html")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院質問主意書個別ページを取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="保存先HTMLが既にある場合は取得をスキップする",
    )
    return parser.parse_args()


def load_shitsumon_list(session: int, input_dir: Path = INPUT_DIR) -> ShugiinShitsumonListDataset:
    """質問主意書一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return ShugiinShitsumonListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def fetch_html(url: str) -> str:
    """個別ページの raw HTML を取得する。"""

    response = polite_get(url, headers=REQUEST_HEADERS, timeout=60)
    response.raise_for_status()
    return decode_html_bytes(
        content=response.content,
        content_type=response.headers.get("Content-Type"),
        fallback_encoding=response.apparent_encoding or response.encoding,
    )


def save_detail_html(
    question_id: str,
    kind: str,
    html: str,
    detail_root: Path = DETAIL_ROOT,
) -> Path:
    """取得した個別ページ HTML を質問主意書単位に保存する。"""

    output_path = detail_root / question_id / f"{kind}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return remember_fetched_output(output_path)


def process_session(session: int, skip_existing: bool = False) -> list[Path]:
    """指定回次の個別ページ raw HTML を一括取得して保存する。"""

    shitsumon_list = load_shitsumon_list(session)
    logger.info("質問主意書個別HTML取得開始: session=%s items=%s", session, len(shitsumon_list.items))
    saved_paths: list[Path] = []

    for item in shitsumon_list.items:
        question_id = build_shugiin_shitsumon_id(
            session_number=session,
            question_number=item.question_number,
        )
        detail_dir = DETAIL_ROOT / question_id
        targets = (
            ("progress", item.progress_url),
            ("question", item.question_html_url),
            ("answer", item.answer_html_url),
        )
        if has_complete_answer_received_shitsumon_detail(detail_dir, COMPLETE_DETAIL_HTML_NAMES):
            logger.info("スキップ: 既存個票が答弁受理済みかつ必要HTMLあり question_id=%s", question_id)
            for kind, _ in targets:
                output_path = detail_dir / f"{kind}.html"
                if output_path.exists():
                    saved_paths.append(output_path)
            continue
        for kind, url in targets:
            if url is None:
                logger.info("スキップ: urlなし question_id=%s kind=%s", question_id, kind)
                continue
            output_path = detail_dir / f"{kind}.html"
            if should_skip_fetch_output(output_path, skip_existing):
                logger.info("スキップ: 既存ファイルあり question_id=%s kind=%s path=%s", question_id, kind, output_path)
                saved_paths.append(output_path)
                continue
            try:
                html = fetch_html(str(url))
            except requests.RequestException as exc:
                logger.warning("取得失敗: question_id=%s kind=%s url=%s error=%s", question_id, kind, url, exc)
                continue
            output_path = save_detail_html(question_id=question_id, kind=kind, html=html)
            logger.info("保存: question_id=%s kind=%s path=%s", question_id, kind, output_path)
            saved_paths.append(output_path)

    logger.info("質問主意書個別HTML取得完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の個別ページ raw HTML を取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
