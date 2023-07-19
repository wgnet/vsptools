import logging
import uuid
from collections import defaultdict
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette import status

from exportana.exporter.constants import (
    NAME_KEY,
    TIMESTAMP_KEY,
    METADATA_PREFIX,
    METADATA_DELIMITER,
    FRAME_START_KEY,
    FRAME_END_KEY,
    RAW_DATA_KEY
)
from exportana.utils.utils import flatten_dict

__ALL__ = ["router"]
EXCLUDED_KEYS = ["_Children", "_Duration", "_Editor", "_Budgets", "_Value"]

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/performance_metrics",
    tags=["performance_metrics"],
    responses={404: {"description": "Page not found"}})


class MetricsHeader(BaseModel):
    metrics_count: Optional[int] = Field(0, alias="MetricFramesCount")


class Frame(BaseModel):
    frame_start: Optional[float] = Field(None, alias=FRAME_START_KEY)
    frame_end: Optional[float] = Field(None, alias=FRAME_END_KEY)
    data: Optional[Dict[str, Any]] = Field(None, alias="Data")
    raw_data: Optional[Dict[str, Any]] = Field(None, alias=RAW_DATA_KEY)

    def to_dict(self) -> dict:
        result = dict()
        result[FRAME_START_KEY] = self.frame_start
        result[FRAME_END_KEY] = self.frame_end
        result.update(self.data)
        return result


Bookmark = Dict[str, float]

metrics_names: List[str] = list()
metadata_names: List[str] = list()
metrics_bookmarks: List[dict] = list()
metrics_header: MetricsHeader = MetricsHeader()

# region perf settings
metrics_settings: Dict[str, Any] = dict()
metrics_budgets: Dict[str, Any] = dict()
# endregion

metrics: List[Frame] = list()


def reformat_bookmarks(bookmarks: List[Bookmark]):
    result: List[Dict] = list()
    for bookmark in bookmarks:
        row: Dict = defaultdict(dict)
        for bookmark_value in bookmark.items():
            row[NAME_KEY] = bookmark_value[0]
            row[TIMESTAMP_KEY] = str(bookmark_value[1])
            result.append(row)
    return result


# todo: remove after new version of UI has been complete and integrated
def get_meta_from_bookmarks(bookmarks: List[Bookmark]) -> list:
    result: List[str] = list()
    for bookmark in bookmarks:
        for v in bookmark.items():
            metadata_name = v[0]
            if metadata_name.startswith(METADATA_PREFIX):
                metadata_digits = metadata_name.split(METADATA_DELIMITER)
                if len(metadata_digits) > 1:
                    meta_name = metadata_digits[1]
                    if meta_name not in result:
                        result.append(meta_name)
    return result


def is_metrics_available() -> bool:
    return all([
        metrics_names,
        metrics_header,
        metrics_header.metrics_count > 0,
        len(metrics) == metrics_header.metrics_count
    ])


def flush_metrics():
    global metrics_names
    global metadata_names
    global metrics_bookmarks
    global metrics_header
    global metrics
    global metrics_settings
    global metrics_budgets

    metrics_names.clear()
    metadata_names.clear()
    metrics_bookmarks.clear()
    metrics_header.metrics_count = 0
    metrics.clear()
    metrics_settings.clear()
    metrics_budgets.clear()


@router.post("/set/perf_config", status_code=status.HTTP_202_ACCEPTED)
async def set_perf_config(request: Request, settings: Dict[str, Any]):
    global metrics_settings
    global metrics_budgets

    metrics_settings_flat = flatten_dict(settings, EXCLUDED_KEYS)
    metrics_settings = settings

    for k, v in metrics_settings_flat.items():  # crutch
        if isinstance(v, int) or isinstance(v, float):
            metrics_names.append(k)
            metrics_budgets[k] = v


@router.post("/set/metadata_names", status_code=status.HTTP_202_ACCEPTED)
async def set_metadata_names(request: Request, names: List[str]):
    global metadata_names
    metadata_names = names


@router.post("/set/bookmarks", status_code=status.HTTP_202_ACCEPTED)
async def set_bookmarks(request: Request, bookmarks: List[Bookmark]):
    global metrics_bookmarks
    # region todo: remove after new version of UI has been complete and integrated
    global metadata_names
    metadata_names = get_meta_from_bookmarks(bookmarks)
    # endregion
    metrics_bookmarks = reformat_bookmarks(bookmarks)


@router.post("/set/header", status_code=status.HTTP_202_ACCEPTED)
async def set_metrics_header(request: Request, header: MetricsHeader):
    global metrics_header
    metrics_header.metrics_count = header.metrics_count


@router.post("/add", status_code=status.HTTP_202_ACCEPTED)
async def add_metrics(request: Request, metrics_data: List[dict]):
    global metrics
    for metric_data in metrics_data:
        frame_data_flatten = flatten_dict(metric_data, EXCLUDED_KEYS)
        frame = Frame()
        frame.frame_start = frame_data_flatten[FRAME_START_KEY]
        frame.frame_end = frame_data_flatten[FRAME_END_KEY]
        del frame_data_flatten[FRAME_START_KEY]
        del frame_data_flatten[FRAME_END_KEY]
        frame.data = frame_data_flatten
        frame.raw_data = metric_data
        metrics.append(frame)
