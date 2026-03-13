"""国会データの取得から配布用 JSON 生成までをまとめて実行する CLI。

引数:
    - sessions: 対象の国会回次。省略時は会期一覧から最新2回分を選ぶ
    - --force: 取得済み raw データがあっても再取得する

入力:
    - 衆議院 会期一覧ページ
    - 衆議院 議案一覧・進捗・本文ページ
    - 衆参両院 質問主意書一覧・個別ページ
    - 既存の `data/kaiki.json`（`--force` なしで存在する場合）

出力:
    - `data/kaiki.json`
    - `tmp/gian/**`
    - `tmp/shitsumon/**`
    - `data/gian/**`
    - `data/shitsumon/**`
    - `data/people/index.json`

主な内容:
    - 最新回次の自動判定
    - 取得系パイプラインの `--skip-existing` 相当制御
    - 議案データと質問主意書データの統合実行
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.models import KaikiDataset
from src.pipeline.gian import build_gian_distribution
from src.pipeline.gian import get_gian_list, get_gian_progress, get_gian_text
from src.pipeline.gian import parse_gian_list, parse_gian_progress, parse_gian_text
from src.pipeline.kaiki import get_kaiki
from src.pipeline.people import build_people_index
from src.pipeline.shitsumon import build_shitsumon_distribution
from src.pipeline.shitsumon import get_sangiin_shitsumon_detail, get_sangiin_shitsumon_list
from src.pipeline.shitsumon import get_shugiin_shitsumon_detail, get_shugiin_shitsumon_list
from src.pipeline.shitsumon import parse_sangiin_shitsumon_detail, parse_sangiin_shitsumon_list
from src.pipeline.shitsumon import parse_shugiin_shitsumon_detail, parse_shugiin_shitsumon_list

DEFAULT_LATEST_COUNT = 2
KAIKI_PATH = Path("data/kaiki.json")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """CLI 引数を解釈する。"""

    parser = argparse.ArgumentParser(description="国会データ取得パイプラインを一括実行する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は最新2回分")
    parser.add_argument(
        "--force",
        action="store_true",
        help="取得済み raw データがあっても再取得する。引数なし時は自動で有効",
    )
    return parser.parse_args()


def load_or_fetch_kaiki(force: bool) -> KaikiDataset:
    """会期一覧を取得または既存 JSON から読み込む。"""

    if force or not KAIKI_PATH.exists():
        logger.info("会期一覧更新開始: force=%s", force)
        html = get_kaiki.fetch_html()
        dataset = get_kaiki.build_dataset(html)
        get_kaiki.save_dataset(dataset)
        logger.info("会期一覧更新完了: path=%s items=%s", KAIKI_PATH, len(dataset.items))
        return dataset

    logger.info("会期一覧は既存 JSON を再利用: path=%s", KAIKI_PATH)
    return KaikiDataset.model_validate_json(KAIKI_PATH.read_text(encoding="utf-8"))


def select_sessions(args: argparse.Namespace, kaiki_dataset: KaikiDataset) -> tuple[list[int], bool]:
    """対象回次と取得の強制更新有無を決める。"""

    if args.sessions:
        sessions = list(dict.fromkeys(args.sessions))
        force = args.force
        return sessions, force

    latest_sessions = sorted({item.number for item in kaiki_dataset.items}, reverse=True)[:DEFAULT_LATEST_COUNT]
    return latest_sessions, True


def run_gian_pipeline(session: int, skip_existing: bool) -> None:
    """議案パイプラインを1回次分実行する。"""

    logger.info("議案処理開始: session=%s skip_existing=%s", session, skip_existing)
    get_gian_list.process_session(session, skip_existing=skip_existing)
    parse_gian_list.process_session(session)
    get_gian_progress.process_session(session, skip_existing=skip_existing)
    parse_gian_progress.process_session(session)
    get_gian_text.process_session(session, skip_existing=skip_existing)
    parse_gian_text.process_session(session)
    logger.info("議案処理完了: session=%s", session)


def run_shugiin_shitsumon_pipeline(session: int, skip_existing: bool) -> None:
    """衆議院質問主意書パイプラインを1回次分実行する。"""

    logger.info("衆議院質問主意書処理開始: session=%s skip_existing=%s", session, skip_existing)
    get_shugiin_shitsumon_list.process_session(session, skip_existing=skip_existing)
    parse_shugiin_shitsumon_list.process_session(session)
    get_shugiin_shitsumon_detail.process_session(session, skip_existing=skip_existing)
    parse_shugiin_shitsumon_detail.process_session(session)
    logger.info("衆議院質問主意書処理完了: session=%s", session)


def run_sangiin_shitsumon_pipeline(session: int, skip_existing: bool) -> None:
    """参議院質問主意書パイプラインを1回次分実行する。"""

    logger.info("参議院質問主意書処理開始: session=%s skip_existing=%s", session, skip_existing)
    get_sangiin_shitsumon_list.process_session(session, skip_existing=skip_existing)
    parse_sangiin_shitsumon_list.process_session(session)
    get_sangiin_shitsumon_detail.process_session(session, skip_existing=skip_existing)
    parse_sangiin_shitsumon_detail.process_session(session)
    logger.info("参議院質問主意書処理完了: session=%s", session)


def run_distribution_builders(sessions: list[int]) -> None:
    """配布用データを更新する。"""

    normalized_sessions = sorted(set(sessions))
    logger.info("配布データ生成開始: sessions=%s", normalized_sessions)
    build_gian_distribution.process_sessions(normalized_sessions)
    for house in build_shitsumon_distribution.HOUSE_CHOICES:
        build_shitsumon_distribution.process_house_sessions(house=house, sessions=normalized_sessions)
    build_people_index.process()
    logger.info("配布データ生成完了: sessions=%s", normalized_sessions)


def main() -> None:
    """国会データ一括更新 CLI のエントリーポイント。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    kaiki_dataset = load_or_fetch_kaiki(force=args.force or not args.sessions)
    sessions, force = select_sessions(args, kaiki_dataset)
    skip_existing = not force

    logger.info("対象回次: sessions=%s force=%s", sessions, force)
    for session in sessions:
        run_gian_pipeline(session=session, skip_existing=skip_existing)
        run_shugiin_shitsumon_pipeline(session=session, skip_existing=skip_existing)
        run_sangiin_shitsumon_pipeline(session=session, skip_existing=skip_existing)

    run_distribution_builders(sessions)


if __name__ == "__main__":
    main()
