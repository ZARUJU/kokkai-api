from pathlib import Path

from src.qa_shu_utils import (
    get_qa_shu_list_data,
    save_qa_shu_question_texts,
    save_qa_shu_answer_texts,
)
from src.utils import write_to_json, file_exists


LATEST_SESSION = 217
WAIT_SECOND = 3.0


def delete_md_files_with_message(directory: str, target_phrase: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(
            f"指定されたパスはディレクトリではありません: {directory}"
        )

    count = 0
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_phrase in content:
                md_file.unlink()
                print(f"[削除] {md_file}")
                count += 1
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")

    print(f"\n削除完了: {count}件")


def remove_text_from_md_files(directory: str, target_text: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(
            f"指定されたパスはディレクトリではありません: {directory}"
        )

    count = 0
    for md_file in dir_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if target_text in content:
                new_content = content.replace(target_text, "")
                md_file.write_text(new_content, encoding="utf-8")
                print(f"[修正] {md_file}")
                count += 1
        except Exception as e:
            print(f"[エラー] {md_file}: {e}")

    print(f"\n文字列を削除したファイル数: {count}件")


# 最新の会期は強制実行
data = get_qa_shu_list_data(LATEST_SESSION)
write_to_json(data.model_dump(), f"data/qa_shu/list/{LATEST_SESSION}.json")
save_qa_shu_question_texts(LATEST_SESSION, 0.0)
save_qa_shu_answer_texts(LATEST_SESSION, 0.0)
delete_md_files_with_message(
    f"data/qa_shu/complete/{LATEST_SESSION}/a",
    "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
)
remove_text_from_md_files(
    directory=f"data/qa_shu/complete/{LATEST_SESSION}/a",
    target_text="""経過へ
|
質問本文(PDF)へ
|
答弁本文(HTML)へ
|
答弁本文(PDF)へ
""",
)
remove_text_from_md_files(
    directory=f"data/qa_shu/complete/{LATEST_SESSION}/a",
    target_text="""経過へ
|
質問本文(PDF)へ
""",
)
remove_text_from_md_files(
    directory=f"data/qa_shu/complete/{LATEST_SESSION}/a",
    target_text="""経過へ
|
質問本文(PDF)へ""",
)

# 最新会期までの質問主意書を取得する（未取得のみ）
# 最新会期は取得済みでも取得する
for session in range(LATEST_SESSION - 1, 1, -1):
    path = f"data/qa_shu/list/{session}.json"

    # 質問主意書一覧の取得
    # ファイルが存在しないなら実行する
    if not file_exists(path):
        data = get_qa_shu_list_data(session)
        write_to_json(data.model_dump(), path)

    # 質問主意書の取得と保存
    save_qa_shu_question_texts(session, WAIT_SECOND)
    save_qa_shu_answer_texts(session, WAIT_SECOND)
    delete_md_files_with_message(
        f"data/qa_shu/complete/{session}/a",
        "ＨＴＭＬファイルについてはしばらくお待ちください。ＰＤＦファイルをご覧ください。",
    )
    remove_text_from_md_files(
        directory=f"data/qa_shu/complete/{session}/a",
        target_text="""経過へ
|
質問本文(PDF)へ
|
答弁本文(HTML)へ
|
答弁本文(PDF)へ
""",
    )
    remove_text_from_md_files(
        directory=f"data/qa_shu/complete/{session}/a",
        target_text="""経過へ
|
質問本文(PDF)へ
""",
    )
    remove_text_from_md_files(
        directory=f"data/qa_shu/complete/{session}/a",
        target_text="""経過へ
|
質問本文(PDF)へ""",
    )
