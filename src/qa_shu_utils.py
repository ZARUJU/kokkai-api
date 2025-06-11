import os
import time
import re
from pathlib import Path
from typing import Optional, List, Literal, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import (
    ShuShitsumonData,
    ShuShitsumonList,
    ShuShitsumonStatusBefore,
)
from src.utils import read_from_json, write_to_json, convert_japanese_date

# 定数定義
SESSION_THRESHOLD = 148
BREADCRUMB_IDS = ["breadcrumb", "TopContents"]
CIRCLE_NUM_MAP = {
    "①": "(1)",
    "②": "(2)",
    "③": "(3)",
    "④": "(4)",
    "⑤": "(5)",
    "⑥": "(6)",
    "⑦": "(7)",
    "⑧": "(8)",
    "⑨": "(9)",
    "⑩": "(10)",
    "⑪": "(11)",
    "⑫": "(12)",
    "⑬": "(13)",
    "⑭": "(14)",
    "⑮": "(15)",
}
DIV_CLASS_MAP: dict[str, Tuple[str, str]] = {
    "q": ("gh31divr", "gh21divr"),
    "a": ("gh32divr", "gh22divr"),
}
COLUMN_MAP = {
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


def get_session_url(session: int) -> str:
    """
    セッション番号に応じた衆議院質問一覧ページのURLを生成する。

    Args:
        session (int): 取得対象の衆議院セッション番号。

    Returns:
        str: 質問一覧ページの絶対URL。
    """
    session_str = f"{session:03d}"
    base = "itdb_shitsumon" if session >= SESSION_THRESHOLD else "itdb_shitsumona"
    return f"https://www.shugiin.go.jp/internet/{base}.nsf/html/shitsumon/kaiji{session_str}_l.htm"


def resolve_url(href: Optional[str], base_url: str) -> Optional[str]:
    """
    相対パス／絶対パスいずれの場合も正しい絶対URLへ変換する。

    Args:
        href (Optional[str]): <a>タグのhref属性値。
        base_url (str): ページのベースURL（ディレクトリ部分）。

    Returns:
        Optional[str]: 正規化された絶対URL、hrefがNoneまたは空文字列ならNone。
    """
    if not href:
        return None
    return urljoin(base_url, href)


def fetch_soup(url: str, encoding: Optional[str] = None) -> BeautifulSoup:
    """
    指定URLからHTMLを取得し、BeautifulSoupオブジェクトを返す。

    Args:
        url (str): 取得先のURL。
        encoding (Optional[str]): レスポンスの文字エンコーディング。指定があれば適用。

    Returns:
        BeautifulSoup: パース済みBeautifulSoupオブジェクト。
    """
    res = requests.get(url)
    if encoding:
        res.encoding = encoding
    return BeautifulSoup(res.text, "html.parser")


def get_qa_shu_list_data(session: int) -> ShuShitsumonList:
    """
    指定セッションの衆議院QA一覧をスクレイピングして構造化データを返す。

    Args:
        session (int): 対象セッション番号。

    Returns:
        ShuShitsumonList: 質問リストを格納したデータモデル。
    """
    url = get_session_url(session)
    soup = fetch_soup(url, encoding="shift_jis")
    base = url.rsplit("/", 1)[0] + "/"

    table = soup.find("table", id="shitsumontable")
    items: List[ShuShitsumonData] = []
    if table:
        headers = [
            th.get_text(strip=True).replace("\n", "") for th in table.find_all("th")
        ]
        cols_map = {text: idx for idx, text in enumerate(headers)}

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            def text_of(key: str) -> Optional[str]:
                idx = cols_map.get(key)
                return (
                    cols[idx].get_text(strip=True)
                    if idx is not None and idx < len(cols)
                    else None
                )

            def href_of(key: str) -> Optional[str]:
                idx = cols_map.get(key)
                if idx is None or idx >= len(cols):
                    return None
                a = cols[idx].find("a")
                return a["href"] if a and a.has_attr("href") else None

            num = text_of("番号")
            items.append(
                ShuShitsumonData(
                    number=int(num) if num and num.isdigit() else None,
                    question_subject=text_of("質問件名"),
                    submitter_name=text_of("提出者氏名"),
                    progress_status=text_of("経過状況"),
                    progress_info_link=resolve_url(href_of("経過情報"), base),
                    question_html_link=resolve_url(href_of("質問情報(HTML)"), base),
                    answer_html_link=resolve_url(href_of("答弁情報(HTML)"), base),
                )
            )

    return ShuShitsumonList(source=url, session=session, items=items)


def extract_text_by_selector(
    html: str,
    id: Optional[str] = None,
    class_name: Optional[str] = None,
    separator: str = "",
    strip: bool = True,
) -> Optional[str]:
    """
    HTMLから指定のIDまたはクラス名の要素を抜き出し、テキストを返す。

    Args:
        html (str): パース対象のHTML文字列。
        id (Optional[str]): 取得する要素のid属性。
        class_name (Optional[str]): 取得する要素のclass属性。
        separator (str): テキスト抽出時の区切り文字。
        strip (bool): 前後の空白を削除するかどうか。

    Returns:
        Optional[str]: 抽出テキスト。要素が見つからなければNone。
    """
    soup = BeautifulSoup(html, "html.parser")
    element = (
        soup.find(id=id) if id else soup.find(class_=class_name) if class_name else None
    )
    return element.get_text(separator=separator, strip=strip) if element else None


def normalize_circles(text: str) -> str:
    """
    丸数字(①～⑮)を括弧付きアラビア数字((1)～(15))に置換する。

    Args:
        text (str): 置換対象のテキスト。

    Returns:
        str: 置換後のテキスト。
    """
    for k, v in CIRCLE_NUM_MAP.items():
        text = text.replace(k, v)
    return text


def _get_qa_content(url: str, kind: Literal["q", "a"]) -> str:
    """
    質問(q)または答弁(a)ページの本文部分を抽出する共通処理。

    Args:
        url (str): 質問または答弁のHTMLページURL。
        kind (Literal['q','a']): 'q'なら質問、'a'なら答弁を処理。

    Returns:
        str: 本文テキスト。要素が取れなければ空文字。
    """
    old_format = "itdb_shitsumona.nsf" in url
    soup = fetch_soup(url)
    main = soup.find("div", id="mainlayout")
    if not main:
        return ""

    # パンくず・タイトル除去
    for eid in BREADCRUMB_IDS:
        el = main.find(id=eid)
        if el:
            el.decompose()

    # 古い/新しい形式に応じた不要divを削除
    old_class, new_class = DIV_CLASS_MAP[kind]
    divs = main.find_all("div", class_=old_class if old_format else new_class)
    for idx in (0, 2):
        if idx < len(divs):
            divs[idx].decompose()

    return main.get_text(separator="\n", strip=True)


def get_qa_shu_q(url: str) -> str:
    """
    質問ページの本文テキストを取得する。

    Args:
        url (str): 質問ページのURL。

    Returns:
        str: 質問本文テキスト。
    """
    return _get_qa_content(url, "q")


def get_qa_shu_a(url: str) -> str:
    """
    答弁ページの本文テキストを取得する。

    Args:
        url (str): 答弁ページのURL。

    Returns:
        str: 答弁本文テキスト。
    """
    return _get_qa_content(url, "a")


def _save_html_texts(
    session: int,
    questions: List[ShuShitsumonData],
    link_attr: str,
    subdir: str,
    fetcher,
    wait: float = 1.0,
):
    """
    質問／答弁HTMLからテキストを取得し、Markdownファイルとして保存する汎用関数。

    Args:
        session (int): セッション番号。
        questions (List[ShuShitsumonData]): 質問一覧データリスト。
        link_attr (str): ShuShitsumonDataのリンク属性名。
        subdir (str): 保存先ディレクトリ(qまたはa)。
        fetcher (callable): 取得関数(get_qa_shu_q or get_qa_shu_a)。
        wait (float): リクエスト間の待機時間（秒）。
    """
    base = Path(f"data/qa_shu/complete/{session}/{subdir}")
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)

    for q in questions:
        link = getattr(q, link_attr)
        num = q.number
        if not link or not num:
            continue
        path = base / f"{num}.md"
        if path.exists():
            print(f"[SKIP] 存在: {path}")
            continue
        print(f"[WAIT] {wait}s 後に取得: {link}")
        time.sleep(wait)
        print(f"[FETCH] {link}")
        content = fetcher(link)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def save_qa_shu_question_texts(session: int, wait_second: float = 1.0):
    """
    質問HTMLを取得してMarkdownに保存するラッパー。

    Args:
        session (int): セッション番号。
        wait_second (float): 各リクエスト間の待機時間（秒）。
    """
    data = ShuShitsumonList(**read_from_json(f"data/qa_shu/list/{session}.json"))
    _save_html_texts(
        session, data.items, "question_html_link", "q", get_qa_shu_q, wait_second
    )


def save_qa_shu_answer_texts(session: int, wait_second: float = 1.0):
    """
    答弁HTMLを取得してMarkdownに保存するラッパー。

    Args:
        session (int): セッション番号。
        wait_second (float): 各リクエスト間の待機時間（秒）。
    """
    data = ShuShitsumonList(**read_from_json(f"data/qa_shu/list/{session}.json"))
    _save_html_texts(
        session, data.items, "answer_html_link", "a", get_qa_shu_a, wait_second
    )


def extract_table_data_from_html(html: str) -> dict:
    """
    経過状況ページの<table>を解析し、辞書に変換して返す。

    Args:
        html (str): 取得した経過状況ページのHTML文字列。

    Returns:
        dict: COLUMN_MAPで定義したキーを持つ値の辞書。

    Raises:
        ValueError: mainlayout<div>または<table>が見つからない場合。
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("div", id="mainlayout")
    if not main:
        raise ValueError("id='mainlayout' が見つかりません")
    table = main.find("table")
    if not table:
        raise ValueError("<table> が見つかりません")

    data = {}
    for tr in table.find_all("tr")[1:]:
        cols = tr.find_all("td")
        if len(cols) != 2:
            continue
        jp, val = cols[0].get_text(strip=True), cols[1].get_text(strip=True)
        key = COLUMN_MAP.get(jp)
        if key:
            data[key] = val or None
    return data


def extract_submitter_name(text: Optional[str]) -> Optional[str]:
    """
    提出者文字列から主提出者名を抽出し、「君」以降を除去する。

    Examples:
        "原口　一博君外二名" → "原口　一博"

    Args:
        text (str): 提出者名を含む文字列。

    Returns:
        str: 主提出者の氏名。
    """
    if not text:
        return None
    return re.match(r"^(.*?)君", text).group(1) if "君" in text else text


KANJI_NUM_MAP = {
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


def kanji_to_int(text: str) -> int:
    """Convert simple Kanji numerals (<=99) to integer."""
    if not text:
        return 0
    if text == "十":
        return 10
    if "十" in text:
        tens_part, _, ones_part = text.partition("十")
        tens = 1 if tens_part == "" else KANJI_NUM_MAP.get(tens_part, 0)
        ones = 0 if ones_part == "" else KANJI_NUM_MAP.get(ones_part, 0)
        return tens * 10 + ones
    return KANJI_NUM_MAP.get(text, 0)


def extract_submitter_count(text: Optional[str]) -> int:
    """
    提出者数を算出（主提出者 + 外〇名）。

    Examples:
        "原口　一博君外二名" → 3
        "田中　太郎君" → 1

    Args:
        text (str): 提出者表記。

    Returns:
        int: 提出者人数。
    """
    if not text:
        return 0
    m = re.search(r"外([零〇一二三四五六七八九十]+)名", text)
    extra = kanji_to_int(m.group(1)) if m else 0
    return 1 + extra


def save_status_if_needed(
    session: int,
    question: ShuShitsumonData,
    wait_second: float = 1.0,
    force_if_not_received: bool = False,
):
    """
    経過情報ページのJSONを取得し、保存が必要な場合のみファイル出力する。

    - 既に「答弁受理」で存在する場合はスキップ
    - force_if_not_received=Falseなら、既存ファイルはスキップ

    Args:
        session (int): セッション番号。
        question (ShuShitsumonData): 対象の質問データ。
        wait_second (float): リクエスト間の待機時間（秒）。
        force_if_not_received (bool): 強制取得フラグ。Trueなら既存でも再取得。

    """
    path = Path(f"data/qa_shu/complete/{session}/status/{question.number}.json")
    if (
        path.exists()
        and question.progress_status == "答弁受理"
        and not force_if_not_received
    ):
        print(f"[SKIP] 答弁受理のため: {path}")
        return
    if path.exists() and not force_if_not_received:
        print(f"[SKIP] 既存: {path}")
        return

    print(f"[WAIT] {wait_second}s 後に取得: {question.progress_info_link}")
    time.sleep(wait_second)
    print(f"[FETCH] {question.progress_info_link}")
    html = requests.get(question.progress_info_link).text
    raw = extract_table_data_from_html(html)
    status = ShuShitsumonStatusBefore(**raw)

    data = {
        "session_number": int(status.session_number),
        "session_type": status.session_type,
        "question_number": int(status.question_number),
        "question_subject": status.question_subject,
        "submitter_name": extract_submitter_name(status.submitter_name),
        "submitter_count": extract_submitter_count(status.submitter_name),
        "party_name": status.party_name,
        **{
            k: convert_japanese_date(v)
            for k, v in raw.items()
            if "date" in k or "deadline" in k
        },
        "status": status.status,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    write_to_json(data, path=str(path))
