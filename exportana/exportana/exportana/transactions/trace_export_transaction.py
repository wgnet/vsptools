import json
import logging
import multiprocessing
import random
import string
from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import unquote, urlparse

import requests
from atlassian import Bitbucket
from configargparse import Namespace
from elasticsearch import exceptions
from elasticsearch._async.client import AsyncElasticsearch
from elasticsearch._async.client.indices import IndicesClient
from elasticsearch._async.helpers import async_streaming_bulk
from elasticsearch.helpers.errors import BulkIndexError

from .base_transaction import BaseExportanaTransaction
from .exceptions.external_service_exception import ExternalServiceException
from .exceptions.trace_exception import TraceException
from ..exporter.constants import (
    DEFAULT_ELASTICSEARCH_INDEX_PREFIX,
    NAME_KEY,
    TIMESTAMP_KEY,
    PATH_DELIMITER,
    DOC_TYPE_KEY,
    DOC_TYPE_BUDGET,
    SETTINGS_KEY,
    KEY_SETTINGS,
    KEY_MAPPING,
    KEY_TOTAL_FIELDS,
    KEY_LIMIT,
    KEY_INDEX,
    DEF_INDEX_FIELDS_LIMIT,
    DOC_TYPE_METRIC
)
from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta, get_meta_from_bookmark
from ..models.trace_with_context import TraceInfoWithContext
from ..routes import metrics_receiver
from ..routes.metrics_receiver import Frame
from ..utils.cleanup import delete_traces_from_index
from ..utils.compatibility import removesuffix
from ..utils.utils import timing

TIME_FIELD_NAME = "Time"

log = logging.getLogger(__name__)

MetricsProcessingReturnType = Optional[Tuple[Optional[float], Optional[dict]]]


def get_index_total_fields_limit_settings(index_name: str, settings: dict, limit: int = DEF_INDEX_FIELDS_LIMIT) -> dict:
    try:
        current_limit = int(settings[index_name][KEY_SETTINGS][KEY_INDEX][KEY_MAPPING][KEY_TOTAL_FIELDS][KEY_LIMIT])
    except KeyError as e:
        log.warning(e)
        current_limit = DEF_INDEX_FIELDS_LIMIT

    if current_limit >= limit:
        limit = current_limit
    settings = {
        KEY_SETTINGS: {
            KEY_INDEX: {
                KEY_MAPPING: {
                    KEY_TOTAL_FIELDS: {
                        KEY_LIMIT: limit,
                    }
                }
            }
        }
    }
    return settings


def metrics_processing(frame: Frame, norm_time: Tuple[Optional[float], Optional[float]]) -> MetricsProcessingReturnType:
    if not frame.frame_start or not frame.frame_end:
        return None
    if frame.frame_end <= frame.frame_start:
        return None
    real_start_time = frame.frame_start
    start_time = real_start_time

    if norm_time[0] is not None:
        if start_time < norm_time[0]:
            return None
        start_time -= norm_time[0]
    if norm_time[1] is not None and real_start_time > norm_time[1]:
        return None
    start_time_sec = start_time / 1000
    hours, remainder = divmod(int(start_time_sec), 3600)
    minutes, seconds = divmod(remainder, 60)

    frame.data[TIME_FIELD_NAME] = "{:02d}:{:02d}:{:02d}.{:03d}".format(
        hours,
        minutes,
        seconds,
        int(start_time % 1 * 1000)
    )

    metrics_data = frame.data
    metrics_data[DOC_TYPE_KEY] = DOC_TYPE_METRIC
    metrics_data[SETTINGS_KEY] = frame.raw_data

    return real_start_time, metrics_data


class TraceExportTransaction(BaseExportanaTransaction):
    __KEY_TYPE = "type"
    __KEYWORD_VALUE = "keyword"
    __KEY_NULL_VALUE = "null_value"
    __NULL_VALUE = "null"

    __INDEX_SETTINGS = {
        KEY_SETTINGS: {
            KEY_INDEX: {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                KEY_MAPPING: {
                    KEY_TOTAL_FIELDS: {
                        KEY_LIMIT: DEF_INDEX_FIELDS_LIMIT,
                    }
                }
            }
        }
    }

    __MAPPING = {
        "properties": {
            "test_name": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "test_id": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "build": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "parameter": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "workstation": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "test_start": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "title": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            "type": {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: __NULL_VALUE
            },
            DOC_TYPE_KEY: {
                __KEY_TYPE: __KEYWORD_VALUE,
                __KEY_NULL_VALUE: DOC_TYPE_METRIC
            },
            TIME_FIELD_NAME: {
                __KEY_TYPE: "date",
                "format": "HH:mm:ss.SSS"
            }
        }
    }

    def __init__(self, args: Namespace,
                 trace_info: TraceInfoWithContext,
                 trace_meta: TraceMeta,
                 verbose_result: VerboseResult):
        super().__init__(args, trace_info, trace_meta, verbose_result)
        self._es: AsyncElasticsearch = None
        self.thread_pool_size = args.thread_pool_size if args.thread_pool_size > 0 else multiprocessing.cpu_count()

    def append_budgets(self, prepared: dict):
        SETTINGS_IDX = 0
        if metrics_receiver.metrics_budgets:
            prepared[SETTINGS_IDX] = metrics_receiver.metrics_budgets
            prepared[SETTINGS_IDX][DOC_TYPE_KEY] = DOC_TYPE_BUDGET
            prepared[SETTINGS_IDX][SETTINGS_KEY] = metrics_receiver.metrics_settings
        return prepared

    async def execute(self):
        if not metrics_receiver.is_metrics_available():
            error_msg = f"No data has been received from Unreal Insights. " \
                        f"MetricsNamesCount: {len(metrics_receiver.metrics_names)} " \
                        f"MetricsHeader: {metrics_receiver.metrics_header} " \
                        f"MetricsCount: {len(metrics_receiver.metrics)}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise TraceException(error_msg)

        header = [TIME_FIELD_NAME]
        metrics_names = metrics_receiver.metrics_names
        header.extend(metrics_names)

        self._es = AsyncElasticsearch(hosts=self._trace_info.worker_configuration.elastic, retry_on_timeout=True)
        self._trace_meta.update(
            metrics_receiver.metrics_bookmarks,
            self._trace_info.trace_name,
            metrics_receiver.metadata_names,
            self._args
        )

        normal_time = self._get_normal_time(self._args.normalize, metrics_receiver.metrics_bookmarks)
        # region --------------------- process thread ---------------------
        prepared = self._process_threads(metrics_receiver.metrics, normal_time)
        # endregion

        if len(prepared) == 0:
            error_msg = f"Trace '{self._trace_info.trace_name}' can't be processed: there are no data in profiling."
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise TraceException(error_msg)

        self.append_budgets(prepared)

        # region --------------------- make index ---------------------
        index_name = f"{self._args.elasticsearch_index_prefix}-" if self._args.elasticsearch_index_prefix else f"{DEFAULT_ELASTICSEARCH_INDEX_PREFIX}- "
        index_name += f"{'.'.join(self._trace_meta.version.split('.')[:2])}"
        index_name += f"-{self._trace_meta.branch}" if self._trace_meta.branch else ""
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-create-index.html
        index_name = index_name[:255]
        # endregion
        # region --------------------- build index ---------------------
        await self._build_index(index_name, header)
        # endregion
        # region --------------------- delete duplicate in the index ---------------------
        del_dupl_res: VerboseResult = await delete_traces_from_index(self._es,
                                                                     index_name,
                                                                     self._trace_meta.test_id,
                                                                     self._trace_meta.workstation,
                                                                     self._trace_meta.test_start)
        # -------------------------------------------------------------------------
        if not del_dupl_res:
            log.error(" ".join(del_dupl_res.errors))
        # endregion
        # region --------------------- push to elastic ---------------------
        await self._push_to_elastic(index_name, prepared, self._trace_meta)
        # endregion
        # region --------------------- try to create perfana layout ---------------------
        layout_id = self._create_perfana_layout(index_name, self._trace_meta, metrics_names)
        # endregion
        # region --------------------- try to push to the bitbucket ---------------------
        self._trace_meta.perfana_ulr = f"{removesuffix(self._trace_info.worker_configuration.perfana, PATH_DELIMITER)}/api/layout?uid={layout_id}"
        self._update_bitbucket_report(layout_id, self._trace_meta.title, self._trace_meta)
        # endregion

        self._trace_meta.processed_timestamp = datetime.now().timestamp()
        self.verbose_result.result = True

    async def rollback(self):
        if self._es:
            await self._es.close()

    async def commit(self):
        if self._es:
            await self._es.close()

    def _process_threads(
        self, metrics: List[Frame],
        normal_time: Tuple[Optional[float], Optional[float]]
    ) -> Dict[str, Any]:
        log.info("Process threads")

        prepared = defaultdict(dict)

        for metric in metrics:
            record = metrics_processing(metric, normal_time)
            if record:
                real_start_time, frame_data = record
                prepared[real_start_time] = frame_data

        return prepared

    @staticmethod
    def _get_normal_time(bookmark_name: List[str], bookmarks: List[dict]) -> Tuple[Optional[float], Optional[float]]:
        """Get time of the bookmark event."""
        start_time = None
        end_time = None
        if not bookmark_name:
            return start_time, end_time
        if not bookmarks:
            return start_time, end_time

        start_bookmark = bookmark_name[0]
        end_bookmark = bookmark_name[1] if len(bookmark_name) == 2 else None

        for row in bookmarks:
            key, _ = get_meta_from_bookmark(row[NAME_KEY])
            if key is None:
                key = row[NAME_KEY]

            if start_bookmark == key:
                start_time = float(row[TIMESTAMP_KEY])
            # skip end bookmarks preceding a start one
            elif all([end_bookmark is not None, end_bookmark == key, start_time is not None]):
                end_time = float(row[TIMESTAMP_KEY])
                return start_time, end_time

        return start_time, end_time

    @staticmethod
    def _sanitize_event_name(name: str) -> str:
        """Remove confusing symbols from the event name."""
        return name.translate(str.maketrans("", "", "!@#$."))

    async def _update_index_field_limit_if_needed(self, index_name: str, limit: int):
        index_settings = await self._es.indices.get_settings(index=index_name)
        settings = get_index_total_fields_limit_settings(index_name, index_settings, limit)
        await self._es.indices.put_settings(
            index=index_name,
            body=settings
        )

    async def _create_index(self, index_name: str, mapping: dict):
        await self._es.indices.create(index=index_name, body=self.__INDEX_SETTINGS)
        if self._args.elastic_mapping_limit > 0:
            await self._update_index_field_limit_if_needed(index_name, self._args.elastic_mapping_limit)
        await self._es.indices.put_mapping(body=mapping, index=index_name)

    async def _build_index(self, index_name: str, header: List[str]):
        """
        Builds index and mapping.
        :return:
            - `bool`: determines is build succeeded;
            - `Optional[str]`: an error/warning string.
        """
        KEY_PROPERTY = "properties"

        log.info(f"Building elasticsearch index {index_name}")
        index = IndicesClient(self._es)
        try:
            mapping = self.__MAPPING
            for h in header:
                mapping[KEY_PROPERTY][h] = mapping[KEY_PROPERTY].get(h, {self.__KEY_TYPE: "float"})
            for metadata_name in metrics_receiver.metadata_names:
                mapping[KEY_PROPERTY][metadata_name] = mapping[KEY_PROPERTY].get(metadata_name, {
                    self.__KEY_TYPE: self.__KEYWORD_VALUE,
                    self.__KEY_NULL_VALUE: self.__NULL_VALUE
                })
            if self._args.dump_mapping:
                log.info(mapping)

            if await index.exists(index=index_name):
                if self._args.same_index:
                    log.info("Index already exists, updating: {}".format(index_name))
                    if self._args.elastic_mapping_limit > 0:
                        await self._update_index_field_limit_if_needed(index_name, self._args.elastic_mapping_limit)
                else:
                    log.info("Index already exists, replacing: {}".format(index_name))
                    await self._es.indices.delete(index=index_name, ignore=[400, 404])
                    await self._create_index(index_name, mapping)
            else:
                await self._create_index(index_name, mapping)
        except (exceptions.ConnectionError, exceptions.ConnectionTimeout, exceptions.RequestError) as e:
            error_msg = f"Builds index: Can't connect to any of elasticsearch hosts: {self._es.transport.hosts}. {e}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise ExternalServiceException(error_msg)

    @timing("Pushing to Elastic")
    async def _push_to_elastic(self, index_name: str, prepared: Dict, trace_meta: TraceMeta):
        """Pushes data into Elastic.
        :return:
            - `bool`: determines is push succeeded;
            - `Optional[str]`: an error/warning string.
        """
        log.info(f"Push to Elastic: {index_name}")

        trace_meta_dict = trace_meta.to_elasticsearch()

        def get_data():
            for data in prepared.values():
                data.update(trace_meta_dict)
                yield {
                    "_index": index_name,
                    "_source": json.dumps(data)
                }

        try:
            async for ok, response in async_streaming_bulk(self._es, actions=get_data()):
                if not ok:
                    error_msg = f"Push to Elastic: Can't insert: {index_name}"
                    self.verbose_result.result = False
                    self.verbose_result.errors.append(error_msg)
                    raise ExternalServiceException(error_msg)
        except (exceptions.ConnectionError, exceptions.ConnectionTimeout, exceptions.RequestError) as e:
            error_msg = f"Push to Elastic: Can't connect to any of elasticsearch hosts: {self._es.transport.hosts}. {e}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise ExternalServiceException(error_msg)
        except BulkIndexError as e:
            error_msg = f"Push to Elastic: {self._extract_exception_reason(e)}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise TraceException(error_msg)

    def _extract_exception_reason(self, exception: BulkIndexError):
        BULK_ERROR_MESSAGE = "Bulk index error"
        ERROR_KEY = "error"
        CAUSED_BY_KEY = "caused_by"
        REASON_KEY = "reason"
        RECORD_DATA_IDX = 1
        if len(exception.args) > 1:
            records = exception.args[RECORD_DATA_IDX]
            if len(records) > 0:
                record: dict = records[0]
                index_data: dict = record.get(KEY_INDEX, None)
                if index_data:
                    error_data = index_data.get(ERROR_KEY, None)
                    if error_data:
                        caused_by_data = error_data.get(CAUSED_BY_KEY, None)
                        if caused_by_data:
                            reason = caused_by_data.get(REASON_KEY, BULK_ERROR_MESSAGE)
                            return reason
        return BULK_ERROR_MESSAGE


    def _create_perfana_layout(self, index_name: str, trace_meta: TraceMeta, metrics: List[str]):
        """
        Create perfana layout for current `trace_name` with this `trace_meta` and presselected `metrics`
        :return:
            - `bool`: determines is layout creation succeeded;
            - `Optional[str]`: if `bool` option are `True` - this is an `layout_id`,
            otherwise - it's a string with error/warning which occurred during `layout_id` generation.
        """
        try:
            layout_id = "".join(random.choices(string.ascii_letters + string.digits, k=9))
            with open(f'perfana.{trace_meta.type if trace_meta.type else "client"}.layout', "r") as f:
                selected_metrics_aggs = {m: ["avg"] for m in metrics}

                template = f.read().replace('\n', '')
                layout = string.Template(template).substitute(
                    trace_name=index_name,
                    layout_id=layout_id,
                    selected_metrics=json.dumps(metrics),
                    metrics=json.dumps(metrics),
                    selected_metrics_aggs=json.dumps(selected_metrics_aggs),
                    build=trace_meta.build,
                    title=trace_meta.title,
                    workstation=trace_meta.workstation,
                    test_name=trace_meta.test_name,
                    test_id=trace_meta.test_id,
                    version=trace_meta.version,
                    test_start=trace_meta.test_start,
                    parameter=trace_meta.parameter,
                    type=str(trace_meta.type))

            log.debug(f"Pushing layout to Perfana: {layout}")
            headers = {"Content-type": "application/json", "Accept": "text/plain"}
            req = requests.post(f"{self._trace_info.worker_configuration.perfana}/api/layout", data=layout,
                                headers=headers)
            if req.status_code == requests.codes.ok:
                return layout_id
            log.warning(f"Can't push layout to Perfana: {req.text}")
            self.verbose_result.errors.append(req.text)
        except BaseException as e:
            error_msg = f"Can't push layout to Perfana. {type(e).__name__}: {e}"
            log.warning(error_msg)
            self.verbose_result.errors.append(error_msg)

    @timing("Pushing report to bitbucket")
    def _update_bitbucket_report(self, layout_id: str, title: str, trace_meta: TraceMeta):
        """Post to Bitbucket Code Insights with reference to Perfana report
        :return:
            - `bool`: determines is report succeeded;
            - `Optional[str]`: an error/warning string.
        """
        # *** prepare bitbucket requisites
        bitbucket_url_parsed = None
        try:
            bitbucket_url_parsed = urlparse(self._args.bitbucket)
        except ValueError as e:
            error_msg = f"Bad bitbucket url: {self._args.bitbucket}. {type(e).__name__}: {e}"
            log.warning(error_msg)
            self.verbose_result.errors.append(error_msg)
            return

        if bitbucket_url_parsed:
            bitbucket_url = f"{bitbucket_url_parsed.scheme}://{bitbucket_url_parsed.hostname}"
            bitbucket_user = bitbucket_url_parsed.username
            bitbucket_token = bitbucket_url_parsed.password

            # ('/', 'scm', 'VSP', 'game.git')
            path = PurePosixPath(unquote(bitbucket_url_parsed.path))
            if len(path.parts) != 4 or path.parts[1] != "scm":
                error_msg = f"Use proper bitbucket url format: https://user:token@bitbucket/scm/vsp/game.git"
                log.warning(error_msg)
                self.verbose_result.errors.append(error_msg)
                return

            bitbucket_project = path.parts[2]
            bitbucket_repo = removesuffix(path.parts[3], ".git")

            try:
                log.info(f"Pushing Perfana report link '{trace_meta.perfana_ulr}' to BitBucket")
                bitbucket = Bitbucket(
                    url=bitbucket_url,
                    oauth2={
                        "client_id": bitbucket_user,
                        "token": {"access_token": bitbucket_token},
                    })

                bitbucket.create_code_insights_report(
                    project_key=bitbucket_project,
                    repository_slug=bitbucket_repo,
                    commit_id=trace_meta.commit,
                    report_key=layout_id,
                    report_title=f'{title}-{layout_id}',
                    link=trace_meta.perfana_ulr
                )
            except BaseException as e:
                error_msg = f"Can't push report to bitbucket. {type(e).__name__}: {e}"
                log.warning(error_msg)
                self.verbose_result.errors.append(error_msg)
