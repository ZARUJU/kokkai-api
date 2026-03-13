"""保存済みの会議録 API JSON を読み込み、会議冒頭・終盤の記述からメタデータを抽出して保存する。

引数:
    - session: 取得対象の国会回次
    - --skip-existing: 保存先JSONが既にある場合はパースをスキップ

入力:
    - tmp/kaigiroku/meeting/{session}.json

出力:
    - tmp/kaigiroku/parsed/{session}.json

主な抽出項目:
    - 開会日・開会時刻・散会時刻
    - 出席者
    - 委員の異動
    - 付託案件
    - 本日の会議に付した案件
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    KokkaiAttendanceEntry,
    KokkaiMeetingApiDataset,
    KokkaiMeetingMetadataParsed,
    KokkaiMeetingParsedDataset,
    KokkaiMeetingParsedItem,
    KokkaiMembershipChange,
)
from src.utils import (
    normalize_person_name,
    normalize_text,
    parse_japanese_date,
    parse_japanese_date_with_default_year,
    parse_japanese_time,
    should_skip_existing,
)

INPUT_DIR = Path("tmp/kaigiroku/meeting")
OUTPUT_DIR = Path("tmp/kaigiroku/parsed")
logger = logging.getLogger(__name__)

SEPARATOR_CHARS = {"―", "－", "-", "─", "—", "◇", "…", "･", "・", " ", "\t"}
ROLE_HEADER_LABELS = {"理事", "委員", "委員長", "事務局側", "政府参考人", "政府特別補佐人", "大臣政務官"}
ATTENDANCE_SECTION_LABELS = {
    "国務大臣",
    "副大臣",
    "大臣政務官",
    "事務局側",
    "参考人",
    "政府参考人",
    "政府特別補佐人",
}
NAME_TOKEN_PATTERN = re.compile(r"^[ぁ-んァ-ヶー一-龥々ゝゞヵヶA-Za-z・]+$")
ROLE_TOKEN_SUFFIXES = (
    "大臣",
    "副大臣",
    "大臣政務官",
    "政務官",
    "審議官",
    "総括審議官",
    "参事官",
    "統括官",
    "次長",
    "局長",
    "部長",
    "室長",
    "課長",
    "所長",
    "長官",
    "委員長",
    "理事長",
    "理事",
    "会長",
    "主査",
    "室",
    "長",
    "官",
    "員",
    "教授",
    "准教授",
    "名誉教授",
    "研究員",
    "研究官",
    "専門員",
    "室長",
    "代表",
    "副総裁候補者",
    "フェロー",
    "ジャーナリスト",
    "リサーチャー",
    "ディレクター",
    "アドバイザー",
)
AGENDA_ITEM_END_MARKERS = (
    "法律案",
    "予算",
    "決算",
    "条約",
    "承認",
    "請求",
    "同意",
    "請願",
    "の件",
    "関する件",
    "互選",
    "選任",
    "選挙",
    "辞職",
    "挨拶",
    "祝辞",
    "謝辞",
    "報告聴取",
)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の会議録JSONからメタデータを抽出する")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="保存先JSONが既にある場合はパースをスキップする",
    )
    return parser.parse_args()


def load_dataset(session: int, input_dir: Path = INPUT_DIR) -> KokkaiMeetingApiDataset:
    """保存済みの raw JSON を読み込む。"""

    input_path = input_dir / f"{session}.json"
    return KokkaiMeetingApiDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def split_raw_lines(text: str) -> list[str]:
    """会議録本文を行ごとに分割する。"""

    return [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def compact_line(line: str) -> str:
    """比較用に空白を畳んだ行文字列を返す。"""

    return normalize_text(line.replace("\u3000", " "))


def is_separator_line(line: str) -> bool:
    """罫線だけの行かを判定する。"""

    text = compact_line(line)
    return bool(text) and set(text) <= SEPARATOR_CHARS


def is_month_day_line(line: str) -> bool:
    """`十二月十六日` のような日付行かを判定する。"""

    return re.fullmatch(r"[〇零一二三四五六七八九十\d]+\s*月\s*[〇零一二三四五六七八九十\d]+\s*日", line) is not None


def is_agenda_section_header(line: str) -> bool:
    """`本日の会議に付した事件` などの案件見出しかを判定する。"""

    normalized = line.lstrip("○●").replace(" ", "")
    return normalized in {"本日の会議に付した案件", "本日の会議に付した事件", "本日の開議に付した事件"}


def has_upcoming_referred_marker(lines: list[str], start_index: int) -> bool:
    """以降の数行に `付託された。` があるかを返す。"""

    for line in lines[start_index + 1 : start_index + 12]:
        if not line:
            continue
        if line.endswith("付託された。"):
            return True
        if "開議" in line or "開会" in line or line == "委員の異動" or line.endswith("本日の会議に付した案件"):
            return False
    return False


def parse_closing_line(text: str) -> tuple[str | None, datetime.time | None]:
    """終盤発言から散会・休憩時刻行を抜き出す。"""

    closing_line = None
    for raw_line in reversed(split_raw_lines(text)):
        line = compact_line(raw_line)
        if "散会" in line or "休憩" in line or "延会" in line:
            closing_line = line
            break
    return closing_line, parse_japanese_time(closing_line or "")


def looks_like_name_token(token: str) -> bool:
    """氏名の一部として自然なトークンかを判定する。"""

    text = normalize_text(token)
    if not text:
        return False
    if any(bracket in text for bracket in "（）()"):
        return False
    return NAME_TOKEN_PATTERN.fullmatch(text) is not None


def is_role_like_token(token: str) -> bool:
    """肩書きの末尾断片らしいトークンかを判定する。"""

    text = normalize_text(token)
    if not text:
        return False
    return any(text.endswith(suffix) for suffix in ROLE_TOKEN_SUFFIXES)


def looks_like_complete_name_token(token: str) -> bool:
    """単独で氏名として完結していそうなトークンかを判定する。"""

    text = normalize_text(token)
    if not looks_like_name_token(text):
        return False
    if re.fullmatch(r"[ァ-ヶー・]+", text):
        return False
    return len(text) >= 4


def split_prefix_and_name(text: str) -> tuple[str, str] | None:
    """`役職 氏名君` 形式から、末尾優先で役職と氏名を分離する。"""

    normalized = compact_line(text)
    if not normalized.endswith("君"):
        return None

    body = normalized[:-1].strip()
    tokens = body.split(" ")
    if not tokens or not looks_like_name_token(tokens[-1]):
        return None

    name_tokens = [tokens[-1]]
    if len(tokens) >= 2 and looks_like_name_token(tokens[-2]) and not is_role_like_token(tokens[-2]):
        previous_is_katakana = re.fullmatch(r"[ァ-ヶー・]+", normalize_text(tokens[-2])) is not None
        previous_continues_prior_token = (
            previous_is_katakana
            and len(tokens) >= 3
            and re.search(r"[ァ-ヶー・A-Za-z]$", normalize_text(tokens[-3])) is not None
        )
        if not looks_like_complete_name_token(tokens[-1]) or (previous_is_katakana and not previous_continues_prior_token):
            name_tokens = [tokens[-2], tokens[-1]]

    name = normalize_person_name(" ".join(name_tokens))
    prefix = normalize_text(" ".join(tokens[: len(tokens) - len(name_tokens)]))
    return prefix, name


def append_wrapped_metadata_item(items: list[str], raw_line: str) -> None:
    """折り返し行を直前の案件に連結しつつ保存する。"""

    text = compact_line(raw_line).lstrip("○")
    if not text:
        return
    if set(text) <= SEPARATOR_CHARS:
        return

    is_circle_item = raw_line.lstrip().startswith("○")
    is_numbered_item = re.match(r"^[一二三四五六七八九十百千]+、", text) is not None
    is_schedule_item = re.match(r"^日程第[一二三四五六七八九十百千\d]+", text) is not None
    is_self_contained_item = text.endswith(AGENDA_ITEM_END_MARKERS)
    leading_indent = len(re.match(r"^[\s\u3000]*", raw_line).group(0))
    starts_like_continuation = text.startswith(("（", "(", "及び", "並びに"))
    if items and not (is_circle_item or is_numbered_item or is_schedule_item or is_self_contained_item) and leading_indent >= 2 and starts_like_continuation:
        items[-1] = f"{items[-1]}{text}"
        return

    items.append(text)


def parse_attendance_entries_from_line(
    line: str,
    section: str | None,
    current_role: str | None,
    default_role: str | None,
) -> list[KokkaiAttendanceEntry]:
    """出席者表記1行から複数の出席者を抽出する。"""

    entries: list[KokkaiAttendanceEntry] = []
    remaining = compact_line(line)
    while remaining:
        match = re.match(r"^(?P<role>委員長|理事)\s+(?P<name>[^\s]+(?:\s+[^\s]+)?)君(?:\s+|$)", remaining)
        prefix = ""
        name = ""
        consumed = 0
        if match is not None:
            prefix = match.group("role")
            name = normalize_person_name(match.group("name"))
            consumed = match.end()
        else:
            segment_match = re.match(r"^(?P<segment>.+?君)(?:\s+|$)", remaining)
            if segment_match is None:
                break
            split = split_prefix_and_name(segment_match.group("segment"))
            if split is None:
                break
            prefix, name = split
            consumed = segment_match.end()

        role = current_role or default_role
        title = None
        if prefix:
            prefix_without_space = prefix.replace(" ", "")
            if prefix.startswith(("（", "(")) and (current_role or section):
                role = current_role or section or default_role
                title = prefix_without_space
            else:
                role = prefix_without_space
        entries.append(
            KokkaiAttendanceEntry(
                section=section,
                role=role,
                title=title,
                name=name,
            )
        )
        remaining = remaining[consumed:].strip()
    return entries


def parse_intro_metadata(text: str, house: str) -> KokkaiMeetingMetadataParsed:
    """冒頭の会議録情報から構造化メタデータを抽出する。"""

    raw_lines = split_raw_lines(text)
    lines = [compact_line(line) for line in raw_lines]
    non_empty_lines = [line for line in lines if line]
    meeting_date = next((parsed for line in non_empty_lines if (parsed := parse_japanese_date(line)) is not None), None)
    opening_line = next((line for line in non_empty_lines if "開議" in line or "開会" in line), None)
    opening_time = parse_japanese_time(opening_line or "")

    attendance: list[KokkaiAttendanceEntry] = []
    membership_changes: list[KokkaiMembershipChange] = []
    referred_items: list[str] = []
    agenda_items: list[str] = []

    default_attendance_section = "出席委員" if house == "衆議院" else "出席者"

    block: str | None = None
    current_section: str | None = None
    current_role: str | None = None
    pending_prefix = ""
    change_date = None
    default_role = "委員" if house == "衆議院" else None

    for index, (raw_line, line) in enumerate(zip(raw_lines, lines)):
        if not line:
            continue
        if is_separator_line(raw_line):
            if block in {"attendance", "membership_changes", "referred", "agenda"}:
                block = None
                current_section = None
                current_role = None
            pending_prefix = ""
            continue

        normalized_label = line.replace(" ", "")
        if line in {"出席委員", "出席者は左のとおり。"}:
            block = "attendance"
            current_section = default_attendance_section
            current_role = None
            pending_prefix = ""
            continue
        if line == "委員の異動":
            block = "membership_changes"
            current_section = None
            current_role = None
            pending_prefix = ""
            continue
        if is_agenda_section_header(line):
            block = "agenda"
            current_section = None
            current_role = None
            pending_prefix = ""
            continue
        if (
            block is None
            and meeting_date is not None
            and is_month_day_line(line)
            and has_upcoming_referred_marker(lines, index)
        ):
            block = "referred"
            current_section = None
            current_role = None
            pending_prefix = ""
            change_date = parse_japanese_date_with_default_year(line, meeting_date.year)
            continue

        if block == "referred":
            if line.endswith("付託された。"):
                block = None
                continue
            append_wrapped_metadata_item(referred_items, raw_line)
            continue

        if block == "agenda":
            if "開議" in line or "開会" in line:
                block = None
                continue
            if is_separator_line(raw_line):
                block = None
                continue
            append_wrapped_metadata_item(agenda_items, raw_line)
            continue

        if block == "membership_changes":
            if meeting_date is not None and is_month_day_line(line):
                change_date = parse_japanese_date_with_default_year(line, meeting_date.year)
                continue
            if normalized_label.replace(" ", "") in {"辞任補欠選任", "辞任", "補欠選任"}:
                continue
            names = re.findall(r"([^\s]+(?:\s+[^\s]+){0,2})君", line)
            if len(names) >= 2:
                membership_changes.append(
                    KokkaiMembershipChange(
                        changed_at=change_date,
                        resigned_name=normalize_person_name(names[0]),
                        appointed_name=normalize_person_name(names[1]),
                    )
                )
            continue

        if block != "attendance":
            continue

        if "君" not in line and not line.startswith("〔"):
            if normalized_label.endswith("委員会") or normalized_label in {"国土交通委員会", "法務委員会"}:
                current_section = normalized_label
                current_role = None
                pending_prefix = ""
                continue
            if normalized_label in ATTENDANCE_SECTION_LABELS:
                current_section = normalized_label
                current_role = None
                pending_prefix = ""
                continue
            if normalized_label in ROLE_HEADER_LABELS:
                current_role = normalized_label
                pending_prefix = ""
                continue
            pending_prefix = f"{pending_prefix} {line}".strip()
            continue

        line_for_parse = f"{pending_prefix} {raw_line}".strip() if pending_prefix else raw_line
        pending_prefix = ""
        normalized_line_for_parse = compact_line(line_for_parse)
        segments = [
            segment.strip()
            for segment in re.split(r"(?=(?:委員長|理事)\s)", normalized_line_for_parse)
            if segment.strip()
        ]
        if len(segments) <= 1:
            segments = [line_for_parse]
        for segment in segments:
            for entry in parse_attendance_entries_from_line(
                line=segment,
                section=current_section,
                current_role=current_role,
                default_role=default_role,
            ):
                attendance.append(entry)

    return KokkaiMeetingMetadataParsed(
        meeting_date=meeting_date,
        opening_line=opening_line,
        opening_time=opening_time,
        attendance=attendance,
        membership_changes=membership_changes,
        referred_items=referred_items,
        agenda_items=agenda_items,
        intro_text=text,
    )


def build_parsed_item(item) -> KokkaiMeetingParsedItem:
    """raw 会議録1件から保存用アイテムを構築する。"""

    first_speech = item.speech_record[0] if item.speech_record else None
    last_speech = item.speech_record[-1] if item.speech_record else None
    parsed = parse_intro_metadata(first_speech.speech, house=item.name_of_house) if first_speech else KokkaiMeetingMetadataParsed()
    closing_line, closing_time = parse_closing_line(last_speech.speech if last_speech else "")
    parsed.closing_line = closing_line
    parsed.closing_time = closing_time
    parsed.closing_text = last_speech.speech if last_speech else None

    return KokkaiMeetingParsedItem(
        issue_id=item.issue_id,
        session=item.session,
        name_of_house=item.name_of_house,
        name_of_meeting=item.name_of_meeting,
        issue=item.issue,
        date=item.date,
        closing=item.closing,
        meeting_url=item.meeting_url,
        pdf_url=item.pdf_url,
        speech_count=len(item.speech_record),
        parsed=parsed,
    )


def save_dataset(dataset: KokkaiMeetingParsedDataset, output_dir: Path = OUTPUT_DIR) -> Path:
    """抽出済みメタデータを JSON として保存する。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{dataset.session_number}.json"
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, skip_existing: bool = False, output_dir: Path = OUTPUT_DIR) -> Path:
    """指定回次の raw JSON からメタデータ抽出結果を保存する。"""

    output_path = output_dir / f"{session}.json"
    if should_skip_existing(output_path, skip_existing):
        logger.info("スキップ: 既存ファイルあり session=%s path=%s", session, output_path)
        return output_path

    raw_dataset = load_dataset(session)
    logger.info("会議録メタデータ抽出開始: session=%s items=%s", session, len(raw_dataset.items))
    dataset = KokkaiMeetingParsedDataset(
        source_url=raw_dataset.source_url,
        fetched_at=raw_dataset.fetched_at,
        parsed_at=datetime.now(timezone.utc),
        session_number=session,
        total_records=raw_dataset.total_records,
        items=[build_parsed_item(item) for item in raw_dataset.items],
    )
    output_path = save_dataset(dataset=dataset, output_dir=output_dir)
    logger.info("保存: session=%s path=%s items=%s", session, output_path, len(dataset.items))
    logger.info("会議録メタデータ抽出完了: session=%s", session)
    return output_path


def main() -> None:
    """指定回次の会議録 JSON からメタデータを抽出する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
