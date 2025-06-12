"""qa_shu CLI

- 最新セッションの質問主意書一覧は常に再取得
- 各質問 ID ごとにステータスが **答弁受理** なら
  質問取得・答弁取得・MD クリーンアップ・ステータス取得を全てスキップ
- ステータスファイルは
  data/qa_shu/complete/{session}/status/{id}.json
  （セッションごとのフォルダ内に 1 層の status ディレクトリ）
"""

import argparse
import time
from pathlib import Path

from src.qa_shu_utils import (
    get_qa_shu_list_data,
    get_qa_shu_q,
    get_qa_shu_a,
    save_status_if_needed,
)
from src.utils import (
    write_to_json,
    read_from_json,
    delete_md_files_with_message,
    remove_text_from_md_files,
)
from src.models import ShuShitsumonList

# ==== 定数定義 ====
WAIT_SECOND = 1.0
SESSION_LIST_FILE = Path("data/session.json")
LIST_JSON_DIR = Path("data/qa_shu/list")
COMPLETE_BASE_DIR = Path("data/qa_shu/complete")
STATUS_SUBDIR = "status"  # セッション配下の status ディレクトリ名

# ------------------------------------------------
# ユーティリティ
# ------------------------------------------------


def ensure_dir(p: Path) -> None:
    """ディレクトリがなければ作成"""
    p.mkdir(parents=True, exist_ok=True)


def status_path(session: int, qid: int) -> Path:
    """ステータス JSON の正規パスを返す"""
    return COMPLETE_BASE_DIR / str(session) / STATUS_SUBDIR / f"{qid}.json"


def clean_texts(session: int, sub: str) -> None:
    base = COMPLETE_BASE_DIR / str(session) / sub
    delete_md_files_with_message(
        str(base),
        "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
    )
    patterns = [
        r"経過へ\n|\n質問本文\(PDF\)へ\n|\n答弁本文\(HTML\)へ\n|\n答弁本文\(PDF\)へ\n",
        r"経過へ\n|\n質問本文\(PDF\)へ\n",
        r"経過へ\n|\n質問本文\(PDF\)へ",
    ]
    for pat in patterns:
        remove_text_from_md_files(str(base), pat)


def load_session_list() -> list[dict]:
    return read_from_json(str(SESSION_LIST_FILE))


def find_latest_session(sessions: list[dict]) -> int:
    nums = [
        s["session_number"] for s in sessions if s.get("session_number") is not None
    ]
    return max(nums)


# ------------------------------------------------
# メイン処理
# ------------------------------------------------


def process_session(
    session: int, idx: int, total: int, force_latest: bool = False
) -> None:
    print(f"[{idx}/{total}] セッション処理: {session}")

    # ---- 質問リスト取得 or 読み込み ----
    list_path = LIST_JSON_DIR / f"{session}.json"
    if force_latest or not list_path.exists():
        print(f"  ▷ リスト取得: session={session}")
        data = get_qa_shu_list_data(session)
        ensure_dir(list_path.parent)
        write_to_json(data.model_dump(), str(list_path))
    else:
        print(f"  ▷ リスト既存, スキップ: {list_path}")
        data = ShuShitsumonList(**read_from_json(str(list_path)))

    # ---- 各質問ごとの処理 ----
    for q in data.items:
        qid = q.number
        if qid is None:
            continue

        s_path = status_path(session, qid)

        # ① ステータスが答弁受理なら丸ごとスキップ
        if s_path.exists():
            st = read_from_json(str(s_path))
            if st.get("status") == "答弁受理":
                print(f"    ▷ 全スキップ (答弁受理済): question_id={qid}")
                continue

        # ② 質問本文（未取得のみ）
        if q.question_html_link:
            out_q = COMPLETE_BASE_DIR / str(session) / "q" / f"{qid}.md"
            if not out_q.exists():
                print(f"    ▷ 質問取得: {q.question_html_link}")
                time.sleep(WAIT_SECOND)
                content = get_qa_shu_q(q.question_html_link)
                ensure_dir(out_q.parent)
                out_q.write_text(content, encoding="utf-8")

        # ③ 答弁本文（未取得のみ）
        if q.answer_html_link:
            out_a = COMPLETE_BASE_DIR / str(session) / "a" / f"{qid}.md"
            if not out_a.exists():
                print(f"    ▷ 答弁取得: {q.answer_html_link}")
                time.sleep(WAIT_SECOND)
                content = get_qa_shu_a(q.answer_html_link)
                ensure_dir(out_a.parent)
                out_a.write_text(content, encoding="utf-8")

        # ④ MDクリーンアップ
        print(f"    ▷ MDクリーンアップ: question_id={qid}")
        clean_texts(session, "q")
        clean_texts(session, "a")

        # ⑤ ステータス取得（常に再取得）
        print(f"    ▷ ステータス保存: question_id={qid}")
        save_status_if_needed(session, q, WAIT_SECOND, force_if_not_received=True)


# ------------------------------------------------
# CLI
# ------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="衆議院QAデータ取得 CLI")
    parser.add_argument(
        "--all",
        action="store_true",
        help="過去セッションもすべて取得する",
    )
    args = parser.parse_args()

    sessions = load_session_list()
    latest = find_latest_session(sessions)

    targets = [latest]  # 最新は必ず処理
    if args.all:
        targets += list(range(latest - 1, 1, -1))

    for idx, sess in enumerate(targets, start=1):
        is_latest = idx == 1  # 先頭が最新
        process_session(sess, idx, len(targets), force_latest=is_latest)

    print("All sessions processed.")


if __name__ == "__main__":
    main()
