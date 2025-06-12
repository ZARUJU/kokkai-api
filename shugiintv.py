import os
import re
import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List

from src.utils import write_to_json, file_exists

# ==== 定数定義 ====
BASE_URL = "https://www.shugiintv.go.jp/jp/index.php"
DATA_FOLDER = "data/shugiintv"
LIST_SLEEP = 0.5  # 日付ごとの一覧取得時の待機秒数
DETAIL_SLEEP = 1  # 個別詳細取得時の待機秒数

# ==== ユーティリティ関数 ====


def japanese_to_iso(date_str: str) -> str:
    """
    例: "2025年5月7日 (水)" を "2025-05-07" に変換して返す。
    """
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_str)
    if not match:
        raise ValueError(f"不正な日付形式です: {date_str}")

    year, month, day = match.groups()
    dt = datetime(int(year), int(month), int(day))
    return dt.strftime("%Y-%m-%d")


def parse_deli_ids_from_html(html: str) -> List[str]:
    """
    HTMLからdeli_idを抽出し、重複を除去して返す
    """
    soup = BeautifulSoup(html, "html.parser")
    deli_ids = []
    for a in soup.find_all("a", href=True):
        match = re.search(r"deli_id=(\d+)", a["href"])
        if match:
            deli_ids.append(match.group(1))

    unique_ids = list(set(deli_ids))
    print(f"  → 発見されたdeli_id数: {len(unique_ids)}")
    return unique_ids


def parse_minutes_detail_page(html: str, detail_url: str) -> dict:
    """
    会議詳細のHTMLから必要な情報をパースして返す
    """
    soup = BeautifulSoup(html, "html.parser")

    # 会議の基本情報取得
    date_text = None
    meeting_name = None
    lib = soup.select_one("#library table")
    if lib:
        for row in lib.select("tr"):
            tds = row.find_all("td")
            if len(tds) >= 4:
                key = tds[1].get_text(strip=True)
                value = tds[3].get_text(strip=True)
                if key == "開会日":
                    date_text = value
                elif key == "会議名":
                    meeting_name = value.split(" (")[0]

    # 議題取得
    topics = []
    for tbl in soup.select("#library2 table"):
        if tbl.find(string=lambda s: isinstance(s, str) and s.strip() == "案件："):
            for td in tbl.select("td"):
                txt = td.get_text(strip=True)
                if txt and txt != "案件：":
                    topics.append(txt)
            break

    # 発言者取得
    speakers = set()
    tables = soup.select("#library2 table")
    for table in tables[2:]:
        for a in table.select("a.play_vod"):
            if name := a.get_text(strip=True):
                speakers.add(name)
    for row in soup.select("#library2 table tr"):
        tds = row.find_all("td")
        if len(tds) >= 2:
            text = tds[1].get_text(strip=True)
            if text and "（" in text:
                speakers.add(text)
    speakers -= set(topics)

    return {
        "date_time": japanese_to_iso(date_text),
        "meeting_name": meeting_name,
        "topics": topics,
        "speakers": list(speakers),
        "url": detail_url,
    }


def get_date_range(start_yyyymmdd: str, end_yyyymmdd: str) -> List[str]:
    """
    start から end までの日付リスト（YYYYMMDD形式）を返す
    """
    start_date = datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
    end_date = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    if start_date > end_date:
        return []

    dates = []
    d = start_date
    while d <= end_date:
        dates.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return dates


def process_deli_id(deli_id: str, base_url: str) -> None:
    """
    単一のdeli_idについて、詳細取得～JSON保存
    """
    path = f"{DATA_FOLDER}/{deli_id}.json"
    if file_exists(path):
        print(f"    ▷ Skipping {deli_id}: 既存ファイルあり ({path})")
        return

    detail_url = f"{base_url}?ex=VL&deli_id={deli_id}"
    print(f"    ▷ Fetching {deli_id} from {detail_url}")
    time.sleep(DETAIL_SLEEP)
    try:
        res = requests.get(detail_url)
        res.encoding = "euc-jp"
        data = {**parse_minutes_detail_page(res.text, detail_url), "deli_id": deli_id}
        write_to_json(data=data, path=path)
        print(f"    ✔ Saved {deli_id} → {path}")
    except Exception as e:
        print(f"    !! Error on {deli_id}: {e}")


def fetch_shugiintv_data(start_date: str, end_date: str) -> None:
    """
    指定期間のデータ取得を統括
    """
    dates = get_date_range(start_date, end_date)
    print(f"開始: {start_date} → 終了: {end_date} ({len(dates)}日分)")

    for i, date in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] 処理中: {date}")
        time.sleep(LIST_SLEEP)
        list_url = f"{BASE_URL}?ex=VL&u_day={date}"
        try:
            res = requests.get(list_url)
            res.encoding = "euc-jp"
        except Exception as e:
            print(f"  !! 一覧取得失敗 ({date}): {e}")
            continue

        ids = parse_deli_ids_from_html(res.text)
        for deli_id in ids:
            process_deli_id(deli_id, BASE_URL)

    print("一覧処理完了。")


def list_deli_ids(data_folder: str) -> List[int]:
    """
    data_folder内の'{delid}.json'ファイル名からIDリストを返す
    """
    deli_ids = []
    if not os.path.isdir(data_folder):
        return deli_ids

    for fname in os.listdir(data_folder):
        if not fname.endswith(".json"):
            continue
        name = fname[:-5]
        if name.isdigit():
            deli_ids.append(int(name))
    return sorted(deli_ids)


def get_missing_deli_ids(data_folder: str) -> List[int]:
    """
    フォルダ内のIDリストから欠損IDを返す
    """
    ids = list_deli_ids(data_folder)
    if not ids:
        return []

    min_id, max_id = ids[0], ids[-1]
    full_range = set(range(min_id, max_id + 1))
    missing = sorted(full_range - set(ids))
    return missing


def main():
    parser = argparse.ArgumentParser(description="衆議院TVデータ取得ツール")
    parser.add_argument(
        "-s", "--start", help="取得開始日（YYYYMMDD）。省略時は本日", type=str
    )
    parser.add_argument(
        "-e", "--end", help="取得終了日（YYYYMMDD）。省略時は開始日と同じ", type=str
    )
    args = parser.parse_args()

    # 日付の設定とバリデーション
    today = datetime.today().strftime("%Y%m%d")
    start = args.start or today
    try:
        datetime.strptime(start, "%Y%m%d")
    except ValueError:
        parser.error("開始日の形式はYYYYMMDDで指定してください。")

    end = args.end or start
    try:
        datetime.strptime(end, "%Y%m%d")
    except ValueError:
        parser.error("終了日の形式はYYYYMMDDで指定してください。")

    # 実行
    fetch_shugiintv_data(start, end)

    # 抜けID再取得
    print("抜けているデータの取得を開始")
    missing = get_missing_deli_ids(DATA_FOLDER)
    for i, deli_id in enumerate(missing, 1):
        print(f"[再取得 {i}/{len(missing)}] ID: {deli_id}")
        process_deli_id(str(deli_id), BASE_URL)

    print("全処理完了。")


if __name__ == "__main__":
    main()
