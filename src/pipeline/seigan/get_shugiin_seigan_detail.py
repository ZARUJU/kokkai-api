"""衆議院サイトの請願個別ページを取得して raw HTML を保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先HTMLが既にある場合は取得をスキップ

入力:
    - tmp/seigan/shugiin/list/{session}.json
    - 各請願の detail_url

出力:
    - tmp/seigan/shugiin/detail/{petition_id}/detail.html

主な内容:
    - 請願個票 raw HTML
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

from src.models import SeiganListDataset
from src.utils import build_shugiin_seigan_id, should_skip_existing

INPUT_DIR = Path("tmp/seigan/shugiin/list")
DETAIL_ROOT = Path("tmp/seigan/shugiin/detail")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://www.shugiin.go.jp/)",
}
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院請願個別ページを取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument("--skip-existing", action="store_true", help="保存先HTMLが既にある場合は取得をスキップする")
    return parser.parse_args()


def load_list(session: int, input_dir: Path = INPUT_DIR) -> SeiganListDataset:
    """請願一覧 JSON を読み込む。"""

    return SeiganListDataset.model_validate_json((input_dir / f"{session}.json").read_text(encoding="utf-8"))


def fetch_html(url: str) -> str:
    """個別ページの raw HTML を取得する。"""

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def save_html(petition_id: str, html: str, detail_root: Path = DETAIL_ROOT) -> Path:
    """取得した HTML を保存する。"""

    output_path = detail_root / petition_id / "detail.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def process_session(session: int, skip_existing: bool = False) -> list[Path]:
    """指定回次の請願個別ページ raw HTML を保存する。"""

    dataset = load_list(session)
    saved_paths: list[Path] = []
    logger.info("衆議院請願個別HTML取得開始: session=%s items=%s", session, len(dataset.items))
    for item in dataset.items:
        if item.detail_url is None:
            continue
        petition_id = build_shugiin_seigan_id(session_number=session, petition_number=item.petition_number)
        output_path = DETAIL_ROOT / petition_id / "detail.html"
        if should_skip_existing(output_path, skip_existing):
            logger.info("スキップ: 既存ファイルあり petition_id=%s path=%s", petition_id, output_path)
            saved_paths.append(output_path)
            continue
        html = fetch_html(str(item.detail_url))
        saved_paths.append(save_html(petition_id=petition_id, html=html))
    logger.info("衆議院請願個別HTML取得完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の請願個別ページ raw HTML を保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
