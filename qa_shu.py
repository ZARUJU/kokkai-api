from src.qa_shu_utils import (
    get_qa_shu_list_data,
    save_qa_shu_question_texts,
    save_qa_shu_answer_texts,
)
from src.utils import write_to_json, file_exists


LATEST_SESSION = 217
WAIT_SECOND = 3.0

# 最新の会期は強制実行
data = get_qa_shu_list_data(LATEST_SESSION)
write_to_json(data.model_dump(), f"data/qa_shu/list/{LATEST_SESSION}.json")
save_qa_shu_question_texts(LATEST_SESSION, WAIT_SECOND)
save_qa_shu_answer_texts(LATEST_SESSION, WAIT_SECOND)


# 最新会期までの質問主意書を取得する（未取得のみ）
# 最新会期は取得済みでも取得する
for session in range(1, LATEST_SESSION + 1):
    path = f"data/qa_shu/list/{session}.json"

    # 質問主意書一覧の取得
    # ファイルが存在しないなら実行する
    if not file_exists(path):
        data = get_qa_shu_list_data(session)
        write_to_json(data.model_dump(), path)

    # 質問主意書の取得と保存
    save_qa_shu_question_texts(session, WAIT_SECOND)
    save_qa_shu_answer_texts(session, WAIT_SECOND)
