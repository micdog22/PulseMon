from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class MonitorCreate(BaseModel):
    name: str
    slug: str
    interval_seconds: int = Field(gt=0)
    grace_seconds: int = Field(ge=0, default=0)
    webhook_url: Optional[HttpUrl] = None

class MonitorOut(BaseModel):
    name: str
    slug: str
    interval_seconds: int
    grace_seconds: int
    status: str
    last_ping: Optional[str] = None
    webhook_url: Optional[str] = None
