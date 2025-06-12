"""
参議院 QA 収集スクリプト
"""

import argparse
from pathlib import Path
from typing import List, Dict

from src.utils import (
    read_from_json,
    write_to_json,
    delete_md_files_with_message,
    remove_text_from_md_files,
)
from src.qa_san_utils import (
    get_qa_sangiin_list,
    save_question_texts,
    save_answer_texts,
    save_status_if_needed,
    status_is_received,
)

WAIT_SECOND = 1.0


# ----------------------------------------------------------------------
# 前処理（Markdown クレンジング）
# ----------------------------------------------------------------------
def clean_texts(session: int):
    """
    data/qa_sangiin/complete/{session}/q および /a の Markdown を
    「HTMLファイルはしばらくお待ちください...」を含む場合削除、
    不要な文言を削除する。
    """
    for sub in ("q", "a"):
        base = Path(f"data/qa_sangiin/complete/{session}/{sub}")
        delete_md_files_with_message(
            str(base),
            "HTMLファイルについてはしばらくお待ちください。PDFファイルをご覧ください。",
        )
        patterns = [
            # --- サイト共通ヘッダ（長文） ---
            r"""質問主意書：参議院
すべての機能をご利用いただくにはJavascriptを有効にしてください。
（中略）""",  # 省略（パターンは元コードと同じ）
            r"""利用案内
著作権
免責事項
ご意見・ご質問
All rights reserved. Copyright\(c\) , House of Councillors, The National Diet of Japan""",
        ]
        for pat in patterns:
            remove_text_from_md_files(str(base), pat)


# ----------------------------------------------------------------------
# セッション関連ユーティリティ
# ----------------------------------------------------------------------
def load_session_list(path: str = "data/session.json") -> List[Dict]:
    """セッション一覧を JSON から読み込み"""
    return read_from_json(path)


def find_latest_session(sessions: List[Dict]) -> int:
    """セッション一覧から最新回次（最大値）を取得"""
    nums = [
        s["session_number"] for s in sessions if s.get("session_number") is not None
    ]
    return max(nums)


# ----------------------------------------------------------------------
# メイン処理（1 セッション単位）
# ----------------------------------------------------------------------
def process_session(session: int, idx: int, total: int, force_latest: bool = False):
    """
    指定回次について
      1. 一覧取得（キャッシュ）
      2. 質問ごとのステータス取得・保存
      3. ステータスが未完のものだけ本文取得
      4. Markdown クリーンアップ
    """
    print(f"[{idx}/{total}] Processing session: {session}")
    list_dir = Path("data/qa_sangiin/list")
    list_dir.mkdir(parents=True, exist_ok=True)
    list_path = list_dir / f"{session}.json"

    # -------------------------------------------------- #
    # ① 一覧取得（キャッシュ優先）
    # -------------------------------------------------- #
    if force_latest or not list_path.exists():
        print(f"  ▷ Fetching list (session={session})")
        data = get_qa_sangiin_list(session)
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))
    else:
        print(f"  ▷ List exists, skip: {list_path}")
        from src.models import SangiinShitsumonList

        data = SangiinShitsumonList(**read_from_json(str(list_path)))

    # -------------------------------------------------- #
    # ② ステータス取得・保存
    # -------------------------------------------------- #
    wait = WAIT_SECOND if not force_latest else 1.0
    for q in data.items:
        print(f"    ▷ ステータス保存: question_id={q.number}")
        save_status_if_needed(
            session,
            q.number,
            q.progress_info_link,
            wait_second=wait,
            force_if_not_received=False,
        )

    # -------------------------------------------------- #
    # ③ 質疑本文取得（status_is_received が True のものはスキップ）
    # -------------------------------------------------- #
    print(f"  ▷ Saving question texts (wait={wait}s)")
    save_question_texts(session, wait)
    print(f"  ▷ Saving answer texts   (wait={wait}s)")
    save_answer_texts(session, wait)

    # -------------------------------------------------- #
    # ④ Markdown クリーン
    # -------------------------------------------------- #
    print("  ▷ Cleaning up markdown files")
    clean_texts(session)


# ----------------------------------------------------------------------
# エントリポイント
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="参議院QAデータ取得")
    parser.add_argument("--all", action="store_true", help="最新に加え過去回次も取得")
    args = parser.parse_args()

    sessions = load_session_list()
    latest = find_latest_session(sessions)
    targets = [latest] + (list(range(latest - 1, 0, -1)) if args.all else [])

    total = len(targets)
    for idx, sess in enumerate(targets, start=1):
        process_session(sess, idx, total, force_latest=(idx == 1))

    print("All sessions processed.")


if __name__ == "__main__":
    main()
