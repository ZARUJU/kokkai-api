from __future__ import annotations
import re, time
from pathlib import Path
from typing import List, Optional, Tuple, Literal
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import (
    ShuShitsumonData,
    ShuShitsumonList,
    ShuShitsumonStatusBefore,
)
from src.utils import read_from_json, write_to_json, convert_japanese_date

# ────────────────────────────
# 定数（外部参照の可能性があるもののみ）
# ────────────────────────────
SESSION_THRESHOLD = 148
BREADCRUMB_IDS = ["breadcrumb", "TopContents"]
DIV_CLASS_MAP: dict[str, Tuple[str, str]] = {
    "q": ("gh31divr", "gh21divr"),
    "a": ("gh32divr", "gh22divr"),
}
COLUMN_MAP = {  # 経過状況テーブルの列名マッピング
    "国会回次": "session_number",
    "国会区別": "session_type",
    "質問番号": "question_number",
    "質問件名": "question_subject",
    "提出者名": "submitter_name",
    "会派名": "party_name",
    "質問主意書提出年月日": "submitted_date",
    "内閣転送年月日": "cabinet_transfer_date",
    "答弁延期通知受領年月日": "reply_delay_notice_date",
    "答弁延期期限年月日": "reply_delay_deadline",
    "答弁書受領年月日": "reply_received_date",
    "撤回年月日": "withdrawal_date",
    "撤回通知年月日": "withdrawal_notice_date",
    "経過状況": "status",
}

KANJI_NUM_MAP = {  # 提出者「外〇名」の数値化に使用
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


# ────────────────────────────
# HTML 取得 & 共通ヘルパ
# ────────────────────────────
def _fetch_soup(url: str, encoding: str | None = None) -> BeautifulSoup:
    res = requests.get(url, timeout=15)
    if encoding:
        res.encoding = encoding
    return BeautifulSoup(res.text, "html.parser")


def _resolve_url(href: str | None, base: str) -> str | None:
    return urljoin(base, href) if href else None


# ────────────────────────────
# Public  API
# ────────────────────────────
__all__ = [
    "get_qa_shu_list_data",
    "get_qa_shu_q",
    "get_qa_shu_a",
    "save_status_if_needed",
]


# 1) 質問主意書一覧（質問リスト）取得
def get_qa_shu_list_data(session: int) -> ShuShitsumonList:
    session_str = f"{session:03d}"
    base_dir = "itdb_shitsumon" if session >= SESSION_THRESHOLD else "itdb_shitsumona"
    url = (
        f"https://www.shugiin.go.jp/internet/"
        f"{base_dir}.nsf/html/shitsumon/kaiji{session_str}_l.htm"
    )

    soup = _fetch_soup(url, encoding="shift_jis")
    base = url.rsplit("/", 1)[0] + "/"

    table = soup.find("table", id="shitsumontable")
    items: List[ShuShitsumonData] = []
    if table:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        col_idx = {h: i for i, h in enumerate(headers)}

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            def txt(key):
                idx = col_idx.get(key)
                return cols[idx].get_text(strip=True) if idx is not None else None

            def href(key):
                idx = col_idx.get(key)
                a = cols[idx].find("a") if idx is not None else None
                return a["href"] if a and a.has_attr("href") else None

            num = txt("番号")
            items.append(
                ShuShitsumonData(
                    number=int(num) if num and num.isdigit() else None,
                    question_subject=txt("質問件名"),
                    submitter_name=txt("提出者氏名"),
                    progress_status=txt("経過状況"),
                    progress_info_link=_resolve_url(href("経過情報"), base),
                    question_html_link=_resolve_url(href("質問情報(HTML)"), base),
                    answer_html_link=_resolve_url(href("答弁情報(HTML)"), base),
                )
            )

    return ShuShitsumonList(source=url, session=session, items=items)


# 2) 質問ページ本文取得
def get_qa_shu_q(url: str) -> str:
    return _get_qa_content(url, kind="q")


# 3) 答弁ページ本文取得
def get_qa_shu_a(url: str) -> str:
    return _get_qa_content(url, kind="a")


# 4) 経過状況 JSON 保存
def save_status_if_needed(
    session: int,
    question: ShuShitsumonData,
    wait_second: float = 1.0,
    force_if_not_received: bool = False,
) -> None:
    path = Path(f"data/qa_shu/complete/{session}/status/{question.number}.json")

    # 既存ステータス判定
    if path.exists():
        existing = read_from_json(str(path))
        if existing.get("status") == "答弁受理" and not force_if_not_received:
            print(f"[SKIP] 答弁受理: {path}")
            return
        if not force_if_not_received:
            print(f"[SKIP] 既存: {path}")
            return

    # 取得
    print(f"[WAIT] {wait_second}s → {question.progress_info_link}")
    time.sleep(wait_second)
    html = requests.get(question.progress_info_link, timeout=15).text
    raw = _extract_table_data_from_html(html)
    status = ShuShitsumonStatusBefore(**raw)

    # 整形して保存
    data = {
        "session_number": int(status.session_number),
        "session_type": status.session_type,
        "question_number": int(status.question_number),
        "question_subject": status.question_subject,
        "submitter_name": _extract_submitter_name(status.submitter_name),
        "submitter_count": _extract_submitter_count(status.submitter_name),
        "party_name": status.party_name,
        **{
            k: convert_japanese_date(v)
            for k, v in raw.items()
            if "date" in k or "deadline" in k
        },
        "status": status.status,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_to_json(data, str(path))
    print(f"[SAVE] {path}")


# ────────────────────────────
# 内部関数  ( _ で始める)
# ────────────────────────────
def _get_qa_content(url: str, kind: Literal["q", "a"]) -> str:
    soup = _fetch_soup(url)
    main = soup.find("div", id="mainlayout")
    if not main:
        return ""

    # パンくず削除
    for bid in BREADCRUMB_IDS:
        tag = main.find(id=bid)
        if tag:
            tag.decompose()

    # 旧/新レイアウトに合わせて不要 DIV 除去
    old_format = "itdb_shitsumona.nsf" in url
    old_cls, new_cls = DIV_CLASS_MAP[kind]
    divs = main.find_all("div", class_=old_cls if old_format else new_cls)
    for idx in (0, 2):  # タイトルなど
        if idx < len(divs):
            divs[idx].decompose()

    return main.get_text(separator="\n", strip=True)


def _extract_table_data_from_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("div", id="mainlayout").find("table")  # 例外は外でキャッチ
    data = {}
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        jp, val = tds[0].get_text(strip=True), tds[1].get_text(strip=True)
        key = COLUMN_MAP.get(jp)
        if key:
            data[key] = val or None
    return data


def _extract_submitter_name(text: str | None) -> str | None:
    if not text:
        return None
    m = re.match(r"^(.*?)君", text)
    return m.group(1) if m else text


def _extract_submitter_count(text: str | None) -> int:
    if not text:
        return 0
    m = re.search(r"外([零〇一二三四五六七八九十]+)名", text)
    extra = _kanji_to_int(m.group(1)) if m else 0
    return 1 + extra


def _kanji_to_int(kan: str) -> int:
    if kan == "十":
        return 10
    if "十" in kan:
        tens, _, ones = kan.partition("十")
        return (1 if tens == "" else KANJI_NUM_MAP[tens]) * 10 + KANJI_NUM_MAP.get(
            ones, 0
        )
    return KANJI_NUM_MAP.get(kan, 0)
