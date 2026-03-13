"""議案の配布用データを生成して `data/` に保存する。

引数:
    - sessions: 対象の国会回次。省略時は `tmp/gian/list/*.json` を全件処理する

入力:
    - tmp/gian/list/{session}.json
    - tmp/gian/detail/{bill_id}/progress/{session}.json
    - tmp/gian/detail/{bill_id}/honbun/index.html
    - tmp/gian/detail/{bill_id}/honbun/documents/*.html

出力:
    - data/gian/list/{session}.json
    - data/gian/detail/{bill_id}.json

主な内容:
    - 会期ごとの配布用議案一覧
    - 議案基本情報
    - 提出者代表名と `外X名` を反映した提出者人数
    - 会期ごとの進捗情報配列
    - 本文文書配列
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    DistributedGianBasicInfo,
    DistributedGianDetailDataset,
    DistributedGianHonbunDocument,
    DistributedGianListDataset,
    DistributedGianListItem,
    DistributedGianMeetingReference,
    DistributedGianProgressRecord,
    DistributedGianSessionStatus,
    KokkaiMeetingParsedDataset,
    GianItem,
    GianListDataset,
    GianMemberLawExtraParsed,
    GianProgressBodyParsed,
    GianProgressDataset,
)
from src.pipeline.gian.parse_gian_text import build_text_dataset
from src.utils import (
    build_gian_bill_id,
    normalize_bill_match_text,
    split_person_and_count,
    strip_name_honorific,
)

INPUT_LIST_DIR = Path("tmp/gian/list")
DETAIL_ROOT = Path("tmp/gian/detail")
KAIGIROKU_INPUT_ROOT = Path("tmp/kaigiroku/parsed")
OUTPUT_ROOT = Path("data/gian")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象回次一覧を受け取る。"""

    parser = argparse.ArgumentParser(description="議案の配布用データを生成する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は全件")
    return parser.parse_args()


def discover_sessions(input_dir: Path = INPUT_LIST_DIR) -> list[int]:
    """保存済みの議案一覧 JSON から処理対象回次を列挙する。"""

    sessions: list[int] = []
    for path in sorted(input_dir.glob("*.json")):
        try:
            sessions.append(int(path.stem))
        except ValueError:
            continue
    return sessions


def load_gian_list(session: int, input_dir: Path = INPUT_LIST_DIR) -> GianListDataset:
    """議案一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return GianListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def build_bill_id(item: GianItem) -> str:
    """議案一覧1件から bill_id を生成する。"""

    return build_gian_bill_id(
        category=item.category,
        submitted_session=item.submitted_session,
        bill_number=item.bill_number,
        title=item.title,
        subcategory=item.subcategory,
    )


def clean_html_text(html: str) -> str:
    """HTML を配布向けの単純な本文文字列へ整形する。"""

    soup = BeautifulSoup(html, "html.parser")
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def clean_person_name_list(values: list[str]) -> list[str]:
    """人名配列から敬称を除去しつつ順序を保って重複排除する。"""

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = strip_name_honorific(value)
        if not name or name in seen:
            continue
        cleaned.append(name)
        seen.add(name)
    return cleaned


def normalize_member_law_extra(member_law_extra: GianMemberLawExtraParsed | None) -> GianMemberLawExtraParsed | None:
    """衆法の提出者関連情報から敬称を除去する。"""

    if member_law_extra is None:
        return None
    return GianMemberLawExtraParsed(
        submitter_list=clean_person_name_list(member_law_extra.submitter_list),
        supporters=clean_person_name_list(member_law_extra.supporters),
    )


def build_progress_body(dataset: GianProgressDataset) -> GianProgressBodyParsed:
    """配布用の進捗差分部分だけを取り出す。"""

    return GianProgressBodyParsed(
        house_of_reps=dataset.parsed.house_of_reps,
        house_of_councillors=dataset.parsed.house_of_councillors,
        promulgation=dataset.parsed.promulgation,
    )


def load_progress_records(bill_id: str, detail_root: Path = DETAIL_ROOT) -> list[DistributedGianProgressRecord]:
    """保存済み進捗 JSON を読み込んで配布用配列へ変換する。"""

    progress_dir = detail_root / bill_id / "progress"
    records: list[DistributedGianProgressRecord] = []
    if not progress_dir.exists():
        return records

    for path in sorted(progress_dir.glob("*.json"), key=lambda p: int(p.stem)):
        dataset = GianProgressDataset.model_validate_json(path.read_text(encoding="utf-8"))
        records.append(
            DistributedGianProgressRecord(
                session_number=dataset.session_number,
                source_url=dataset.source_url,
                page_title=dataset.page_title,
                status=dataset.status,
                parsed=build_progress_body(dataset),
            )
        )
    return records


def load_honbun_documents(item: GianItem, bill_id: str, detail_root: Path = DETAIL_ROOT) -> tuple[str | None, str | None, list[DistributedGianHonbunDocument]]:
    """保存済み本文 HTML 群を読み込んで配布用配列へ変換する。"""

    honbun_index_path = detail_root / bill_id / "honbun" / "index.html"
    if item.text_url is None or not honbun_index_path.exists():
        return None, None, []

    html = honbun_index_path.read_text(encoding="utf-8")
    dataset = build_text_dataset(session=item.submitted_session or 0, item=item, html=html)
    documents: list[DistributedGianHonbunDocument] = []
    for document in dataset.parsed.documents:
        document_path = Path(document.local_path)
        if not document_path.exists():
            logger.info("本文文書が見つからないためスキップ: bill_id=%s path=%s", bill_id, document_path)
            continue
        document_html = document_path.read_text(encoding="utf-8")
        documents.append(
            DistributedGianHonbunDocument(
                label=document.label,
                title=document.title,
                document_type=document.document_type,
                note=document.note,
                source_url=document.url,
                html=document_html,
                text=clean_html_text(document_html),
            )
        )
    return str(dataset.source_url), dataset.parsed.page_title, documents


def load_progress_datasets(bill_id: str, detail_root: Path = DETAIL_ROOT) -> list[GianProgressDataset]:
    """保存済み進捗 JSON を完全なモデルとして読み込む。"""

    progress_dir = detail_root / bill_id / "progress"
    if not progress_dir.exists():
        return []
    return [
        GianProgressDataset.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(progress_dir.glob("*.json"), key=lambda p: int(p.stem))
    ]


def build_basic_info(item: GianItem, progress_datasets: list[GianProgressDataset]) -> DistributedGianBasicInfo:
    """議案個票の基本情報を組み立てる。"""

    for dataset in progress_datasets:
        parsed = dataset.parsed
        if (
            parsed.bill_type
            or parsed.bill_title
            or parsed.submitter
            or parsed.submitter_group
            or parsed.member_law_extra is not None
        ):
            submitter_name, submitter_count, submitter_has_more = split_person_and_count(parsed.submitter or "")
            return DistributedGianBasicInfo(
                bill_type=parsed.bill_type,
                bill_title=parsed.bill_title or item.title,
                submitter=submitter_name or None,
                submitter_count=submitter_count,
                submitter_has_more=submitter_has_more,
                submitter_group=parsed.submitter_group,
                member_law_extra=normalize_member_law_extra(parsed.member_law_extra),
            )

    return DistributedGianBasicInfo(
        bill_type=item.category,
        bill_title=item.title,
    )


def save_json(path: Path, payload: dict) -> Path:
    """JSON を UTF-8 インデント付きで保存する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_bill_title_index(
    bill_occurrences: dict[str, list[tuple[int, GianItem]]],
) -> dict[str, tuple[str, str]]:
    """議案個票候補からタイトル照合用インデックスを作る。"""

    index: dict[str, tuple[str, str]] = {}
    for bill_id, occurrences in bill_occurrences.items():
        canonical_item = sorted(occurrences, key=lambda pair: pair[0])[-1][1]
        normalized = normalize_bill_match_text(canonical_item.title)
        if normalized and normalized not in index:
            index[normalized] = (bill_id, canonical_item.title)
    return index


def link_bill_id_from_agenda_text(text: str, bill_index: dict[str, tuple[str, str]]) -> tuple[str | None, str | None]:
    """会議録案件文から bill_id と議案名を推定する。"""

    normalized = normalize_bill_match_text(text)
    if not normalized:
        return None, None
    if normalized in bill_index:
        return bill_index[normalized]
    for candidate, value in bill_index.items():
        if candidate and (normalized.startswith(candidate) or candidate.startswith(normalized)):
            return value
    return None, None


def load_bill_meeting_references(
    sessions: list[int],
    bill_index: dict[str, tuple[str, str]],
    kaigiroku_input_root: Path = KAIGIROKU_INPUT_ROOT,
) -> dict[str, list[DistributedGianMeetingReference]]:
    """会議録 parsed JSON から議案ごとの会議参照一覧を作る。"""

    references: dict[str, list[DistributedGianMeetingReference]] = defaultdict(list)
    for session in sessions:
        path = kaigiroku_input_root / f"{session}.json"
        if not path.exists():
            continue
        dataset = KokkaiMeetingParsedDataset.model_validate_json(path.read_text(encoding="utf-8"))
        for item in dataset.items:
            for agenda_text in item.parsed.agenda_items:
                bill_id, _ = link_bill_id_from_agenda_text(agenda_text, bill_index)
                if bill_id is None:
                    continue
                references[bill_id].append(
                    DistributedGianMeetingReference(
                        issue_id=item.issue_id,
                        session=item.session,
                        name_of_house=item.name_of_house,
                        name_of_meeting=item.name_of_meeting,
                        issue=item.issue,
                        date=item.date,
                        meeting_url=item.meeting_url,
                        pdf_url=item.pdf_url,
                        agenda_text=agenda_text,
                    )
                )

    for bill_id, items in list(references.items()):
        unique: dict[str, DistributedGianMeetingReference] = {}
        for item in items:
            unique[item.issue_id] = item
        references[bill_id] = sorted(unique.values(), key=lambda entry: (entry.date, entry.issue_id))
    return references


def build_list_dataset(session: int, gian_list: GianListDataset, detail_root: Path = DETAIL_ROOT) -> DistributedGianListDataset:
    """会期別の配布用議案一覧を構築する。"""

    items: list[DistributedGianListItem] = []
    for item in gian_list.items:
        bill_id = build_bill_id(item)
        items.append(
            DistributedGianListItem(
                bill_id=bill_id,
                category=item.category,
                subcategory=item.subcategory,
                submitted_session=item.submitted_session,
                bill_number=item.bill_number,
                title=item.title,
                status=item.status,
                progress_url=item.progress_url,
                text_url=item.text_url,
                has_progress=(detail_root / bill_id / "progress" / f"{session}.json").exists(),
                has_honbun=(detail_root / bill_id / "honbun" / "index.html").exists(),
            )
        )

    return DistributedGianListDataset(
        session_number=session,
        built_at=datetime.now(timezone.utc),
        items=items,
    )


def build_detail_dataset(
    bill_id: str,
    occurrences: list[tuple[int, GianItem]],
    meeting_references: list[DistributedGianMeetingReference] | None = None,
    detail_root: Path = DETAIL_ROOT,
) -> DistributedGianDetailDataset:
    """議案単位の配布用個票を構築する。"""

    ordered_occurrences = sorted(occurrences, key=lambda pair: pair[0])
    canonical_item = ordered_occurrences[-1][1]
    honbun_item = next(
        (
            item
            for _, item in reversed(ordered_occurrences)
            if item.text_url is not None and (detail_root / bill_id / "honbun" / "index.html").exists()
        ),
        canonical_item,
    )
    listed_sessions = [session for session, _ in ordered_occurrences]
    session_statuses = [
        DistributedGianSessionStatus(session_number=session, status=item.status)
        for session, item in ordered_occurrences
    ]
    progress_datasets = load_progress_datasets(bill_id=bill_id, detail_root=detail_root)
    progress_records = load_progress_records(bill_id=bill_id, detail_root=detail_root)
    honbun_source_url, honbun_page_title, honbun_documents = load_honbun_documents(
        item=honbun_item,
        bill_id=bill_id,
        detail_root=detail_root,
    )

    return DistributedGianDetailDataset(
        bill_id=bill_id,
        category=canonical_item.category,
        subcategory=canonical_item.subcategory,
        submitted_session=canonical_item.submitted_session,
        bill_number=canonical_item.bill_number,
        title=canonical_item.title,
        listed_sessions=listed_sessions,
        session_statuses=session_statuses,
        basic_info=build_basic_info(canonical_item, progress_datasets),
        progress=progress_records,
        meetings=meeting_references or [],
        honbun_source_url=honbun_source_url,
        honbun_page_title=honbun_page_title,
        honbun_documents=honbun_documents,
        built_at=datetime.now(timezone.utc),
    )


def process_sessions(sessions: list[int], input_dir: Path = INPUT_LIST_DIR, output_root: Path = OUTPUT_ROOT) -> None:
    """指定回次群から配布用データ一式を生成する。"""

    bill_occurrences: dict[str, list[tuple[int, GianItem]]] = defaultdict(list)
    logger.info("配布データ生成開始: sessions=%s", sessions)

    for session in sessions:
        gian_list = load_gian_list(session, input_dir=input_dir)
        list_dataset = build_list_dataset(session=session, gian_list=gian_list)
        list_path = output_root / "list" / f"{session}.json"
        save_json(list_path, list_dataset.model_dump(mode="json"))
        logger.info("一覧保存: session=%s path=%s items=%s", session, list_path, len(list_dataset.items))

        for item in gian_list.items:
            bill_occurrences[build_bill_id(item)].append((session, item))

    bill_index = build_bill_title_index(bill_occurrences)
    meeting_references = load_bill_meeting_references(sessions=sessions, bill_index=bill_index)

    for bill_id in sorted(bill_occurrences):
        detail_dataset = build_detail_dataset(
            bill_id=bill_id,
            occurrences=bill_occurrences[bill_id],
            meeting_references=meeting_references.get(bill_id, []),
        )
        detail_path = output_root / "detail" / f"{bill_id}.json"
        save_json(detail_path, detail_dataset.model_dump(mode="json"))
        logger.info("個票保存: bill_id=%s path=%s", bill_id, detail_path)

    logger.info("配布データ生成完了: sessions=%s bills=%s", sessions, len(bill_occurrences))


def main() -> None:
    """配布用の議案一覧・議案個票データを生成する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    sessions = args.sessions or discover_sessions()
    process_sessions(sorted(set(sessions)))


if __name__ == "__main__":
    main()
