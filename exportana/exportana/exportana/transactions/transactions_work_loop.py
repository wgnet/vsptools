import asyncio
import logging
from asyncio import CancelledError

import httpx
from httpx import Response

from ..configs import Configs
from ..exporter import worker
from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.traces import TraceInfo, ProcessedTraceReport
from ..models.worker import WorkerInfo, WorkerStatus, Worker
from ..transactions.exceptions.environment_exception import EnvironmentException
from ..transactions.exceptions.external_service_exception import ExternalServiceException
from ..transactions.exceptions.trace_exception import TraceException
from ..transactions.trace_transaction_composition import TraceTransactionComposition
from ..utils.utils import make_url

log = logging.getLogger(__name__)


async def send_transaction_report(url: str,
                                  worker_info: WorkerInfo,
                                  trace_info: TraceInfo,
                                  trace_meta: TraceMeta,
                                  verbose_result: VerboseResult):
    DELAY_SEC = 30
    report = ProcessedTraceReport(trace_name=trace_info.trace_name,
                                  worker=Worker(url=worker_info.url),
                                  result=verbose_result,
                                  trace_meta=trace_meta)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response: Response = await client.put(url, json=report.dict())
                if response.is_success:
                    return
                else:
                    await asyncio.sleep(DELAY_SEC)
            except Exception as e:
                log.info(f"manage_task: Can't connect to the exportana manager: {e}")
                await asyncio.sleep(DELAY_SEC)


async def mark_task_as_poisoned(worker_info: WorkerInfo,
                                trace_info: TraceInfo,
                                trace_meta: TraceMeta,
                                verbose_result: VerboseResult):
    url = make_url("trace", "queued", "mark_poisoned")
    await send_transaction_report(url, worker_info, trace_info, trace_meta, verbose_result)


async def release_task_from_worker(worker_info: WorkerInfo,
                                   trace_info: TraceInfo,
                                   trace_meta: TraceMeta,
                                   verbose_result: VerboseResult):
    url = make_url("trace", "queued", "release_from_worker")
    await send_transaction_report(url, worker_info, trace_info, trace_meta, verbose_result)


async def transactions_work_loop(worker_info: WorkerInfo):
    SLEEP_TIME_SEC = 30
    log.info(f"transactions_work_loop. Transaction work loop started!")
    while True:
        try:
            trace_proc_transaction = TraceTransactionComposition(Configs, worker_info)
        except Exception as e:
            log.error(f"transactions_work_loop: Error on create transaction: {type(e).__name__}: {e}")
            await asyncio.sleep(SLEEP_TIME_SEC)
            return

        try:
            await trace_proc_transaction.execute()
        except (EnvironmentException, TraceException) as e:
            log.error(f"transactions_work_loop. "
                      f"[{trace_proc_transaction.current_transaction_index}]: "
                      f"{type(e).__name__}: {e}")
            await trace_proc_transaction.rollback()
            await mark_task_as_poisoned(
                worker_info,
                trace_proc_transaction.trace_info,
                trace_proc_transaction.trace_meta,
                trace_proc_transaction.verbose_result
            )
            worker_info.status = WorkerStatus.idle
            continue
        except ExternalServiceException as e:
            log.error(f"transactions_work_loop. "
                      f"[{trace_proc_transaction.current_transaction_index}]: "
                      f"{type(e).__name__}: {e}")
            await trace_proc_transaction.rollback()
            await release_task_from_worker(
                worker_info,
                trace_proc_transaction.trace_info,
                trace_proc_transaction.trace_meta,
                trace_proc_transaction.verbose_result
            )
            worker_info.status = WorkerStatus.idle
            continue
        except CancelledError as e:
            log.error(f"transactions_work_loop. "
                      f"[{trace_proc_transaction.current_transaction_index}]: "
                      f"{type(e).__name__}: {e}")
            await trace_proc_transaction.rollback()
            if trace_proc_transaction.trace_info.trace_name:
                await release_task_from_worker(
                    worker_info,
                    trace_proc_transaction.trace_info,
                    trace_proc_transaction.trace_meta,
                    trace_proc_transaction.verbose_result
                )
            worker_info.status = WorkerStatus.idle
            await worker.go_offline(worker_info)
            break
        except Exception as e:
            log.error(f"transactions_work_loop. "
                      f"[{trace_proc_transaction.current_transaction_index}]: "
                      f"{type(e).__name__}: {e}")
            await trace_proc_transaction.rollback()
            await release_task_from_worker(
                worker_info,
                trace_proc_transaction.trace_info,
                trace_proc_transaction.trace_meta,
                trace_proc_transaction.verbose_result
            )
            worker_info.status = WorkerStatus.idle
            continue

        try:
            await trace_proc_transaction.commit()
        except Exception as e:
            log.error(f"transactions_work_loop: Error on commit transaction: {type(e).__name__}: {e}")
        finally:
            worker_info.status = WorkerStatus.idle
    log.info(f"transactions_work_loop. Transaction work loop ended!")
