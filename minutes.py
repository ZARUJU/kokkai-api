#!/usr/bin/env python3
"""
minutes_api_fetcher.py
======================
国会会議録検索システム API から会議録を取得し、
`data/minutes_api/{issueID}.json` に保存するスクリプト。

更新点（2025‑06‑13）
---------------------
* 進捗表示を `[nn/tt]` 形式（先頭ゼロ埋め）で stderr 出力
* 終了時に合計件数もサマリ表示
* docstring を整理

特長
----
* `meeting_list` エンドポイントで issueID 一覧を効率取得
* 既存 issueID はスキップし増分取得
* API 負荷軽減のため 2.5 秒スリープを挟む
* コマンドライン引数で検索条件を柔軟に指定
* `--overwrite` で既存 JSON を再取得可能

使用例
------
```bash
# 発言に「科学技術」を含む会議録を取得
python minutes_api_fetcher.py --any 科学技術

# 期間指定（2024 年）＆ 会議名指定、10 件だけ試験取得
python minutes_api_fetcher.py --from_date 2024-01-01 --until 2024-12-31 \
  --nameOfMeeting 文部科学委員会 --limit 10
```

依存
----
```bash
pip install requests
```
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date as _date
from typing import Dict, List

import requests

BASE_DIR = "data/minutes_api"
BASE_URL = "https://kokkai.ndl.go.jp/api"
DEFAULT_HEADERS = {"User-Agent": "MinutesAPIFetcher/1.2 (+https://example.com)"}
SLEEP_SEC = 2.5  # API ガイドラインより


# ────────────────────────────── 基本ユーティリティ ─────────


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def is_cached(issue_id: str) -> bool:
    return os.path.exists(os.path.join(BASE_DIR, f"{issue_id}.json"))


def fetch_json(url: str, params: Dict[str, str]) -> Dict:
    """GET and return JSON with basic retry."""
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            print(f"HTTP {resp.status_code}: {resp.reason} — retry", file=sys.stderr)
        except requests.RequestException as exc:
            print(f"Request error: {exc} — retry", file=sys.stderr)
        time.sleep(SLEEP_SEC)
    resp.raise_for_status()


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
        for rec in data.get("meetingRecord", []):
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


def download_issue(issue_id: str, overwrite: bool = False) -> str:
    ensure_dir(BASE_DIR)
    path = os.path.join(BASE_DIR, f"{issue_id}.json")
    if not overwrite and is_cached(issue_id):
        return "skipped"

    url = f"{BASE_URL}/meeting"
    params = {"issueID": issue_id, "recordPacking": "json", "maximumRecords": "1"}
    data = fetch_json(url, params)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    time.sleep(SLEEP_SEC)
    return "downloaded"


# ────────────────────────────── デフォルト日付レンジ ─────────


def default_date_range() -> tuple[str, str]:
    """既存ファイルの最大開催日から今日までの範囲を返す。"""
    import glob

    latest = _date(1900, 1, 1)
    for path in glob.glob(f"{BASE_DIR}/*.json"):
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            date_str = data["meetingRecord"][0]["date"]
            latest = max(latest, _date.fromisoformat(date_str))
        except Exception:
            continue  # 壊れた JSON などは無視
    today = _date.today()
    return latest.isoformat(), today.isoformat()


# ────────────────────────────── CLI ─────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Diet minutes and cache locally")
    # 検索パラメータ (代表的なもののみ)
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


def main() -> int:
    args = parse_args()

    # API パラメータへ変換
    search_params: Dict[str, str] = {}
    for key, value in vars(args).items():
        if value and key not in ("overwrite", "limit", "from_"):
            search_params[key] = str(value)
    if args.from_:
        search_params["from"] = args.from_

    # 引数なしの場合、既存データから日付範囲を推定
    if not search_params:
        _from, _until = default_date_range()
        search_params.update({"from": _from, "until": _until})
        print(f"[auto] from={_from} until={_until}", file=sys.stderr)

    print("[+] Collecting issueIDs …", file=sys.stderr)
    issue_ids = collect_issue_ids(search_params, limit=args.limit)
    total = len(issue_ids)
    print(f" → {total} 件ヒット", file=sys.stderr)

    width = len(str(total)) or 1  # 桁数
    stats = {"downloaded": 0, "skipped": 0}
    for idx, iid in enumerate(issue_ids, 1):
        status = download_issue(iid, overwrite=args.overwrite)
        stats[status] += 1
        print(f"[{idx:0{width}d}/{total}] {status}: {iid}", file=sys.stderr)

    # 終了サマリ
    print(json.dumps({"total": total} | stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
