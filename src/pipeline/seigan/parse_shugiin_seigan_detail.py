"""保存済みの衆議院請願個別 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/seigan/shugiin/list/{session}.json
    - tmp/seigan/shugiin/detail/{petition_id}/detail.html

出力:
    - tmp/seigan/shugiin/detail/{petition_id}/index.json

主な内容:
    - 請願番号
    - 件名
    - 請願要旨
    - 受理件数
    - 請願者通数
    - 付託委員会
    - 結果
    - 紹介議員一覧
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import SeiganDetailDataset, SeiganListDataset, SeiganPresenter
from src.utils import build_shugiin_seigan_id, normalize_text, parse_int

INPUT_DIR = Path("tmp/seigan/shugiin/list")
DETAIL_ROOT = Path("tmp/seigan/shugiin/detail")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の衆議院請願個別 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_list(session: int, input_dir: Path = INPUT_DIR) -> SeiganListDataset:
    """請願一覧 JSON を読み込む。"""

    return SeiganListDataset.model_validate_json((input_dir / f"{session}.json").read_text(encoding="utf-8"))


def load_html(path: Path) -> str:
    """保存済み HTML を読み込む。"""

    return path.read_text(encoding="utf-8")


def parse_value_rows(html: str) -> dict[str, Tag]:
    """個票テーブルの項目名と値セルを対応付ける。"""

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table")
    if table is None:
        raise ValueError("衆議院請願個票テーブルを特定できませんでした。")
    values: dict[str, Tag] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 2:
            continue
        label = normalize_text(cells[0].get_text(" ", strip=True))
        if label in {"項目", "内容"} or not label:
            continue
        values[label] = cells[1]
    return values


def get_cell_text(values: dict[str, Tag], label: str) -> str:
    """項目名に対応するセルのテキストを返す。"""

    cell = values.get(label)
    if cell is None:
        return ""
    return normalize_text(cell.get_text(" ", strip=True))


def html_cell_to_text(cell: Tag) -> str:
    """セルの改行を維持してテキスト化する。"""

    text = cell.get_text("\n", strip=False)
    lines = [normalize_text(line) for line in text.splitlines()]
    compacted: list[str] = []
    for line in lines:
        if line == "" and compacted and compacted[-1] == "":
            continue
        compacted.append(line)
    return "\n".join(line for line in compacted if line != "" or compacted.count("") == 1).strip()


def parse_presenters(cell: Tag) -> list[SeiganPresenter]:
    """紹介議員一覧セルから紹介議員配列を作る。"""

    presenters: list[SeiganPresenter] = []
    for line in [normalize_text(part) for part in cell.get_text("\n", strip=False).splitlines()]:
        if not line or "紹介議員一覧" in line:
            continue
        match = re.search(r"受理番号\s*(\d+)番\s*(.+)", line)
        if match:
            presenters.append(
                SeiganPresenter(
                    receipt_number=int(match.group(1)),
                    presenter_name=normalize_text(match.group(2)),
                )
            )
    return presenters


def save_dataset(dataset: SeiganDetailDataset, petition_id: str, detail_root: Path = DETAIL_ROOT) -> Path:
    """パース済み個票 JSON を保存する。"""

    output_path = detail_root / petition_id / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def process_session(session: int) -> list[Path]:
    """指定回次の個別 HTML を一括パースして保存する。"""

    dataset = load_list(session)
    saved_paths: list[Path] = []
    logger.info("衆議院請願個票JSONパース開始: session=%s items=%s", session, len(dataset.items))
    for item in dataset.items:
        petition_id = build_shugiin_seigan_id(session_number=session, petition_number=item.petition_number)
        detail_path = DETAIL_ROOT / petition_id / "detail.html"
        if not detail_path.exists():
            continue
        values = parse_value_rows(load_html(detail_path))
        parsed = SeiganDetailDataset(
            petition_id=petition_id,
            house="shugiin",
            session_number=session,
            petition_number=item.petition_number,
            title=get_cell_text(values, "件名") or item.title,
            committee_name=get_cell_text(values, "付託委員会") or item.committee_name,
            committee_code=item.committee_code,
            detail_source_url=item.detail_url,
            fetched_at=datetime.now(timezone.utc),
            summary_text=html_cell_to_text(values["請願要旨"]) if "請願要旨" in values else None,
            accepted_count=parse_int(get_cell_text(values, "受理件数（計）")),
            signer_count=parse_int(get_cell_text(values, "請願者通数（計）").replace(",", "")),
            outcome=get_cell_text(values, "結果／年月日") or None,
            presenters=parse_presenters(values["紹介議員一覧"]) if "紹介議員一覧" in values else [],
        )
        output_path = save_dataset(dataset=parsed, petition_id=petition_id)
        saved_paths.append(output_path)
    logger.info("衆議院請願個票JSONパース完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の個別 HTML を一括パースして保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
