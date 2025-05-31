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
    file_exists,
)
from src.models import ShuShitsumonListData

session_list = read_from_json("data/session.json")

# 方法A: sorted を使って昇順にソートし、最後の要素を取り出す
valid_sessions = [s for s in session_list if s.get("session_number") is not None]
# session_number をキーにソート
valid_sessions.sort(key=lambda x: x["session_number"])

# 昇順ソート後の末尾要素が最新
latest_session = valid_sessions[-1]
latest_number = latest_session["session_number"]

LATEST_SESSION = latest_number
WAIT_SECOND = 3.0


def delete_md_files_with_message(directory: str, target_phrase: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_phrase in content:
                md_file.unlink()
                print(f"[削除] {md_file}")
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")


def remove_text_from_md_files(directory: str, target_text: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_text in content:
                new_content = content.replace(target_text, "")
                md_file.write_text(new_content, encoding="utf-8")
                print(f"[修正] {md_file}")
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")


def clean_texts(session: int):
    base_dir = f"data/qa_shu/complete/{session}/a"
    delete_md_files_with_message(
        base_dir,
        "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
    )
    remove_text_from_md_files(
        base_dir,
        """経過へ\n|\n質問本文(PDF)へ\n|\n答弁本文(HTML)へ\n|\n答弁本文(PDF)へ\n""",
    )
    remove_text_from_md_files(base_dir, """経過へ\n|\n質問本文(PDF)へ\n""")
    remove_text_from_md_files(base_dir, """経過へ\n|\n質問本文(PDF)へ""")


# --- 最新セッション（強制更新） ---
data = get_qa_shu_list_data(LATEST_SESSION)
write_to_json(data.model_dump(), f"data/qa_shu/list/{LATEST_SESSION}.json")
save_qa_shu_question_texts(LATEST_SESSION, 1.0)
save_qa_shu_answer_texts(LATEST_SESSION, 1.0)
clean_texts(LATEST_SESSION)

# ステータス保存（質問ごと）
for q in data.questions:
    save_status_if_needed(
        LATEST_SESSION, q, wait_second=1.0, force_if_not_received=True
    )

# --- 過去セッション（未取得のみ） ---
for session in range(LATEST_SESSION - 1, 1, -1):
    path = f"data/qa_shu/list/{session}.json"
    if not file_exists(path):
        data = get_qa_shu_list_data(session)
        write_to_json(data.model_dump(), path)

    save_qa_shu_question_texts(session, WAIT_SECOND)
    save_qa_shu_answer_texts(session, WAIT_SECOND)
    clean_texts(session)

    list_data = ShuShitsumonListData(**read_from_json(path))
    for q in list_data.questions:
        save_status_if_needed(session, q, WAIT_SECOND)
