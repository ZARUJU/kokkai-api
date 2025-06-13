"""
衆議院 TV と国会会議録の対応表作成スクリプト
=================================================

ShugiinTV (衆議院の動画配信) の `deli_id` と、minutes_api の `issueID` を
`date` + `nameOfMeeting` で突き合わせ、JSON で保存する。
"""

import json
import os
from typing import Any, Dict, List, Tuple

from src.models import MeetingRecord, ShugiinTV
from src.utils import write_to_json

# ── 設定 ──
MINUTES_DIR = "data/minutes_api"
SHUGIINTV_DIR = "data/shugiintv"
OUTPUT_PATH = "data/relations/shutv-minutes.json"
HOUSE_FILTER = "衆議院"  # 衆議院のみ対象

# ── ロード関数 ──


def load_json_models(
    data_dir: str, model_class: Any, array_key: str | None = None
) -> List[Any]:
    """フォルダ内の全 JSON を読み込み Pydantic モデルに変換して返す。"""
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
        except Exception as e:  # noqa: BLE001
            print(f"Failed to load {path}: {e}")
    return results


# ── データ整形関数 ──


def to_simple_dicts(
    meetings: List[MeetingRecord], shutvs: List[ShugiinTV]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """MeetingRecord / ShugiinTV からシンプルな辞書リストを作成。"""
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
    """会議録と Shugiintv を date+name でマージし deli_id 昇順で返す。"""
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


def main() -> None:
    raw_meetings: List[MeetingRecord] = load_json_models(
        MINUTES_DIR, MeetingRecord, array_key="meetingRecord"
    )
    raw_shutvs: List[ShugiinTV] = load_json_models(SHUGIINTV_DIR, ShugiinTV)

    print(f"Loaded {len(raw_meetings)} meetings (all houses)")
    print(f"Loaded {len(raw_shutvs)} shugiintv records")

    # nameOfHouse == '衆議院' にフィルタ
    meetings_filtered: List[MeetingRecord] = [
        m for m in raw_meetings if m.nameOfHouse == HOUSE_FILTER
    ]
    print(
        f"Filtered to {len(meetings_filtered)} meetings where nameOfHouse == '{HOUSE_FILTER}'"
    )

    meetings_simple, shutvs_simple = to_simple_dicts(meetings_filtered, raw_shutvs)
    merged_sorted: List[Dict[str, str]] = merge_and_sort(meetings_simple, shutvs_simple)

    print(f"Merged {len(merged_sorted)} / {len(meetings_filtered)} meetings")
    write_to_json(merged_sorted, OUTPUT_PATH)
    print(f"Written merged data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
