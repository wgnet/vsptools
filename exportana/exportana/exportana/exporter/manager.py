import datetime
import logging
import os
from typing import Optional

from .constants import UTRACE_EXT
from ..configs import Configs
from ..database.broker import MongoDatabase
from ..database.utils import retry_on_mongo_exception
from ..models.trace_with_context import TraceInfoWithContext
from ..models.traces import TraceInfo
from ..models.worker_configuration import WorkerConfiguration

log = logging.getLogger(__name__)


@retry_on_mongo_exception
async def add_queued_trace(
    database: MongoDatabase,
    trace_name: str,
    worker_configuration: WorkerConfiguration,
    creation_date: datetime
):
    async with await database.start_session() as session, session.start_transaction():
        trace_info: TraceInfoWithContext = await database.find_queued_trace(trace_name, session)
        if trace_info is None:
            trace_info = TraceInfoWithContext(trace_name=trace_name, creation_date=creation_date)
            trace_info.worker_configuration = worker_configuration
            await database.set_queued_trace(trace_info, session)
            log.info(f"Registered queued trace: {trace_info.trace_name}")
        return trace_info


async def enqueue_unprocessed_traces(database: MongoDatabase):
    @retry_on_mongo_exception
    async def find_queued_trace(trace_name: str) -> Optional[TraceInfo]:
        return await database.find_queued_trace(trace_name)

    @retry_on_mongo_exception
    async def find_ready_trace(trace_name: str) -> Optional[TraceInfo]:
        return await database.find_ready_trace(trace_name)

    traces_dir: str = os.path.join(Configs.trace_sessions_dir)
    ignore = Configs.ignore or set()

    traces = set()
    for name in os.listdir(traces_dir):
        if os.path.isfile(os.path.join(traces_dir, name)) and name.endswith(UTRACE_EXT):
            traces.add(os.path.splitext(name)[0])

    missing = set()
    for trace in traces:
        if trace in ignore:
            continue

        trace_info = await find_queued_trace(trace)
        if trace_info is not None:
            continue

        trace_info = await find_ready_trace(trace)
        if trace_info is not None:
            continue

        missing.add(trace)

    log.debug(f"Going to add to queue: {missing}, ignoring: {Configs.ignore}")

    for missed in missing:
        await add_queued_trace(database, missed, WorkerConfiguration(), datetime.datetime.now())
