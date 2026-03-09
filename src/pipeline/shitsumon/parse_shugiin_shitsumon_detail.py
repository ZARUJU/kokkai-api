"""保存済みの衆議院質問主意書個別 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/shitsumon/shugiin/list/{session}.json
    - tmp/shitsumon/shugiin/detail/{question_id}/progress.html
    - tmp/shitsumon/shugiin/detail/{question_id}/question.html
    - tmp/shitsumon/shugiin/detail/{question_id}/answer.html

出力:
    - tmp/shitsumon/shugiin/detail/{question_id}/index.json

主な内容:
    - 一覧情報
    - 経過情報の構造化データ
    - 質問本文のメタデータと本文テキスト
    - 答弁本文のメタデータと本文テキスト
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    ShugiinShitsumonDetailDataset,
    ShugiinShitsumonDocumentParsed,
    ShugiinShitsumonListDataset,
    ShugiinShitsumonProgressParsed,
)
from src.utils import (
    build_shugiin_shitsumon_id,
    normalize_text,
    parse_int,
    parse_japanese_date,
)

INPUT_DIR = Path("tmp/shitsumon/shugiin/list")
DETAIL_ROOT = Path("tmp/shitsumon/shugiin/detail")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院質問主意書個別HTMLをパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_shitsumon_list(session: int, input_dir: Path = INPUT_DIR) -> ShugiinShitsumonListDataset:
    """質問主意書一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return ShugiinShitsumonListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def load_html(path: Path) -> str:
    """保存済み HTML を読み込む。"""

    return path.read_text(encoding="utf-8")


def extract_text_lines(node: Tag | NavigableString) -> list[str]:
    """要素から空行を保ちながらテキスト行を抽出する。"""

    if isinstance(node, NavigableString):
        text = str(node)
    else:
        text = node.get_text("\n", strip=False)
    lines = []
    for raw_line in text.splitlines():
        normalized = normalize_text(raw_line)
        lines.append(normalized)
    return lines


def compact_lines(lines: list[str]) -> list[str]:
    """連続空行を圧縮し、前後の空行を除去する。"""

    result: list[str] = []
    previous_blank = True
    for line in lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        result.append(line)
        previous_blank = is_blank
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()
    return result


def parse_progress_html(html: str) -> ShugiinShitsumonProgressParsed:
    """経過ページ HTML を構造化データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("経過情報テーブルを特定できませんでした。")

    entries: list[tuple[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 2:
            continue
        label = normalize_text(cells[0].get_text(" ", strip=True))
        value = normalize_text(cells[1].get_text(" ", strip=True))
        if label in {"項目", "内容"} or not label:
            continue
        entries.append((label, value))

    values = {label: value for label, value in entries}
    return ShugiinShitsumonProgressParsed(
        session_type=values.get("国会区別") or None,
        group_name=values.get("会派名") or None,
        submitted_at=parse_japanese_date(values.get("質問主意書提出年月日", "")),
        cabinet_sent_at=parse_japanese_date(values.get("内閣転送年月日", "")),
        answer_delay_notice_received_at=parse_japanese_date(values.get("答弁延期通知受領年月日", "")),
        answer_due_at=parse_japanese_date(values.get("答弁延期期限年月日", "")),
        answer_received_at=parse_japanese_date(values.get("答弁書受領年月日", "")),
        withdrawn_at=parse_japanese_date(values.get("撤回年月日", "")),
        withdrawal_notice_at=parse_japanese_date(values.get("撤回通知年月日", "")),
        status=values.get("経過状況") or None,
    )


def extract_document_sections(mainlayout: Tag) -> tuple[list[str], list[str]]:
    """本文ページから前書き部と本文部を抽出する。"""

    top_contents = mainlayout.find(id="TopContents")
    if top_contents is None:
        raise ValueError("本文ページの見出しを特定できませんでした。")

    before_hr_lines: list[str] = []
    body_lines: list[str] = []
    in_body = False

    for node in top_contents.next_siblings:
        if isinstance(node, Tag):
            if node.name == "hr":
                in_body = True
                continue
            if node.name == "div" and node.find("a", href=True) is not None:
                continue
        lines = extract_text_lines(node)
        if in_body:
            body_lines.extend(lines)
        else:
            before_hr_lines.extend(lines)

    return compact_lines(before_hr_lines), compact_lines(body_lines)


def parse_question_document(html: str) -> ShugiinShitsumonDocumentParsed:
    """質問本文ページ HTML を構造化データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    mainlayout = soup.find("div", id="mainlayout")
    if mainlayout is None:
        raise ValueError("質問本文ページの本文領域を特定できませんでした。")

    lines, body_lines = extract_document_sections(mainlayout)
    return ShugiinShitsumonDocumentParsed(
        document_date=parse_japanese_date(next((line for line in lines if line.endswith("提出")), "")),
        body_text="\n".join(body_lines) or None,
    )


def parse_answer_document(html: str) -> ShugiinShitsumonDocumentParsed:
    """答弁本文ページ HTML を構造化データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    mainlayout = soup.find("div", id="mainlayout")
    if mainlayout is None:
        raise ValueError("答弁本文ページの本文領域を特定できませんでした。")

    lines, body_lines = extract_document_sections(mainlayout)
    answerer_line = next((line for line in lines if line.startswith("内閣総理大臣")), "")

    return ShugiinShitsumonDocumentParsed(
        document_date=parse_japanese_date(next((line for line in lines if line.endswith("受領")), "")),
        answerer_name=normalize_text(answerer_line.removeprefix("内閣総理大臣")) or None,
        body_text="\n".join(body_lines) or None,
    )


def save_dataset(dataset: ShugiinShitsumonDetailDataset, question_id: str, detail_root: Path = DETAIL_ROOT) -> Path:
    """パース済み個票 JSON を保存する。"""

    output_path = detail_root / question_id / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int) -> list[Path]:
    """指定回次の個別 HTML を一括パースして保存する。"""

    shitsumon_list = load_shitsumon_list(session)
    logger.info("質問主意書個票JSONパース開始: session=%s items=%s", session, len(shitsumon_list.items))
    saved_paths: list[Path] = []

    for item in shitsumon_list.items:
        question_id = build_shugiin_shitsumon_id(session_number=session, question_number=item.question_number)
        detail_dir = DETAIL_ROOT / question_id

        progress = None
        question_document = None
        answer_document = None

        progress_path = detail_dir / "progress.html"
        if progress_path.exists():
            progress = parse_progress_html(load_html(progress_path))

        question_path = detail_dir / "question.html"
        if question_path.exists():
            question_document = parse_question_document(load_html(question_path))

        answer_path = detail_dir / "answer.html"
        if answer_path.exists():
            answer_document = parse_answer_document(load_html(answer_path))

        dataset = ShugiinShitsumonDetailDataset(
            question_id=question_id,
            source_url=shitsumon_list.source_url,
            fetched_at=datetime.now(timezone.utc),
            title=item.title,
            submitter_name=item.submitter_name,
            progress=progress,
            question_document=question_document,
            answer_document=answer_document,
        )
        output_path = save_dataset(dataset=dataset, question_id=question_id)
        logger.info("保存: question_id=%s path=%s", question_id, output_path)
        saved_paths.append(output_path)

    logger.info("質問主意書個票JSONパース完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の個別 HTML を一括パースして保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
