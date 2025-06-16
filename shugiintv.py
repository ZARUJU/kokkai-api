import os
import re
import json
import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Set

from src.utils import write_to_json, file_exists  # ※既存ユーティリティを利用

# ==== 定数定義 ============================================================
BASE_URL = "https://www.shugiintv.go.jp/jp/index.php"
DATA_FOLDER = "data/shugiintv"
EMPTY_HTML_IDS_PATH = os.path.join(DATA_FOLDER, "empty_html_ids.json")
LIST_SLEEP = 0.5  # 日付ごとの一覧取得時の待機秒数
DETAIL_SLEEP = 1  # 個別詳細取得時の待機秒数

# フォルダが無い場合でも自動作成
os.makedirs(DATA_FOLDER, exist_ok=True)

# ==== ユーティリティ関数 ===================================================


def load_empty_html_ids(path: str = EMPTY_HTML_IDS_PATH) -> Set[int]:
    """空 HTML と判定された deli_id セットを読み込む"""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                pass
    return set()


def save_empty_html_ids(ids: Set[int], path: str = EMPTY_HTML_IDS_PATH) -> None:
    """空 HTML ID セットをファイルに保存"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)


def is_html_empty(text: str, threshold: int = 50) -> bool:
    """実質的に中身が無い HTML かどうかを判定"""
    stripped = re.sub(r"\s+", "", text)
    return len(stripped) < threshold


def japanese_to_iso(date_str: str) -> str:
    """例: "2025年5月7日 (水)" → "2025-05-07"""
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_str)
    if not match:
        raise ValueError(f"不正な日付形式です: {date_str}")
    year, month, day = match.groups()
    dt = datetime(int(year), int(month), int(day))
    return dt.strftime("%Y-%m-%d")


def parse_deli_ids_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    deli_ids = [
        m.group(1)
        for a in soup.find_all("a", href=True)
        if (m := re.search(r"deli_id=(\d+)", a["href"]))
    ]
    unique_ids = list(set(deli_ids))
    print(f"  → 発見された deli_id 数: {len(unique_ids)}")
    return unique_ids


def parse_minutes_detail_page(html: str, detail_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    date_text, meeting_name = None, None
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
    topics = []
    for tbl in soup.select("#library2 table"):
        if tbl.find(string=lambda s: isinstance(s, str) and s.strip() == "案件："):
            for td in tbl.select("td"):
                txt = td.get_text(strip=True)
                if txt and txt != "案件：":
                    topics.append(txt)
            break
    speakers = set()
    for table in soup.select("#library2 table")[2:]:
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
        "date_time": japanese_to_iso(date_text) if date_text else None,
        "meeting_name": meeting_name,
        "topics": topics,
        "speakers": list(speakers),
        "url": detail_url,
    }


def get_date_range(start_yyyymmdd: str, end_yyyymmdd: str) -> List[str]:
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


# ==== 核心処理 ============================================================


def process_deli_id(deli_id: str, base_url: str, *, mode: str = "auto") -> None:
    html_path = f"{DATA_FOLDER}/{deli_id}.html"
    json_path = f"{DATA_FOLDER}/{deli_id}.json"
    # --- スキップ判定（auto モードのみ） -----------------------------------
    if mode == "auto" and file_exists(json_path):
        print(f"    ▷ Skipping {deli_id}: 既存 JSON あり ({json_path})")
        return
    # --- HTML を確保 -------------------------------------------------------
    cached_html_ok = mode in ("auto", "rebuild") and os.path.exists(html_path)
    if mode == "refetch" or not cached_html_ok:
        detail_url = f"{base_url}?ex=VL&deli_id={deli_id}"
        print(f"    ▷ Downloading HTML from {detail_url}")
        time.sleep(DETAIL_SLEEP)
        res = requests.get(detail_url)
        res.encoding = "euc-jp"
        html_text = res.text
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_text)
    else:
        print(f"    ▷ Using cached HTML ({html_path})")
        detail_url = f"{base_url}?ex=VL&deli_id={deli_id}"
        with open(html_path, encoding="utf-8") as f:
            html_text = f.read()

    # --- 空 HTML チェック --------------------------------------------------
    if is_html_empty(html_text):
        print(f"    ⚠ 空 HTML 検出: {deli_id}.html → 削除し記録")
        # 削除処理
        os.remove(html_path)
        if os.path.exists(json_path):
            os.remove(json_path)
        # 空 HTML ID の保存
        ids_set = load_empty_html_ids()
        ids_set.add(int(deli_id))
        save_empty_html_ids(ids_set)
        return  # JSON 生成スキップ

    # --- JSON 生成 ---------------------------------------------------------
    if mode != "auto" or not file_exists(json_path):
        try:
            data = {
                **parse_minutes_detail_page(html_text, detail_url),
                "deli_id": int(deli_id),
            }
            write_to_json(data=data, path=json_path)
            print(f"    ✔ JSON saved → {json_path}")
        except Exception as e:
            print(f"    !! Error parsing {deli_id}: {e}")


def fetch_shugiintv_data(start_date: str, end_date: str, *, mode: str = "auto") -> None:
    dates = get_date_range(start_date, end_date)
    print(f"開始: {start_date} → 終了: {end_date} （{len(dates)} 日分）")
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
        for deli_id in parse_deli_ids_from_html(res.text):
            process_deli_id(deli_id, BASE_URL, mode=mode)
    print("一覧処理完了。")


# ==== サポート関数（欠番チェック） =========================================


def list_deli_ids(data_folder: str) -> List[int]:
    ids = [
        int(fname[:-5])
        for fname in os.listdir(data_folder)
        if fname.endswith(".json") and fname[:-5].isdigit()
    ]
    return sorted(ids)


def get_missing_deli_ids(data_folder: str, *, ignore_empty: bool = True) -> List[int]:
    ids = list_deli_ids(data_folder)
    if not ids:
        return []
    full = set(range(ids[0], ids[-1] + 1))
    missing = sorted(full - set(ids))
    if ignore_empty:
        missing = [i for i in missing if i not in load_empty_html_ids()]
    return missing


# ==== クリーニング処理 =====================================================


def clean_empty_html_files(data_folder: str) -> List[int]:
    """サイズ 0 または本文実質空の HTML & 対応 JSON を削除し、ID を返す"""
    removed: List[int] = []
    for fname in os.listdir(data_folder):
        if not (fname.endswith(".html") and fname[:-5].isdigit()):
            continue
        html_path = os.path.join(data_folder, fname)
        deli_id = int(fname[:-5])
        try:
            if os.path.getsize(html_path) == 0:
                empty = True
            else:
                with open(html_path, encoding="utf-8") as f:
                    empty = is_html_empty(f.read())
            if empty:
                os.remove(html_path)
                json_path = os.path.join(data_folder, f"{deli_id}.json")
                if os.path.exists(json_path):
                    os.remove(json_path)
                removed.append(deli_id)
        except Exception as e:
            print(f"  !! 空 HTML 判定時エラー ({deli_id}): {e}")
    if removed:
        ids_set = load_empty_html_ids()
        ids_set.update(removed)
        save_empty_html_ids(ids_set)
    return removed


# ==== メインエントリ =======================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="衆議院TV データ取得ツール")
    parser.add_argument(
        "-s", "--start", type=str, help="取得開始日 (YYYYMMDD)。省略時は本日"
    )
    parser.add_argument(
        "-e", "--end", type=str, help="取得終了日 (YYYYMMDD)。省略時は開始日と同じ"
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "rebuild", "refetch"],
        default="auto",
        help="HTML/JSON 再利用モード (default: auto)",
    )
    args = parser.parse_args()
    today = datetime.today().strftime("%Y%m%d")
    start = args.start or today
    end = args.end or start
    try:
        datetime.strptime(start, "%Y%m%d")
        datetime.strptime(end, "%Y%m%d")
    except ValueError:
        parser.error("開始日・終了日は YYYYMMDD 形式で指定してください。")

    # 1) 通常取得
    fetch_shugiintv_data(start, end, mode=args.mode)

    # 2) 欠番再取得
    print("抜けているデータの取得を開始")
    missing_ids = get_missing_deli_ids(DATA_FOLDER)
    for i, deli_id in enumerate(missing_ids, 1):
        print(f"[再取得 {i}] ID: {deli_id}")
        process_deli_id(str(deli_id), BASE_URL, mode=args.mode)

    # 3) 空 HTML クリーンアップ（再取得後に再確認）
    removed = clean_empty_html_files(DATA_FOLDER)
    if removed:
        print(f"空 HTML を削除し記録: {removed}")

    print("全処理完了。")


if __name__ == "__main__":
    main()
