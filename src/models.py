"""会期データの構造を定義する Pydantic モデル群。"""

from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict


class Kaiki(BaseModel):
    """単一の国会会期を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    number: int
    session_type: str | None = None
    convocation_date: date | None = None
    closing_date: date | None = None
    closing_note: str | None = None
    duration_days: int | None = None
    initial_duration_days: int | None = None
    extension_days: int | None = None


class KaikiDataset(BaseModel):
    """会期一覧の取得結果全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: datetime
    items: list[Kaiki]


class GianItem(BaseModel):
    """単一の議案一覧行を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    category: str
    subcategory: str | None = None
    submitted_session: int | None = None
    bill_number: int | None = None
    title: str
    status: str | None = None
    progress_url: AnyHttpUrl | None = None
    text_url: AnyHttpUrl | None = None


class GianListDataset(BaseModel):
    """特定会期の議案一覧取得結果全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: datetime
    session_number: int
    items: list[GianItem]
