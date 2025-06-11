import os
import requests
import time
import json
from typing import List, Dict, Any
import requests

from src.utils import read_from_json


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


def fetch_and_save_minutes_by_session(
    session, data_dir="data/minutes_api", maximum_records=10
):
    """
    特定回次(session)の全会議録（会議単位）をAPIから再起的に取得し、
    各issueIDごとにJSONファイルで保存。全件取得し終えたら必ず終了する。
    """
    os.makedirs(data_dir, exist_ok=True)
    endpoint = "https://kokkai.ndl.go.jp/api/meeting"
    start_record = 1
    total_fetched = 0
    total_records = None  # 全件数

    while True:
        params = {
            "sessionFrom": session,
            "sessionTo": session,
            "maximumRecords": maximum_records,  # 会議単位出力は1~10のみ
            "startRecord": start_record,
            "recordPacking": "json",
        }
        res = requests.get(endpoint, params=params)
        res.raise_for_status()
        data = res.json()

        if "message" in data:
            print("APIエラー:", data["message"])
            break

        # 1回目で総件数取得
        if total_records is None:
            total_records = data.get("numberOfRecords", "?")
            if total_records == 0:
                print("該当データなし。終了。")
                break

        records = data.get("meetingRecord", [])
        num_records = len(records)

        if num_records == 0:
            print("新たなデータ無し。終了。")
            break

        for meeting in records:
            issue_id = meeting["issueID"]
            out_path = os.path.join(data_dir, f"{issue_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(meeting, f, ensure_ascii=False, indent=2)

        total_fetched += num_records
        print(f"進捗: {total_fetched} / {total_records} 件")

        # ここで「全件数に達したら」必ず終了
        if total_fetched >= total_records:
            print("全件保存完了")
            break

        # 次が無ければ終了
        if "nextRecordPosition" in data:
            start_record = data["nextRecordPosition"]
            time.sleep(2)
        else:
            print("全件保存完了")
            break


def load_jsons_from_folder(data_dir: str) -> List[Dict[str, Any]]:
    """
    指定フォルダ内の全 JSON ファイルを読み込み、
    各ファイルの JSON オブジェクトをそのままリストにして返します。
    """
    items: List[Dict[str, Any]] = []
    for fname in os.listdir(data_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(data_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            items.append(obj)
        except Exception as e:
            print(f"Failed to load {path}: {e}")
    return items


sessions = load_session_list()
latest = find_latest_session(sessions)
fetch_and_save_minutes_by_session(215)

# 不必要なデータを除去するためのもの
jsons = load_jsons_from_folder("data/minutes_api")
for item in jsons:
    if item["issue"] == "第0号":
        issueID = item["issueID"]
        path = f"data/minutes_api/{issueID}.json"
        print(path)
        os.remove(path)
