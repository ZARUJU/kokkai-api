"""保存済みの参議院請願個別 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/seigan/sangiin/list/{session}.json
    - tmp/seigan/sangiin/detail/{petition_id}/detail.html
    - tmp/seigan/sangiin/detail/{petition_id}/similar.html

出力:
    - tmp/seigan/sangiin/detail/{petition_id}/index.json

主な内容:
    - 請願番号
    - 件名
    - 要旨
    - 件数
    - 署名者数
    - 結果
    - 紹介議員・受理一覧
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import SeiganDetailDataset, SeiganListDataset, SeiganPresenter
from src.utils import build_sangiin_seigan_id, normalize_person_name, normalize_text, parse_int, parse_japanese_date

INPUT_DIR = Path("tmp/seigan/sangiin/list")
DETAIL_ROOT = Path("tmp/seigan/sangiin/detail")


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の参議院請願個別 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_list(session: int, input_dir: Path = INPUT_DIR) -> SeiganListDataset:
    """請願一覧 JSON を読み込む。"""

    return SeiganListDataset.model_validate_json((input_dir / f"{session}.json").read_text(encoding="utf-8"))


def load_html(path: Path) -> str:
    """保存済み HTML を読み込む。"""

    return path.read_text(encoding="utf-8")


def parse_summary_text(html: str) -> str | None:
    """請願要旨ページから要旨本文を抽出する。"""

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="list_c")
    if table is None:
        return None
    rows = table.find_all("tr", recursive=False)
    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 4 and len(cells) != 2:
            continue
        label = normalize_text(cells[0].get_text(" ", strip=True))
        if label != "要旨":
            continue
        body_cell = cells[-1]
        lines = [normalize_text(line) for line in body_cell.get_text("\n", strip=False).splitlines()]
        compacted: list[str] = []
        for line in lines:
            if line == "" and compacted and compacted[-1] == "":
                continue
            compacted.append(line)
        return "\n".join(line for line in compacted if line).strip() or None
    return None


def extract_cell_lines(cell: Tag) -> list[str]:
    """セル内の `<br>` 区切りを保って行配列に変換する。"""

    return [normalize_text(line) for line in cell.get_text("\n", strip=False).splitlines() if normalize_text(line)]


def parse_similar_page(html: str) -> tuple[str | None, int | None, int | None, list[SeiganPresenter]]:
    """同趣旨一覧ページから件数や紹介議員一覧を抽出する。"""

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="list_c")
    if table is None:
        return None, None, None, []

    accepted_count = None
    signer_count = None
    presenters: list[SeiganPresenter] = []
    for row in table.find_all("tr", recursive=False):
        cells = row.find_all(["th", "td"], recursive=False)
        texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
        if len(cells) == 2 and texts[0] == "件名":
            continue
        if len(cells) >= 6 and texts[0] == "新件番号":
            accepted_count = parse_int(texts[3] if len(texts) > 3 else "")
            signer_count = parse_int((texts[5] if len(texts) > 5 else "").replace(",", ""))
            continue
        if texts and texts[0] == "受理番号":
            continue
        if len(cells) >= 6 and parse_int(texts[0] or "") is not None:
            presenter_names = extract_cell_lines(cells[1]) or ([texts[1]] if len(texts) > 1 and texts[1] else [])
            party_names = extract_cell_lines(cells[2]) or ([texts[2]] if len(texts) > 2 and texts[2] else [])
            receipt_number = parse_int(texts[0])
            received_at = parse_japanese_date(texts[3])
            referred_at = parse_japanese_date(texts[4])
            result = texts[5] or None

            for presenter_name, party_name in zip_longest(presenter_names, party_names, fillvalue=None):
                if not presenter_name:
                    continue
                presenters.append(
                    SeiganPresenter(
                        receipt_number=receipt_number,
                        presenter_name=normalize_person_name(presenter_name),
                        party_name=party_name or None,
                        received_at=received_at,
                        referred_at=referred_at,
                        result=result,
                    )
                )

    outcome = None
    if presenters:
        counter = Counter(presenter.result for presenter in presenters if presenter.result)
        if counter:
            outcome = counter.most_common(1)[0][0]
    return outcome, accepted_count, signer_count, presenters


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
    for item in dataset.items:
        petition_id = build_sangiin_seigan_id(session_number=session, petition_number=item.petition_number)
        detail_path = DETAIL_ROOT / petition_id / "detail.html"
        similar_path = DETAIL_ROOT / petition_id / "similar.html"

        summary_text = parse_summary_text(load_html(detail_path)) if detail_path.exists() else None
        outcome = None
        accepted_count = None
        signer_count = None
        presenters: list[SeiganPresenter] = []
        if similar_path.exists():
            outcome, accepted_count, signer_count, presenters = parse_similar_page(load_html(similar_path))

        parsed = SeiganDetailDataset(
            petition_id=petition_id,
            house="sangiin",
            session_number=session,
            petition_number=item.petition_number,
            title=item.title,
            committee_name=item.committee_name,
            committee_code=item.committee_code,
            detail_source_url=item.detail_url,
            similar_petitions_source_url=item.similar_petitions_url,
            fetched_at=datetime.now(timezone.utc),
            summary_text=summary_text,
            accepted_count=accepted_count,
            signer_count=signer_count,
            outcome=outcome,
            presenters=presenters,
        )
        saved_paths.append(save_dataset(dataset=parsed, petition_id=petition_id))
    return saved_paths


def main() -> None:
    """指定回次の個別 HTML を一括パースして保存する。"""

    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
