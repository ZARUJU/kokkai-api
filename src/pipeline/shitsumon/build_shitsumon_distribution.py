"""質問主意書の配布一歩手前データを生成して `tmp/ready/` に保存する。

引数:
    - sessions: 対象の国会回次。省略時は保存済み一覧 JSON を全件処理する
    - --house: 対象院。`shugiin` `sangiin` `all` から選ぶ。既定値は `all`

入力:
    - tmp/shitsumon/{house}/list/{session}.json
    - tmp/shitsumon/{house}/detail/{question_id}/index.json

出力:
    - tmp/ready/shitsumon/{house}/list/{session}.json
    - tmp/ready/shitsumon/{house}/detail/{question_id}.json

主な内容:
    - 回次ごとの質問主意書一覧
    - 質問主意書個票
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    SangiinShitsumonDetailDataset,
    SangiinShitsumonListDataset,
    ShugiinShitsumonDetailDataset,
    ShugiinShitsumonListDataset,
)

HOUSE_CHOICES = ("shugiin", "sangiin")
INPUT_ROOT = Path("tmp/shitsumon")
OUTPUT_ROOT = Path("tmp/ready/shitsumon")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を受け取る。"""

    parser = argparse.ArgumentParser(description="質問主意書の配布一歩手前データを生成する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は全件")
    parser.add_argument(
        "--house",
        choices=(*HOUSE_CHOICES, "all"),
        default="all",
        help="対象院。既定値は all",
    )
    return parser.parse_args()


def selected_houses(house: str) -> list[str]:
    """対象院の一覧を返す。"""

    if house == "all":
        return list(HOUSE_CHOICES)
    return [house]


def discover_sessions(house: str, input_root: Path = INPUT_ROOT) -> list[int]:
    """保存済み一覧 JSON から処理対象回次を列挙する。"""

    sessions: list[int] = []
    for path in sorted((input_root / house / "list").glob("*.json")):
        try:
            sessions.append(int(path.stem))
        except ValueError:
            continue
    return sessions


def validate_list_json(house: str, path: Path) -> dict:
    """一覧 JSON を読み込んでモデル検証し、辞書に戻す。"""

    text = path.read_text(encoding="utf-8")
    if house == "shugiin":
        return ShugiinShitsumonListDataset.model_validate_json(text).model_dump(mode="json")
    return SangiinShitsumonListDataset.model_validate_json(text).model_dump(mode="json")


def validate_detail_json(house: str, path: Path) -> dict:
    """個票 JSON を読み込んでモデル検証し、辞書に戻す。"""

    text = path.read_text(encoding="utf-8")
    if house == "shugiin":
        return ShugiinShitsumonDetailDataset.model_validate_json(text).model_dump(mode="json")
    return SangiinShitsumonDetailDataset.model_validate_json(text).model_dump(mode="json")


def save_json(path: Path, payload: dict) -> Path:
    """JSON を UTF-8 インデント付きで保存する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def process_house_sessions(house: str, sessions: list[int], input_root: Path = INPUT_ROOT, output_root: Path = OUTPUT_ROOT) -> None:
    """対象院・対象回次の一覧と個票を `tmp/ready` に保存する。"""

    logger.info("質問主意書配布データ生成開始: house=%s sessions=%s", house, sessions)
    for session in sessions:
        list_path = input_root / house / "list" / f"{session}.json"
        if not list_path.exists():
            logger.info("一覧JSONが見つからないためスキップ: house=%s session=%s", house, session)
            continue
        payload = validate_list_json(house=house, path=list_path)
        output_path = output_root / house / "list" / f"{session}.json"
        save_json(output_path, payload)
        logger.info("一覧保存: house=%s session=%s path=%s", house, session, output_path)

    detail_dir = input_root / house / "detail"
    if detail_dir.exists():
        for path in sorted(detail_dir.glob("*/index.json")):
            payload = validate_detail_json(house=house, path=path)
            question_id = path.parent.name
            output_path = output_root / house / "detail" / f"{question_id}.json"
            save_json(output_path, payload)
            logger.info("個票保存: house=%s question_id=%s path=%s", house, question_id, output_path)

    logger.info("質問主意書配布データ生成完了: house=%s", house)


def main() -> None:
    """質問主意書の配布一歩手前データを生成する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    for house in selected_houses(args.house):
        sessions = sorted(set(args.sessions or discover_sessions(house)))
        if not sessions:
            logger.info("対象回次が見つからないためスキップ: house=%s", house)
            continue
        process_house_sessions(house=house, sessions=sessions)


if __name__ == "__main__":
    main()
