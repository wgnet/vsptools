import json
import logging
from datetime import datetime
from typing import List, Optional

import httpx
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, status, Request
from fastapi.responses import Response

from ..configs import Configs
from ..database.broker import MongoDatabase
from ..database.utils import retry_on_mongo_exception
from ..exporter.constants import KEY_TRACE_NAME, KEY_TRACE_ID, KEY_TRACE_SIZE, KEY_TIME_STAMP, UTRACE_EXT
from ..exporter.manager import add_queued_trace
from ..models.base import VerboseResult
from ..models.trace_with_context import TraceInfoWithContext, TraceInProcessing
from ..models.traces import TraceInfo, ProcessedTraceInfo, ProcessedTraceReport, TraceInfoStatus, TraceStatus
from ..models.worker import Worker, WorkerStatus, WorkerInfo
from ..models.worker_configuration import WorkerConfiguration
from ..utils import monitoring
from ..utils.cleanup import delete_traces_from_index
from ..utils.compatibility import removesuffix
from ..utils.utils import make_entrypoint_address

__ALL__ = ["router"]

log = logging.getLogger(__name__)

router = APIRouter(prefix="/manager", responses={404: {"description": "Page not found"}})
trace_router = APIRouter(prefix="/trace", tags=["manager / trace"])
worker_router = APIRouter(prefix="/worker", tags=["manager / worker"])

workers_addresses: set = set()


@worker_router.get("/list", response_model=List[WorkerInfo])
async def worker_list(request: Request):
    async with httpx.AsyncClient() as client:
        workers: List[WorkerInfo] = list()

        for worker_address in workers_addresses:
            entrypoint_url = make_entrypoint_address(f"http://{worker_address}", ["worker", "status"])
            response: Response = None
            try:
                response: Response = await client.request(method="GET", url=entrypoint_url)
            except Exception as e:
                worker_info = WorkerInfo()
                worker_info.url = worker_address
                worker_info.status = WorkerStatus.offline
                workers.append(worker_info)
                continue

            if response and response.status_code == status.HTTP_200_OK:
                try:
                    worker_info: WorkerInfo = json.loads(response.content, object_hook=lambda d: WorkerInfo(**d))
                    workers.append(worker_info)
                except Exception as e:
                    if response and response.text:
                        log.warning(f"worker_list. Error on deserialize worker_info {response.text}. {e}")

    idle_workers = filter(lambda w: w.status == WorkerStatus.idle, workers)
    working_workers = filter(lambda w: w.status == WorkerStatus.working, workers)
    offline_workers = filter(lambda w: w.status == WorkerStatus.offline, workers)

    return [*working_workers, *idle_workers, *offline_workers]


@trace_router.get("/queued/list", response_model=List[TraceInfoWithContext])
@retry_on_mongo_exception
async def trace_queued_list(request: Request):
    db: MongoDatabase = request.state.db
    queued_traces = await db.get_queued_traces()
    return queued_traces


@trace_router.get("/queued/acquire", response_model=TraceInfoWithContext)
@retry_on_mongo_exception
async def trace_queued_acquire(request: Request, worker: Worker):
    workers_addresses.add(worker.url)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        trace_info: Optional[TraceInfoWithContext] = None
        trace_in_processing = await db.find_processing_trace(worker.url)
        if trace_in_processing:
            trace_info = trace_in_processing
        else:
            trace_info = await db.extract_trace_from_queue(session)

        if trace_info is None:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        if not trace_info.worker_configuration:
            trace_info.worker_configuration = WorkerConfiguration()
        # region set metrics for prometheus
        traces_count = await db.get_queued_trace_count(session)
        monitoring.set_traces_queue_count(traces_count)
        monitoring.set_worker_status(worker.url, WorkerStatus.working)
        # endregion
        log.debug(f"trace_queued_acquire: worker={worker.json()} acquired={trace_info.json()}")

        if not trace_in_processing:
            trace_in_processing = TraceInProcessing()
            trace_in_processing.trace_name = trace_info.trace_name
            trace_in_processing.creation_date = trace_info.creation_date
            trace_in_processing.worker_configuration = trace_info.worker_configuration
            trace_in_processing.worker_url = worker.url
            await db.set_processing_trace(trace_in_processing)

        return trace_info


@trace_router.put("/queued/put", response_model=TraceInfo, status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_queued_put(request: Request, trace_name: str):
    if trace_name.endswith(UTRACE_EXT):
        trace_name = removesuffix(trace_name, UTRACE_EXT)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        result = await add_queued_trace(db, trace_name, WorkerConfiguration(), datetime.now())
        # region set metrics for prometheus
        traces_count = await db.get_queued_trace_count(session)
        monitoring.set_traces_queue_count(traces_count)
        # endregion
        return result


@trace_router.put("/queued/put_trace_meta", response_model=TraceInfo, status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_queued_put_trace_meta(request: Request, trace_data: dict):
    if not all(k in trace_data for k in (KEY_TRACE_ID, KEY_TRACE_NAME, KEY_TRACE_SIZE, KEY_TIME_STAMP)):
        log.error(f"trace_queued_put_trace_meta: invalid data format: {trace_data}")
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    else:
        trace_name = trace_data[KEY_TRACE_NAME]
        log.info(f"trace_queued_put_trace_meta: trace {trace_name} was added to the queue.")
        log.debug(
            f"Trace. Id: {trace_data[KEY_TRACE_ID]}, "
            f"Name: {trace_name}, "
            f"Size: {trace_data[KEY_TRACE_SIZE]}, "
            f"TimeStamp: {trace_data[KEY_TIME_STAMP]}"
        )
        await trace_queued_put(request, trace_name)


@trace_router.put("/queued/drop", response_model=TraceInfo, status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_queued_drop(request: Request, trace_name: str):
    if trace_name.endswith(UTRACE_EXT):
        trace_name = removesuffix(trace_name, UTRACE_EXT)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        trace_info = await db.find_queued_trace(trace_name)
        if not trace_info:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        await db.remove_queued_trace(trace_info)
        log.warning(f"trace_queued_drop: trace {trace_name} was dropped.")
        return trace_info


@trace_router.put("/queued/mark_poisoned", response_model=TraceInfo, status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_queued_mark_poisoned(request: Request, report: ProcessedTraceReport):
    workers_addresses.add(report.worker.url)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        if report.trace_name:
            processing_trace = await db.find_processing_trace_by_name(report.trace_name, session)
            if processing_trace:
                poisoned_trace_info: ProcessedTraceInfo = await db.find_poisoned_trace(report.trace_name, session)
                if poisoned_trace_info is None:
                    poisoned_trace_info = ProcessedTraceInfo()
                    poisoned_trace_info.trace_name = report.trace_name
                    poisoned_trace_info.creation_date = processing_trace.creation_date

                report.processed_date = datetime.now()
                poisoned_trace_info.processing_reports.append(report)

                await db.set_poisoned_trace(poisoned_trace_info, session)
                await db.remove_processing_trace(report.worker.url)
                # region set metrics for prometheus
                traces_count = await db.get_poisoned_trace_count(session)
                monitoring.set_poisoned_traces_count(traces_count)
                monitoring.set_worker_status(report.worker.url, WorkerStatus.idle)
                # endregion

    error_msg = f"Exportana. Trace {report.trace_name} mark as poisoned: "
    error_msg += f"{report.result.errors}"
    log.info(error_msg)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@trace_router.put("/queued/release_from_worker", status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_queued_release_from_worker(request: Request, report: ProcessedTraceReport):
    workers_addresses.add(report.worker.url)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        if report.trace_name:
            processing_trace = await db.find_processing_trace_by_name(report.trace_name, session)
            if processing_trace:
                await add_queued_trace(
                    db,
                    processing_trace.trace_name,
                    processing_trace.worker_configuration,
                    processing_trace.creation_date
                )
                await db.remove_processing_trace(report.worker.url, session)
            # region set metrics for prometheus
            traces_count = await db.get_queued_trace_count(session)
            monitoring.set_traces_queue_count(traces_count)
            monitoring.set_worker_status(report.worker.url, WorkerStatus.idle)
            # endregion
            warning_msg = f"Exportana. Trace {report.trace_name} released from the worker {report.worker.url}: "
            warning_msg += f"{report.result.errors}"
            log.info(warning_msg)
            return Response(status_code=status.HTTP_202_ACCEPTED)


@trace_router.get("/ready/list", response_model=List[ProcessedTraceInfo])
@retry_on_mongo_exception
async def trace_ready_list(request: Request):
    db: MongoDatabase = request.state.db
    return sorted(
        await db.get_ready_traces(),
        key=lambda trace: trace.processing_reports[-1].processed_date,
        reverse=False
    )


@trace_router.get("/poisoned/list", response_model=List[ProcessedTraceInfo])
@retry_on_mongo_exception
async def trace_poisoned_list(request: Request):
    db: MongoDatabase = request.state.db
    return sorted(
        await db.get_poisoned_traces(),
        key=lambda trace: trace.processing_reports[-1].processed_date,
        reverse=False
    )


@trace_router.put("/ready/put", status_code=status.HTTP_202_ACCEPTED)
@retry_on_mongo_exception
async def trace_ready_put(request: Request, report: ProcessedTraceReport):
    workers_addresses.add(report.worker.url)

    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        processing_trace = await db.find_processing_trace_by_name(report.trace_name, session)
        if processing_trace:
            processed_trace_info: ProcessedTraceInfo = await db.find_ready_trace(report.trace_name, session)
            if processed_trace_info is None:
                processed_trace_info = ProcessedTraceInfo()
                processed_trace_info.trace_name = report.trace_name
                processed_trace_info.creation_date = processing_trace.creation_date

            report.processed_date = datetime.now()
            processed_trace_info.processing_reports.append(report)

            await db.set_ready_trace(processed_trace_info, session)
            await db.remove_processing_trace(report.worker.url, session)

            log.debug(f"trace_ready_put: {processed_trace_info}")
            # region set metrics for prometheus
            traces_count = await db.get_ready_trace_count(session)
            monitoring.set_ready_traces_count(traces_count)
            monitoring.set_trace_report_result(report)
            monitoring.set_worker_status(report.worker.url, WorkerStatus.idle)
            # endregion


@trace_router.get("/get_status", status_code=status.HTTP_200_OK)
@retry_on_mongo_exception
async def get_trace_status(request: Request, trace_name: str):
    db: MongoDatabase = request.state.db
    async with await db.start_session() as session, session.start_transaction():
        trace_info: TraceInfo = await db.find_queued_trace(trace_name, session)
        if trace_info is None:
            trace_info: TraceInProcessing = await db.find_processing_trace_by_name(trace_name, session)
            if trace_info is None:
                trace_info: ProcessedTraceInfo = await db.find_ready_trace(trace_name, session)
                if trace_info is None:
                    trace_info: ProcessedTraceInfo = await db.find_poisoned_trace(trace_name, session)
                    if trace_info is None:
                        return Response(status_code=status.HTTP_404_NOT_FOUND)
                    else:
                        response = TraceInfoStatus.parse_obj(trace_info.dict())
                        response.status = TraceStatus.POISONED
                        return response
                else:
                    response = TraceInfoStatus.parse_obj(trace_info.dict())
                    response.status = TraceStatus.PROCESSED
                    return response
            else:
                response = TraceInfoStatus.parse_obj(trace_info.dict())
                response.status = TraceStatus.IN_PROGRESS
                return response
        else:
            response = TraceInfoStatus.parse_obj(trace_info.dict())
            response.status = TraceStatus.QUEUED
            return response


@trace_router.delete("/remove", status_code=status.HTTP_200_OK)
@retry_on_mongo_exception
async def trace_remove(
    request: Request,
    es_index: str,
    test_id: str,
    workstation: str,
    test_start: str
):
    elastic_url = Configs.elastic
    es = AsyncElasticsearch(hosts=[elastic_url], retry_on_timeout=True)
    verbose_result: VerboseResult = await delete_traces_from_index(es, es_index, test_id, workstation, test_start)
    await es.close()
    return verbose_result.json()


router.include_router(worker_router)
router.include_router(trace_router)
