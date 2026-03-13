"""会期一覧・議案・質問主意書・人物インデックスの配布用 JSON を公開する FastAPI アプリケーション。

主なエンドポイント:
    - GET /health
    - GET /meta
    - GET /v1/kaiki
    - GET /v1/gian/list
    - GET /v1/gian/list/{session}
    - GET /v1/gian/detail
    - GET /v1/gian/detail/{bill_id}
    - GET /v1/shitsumon/{house}/list
    - GET /v1/shitsumon/{house}/list/{session}
    - GET /v1/shitsumon/{house}/detail
    - GET /v1/shitsumon/{house}/detail/{question_id}
    - GET /v1/people
    - GET /v1/people/search
    - GET /v1/people/{person_key}

入力:
    - data/kaiki.json
    - data/gian/list/*.json
    - data/gian/detail/*.json
    - data/shitsumon/{house}/list/*.json
    - data/shitsumon/{house}/detail/*.json
    - data/people/index.json

実行例:
    uv run api.py
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from src.models import (
    ApiIdListResponse,
    ApiMetaResponse,
    ApiPeopleSearchResponse,
    ApiSessionListResponse,
    DistributedGianDetailDataset,
    DistributedGianListDataset,
    DistributedPeopleDataset,
    DistributedPersonItem,
    KaikiDataset,
    SangiinShitsumonDetailDataset,
    SangiinShitsumonListDataset,
    ShugiinShitsumonDetailDataset,
    ShugiinShitsumonListDataset,
)

API_VERSION = "v1"
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data"
KAIKI_PATH = DATA_ROOT / "kaiki.json"
GIAN_LIST_DIR = DATA_ROOT / "gian" / "list"
GIAN_DETAIL_DIR = DATA_ROOT / "gian" / "detail"
SHITSUMON_ROOT = DATA_ROOT / "shitsumon"
PEOPLE_PATH = DATA_ROOT / "people" / "index.json"


class House(str, Enum):
    """質問主意書 API で受け付ける院種別。"""

    SHUGIIN = "shugiin"
    SANGIIN = "sangiin"


app = FastAPI(
    title="kokkai-api",
    description="会期一覧・議案・質問主意書・人物インデックスの配布用データを公開する API",
    version=API_VERSION,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

router = APIRouter(prefix=f"/{API_VERSION}")


def _read_json(path: Path) -> str:
    """JSON ファイルを UTF-8 で読み込む。"""

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"data not found: {path.relative_to(PROJECT_ROOT)}")
    return path.read_text(encoding="utf-8")


def _paginate(items: list[str], offset: int, limit: int) -> ApiIdListResponse:
    """ID 一覧のページングレスポンスを返す。"""

    return ApiIdListResponse(
        total=len(items),
        offset=offset,
        limit=limit,
        items=items[offset : offset + limit],
    )


@lru_cache(maxsize=1)
def load_kaiki() -> KaikiDataset:
    """会期一覧データを読み込む。"""

    return KaikiDataset.model_validate_json(_read_json(KAIKI_PATH))


@lru_cache(maxsize=256)
def load_gian_list(session: int) -> DistributedGianListDataset:
    """指定回次の議案一覧データを読み込む。"""

    return DistributedGianListDataset.model_validate_json(_read_json(GIAN_LIST_DIR / f"{session}.json"))


@lru_cache(maxsize=4096)
def load_gian_detail(bill_id: str) -> DistributedGianDetailDataset:
    """指定議案の個票を読み込む。"""

    return DistributedGianDetailDataset.model_validate_json(_read_json(GIAN_DETAIL_DIR / f"{bill_id}.json"))


@lru_cache(maxsize=512)
def load_shitsumon_list(house: House, session: int) -> ShugiinShitsumonListDataset | SangiinShitsumonListDataset:
    """指定院・指定回次の質問主意書一覧を読み込む。"""

    path = SHITSUMON_ROOT / house.value / "list" / f"{session}.json"
    text = _read_json(path)
    if house is House.SHUGIIN:
        return ShugiinShitsumonListDataset.model_validate_json(text)
    return SangiinShitsumonListDataset.model_validate_json(text)


@lru_cache(maxsize=4096)
def load_shitsumon_detail(
    house: House, question_id: str
) -> ShugiinShitsumonDetailDataset | SangiinShitsumonDetailDataset:
    """指定院・指定質問主意書の個票を読み込む。"""

    path = SHITSUMON_ROOT / house.value / "detail" / f"{question_id}.json"
    text = _read_json(path)
    if house is House.SHUGIIN:
        return ShugiinShitsumonDetailDataset.model_validate_json(text)
    return SangiinShitsumonDetailDataset.model_validate_json(text)


@lru_cache(maxsize=1)
def load_people() -> DistributedPeopleDataset:
    """人物インデックスを読み込む。"""

    return DistributedPeopleDataset.model_validate_json(_read_json(PEOPLE_PATH))


def list_available_gian_sessions() -> list[int]:
    """配布済み議案一覧の回次一覧を返す。"""

    sessions: list[int] = []
    for path in sorted(GIAN_LIST_DIR.glob("*.json")):
        try:
            sessions.append(int(path.stem))
        except ValueError:
            continue
    return sessions


def list_available_bill_ids() -> list[str]:
    """配布済み議案個票の bill_id 一覧を返す。"""

    return sorted(path.stem for path in GIAN_DETAIL_DIR.glob("*.json"))


def list_available_shitsumon_sessions(house: House) -> list[int]:
    """指定院の質問主意書一覧回次を返す。"""

    sessions: list[int] = []
    for path in sorted((SHITSUMON_ROOT / house.value / "list").glob("*.json")):
        try:
            sessions.append(int(path.stem))
        except ValueError:
            continue
    return sessions


def list_available_question_ids(house: House) -> list[str]:
    """指定院の質問主意書 ID 一覧を返す。"""

    return sorted(path.stem for path in (SHITSUMON_ROOT / house.value / "detail").glob("*.json"))


def list_available_person_keys() -> list[str]:
    """人物キー一覧を返す。"""

    return [item.person_key for item in load_people().items]


def find_person(person_key: str) -> DistributedPersonItem:
    """人物キーに一致する人物項目を返す。"""

    decoded_key = unquote(person_key)
    for item in load_people().items:
        if item.person_key == decoded_key:
            return item
    raise HTTPException(status_code=404, detail=f"person not found: {decoded_key}")


def search_people(query: str) -> list[DistributedPersonItem]:
    """人物キーと表記ゆれに対して部分一致検索する。"""

    normalized_query = query.strip()
    if not normalized_query:
        return []

    matches: list[tuple[int, DistributedPersonItem]] = []
    for item in load_people().items:
        haystacks = [item.person_key, item.canonical_name, *item.name_variants]
        if any(normalized_query in value for value in haystacks):
            score = 0 if item.person_key == normalized_query else 1
            matches.append((score, item))
    matches.sort(key=lambda pair: (pair[0], pair[1].person_key))
    return [item for _, item in matches]


def build_meta() -> ApiMetaResponse:
    """API と配布データのメタ情報を返す。"""

    people_dataset = load_people()
    datasets_built_at = {
        "kaiki": load_kaiki().fetched_at,
        "people": people_dataset.built_at,
        "gian_latest_list": max(
            (load_gian_list(session).built_at for session in list_available_gian_sessions()),
            default=None,
        ),
        "shitsumon_shugiin_latest_list": max(
            (load_shitsumon_list(House.SHUGIIN, session).fetched_at for session in list_available_shitsumon_sessions(House.SHUGIIN)),
            default=None,
        ),
        "shitsumon_sangiin_latest_list": max(
            (load_shitsumon_list(House.SANGIIN, session).fetched_at for session in list_available_shitsumon_sessions(House.SANGIIN)),
            default=None,
        ),
    }
    return ApiMetaResponse(
        api_version=API_VERSION,
        datasets_built_at=datasets_built_at,
        available_gian_sessions=list_available_gian_sessions(),
        available_shitsumon_sessions={house.value: list_available_shitsumon_sessions(house) for house in House},
        available_bill_count=len(list_available_bill_ids()),
        available_people_count=len(people_dataset.items),
    )


@app.get("/")
def read_root() -> dict[str, object]:
    """API 概要と利用可能データの一覧を返す。"""

    meta = build_meta()
    return {
        "name": "kokkai-api",
        "version": API_VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "meta": "/meta",
        "v1": f"/{API_VERSION}",
        "available_gian_sessions": meta.available_gian_sessions,
        "available_bill_count": meta.available_bill_count,
        "available_shitsumon_sessions": meta.available_shitsumon_sessions,
        "available_people_count": meta.available_people_count,
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """ヘルスチェック結果を返す。"""

    return {"status": "ok"}


@app.get("/meta", response_model=ApiMetaResponse)
def read_meta() -> ApiMetaResponse:
    """API と配布データのメタ情報を返す。"""

    return build_meta()


@router.get("/kaiki", response_model=KaikiDataset)
def read_kaiki() -> KaikiDataset:
    """会期一覧データを返す。"""

    return load_kaiki()


@router.get("/gian/list", response_model=ApiSessionListResponse)
def read_gian_list_index() -> ApiSessionListResponse:
    """利用可能な議案一覧回次を返す。"""

    return ApiSessionListResponse(sessions=list_available_gian_sessions())


@router.get("/gian/list/{session}", response_model=DistributedGianListDataset)
def read_gian_list(session: int) -> DistributedGianListDataset:
    """指定回次の議案一覧を返す。"""

    return load_gian_list(session)


@router.get("/gian/detail", response_model=ApiIdListResponse)
def read_gian_detail_index(
    limit: int = Query(100, ge=1, le=1000, description="返す bill_id 件数"),
    offset: int = Query(0, ge=0, description="返却開始位置"),
) -> ApiIdListResponse:
    """利用可能な議案個票 bill_id 一覧を返す。"""

    return _paginate(list_available_bill_ids(), offset=offset, limit=limit)


@router.get("/gian/detail/{bill_id}", response_model=DistributedGianDetailDataset)
def read_gian_detail_item(bill_id: str) -> DistributedGianDetailDataset:
    """指定議案の個票を返す。"""

    return load_gian_detail(bill_id)


@router.get("/shitsumon/{house}/list", response_model=ApiSessionListResponse)
def read_shitsumon_list_index(house: House) -> ApiSessionListResponse:
    """指定院で利用可能な質問主意書一覧回次を返す。"""

    return ApiSessionListResponse(sessions=list_available_shitsumon_sessions(house))


@router.get(
    "/shitsumon/{house}/list/{session}",
    response_model=ShugiinShitsumonListDataset | SangiinShitsumonListDataset,
)
def read_shitsumon_list(
    house: House, session: int
) -> ShugiinShitsumonListDataset | SangiinShitsumonListDataset:
    """指定院・指定回次の質問主意書一覧を返す。"""

    return load_shitsumon_list(house, session)


@router.get("/shitsumon/{house}/detail", response_model=ApiIdListResponse)
def read_shitsumon_detail_index(
    house: House,
    limit: int = Query(100, ge=1, le=1000, description="返す question_id 件数"),
    offset: int = Query(0, ge=0, description="返却開始位置"),
) -> ApiIdListResponse:
    """指定院で利用可能な質問主意書個票 ID 一覧を返す。"""

    return _paginate(list_available_question_ids(house), offset=offset, limit=limit)


@router.get(
    "/shitsumon/{house}/detail/{question_id}",
    response_model=ShugiinShitsumonDetailDataset | SangiinShitsumonDetailDataset,
)
def read_shitsumon_detail_item(
    house: House, question_id: str
) -> ShugiinShitsumonDetailDataset | SangiinShitsumonDetailDataset:
    """指定院・指定質問主意書の個票を返す。"""

    return load_shitsumon_detail(house, question_id)


@router.get("/people", response_model=ApiIdListResponse)
def read_people_index(
    limit: int = Query(100, ge=1, le=1000, description="返す person_key 件数"),
    offset: int = Query(0, ge=0, description="返却開始位置"),
) -> ApiIdListResponse:
    """利用可能な人物キー一覧を返す。"""

    return _paginate(list_available_person_keys(), offset=offset, limit=limit)


@router.get("/people/search", response_model=ApiPeopleSearchResponse)
def read_people_search(
    q: str = Query(..., min_length=1, description="人物名の部分一致検索文字列"),
    limit: int = Query(20, ge=1, le=100, description="返す人物件数"),
    offset: int = Query(0, ge=0, description="返却開始位置"),
) -> ApiPeopleSearchResponse:
    """人物キーと表記ゆれに対して部分一致検索する。"""

    items = search_people(q)
    return ApiPeopleSearchResponse(
        total=len(items),
        offset=offset,
        limit=limit,
        items=items[offset : offset + limit],
    )


@router.get("/people/{person_key}", response_model=DistributedPersonItem)
def read_person(person_key: str) -> DistributedPersonItem:
    """指定人物のインデックス個票を返す。"""

    return find_person(person_key)


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "9000")),
        reload=False,
    )
