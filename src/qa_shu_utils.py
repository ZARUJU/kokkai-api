import os, time
from pathlib import Path
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from typing import Optional, List

from src.models import ShuShitsumonData, ShuShitsumonListData
from src.utils import read_from_json


def get_url(session: int) -> str:
    """
    session >= 148 → itdb_shitsumon.nsf
    session  < 148 → itdb_shitsumona.nsf
    session は常に 3 桁のゼロ埋め文字列を使用
    """
    session_str = f"{session:03d}"
    base = "itdb_shitsumon" if session >= 148 else "itdb_shitsumona"
    return f"https://www.shugiin.go.jp/internet/{base}.nsf/html/shitsumon/kaiji{session_str}_l.htm"


def fix_url(href: str, base_url: str) -> Optional[str]:
    """相対パス／絶対パスを問わず、正しい絶対 URL に変換"""
    return urljoin(base_url, href) if href else None


def get_qa_shu_list_data(session: int) -> ShuShitsumonListData:
    url = get_url(session)
    res = requests.get(url)
    res.encoding = "shift_jis"

    soup = BeautifulSoup(res.text, "html.parser")
    page_base = url.rsplit("/", 1)[0] + "/"

    extracted: List[ShuShitsumonData] = []
    table = soup.find("table", id="shitsumontable")
    if table:
        header = table.find("tr")
        cols_map = {
            th.get_text(strip=True).replace("\n", ""): idx
            for idx, th in enumerate(header.find_all("th"))
        }

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            def get_text(key: str) -> Optional[str]:
                idx = cols_map.get(key)
                return (
                    cols[idx].get_text(strip=True)
                    if idx is not None and idx < len(cols)
                    else None
                )

            def get_href(key: str) -> Optional[str]:
                idx = cols_map.get(key)
                if idx is not None and idx < len(cols):
                    a = cols[idx].find("a")
                    return a["href"] if a and a.has_attr("href") else None
                return None

            num_text = get_text("番号")
            number = int(num_text) if num_text and num_text.isdigit() else None

            item = ShuShitsumonData(
                number=number,
                question_subject=get_text("質問件名"),
                submitter_name=get_text("提出者氏名"),
                progress_status=get_text("経過状況"),
                progress_info_link=fix_url(get_href("経過情報"), page_base),
                question_html_link=fix_url(get_href("質問情報(HTML)"), page_base),
                answer_html_link=fix_url(get_href("答弁情報(HTML)"), page_base),
            )
            extracted.append(item)

    data = ShuShitsumonListData(source=url, session=session, questions=extracted)
    return data


def extract_text_by_selector(
    html: str,
    id: str = None,
    class_name: str = None,
    separator: str = "",
    strip: bool = True,
) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if id:
        element = soup.find(id=id)
    elif class_name:
        element = soup.find(class_=class_name)
    else:
        return None
    return element.get_text(separator=separator, strip=strip) if element else None


def normalize_marunumbers(text: str) -> str:
    replace_map = {
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
        # 必要に応じて拡張
    }
    for k, v in replace_map.items():
        text = text.replace(k, v)
    return text


def get_qa_shu_q(url: str) -> str:
    # 147以前かどうか判断
    old: bool = url.split("/")[4] == "itdb_shitsumona.nsf"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    main_div = soup.find("div", id="mainlayout")
    if not main_div:
        return ""

    # 共通：パンくず、タイトル部分は削除
    for element_id in ["breadcrumb", "TopContents"]:
        target = main_div.find(id=element_id)
        if target:
            target.decompose()

    if old:
        # 古い形式: gh31divr の1つ目と3つ目を削除
        divs = main_div.find_all("div", class_="gh31divr")
    else:
        # 新しい形式: gh21divr の1つ目と3つ目を削除
        divs = main_div.find_all("div", class_="gh21divr")

    for i in [0, 2]:
        if i < len(divs):
            divs[i].decompose()

    # 最終的な本文テキストを返す
    return main_div.get_text(separator="\n", strip=True)


def save_qa_shu_question_texts(session: int, wait_second: float = 1.0):
    json_path = f"data/qa_shu/list/{session}.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSONファイルが見つかりません: {json_path}")

    data_dict = read_from_json(json_path)
    data = ShuShitsumonListData(**data_dict)

    for q in data.questions:
        if not q.question_html_link or not q.number:
            continue  # 不完全なデータはスキップ

        save_path = Path(f"data/qa_shu/complete/{session}/{q.number}/q.md")
        if save_path.exists():
            print(f"[SKIP] 既に存在: {save_path}")
            continue

        print(f"[WAIT] {wait_second}s before fetching {q.question_html_link}")
        time.sleep(wait_second)

        print(f"[FETCH] {q.question_html_link}")
        q_text = get_qa_shu_q(q.question_html_link)

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(q_text)


def get_qa_shu_a(url: str) -> str:
    # 147以前かどうか判断
    old: bool = url.split("/")[4] == "itdb_shitsumona.nsf"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    main_div = soup.find("div", id="mainlayout")
    if not main_div:
        return ""

    # 共通：パンくず、タイトル部分は削除
    for element_id in ["breadcrumb", "TopContents"]:
        target = main_div.find(id=element_id)
        if target:
            target.decompose()

    if old:
        # 古い形式: gh31divr の1つ目と3つ目を削除
        divs = main_div.find_all("div", class_="gh32divr")
    else:
        # 新しい形式: gh21divr の1つ目と3つ目を削除
        divs = main_div.find_all("div", class_="gh22divr")

    for i in [0, 2]:
        if i < len(divs):
            divs[i].decompose()

    # 最終的な本文テキストを返す
    return main_div.get_text(separator="\n", strip=True)


def save_qa_shu_answer_texts(session: int, wait_second: float = 1.0):
    json_path = f"data/qa_shu/list/{session}.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSONファイルが見つかりません: {json_path}")

    data_dict = read_from_json(json_path)
    data = ShuShitsumonListData(**data_dict)

    for q in data.questions:
        if not q.question_html_link or not q.number:
            continue  # 不完全なデータはスキップ

        save_path = Path(f"data/qa_shu/complete/{session}/{q.number}/a.md")
        if save_path.exists():
            print(f"[SKIP] 既に存在: {save_path}")
            continue

        print(f"[WAIT] {wait_second}s before fetching {q.question_html_link}")
        time.sleep(wait_second)

        print(f"[FETCH] {q.question_html_link}")
        a_text = get_qa_shu_a(q.question_html_link)

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(a_text)
