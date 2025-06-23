import os
import re
import json
import argparse
from bs4 import BeautifulSoup
from datetime import datetime

# ==== 定数定義 ============================================================
# HTMLファイルが格納されているディレクトリ
HTML_DIR = "data/shugiintv/html"
# 抽出したJSONファイルを保存するディレクトリ
JSON_DIR = "data/shugiintv/json"
# 衆議院TVの元URL（JSON内のURL生成用）
BASE_URL = "https://www.shugiintv.go.jp/jp/index.php"

# ==== ユーティリティ関数 ===================================================


def japanese_to_iso(date_str: str) -> str:
    """
    日本語形式の日付文字列（例: "2025年5月7日 (水)"）を "YYYY-MM-DD" 形式に変換する。
    """
    if not date_str:
        return None
    try:
        # "年", "月", "日" を使って正規表現で数値を抽出
        match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_str)
        if not match:
            # 見つからない場合はNoneを返す
            return None
        year, month, day = match.groups()
        # datetimeオブジェクトに変換してからフォーマット
        dt = datetime(int(year), int(month), int(day))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        # 変換に失敗した場合はNoneを返す
        return None


# ==== 抽出処理 ============================================================


def parse_html_to_json(html_text: str, deli_id: str) -> dict:
    """
    HTML文字列を解析し、会議情報を格納した辞書（JSONのもと）を返す。
    """
    soup = BeautifulSoup(html_text, "html.parser")
    date_text = None
    meeting_name = None

    # 「開会日」「会議名」などをテーブルから抽出
    # #library テーブル内の情報を探す
    lib_table = soup.select_one("#library table")
    if lib_table:
        for row in lib_table.select("tr"):
            cells = row.select("td")
            if len(cells) >= 4:
                key = cells[1].get_text(strip=True)
                value = cells[3].get_text(strip=True)
                if key == "開会日":
                    date_text = value
                elif key == "会議名":
                    # 会議名の後ろに " (第1回)" のような表記があれば削除
                    meeting_name = value.split(" (")[0]

    # 「案件」を抽出
    topics = []
    # #library2 テーブル群から「案件：」というテキストを含むものを探す
    for table in soup.select("#library2 table"):
        if table.find(string=lambda s: isinstance(s, str) and s.strip() == "案件："):
            # 該当テーブル内のセルからテキストを取得
            for cell in table.select("td"):
                text = cell.get_text(strip=True)
                # "案件："自体は除外
                if text and text != "案件：":
                    topics.append(text)
            break  # 案件テーブルが見つかったらループを抜ける

    # 「発言者」を抽出
    speakers = set()
    # a.play_vod クラスを持つリンク（ビデオ再生リンク）から名前を取得
    for a_tag in soup.select("a.play_vod"):
        speaker_name = a_tag.get_text(strip=True)
        if speaker_name:
            speakers.add(speaker_name)

    # ★★★ 変更点 ★★★
    # リストから「はじめから再生」を除去
    speakers.discard("はじめから再生")

    # 案件と発言者が重複している場合があるため、差分を取る
    speakers -= set(topics)

    # 元ページのURLを生成
    detail_url = f"{BASE_URL}?ex=VL&deli_id={deli_id}"

    # 抽出した情報を辞書にまとめる
    return {
        "deli_id": int(deli_id),
        "date_time": japanese_to_iso(date_text),
        "meeting_name": meeting_name,
        "topics": topics,
        "speakers": sorted(list(speakers)),  # ソートして順序を固定
        "url": detail_url,
    }


def process_all_html_files(rebuild: bool = False):
    """
    HTMLディレクトリ内のすべてのHTMLファイルを処理し、JSONとして保存する。
    """
    # 保存先ディレクトリがなければ作成
    os.makedirs(JSON_DIR, exist_ok=True)

    if not os.path.exists(HTML_DIR):
        print(f"エラー: HTMLディレクトリ '{HTML_DIR}' が見つかりません。")
        return

    # 処理対象のHTMLファイルリストを取得
    html_files = [f for f in os.listdir(HTML_DIR) if f.endswith(".html")]

    if not html_files:
        print("処理対象のHTMLファイルが見つかりませんでした。")
        return

    print(f"{len(html_files)} 件のHTMLファイルを処理します...")

    processed_count = 0
    error_count = 0

    for i, filename in enumerate(html_files, 1):
        deli_id = filename.replace(".html", "")
        if not deli_id.isdigit():
            continue  # 数字でないファイルはスキップ

        html_path = os.path.join(HTML_DIR, filename)
        json_path = os.path.join(JSON_DIR, f"{deli_id}.json")

        # rebuild=False の場合、既存のJSONはスキップ
        if not rebuild and os.path.exists(json_path):
            continue

        print(f"[{i}/{len(html_files)}] 処理中: {filename}")

        try:
            # HTMLファイルはUTF-8で保存されているため、読み込み時もUTF-8を指定します。
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # HTMLから情報を抽出
            data = parse_html_to_json(html_content, deli_id)

            # JSONファイルに書き込み
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            processed_count += 1

        except Exception as e:
            print(f"  !! エラー: {filename} の処理中に問題が発生しました: {e}")
            error_count += 1

    print("\n処理完了。")
    print(f"  - 新規/更新ファイル数: {processed_count}")
    print(f"  - エラー発生数: {error_count}")


# ==== メインエントリ =======================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ローカルのHTMLファイルから会議情報を抽出し、JSONとして保存するツール。"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",  # この引数が指定されるとTrueになる
        help="このフラグを立てると、既存のJSONファイルも再生成します。",
    )
    args = parser.parse_args()

    process_all_html_files(rebuild=args.rebuild)
