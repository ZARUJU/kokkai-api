"""国会会議録APIの meeting エンドポイントから指定回次の会議録 JSON を取得して保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先JSONが既にある場合は取得をスキップ

入力:
    - 国会会議録検索システム API
      https://kokkai.ndl.go.jp/api/meeting

出力:
    - tmp/kaigiroku/meeting/{session}.json

主な保存項目:
    - issueID
    - session
    - nameOfHouse
    - nameOfMeeting
    - issue
    - date
    - speechRecord
    - meetingURL
    - pdfURL
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import KokkaiMeetingApiDataset, KokkaiMeetingRecord, KokkaiSpeechRecord
from src.utils import remember_fetched_output, should_skip_fetch_output

SOURCE_URL = "https://kokkai.ndl.go.jp/api/meeting"
OUTPUT_DIR = Path("tmp/kaigiroku/meeting")
REQUEST_HEADERS = {
    "User-Agent": "kokkai-api/0.1 (+https://kokkai.ndl.go.jp/)",
}
PAGE_SIZE = 10
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の会議録JSONを国会会議録APIから取得する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="保存先JSONが既にある場合は取得をスキップする",
    )
    return parser.parse_args()


def build_query_params(session: int, start_record: int = 1) -> dict[str, str | int]:
    """API リクエスト用クエリを組み立てる。"""

    return {
        "sessionFrom": session,
        "sessionTo": session,
        "maximumRecords": PAGE_SIZE,
        "startRecord": start_record,
        "recordPacking": "json",
    }


def build_source_url(session: int) -> str:
    """保存用メタデータに含める source_url を返す。"""

    return f"{SOURCE_URL}?{urlencode(build_query_params(session=session, start_record=1))}"


def fetch_page(session: int, start_record: int) -> dict:
    """API の1ページ分を取得する。"""

    response = requests.get(
        SOURCE_URL,
        params=build_query_params(session=session, start_record=start_record),
        headers=REQUEST_HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def fetch_all_meetings(session: int) -> tuple[int, list[KokkaiMeetingRecord]]:
    """指定回次の会議録をページングしながら全件取得する。"""

    total_records = 0
    items: list[KokkaiMeetingRecord] = []
    start_record = 1

    while True:
        payload = fetch_page(session=session, start_record=start_record)
        if total_records == 0:
            total_records = int(payload.get("numberOfRecords", 0))

        meeting_records = payload.get("meetingRecord", [])
        for raw_item in meeting_records:
            try:
                speech_records = [KokkaiSpeechRecord.model_validate(raw) for raw in raw_item.get("speechRecord", [])]
                raw_item = {**raw_item, "speechRecord": speech_records}
                items.append(KokkaiMeetingRecord.model_validate(raw_item))
            except ValidationError as exc:
                logger.warning("不正な会議録レコードをスキップ: session=%s issue_id=%s error=%s", session, raw_item.get("issueID"), exc.errors())
                continue

        next_position = payload.get("nextRecordPosition")
        if not meeting_records or next_position in (None, 0):
            break
        start_record = int(next_position)

    return total_records, items


def save_dataset(dataset: KokkaiMeetingApiDataset, output_dir: Path = OUTPUT_DIR) -> Path:
    """取得済みデータセットを JSON として保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{dataset.session_number}.json"
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return remember_fetched_output(output_path)


def process_session(session: int, skip_existing: bool = False, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の会議録を取得して保存する。"""

    output_path = output_dir / f"{session}.json"
    if should_skip_fetch_output(output_path, skip_existing):
        logger.info("スキップ: 既存ファイルあり session=%s path=%s", session, output_path)
        return output_path

    logger.info("会議録API取得開始: session=%s", session)
    total_records, items = fetch_all_meetings(session=session)
    dataset = KokkaiMeetingApiDataset(
        source_url=build_source_url(session),
        fetched_at=datetime.now(timezone.utc),
        session_number=session,
        total_records=total_records,
        items=items,
    )
    output_path = save_dataset(dataset=dataset, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(items))
    logger.info("会議録API取得完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の会議録 JSON を取得して保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
