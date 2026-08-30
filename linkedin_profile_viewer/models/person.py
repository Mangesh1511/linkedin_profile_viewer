"""
Pydantic data models for LinkedIn Person profile schema.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Experience(BaseModel):
    position_title: str
    institution_name: str
    linkedin_url: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    institution_name: str
    degree: Optional[str] = None
    linkedin_url: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    description: Optional[str] = None


class Accomplishment(BaseModel):
    category: str
    title: str
    issuer: Optional[str] = None


class Interest(BaseModel):
    name: str
    category: Optional[str] = "General"


class Contact(BaseModel):
    type: str
    value: str


class Person(BaseModel):
    linkedin_url: str
    name: str
    headline: Optional[str] = None
    location: Optional[str] = None
    profile_picture_url: Optional[str] = None
    connections: Optional[str] = None
    about: Optional[str] = None
    open_to_work: bool = False
    experiences: List[Experience] = Field(default_factory=list)
    educations: List[Education] = Field(default_factory=list)
    interests: List[Interest] = Field(default_factory=list)
    accomplishments: List[Accomplishment] = Field(default_factory=list)
    contacts: List[Contact] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
