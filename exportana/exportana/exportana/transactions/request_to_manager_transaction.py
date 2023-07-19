from abc import ABC

import httpx
from configargparse import Namespace

from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.worker import WorkerInfo
from ..transactions.base_transaction import BaseExportanaTransaction


class RequestToManagerTransaction(BaseExportanaTransaction, ABC):
    def __init__(self, args: Namespace, trace_info: TraceInfoWithContext, trace_meta: TraceMeta,
                 verbose_result: VerboseResult,
                 worker: WorkerInfo):
        super().__init__(args, trace_info, trace_meta, verbose_result, worker)
        self._client = httpx.AsyncClient()

    async def commit(self):
        await self._client.aclose()

    async def rollback(self):
        await self._client.aclose()
