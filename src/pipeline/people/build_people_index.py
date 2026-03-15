"""議案・請願・質問主意書の配布用 JSON から人物インデックスを生成して `data/` に保存する。

引数:
    - なし

入力:
    - data/gian/detail/*.json
    - data/seigan/{house}/detail/*.json
    - data/shitsumon/shugiin/detail/*.json
    - data/shitsumon/sangiin/detail/*.json
    - data/kaigiroku/detail/*.json
    - tmp/kaigiroku/meeting/*.json

出力:
    - data/people/index.json
    - data/people/detail/*.json

主な内容:
    - 人物ごとの正規化キー
    - 表記ゆれ一覧
    - 人物個票への参照
    - 議案との関係
    - 請願との関係
    - 質問主意書との関係
    - 出席会議との関係
"""

from __future__ import annotations

import json
import hashlib
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    DistributedGianDetailDataset,
    DistributedKokkaiMeetingDetailDataset,
    DistributedPeopleIndexDataset,
    DistributedPersonDetailDataset,
    DistributedPersonGianRelation,
    DistributedPersonIndexItem,
    DistributedPersonRelationCounts,
    DistributedPersonMeetingRelation,
    DistributedPersonSeiganRelation,
    DistributedPersonSpeakingMeetingRelation,
    DistributedPersonShitsumonRelation,
    DistributedSeiganDetailDataset,
    KokkaiMeetingApiDataset,
    SangiinShitsumonDetailDataset,
    ShugiinShitsumonDetailDataset,
)
from src.utils import normalize_person_name, normalize_text

GIAN_DETAIL_DIR = Path("data/gian/detail")
SEIGAN_ROOT = Path("data/seigan")
SHITSUMON_ROOT = Path("data/shitsumon")
KAIGIROKU_DETAIL_DIR = Path("data/kaigiroku/detail")
KAIGIROKU_MEETING_DIR = Path("tmp/kaigiroku/meeting")
OUTPUT_PATH = Path("data/people/index.json")
DETAIL_DIR = Path("data/people/detail")
logger = logging.getLogger(__name__)


def build_person_key(name: str) -> str:
    """人物名から配布用の正規化キーを作る。"""

    return normalize_person_name(name)


def save_json(path: Path, payload: dict) -> Path:
    """JSON を UTF-8 インデント付きで保存する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_person_detail_id(person_key: str) -> str:
    """人物キーから人物個票ファイル用の固定 ID を作る。"""

    return hashlib.sha256(person_key.encode("utf-8")).hexdigest()


def relation_sort_key(
    relation: DistributedPersonGianRelation | DistributedPersonSeiganRelation | DistributedPersonShitsumonRelation | DistributedPersonMeetingRelation | DistributedPersonSpeakingMeetingRelation,
) -> tuple:
    """関係配列の並び順を安定化する。"""

    if isinstance(relation, DistributedPersonGianRelation):
        return (relation.submitted_session or 0, relation.bill_id, relation.role, relation.title)
    if isinstance(relation, DistributedPersonSeiganRelation):
        return (relation.session_number or 0, relation.house, relation.petition_id, relation.role, relation.title)
    if isinstance(relation, DistributedPersonMeetingRelation):
        return (relation.session or 0, relation.date, relation.issue_id, relation.role or "", relation.name_of_meeting)
    if isinstance(relation, DistributedPersonSpeakingMeetingRelation):
        return (relation.session or 0, relation.date, relation.issue_id, relation.speech_count, relation.name_of_meeting)
    return (relation.session_number or 0, relation.house, relation.question_id, relation.role, relation.title)


def load_seigan_details() -> list[tuple[str, DistributedSeiganDetailDataset]]:
    """衆参請願の個票を読み込む。"""

    details: list[tuple[str, DistributedSeiganDetailDataset]] = []
    for house in ("shugiin", "sangiin"):
        detail_dir = SEIGAN_ROOT / house / "detail"
        if not detail_dir.exists():
            continue
        for path in sorted(detail_dir.glob("*.json")):
            details.append((house, DistributedSeiganDetailDataset.model_validate_json(path.read_text(encoding="utf-8"))))
    return details


def load_shitsumon_details() -> list[tuple[str, ShugiinShitsumonDetailDataset | SangiinShitsumonDetailDataset]]:
    """衆参質問主意書の個票を読み込む。"""

    details: list[tuple[str, ShugiinShitsumonDetailDataset | SangiinShitsumonDetailDataset]] = []
    for house in ("shugiin", "sangiin"):
        detail_dir = SHITSUMON_ROOT / house / "detail"
        if not detail_dir.exists():
            continue
        for path in sorted(detail_dir.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            if house == "shugiin":
                details.append((house, ShugiinShitsumonDetailDataset.model_validate_json(text)))
            else:
                details.append((house, SangiinShitsumonDetailDataset.model_validate_json(text)))
    return details


def extract_session_number_from_question_id(question_id: str) -> int | None:
    """`shu-221-001` のような質問主意書 ID から回次を取り出す。"""

    parts = question_id.split("-")
    if len(parts) < 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def process() -> Path:
    """人物インデックスを生成して保存する。"""

    name_variants: dict[str, set[str]] = defaultdict(set)
    gian_relations: dict[str, list[DistributedPersonGianRelation]] = defaultdict(list)
    seigan_relations: dict[str, list[DistributedPersonSeiganRelation]] = defaultdict(list)
    shitsumon_relations: dict[str, list[DistributedPersonShitsumonRelation]] = defaultdict(list)
    meeting_relations: dict[str, list[DistributedPersonMeetingRelation]] = defaultdict(list)
    speaking_meeting_relations: dict[str, list[DistributedPersonSpeakingMeetingRelation]] = defaultdict(list)

    if GIAN_DETAIL_DIR.exists():
        for path in sorted(GIAN_DETAIL_DIR.glob("*.json")):
            detail = DistributedGianDetailDataset.model_validate_json(path.read_text(encoding="utf-8"))
            basic_info = detail.basic_info

            if basic_info.submitter:
                person_key = build_person_key(basic_info.submitter)
                if person_key:
                    name_variants[person_key].add(basic_info.submitter)
                    gian_relations[person_key].append(
                        DistributedPersonGianRelation(
                            bill_id=detail.bill_id,
                            title=detail.title,
                            role="submitter_representative",
                            submitted_session=detail.submitted_session,
                        )
                    )

            member_law_extra = basic_info.member_law_extra
            if member_law_extra is not None:
                for name in member_law_extra.submitter_list:
                    person_key = build_person_key(name)
                    if not person_key:
                        continue
                    name_variants[person_key].add(name)
                    gian_relations[person_key].append(
                        DistributedPersonGianRelation(
                            bill_id=detail.bill_id,
                            title=detail.title,
                            role="submitter",
                            submitted_session=detail.submitted_session,
                        )
                    )
                for name in member_law_extra.supporters:
                    person_key = build_person_key(name)
                    if not person_key:
                        continue
                    name_variants[person_key].add(name)
                    gian_relations[person_key].append(
                        DistributedPersonGianRelation(
                            bill_id=detail.bill_id,
                            title=detail.title,
                            role="supporter",
                            submitted_session=detail.submitted_session,
                        )
                    )

    for house, detail in load_seigan_details():
        for presenter in detail.presenters:
            person_key = build_person_key(presenter.presenter_name)
            if not person_key:
                continue
            name_variants[person_key].add(presenter.presenter_name)
            seigan_relations[person_key].append(
                DistributedPersonSeiganRelation(
                    petition_id=detail.petition_id,
                    title=detail.title,
                    role="presenter",
                    house=house,
                    session_number=detail.session_number,
                )
            )

    for house, detail in load_shitsumon_details():
        session_number = extract_session_number_from_question_id(detail.question_id)

        if detail.submitter_name:
            person_key = build_person_key(detail.submitter_name)
            if person_key:
                name_variants[person_key].add(detail.submitter_name)
                shitsumon_relations[person_key].append(
                    DistributedPersonShitsumonRelation(
                        question_id=detail.question_id,
                        title=detail.title,
                        role="submitter",
                        house=house,
                        session_number=session_number,
                    )
                )

        answer_document = detail.answer_document
        if answer_document is not None and answer_document.answerer_name:
            person_key = build_person_key(answer_document.answerer_name)
            if person_key:
                name_variants[person_key].add(answer_document.answerer_name)
                shitsumon_relations[person_key].append(
                    DistributedPersonShitsumonRelation(
                        question_id=detail.question_id,
                        title=detail.title,
                        role="answerer",
                        house=house,
                        session_number=session_number,
                    )
                )

    if KAIGIROKU_DETAIL_DIR.exists():
        for path in sorted(KAIGIROKU_DETAIL_DIR.glob("*.json")):
            detail = DistributedKokkaiMeetingDetailDataset.model_validate_json(path.read_text(encoding="utf-8"))
            for attendee in detail.attendance:
                person_key = build_person_key(attendee.name)
                if not person_key:
                    continue
                name_variants[person_key].add(attendee.name)
                meeting_relations[person_key].append(
                    DistributedPersonMeetingRelation(
                        issue_id=detail.issue_id,
                        session=detail.session,
                        name_of_house=detail.name_of_house,
                        name_of_meeting=detail.name_of_meeting,
                        issue=detail.issue,
                        date=detail.date,
                        role=attendee.role,
                        section=attendee.section,
                    )
                )

    if KAIGIROKU_MEETING_DIR.exists():
        for path in sorted(KAIGIROKU_MEETING_DIR.glob("*.json")):
            dataset = KokkaiMeetingApiDataset.model_validate_json(path.read_text(encoding="utf-8"))
            for meeting in dataset.items:
                per_person: dict[str, DistributedPersonSpeakingMeetingRelation] = {}
                for speech in meeting.speech_record:
                    if not speech.speaker or speech.speaker == "会議録情報":
                        continue
                    person_key = build_person_key(speech.speaker)
                    if not person_key:
                        continue
                    name_variants[person_key].add(speech.speaker)
                    if person_key not in per_person:
                        per_person[person_key] = DistributedPersonSpeakingMeetingRelation(
                            issue_id=meeting.issue_id,
                            session=meeting.session,
                            name_of_house=meeting.name_of_house,
                            name_of_meeting=meeting.name_of_meeting,
                            issue=meeting.issue,
                            date=meeting.date,
                            speech_count=0,
                            speaker_role=speech.speaker_role,
                            speaker_position=speech.speaker_position,
                        )
                    relation = per_person[person_key]
                    relation.speech_count += 1
                    if relation.speaker_role is None and speech.speaker_role:
                        relation.speaker_role = speech.speaker_role
                    if relation.speaker_position is None and speech.speaker_position:
                        relation.speaker_position = speech.speaker_position

                for person_key, relation in per_person.items():
                    speaking_meeting_relations[person_key].append(relation)

    built_at = datetime.now(timezone.utc)
    items: list[DistributedPersonIndexItem] = []
    for person_key in sorted(name_variants):
        unique_gian_relations = {
            (relation.bill_id, relation.role): relation for relation in gian_relations.get(person_key, [])
        }
        unique_seigan_relations = {
            (relation.petition_id, relation.house, relation.role): relation
            for relation in seigan_relations.get(person_key, [])
        }
        unique_shitsumon_relations = {
            (relation.question_id, relation.house, relation.role): relation
            for relation in shitsumon_relations.get(person_key, [])
        }
        unique_meeting_relations = {
            (relation.issue_id, relation.role, relation.section): relation
            for relation in meeting_relations.get(person_key, [])
        }
        unique_speaking_meeting_relations = {
            relation.issue_id: relation for relation in speaking_meeting_relations.get(person_key, [])
        }
        sorted_gian_relations = sorted(unique_gian_relations.values(), key=relation_sort_key)
        sorted_seigan_relations = sorted(unique_seigan_relations.values(), key=relation_sort_key)
        sorted_shitsumon_relations = sorted(unique_shitsumon_relations.values(), key=relation_sort_key)
        sorted_meeting_relations = sorted(unique_meeting_relations.values(), key=relation_sort_key)
        sorted_speaking_meeting_relations = sorted(unique_speaking_meeting_relations.values(), key=relation_sort_key)
        sorted_name_variants = sorted(name_variants[person_key])
        detail_id = build_person_detail_id(person_key)
        detail_path = DETAIL_DIR / f"{detail_id}.json"
        relation_counts = DistributedPersonRelationCounts(
            gian=len(sorted_gian_relations),
            seigan=len(sorted_seigan_relations),
            shitsumon=len(sorted_shitsumon_relations),
            meeting_attendance=len(sorted_meeting_relations),
            meeting_speech=len(sorted_speaking_meeting_relations),
        )
        detail_dataset = DistributedPersonDetailDataset(
            built_at=built_at,
            person_key=person_key,
            canonical_name=person_key,
            name_variants=sorted_name_variants,
            relation_counts=relation_counts,
            gian_relations=sorted_gian_relations,
            seigan_relations=sorted_seigan_relations,
            shitsumon_relations=sorted_shitsumon_relations,
            meeting_relations=sorted_meeting_relations,
            speaking_meeting_relations=sorted_speaking_meeting_relations,
        )
        save_json(detail_path, detail_dataset.model_dump(mode="json"))
        items.append(
            DistributedPersonIndexItem(
                person_key=person_key,
                canonical_name=person_key,
                name_variants=sorted_name_variants,
                detail_id=detail_id,
                relation_counts=relation_counts,
            )
        )

    dataset = DistributedPeopleIndexDataset(
        built_at=built_at,
        items=items,
    )
    output_path = save_json(OUTPUT_PATH, dataset.model_dump(mode="json"))
    logger.info("人物インデックス保存: path=%s items=%s", output_path, len(items))
    return output_path


def main() -> None:
    """人物インデックス生成のエントリーポイント。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    process()


if __name__ == "__main__":
    main()
