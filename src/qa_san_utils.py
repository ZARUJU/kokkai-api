import time
from pathlib import Path
from typing import Optional, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field  # ← Fieldをインポート


class SangiinShitsumonData(BaseModel):
    number: Optional[int] = Field(None)
    question_subject: Optional[str] = Field(None)
    submitter_name: Optional[str] = Field(None)
    question_html_link: Optional[str] = Field(None)
    question_pdf_link: Optional[str] = Field(None)
    answer_html_link: Optional[str] = Field(None)
    answer_pdf_link: Optional[str] = Field(None)


class SangiinShitsumonList(BaseModel):
    session: int
    source: str
    items: List[SangiinShitsumonData]


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
