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
    shitsumon_list: List[ShuShitsumonData]


class ShuShitsumonListData(BaseModel):
    source: str
    session: int
    questions: List[ShuShitsumonData]
