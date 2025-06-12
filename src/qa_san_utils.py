"""
qa_san_utils – 参議院 QA 取得ユーティリティ集
"""

import time
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from src.models import SangiinShitsumonData, SangiinShitsumonList
from src.utils import read_from_json, write_to_json, convert_japanese_date


# ----------------------------------------------------------------------
# ステータス判定
# ----------------------------------------------------------------------
def status_is_received(session: int, question_number: int) -> bool:
    """既存ステータスが『答弁受理』か判定"""
    path = Path(f"data/qa_sangiin/complete/{session}/status/{question_number}.json")
    if not path.exists():
        return False
    data = read_from_json(str(path))
    return data.get("status") == "答弁受理"


# ----------------------------------------------------------------------
# URL / HTML 取得系
# ----------------------------------------------------------------------
def get_session_url(session: int) -> str:
    return (
        f"https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm"
    )


def fetch_soup(url: str, encoding: str = "utf-8") -> BeautifulSoup:
    res = requests.get(url, timeout=10)
    res.encoding = encoding
    return BeautifulSoup(res.text, "html.parser")


def resolve_url(page_url: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    base = page_url.rsplit("/", 1)[0] + "/"
    return urljoin(base, href)


# ----------------------------------------------------------------------
# 一覧取得
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# 質問／答弁本文保存
# ----------------------------------------------------------------------
def _save_texts(
    session: int,
    items: List[SangiinShitsumonData],
    attr: str,
    subdir: str,
    wait: float = 1.0,
):
    """
    HTML → Markdown 保存
    『答弁受理 かつ Markdown が存在』時のみ取得をスキップ
    """
    base = Path(f"data/qa_sangiin/complete/{session}/{subdir}")
    base.mkdir(parents=True, exist_ok=True)

    for item in items:
        num = item.number
        link = getattr(item, attr)
        if num is None or not link:
            continue

        path = base / f"{num}.md"

        # --- スキップ条件 ---
        if path.exists() and status_is_received(session, num):
            print(f"[SKIP] 受理済み & ファイル有 (session={session}, id={num})")
            continue

        # --- 取得・保存 ---
        if path.exists():
            print(f"[REFETCH] {path} (未受理・再取得)")

        print(f"[WAIT] {wait}s -> {link}")
        time.sleep(wait)
        print(f"[FETCH] {link}")
        text = fetch_soup(link).get_text(separator="\n", strip=True)
        path.write_text(text, encoding="utf-8")


def save_question_texts(session: int, wait: float = 1.0):
    data = get_qa_sangiin_list(session)
    _save_texts(session, data.items, "question_html_link", "q", wait)


def save_answer_texts(session: int, wait: float = 1.0):
    data = get_qa_sangiin_list(session)
    _save_texts(session, data.items, "answer_html_link", "a", wait)


# ----------------------------------------------------------------------
# 経過状況ページ（プログレス）処理
# ----------------------------------------------------------------------
def extract_table_data_from_html(html: str) -> Dict[str, Optional[str]]:
    """経過状況ページ HTML から各種情報を抽出し status を判定"""
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

    # --- 回次・種別 ---
    header = soup.find("p", class_="exp")
    if header:
        import re

        m = re.match(r"第(\d+)回国会（(.+?)）", header.get_text(strip=True))
        if m:
            data["session_number"] = int(m.group(1))
            data["session_type"] = m.group(2)

    tables = soup.find_all("table", class_="list_c")

    # テーブル 0: 件名・回次・番号
    if len(tables) > 0:
        for row in tables[0].find_all("tr"):
            cols = row.find_all(["th", "td"])
            for i in range(0, len(cols) - 1, 2):
                key = cols[i].get_text(strip=True)
                val = cols[i + 1].get_text(strip=True)
                if key == "件名":
                    data["question_subject"] = val
                elif key == "提出回次":
                    data["session_number"] = int(val.replace("回", ""))
                elif key == "提出番号":
                    data["question_number"] = int(val)

    # テーブル 1: 提出日・提出者
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

    # テーブル 3: 転送日・答弁書受領日
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

    # --- status 判定 ---
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
    経過状況ページを取得して JSON 保存。
    『答弁受理』なら再取得不要（ただし force_if_not_received=True で再取得可）
    """
    path = Path(f"data/qa_sangiin/complete/{session}/status/{question_number}.json")

    if path.exists() and not force_if_not_received:
        if status_is_received(session, question_number):
            print(f"[SKIP] 答弁受理済み: {path}")
            return
        print(f"[SKIP] 既存ファイルあり（未受理）: {path}")
        return

    print(f"[WAIT] {wait_second}s 後に取得: {progress_info_link}")
    time.sleep(wait_second)
    print(f"[FETCH] {progress_info_link}")

    res = requests.get(progress_info_link, timeout=10)
    res.encoding = "utf-8"
    html = res.text
    raw = extract_table_data_from_html(html)

    data = {
        **raw,
        "submitted_date": convert_japanese_date(raw.get("submitted_date")),
        "cabinet_transfer_date": convert_japanese_date(
            raw.get("cabinet_transfer_date")
        ),
        "reply_received_date": convert_japanese_date(raw.get("reply_received_date")),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    write_to_json(data, path=str(path))
