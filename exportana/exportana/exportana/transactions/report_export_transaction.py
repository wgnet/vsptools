import asyncio
import logging

from configargparse import Namespace
from httpx import Response, NetworkError, ReadTimeout, RemoteProtocolError, RequestError
from starlette import status

from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.traces import ProcessedTraceReport
from ..models.worker import WorkerInfo, Worker
from ..transactions.exceptions.external_service_exception import ExternalServiceException
from ..transactions.request_to_manager_transaction import RequestToManagerTransaction
from ..utils.utils import make_url

log = logging.getLogger(__name__)


class ReportExportTransaction(RequestToManagerTransaction):
    def __init__(self, args: Namespace, trace_info: TraceInfoWithContext, trace_meta: TraceMeta,
                 verbose_result: VerboseResult,
                 worker: WorkerInfo):
        super().__init__(args, trace_info, trace_meta, verbose_result, worker)

    async def execute(self):
        await super(ReportExportTransaction, self).execute()
        await self._send_export_result()

    async def commit(self):
        await super(ReportExportTransaction, self).commit()

    async def rollback(self):
        await super(ReportExportTransaction, self).rollback()

    async def _send_export_result(self):
        DELAY_SEC = 30
        report = ProcessedTraceReport(
            trace_name=self._trace_info.trace_name,
            worker=Worker(url=self._worker.url),
            result=self.verbose_result,
            trace_meta=self._trace_meta)

        while not self._client.is_closed:
            try:
                response: Response = await self._client.put(make_url("trace", "ready", "put"), json=report.dict())
                if not response.is_success:
                    if response.status_code == status.HTTP_401_UNAUTHORIZED:
                        error_msg = "worker unauthorized!"
                        self.verbose_result.result = False
                        self.verbose_result.errors.append(error_msg)
                        raise ExternalServiceException(error_msg)
                    else:
                        await asyncio.sleep(DELAY_SEC)
                else:
                    return
            except (NetworkError, ReadTimeout, RemoteProtocolError, RequestError) as e:
                log.warning(f"ReportExportTransaction: _send_export_result: {e}")
                await asyncio.sleep(DELAY_SEC)
