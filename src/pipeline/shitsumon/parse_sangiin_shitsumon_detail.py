"""保存済みの参議院質問主意書個別 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/shitsumon/sangiin/list/{session}.json
    - tmp/shitsumon/sangiin/detail/{question_id}/detail.html
    - tmp/shitsumon/sangiin/detail/{question_id}/question.html
    - tmp/shitsumon/sangiin/detail/{question_id}/answer.html

出力:
    - tmp/shitsumon/sangiin/detail/{question_id}/index.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    SangiinShitsumonDetailDataset,
    SangiinShitsumonListDataset,
    ShugiinShitsumonDocumentParsed,
    ShugiinShitsumonProgressParsed,
)
from src.utils import (
    build_sangiin_shitsumon_id,
    normalize_text,
    parse_int,
    parse_japanese_date,
)

INPUT_DIR = Path("tmp/shitsumon/sangiin/list")
DETAIL_ROOT = Path("tmp/shitsumon/sangiin/detail")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の参議院質問主意書個別HTMLをパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_shitsumon_list(session: int, input_dir: Path = INPUT_DIR) -> SangiinShitsumonListDataset:
    """質問主意書一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return SangiinShitsumonListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def load_html(path: Path) -> str:
    """保存済み HTML を読み込む。"""

    return path.read_text(encoding="utf-8")


def extract_text_lines(node: Tag | NavigableString) -> list[str]:
    """要素からテキスト行を抽出する。"""

    text = str(node) if isinstance(node, NavigableString) else node.get_text("\n", strip=False)
    return [normalize_text(line) for line in text.splitlines()]


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
    """詳細ページ HTML を衆議院と同型の経過データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    session_type = None
    exp_node = soup.find("p", class_="exp")
    if exp_node is not None:
        exp_text = normalize_text(exp_node.get_text(" ", strip=True))
        session_match = re.search(r"第\d+回国会（([^）]+)）", exp_text)
        if session_match:
            session_type = session_match.group(1)

    tables = soup.find_all("table", class_="list_c")
    values: dict[str, str] = {}
    note = None
    for table in tables:
        rows = table.find_all("tr", recursive=False)
        for row in rows:
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) == 2:
                label = normalize_text(cells[0].get_text(" ", strip=True))
                value = normalize_text(cells[1].get_text(" ", strip=True))
                if label:
                    values[label] = value
            elif len(cells) == 1:
                head = normalize_text(cells[0].get_text(" ", strip=True))
                if "内閣から通知書受領" in head or "答弁延期" in head:
                    note = head

    submitted_at = parse_japanese_date(values.get("提出日", ""))
    cabinet_sent_at = parse_japanese_date(values.get("転送日", ""))
    answer_received_at = parse_japanese_date(values.get("答弁書受領日", ""))
    answer_delay_notice_received_at = None
    answer_due_at = None
    if note:
        notice_match = re.search(r"(\d+月\d+日)内閣から通知書受領", note)
        due_match = re.search(r"(\d+月\d+日)まで答弁延期", note)
        year_text = None
        if submitted_at is not None:
            year_text = f"{submitted_at.year}年"
        if year_text and notice_match:
            answer_delay_notice_received_at = parse_japanese_date(f"{year_text}{notice_match.group(1)}")
        if year_text and due_match:
            answer_due_at = parse_japanese_date(f"{year_text}{due_match.group(1)}")

    status = "答弁受理" if answer_received_at is not None else "未答弁"
    if answer_due_at is not None and answer_received_at is None:
        status = "答弁延期"

    return ShugiinShitsumonProgressParsed(
        session_type=session_type,
        submitted_at=submitted_at,
        cabinet_sent_at=cabinet_sent_at,
        answer_delay_notice_received_at=answer_delay_notice_received_at,
        answer_due_at=answer_due_at,
        answer_received_at=answer_received_at,
        status=status,
    )


def extract_document_td(soup: BeautifulSoup) -> Tag:
    """本文を含む TD 要素を取得する。"""

    td = soup.find("div", id="ContentsBox")
    if td is None:
        raise ValueError("参議院本文ページの本文領域を特定できませんでした。")
    target = td.find("td")
    if target is None:
        raise ValueError("参議院本文ページの本文TDを特定できませんでした。")
    return target


def extract_document_lines(td: Tag) -> list[str]:
    """本文 TD から行配列を作る。"""

    lines: list[str] = []
    for node in td.children:
        if isinstance(node, Tag) and node.name == "hr":
            lines.append("")
            continue
        lines.extend(extract_text_lines(node))
    return compact_lines(lines)


def parse_question_document(html: str) -> ShugiinShitsumonDocumentParsed:
    """質問本文ページ HTML を衆議院と同型の本文データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    lines = extract_document_lines(extract_document_td(soup))
    document_date = parse_japanese_date(
        next(
            (
                line
                for line in lines
                if line.endswith("日") and ("令和" in line or "平成" in line or "昭和" in line)
            ),
            "",
        )
    )
    title_indexes = [idx for idx, line in enumerate(lines) if line.endswith("質問主意書")]
    body_start = title_indexes[-1] if title_indexes else 0
    body_lines = lines[body_start:]
    return ShugiinShitsumonDocumentParsed(
        document_date=document_date,
        body_text="\n".join(body_lines) or None,
    )


def parse_answer_document(html: str) -> ShugiinShitsumonDocumentParsed | None:
    """答弁本文ページ HTML を衆議院と同型の本文データへ変換する。"""

    soup = BeautifulSoup(html, "html.parser")
    lines = extract_document_lines(extract_document_td(soup))
    if not lines:
        return None
    date_line = next(
        (
            line
            for line in lines
            if line.endswith("日") and ("令和" in line or "平成" in line or "昭和" in line)
        ),
        "",
    )
    answerer_line = next((line for line in lines if line.startswith("内閣総理大臣")), "")
    body_start = next((idx for idx, line in enumerate(lines) if line.endswith("答弁書")), 0)
    body_lines = lines[body_start:]
    return ShugiinShitsumonDocumentParsed(
        document_date=parse_japanese_date(date_line),
        answerer_name=normalize_text(answerer_line.removeprefix("内閣総理大臣")) or None,
        body_text="\n".join(body_lines) or None,
    )


def save_dataset(dataset: SangiinShitsumonDetailDataset, question_id: str, detail_root: Path = DETAIL_ROOT) -> Path:
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
    logger.info("参議院質問主意書個票JSONパース開始: session=%s items=%s", session, len(shitsumon_list.items))
    saved_paths: list[Path] = []
    for item in shitsumon_list.items:
        question_id = build_sangiin_shitsumon_id(session_number=session, question_number=item.question_number)
        detail_dir = DETAIL_ROOT / question_id
        progress = None
        question_document = None
        answer_document = None

        detail_path = detail_dir / "detail.html"
        if detail_path.exists():
            progress = parse_progress_html(load_html(detail_path))

        question_path = detail_dir / "question.html"
        if question_path.exists():
            question_document = parse_question_document(load_html(question_path))

        answer_path = detail_dir / "answer.html"
        if answer_path.exists():
            answer_document = parse_answer_document(load_html(answer_path))

        dataset = SangiinShitsumonDetailDataset(
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

    logger.info("参議院質問主意書個票JSONパース完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の個別 HTML を一括パースして保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
