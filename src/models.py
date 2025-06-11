from typing import Optional, List
from pydantic import BaseModel, Field


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
    question_html_link: Optional[str] = Field(None)
    question_pdf_link: Optional[str] = Field(None)
    answer_html_link: Optional[str] = Field(None)
    answer_pdf_link: Optional[str] = Field(None)


class SangiinShitsumonList(BaseModel):
    session: int
    source: str
    items: List[SangiinShitsumonData]
