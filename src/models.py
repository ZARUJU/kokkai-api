from typing import Optional, List
from pydantic import BaseModel, Field


class ShuShitsumonData(BaseModel):
    number: Optional[int] = Field(None, alias="番号")
    question_subject: Optional[str] = Field(None, alias="質問件名")
    submitter_name: Optional[str] = Field(None, alias="提出者氏名")
    progress_status: Optional[str] = Field(None, alias="経過状況")
    progress_info_link: Optional[str] = Field(None, alias="経過情報リンク")
    question_html_link: Optional[str] = Field(None, alias="質問情報HTMLリンク")
    answer_html_link: Optional[str] = Field(None, alias="答弁情報HTMLリンク")


class ShuShitsumonList(BaseModel):
    shitsumon_list: List[ShuShitsumonData]


class ShuShitsumonListData(BaseModel):
    source: str
    session: int
    list: List[ShuShitsumonData]
