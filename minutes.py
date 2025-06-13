from __future__ import annotations

"""
Minutes API Fetcher (typed)
==========================
国会会議録検索システム API から会議録を取得し、
`data/minutes_api/{issueID}.json` に保存するスクリプト。
"""


import argparse
import json
import os
import sys
import time
from datetime import date as _date
from typing import Any, Dict, List, Literal, Optional

import requests
from pydantic import BaseModel, Field, ValidationError

from src.models import MeetingResponse

# ────────────────────────────── 定数 ─────────

BASE_DIR: str = "data/minutes_api"
BASE_URL: str = "https://kokkai.ndl.go.jp/api"
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "MinutesAPIFetcher/2.0 (+https://example.com)"
}
SLEEP_SEC: float = 2.5  # API ガイドラインより

# ────────────────────────────── Pydantic モデル ─────────


# ────────────────────────────── 型エイリアス ─────────

JSONDict = Dict[str, Any]
DownloadStatus = Literal["downloaded", "skipped"]

# ────────────────────────────── 基本ユーティリティ ─────────


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def cached_path(issue_id: str) -> str:
    return os.path.join(BASE_DIR, f"{issue_id}.json")


def is_cached(issue_id: str) -> bool:
    return os.path.exists(cached_path(issue_id))


def fetch_json(url: str, params: Dict[str, str]) -> JSONDict:
    """GET して JSON を返す。リトライ付き。"""
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()  # type: ignore[override]
            print(f"HTTP {resp.status_code}: {resp.reason} — retry", file=sys.stderr)
        except requests.RequestException as exc:
            print(f"Request error: {exc} — retry", file=sys.stderr)
        time.sleep(SLEEP_SEC)
    resp.raise_for_status()  # type: ignore[func-returns-value]


def fetch_meeting_response(params: Dict[str, str]) -> MeetingResponse:
    """`meeting` エンドポイントを取得し `MeetingResponse` に変換。"""
    raw = fetch_json(f"{BASE_URL}/meeting", params)
    try:
        return MeetingResponse.model_validate(raw)
    except ValidationError as e:
        raise RuntimeError("Failed to validate MeetingResponse") from e


# ────────────────────────────── issueID 収集 ─────────


def collect_issue_ids(
    search_params: Dict[str, str], limit: int | None = None
) -> List[str]:
    url = f"{BASE_URL}/meeting_list"
    params = search_params | {"recordPacking": "json", "maximumRecords": "100"}
    issue_ids: List[str] = []
    start = 1
    while True:
        params["startRecord"] = str(start)
        data = fetch_json(url, params)
        records: List[JSONDict] = data.get("meetingRecord", [])
        for rec in records:
            issue_ids.append(rec["issueID"])
            if limit and len(issue_ids) >= limit:
                return issue_ids
        next_pos = data.get("nextRecordPosition")
        if not next_pos:
            break
        start = int(next_pos)
        time.sleep(SLEEP_SEC)
    return issue_ids


# ────────────────────────────── 会議録ダウンロード ─────────


def download_issue(issue_id: str, *, overwrite: bool = False) -> DownloadStatus:
    ensure_dir(BASE_DIR)
    path = cached_path(issue_id)
    if not overwrite and is_cached(issue_id):
        return "skipped"

    params: Dict[str, str] = {
        "issueID": issue_id,
        "recordPacking": "json",
        "maximumRecords": "1",
    }
    meeting = fetch_meeting_response(params)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(
            meeting.model_dump(mode="json", exclude_none=True),
            fp,
            ensure_ascii=False,
            indent=2,
        )
    time.sleep(SLEEP_SEC)
    return "downloaded"


# ────────────────────────────── デフォルト日付レンジ ─────────


def default_date_range() -> tuple[str, str]:
    """既存ファイルから最新開催日を取得し、今日までの範囲を返却。"""
    import glob

    latest = _date(1900, 1, 1)
    for path in glob.glob(f"{BASE_DIR}/*.json"):
        try:
            with open(path, encoding="utf-8") as fp:
                raw: JSONDict = json.load(fp)
            meeting = MeetingResponse.model_validate(raw)
            date_str = meeting.meetingRecord[0].date
            latest = max(latest, _date.fromisoformat(date_str))
        except Exception:
            continue  # 壊れた JSON 等
    today = _date.today()
    return latest.isoformat(), today.isoformat()


# ────────────────────────────── CLI ヘルパ ─────────


def build_search_params(args: argparse.Namespace) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for key, value in vars(args).items():
        if value and key not in ("overwrite", "limit", "from_"):
            params[key] = str(value)
    if args.from_:
        params["from"] = args.from_
    return params


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch Diet minutes and cache locally (typed)"
    )
    p.add_argument("--any", help="検索語 (AND)")
    p.add_argument("--nameOfMeeting", help="会議名 (OR)")
    p.add_argument("--speaker", help="発言者名 (OR)")
    p.add_argument("--from_date", dest="from_", help="開催日 from (YYYY-MM-DD)")
    p.add_argument("--until", help="開催日 until (YYYY-MM-DD)")
    p.add_argument("--sessionFrom", help="国会回次 From")
    p.add_argument("--sessionTo", help="国会回次 To")
    p.add_argument("--limit", type=int, help="取得上限件数 (テスト用)")
    p.add_argument("--overwrite", action="store_true", help="既存 JSON を上書き")
    return p.parse_args()


# ────────────────────────────── main ─────────


def main() -> int:  # noqa: C901
    args = parse_args()
    search_params = build_search_params(args)

    if not search_params:
        _from, _until = default_date_range()
        search_params.update({"from": _from, "until": _until})
        print(f"[auto] from={_from} until={_until}", file=sys.stderr)

    print("[+] Collecting issueIDs …", file=sys.stderr)
    issue_ids = collect_issue_ids(search_params, limit=args.limit)
    total = len(issue_ids)
    print(f" → {total} 件ヒット", file=sys.stderr)

    width = len(str(total)) or 1
    stats: Dict[DownloadStatus, int] = {"downloaded": 0, "skipped": 0}
    for idx, iid in enumerate(issue_ids, 1):
        status = download_issue(iid, overwrite=args.overwrite)
        stats[status] += 1
        print(f"[{idx:0{width}d}/{total}] {status}: {iid}", file=sys.stderr)

    # 終了サマリ
    summary: Dict[str, int] = {"total": total} | stats
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
