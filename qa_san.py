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
)

WAIT_SECOND = 1.0


def clean_texts(session: int):
    """
    data/qa_sangiin/complete/{session}/q および /a のMarkdownを
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
            r"""質問主意書：参議院
すべての機能をご利用いただくにはJavascriptを有効にしてください。
本文へ
検索方法
検索
文字サイズの変更
標準
拡大
最大
サイトマップ
よくある質問
リンク集
English
トップページに戻る
議員情報
今国会情報
ライブラリー
議案情報
会議録情報
請願
質問主意書
参議院公報
参議院のあらまし
国会体験・見学
国際関係
調査室作成資料
参議院審議中継
（別ウィンドウで開きます）
特別体験プログラム
キッズページ
トップ
>
質問主意書

""",
            r"""質問主意書：参議院
すべての機能をご利用いただくにはJavascriptを有効にしてください。
本文へ
検索方法
検索
文字サイズの変更
標準
拡大
最大
サイトマップ
よくある質問
リンク集
English
トップページに戻る
議員情報
今国会情報
ライブラリー
議案情報
会議録情報
請願
質問主意書
参議院公報
参議院のあらまし
国会体験・見学
国際関係
調査室作成資料
参議院審議中継
（別ウィンドウで開きます）
特別体験プログラム
キッズページ
トップ
>
質問主意書
""",
            r"""利用案内
著作権
免責事項
ご意見・ご質問
All rights reserved. Copyright(c) , House of Councillors, The National Diet of Japan""",
        ]
        for pat in patterns:
            remove_text_from_md_files(str(base), pat)


def load_session_list(path: str = "data/session.json") -> List[Dict]:
    """
    セッション一覧をJSONファイルから読み込む。

    Args:
        path (str): セッション情報を持つJSONファイルのパス。

    Returns:
        List[Dict]: [{'session_number': ..., ...}, ...]
    """
    return read_from_json(path)


def find_latest_session(sessions: List[Dict]) -> int:
    """
    セッション一覧から最新（最大）の回次を返す。

    Args:
        sessions (List[Dict]): セッション情報リスト。

    Returns:
        int: 最新のセッション番号。
    """
    nums = [
        s["session_number"] for s in sessions if s.get("session_number") is not None
    ]
    return max(nums)


def process_session(session: int, idx: int, total: int, force_latest: bool = False):
    """
    指定回次の参議院QAを取得・保存し、Markdownの不要箇所をクリーンアップする。
    各質問について経過状況も保存する。
    """
    print(f"[{idx}/{total}] Processing session: {session}")
    list_dir = Path("data/qa_sangiin/list")
    list_dir.mkdir(parents=True, exist_ok=True)
    list_path = list_dir / f"{session}.json"

    # 一覧取得 or スキップ
    if force_latest or not list_path.exists():
        print(f"  ▷ Fetching list (session={session})")
        data = get_qa_sangiin_list(session)
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))
    else:
        print(f"  ▷ List exists, skip: {list_path}")
        from src.models import SangiinShitsumonList

        data = SangiinShitsumonList(**read_from_json(str(list_path)))

    # テキスト保存
    wait = WAIT_SECOND if not force_latest else 1.0
    print(f"  ▷ Saving question texts (wait={wait}s)")
    save_question_texts(session, wait)
    print(f"  ▷ Saving answer texts   (wait={wait}s)")
    save_answer_texts(session, wait)

    # MDクリーンアップ
    print("  ▷ Cleaning up markdown files")
    clean_texts(session)

    # 各質問の経過状況保存
    for q in data.items:
        print(f"    ▷ ステータス保存: question_id={q.number}")
        save_status_if_needed(
            session, q.number, q.progress_info_link, wait, force_latest
        )


def main():
    parser = argparse.ArgumentParser(description="参議院QAデータ取得")
    parser.add_argument("--all", action="store_true", help="最新に加え過去回次も取得")
    args = parser.parse_args()

    sessions = load_session_list()
    latest = find_latest_session(sessions)
    # 最新回次 + (--allなら過去2回～1回まで)
    targets = [latest] + (list(range(latest - 1, 0, -1)) if args.all else [])

    total = len(targets)
    for idx, sess in enumerate(targets, start=1):
        process_session(sess, idx, total, force_latest=(idx == 1))

    print("All sessions processed.")


if __name__ == "__main__":
    main()
