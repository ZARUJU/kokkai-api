import argparse
from pathlib import Path
from src.qa_shu_utils import (
    get_qa_shu_list_data,
    save_qa_shu_question_texts,
    save_qa_shu_answer_texts,
    save_status_if_needed,
)
from src.utils import (
    write_to_json,
    read_from_json,
    delete_md_files_with_message,
    remove_text_from_md_files,
    file_exists,
)
from src.models import ShuShitsumonListData

WAIT_SECOND = 1.0


def clean_texts(session: int):
    base_dirs = [
        f"data/qa_shu/complete/{session}/a",
        f"data/qa_shu/complete/{session}/q",
    ]
    for base_dir in base_dirs:
        delete_md_files_with_message(
            base_dir,
            "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
        )
        patterns = [
            r"経過へ\n|\n質問本文\(PDF\)へ\n|\n答弁本文\(HTML\)へ\n|\n答弁本文\(PDF\)へ\n",
            r"経過へ\n|\n質問本文\(PDF\)へ\n",
            r"経過へ\n|\n質問本文\(PDF\)へ",
        ]
        for pat in patterns:
            remove_text_from_md_files(base_dir, pat)


def load_session_list() -> list[dict]:
    return read_from_json("data/session.json")


def find_latest_session(session_list: list[dict]) -> int:
    valid = [s for s in session_list if s.get("session_number") is not None]
    valid.sort(key=lambda x: x["session_number"])
    return valid[-1]["session_number"]


def process_session(session: int, index: int, total: int, force_latest: bool = False):
    """
    １セッション分の処理を行う。force_latest=True なら強制更新。
    """
    print(f"[{index}/{total}] Processing session: {session}")
    list_path = Path(f"data/qa_shu/list/{session}.json")

    # リストデータ取得
    need_fetch_list = force_latest or not list_path.exists()
    if need_fetch_list:
        print(f"  ▷ Fetching list data for session {session}")
        data = get_qa_shu_list_data(session)
        write_to_json(data.model_dump(), str(list_path))
    else:
        print(f"  ▷ List JSON exists, skip fetch: {list_path}")
        data = ShuShitsumonListData(**read_from_json(str(list_path)))

    # テキスト保存
    wait = 1.0 if force_latest else WAIT_SECOND
    print(f"  ▷ Saving question texts (wait={wait}s)")
    save_qa_shu_question_texts(session, wait_second=wait)
    print(f"  ▷ Saving answer texts   (wait={wait}s)")
    save_qa_shu_answer_texts(session, wait_second=wait)

    # MDクリーンアップ
    print("  ▷ Cleaning up markdown files")
    clean_texts(session)

    # ステータス保存
    for q in data.questions:
        print(f"    ▷ Saving status for question_id={q.number}")
        save_status_if_needed(
            session, q, wait_second=wait, force_if_not_received=force_latest
        )


def main():
    parser = argparse.ArgumentParser(
        description="衆議院QAデータ取得 (引数 --all: 過去セッションも含む全件取得)"
    )
    parser.add_argument(
        "--all", action="store_true", help="最新セッションに加え、過去セッションも取得"
    )
    args = parser.parse_args()

    session_list = load_session_list()
    latest = find_latest_session(session_list)

    if args.all:
        # 最新＋過去
        sessions = [latest] + list(range(latest - 1, 1, -1))
    else:
        # 最新のみ
        sessions = [latest]

    total = len(sessions)
    for idx, sess in enumerate(sessions, start=1):
        process_session(sess, idx, total, force_latest=(idx == 1))

    print("All sessions processed.")


if __name__ == "__main__":
    main()
