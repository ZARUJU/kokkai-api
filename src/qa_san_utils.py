import time
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from src.models import SangiinShitsumonData, SangiinShitsumonList
from src.utils import read_from_json, write_to_json, convert_japanese_date


def get_session_url(session: int) -> str:
    return (
        f"https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm"
    )


def fetch_soup(url: str, encoding: str = "utf-8") -> BeautifulSoup:
    res = requests.get(url)
    res.encoding = encoding
    return BeautifulSoup(res.text, "html.parser")


def resolve_url(page_url: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    base = page_url.rsplit("/", 1)[0] + "/"
    return urljoin(base, href)


def get_qa_sangiin_list(session: int) -> SangiinShitsumonList:
    url = get_session_url(session)
    soup = fetch_soup(url)
    table = soup.find("table", class_="list_c")

    items: List[SangiinShitsumonData] = []
    if table:
        trs = table.find_all("tr")
        for i in range(0, len(trs), 3):
            header = trs[i]
            html_row = trs[i + 1] if i + 1 < len(trs) else None
            pdf_row = trs[i + 2] if i + 2 < len(trs) else None
            if not html_row or not pdf_row:
                break

            # 提出番号
            num = None
            th = header.find("th")
            if th and th.has_attr("id"):
                td_num = html_row.find("td", {"headers": th["id"]})
                if td_num:
                    txt = td_num.get_text(strip=True)
                    num = int(txt) if txt.isdigit() else None

            # 件名
            a_subj = header.find("a", class_="Graylink")
            subject = a_subj.get_text(strip=True) if a_subj else None
            progress_info_link = resolve_url(url, a_subj["href"]) if a_subj else None

            # 提出者
            td_sub = html_row.find("td", class_="ta_l")
            submitter = td_sub.get_text(strip=True) if td_sub else None

            # 各リンク
            q_html = html_row.find("a", string="質問本文（html）")
            q_pdf = pdf_row.find("a", string="質問本文（PDF）")
            a_html = html_row.find("a", string="答弁本文（html）")
            a_pdf = pdf_row.find("a", string="答弁本文（PDF）")

            items.append(
                SangiinShitsumonData(
                    number=num,
                    question_subject=subject,
                    submitter_name=submitter,
                    progress_info_link=progress_info_link,
                    question_html_link=resolve_url(
                        url, q_html["href"] if q_html else None
                    ),
                    question_pdf_link=resolve_url(
                        url, q_pdf["href"] if q_pdf else None
                    ),
                    answer_html_link=resolve_url(
                        url, a_html["href"] if a_html else None
                    ),
                    answer_pdf_link=resolve_url(url, a_pdf["href"] if a_pdf else None),
                )
            )

    return SangiinShitsumonList(session=session, source=url, items=items)


def _save_texts(
    session: int,
    items: List[SangiinShitsumonData],
    attr: str,
    subdir: str,
    wait: float = 1.0,
):
    """
    質問／答弁HTMLを取得し、Markdownに保存する内部共通関数。
    """
    base = Path(f"data/qa_sangiin/complete/{session}/{subdir}")
    base.mkdir(parents=True, exist_ok=True)

    for item in items:
        link = getattr(item, attr)
        num = item.number
        if not link or num is None:
            continue
        path = base / f"{num}.md"
        if path.exists():
            print(f"[SKIP] {path} already exists")
            continue
        print(f"[WAIT] {wait}s -> {link}")
        time.sleep(wait)
        print(f"[FETCH] {link}")
        text = fetch_soup(link).get_text(separator="\n", strip=True)
        path.write_text(text, encoding="utf-8")


def save_question_texts(session: int, wait: float = 1.0):
    """
    質問本文HTMLを取得し、data/qa_sangiin/complete/{session}/q/{num}.md へ保存。
    """
    data = get_qa_sangiin_list(session)
    _save_texts(session, data.items, "question_html_link", "q", wait)


def save_answer_texts(session: int, wait: float = 1.0):
    """
    答弁本文HTMLを取得し、data/qa_sangiin/complete/{session}/a/{num}.md へ保存。
    """
    data = get_qa_sangiin_list(session)
    _save_texts(session, data.items, "answer_html_link", "a", wait)


def extract_table_data_from_html(html: str) -> Dict[str, Optional[str]]:
    """
    経過状況ページのHTMLから以下を抽出し、statusを判別して返す。

    - session_number: セッション番号（整数）
    - session_type: セッション種別（常会 or 臨時会など）
    - question_number: 質問番号（整数）
    - question_subject: 件名
    - submitter_name: 提出者名（「君」を除去）
    - submitted_date: 提出日（和暦文字列）
    - cabinet_transfer_date: 転送日（和暦文字列）
    - reply_received_date: 答弁書受領日（和暦文字列）
    - status: 「答弁受理」／「内閣転送」／「質問受理」
    """
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[str, Optional[str]] = {
        "session_number": None,
        "session_type": None,
        "question_number": None,
        "question_subject": None,
        "submitter_name": None,
        "submitted_date": None,
        "cabinet_transfer_date": None,
        "reply_received_date": None,
        "status": None,
    }

    # 回次・種別
    header = soup.find("p", class_="exp")
    if header:
        import re

        m = re.match(r"第(\d+)回国会（(.+?)）", header.get_text(strip=True))
        if m:
            data["session_number"] = int(m.group(1))
            data["session_type"] = m.group(2)

    tables = soup.find_all("table", class_="list_c")

    # -- テーブル①：件名・回次・番号
    if len(tables) > 0:
        for row in tables[0].find_all("tr"):
            cols = row.find_all(["th", "td"])
            # 2つおきに key/value として読む
            for i in range(0, len(cols) - 1, 2):
                key = cols[i].get_text(strip=True)
                val = cols[i + 1].get_text(strip=True)
                if key == "件名":
                    data["question_subject"] = val
                elif key == "提出回次":
                    data["session_number"] = int(val.replace("回", ""))
                elif key == "提出番号":
                    # ここできちんと数値変換
                    data["question_number"] = int(val)

    # -- テーブル②：提出日・提出者
    if len(tables) > 1:
        for row in tables[1].find_all("tr"):
            cols = row.find_all(["th", "td"])
            for i in range(0, len(cols) - 1, 2):
                key = cols[i].get_text(strip=True)
                val = cols[i + 1].get_text(strip=True)
                if key == "提出日":
                    data["submitted_date"] = val
                elif key == "提出者":
                    data["submitter_name"] = (
                        val.replace("君", "").strip().replace("　", "")
                    )

    # -- テーブル④：転送日・答弁書受領日
    if len(tables) > 3:
        for row in tables[3].find_all("tr"):
            cols = row.find_all(["th", "td"])
            for i in range(0, len(cols) - 1, 2):
                key = cols[i].get_text(strip=True)
                val = cols[i + 1].get_text(strip=True)
                if key == "転送日":
                    data["cabinet_transfer_date"] = val
                elif key == "答弁書受領日":
                    data["reply_received_date"] = val

    # -- status 判定
    if data["reply_received_date"]:
        data["status"] = "答弁受理"
    elif data["cabinet_transfer_date"]:
        data["status"] = "内閣転送"
    elif data["submitted_date"]:
        data["status"] = "質問受理"

    return data


def save_status_if_needed(
    session: int,
    question_number: int,
    progress_info_link: str,
    wait_second: float = 1.0,
    force_if_not_received: bool = False,
):
    """
    参議院の経過情報ページのJSONを取得し、保存が必要な場合のみファイル出力する。

    Args:
        session (int): セッション番号。
        question_number (int): 質問番号。
        progress_info_link (str): 経過情報ページのURL。
        wait_second (float): リクエスト間の待機時間（秒）。
        force_if_not_received (bool): 強制取得フラグ。Trueなら既存でも再取得。
    """
    path = Path(f"data/qa_sangiin/complete/{session}/status/{question_number}.json")

    # 既存ファイルのチェック
    if path.exists() and not force_if_not_received:
        existing_data = read_from_json(str(path))
        if existing_data.get("reply_received_date"):
            print(f"[SKIP] 答弁受領済みのため: {path}")
            return
        print(f"[SKIP] 既存: {path}")
        return

    print(f"[WAIT] {wait_second}s 後に取得: {progress_info_link}")
    time.sleep(wait_second)
    print(f"[FETCH] {progress_info_link}")

    res = requests.get(progress_info_link)
    res.encoding = "utf-8"
    html = res.text
    raw_data = extract_table_data_from_html(html)

    # 日付の変換
    data = {
        **raw_data,
        "submitted_date": convert_japanese_date(raw_data.get("submitted_date")),
        "cabinet_transfer_date": convert_japanese_date(
            raw_data.get("cabinet_transfer_date")
        ),
        "reply_received_date": convert_japanese_date(
            raw_data.get("reply_received_date")
        ),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    write_to_json(data, path=str(path))
