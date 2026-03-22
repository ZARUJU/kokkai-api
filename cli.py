"""国会データの更新対象判定、取得、配布生成、後片付けをまとめて実行する CLI。

引数:
    - sessions: 対象の国会回次。省略時は会期一覧から最新回次を選ぶ
    - --all: 会期一覧にある全回次を対象にする
    - --latest-count: 引数省略時に処理する最新回次数
    - --force: 取得済み raw データや配布データがあっても再取得・再生成する
    - --parse-only: 取得済み raw / 中間データだけを使って再パースと配布用 JSON 更新を行う
    - --cleanup-tmp: 配布用データ生成後に不要な `tmp/` の中間生成物を削除する

入力:
    - 衆議院 会期一覧ページ
    - 衆議院 議案一覧・進捗・本文ページ
    - 衆参両院 請願一覧・個別ページ
    - 衆参両院 質問主意書一覧・個別ページ
    - 国会会議録検索システム API
    - 既存の `data/` と `tmp/`

出力:
    - `data/kaiki.json`
    - `data/gian/**`
    - `data/kaigiroku/**`
    - `data/seigan/**`
    - `data/shitsumon/**`
    - `data/people/**`
    - 必要に応じて `tmp/**`
"""

from __future__ import annotations

import argparse
import logging
import shutil
from dataclasses import dataclass
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
TMP_ROOT = Path("tmp")
GIAN_TMP_ROOT = TMP_ROOT / "gian"
KAIGIROKU_TMP_ROOT = TMP_ROOT / "kaigiroku"
SEIGAN_TMP_ROOT = TMP_ROOT / "seigan"
SHITSUMON_TMP_ROOT = TMP_ROOT / "shitsumon"
DATA_ROOT = Path("data")
GIAN_DATA_ROOT = DATA_ROOT / "gian"
KAIGIROKU_DATA_ROOT = DATA_ROOT / "kaigiroku"
SEIGAN_DATA_ROOT = DATA_ROOT / "seigan"
SHITSUMON_DATA_ROOT = DATA_ROOT / "shitsumon"
logger = logging.getLogger(__name__)

PipelineRunner = Callable[[int, bool, bool], None]


@dataclass(frozen=True)
class PipelineFailure:
    """失敗したパイプラインを識別する情報。"""

    pipeline_name: str
    session: int


PIPELINE_TO_DATASET: dict[str, tuple[str, str | None]] = {
    "gian": ("gian", None),
    "kaigiroku": ("kaigiroku", None),
    "shugiin_seigan": ("seigan", "shugiin"),
    "sangiin_seigan": ("seigan", "sangiin"),
    "shugiin_shitsumon": ("shitsumon", "shugiin"),
    "sangiin_shitsumon": ("shitsumon", "sangiin"),
}


def parse_args() -> argparse.Namespace:
    """CLI 引数を解釈する。"""

    parser = argparse.ArgumentParser(description="国会データ更新パイプラインを一括実行する")
    parser.add_argument("sessions", nargs="*", type=int, help="対象の国会回次。省略時は最新回次を対象にする")
    parser.add_argument(
        "--all",
        action="store_true",
        help="会期一覧にある全回次を対象にする",
    )
    parser.add_argument(
        "--latest-count",
        type=int,
        default=DEFAULT_LATEST_COUNT,
        help="引数省略時に処理する最新回次数。既定値は 2",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="取得済み raw データや配布データがあっても再取得・再生成する",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="取得済み raw / 中間データから再パースと配布用 JSON 更新のみを行う",
    )
    parser.add_argument(
        "--cleanup-tmp",
        action="store_true",
        help="配布用データ生成後に、対象回次の `tmp/` 中間生成物を削除する",
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
    """対象回次と強制更新有無を決める。"""

    if args.sessions:
        return list(dict.fromkeys(args.sessions)), args.force

    if args.all:
        sessions = sorted({item.number for item in kaiki_dataset.items}, reverse=True)
        return sessions, args.force

    latest_count = max(1, args.latest_count)
    sessions = sorted({item.number for item in kaiki_dataset.items}, reverse=True)[:latest_count]
    return sessions, True


def is_http_not_found(error: requests.HTTPError) -> bool:
    """HTTP 404 かどうかを返す。"""

    response = error.response
    return response is not None and response.status_code == 404


def distribution_path(dataset_name: str, session: int, house: str | None = None) -> Path:
    """データ種別ごとの配布用一覧 JSON パスを返す。"""

    if dataset_name == "gian":
        return GIAN_DATA_ROOT / "list" / f"{session}.json"
    if dataset_name == "kaigiroku":
        return KAIGIROKU_DATA_ROOT / "list" / f"{session}.json"
    if dataset_name == "seigan":
        if house is None:
            raise ValueError("請願の配布パスには house が必要です。")
        return SEIGAN_DATA_ROOT / house / "list" / f"{session}.json"
    if dataset_name == "shitsumon":
        if house is None:
            raise ValueError("質問主意書の配布パスには house が必要です。")
        return SHITSUMON_DATA_ROOT / house / "list" / f"{session}.json"
    raise ValueError(f"未対応のデータ種別です: {dataset_name}")


def has_distribution_output(dataset_name: str, session: int, house: str | None = None) -> bool:
    """対象回次の配布用一覧 JSON が既にあるかを返す。"""

    return distribution_path(dataset_name, session=session, house=house).exists()


def should_skip_dataset(dataset_name: str, session: int, skip_existing: bool, parse_only: bool, house: str | None = None) -> bool:
    """配布済みデータを基準に対象回次の更新を省略するか判定する。"""

    return skip_existing and not parse_only and has_distribution_output(dataset_name, session=session, house=house)


def run_gian_pipeline(session: int, skip_existing: bool, parse_only: bool = False) -> None:
    """議案パイプラインを1回次分実行する。"""

    logger.info("議案処理開始: session=%s skip_existing=%s parse_only=%s", session, skip_existing, parse_only)
    if should_skip_dataset("gian", session=session, skip_existing=skip_existing, parse_only=parse_only):
        logger.info("議案処理スキップ: 配布用データが既に存在 session=%s", session)
        return
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
    if should_skip_dataset("shitsumon", session=session, house="shugiin", skip_existing=skip_existing, parse_only=parse_only):
        logger.info("衆議院質問主意書処理スキップ: 配布用データが既に存在 session=%s", session)
        return
    if parse_only and not (SHITSUMON_TMP_ROOT / "shugiin" / "list" / f"{session}.html").exists():
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
    if should_skip_dataset("seigan", session=session, house="shugiin", skip_existing=skip_existing, parse_only=parse_only):
        logger.info("衆議院請願処理スキップ: 配布用データが既に存在 session=%s", session)
        return
    if parse_only and not (SEIGAN_TMP_ROOT / "shugiin" / "list" / f"{session}.html").exists():
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
    if should_skip_dataset("seigan", session=session, house="sangiin", skip_existing=skip_existing, parse_only=parse_only):
        logger.info("参議院請願処理スキップ: 配布用データが既に存在 session=%s", session)
        return
    if parse_only and not (SEIGAN_TMP_ROOT / "sangiin" / "list" / f"{session}.html").exists():
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
    if should_skip_dataset("shitsumon", session=session, house="sangiin", skip_existing=skip_existing, parse_only=parse_only):
        logger.info("参議院質問主意書処理スキップ: 配布用データが既に存在 session=%s", session)
        return
    if parse_only and not (SHITSUMON_TMP_ROOT / "sangiin" / "list" / f"{session}.html").exists():
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
    if should_skip_dataset("kaigiroku", session=session, skip_existing=skip_existing, parse_only=parse_only):
        logger.info("会議録処理スキップ: 配布用データが既に存在 session=%s", session)
        return
    if parse_only and not (KAIGIROKU_TMP_ROOT / "meeting" / f"{session}.json").exists():
        logger.warning("会議録raw JSONがないため parse-only をスキップ: session=%s", session)
        return
    if not parse_only:
        get_meeting_records.process_session(session, skip_existing=skip_existing)
    parse_meeting_records.process_session(session, skip_existing=skip_existing)
    logger.info("会議録処理完了: session=%s", session)


def run_distribution_builders(
    sessions: list[int],
    skip_existing: bool = False,
    blocked_targets: set[tuple[str, int, str | None]] | None = None,
    skip_people_index: bool = False,
) -> None:
    """配布用データを更新する。"""

    normalized_sessions = sorted(set(sessions))
    blocked_targets = blocked_targets or set()
    logger.info("配布データ生成開始: sessions=%s", normalized_sessions)

    gian_sessions = [
        session
        for session in normalized_sessions
        if (GIAN_TMP_ROOT / "list" / f"{session}.json").exists()
        and ("gian", session, None) not in blocked_targets
        and not (skip_existing and has_distribution_output("gian", session=session))
    ]
    if gian_sessions:
        build_gian_distribution.process_sessions(gian_sessions)
    else:
        logger.warning("議案の配布データ生成対象がないためスキップ: sessions=%s", normalized_sessions)

    kaigiroku_sessions = [
        session
        for session in normalized_sessions
        if (KAIGIROKU_TMP_ROOT / "parsed" / f"{session}.json").exists()
        and ("kaigiroku", session, None) not in blocked_targets
        and not (skip_existing and has_distribution_output("kaigiroku", session=session))
    ]
    if kaigiroku_sessions:
        build_kaigiroku_distribution.process_sessions(kaigiroku_sessions)
    else:
        logger.warning("会議録の配布データ生成対象がないためスキップ: sessions=%s", normalized_sessions)

    for house in build_seigan_distribution.HOUSE_CHOICES:
        house_sessions = [
            session
            for session in normalized_sessions
            if (SEIGAN_TMP_ROOT / house / "list" / f"{session}.json").exists()
            and ("seigan", session, house) not in blocked_targets
            and not (skip_existing and has_distribution_output("seigan", session=session, house=house))
        ]
        if not house_sessions:
            logger.warning("請願の配布データ生成対象がないためスキップ: house=%s sessions=%s", house, normalized_sessions)
            continue
        build_seigan_distribution.process_house_sessions(house=house, sessions=house_sessions)

    for house in build_shitsumon_distribution.HOUSE_CHOICES:
        house_sessions = [
            session
            for session in normalized_sessions
            if (SHITSUMON_TMP_ROOT / house / "list" / f"{session}.json").exists()
            and ("shitsumon", session, house) not in blocked_targets
            and not (skip_existing and has_distribution_output("shitsumon", session=session, house=house))
        ]
        if not house_sessions:
            logger.warning("質問主意書の配布データ生成対象がないためスキップ: house=%s sessions=%s", house, normalized_sessions)
            continue
        build_shitsumon_distribution.process_house_sessions(house=house, sessions=house_sessions)

    if skip_people_index:
        logger.warning("上流パイプラインに失敗があるため人物索引生成をスキップします")
    else:
        build_people_index.process()
    logger.info("配布データ生成完了: sessions=%s", normalized_sessions)


def run_pipeline_with_error_logging(
    pipeline_name: str,
    runner: PipelineRunner,
    session: int,
    skip_existing: bool,
    parse_only: bool,
) -> PipelineFailure | None:
    """個別パイプライン失敗時にログを残して続行する。"""

    try:
        runner(session=session, skip_existing=skip_existing, parse_only=parse_only)
    except Exception:
        logger.exception("パイプライン失敗。処理を続行します: pipeline=%s session=%s", pipeline_name, session)
        return PipelineFailure(pipeline_name=pipeline_name, session=session)
    return None


def build_blocked_targets(failures: list[PipelineFailure]) -> set[tuple[str, int, str | None]]:
    """失敗したパイプラインに対応する配布生成対象を返す。"""

    blocked_targets: set[tuple[str, int, str | None]] = set()
    for failure in failures:
        dataset_name, house = PIPELINE_TO_DATASET[failure.pipeline_name]
        blocked_targets.add((dataset_name, failure.session, house))
    return blocked_targets


def format_failure_summary(failures: list[PipelineFailure]) -> str:
    """失敗したパイプライン一覧を終了メッセージ向けに整形する。"""

    joined = ", ".join(f"{failure.pipeline_name}:{failure.session}" for failure in failures)
    return f"一部の更新に失敗しました。ログを確認してください: {joined}"


def remove_file_if_exists(path: Path) -> None:
    """存在するファイルだけを削除する。"""

    if path.exists():
        path.unlink()


def remove_dir_if_exists(path: Path) -> None:
    """存在するディレクトリだけを削除する。"""

    if path.exists():
        shutil.rmtree(path)


def cleanup_gian_tmp(session: int) -> None:
    """対象回次の議案中間生成物を削除する。"""

    if not has_distribution_output("gian", session=session):
        return
    remove_file_if_exists(GIAN_TMP_ROOT / "list" / f"{session}.html")
    remove_file_if_exists(GIAN_TMP_ROOT / "list" / f"{session}.json")
    for detail_dir in sorted((GIAN_TMP_ROOT / "detail").glob(f"{session}-*")):
        remove_dir_if_exists(detail_dir)


def cleanup_kaigiroku_tmp(session: int) -> None:
    """対象回次の会議録中間生成物を削除する。"""

    if not has_distribution_output("kaigiroku", session=session):
        return
    remove_file_if_exists(KAIGIROKU_TMP_ROOT / "meeting" / f"{session}.json")
    remove_file_if_exists(KAIGIROKU_TMP_ROOT / "parsed" / f"{session}.json")


def cleanup_house_tmp(root: Path, dataset_name: str, house: str, session: int) -> None:
    """請願・質問主意書の対象院・対象回次の中間生成物を削除する。"""

    if not has_distribution_output(dataset_name, session=session, house=house):
        return
    remove_file_if_exists(root / house / "list" / f"{session}.html")
    remove_file_if_exists(root / house / "list" / f"{session}.json")
    for detail_dir in sorted((root / house / "detail").glob(f"*-{session}-*")):
        remove_dir_if_exists(detail_dir)


def cleanup_tmp_artifacts(sessions: list[int]) -> None:
    """配布用データ生成済みの対象回次について `tmp/` を掃除する。"""

    normalized_sessions = sorted(set(sessions))
    logger.info("tmp 掃除開始: sessions=%s", normalized_sessions)
    for session in normalized_sessions:
        cleanup_gian_tmp(session)
        cleanup_kaigiroku_tmp(session)
        cleanup_house_tmp(SEIGAN_TMP_ROOT, "seigan", "shugiin", session)
        cleanup_house_tmp(SEIGAN_TMP_ROOT, "seigan", "sangiin", session)
        cleanup_house_tmp(SHITSUMON_TMP_ROOT, "shitsumon", "shugiin", session)
        cleanup_house_tmp(SHITSUMON_TMP_ROOT, "shitsumon", "sangiin", session)
    logger.info("tmp 掃除完了: sessions=%s", normalized_sessions)


def main() -> None:
    """国会データ一括更新 CLI のエントリーポイント。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if args.sessions and args.all:
        raise SystemExit("`sessions` と `--all` は同時に指定できません。")
    if args.latest_count < 1:
        raise SystemExit("`--latest-count` には 1 以上を指定してください。")

    if args.sessions:
        sessions = list(dict.fromkeys(args.sessions))
        force = args.force
    else:
        kaiki_dataset = load_or_fetch_kaiki(force=not args.parse_only)
        sessions, force = select_sessions(args, kaiki_dataset)

    skip_existing = not force
    if args.parse_only:
        skip_existing = True

    logger.info(
        "対象回次: sessions=%s force=%s parse_only=%s cleanup_tmp=%s",
        sessions,
        force,
        args.parse_only,
        args.cleanup_tmp,
    )
    failures: list[PipelineFailure] = []
    for session in sessions:
        failure = run_pipeline_with_error_logging(
            pipeline_name="gian",
            runner=run_gian_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)
        failure = run_pipeline_with_error_logging(
            pipeline_name="kaigiroku",
            runner=run_kaigiroku_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)
        failure = run_pipeline_with_error_logging(
            pipeline_name="shugiin_seigan",
            runner=run_shugiin_seigan_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)
        failure = run_pipeline_with_error_logging(
            pipeline_name="sangiin_seigan",
            runner=run_sangiin_seigan_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)
        failure = run_pipeline_with_error_logging(
            pipeline_name="shugiin_shitsumon",
            runner=run_shugiin_shitsumon_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)
        failure = run_pipeline_with_error_logging(
            pipeline_name="sangiin_shitsumon",
            runner=run_sangiin_shitsumon_pipeline,
            session=session,
            skip_existing=skip_existing,
            parse_only=args.parse_only,
        )
        if failure is not None:
            failures.append(failure)

    distribution_skip_existing = skip_existing and not args.parse_only
    run_distribution_builders(
        sessions,
        skip_existing=distribution_skip_existing,
        blocked_targets=build_blocked_targets(failures),
        skip_people_index=bool(failures),
    )
    if args.cleanup_tmp:
        cleanup_tmp_artifacts(sessions)
    if failures:
        raise SystemExit(format_failure_summary(failures))


if __name__ == "__main__":
    main()
