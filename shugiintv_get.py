import os
import re
import json
import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Set

# ==== 定数定義 ============================================================
BASE_URL = "https://www.shugiintv.go.jp/jp/index.php"
# データ全体を格納するルートフォルダ
DATA_ROOT = "data/shugiintv"
# HTMLファイルの保存先フォルダ
HTML_DIR = os.path.join(DATA_ROOT, "html")
# 空のHTMLと判定されたIDを記録するファイル
EMPTY_HTML_IDS_PATH = os.path.join(DATA_ROOT, "empty_html_ids.json")
# 連続アクセスを避けるための待機秒数
LIST_SLEEP = 0.5
DETAIL_SLEEP = 1

# ==== ユーティリティ関数 ===================================================


def load_empty_html_ids(path: str = EMPTY_HTML_IDS_PATH) -> Set[int]:
    """空HTMLと判定されたdeli_idのセットをファイルから読み込む"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                pass  # ファイルが空または不正な形式の場合
    return set()


def save_empty_html_ids(ids: Set[int], path: str = EMPTY_HTML_IDS_PATH) -> None:
    """空HTMLのdeli_idセットをファイルに保存する"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        # 見やすいようにソートして書き込む
        json.dump(sorted(list(ids)), f, ensure_ascii=False, indent=2)


def is_html_empty(html_text: str, threshold: int = 100) -> bool:
    """HTMLの内容が実質的に空かどうかを判定する（文字数で判断）"""
    # scriptタグ、styleタグ、空白文字を除去して文字数を数える
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    stripped_text = re.sub(r"\s+", "", soup.get_text())
    return len(stripped_text) < threshold


def get_date_range(start_yyyymmdd: str, end_yyyymmdd: str) -> List[str]:
    """指定された期間内の日付リストを 'YYYYMMDD' 形式で生成する"""
    try:
        start_date = datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
        end_date = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    except ValueError:
        print(
            f"エラー: 日付形式が正しくありません。'YYYYMMDD' 形式で指定してください。"
        )
        return []
    if start_date > end_date:
        return []
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime("%Y%m%d"))
        current_date += timedelta(days=1)
    return dates


def parse_deli_ids_from_html(html: str) -> List[str]:
    """HTMLから審議ID (deli_id) のリストを抽出する"""
    soup = BeautifulSoup(html, "html.parser")
    deli_ids = [
        match.group(1)
        for a_tag in soup.find_all("a", href=True)
        if (match := re.search(r"deli_id=(\d+)", a_tag["href"]))
    ]
    unique_ids = sorted(list(set(deli_ids)), key=int)
    print(f"  → 発見された deli_id 数: {len(unique_ids)}")
    return unique_ids


# ==== 核心処理 ============================================================


def process_deli_id(deli_id: str):
    """
    単一の deli_id を処理する。HTMLをダウンロードし、空でないかチェックして保存する。
    """
    html_path = os.path.join(HTML_DIR, f"{deli_id}.html")
    if os.path.exists(html_path):
        print(f"    ▷ スキップ: {deli_id}.html は既に存在します。")
        return

    detail_url = f"{BASE_URL}?ex=VL&deli_id={deli_id}"
    print(f"    ▷ HTMLをダウンロード中: {detail_url}")
    time.sleep(DETAIL_SLEEP)

    try:
        res = requests.get(detail_url)
        res.encoding = "euc-jp"
        html_text = res.text

        # HTMLが実質的に空でないかチェック
        if is_html_empty(html_text):
            print(f"    ⚠ 空のHTMLを検出: {deli_id}。保存せず、空リストに追加します。")
            empty_ids = load_empty_html_ids()
            empty_ids.add(int(deli_id))
            save_empty_html_ids(empty_ids)
            return

        # HTMLを保存
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"    ✔ 保存完了 → {html_path}")

    except requests.RequestException as e:
        print(f"    !! ダウンロードエラー ({deli_id}): {e}")
    except Exception as e:
        print(f"    !! 不明なエラー ({deli_id}): {e}")


def fetch_by_date_range(start_date: str, end_date: str):
    """指定された期間の日付ごとに審議一覧を取得し、各審議のHTMLを保存する"""
    dates = get_date_range(start_date, end_date)
    if not dates:
        print("処理対象の日付がありません。")
        return
    print(f"\n--- 日付範囲指定での取得開始 ({start_date} ～ {end_date}) ---")

    for i, date_str in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] 日付を処理中: {date_str}")
        time.sleep(LIST_SLEEP)
        list_url = f"{BASE_URL}?ex=VL&u_day={date_str}"
        try:
            res = requests.get(list_url)
            res.encoding = "euc-jp"
            deli_ids = parse_deli_ids_from_html(res.text)
            for deli_id in deli_ids:
                process_deli_id(deli_id)
        except requests.RequestException as e:
            print(f"  !! 一覧ページの取得に失敗しました ({date_str}): {e}")
            continue
    print("--- 日付範囲指定での取得完了 ---")


# ==== 欠番処理・クリーンアップ ================================================


def list_downloaded_deli_ids(html_dir: str = HTML_DIR) -> List[int]:
    """保存先のフォルダから、ダウンロード済みの deli_id のリストを取得する"""
    if not os.path.exists(html_dir):
        return []
    ids = [
        int(fname.replace(".html", ""))
        for fname in os.listdir(html_dir)
        if fname.endswith(".html") and fname.replace(".html", "").isdigit()
    ]
    return sorted(ids)


def get_missing_deli_ids(html_dir: str = HTML_DIR) -> List[int]:
    """ダウンロード済みのIDリストを基に、欠番となっているIDを検出する"""
    print("\n--- 欠番チェック開始 ---")
    downloaded_ids = list_downloaded_deli_ids(html_dir)
    if not downloaded_ids:
        print("ダウンロード済みのファイルがないため、欠番チェックをスキップします。")
        return []

    # 最小IDから最大IDまでの全てのIDのセットを作成
    full_range = set(range(min(downloaded_ids), max(downloaded_ids) + 1))

    # 欠番 = (全てのID) - (ダウンロード済みのID) - (空だとわかっているID)
    missing = sorted(list(full_range - set(downloaded_ids) - load_empty_html_ids()))

    if missing:
        print(f"発見された欠番ID数: {len(missing)}件")
    else:
        print("欠番は見つかりませんでした。")
    print("--- 欠番チェック完了 ---")
    return missing


def clean_empty_html_files(html_dir: str = HTML_DIR):
    """既存のHTMLファイルをスキャンし、空のものを削除して記録する"""
    print("\n--- 既存ファイルのクリーンアップ開始 ---")
    removed_ids = []
    if not os.path.exists(html_dir):
        print("HTMLフォルダが存在しないため、クリーンアップをスキップします。")
        return

    for fname in os.listdir(html_dir):
        if not (fname.endswith(".html") and fname.replace(".html", "").isdigit()):
            continue

        html_path = os.path.join(html_dir, fname)
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                if is_html_empty(f.read()):
                    deli_id = int(fname.replace(".html", ""))
                    removed_ids.append(deli_id)
        except Exception as e:
            print(f"  !! ファイル読み込み/チェックエラー ({fname}): {e}")

    if removed_ids:
        print(f"空のHTMLファイルを{len(removed_ids)}件削除します: {removed_ids}")
        for deli_id in removed_ids:
            os.remove(os.path.join(html_dir, f"{deli_id}.html"))

        empty_ids = load_empty_html_ids()
        empty_ids.update(removed_ids)
        save_empty_html_ids(empty_ids)
        print("空IDリストを更新しました。")
    else:
        print("削除対象の空ファイルはありませんでした。")
    print("--- クリーンアップ完了 ---")


# ==== メインエントリ =======================================================


def main():
    """コマンドライン引数を解釈して、全体の処理を実行する"""
    parser = argparse.ArgumentParser(
        description="衆議院インターネット審議中継からHTMLデータを取得・管理するツール",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--start",
        type=str,
        help="取得を開始する日付 (YYYYMMDD形式)。\n省略した場合は当日になります。",
    )
    parser.add_argument(
        "-e",
        "--end",
        type=str,
        help="取得を終了する日付 (YYYYMMDD形式)。\n省略した場合は開始日と同じ日付になります。",
    )
    args = parser.parse_args()

    today = datetime.today().strftime("%Y%m%d")
    start = args.start or today
    end = args.end or start

    # 保存先フォルダがなければ作成
    os.makedirs(HTML_DIR, exist_ok=True)

    # 1. 指定された日付範囲でHTMLを取得
    fetch_by_date_range(start, end)

    # 2. 欠番IDを取得して再ダウンロード
    missing_ids = get_missing_deli_ids()
    if missing_ids:
        print(f"\n--- 欠番ID ({len(missing_ids)}件) の取得開始 ---")
        for i, deli_id in enumerate(missing_ids, 1):
            print(f"[{i}/{len(missing_ids)}] 欠番IDを処理中: {deli_id}")
            process_deli_id(str(deli_id))
        print("--- 欠番IDの取得完了 ---")

    # 3. 既存ファイルに空のものがないか最終チェックとクリーンアップ
    clean_empty_html_files()

    print("\nすべての処理が完了しました。")


if __name__ == "__main__":
    main()
