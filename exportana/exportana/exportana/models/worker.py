import logging
from typing import Optional

from pydantic import Field

from .base import DBModel, OrderedEnum
from ..exporter.constants import LOCALHOST, URL

log = logging.getLogger(__name__)


class WorkerStatus(str, OrderedEnum):
    offline = "offline"
    idle = "idle"
    working = "working"


class Worker(DBModel, allow_population_by_field_name=True):
    url: str = Field(None, example=LOCALHOST, alias="_id")

    def __lt__(self, other):
        return self.url < other.url

    def get_id(self) -> dict:
        return self.dict(by_alias=True, include={URL})

    def get_data(self) -> dict:
        return self.dict(exclude={URL})


class WorkerInfo(Worker):
    status: WorkerStatus = WorkerStatus.idle
    trace_name: Optional[str] = None
