"""保存済みの議案進捗 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/gian/list/{session}.json
    - tmp/gian/detail/{bill_id}/progress/{session}.html

出力:
    - tmp/gian/detail/{bill_id}/progress/{session}.json

主な内容:
    - bill_id
    - 議案一覧由来の識別情報
    - 型付きに整形した進捗情報
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    GianItem,
    GianListDataset,
    GianMemberLawExtraParsed,
    GianProgressDateText,
    GianProgressDataset,
    GianProgressEntry,
    GianProgressParsed,
    GianProgressSection,
)
from src.utils import build_gian_bill_id, normalize_text, parse_int, parse_japanese_date

INPUT_LIST_DIR = Path("tmp/gian/list")
DETAIL_ROOT = Path("tmp/gian/detail")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案進捗 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_gian_list(session: int, input_dir: Path = INPUT_LIST_DIR) -> GianListDataset:
    """議案一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return GianListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def extract_row_texts(table: Tag) -> list[list[str]]:
    """テーブルを文字列の2次元配列に変換する。"""

    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [normalize_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def parse_entries_from_rows(rows: list[list[str]], skip_header: bool) -> list[GianProgressEntry]:
    """テーブル行を `label` と `value` の配列に変換する。"""

    entries: list[GianProgressEntry] = []
    start_index = 1 if skip_header else 0
    for row in rows[start_index:]:
        if not row:
            continue
        label = row[0]
        value = normalize_text(" ".join(row[1:])) if len(row) > 1 else ""
        if not label:
            continue
        entries.append(GianProgressEntry(label=label, value=value))
    return entries


def parse_progress_tables(soup: BeautifulSoup) -> tuple[list[GianProgressEntry], list[GianProgressSection]]:
    """進捗ページから主テーブルと補助テーブルを抽出する。"""

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("進捗ページにテーブルが見つかりませんでした。")

    main_rows = extract_row_texts(tables[0])
    main_entries = parse_entries_from_rows(main_rows, skip_header=True)
    if not main_entries:
        raise ValueError("進捗ページの主テーブルを抽出できませんでした。")

    extra_sections: list[GianProgressSection] = []
    for table in tables[1:]:
        rows = extract_row_texts(table)
        entries = parse_entries_from_rows(rows, skip_header=False)
        if not entries:
            continue
        caption = table.find("caption")
        section_name = normalize_text(caption.get_text(" ", strip=True)) if caption else None
        extra_sections.append(GianProgressSection(section_name=section_name, entries=entries))

    return main_entries, extra_sections


def entries_to_map(entries: list[GianProgressEntry]) -> dict[str, str]:
    """進捗項目配列をラベル基準の辞書に変換する。"""

    return {entry.label: entry.value for entry in entries}


def split_slash_value(value: str) -> tuple[str | None, str | None]:
    """`日付 ／ 委員会` のような値を前後に分割する。"""

    text = normalize_text(value)
    if not text or text == "／":
        return None, None

    parts = [normalize_text(part) for part in text.split("／", 1)]
    if len(parts) == 1:
        return parts[0] or None, None
    left = parts[0] or None
    right = parts[1] or None
    return left, right


def parse_date_text(value: str) -> GianProgressDateText | None:
    """`日付 ／ 補足` 形式の値を正規化する。"""

    left, right = split_slash_value(value)
    if left is None and right is None:
        return None

    date = parse_japanese_date(left or "")
    text = right
    if date is None and left and right is None:
        text = left

    if date is None and text is None:
        return None
    return GianProgressDateText(occurred_at=date, text=text)


def parse_group_list(value: str) -> list[str]:
    """会派や議員のセミコロン区切り文字列を配列に変換する。"""

    text = normalize_text(value)
    if not text:
        return []
    return [part for part in (normalize_text(item) for item in text.split(";")) if part]


def parse_member_law_extra(extra_sections: list[GianProgressSection]) -> GianMemberLawExtraParsed | None:
    """衆法の補助テーブルを専用型へ変換する。"""

    values: dict[str, str] = {}
    for section in extra_sections:
        for entry in section.entries:
            values[entry.label] = entry.value

    submitter_list = parse_group_list(values.get("議案提出者一覧", ""))
    supporters = parse_group_list(values.get("議案提出の賛成者", ""))
    if not submitter_list and not supporters:
        return None
    return GianMemberLawExtraParsed(
        submitter_list=submitter_list,
        supporters=supporters,
    )


def build_parsed_progress(
    entries: list[GianProgressEntry],
    extra_sections: list[GianProgressSection],
) -> GianProgressParsed:
    """raw の進捗情報から型付き `parsed` を構築する。"""

    values = entries_to_map(entries)
    parsed = GianProgressParsed(
        bill_type=values.get("議案種類") or None,
        bill_submit_session=parse_int(values.get("議案提出回次", "")),
        bill_number=parse_int(values.get("議案番号", "")),
        bill_title=values.get("議案件名") or None,
        submitter=values.get("議案提出者") or None,
        submitter_group=values.get("議案提出会派") or None,
        member_law_extra=parse_member_law_extra(extra_sections),
    )

    parsed.house_of_reps.pre_review_received_at = parse_japanese_date(
        values.get("衆議院予備審査議案受理年月日", "")
    )
    parsed.house_of_reps.pre_referral = parse_date_text(
        values.get("衆議院予備付託年月日／衆議院予備付託委員会", "")
    )
    parsed.house_of_reps.bill_received_at = parse_japanese_date(values.get("衆議院議案受理年月日", ""))
    parsed.house_of_reps.referral = parse_date_text(values.get("衆議院付託年月日／衆議院付託委員会", ""))
    parsed.house_of_reps.review_finished = parse_date_text(
        values.get("衆議院審査終了年月日／衆議院審査結果", "")
    )
    parsed.house_of_reps.plenary_finished = parse_date_text(
        values.get("衆議院審議終了年月日／衆議院審議結果", "")
    )
    parsed.house_of_reps.stance = values.get("衆議院審議時会派態度") or None
    parsed.house_of_reps.supporting_groups = parse_group_list(values.get("衆議院審議時賛成会派", ""))
    parsed.house_of_reps.opposing_groups = parse_group_list(values.get("衆議院審議時反対会派", ""))

    parsed.house_of_councillors.pre_review_received_at = parse_japanese_date(
        values.get("参議院予備審査議案受理年月日", "")
    )
    parsed.house_of_councillors.pre_referral = parse_date_text(
        values.get("参議院予備付託年月日／参議院予備付託委員会", "")
    )
    parsed.house_of_councillors.bill_received_at = parse_japanese_date(
        values.get("参議院議案受理年月日", "")
    )
    parsed.house_of_councillors.referral = parse_date_text(
        values.get("参議院付託年月日／参議院付託委員会", "")
    )
    parsed.house_of_councillors.review_finished = parse_date_text(
        values.get("参議院審査終了年月日／参議院審査結果", "")
    )
    parsed.house_of_councillors.plenary_finished = parse_date_text(
        values.get("参議院審議終了年月日／参議院審議結果", "")
    )

    promulgation = parse_date_text(values.get("公布年月日／法律番号", ""))
    if promulgation is not None:
        parsed.promulgation.promulgated_at = promulgation.occurred_at
        parsed.promulgation.law_number = promulgation.text

    return parsed


def build_progress_dataset(session: int, item: GianItem, html: str) -> GianProgressDataset:
    """議案一覧の1件と進捗ページ HTML から保存用データを構築する。"""

    if item.progress_url is None:
        raise ValueError("progress_url がない議案は進捗取得できません。")

    soup = BeautifulSoup(html, "html.parser")
    entries, extra_sections = parse_progress_tables(soup)
    page_title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else None
    bill_id = build_gian_bill_id(
        category=item.category,
        submitted_session=item.submitted_session,
        bill_number=item.bill_number,
        title=item.title,
        subcategory=item.subcategory,
    )

    return GianProgressDataset(
        bill_id=bill_id,
        category=item.category,
        subcategory=item.subcategory,
        submitted_session=item.submitted_session,
        bill_number=item.bill_number,
        title=item.title,
        status=item.status,
        source_url=str(item.progress_url),
        fetched_at=datetime.now(timezone.utc),
        page_title=page_title,
        session_number=session,
        parsed=build_parsed_progress(entries=entries, extra_sections=extra_sections),
    )


def save_progress_dataset(dataset: GianProgressDataset, detail_root: Path = DETAIL_ROOT) -> Path:
    """パース済み進捗情報を JSON に保存する。"""

    output_path = detail_root / dataset.bill_id / "progress" / f"{dataset.session_number}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, detail_root: Path = DETAIL_ROOT) -> list[Path]:
    """指定回次の保存済み進捗 HTML を一括パースして保存する。"""

    gian_list = load_gian_list(session)
    logger.info("進捗JSONパース開始: session=%s items=%s", session, len(gian_list.items))
    saved_paths: list[Path] = []
    for item in gian_list.items:
        if item.progress_url is None:
            logger.info("スキップ: progress_urlなし title=%s", item.title)
            continue
        bill_id = build_gian_bill_id(
            category=item.category,
            submitted_session=item.submitted_session,
            bill_number=item.bill_number,
            title=item.title,
            subcategory=item.subcategory,
        )
        html_path = detail_root / bill_id / "progress" / f"{session}.html"
        logger.info("読込: bill_id=%s path=%s", bill_id, html_path)
        html = html_path.read_text(encoding="utf-8")
        dataset = build_progress_dataset(session=session, item=item, html=html)
        output_path = save_progress_dataset(dataset, detail_root=detail_root)
        logger.info("保存: bill_id=%s path=%s", bill_id, output_path)
        saved_paths.append(output_path)
    logger.info("進捗JSONパース完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の保存済み進捗 HTML をパースして JSON に保存する。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
