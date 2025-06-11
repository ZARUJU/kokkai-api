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
)
from src.models import ShuShitsumonListData

WAIT_SECOND = 1.0


def clean_texts(session: int):
    for sub in ("a", "q"):
        base = Path(f"data/qa_shu/complete/{session}/{sub}")
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
    return read_from_json("data/session.json")


def find_latest_session(sessions: list[dict]) -> int:
    nums = [
        s["session_number"] for s in sessions if s.get("session_number") is not None
    ]
    return max(nums)


def process_session(session: int, idx: int, total: int, force_latest: bool = False):
    print(f"[{idx}/{total}] セッション処理: {session}")
    list_path = Path(f"data/qa_shu/list/{session}.json")

    if force_latest or not list_path.exists():
        print(f"  ▷ リスト取得: session={session}")
        data = get_qa_shu_list_data(session)
        write_to_json(data.model_dump(), str(list_path))
    else:
        print(f"  ▷ リスト既存, スキップ: {list_path}")
        data = ShuShitsumonListData(**read_from_json(str(list_path)))

    wait = WAIT_SECOND if not force_latest else 1.0
    print(f"  ▷ 質問テキスト保存 (wait={wait}s)")
    save_qa_shu_question_texts(session, wait)
    print(f"  ▷ 答弁テキスト保存 (wait={wait}s)")
    save_qa_shu_answer_texts(session, wait)

    print("  ▷ MDクリーンアップ")
    clean_texts(session)

    for q in data.questions:
        print(f"    ▷ ステータス保存: question_id={q.number}")
        save_status_if_needed(session, q, wait, force_latest)


def main():
    parser = argparse.ArgumentParser(description="衆議院QAデータ取得")
    parser.add_argument("--all", action="store_true", help="過去セッションも取得")
    args = parser.parse_args()

    sessions = load_session_list()
    latest = find_latest_session(sessions)
    targets = [latest] + (list(range(latest - 1, 1, -1)) if args.all else [])

    for idx, sess in enumerate(targets, start=1):
        process_session(sess, idx, len(targets), force_latest=(idx == 1))
    print("All sessions processed.")


if __name__ == "__main__":
    main()
