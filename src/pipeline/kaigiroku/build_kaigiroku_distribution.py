"""会議録メタデータの配布用データを生成して `data/` に保存する。

引数:
    - sessions: 対象の国会回次。省略時は保存済み parsed JSON を全件処理する

入力:
    - tmp/kaigiroku/parsed/{session}.json
    - data/gian/list/{session}.json
    - data/seigan/{house}/list/{session}.json

出力:
    - data/kaigiroku/list/{session}.json
    - data/kaigiroku/detail/{issue_id}.json

主な内容:
    - 会議録一覧
    - 開会・散会時刻
    - 出席者
    - 本日の会議に付した案件
    - 本日の案件と議案・請願 ID の紐付け
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    DistributedGianListDataset,
    DistributedKokkaiAgendaItem,
    DistributedKokkaiMeetingDetailDataset,
    DistributedKokkaiMeetingListDataset,
    DistributedKokkaiMeetingListItem,
    DistributedSeiganListDataset,
    KokkaiMeetingParsedDataset,
)
from src.utils import normalize_bill_match_text, normalize_petition_match_text

INPUT_ROOT = Path("tmp/kaigiroku/parsed")
GIAN_ROOT = Path("data/gian/list")
SEIGAN_ROOT = Path("data/seigan")
OUTPUT_ROOT = Path("data/kaigiroku")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="会議録の配布用データを生成する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は全件")
    return parser.parse_args()


def discover_sessions(input_root: Path = INPUT_ROOT) -> list[int]:
    """保存済み parsed JSON から処理対象回次を列挙する。"""

    sessions: list[int] = []
    for path in sorted(input_root.glob("*.json")):
        try:
            sessions.append(int(path.stem))
        except ValueError:
            continue
    return sessions


def save_json(path: Path, payload: dict) -> Path:
    """JSON を UTF-8 インデント付きで保存する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_bill_index(session: int, gian_root: Path = GIAN_ROOT) -> dict[str, tuple[str, str]]:
    """指定回次の議案一覧からタイトル照合用インデックスを作る。"""

    path = gian_root / f"{session}.json"
    if not path.exists():
        return {}

    dataset = DistributedGianListDataset.model_validate_json(path.read_text(encoding="utf-8"))
    index: dict[str, tuple[str, str]] = {}
    for item in dataset.items:
        normalized = normalize_bill_match_text(item.title)
        if normalized and normalized not in index:
            index[normalized] = (item.bill_id, item.title)
    return index


def load_petition_index(session: int, house: str, seigan_root: Path = SEIGAN_ROOT) -> dict[str, tuple[str, str]]:
    """指定回次・指定院の請願一覧からタイトル照合用インデックスを作る。"""

    path = seigan_root / house / "list" / f"{session}.json"
    if not path.exists():
        return {}

    dataset = DistributedSeiganListDataset.model_validate_json(path.read_text(encoding="utf-8"))
    index: dict[str, tuple[str, str]] = {}
    for item in dataset.items:
        petition_id = f"{'shu' if house == 'shugiin' else 'san'}-seigan-{session}-{item.petition_number:04d}"
        normalized = normalize_petition_match_text(item.title)
        if normalized and normalized not in index:
            index[normalized] = (petition_id, item.title)
    return index


def link_agenda_item(
    text: str,
    bill_index: dict[str, tuple[str, str]],
    petition_index: dict[str, tuple[str, str]],
) -> DistributedKokkaiAgendaItem:
    """本日の案件1件を議案または請願一覧と照合する。"""

    bill_id = None
    bill_title = None
    petition_id = None
    petition_title = None
    item_type = None

    normalized_bill = normalize_bill_match_text(text)
    normalized_petition = normalize_petition_match_text(text)

    if normalized_bill in bill_index:
        bill_id, bill_title = bill_index[normalized_bill]
        item_type = "bill"
    elif normalized_petition in petition_index:
        petition_id, petition_title = petition_index[normalized_petition]
        item_type = "petition"
    else:
        if normalized_bill:
            for candidate, value in bill_index.items():
                if candidate and (normalized_bill.startswith(candidate) or candidate.startswith(normalized_bill)):
                    bill_id, bill_title = value
                    item_type = "bill"
                    break
        if item_type is None:
            if normalized_petition:
                for candidate, value in petition_index.items():
                    if candidate and (normalized_petition.startswith(candidate) or candidate.startswith(normalized_petition)):
                        petition_id, petition_title = value
                        item_type = "petition"
                        break

    return DistributedKokkaiAgendaItem(
        text=text,
        item_type=item_type,
        bill_id=bill_id,
        bill_title=bill_title,
        petition_id=petition_id,
        petition_title=petition_title,
    )


def process_sessions(sessions: list[int], input_root: Path = INPUT_ROOT, output_root: Path = OUTPUT_ROOT) -> None:
    """対象回次の配布用一覧・個票を保存する。"""

    for session in sessions:
        input_path = input_root / f"{session}.json"
        if not input_path.exists():
            logger.info("parsed JSON が見つからないためスキップ: session=%s", session)
            continue

        parsed_dataset = KokkaiMeetingParsedDataset.model_validate_json(input_path.read_text(encoding="utf-8"))
        bill_index = load_bill_index(session=session)
        petition_indexes = {
            "衆議院": load_petition_index(session=session, house="shugiin"),
            "参議院": load_petition_index(session=session, house="sangiin"),
        }
        built_at = datetime.now(timezone.utc)

        list_items: list[DistributedKokkaiMeetingListItem] = []
        for item in parsed_dataset.items:
            distributed_agenda_items = [
                link_agenda_item(
                    text=text,
                    bill_index=bill_index,
                    petition_index=petition_indexes.get(item.name_of_house, {}),
                )
                for text in item.parsed.agenda_items
            ]
            detail = DistributedKokkaiMeetingDetailDataset(
                issue_id=item.issue_id,
                session=item.session,
                name_of_house=item.name_of_house,
                name_of_meeting=item.name_of_meeting,
                issue=item.issue,
                date=item.date,
                meeting_url=item.meeting_url,
                pdf_url=item.pdf_url,
                opening_line=item.parsed.opening_line,
                opening_time=item.parsed.opening_time,
                closing_line=item.parsed.closing_line,
                closing_time=item.parsed.closing_time,
                speech_count=item.speech_count,
                attendance=item.parsed.attendance,
                agenda_items=distributed_agenda_items,
                built_at=built_at,
            )
            save_json(output_root / "detail" / f"{item.issue_id}.json", detail.model_dump(mode="json", exclude_none=True))

            list_items.append(
                DistributedKokkaiMeetingListItem(
                    issue_id=item.issue_id,
                    session=item.session,
                    name_of_house=item.name_of_house,
                    name_of_meeting=item.name_of_meeting,
                    issue=item.issue,
                    date=item.date,
                    meeting_url=item.meeting_url,
                    pdf_url=item.pdf_url,
                    opening_time=item.parsed.opening_time,
                    closing_time=item.parsed.closing_time,
                    speech_count=item.speech_count,
                    matched_item_count=sum(
                        1
                        for agenda in distributed_agenda_items
                        if agenda.bill_id is not None or agenda.petition_id is not None
                    ),
                )
            )

        list_dataset = DistributedKokkaiMeetingListDataset(
            session_number=session,
            built_at=built_at,
            items=list_items,
        )
        save_json(output_root / "list" / f"{session}.json", list_dataset.model_dump(mode="json", exclude_none=True))
        logger.info("会議録配布データ生成完了: session=%s items=%s", session, len(list_items))


def main() -> None:
    """会議録の配布用データを生成する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    sessions = sorted(set(args.sessions or discover_sessions()))
    if not sessions:
        logger.info("対象回次が見つからないためスキップ")
        return
    process_sessions(sessions)


if __name__ == "__main__":
    main()
