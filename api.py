"""会期一覧と議案の配布一歩手前 JSON を公開する FastAPI アプリケーション。

主なエンドポイント:
    - GET /health
    - GET /kaiki
    - GET /gian/list
    - GET /gian/list/{session}
    - GET /gian/detail
    - GET /gian/detail/{bill_id}

入力:
    - data/kaiki.json
    - tmp/ready/gian/list/*.json
    - tmp/ready/gian/detail/*.json

実行例:
    uv run api.py
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from src.models import (
    DistributedGianDetailDataset,
    DistributedGianListDataset,
    KaikiDataset,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data"
READY_ROOT = PROJECT_ROOT / "tmp" / "ready"
KAIKI_PATH = DATA_ROOT / "kaiki.json"
GIAN_LIST_DIR = READY_ROOT / "gian" / "list"
GIAN_DETAIL_DIR = READY_ROOT / "gian" / "detail"

app = FastAPI(
    title="kokkai-api",
    description="会期一覧と議案の配布一歩手前データを公開する API",
    version="0.1.0",
)


def _read_json(path: Path) -> str:
    """JSON ファイルを UTF-8 で読み込む。"""

    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"data not found: {path.relative_to(PROJECT_ROOT)}"
        )
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_kaiki() -> KaikiDataset:
    """会期一覧データを読み込む。"""

    return KaikiDataset.model_validate_json(_read_json(KAIKI_PATH))


@lru_cache(maxsize=256)
def load_gian_list(session: int) -> DistributedGianListDataset:
    """指定回次の議案一覧 ready データを読み込む。"""

    return DistributedGianListDataset.model_validate_json(
        _read_json(GIAN_LIST_DIR / f"{session}.json")
    )


@lru_cache(maxsize=4096)
def load_gian_detail(bill_id: str) -> DistributedGianDetailDataset:
    """指定議案の ready 個票を読み込む。"""

    return DistributedGianDetailDataset.model_validate_json(
        _read_json(GIAN_DETAIL_DIR / f"{bill_id}.json")
    )


def list_available_sessions() -> list[int]:
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


@app.get("/")
def read_root() -> dict[str, object]:
    """API 概要と利用可能データの一覧を返す。"""

    return {
        "name": "kokkai-api",
        "endpoints": {
            "health": "/health",
            "kaiki": "/kaiki",
            "gian_list_index": "/gian/list",
            "gian_list": "/gian/list/{session}",
            "gian_detail_index": "/gian/detail",
            "gian_detail": "/gian/detail/{bill_id}",
        },
        "available_sessions": list_available_sessions(),
        "available_bill_count": len(list_available_bill_ids()),
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """ヘルスチェック結果を返す。"""

    return {"status": "ok"}


@app.get("/kaiki", response_model=KaikiDataset)
def read_kaiki() -> KaikiDataset:
    """会期一覧データを返す。"""

    return load_kaiki()


@app.get("/gian/list")
def read_gian_list_index() -> dict[str, object]:
    """利用可能な議案一覧回次を返す。"""

    return {"sessions": list_available_sessions()}


@app.get("/gian/list/{session}", response_model=DistributedGianListDataset)
def read_gian_list(session: int) -> DistributedGianListDataset:
    """指定回次の議案一覧を返す。"""

    return load_gian_list(session)


@app.get("/gian/detail")
def read_gian_detail_index(
    limit: int = Query(100, ge=1, le=1000, description="返す bill_id 件数"),
    offset: int = Query(0, ge=0, description="返却開始位置"),
) -> dict[str, object]:
    """利用可能な議案個票 bill_id 一覧を返す。"""

    bill_ids = list_available_bill_ids()
    return {
        "total": len(bill_ids),
        "offset": offset,
        "limit": limit,
        "items": bill_ids[offset : offset + limit],
    }


@app.get("/gian/detail/{bill_id}", response_model=DistributedGianDetailDataset)
def read_gian_detail_item(bill_id: str) -> DistributedGianDetailDataset:
    """指定議案の個票を返す。"""

    return load_gian_detail(bill_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "9000")),
        reload=False,
    )
