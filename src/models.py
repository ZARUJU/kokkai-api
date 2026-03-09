from __future__ import annotations

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


class GianProgressEntry(BaseModel):
    """議案審議経過ページ内の項目と内容の1組を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: str


class GianProgressSection(BaseModel):
    """議案審議経過ページ内の補助セクションを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    section_name: str | None = None
    entries: list[GianProgressEntry]


class GianProgressDateText(BaseModel):
    """日付と補足テキストの組を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    occurred_at: date | None = None
    text: str | None = None


class GianHouseProgressParsed(BaseModel):
    """衆議院または参議院における審議進捗の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    pre_review_received_at: date | None = None
    pre_referral: GianProgressDateText | None = None
    bill_received_at: date | None = None
    referral: GianProgressDateText | None = None
    review_finished: GianProgressDateText | None = None
    plenary_finished: GianProgressDateText | None = None
    stance: str | None = None
    supporting_groups: list[str] = []
    opposing_groups: list[str] = []


class GianPromulgationParsed(BaseModel):
    """公布情報の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    promulgated_at: date | None = None
    law_number: str | None = None


class GianMemberLawExtraParsed(BaseModel):
    """衆法で現れる追加情報の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    submitter_list: list[str] = []
    supporters: list[str] = []


class GianProgressBodyParsed(BaseModel):
    """会期差分として扱う進捗本体の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    house_of_reps: GianHouseProgressParsed = GianHouseProgressParsed()
    house_of_councillors: GianHouseProgressParsed = GianHouseProgressParsed()
    promulgation: GianPromulgationParsed = GianPromulgationParsed()


class GianProgressParsed(BaseModel):
    """議案進捗ページ全体の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_type: str | None = None
    bill_submit_session: int | None = None
    bill_number: int | None = None
    bill_title: str | None = None
    submitter: str | None = None
    submitter_group: str | None = None
    house_of_reps: GianHouseProgressParsed = GianHouseProgressParsed()
    house_of_councillors: GianHouseProgressParsed = GianHouseProgressParsed()
    promulgation: GianPromulgationParsed = GianPromulgationParsed()
    member_law_extra: GianMemberLawExtraParsed | None = None


class GianProgressDataset(BaseModel):
    """単一議案・単一会期の進捗パース結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_id: str
    category: str
    subcategory: str | None = None
    submitted_session: int | None = None
    bill_number: int | None = None
    title: str
    status: str | None = None
    source_url: AnyHttpUrl
    fetched_at: datetime
    page_title: str | None = None
    session_number: int
    parsed: GianProgressParsed


class GianTextDocumentParsed(BaseModel):
    """本文ページから辿れる個別文書の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    title: str | None = None
    document_type: str
    note: str | None = None
    url: AnyHttpUrl
    local_path: str


class GianTextParsed(BaseModel):
    """議案本文ページ全体の正規化モデル。"""

    model_config = ConfigDict(extra="forbid")

    page_title: str | None = None
    submit_session_label: str | None = None
    bill_type: str | None = None
    bill_number_label: str | None = None
    bill_title: str | None = None
    documents: list[GianTextDocumentParsed]


class GianTextDataset(BaseModel):
    """単一議案の本文情報パース結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_id: str
    category: str
    subcategory: str | None = None
    submitted_session: int | None = None
    bill_number: int | None = None
    title: str
    status: str | None = None
    source_url: AnyHttpUrl
    fetched_at: datetime
    parsed: GianTextParsed


class DistributedGianListItem(BaseModel):
    """配布用の議案一覧1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_id: str
    category: str
    subcategory: str | None = None
    submitted_session: int | None = None
    bill_number: int | None = None
    title: str
    status: str | None = None
    progress_url: AnyHttpUrl | None = None
    text_url: AnyHttpUrl | None = None
    has_progress: bool
    has_honbun: bool


class DistributedGianListDataset(BaseModel):
    """配布用の会期別議案一覧を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    session_number: int
    built_at: datetime
    items: list[DistributedGianListItem]


class DistributedGianSessionStatus(BaseModel):
    """特定会期における議案の掲載状況を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    session_number: int
    status: str | None = None


class DistributedGianBasicInfo(BaseModel):
    """配布用個票の基本情報を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_type: str | None = None
    bill_title: str | None = None
    submitter: str | None = None
    submitter_group: str | None = None
    member_law_extra: GianMemberLawExtraParsed | None = None


class DistributedGianProgressRecord(BaseModel):
    """配布用個票に含める会期別進捗情報を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    session_number: int
    source_url: AnyHttpUrl
    page_title: str | None = None
    status: str | None = None
    parsed: GianProgressBodyParsed


class DistributedGianHonbunDocument(BaseModel):
    """配布用個票に含める本文文書1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    title: str | None = None
    document_type: str
    note: str | None = None
    source_url: AnyHttpUrl
    html: str
    text: str


class DistributedGianDetailDataset(BaseModel):
    """配布用の議案個票を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_id: str
    category: str
    subcategory: str | None = None
    submitted_session: int | None = None
    bill_number: int | None = None
    title: str
    listed_sessions: list[int]
    session_statuses: list[DistributedGianSessionStatus]
    basic_info: DistributedGianBasicInfo
    progress: list[DistributedGianProgressRecord]
    honbun_source_url: AnyHttpUrl | None = None
    honbun_page_title: str | None = None
    honbun_documents: list[DistributedGianHonbunDocument]
    built_at: datetime
