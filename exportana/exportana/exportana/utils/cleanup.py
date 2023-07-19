import asyncio
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List

import aioschedule
from elasticsearch import Elasticsearch
from elasticsearch import exceptions
from elasticsearch._async.client import AsyncElasticsearch

from ..database.broker import MongoDatabase
from ..exporter.constants import UTRACE_EXT, INF
from ..models.base import VerboseResult
from ..models.traces import ProcessedTraceInfo
from ..utils.compatibility import removesuffix
from ..utils.utils import timing

log = logging.getLogger(__name__)


def cleanup_indices(elastic_url: str):
    log.info(f"Cleaning indices")

    es = Elasticsearch(hosts=[elastic_url], retry_on_timeout=True)
    for index in es.indices.get_alias(index="*"):
        if index[0] != ".":
            es.indices.delete(index=index, ignore=[400, 404])


async def delete_traces_from_index(es: AsyncElasticsearch,
                                   es_index: str,
                                   test_id: str,
                                   workstation: str,
                                   test_start: str) -> VerboseResult:
    KEY_TEST_ID = "test_id"
    KEY_WORKSTATION = "workstation"
    KEY_TEST_START = "test_start"
    KEY_MATCH = "match"
    KEY_FAILURES = "failures"

    try:
        error_msg_list = list()
        response = await es.delete_by_query(
            index=es_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {KEY_MATCH: {KEY_TEST_ID: test_id}},
                            {KEY_MATCH: {KEY_WORKSTATION: workstation}},
                            {KEY_MATCH: {KEY_TEST_START: test_start}},
                        ]
                    }
                }
            },
            conflicts="proceed"
        )
        failures = response[KEY_FAILURES]
        if len(failures) > 0:
            for fail in failures:
                error_msg_list.append(fail)

        return VerboseResult(True, *error_msg_list)
    except (exceptions.ConnectionError, exceptions.ConnectionTimeout) as e:
        error_msg = f"Get from Elastic: Can't connect to any of elasticsearch hosts. {e}"
        log.error(error_msg)
        return VerboseResult(False, error_msg)
    except Exception as e:
        error_msg = f"Get from Elastic: Something else. {e}"
        log.error(error_msg)
        return VerboseResult(False, error_msg)


@dataclass
class CleanupTracesInfo:
    force_cleanup: bool = None
    cleanup_unprocessed: bool = None
    trace_sessions_dir: str = None

    cleanup_ignore: List[str] = None

    cleanup_master_days: float = None
    cleanup_release_days: float = None
    cleanup_branches_days: float = None
    cleanup_interval_hours: float = None


def get_time_from_test_start(test_start: str) -> datetime:
    TIME_MASK = "%H%M%S"

    time_str = datetime.now().strftime(TIME_MASK)
    if test_start:
        time_variants = re.findall(r"(\d{6})$", test_start)
        if len(time_variants) > 0:
            time_str = time_variants[0]

    return datetime.strptime(time_str, TIME_MASK)


@timing("Cleanup traces", log_level=logging.INFO)
async def _cleanup_traces(info: CleanupTracesInfo):
    SECONDS_IN_DAY = 24 * 60 * 60
    log.info("Cleanup traces: started")

    db: MongoDatabase = MongoDatabase()
    db.init()

    current_time = datetime.now()
    max_delta_master = info.cleanup_master_days * SECONDS_IN_DAY
    max_delta_release = info.cleanup_release_days * SECONDS_IN_DAY
    max_delta_branches = info.cleanup_branches_days * SECONDS_IN_DAY

    def remove_trace_artifacts_if_old(processed_trace_info: ProcessedTraceInfo):
        last_processing_report = processed_trace_info.processing_reports[-1]
        branch = last_processing_report.trace_meta.branch
        scenario = branch
        if branch == "master":
            max_delta = max_delta_master
        elif not branch:
            max_delta = max_delta_release
            scenario = "release"
        else:
            max_delta = max_delta_branches
            scenario = "branch"

        log.debug(
            f"Cleanup traces: "
            f"Try to remove trace: {last_processing_report.trace_name}, "
            f"Scenario: {scenario}, "
            f"Branch: {branch}, "
            f"Trace storage time (sec): {max_delta}, "
            f"Processed date: {last_processing_report.processed_date}"
        )

        delta_time = current_time - last_processing_report.processed_date
        need_to_remove = max_delta < delta_time.total_seconds()
        trace_path = os.path.join(info.trace_sessions_dir, last_processing_report.trace_name)
        trace_path += UTRACE_EXT
        if not need_to_remove:
            log.debug(f"Cleanup traces: No need to delete trace file: {trace_path}")
            return
        try:
            os.remove(trace_path)
        except Exception as e:
            log.error(f"Cleanup traces: Error on delete trace file: {trace_path}: {type(e).__name__}: {e}")
        else:
            log.info(f"Cleanup traces: Remove trace: {last_processing_report.trace_name}")

        log.info(f"Cleanup traces: Remove trace: {last_processing_report.trace_name}")

    async with await db.start_session() as session, session.start_transaction():
        trace_file_names = os.listdir(info.trace_sessions_dir)
        for trace_file_name in trace_file_names:
            if trace_file_name.endswith(UTRACE_EXT):
                trace_name = removesuffix(trace_file_name, UTRACE_EXT)

                if info.cleanup_ignore and trace_name in info.cleanup_ignore:
                    log.debug(f"Cleanup traces. Ignore trace: {trace_name}")
                    continue

                trace_in_queue = await db.find_queued_trace(trace_name)
                if trace_in_queue:
                    log.debug(f"Cleanup traces. Trace {trace_name} in queue. Ignore")
                    continue

                trace = await db.find_ready_trace(trace_name)
                if not trace:
                    trace = await db.find_poisoned_trace(trace_name)
                if trace:
                    remove_trace_artifacts_if_old(trace)
                else:
                    log.debug(
                        f"Cleanup traces. Can't find trace info: {trace_name} "
                        f"in ready_traces table, poisoned_traces table"
                    )

    db.close()


async def scheduler_loop(info: CleanupTracesInfo):
    TIMEOUT_SEC: int = 60
    aioschedule.every(info.cleanup_interval_hours).hours.do(_cleanup_traces, info)

    if info.cleanup_interval_hours == float(INF):
        info.cleanup_interval_hours = None

    if info.force_cleanup:
        await _cleanup_traces(info)

    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(TIMEOUT_SEC)


def schedule_cleanup_traces(info: CleanupTracesInfo):
    scheduler_thread = threading.Thread(target=asyncio.run, daemon=True, args=(scheduler_loop(info),))
    scheduler_thread.start()
