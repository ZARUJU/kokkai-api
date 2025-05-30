import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from .models import ShuShitsumonData, ShuShitsumonList, ShuShitsumonListData


def get_url(session: int) -> str:
    """
    session >= 148 → itdb_shitsumon.nsf
    session  < 148 → itdb_shitsumona.nsf
    session は常に 3 桁のゼロ埋め文字列を使用
    """
    # 3桁未満なら左側を '0' で埋める
    session_str = f"{session:03d}"
    base = "itdb_shitsumon" if session >= 148 else "itdb_shitsumona"
    return f"https://www.shugiin.go.jp/internet/{base}.nsf/html/shitsumon/kaiji{session_str}_l.htm"


def fix_url(href: str, base_url: str) -> str:
    """相対パス／絶対パスを問わず、正しい絶対 URL に変換"""
    return urljoin(base_url, href) if href else None


def get_qa_shu_list_data(session: int) -> ShuShitsumonListData:
    url = get_url(session)
    res = requests.get(url)
    # ページは Shift_JIS なので明示的に設定
    res.encoding = "shift_jis"

    soup = BeautifulSoup(res.text, "html.parser")
    # 相対リンク解決用のベース URL（同じディレクトリ）
    page_base = url.rsplit("/", 1)[0] + "/"

    extracted = []
    table = soup.find("table", id="shitsumontable")
    if table:
        # ヘッダー行から各列のテキスト→インデックスをマッピング
        header = table.find("tr")
        cols_map = {
            th.get_text(strip=True).replace("\n", ""): idx
            for idx, th in enumerate(header.find_all("th"))
        }

        # データ行を順に処理
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            def get_text(key: str) -> str | None:
                idx = cols_map.get(key)
                if idx is not None and idx < len(cols):
                    return cols[idx].get_text(strip=True)
                return None

            def get_href(key: str) -> str | None:
                idx = cols_map.get(key)
                if idx is not None and idx < len(cols):
                    a = cols[idx].find("a")
                    if a and a.has_attr("href"):
                        return a["href"]
                return None

            # 番号は数字でなければ None
            num_text = get_text("番号")
            number = int(num_text) if num_text and num_text.isdigit() else None

            item = ShuShitsumonData(
                番号=number,
                質問件名=get_text("質問件名"),
                提出者氏名=get_text("提出者氏名"),
                経過状況=get_text("経過状況"),
                経過情報リンク=fix_url(get_href("経過情報"), page_base),
                質問情報HTMLリンク=fix_url(get_href("質問情報(HTML)"), page_base),
                答弁情報HTMLリンク=fix_url(get_href("答弁情報(HTML)"), page_base),
            )
            extracted.append(item)

    # Pydantic モデルへ詰め替え
    list_obj = ShuShitsumonList(shitsumon_list=extracted)
    data = ShuShitsumonListData(
        source=url, session=session, list=list_obj.shitsumon_list
    )
    return data


import requests
from bs4 import BeautifulSoup


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
        divs = main_div.find_all("div", class_="gh31divr")
    else:
        # 新しい形式: gh21divr の1つ目と3つ目を削除
        divs = main_div.find_all("div", class_="gh21divr")

    for i in [0, 2]:
        if i < len(divs):
            divs[i].decompose()

    # 最終的な本文テキストを返す
    return main_div.get_text(separator="\n", strip=True)
