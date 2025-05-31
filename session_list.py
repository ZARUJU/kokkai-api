import requests
from bs4 import BeautifulSoup
import json
import re
from src.utils import convert_japanese_date, write_to_json

url = "https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiki.htm"  # ← 正しいURLに変更してください

response = requests.get(url)
response.encoding = "shift_jis"

soup = BeautifulSoup(response.text, "html.parser")
table = soup.find("table")
rows = table.find_all("tr")

sessions = []


# 日数文字列から整数を抽出する関数
def parse_days(text):
    match = re.search(r"\d+", text)
    return int(match.group()) if match else 0


for row in rows[1:]:
    cols = row.find_all("td")
    if len(cols) != 6:
        continue

    # 回次情報の抽出
    session_text = cols[0].get_text(strip=True)
    session_match = re.match(r"第(\d+)回（(.+?)）", session_text)
    session_number = int(session_match.group(1)) if session_match else None
    session_type = session_match.group(2) if session_match else None

    # 会期終了日と解散判定
    raw_end_text = cols[2].get_text(strip=True)
    if "解散" in raw_end_text:
        match = re.search(
            r"(明治|大正|昭和|平成|令和)\s*(\d+|元)年\s*(\d+)月\s*(\d+)日", raw_end_text
        )
        end_date = match.group(0) if match else ""
        dissolved = True
    else:
        end_date = raw_end_text
        dissolved = False

    print(session_number)
    session = {
        "session_number": session_number,
        "session_type": session_type,
        "start_date": convert_japanese_date(cols[1].get_text(strip=True)),
        "end_date": convert_japanese_date(end_date),
        "dissolved": dissolved,
        "total_days": parse_days(cols[3].get_text(strip=True)),
        "initial_days": parse_days(cols[4].get_text(strip=True)),
        "extension_days": parse_days(cols[5].get_text(strip=True)),
    }
    sessions.append(session)

print(json.dumps(sessions, ensure_ascii=False, indent=2))

write_to_json(data=sessions, path="data/session.json")
