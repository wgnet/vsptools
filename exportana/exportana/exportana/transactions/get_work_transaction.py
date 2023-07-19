import asyncio
import json
import logging
from json import JSONDecodeError

from configargparse import Namespace
from httpx import Response, NetworkError, ReadTimeout, RemoteProtocolError, RequestError
from starlette import status

from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.worker import WorkerInfo, WorkerStatus
from ..transactions.exceptions.environment_exception import EnvironmentException
from ..transactions.request_to_manager_transaction import RequestToManagerTransaction
from ..utils.utils import make_url

log = logging.getLogger(__name__)


class GetWorkTransaction(RequestToManagerTransaction):
    def __init__(
        self, args: Namespace,
        trace_info: TraceInfoWithContext,
        trace_meta: TraceMeta,
        verbose_result: VerboseResult,
        worker: WorkerInfo
    ):
        super().__init__(args, trace_info, trace_meta, verbose_result, worker)

    async def execute(self):
        await super(GetWorkTransaction, self).execute()
        await self._request_work()

    async def commit(self):
        await super(GetWorkTransaction, self).commit()

    async def rollback(self):
        await super(GetWorkTransaction, self).rollback()

    async def _request_work(self):
        DELAY_SEC = 30
        while not self._client.is_closed:
            try:
                response: Response = await self._client.request(
                    method="GET",
                    url=make_url("trace", "queued", "acquire"),
                    content=json.dumps(self._worker.get_id()))

                if response.is_success:
                    try:
                        trace_info_tmp = TraceInfoWithContext.parse_raw(response.content)

                        self._trace_info.trace_name = trace_info_tmp.trace_name
                        self._trace_info.creation_date = trace_info_tmp.creation_date
                        self._trace_info.worker_configuration = trace_info_tmp.worker_configuration

                        self._worker.status = WorkerStatus.working
                        self._worker.trace_name = trace_info_tmp.trace_name
                        return
                    except JSONDecodeError as e:
                        error_msg = f"[{self._request_work.__name__}]: error on parse response content: {e}"
                        self.verbose_result.result = False
                        self.verbose_result.errors.append(error_msg)
                        raise EnvironmentException(error_msg)
                else:
                    if response.status_code == status.HTTP_404_NOT_FOUND:
                        log.debug(f"GetWorkTransaction. Waiting for a task...")
                        await asyncio.sleep(DELAY_SEC)
                        continue
                    if response.status_code == status.HTTP_401_UNAUTHORIZED:
                        error_msg = f"[{self._request_work.__name__}]: HTTP_401_UNAUTHORIZED"
                        self.verbose_result.result = False
                        self.verbose_result.errors.append(error_msg)
                        raise EnvironmentException(error_msg)

            except (NetworkError, ReadTimeout, RemoteProtocolError, RequestError) as e:
                log.warning(f"GetWorkTransaction: _request_work: {e}")
                await asyncio.sleep(DELAY_SEC)
