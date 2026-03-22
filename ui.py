"""既存の kokkai-api を利用して国会データを閲覧する Flask UI。

役割:
    - FastAPI で公開している配布用 JSON を HTTP 経由で取得する
    - 人物検索、議案一覧、請願一覧、質問主意書一覧と詳細をブラウザで見やすく表示する

入力:
    - 環境変数 `API_BASE_URL` で指定した API エンドポイント
      既定値は `http://127.0.0.1:9000`

出力:
    - Flask が返す HTML

実行例:
    uv run flask --app ui run --port 5001
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
import re

import requests
from flask import Flask, abort, render_template, request

from src.utils import normalize_person_name

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:9000").rstrip("/")
API_TIMEOUT = 15
HOUSE_LABELS = {
    "shugiin": "衆議院",
    "sangiin": "参議院",
}
HOUSE_ID_PREFIX = {
    "shugiin": "shu",
    "sangiin": "san",
}
ROLE_LABELS = {
    "submitter": "提出者",
    "supporter": "賛成者",
    "presenter": "紹介議員",
    "answerer": "答弁者",
}


@dataclass
class ApiRequestError(Exception):
    """API 取得失敗時の情報を保持する例外。"""

    message: str
    status_code: int = 502


app = Flask(__name__)


@app.template_filter("pretty_json")
def pretty_json(value: Any) -> str:
    """JSON を整形済み文字列として返す。"""

    return json.dumps(value, ensure_ascii=False, indent=2)


@app.template_filter("person_key")
def person_key(value: str) -> str:
    """人物名から人物詳細ページ用のキーを返す。"""

    return normalize_person_name(value)


@app.template_filter("role_label")
def role_label(value: str) -> str:
    """内部ロール名を表示用の日本語ラベルへ変換する。"""

    return ROLE_LABELS.get(value, value)


@app.context_processor
def inject_globals() -> dict[str, Any]:
    """全テンプレートで使う共通値を注入する。"""

    path = request.path
    if path.startswith("/people"):
        active_section = "people"
    elif path.startswith("/kaiki"):
        active_section = "kaiki"
    elif path.startswith("/kaigiroku"):
        active_section = "kaigiroku"
    elif path.startswith("/gian"):
        active_section = "gian"
    elif path.startswith("/seigan"):
        active_section = "seigan"
    elif path.startswith("/shitsumon"):
        active_section = "shitsumon"
    else:
        active_section = "home"

    return {
        "api_base_url": API_BASE_URL,
        "house_labels": HOUSE_LABELS,
        "active_section": active_section,
    }


def api_get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """既存 API の JSON を取得する。"""

    url = f"{API_BASE_URL}{path}"
    try:
        response = requests.get(url, params=params, timeout=API_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiRequestError(f"API に接続できませんでした: {url}") from exc

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason
        raise ApiRequestError(
            f"API 取得に失敗しました ({response.status_code}): {detail}",
            status_code=response.status_code,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ApiRequestError(f"API のレスポンスが JSON ではありません: {url}") from exc


def group_attendance_by_section(
    attendance: list[dict[str, Any]], house: str | None = None
) -> list[dict[str, Any]]:
    """出席者を section ごとにまとめてテンプレートへ渡す。"""

    grouped: OrderedDict[str, OrderedDict[tuple[str, str | None], list[str]]] = (
        OrderedDict()
    )
    default_section = "出席委員" if house == "衆議院" else "出席者"
    for item in attendance:
        section = item.get("section") or default_section
        role = item.get("role") or "出席者"
        title = item.get("title")
        grouped.setdefault(section, OrderedDict()).setdefault((role, title), []).append(
            item.get("name", "")
        )

    result = []
    for section, role_groups in grouped.items():
        items = [
            {
                "role": role,
                "title": title,
                "names": names,
                "count": len(names),
            }
            for (role, title), names in role_groups.items()
        ]
        result.append(
            {
                "section": section,
                "items": items,
                "count": sum(item["count"] for item in items),
            }
        )
    return result


def require_house(house: str) -> str:
    """URL パラメータの院種別を検証する。"""

    if house not in HOUSE_LABELS:
        abort(404)
    return house


def render_api_error(exc: ApiRequestError):
    """API エラー画面を返す。"""

    return (
        render_template(
            "error.html",
            title="API エラー",
            message=exc.message,
            status_code=exc.status_code,
        ),
        exc.status_code,
    )


def build_question_id(house: str, session: int, question_number: int) -> str:
    """院種別・回次・番号から質問主意書 ID を組み立てる。"""

    return f"{HOUSE_ID_PREFIX[house]}-{session}-{question_number:03d}"


def build_petition_id(house: str, session: int, petition_number: int) -> str:
    """院種別・回次・番号から請願 ID を組み立てる。"""

    return f"{HOUSE_ID_PREFIX[house]}-seigan-{session}-{petition_number:04d}"


def slugify_label(value: str) -> str:
    """見出しラベルから HTML id 向けの簡易 slug を作る。"""

    text = normalize_person_name(value)
    text = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠]+", "-", text)
    return text.strip("-").lower() or "section"


def group_relations_by_session(
    relations: list[dict[str, Any]], session_field: str
) -> list[dict[str, Any]]:
    """人物関連データを回次ごとにまとめる。"""

    grouped: dict[int | None, list[dict[str, Any]]] = {}
    for relation in relations:
        session = relation.get(session_field)
        grouped.setdefault(session, []).append(relation)

    ordered_sessions = sorted(
        (session for session in grouped if session is not None), reverse=True
    )
    if None in grouped:
        ordered_sessions.append(None)

    return [
        {
            "session_number": session,
            "items": grouped[session],
        }
        for session in ordered_sessions
    ]


@app.get("/")
def index():
    """トップページを返す。"""

    try:
        meta = api_get("/meta")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template("index.html", title="国会データ UI", meta=meta)


@app.get("/kaiki")
def kaiki_index():
    """会期一覧ページを返す。"""

    try:
        kaiki = api_get("/v1/kaiki")
        meta = api_get("/meta")
    except ApiRequestError as exc:
        return render_api_error(exc)

    available_gian_sessions = set(meta["available_gian_sessions"])
    available_kaigiroku_sessions = set(meta.get("available_kaigiroku_sessions", []))
    available_seigan_sessions = {
        house: set(sessions)
        for house, sessions in meta["available_seigan_sessions"].items()
    }
    available_shitsumon_sessions = {
        house: set(sessions)
        for house, sessions in meta["available_shitsumon_sessions"].items()
    }
    kaigiroku_counts: dict[int, int] = {}
    for session in sorted(available_kaigiroku_sessions):
        try:
            dataset = api_get(f"/v1/kaigiroku/list/{session}")
        except ApiRequestError:
            continue
        kaigiroku_counts[session] = len(dataset.get("items", []))

    session_cards = []
    for item in kaiki["items"]:
        session_number = item["number"]
        session_cards.append(
            {
                **item,
                "kaigiroku_count": kaigiroku_counts.get(session_number),
                "links": {
                    "gian": session_number in available_gian_sessions,
                    "kaigiroku": session_number in available_kaigiroku_sessions,
                    "seigan_shugiin": session_number
                    in available_seigan_sessions.get("shugiin", set()),
                    "seigan_sangiin": session_number
                    in available_seigan_sessions.get("sangiin", set()),
                    "shitsumon_shugiin": session_number
                    in available_shitsumon_sessions.get("shugiin", set()),
                    "shitsumon_sangiin": session_number
                    in available_shitsumon_sessions.get("sangiin", set()),
                },
            }
        )

    return render_template(
        "kaiki_list.html",
        title="会期一覧",
        kaiki=kaiki,
        session_cards=session_cards,
    )


@app.get("/people")
def people_index():
    """人物検索ページを返す。"""

    query = request.args.get("q", "").strip()
    try:
        if query:
            results = api_get(
                "/v1/people/search", params={"q": query, "limit": 30, "offset": 0}
            )
            return render_template(
                "people_search.html",
                title="人物検索",
                query=query,
                mode="search",
                results=results,
            )

        people = api_get(
            "/v1/people/index-items",
            params={"limit": 100, "offset": 0, "sort": "relation_total_asc"},
        )
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template(
        "people_search.html",
        title="人物検索",
        query="",
        mode="index",
        results=people,
    )


@app.get("/people/<path:person_key>")
def person_detail(person_key: str):
    """人物詳細ページを返す。"""

    try:
        person = api_get(f"/v1/people/{quote(person_key, safe='')}")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template(
        "person_detail.html",
        title=person["canonical_name"],
        person=person,
        gian_groups=group_relations_by_session(
            person["gian_relations"], "submitted_session"
        ),
        seigan_groups=group_relations_by_session(
            person["seigan_relations"], "session_number"
        ),
        shitsumon_groups=group_relations_by_session(
            person["shitsumon_relations"], "session_number"
        ),
        meeting_groups=group_relations_by_session(
            person.get("meeting_relations", []), "session"
        ),
        speaking_meeting_groups=group_relations_by_session(
            person.get("speaking_meeting_relations", []), "session"
        ),
    )


@app.get("/gian")
def gian_index():
    """議案一覧ページを返す。"""

    try:
        session_index = api_get("/v1/gian/list")
        sessions = session_index["sessions"]
        requested_session = request.args.get("session", type=int)
        default_session = sessions[-1] if sessions else 0
        selected_session = (
            requested_session if requested_session in sessions else default_session
        )
        dataset = (
            api_get(f"/v1/gian/list/{selected_session}") if sessions else {"items": []}
        )
    except ApiRequestError as exc:
        return render_api_error(exc)

    category_order: list[str] = []
    grouped_items: dict[str, list[dict[str, Any]]] = {}
    for item in dataset.get("items", []):
        category = item.get("category") or "分類不明"
        if category not in grouped_items:
            grouped_items[category] = []
            category_order.append(category)
        grouped_items[category].append(item)

    category_groups = [
        {
            "category": category,
            "items": grouped_items[category],
            "count": len(grouped_items[category]),
        }
        for category in category_order
    ]

    return render_template(
        "gian_list.html",
        title="議案一覧",
        sessions=sessions,
        selected_session=selected_session,
        dataset=dataset,
        category_groups=category_groups,
    )


@app.get("/gian/<bill_id>")
def gian_detail(bill_id: str):
    """議案詳細ページを返す。"""

    try:
        bill = api_get(f"/v1/gian/detail/{bill_id}")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template("gian_detail.html", title=bill["title"], bill=bill)


@app.get("/kaigiroku")
def kaigiroku_index():
    """会議録一覧ページを返す。"""

    try:
        session_index = api_get("/v1/kaigiroku/list")
        sessions = session_index["sessions"]
        requested_session = request.args.get("session", type=int)
        default_session = sessions[-1] if sessions else 0
        selected_session = (
            requested_session if requested_session in sessions else default_session
        )
        dataset = (
            api_get(f"/v1/kaigiroku/list/{selected_session}")
            if sessions
            else {"items": []}
        )
    except ApiRequestError as exc:
        return render_api_error(exc)

    sorted_items = sorted(
        dataset.get("items", []),
        key=lambda item: (
            item.get("date") or "",
            item.get("opening_time") or "",
            item.get("issue_id") or "",
        ),
        reverse=True,
    )
    dataset["items"] = sorted_items
    house_counts = Counter(item.get("name_of_house") or "不明" for item in sorted_items)
    latest_date = sorted_items[0].get("date") if sorted_items else None
    return render_template(
        "kaigiroku_list.html",
        title="会議録一覧",
        sessions=sessions,
        selected_session=selected_session,
        dataset=dataset,
        house_counts=house_counts,
        item_count=len(sorted_items),
        latest_date=latest_date,
    )


@app.get("/kaigiroku/<issue_id>")
def kaigiroku_detail(issue_id: str):
    """会議録詳細ページを返す。"""

    try:
        meeting = api_get(f"/v1/kaigiroku/detail/{issue_id}")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template(
        "kaigiroku_detail.html",
        title=f"{meeting['name_of_meeting']} {meeting['issue']}",
        meeting=meeting,
        grouped_attendance=group_attendance_by_section(
            meeting.get("attendance", []), meeting.get("name_of_house")
        ),
    )


@app.get("/seigan/<house>")
def seigan_index(house: str):
    """請願一覧ページを返す。"""

    house = require_house(house)
    try:
        session_index = api_get(f"/v1/seigan/{house}/list")
        sessions = session_index["sessions"]
        requested_session = request.args.get("session", type=int)
        default_session = sessions[-1] if sessions else 0
        selected_session = (
            requested_session if requested_session in sessions else default_session
        )
        dataset = (
            api_get(f"/v1/seigan/{house}/list/{selected_session}")
            if sessions
            else {"items": []}
        )
    except ApiRequestError as exc:
        return render_api_error(exc)

    items = []
    for item in dataset.get("items", []):
        enriched_item = dict(item)
        enriched_item["petition_id"] = build_petition_id(
            house, selected_session, item["petition_number"]
        )
        items.append(enriched_item)

    committee_counts = Counter(
        item.get("committee_name") or "委員会不明" for item in items
    )
    referred_count = sum(1 for item in items if item.get("is_referred"))

    grouped_items: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        committee_name = item.get("committee_name") or "委員会不明"
        grouped_items.setdefault(committee_name, []).append(item)

    committee_groups = [
        {
            "committee_name": committee_name,
            "anchor_id": f"committee-{slugify_label(committee_name)}",
            "count": len(grouped_items[committee_name]),
            "items": grouped_items[committee_name],
        }
        for committee_name, _ in committee_counts.most_common()
    ]

    return render_template(
        "seigan_list.html",
        title=f"{HOUSE_LABELS[house]}請願",
        house=house,
        sessions=sessions,
        selected_session=selected_session,
        item_count=len(items),
        referred_count=referred_count,
        not_referred_count=len(items) - referred_count,
        committee_groups=committee_groups,
        items=items,
    )


@app.get("/seigan/<house>/<petition_id>")
def seigan_detail(house: str, petition_id: str):
    """請願詳細ページを返す。"""

    house = require_house(house)
    try:
        petition = api_get(f"/v1/seigan/{house}/detail/{petition_id}")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template(
        "seigan_detail.html",
        title=petition["title"],
        house=house,
        petition=petition,
    )


@app.get("/shitsumon/<house>")
def shitsumon_index(house: str):
    """質問主意書一覧ページを返す。"""

    house = require_house(house)
    try:
        session_index = api_get(f"/v1/shitsumon/{house}/list")
        sessions = session_index["sessions"]
        requested_session = request.args.get("session", type=int)
        default_session = sessions[-1] if sessions else 0
        selected_session = (
            requested_session if requested_session in sessions else default_session
        )
        dataset = (
            api_get(f"/v1/shitsumon/{house}/list/{selected_session}")
            if sessions
            else {"items": []}
        )
    except ApiRequestError as exc:
        return render_api_error(exc)

    items = []
    for item in dataset.get("items", []):
        enriched_item = dict(item)
        enriched_item["question_id"] = build_question_id(
            house, selected_session, item["question_number"]
        )
        items.append(enriched_item)

    submitter_counts = Counter(
        item.get("submitter_name") or "提出者不明" for item in items
    )
    submitter_summary = [
        {
            "submitter_name": submitter_name,
            "count": count,
            "anchor_id": f"submitter-{slugify_label(submitter_name)}",
        }
        for submitter_name, count in submitter_counts.most_common(8)
    ]

    grouped_items: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        submitter_name = item.get("submitter_name") or "提出者不明"
        grouped_items.setdefault(submitter_name, []).append(item)

    submitter_groups = [
        {
            "submitter_name": submitter_name,
            "anchor_id": f"submitter-{slugify_label(submitter_name)}",
            "count": len(grouped_items[submitter_name]),
            "items": grouped_items[submitter_name],
        }
        for submitter_name, _ in submitter_counts.most_common()
    ]

    return render_template(
        "shitsumon_list.html",
        title=f"{HOUSE_LABELS[house]}質問主意書",
        house=house,
        sessions=sessions,
        selected_session=selected_session,
        item_count=len(items),
        answer_available_count=sum(1 for item in items if item.get("answer_html_url")),
        submitter_summary=submitter_summary,
        submitter_groups=submitter_groups,
        items=items,
    )


@app.get("/shitsumon/<house>/<question_id>")
def shitsumon_detail(house: str, question_id: str):
    """質問主意書詳細ページを返す。"""

    house = require_house(house)
    try:
        question = api_get(f"/v1/shitsumon/{house}/detail/{question_id}")
    except ApiRequestError as exc:
        return render_api_error(exc)

    return render_template(
        "shitsumon_detail.html",
        title=question["title"],
        house=house,
        question=question,
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5001")),
        debug=False,
    )
