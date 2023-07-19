import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from configargparse import Namespace
from pydantic import BaseModel, Extra

from ..exporter.constants import (
    METADATA_PREFIX,
    METADATA_DELIMITER,
    NAME_KEY,
    DEFAULT_ELASTICSEARCH_INDEX_PREFIX,
    IS_SERVER_KEY)
from ..utils.compatibility import removeprefix
from ..utils.utils import get_hostname_from_ip

BUILD_KEY = "build"
BRANCH_BUILD_KEY = "branch_build"
BRANCH_KEY = "branch"
COMMIT_KEY = "commit"
SHORT_COMMIT_KEY = "short_commit"
TYPE_KEY = "type"
VERSION_KEY = "version"
UNKNOWN_VALUE = "unknown"
SERVER_VALUE = "server"
CLIENT_VALUE = "client"
INVALID_VALUE = "invalid"
DEV_VALUE = "dev"
DEFAULT_VERSION_KEY_VALUE = "0.0.0"

log = logging.getLogger(__name__)


def get_meta_from_bookmark(bookmark: str) -> Tuple[Optional[str], Optional[str]]:
    if bookmark.startswith(METADATA_PREFIX):
        metadata: List[str] = bookmark.split(METADATA_DELIMITER, maxsplit=2)
        if len(metadata) > 1:
            return metadata[1], metadata[2] if len(metadata) == 3 else None
    return None, None


def get_bookmarks_metadata(bookmarks: List[dict], metadata_names: List[str] = None) -> dict:
    result: Dict = defaultdict(dict)

    if not bookmarks:
        return result

    allowed_keys = {*TraceMeta.__fields__.keys(), *(metadata_names or [])}

    for row in bookmarks:
        key, value = get_meta_from_bookmark(row[NAME_KEY])
        if any([key is None, value is None, key not in allowed_keys]):
            continue

        if key == IS_SERVER_KEY:
            result[TYPE_KEY] = SERVER_VALUE if int(value) else CLIENT_VALUE
            continue

        if key == VERSION_KEY:
            if value == "0.0.0.dev":
                result.update(
                    {
                        VERSION_KEY: DEFAULT_VERSION_KEY_VALUE,
                        BUILD_KEY: DEV_VALUE,
                        BRANCH_BUILD_KEY: 0,
                        BRANCH_KEY: DEV_VALUE,
                        SHORT_COMMIT_KEY: ""
                    })
                continue

            value = value.lower()
            version_match = re.match("([0-9]+).([0-9]+).([0-9]+).([0-9]+)(-([0-9]+))?(-(.+))?-(.+)", value)
            if version_match is None:
                continue

            result.update(
                {
                    VERSION_KEY: f"{version_match.group(1)}.{version_match.group(2)}.{version_match.group(3)}",
                    BUILD_KEY: version_match.group(4),
                    BRANCH_BUILD_KEY: version_match.group(6) or 0,
                    BRANCH_KEY: version_match.group(8) or "",
                    SHORT_COMMIT_KEY: version_match.group(9)
                })
            continue

        result[key] = value

    return result


def get_trace_info(bookmarks: List[dict], bookmark_name: str) -> Optional[dict]:
    """Get trace info out of the bookmark event."""
    result: Dict = defaultdict(dict)
    if not bookmark_name:
        return result

    for row in bookmarks:
        if row[NAME_KEY].startswith(bookmark_name):
            trace_info = removeprefix(row[NAME_KEY], bookmark_name).lower()
            # remove this branch after VSP-14652 is merged
            version_match = re.match(
                ":([0-1]+):(.+):([0-9]+).([0-9]+).([0-9]+).([0-9]+)(-([0-9]+))?(-(.+))?-(.+)",
                trace_info)
            if version_match:
                result.update(
                    {
                        TYPE_KEY: SERVER_VALUE if int(version_match.group(1)) else CLIENT_VALUE,
                        COMMIT_KEY: version_match.group(2),
                        VERSION_KEY: f"{version_match.group(3)}.{version_match.group(4)}.{version_match.group(5)}",
                        BUILD_KEY: version_match.group(6),
                        BRANCH_BUILD_KEY: version_match.group(8),
                        BRANCH_KEY: version_match.group(10),
                        SHORT_COMMIT_KEY: version_match.group(11),
                    })
                return result

    return result


def try_parse_trace_name(trace_name):
    IDX_TRACE_DATE: int = 0
    IDX_TRACE_TIME: int = 1
    IDX_WORKSTATION: int = 2
    REQUIRED: int = 3
    DELIMITER = "_"
    APPROXIMATE: str = "approx"

    segments = trace_name.split(DELIMITER)
    segments_count = len(segments)
    if segments_count == REQUIRED:
        test_start = segments[IDX_TRACE_DATE] + DELIMITER + segments[IDX_TRACE_TIME]
        return test_start, segments[IDX_WORKSTATION]

    current_time_str = datetime.now().strftime(APPROXIMATE + DELIMITER + "%Y%m%d" + DELIMITER + "%H%M%S")
    return current_time_str, UNKNOWN_VALUE


class DotDefaultDict(defaultdict):
    __getattr__ = defaultdict.get
    __setattr__ = defaultdict.__setitem__
    __delattr__ = defaultdict.__delitem__


class TraceMeta(BaseModel):
    class Config:
        extra = Extra.allow

    es_index: str = None
    branch: str = None
    type: str = None
    commit: str = None
    short_commit: str = None
    version: str = None
    branch_build: str = None

    title: str = None
    build: str = None
    parameter: str = None
    workstation: str = None
    test_start: str = None
    test_name: str = None
    test_id: str = None

    perfana_ulr: str = None

    started_timestamp: float = 0.0
    processed_timestamp: float = 0.0

    def __init__(self, **kwargs):
        super(TraceMeta, self).__init__(**kwargs)

    def update(self, bookmarks: List[dict], trace_name: str, metadata_names: List[str] = None,
               parsed_args: Namespace = None,
               **kwargs):
        parsed_args = parsed_args or DotDefaultDict(default_factory=None)

        init_data = get_bookmarks_metadata(
            bookmarks,
            metadata_names)
        if not init_data[VERSION_KEY]:
            init_data = get_trace_info(
                bookmarks,
                parsed_args.trace_info)
        if not init_data[VERSION_KEY]:
            init_data = {
                VERSION_KEY: DEFAULT_VERSION_KEY_VALUE,
                BUILD_KEY: INVALID_VALUE,
                BRANCH_BUILD_KEY: 0,
                BRANCH_KEY: INVALID_VALUE,
                SHORT_COMMIT_KEY: ""
            }
            log.warning(f"No trace version found! Trace seem to be corrupt or incomplete.")

        started_timestamp = self.started_timestamp

        super().__init__(**init_data, **kwargs)

        self.test_start, *workstation = try_parse_trace_name(trace_name)
        self.test_id = self.test_id or f"noid_{trace_name}"
        self.test_name = self.test_name or UNKNOWN_VALUE
        self.parameter = self.parameter or self.version
        self.build = parsed_args.build or self.build

        # title
        if parsed_args.title is None:
            self.title = f"{self.version}.{self.build}"
            self.title += f"-{self.branch}" if self.branch else ""
            self.title += f"-{self.short_commit}" if self.short_commit else ""
        else:
            self.title = parsed_args.title

        # workstation
        self.workstation = parsed_args.workstation or self.workstation
        if not self.workstation:
            if workstation and workstation[0]:
                self.workstation = get_hostname_from_ip(workstation[0])
            self.workstation = self.workstation or UNKNOWN_VALUE
        self.workstation = self.workstation.lower()

        self.es_index = self._make_es_index(parsed_args.elasticsearch_index_prefix)
        self.started_timestamp = started_timestamp

    def to_elasticsearch(self) -> Dict[str, Any]:
        return self.dict(exclude={"perfana_ulr"})

    def _make_es_index(self, es_index_prefix: str):
        index_name = f"{es_index_prefix}-" if es_index_prefix else f"{DEFAULT_ELASTICSEARCH_INDEX_PREFIX}-"
        index_name += f"{'.'.join(self.version.split('.')[:2])}"
        index_name += f"-{self.branch}" if self.branch else ""
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-create-index.html
        return index_name[:255]
