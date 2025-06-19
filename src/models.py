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


class Inquiry(BaseModel):
    """個々の質問主意書の基本情報を保持するモデル"""

    number: int
    subject: str
    submitter: str
    progress_info_link: str
    question_html_link: str
    answer_html_link: str


class InquiryInfoList(BaseModel):
    """質問主意書リスト全体の情報を保持するモデル"""

    source: str
    items: List[Inquiry]


class InquiryStatus(BaseModel):
    """質問主意書の詳細なステータス情報を保持するモデル"""

    session: int
    number: int
    subject: str
    submitter: str
    question_date: str
    cabinet_date: str
    answer_date: str
    status: str


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
