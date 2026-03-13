"""請願の配布用データを生成して `data/` に保存する。

引数:
    - sessions: 対象の国会回次。省略時は保存済み一覧 JSON を全件処理する
    - --house: 対象院。`shugiin` `sangiin` `all` から選ぶ。既定値は `all`

入力:
    - tmp/seigan/{house}/list/{session}.json
    - tmp/seigan/{house}/detail/{petition_id}/index.json

出力:
    - data/seigan/{house}/list/{session}.json
    - data/seigan/{house}/detail/{petition_id}.json

主な内容:
    - 回次ごとの請願一覧
    - 請願個票
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
    DistributedSeiganDetailDataset,
    DistributedSeiganListDataset,
    SeiganDetailDataset,
    SeiganListDataset,
)

HOUSE_CHOICES = ("shugiin", "sangiin")
INPUT_ROOT = Path("tmp/seigan")
OUTPUT_ROOT = Path("data/seigan")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="請願の配布用データを生成する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は全件")
    parser.add_argument("--house", choices=(*HOUSE_CHOICES, "all"), default="all", help="対象院。既定値は all")
    return parser.parse_args()


def selected_houses(house: str) -> list[str]:
    """対象院の一覧を返す。"""

    return list(HOUSE_CHOICES) if house == "all" else [house]


def discover_sessions(house: str, input_root: Path = INPUT_ROOT) -> list[int]:
    """保存済み一覧 JSON から処理対象回次を列挙する。"""

    sessions: list[int] = []
    for path in sorted((input_root / house / "list").glob("*.json")):
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


def process_house_sessions(house: str, sessions: list[int], input_root: Path = INPUT_ROOT, output_root: Path = OUTPUT_ROOT) -> None:
    """対象院・対象回次の一覧と個票を `data/` に保存する。"""

    built_at = datetime.now(timezone.utc)
    target_sessions = set(sessions)
    for session in sessions:
        list_path = input_root / house / "list" / f"{session}.json"
        if not list_path.exists():
            continue
        list_dataset = SeiganListDataset.model_validate_json(list_path.read_text(encoding="utf-8"))
        distributed_list = DistributedSeiganListDataset(
            house=house,
            session_number=session,
            built_at=built_at,
            items=list_dataset.items,
        )
        save_json(output_root / house / "list" / f"{session}.json", distributed_list.model_dump(mode="json"))

    detail_dir = input_root / house / "detail"
    if not detail_dir.exists():
        return
    for path in sorted(detail_dir.glob("*/index.json")):
        detail = SeiganDetailDataset.model_validate_json(path.read_text(encoding="utf-8"))
        if detail.session_number not in target_sessions:
            continue
        distributed_detail = DistributedSeiganDetailDataset(
            petition_id=detail.petition_id,
            house=house,
            session_number=detail.session_number,
            petition_number=detail.petition_number,
            title=detail.title,
            committee_name=detail.committee_name,
            committee_code=detail.committee_code,
            detail_source_url=detail.detail_source_url,
            similar_petitions_source_url=detail.similar_petitions_source_url,
            summary_text=detail.summary_text,
            accepted_count=detail.accepted_count,
            signer_count=detail.signer_count,
            outcome=detail.outcome,
            presenters=detail.presenters,
            built_at=built_at,
        )
        save_json(output_root / house / "detail" / f"{detail.petition_id}.json", distributed_detail.model_dump(mode="json"))


def main() -> None:
    """請願の配布用データを生成する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    for house in selected_houses(args.house):
        sessions = sorted(set(args.sessions or discover_sessions(house)))
        if sessions:
            process_house_sessions(house=house, sessions=sessions)


if __name__ == "__main__":
    main()
