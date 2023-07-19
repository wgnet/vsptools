from datetime import datetime
from typing import Optional, List, Union

from pydantic import Field, BaseModel

from .base import DBModel, VerboseResult, OrderedEnum
from .trace_meta import TraceMeta
from ..models.worker import Worker


class TraceStatus(str, OrderedEnum):
    PROCESSED = "processed"
    IN_PROGRESS = "in_progress"
    QUEUED = "queued"
    UNKNOWN = "unknown"
    POISONED = "poisoned"


class TraceInfo(DBModel, allow_population_by_field_name=True):
    trace_name: str = Field(None, example="19960303_133333_127.0.0.1", alias="_id")
    creation_date: datetime = None

    def get_id(self) -> dict:
        return self.dict(by_alias=True, include={"trace_name"})

    def get_data(self) -> dict:
        return self.dict(exclude={"trace_name"})


class ProcessedTraceReport(BaseModel):
    trace_name: str = None
    worker: Worker = None
    processed_date: Optional[datetime] = None
    result: VerboseResult = None
    trace_meta: Union[None, TraceMeta, dict] = None


class ProcessedTraceInfo(TraceInfo):
    processing_reports: List[ProcessedTraceReport] = []


class TraceInfoStatus(TraceInfo):
    status: TraceStatus = TraceStatus.UNKNOWN
