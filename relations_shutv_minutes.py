import os
import json
import pprint
from typing import Any, Dict, List, Tuple

from src.models import MeetingRecord, ShugiinTV
from src.utils import write_to_json


# ── 設定 ──
MINUTES_DIR = "data/minutes_api"
SHUGIINTV_DIR = "data/shugiintv"
OUTPUT_PATH = "data/relations/shutv-minutes.json"


# ── ロード関数 ──
def load_json_models(
    data_dir: str, model_class: Any, array_key: str = None
) -> List[Any]:
    """
    フォルダ内の全 JSON ファイルを読み込み、Pydantic モデルを返す。

    - model_class: BaseModel のサブクラス
    - array_key: JSON 内に model_class の配列がある場合のキー
    """
    results: List[Any] = []
    for fname in os.listdir(data_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(data_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if array_key and isinstance(data, dict) and array_key in data:
                for item in data[array_key]:
                    results.append(model_class.model_validate(item))
            else:
                results.append(model_class.model_validate(data))
        except Exception as e:
            print(f"Failed to load {path}: {e}")
    return results


# ── データ整形関数 ──
def to_simple_dicts(
    meetings: List[MeetingRecord], shutvs: List[ShugiinTV]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    MeetingRecord, ShugiinTV のリストから
    - meetings_list: {'date','name','issueID'} のリスト
    - shutvs_list:   {'date','name','deli_id'} のリスト
    を生成して返す。
    """
    meetings_list: List[Dict[str, str]] = [
        {
            "date": rec.date,
            "name": rec.nameOfMeeting,
            "issueID": rec.issueID,
        }
        for rec in meetings
    ]
    shutvs_list: List[Dict[str, str]] = [
        {"date": tv.date_time, "name": tv.meeting_name, "deli_id": tv.deli_id}
        for tv in shutvs
    ]
    return meetings_list, shutvs_list


# ── マージ＆ソート関数 ──
def merge_and_sort(
    meetings: List[Dict[str, str]], shutvs: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    date と name が一致する要素をマージし、
    issueID と deli_id を含む辞書のリストを、
    deli_id を数値として昇順ソートで返す。
    """
    deli_map: Dict[Tuple[str, str], str] = {
        (s["date"], s["name"]): s["deli_id"] for s in shutvs
    }

    merged: List[Dict[str, str]] = []
    for m in meetings:
        key = (m["date"], m["name"])
        if key in deli_map:
            merged.append(
                {
                    "date": m["date"],
                    "name": m["name"],
                    "issueID": m["issueID"],
                    "deli_id": deli_map[key],
                }
            )

    return sorted(merged, key=lambda x: int(x["deli_id"]))


# ── メイン処理 ──
def main():
    raw_meetings = load_json_models(
        MINUTES_DIR, MeetingRecord, array_key="meetingRecord"
    )
    raw_shutvs = load_json_models(SHUGIINTV_DIR, ShugiinTV)

    print(f"Loaded {len(raw_meetings)} meetings from {MINUTES_DIR}")
    print(f"Loaded {len(raw_shutvs)} records from {SHUGIINTV_DIR}")

    meetings, shutvs = to_simple_dicts(raw_meetings, raw_shutvs)
    merged_sorted = merge_and_sort(meetings, shutvs)

    pprint.pprint(merged_sorted)
    write_to_json(merged_sorted, OUTPUT_PATH)
    print(f"Written merged data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
