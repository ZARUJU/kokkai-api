"""国会データの取得から配布用 JSON 生成までをまとめて実行する CLI。

引数:
    - sessions: 対象の国会回次。省略時は会期一覧から最新2回分を選ぶ
    - --all: 会期一覧にある全回次を対象にする
    - --force: 取得済み raw データがあっても再取得する
    - --parse-only: 取得済み raw / 中間データだけを使って再パースと配布用 JSON 更新を行う

入力:
    - 衆議院 会期一覧ページ
    - 衆議院 議案一覧・進捗・本文ページ
    - 衆参両院 請願一覧・個別ページ
    - 衆参両院 質問主意書一覧・個別ページ
    - 既存の `data/kaiki.json`（`--force` なしで存在する場合）

出力:
    - `data/kaiki.json`
    - `tmp/gian/**`
    - `tmp/kaigiroku/**`
    - `tmp/seigan/**`
    - `tmp/shitsumon/**`
    - `data/gian/**`
    - `data/kaigiroku/**`
    - `data/seigan/**`
    - `data/shitsumon/**`
    - `data/people/index.json`

主な内容:
    - 最新回次の自動判定
    - 取得系パイプラインの `--skip-existing` 相当制御
    - 議案・請願・質問主意書データの統合実行
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable

import requests

from src.models import KaikiDataset
from src.pipeline.gian import build_gian_distribution
from src.pipeline.gian import get_gian_list, get_gian_progress, get_gian_text
from src.pipeline.gian import parse_gian_list, parse_gian_progress, parse_gian_text
from src.pipeline.kaigiroku import build_kaigiroku_distribution
from src.pipeline.kaigiroku import get_meeting_records, parse_meeting_records
from src.pipeline.kaiki import get_kaiki
from src.pipeline.people import build_people_index
from src.pipeline.seigan import build_seigan_distribution
from src.pipeline.seigan import get_sangiin_seigan_detail, get_sangiin_seigan_list
from src.pipeline.seigan import get_shugiin_seigan_detail, get_shugiin_seigan_list
from src.pipeline.seigan import parse_sangiin_seigan_detail, parse_sangiin_seigan_list
from src.pipeline.seigan import parse_shugiin_seigan_detail, parse_shugiin_seigan_list
from src.pipeline.shitsumon import build_shitsumon_distribution
from src.pipeline.shitsumon import get_sangiin_shitsumon_detail, get_sangiin_shitsumon_list
from src.pipeline.shitsumon import get_shugiin_shitsumon_detail, get_shugiin_shitsumon_list
from src.pipeline.shitsumon import parse_sangiin_shitsumon_detail, parse_sangiin_shitsumon_list
from src.pipeline.shitsumon import parse_shugiin_shitsumon_detail, parse_shugiin_shitsumon_list

DEFAULT_LATEST_COUNT = 2
KAIKI_PATH = Path("data/kaiki.json")
GIAN_LIST_JSON_DIR = Path("tmp/gian/list")
KAIGIROKU_MEETING_DIR = Path("tmp/kaigiroku/meeting")
KAIGIROKU_PARSED_DIR = Path("tmp/kaigiroku/parsed")
SHUGIIN_SHITSUMON_LIST_HTML_DIR = Path("tmp/shitsumon/shugiin/list")
SANGIIN_SHITSUMON_LIST_HTML_DIR = Path("tmp/shitsumon/sangiin/list")
SHUGIIN_SEIGAN_LIST_HTML_DIR = Path("tmp/seigan/shugiin/list")
SANGIIN_SEIGAN_LIST_HTML_DIR = Path("tmp/seigan/sangiin/list")
logger = logging.getLogger(__name__)

PipelineRunner = Callable[[int, bool, bool], None]


def parse_args() -> argparse.Namespace:
    """CLI 引数を解釈する。"""

    parser = argparse.ArgumentParser(description="国会データ取得パイプラインを一括実行する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は最新2回分")
    parser.add_argument(
        "--all",
        action="store_true",
        help="会期一覧にある全回次を対象にする",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="取得済み raw データがあっても再取得する。引数なし時は自動で有効",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="取得済み raw / 中間データから再パースと配布用 JSON 更新のみを行う",
    )
    return parser.parse_args()


def load_or_fetch_kaiki(force: bool) -> KaikiDataset:
    """会期一覧を取得または既存 JSON から読み込む。"""

    if KAIKI_PATH.exists() and not force:
        logger.info("会期一覧は既存 JSON を再利用: path=%s", KAIKI_PATH)
        return KaikiDataset.model_validate_json(KAIKI_PATH.read_text(encoding="utf-8"))

    logger.info("会期一覧更新開始: force=%s", force)
    html = get_kaiki.fetch_html()
    dataset = get_kaiki.build_dataset(html)
    get_kaiki.save_dataset(dataset)
    logger.info("会期一覧更新完了: path=%s items=%s", KAIKI_PATH, len(dataset.items))
    return dataset


def select_sessions(args: argparse.Namespace, kaiki_dataset: KaikiDataset) -> tuple[list[int], bool]:
    """対象回次と取得の強制更新有無を決める。"""

    if args.sessions:
        sessions = list(dict.fromkeys(args.sessions))
        force = args.force
        return sessions, force

    if args.all:
        all_sessions = sorted({item.number for item in kaiki_dataset.items}, reverse=True)
        return all_sessions, args.force

    latest_sessions = sorted({item.number for item in kaiki_dataset.items}, reverse=True)[:DEFAULT_LATEST_COUNT]
    return latest_sessions, True


def is_http_not_found(error: requests.HTTPError) -> bool:
    """HTTP 404 かどうかを返す。"""

    response = error.response
    return response is not None and response.status_code == 404


def run_gian_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """議案パイプラインを1回次分実行する。"""

    logger.info("議案処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if not parse_only:
        get_gian_list.process_session(session, skip_existing=skip_existing)
    parse_gian_list.process_session(session)
    if not parse_only:
        get_gian_progress.process_session(session, skip_existing=skip_existing)
    parse_gian_progress.process_session(session)
    if not parse_only:
        get_gian_text.process_session(session, skip_existing=skip_existing)
    parse_gian_text.process_session(session)
    logger.info("議案処理完了: session=%s", session)


def run_shugiin_shitsumon_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """衆議院質問主意書パイプラインを1回次分実行する。"""

    logger.info("衆議院質問主意書処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if parse_only and not (SHUGIIN_SHITSUMON_LIST_HTML_DIR / f"{session}.html").exists():
        logger.warning("衆議院質問主意書一覧HTMLがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        get_shugiin_shitsumon_list.process_session(session, skip_existing=skip_existing)
    parse_shugiin_shitsumon_list.process_session(session)
    if not parse_only:
        get_shugiin_shitsumon_detail.process_session(session, skip_existing=skip_existing)
    parse_shugiin_shitsumon_detail.process_session(session)
    logger.info("衆議院質問主意書処理完了: session=%s", session)


def run_shugiin_seigan_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """衆議院請願パイプラインを1回次分実行する。"""

    logger.info("衆議院請願処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if parse_only and not (SHUGIIN_SEIGAN_LIST_HTML_DIR / f"{session}.html").exists():
        logger.warning("衆議院請願一覧HTMLがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        try:
            get_shugiin_seigan_list.process_session(session, skip_existing=skip_existing)
        except requests.HTTPError as exc:
            if is_http_not_found(exc):
                logger.warning("衆議院請願一覧が未公開のためスキップ: session=%s", session)
                return
            raise
    parse_shugiin_seigan_list.process_session(session)
    if not parse_only:
        get_shugiin_seigan_detail.process_session(session, skip_existing=skip_existing)
    parse_shugiin_seigan_detail.process_session(session)
    logger.info("衆議院請願処理完了: session=%s", session)


def run_sangiin_seigan_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """参議院請願パイプラインを1回次分実行する。"""

    logger.info("参議院請願処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if parse_only and not (SANGIIN_SEIGAN_LIST_HTML_DIR / f"{session}.html").exists():
        logger.warning("参議院請願一覧HTMLがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        try:
            get_sangiin_seigan_list.process_session(session, skip_existing=skip_existing)
        except requests.HTTPError as exc:
            if is_http_not_found(exc):
                logger.warning("参議院請願一覧が未公開のためスキップ: session=%s", session)
                return
            raise
    parse_sangiin_seigan_list.process_session(session)
    if not parse_only:
        get_sangiin_seigan_detail.process_session(session, skip_existing=skip_existing)
    parse_sangiin_seigan_detail.process_session(session)
    logger.info("参議院請願処理完了: session=%s", session)


def run_sangiin_shitsumon_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """参議院質問主意書パイプラインを1回次分実行する。"""

    logger.info("参議院質問主意書処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if parse_only and not (SANGIIN_SHITSUMON_LIST_HTML_DIR / f"{session}.html").exists():
        logger.warning("参議院質問主意書一覧HTMLがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        try:
            get_sangiin_shitsumon_list.process_session(session, skip_existing=skip_existing)
        except requests.HTTPError as exc:
            if is_http_not_found(exc):
                logger.warning("参議院質問主意書一覧が未公開のためスキップ: session=%s", session)
                return
            raise
    parse_sangiin_shitsumon_list.process_session(session)
    if not parse_only:
        get_sangiin_shitsumon_detail.process_session(session, skip_existing=skip_existing)
    parse_sangiin_shitsumon_detail.process_session(session)
    logger.info("参議院質問主意書処理完了: session=%s", session)


def run_kaigiroku_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """会議録 API パイプラインを1回次分実行する。"""

    logger.info("会議録処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if parse_only and not (KAIGIROKU_MEETING_DIR / f"{session}.json").exists():
        logger.warning("会議録raw JSONがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        get_meeting_records.process_session(session, skip_existing=skip_existing)
    parse_meeting_records.process_session(session, skip_existing=skip_existing)
    logger.info("会議録処理完了: session=%s", session)


def run_distribution_builders(sessions: list[int]) -> None:
    """配布用データを更新する。"""

    normalized_sessions = sorted(set(sessions))
    logger.info("配布データ生成開始: sessions=%s", normalized_sessions)

    gian_sessions = [session for session in normalized_sessions if (GIAN_LIST_JSON_DIR / f"{session}.json").exists()]
    if gian_sessions:
        build_gian_distribution.process_sessions(gian_sessions)
    else:
        logger.warning("議案の配布データ生成対象がないためスキップ: sessions=%s", normalized_sessions)

    kaigiroku_sessions = [session for session in normalized_sessions if (KAIGIROKU_PARSED_DIR / f"{session}.json").exists()]
    if kaigiroku_sessions:
        build_kaigiroku_distribution.process_sessions(kaigiroku_sessions)
    else:
        logger.warning("会議録の配布データ生成対象がないためスキップ: sessions=%s", normalized_sessions)

    for house in build_seigan_distribution.HOUSE_CHOICES:
        house_sessions = [
            session
            for session in normalized_sessions
            if (Path("tmp/seigan") / house / "list" / f"{session}.json").exists()
        ]
        if not house_sessions:
            logger.warning("請願の配布データ生成対象がないためスキップ: house=%s sessions=%s", house, normalized_sessions)
            continue
        build_seigan_distribution.process_house_sessions(house=house, sessions=house_sessions)
    for house in build_shitsumon_distribution.HOUSE_CHOICES:
        house_sessions = [
            session
            for session in normalized_sessions
            if (Path("tmp/shitsumon") / house / "list" / f"{session}.json").exists()
        ]
        if not house_sessions:
            logger.warning("質問主意書の配布データ生成対象がないためスキップ: house=%s sessions=%s", house, normalized_sessions)
            continue
        build_shitsumon_distribution.process_house_sessions(house=house, sessions=house_sessions)
    build_people_index.process()
    logger.info("配布データ生成完了: sessions=%s", normalized_sessions)


def run_pipeline_with_error_logging(
    pipeline_name: str,
    runner: PipelineRunner,
    session: int,
    skip_existing: bool,
    parse_only: bool,
) -> None:
    """個別パイプライン失敗時にログを残して続行する。"""

    try:
        runner(session=session, skip_existing=skip_existing, parse_only=parse_only)
    except Exception:
        logger.exception("パイプライン失敗。処理を続行します: pipeline=%s session=%s", pipeline_name, session)


def main() -> None:
    """国会データ一括更新 CLI のエントリーポイント。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if args.sessions and args.all:
        raise SystemExit("`sessions` と `--all` は同時に指定できません。")
    if args.sessions:
        sessions = list(dict.fromkeys(args.sessions))
        force = args.force
    else:
        kaiki_dataset = load_or_fetch_kaiki(force=not args.parse_only)
        sessions, force = select_sessions(args, kaiki_dataset)
    skip_existing = not force
    if args.parse_only:
        skip_existing = True

    logger.info("対象回次: sessions=%s force=%s parse_only=%s", sessions, force, args.parse_only)
    for session in sessions:
        run_pipeline_with_error_logging(
            pipeline_name="gian",
            runner=run_gian_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        run_pipeline_with_error_logging(
            pipeline_name="kaigiroku",
            runner=run_kaigiroku_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        run_pipeline_with_error_logging(
            pipeline_name="shugiin_seigan",
            runner=run_shugiin_seigan_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        run_pipeline_with_error_logging(
            pipeline_name="sangiin_seigan",
            runner=run_sangiin_seigan_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        run_pipeline_with_error_logging(
            pipeline_name="shugiin_shitsumon",
            runner=run_shugiin_shitsumon_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        run_pipeline_with_error_logging(
            pipeline_name="sangiin_shitsumon",
            runner=run_sangiin_shitsumon_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )

    run_distribution_builders(sessions)


if __name__ == "__main__":
    main()
