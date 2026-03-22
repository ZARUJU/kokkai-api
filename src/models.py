from __future__ import annotations

"""会期データの構造を定義する Pydantic モデル群。"""

import datetime as dt
from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_serializer


def format_time_to_minute(value: dt.time | None) -> str | None:
    """時刻を分単位の `HH:MM` 文字列に整形する。"""

    if value is None:
        return None
    return value.strftime("%H:%M")


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


class ShugiinShitsumonItem(BaseModel):
    """衆議院の質問主意書一覧1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    question_number: int
    title: str
    submitter_name: str | None = None
    status: str | None = None
    progress_url: AnyHttpUrl | None = None
    question_html_url: AnyHttpUrl | None = None
    question_pdf_url: AnyHttpUrl | None = None
    answer_html_url: AnyHttpUrl | None = None
    answer_pdf_url: AnyHttpUrl | None = None


class ShugiinShitsumonListDataset(BaseModel):
    """衆議院の回次別質問主意書一覧取得結果全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    source_series: str
    fetched_at: datetime
    session_number: int
    items: list[ShugiinShitsumonItem]


class SangiinShitsumonItem(BaseModel):
    """参議院の質問主意書一覧1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    question_number: int
    title: str
    submitter_name: str | None = None
    detail_url: AnyHttpUrl | None = None
    question_html_url: AnyHttpUrl | None = None
    question_pdf_url: AnyHttpUrl | None = None
    answer_html_url: AnyHttpUrl | None = None
    answer_pdf_url: AnyHttpUrl | None = None


class SangiinShitsumonListDataset(BaseModel):
    """参議院の回次別質問主意書一覧取得結果全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: datetime
    session_number: int
    session_label: str | None = None
    items: list[SangiinShitsumonItem]


class SangiinShitsumonDetailDataset(BaseModel):
    """参議院質問主意書個票のパース結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    source_url: AnyHttpUrl
    fetched_at: datetime
    title: str
    submitter_name: str | None = None
    progress: ShugiinShitsumonProgressParsed | None = None
    question_document: ShugiinShitsumonDocumentParsed | None = None
    answer_document: ShugiinShitsumonDocumentParsed | None = None


class SeiganListItem(BaseModel):
    """請願一覧の1件を表す共通モデル。"""

    model_config = ConfigDict(extra="forbid")

    house: str
    petition_number: int
    title: str
    committee_name: str | None = None
    committee_code: str | None = None
    detail_url: AnyHttpUrl | None = None
    similar_petitions_url: AnyHttpUrl | None = None
    is_referred: bool = True


class SeiganListDataset(BaseModel):
    """請願一覧の共通データセットを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: datetime
    house: str
    session_number: int
    items: list[SeiganListItem]


class SeiganPresenter(BaseModel):
    """請願の紹介議員・受理単位情報1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    receipt_number: int | None = None
    presenter_name: str
    party_name: str | None = None
    received_at: date | None = None
    referred_at: date | None = None
    result: str | None = None


class SeiganDetailDataset(BaseModel):
    """請願個票の共通パース結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    petition_id: str
    house: str
    session_number: int
    petition_number: int
    title: str
    committee_name: str | None = None
    committee_code: str | None = None
    detail_source_url: AnyHttpUrl | None = None
    similar_petitions_source_url: AnyHttpUrl | None = None
    fetched_at: datetime
    summary_text: str | None = None
    accepted_count: int | None = None
    signer_count: int | None = None
    outcome: str | None = None
    presenters: list[SeiganPresenter] = []


class ShugiinShitsumonProgressParsed(BaseModel):
    """衆議院質問主意書の経過情報を正規化したモデル。"""

    model_config = ConfigDict(extra="forbid")

    session_type: str | None = None
    group_name: str | None = None
    submitted_at: date | None = None
    cabinet_sent_at: date | None = None
    answer_delay_notice_received_at: date | None = None
    answer_due_at: date | None = None
    answer_received_at: date | None = None
    withdrawn_at: date | None = None
    withdrawal_notice_at: date | None = None
    status: str | None = None


class ShugiinShitsumonDocumentParsed(BaseModel):
    """質問本文または答弁本文の抽出結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    document_date: date | None = None
    answerer_name: str | None = None
    body_text: str | None = None


class ShugiinShitsumonDetailDataset(BaseModel):
    """衆議院質問主意書個票のパース結果を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    source_url: AnyHttpUrl
    fetched_at: datetime
    title: str
    submitter_name: str | None = None
    progress: ShugiinShitsumonProgressParsed | None = None
    question_document: ShugiinShitsumonDocumentParsed | None = None
    answer_document: ShugiinShitsumonDocumentParsed | None = None


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
    submitter_count: int | None = None
    submitter_has_more: bool = False
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


class DistributedGianMeetingReference(BaseModel):
    """議案が取り上げられた会議録1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: dt.date
    meeting_url: AnyHttpUrl | None = None
    pdf_url: AnyHttpUrl | None = None
    agenda_text: str


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
    meetings: list[DistributedGianMeetingReference] = []
    honbun_source_url: AnyHttpUrl | None = None
    honbun_page_title: str | None = None
    honbun_documents: list[DistributedGianHonbunDocument]
    built_at: datetime


class DistributedPersonGianRelation(BaseModel):
    """人物と議案の関係1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    bill_id: str
    title: str
    role: str
    submitted_session: int | None = None


class DistributedPersonShitsumonRelation(BaseModel):
    """人物と質問主意書の関係1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    title: str
    role: str
    house: str
    session_number: int | None = None


class DistributedPersonSeiganRelation(BaseModel):
    """人物と請願の関係1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    petition_id: str
    title: str
    role: str
    house: str
    session_number: int | None = None


class DistributedPersonMeetingRelation(BaseModel):
    """人物と会議録の関係1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: date
    role: str | None = None
    section: str | None = None


class DistributedPersonSpeakingMeetingRelation(BaseModel):
    """人物が発言した会議録との関係1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: date
    speech_count: int = 1
    speaker_role: str | None = None
    speaker_position: str | None = None


class DistributedPersonItem(BaseModel):
    """人物インデックスの1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    person_key: str
    canonical_name: str
    name_variants: list[str] = []
    gian_relations: list[DistributedPersonGianRelation] = []
    seigan_relations: list[DistributedPersonSeiganRelation] = []
    shitsumon_relations: list[DistributedPersonShitsumonRelation] = []
    meeting_relations: list[DistributedPersonMeetingRelation] = []
    speaking_meeting_relations: list[DistributedPersonSpeakingMeetingRelation] = []


class DistributedPersonRelationCounts(BaseModel):
    """人物に紐づく関連件数の要約を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    gian: int = 0
    seigan: int = 0
    shitsumon: int = 0
    meeting_attendance: int = 0
    meeting_speech: int = 0


class DistributedPersonIndexItem(BaseModel):
    """人物一覧・検索用の軽量項目を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    person_key: str
    canonical_name: str
    name_variants: list[str] = []
    detail_id: str
    relation_counts: DistributedPersonRelationCounts


class DistributedPeopleIndexDataset(BaseModel):
    """配布用の人物インデックス全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    built_at: datetime
    items: list[DistributedPersonIndexItem]


class DistributedPersonDetailDataset(BaseModel):
    """配布用の人物個票を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    built_at: datetime
    person_key: str
    canonical_name: str
    name_variants: list[str] = []
    relation_counts: DistributedPersonRelationCounts
    gian_relations: list[DistributedPersonGianRelation] = []
    seigan_relations: list[DistributedPersonSeiganRelation] = []
    shitsumon_relations: list[DistributedPersonShitsumonRelation] = []
    meeting_relations: list[DistributedPersonMeetingRelation] = []
    speaking_meeting_relations: list[DistributedPersonSpeakingMeetingRelation] = []


class DistributedSeiganListDataset(BaseModel):
    """配布用の請願一覧を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    house: str
    session_number: int
    built_at: datetime
    items: list[SeiganListItem]


class DistributedSeiganDetailDataset(BaseModel):
    """配布用の請願個票を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    petition_id: str
    house: str
    session_number: int
    petition_number: int
    title: str
    committee_name: str | None = None
    committee_code: str | None = None
    detail_source_url: AnyHttpUrl | None = None
    similar_petitions_source_url: AnyHttpUrl | None = None
    summary_text: str | None = None
    accepted_count: int | None = None
    signer_count: int | None = None
    outcome: str | None = None
    presenters: list[SeiganPresenter] = []
    built_at: datetime


class KokkaiSpeechRecord(BaseModel):
    """会議録 API の speechRecord 1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    speech_id: str | None = Field(default=None, alias="speechID")
    issue_id: str | None = Field(default=None, alias="issueID")
    image_kind: str | None = Field(default=None, alias="imageKind")
    search_object: int | None = Field(default=None, alias="searchObject")
    session: int | None = None
    name_of_house: str | None = Field(default=None, alias="nameOfHouse")
    name_of_meeting: str | None = Field(default=None, alias="nameOfMeeting")
    issue: str | None = None
    date: dt.date | None = None
    closing: str | None = None
    speech_order: int | None = Field(default=None, alias="speechOrder")
    speaker: str | None = None
    speaker_yomi: str | None = Field(default=None, alias="speakerYomi")
    speaker_group: str | None = Field(default=None, alias="speakerGroup")
    speaker_position: str | None = Field(default=None, alias="speakerPosition")
    speaker_role: str | None = Field(default=None, alias="speakerRole")
    speech: str | None = None
    start_page: int | None = Field(default=None, alias="startPage")
    create_time: dt.datetime | None = Field(default=None, alias="createTime")
    update_time: dt.datetime | None = Field(default=None, alias="updateTime")
    speech_url: AnyHttpUrl | None = Field(default=None, alias="speechURL")


class KokkaiMeetingRecord(BaseModel):
    """会議録 API の meetingRecord 1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    issue_id: str = Field(alias="issueID")
    image_kind: str | None = Field(default=None, alias="imageKind")
    search_object: int | None = Field(default=None, alias="searchObject")
    session: int
    name_of_house: str = Field(alias="nameOfHouse")
    name_of_meeting: str = Field(alias="nameOfMeeting")
    issue: str
    date: dt.date
    closing: str | None = None
    speech_record: list[KokkaiSpeechRecord] = Field(default_factory=list, alias="speechRecord")
    meeting_url: AnyHttpUrl | None = Field(default=None, alias="meetingURL")
    pdf_url: AnyHttpUrl | None = Field(default=None, alias="pdfURL")


class KokkaiMeetingApiDataset(BaseModel):
    """会議録 API の回次単位取得結果全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: dt.datetime
    session_number: int
    total_records: int
    items: list[KokkaiMeetingRecord]


class KokkaiAttendanceEntry(BaseModel):
    """会議冒頭から抽出した出席者1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    section: str | None = None
    role: str | None = None
    title: str | None = None
    name: str


class KokkaiMembershipChange(BaseModel):
    """委員異動の1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    changed_at: dt.date | None = None
    resigned_name: str | None = None
    appointed_name: str | None = None


class KokkaiMeetingMetadataParsed(BaseModel):
    """会議冒頭・終盤から抽出した正規化メタデータを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    meeting_date: dt.date | None = None
    opening_line: str | None = None
    opening_time: dt.time | None = None
    closing_line: str | None = None
    closing_time: dt.time | None = None
    attendance: list[KokkaiAttendanceEntry] = []
    membership_changes: list[KokkaiMembershipChange] = []
    referred_items: list[str] = []
    agenda_items: list[str] = []
    intro_text: str | None = None
    closing_text: str | None = None


class KokkaiMeetingSpeakerSummary(BaseModel):
    """会議録1件に含まれる発言者ごとの集計を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    speech_count: int
    speaker_role: str | None = None
    speaker_position: str | None = None


class KokkaiMeetingParsedItem(BaseModel):
    """会議録1件に対する抽出済みメタデータ付き個票を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: dt.date
    closing: str | None = None
    meeting_url: AnyHttpUrl | None = None
    pdf_url: AnyHttpUrl | None = None
    speech_count: int
    speakers: list[KokkaiMeetingSpeakerSummary] = []
    parsed: KokkaiMeetingMetadataParsed


class KokkaiMeetingParsedDataset(BaseModel):
    """回次単位の抽出済み会議録メタデータ全体を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    source_url: AnyHttpUrl
    fetched_at: dt.datetime
    parsed_at: dt.datetime
    session_number: int
    total_records: int
    items: list[KokkaiMeetingParsedItem]


class DistributedKokkaiAgendaItem(BaseModel):
    """配布用の本日の案件1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    text: str
    item_type: str | None = None
    bill_id: str | None = None
    bill_title: str | None = None
    petition_id: str | None = None
    petition_title: str | None = None


class DistributedKokkaiMeetingListItem(BaseModel):
    """配布用の会議録一覧1件を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: dt.date
    meeting_url: AnyHttpUrl | None = None
    pdf_url: AnyHttpUrl | None = None
    opening_time: dt.time | None = None
    closing_time: dt.time | None = None
    speech_count: int
    matched_item_count: int = 0

    @field_serializer("opening_time", "closing_time", when_used="json")
    def serialize_times(self, value: dt.time | None) -> str | None:
        """開会・散会時刻を分単位で JSON 化する。"""

        return format_time_to_minute(value)


class DistributedKokkaiMeetingListDataset(BaseModel):
    """配布用の会議録一覧データセットを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    session_number: int
    built_at: dt.datetime
    items: list[DistributedKokkaiMeetingListItem]


class DistributedKokkaiMeetingDetailDataset(BaseModel):
    """配布用の会議録個票を表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    session: int
    name_of_house: str
    name_of_meeting: str
    issue: str
    date: dt.date
    meeting_url: AnyHttpUrl | None = None
    pdf_url: AnyHttpUrl | None = None
    opening_line: str | None = None
    opening_time: dt.time | None = None
    closing_line: str | None = None
    closing_time: dt.time | None = None
    speech_count: int
    speakers: list[KokkaiMeetingSpeakerSummary] = []
    attendance: list[KokkaiAttendanceEntry] = []
    agenda_items: list[DistributedKokkaiAgendaItem] = []
    built_at: dt.datetime

    @field_serializer("opening_time", "closing_time", when_used="json")
    def serialize_times(self, value: dt.time | None) -> str | None:
        """開会・散会時刻を分単位で JSON 化する。"""

        return format_time_to_minute(value)


class ApiSessionListResponse(BaseModel):
    """回次一覧 API のレスポンスを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    sessions: list[int]


class ApiIdListResponse(BaseModel):
    """ID 一覧 API のレスポンスを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    total: int
    offset: int
    limit: int
    items: list[str]


class ApiMetaResponse(BaseModel):
    """API メタ情報レスポンスを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    api_version: str
    datasets_built_at: dict[str, datetime | None]
    available_gian_sessions: list[int]
    available_kaigiroku_sessions: list[int]
    available_seigan_sessions: dict[str, list[int]]
    available_shitsumon_sessions: dict[str, list[int]]
    available_bill_count: int
    available_kaigiroku_count: int
    available_petition_count: int
    available_people_count: int


class ApiPeopleSearchResponse(BaseModel):
    """人物検索 API のレスポンスを表すモデル。"""

    model_config = ConfigDict(extra="forbid")

    total: int
    offset: int
    limit: int
    items: list[DistributedPersonIndexItem]
