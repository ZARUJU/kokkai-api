from typing import Optional, List, Union
from pydantic import BaseModel, Field


# 衆議院TV
class ShugiinTV(BaseModel):
    date_time: str
    meeting_name: str
    topics: List[str] = []
    speakers: List[str] = []
    url: str
    deli_id: int


# 質問主意書


class ShuShitsumonData(BaseModel):
    number: Optional[int] = Field(None)
    question_subject: Optional[str] = Field(None)
    submitter_name: Optional[str] = Field(None)
    progress_status: Optional[str] = Field(None)
    progress_info_link: Optional[str] = Field(None)
    question_html_link: Optional[str] = Field(None)
    answer_html_link: Optional[str] = Field(None)


class ShuShitsumonList(BaseModel):
    session: int
    source: str
    items: List[ShuShitsumonData]


class ShuShitsumonStatusBefore(BaseModel):
    session_number: Optional[int]
    session_type: Optional[str]
    question_number: Optional[int]
    question_subject: Optional[str]
    submitter_name: Optional[str]
    party_name: Optional[str]
    submitted_date: Optional[str]
    cabinet_transfer_date: Optional[str]
    reply_delay_notice_date: Optional[str]
    reply_delay_deadline: Optional[str]
    reply_received_date: Optional[str]
    withdrawal_date: Optional[str]
    withdrawal_notice_date: Optional[str]
    status: Optional[str]


class ShuShitsumonStatus(BaseModel):
    session_number: Optional[int]
    session_type: Optional[str]
    question_number: Optional[int]
    question_subject: Optional[str]
    submitter_name: Optional[str]
    submitter_count: Optional[int]
    party_name: Optional[str]
    submitted_date: Optional[str]
    cabinet_transfer_date: Optional[str]
    reply_delay_notice_date: Optional[str]
    reply_delay_deadline: Optional[str]
    reply_received_date: Optional[str]
    withdrawal_date: Optional[str]
    withdrawal_notice_date: Optional[str]
    status: Optional[str]


class SangiinShitsumonData(BaseModel):
    number: Optional[int] = Field(None)
    question_subject: Optional[str] = Field(None)
    submitter_name: Optional[str] = Field(None)
    progress_info_link: Optional[str] = Field(None)
    question_html_link: Optional[str] = Field(None)
    question_pdf_link: Optional[str] = Field(None)
    answer_html_link: Optional[str] = Field(None)
    answer_pdf_link: Optional[str] = Field(None)


class SangiinShitsumonList(BaseModel):
    session: int
    source: str
    items: List[SangiinShitsumonData]


# 国会会議録検索システムAPI

from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class SpeechRecord(BaseModel):
    speechID: str
    speechOrder: int
    speaker: str
    speakerYomi: Optional[str] = None
    speakerGroup: Optional[str] = None
    speakerPosition: Optional[str] = None
    speakerRole: Optional[str] = None
    speech: Optional[str] = None
    startPage: Optional[int] = None
    createTime: Optional[str] = None
    updateTime: Optional[str] = None
    speechURL: Optional[str] = None


class MeetingRecord(BaseModel):
    issueID: str
    imageKind: str
    # API sometimes returns numeric or string
    searchObject: int
    session: int
    nameOfHouse: str
    nameOfMeeting: str
    # issue may be string like '第4号'
    issue: str
    date: str
    # closing may be None
    closing: Optional[str] = None
    speechRecord: List[SpeechRecord] = Field(default_factory=list)
    meetingURL: str
    pdfURL: Optional[str] = None


class MeetingResponse(BaseModel):
    numberOfRecords: int
    numberOfReturn: int
    startRecord: int
    nextRecordPosition: Optional[int] = None
    meetingRecord: List[MeetingRecord] = Field(default_factory=list)
