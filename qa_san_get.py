import requests
import json
import re
import time
import argparse
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import List, Dict, Optional
from urllib.parse import urljoin
from pathlib import Path

from src.models import Inquiry, InquiryInfoList, InquiryStatus


# --- ユーティリティ関数 ---


def write_to_json(data: dict, path: str):
    """辞書データをJSONファイルに書き込む"""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def fetch_and_save_html(url: str, output_path_str: str):
    """指定されたURLからHTMLを取得し、ファイルに保存する"""
    if not url:
        return
    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"    -> HTMLを保存しました: {output_path_str}")
    except requests.exceptions.RequestException as e:
        print(f"    -> HTMLの取得に失敗しました: {url}, Error: {e}")


def convert_japanese_date_to_iso(jp_date_str: str) -> str:
    """和暦の日付文字列をISO 8601形式 (YYYY-MM-DD) に変換する"""
    if not jp_date_str or jp_date_str.isspace():
        return ""
    jp_date_str = jp_date_str.strip()
    era_map = {
        "明治": 1868 - 1,
        "大正": 1912 - 1,
        "昭和": 1926 - 1,
        "平成": 1989 - 1,
        "令和": 2019 - 1,
    }
    pattern = re.compile(
        r"(明治|大正|昭和|平成|令和)\s*(\d+|元)\s*年\s*(\d+)\s*月\s*(\d+)\s*日"
    )
    match = pattern.search(jp_date_str)
    if not match:
        return ""
    era, year_str, month, day = match.groups()
    year = int(year_str) if year_str != "元" else 1
    ad_year = era_map[era] + year
    return f"{ad_year:04d}-{int(month):02d}-{int(day):02d}"


# --- データ取得関数 ---


def create_sangiin_inquiry_info_list(session: int) -> InquiryInfoList:
    """参議院の特定会期の質問主意書一覧を取得し、リストを返す"""
    base_url = f"https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/"
    list_url = urljoin(base_url, "syuisyo.htm")

    print(f"リスト取得対象URL: {list_url}")
    response = requests.get(list_url)
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="list_c")
    if not table:
        raise ValueError(f"質問一覧のテーブルが見つかりませんでした (会期: {session})")

    inquiries = []
    rows = table.find_all("tr")

    for i in range(0, len(rows), 3):
        if i + 2 >= len(rows):
            continue
        tr1, tr2, tr3 = rows[i], rows[i + 1], rows[i + 2]

        try:
            title_tag = tr1.find("a", class_="Graylink")
            subject = title_tag.get_text(strip=True) if title_tag else ""
            progress_info_link = (
                urljoin(base_url, title_tag["href"])
                if title_tag and title_tag.has_attr("href")
                else ""
            )

            tds_2 = tr2.find_all(["th", "td"])
            number = int(tds_2[0].get_text(strip=True))
            submitter = tds_2[2].get_text(strip=True)

            question_html_link, answer_html_link = "", ""
            all_links = tr2.find_all("a") + tr3.find_all("a")
            for link in all_links:
                text = link.get_text(strip=True)
                href = urljoin(base_url, link["href"])
                if "質問本文（html）" in text:
                    question_html_link = href
                elif "答弁本文（html）" in text:
                    answer_html_link = href

            inquiry = Inquiry(
                number=number,
                subject=subject,
                submitter=submitter,
                progress_info_link=progress_info_link,
                question_html_link=question_html_link,
                answer_html_link=answer_html_link,
            )
            inquiries.append(inquiry)
        except (ValueError, IndexError, AttributeError, TypeError) as e:
            print(f"Skipping a row due to parsing error: {e}")

    return InquiryInfoList(source=list_url, items=inquiries)


def get_sangiin_inquiry_status(
    inquiry: Inquiry, session: int
) -> Optional[InquiryStatus]:
    """参議院の経過情報ページからステータス情報を取得する"""
    if not inquiry.progress_info_link:
        print(
            f"警告: 質問番号 {inquiry.number} には経過情報リンクがありません。スキップします。"
        )
        return None
    try:
        response = requests.get(inquiry.progress_info_link)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
    except requests.exceptions.RequestException as e:
        print(
            f"エラー: 質問番号 {inquiry.number} の経過情報取得に失敗しました。URL: {inquiry.progress_info_link}, Error: {e}"
        )
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    data_map: Dict[str, str] = {}

    tables = soup.find_all("table", class_="list_c")
    if not tables:
        print(f"警告: 質問番号 {inquiry.number} の経過情報テーブルが見つかりません。")
        return None

    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).replace("　", "")
                value = cells[1].get_text(strip=True)
                data_map[key] = value

    question_date = convert_japanese_date_to_iso(data_map.get("提出日", ""))
    cabinet_date = convert_japanese_date_to_iso(data_map.get("転送日", ""))
    answer_date = convert_japanese_date_to_iso(data_map.get("答弁書受領日", ""))

    status = ""
    if answer_date:
        status = "答弁受理"
    elif cabinet_date:
        status = "内閣転送"
    elif question_date:
        status = "質問受理"

    return InquiryStatus(
        session=session,
        number=inquiry.number,
        subject=inquiry.subject,
        submitter=inquiry.submitter,
        question_date=question_date,
        cabinet_date=cabinet_date,
        answer_date=answer_date,
        status=status,
    )


# --- 実行ロジック ---


def process_session(session_number: int):
    """指定された会期の参議院質問主意書データを一括で取得・保存する"""
    try:
        print(f"--- 処理開始: 参議院 第{session_number}回国会 ---")
        inquiry_list = create_sangiin_inquiry_info_list(session_number)
        print(f"{len(inquiry_list.items)}件の質問が見つかりました。")

        # 保存先ディレクトリを 'qa_san' に指定
        list_output_path = f"data/qa_san/list/{session_number}.json"
        write_to_json(data=inquiry_list.model_dump(), path=list_output_path)
        print(f"質問リストを '{list_output_path}' に保存しました。")

        print("各質問の詳細情報を取得・保存します...")
        total_items = len(inquiry_list.items)
        for i, inquiry_item in enumerate(inquiry_list.items):
            print(f"  処理中: {i + 1}/{total_items} (質問番号: {inquiry_item.number})")

            action_taken = False

            # 1. ステータス情報の取得と保存
            status_path = Path(
                f"data/qa_san/detail/{session_number}/status/{inquiry_item.number}.json"
            )
            if not status_path.exists():
                action_taken = True
                status_info = get_sangiin_inquiry_status(inquiry_item, session_number)
                if status_info:
                    write_to_json(status_info.model_dump(), str(status_path))
                    print(f"    -> ステータス情報を保存しました: {status_path}")
            else:
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    if existing_data.get("status") != "答弁受理":
                        action_taken = True
                        print(
                            "    -> ステータスが「答弁受理」ではないため、再取得します。"
                        )
                        status_info = get_sangiin_inquiry_status(
                            inquiry_item, session_number
                        )
                        if status_info:
                            write_to_json(status_info.model_dump(), str(status_path))
                            print(f"    -> ステータス情報を更新しました: {status_path}")
                    else:
                        print(
                            "    -> ステータスは既に「答弁受理」のためスキップします。"
                        )
                except (json.JSONDecodeError, IOError) as e:
                    action_taken = True
                    print(
                        f"    -> 既存ステータスファイルの読み込みに失敗({e})。再取得します。"
                    )
                    status_info = get_sangiin_inquiry_status(
                        inquiry_item, session_number
                    )
                    if status_info:
                        write_to_json(status_info.model_dump(), str(status_path))

            # 2. 質問HTMLの取得と保存
            q_html_path = Path(
                f"data/qa_san/detail/{session_number}/q_html/{inquiry_item.number}.html"
            )
            if not q_html_path.exists():
                action_taken = True
                fetch_and_save_html(inquiry_item.question_html_link, str(q_html_path))
            else:
                print(f"    -> 質問HTMLは既に存在します。")

            # 3. 答弁HTMLの取得と保存
            a_html_path = Path(
                f"data/qa_san/detail/{session_number}/a_html/{inquiry_item.number}.html"
            )
            if not a_html_path.exists():
                action_taken = True
                fetch_and_save_html(inquiry_item.answer_html_link, str(a_html_path))
            else:
                print("    -> 答弁HTMLは既に存在します。")

            if action_taken:
                time.sleep(1)

        print(f"第{session_number}回国会の全質問の詳細情報処理が完了しました。")
        print("-" * 30 + "\n")

    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"第{session_number}回国会の処理中に致命的なエラーが発生しました: {e}")
        print("-" * 30 + "\n")


def get_latest_session_from_file(file_path: str) -> Optional[int]:
    """JSONファイルから最新の会期番号を取得する"""
    session_file = Path(file_path)
    if not session_file.exists():
        print(f"エラー: セッションファイル '{file_path}' が見つかりません。")
        return None
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            sessions_data = json.load(f)
        if not isinstance(sessions_data, list) or not sessions_data:
            print(f"エラー: '{file_path}' が空か、またはリスト形式ではありません。")
            return None

        # 'session_number' を持ち、その値が「整数」である有効なエントリのみをフィルタリング
        valid_sessions = [
            s
            for s in sessions_data
            if isinstance(s, dict) and isinstance(s.get("session_number"), int)
        ]

        if not valid_sessions:
            print(
                f"エラー: '{file_path}' 内に、整数値の 'session_number' を持つ有効なデータが見つかりません。"
            )
            return None

        latest_session = max(valid_sessions, key=lambda x: x["session_number"])
        return latest_session["session_number"]
    except (json.JSONDecodeError, IOError) as e:
        print(f"エラー: '{file_path}' の読み込みまたは解析に失敗しました: {e}")
        return None
    except (KeyError, TypeError) as e:
        print(f"エラー: '{file_path}' のデータ構造が正しくありません: {e}")
        return None


def main():
    """CLIのエントリーポイント"""
    parser = argparse.ArgumentParser(
        description="参議院の質問主意書データを取得するCLIツール",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--session",
        type=int,
        help="取得対象の国会の会期番号。\n指定しない場合は data/session.json から最新のものを自動的に利用します。",
    )
    args = parser.parse_args()

    session_to_process = 0

    if args.session:
        session_to_process = args.session
        print(f"引数で指定された会期を処理します: 第{session_to_process}回国会")
    else:
        print(
            "引数 --session が指定されていません。data/session.json から最新の会期を探します。"
        )
        latest_session_num = get_latest_session_from_file("data/session.json")
        if latest_session_num:
            session_to_process = latest_session_num
            print(f"最新の会期が見つかりました: 第{session_to_process}回国会")
        else:
            print("処理を中止します。--session引数で会期を明示的に指定してください。")
            return

    if session_to_process > 0:
        process_session(session_to_process)


if __name__ == "__main__":
    main()
