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
