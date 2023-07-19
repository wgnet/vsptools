import logging.config
from datetime import datetime
from typing import List

from configargparse import Namespace

from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.worker import WorkerInfo, WorkerStatus
from ..transactions.base_transaction import BaseTransaction
from ..transactions.get_work_transaction import GetWorkTransaction
from ..transactions.report_export_transaction import ReportExportTransaction
from ..transactions.trace_export_transaction import TraceExportTransaction
from ..transactions.trace_processing_transaction import TraceProcessingTransaction
from ..utils.utils import timing

log = logging.getLogger(__name__)


class TraceTransactionComposition(BaseTransaction):
    def __init__(self, args: Namespace, worker: WorkerInfo, process: bool = True):
        super().__init__()
        self._transaction_list: List[BaseTransaction] = list()
        self._current_transaction_index: int = 0

        self.trace_info = TraceInfoWithContext()
        self.trace_meta = TraceMeta()
        self.verbose_result = VerboseResult()
        self.worker = worker

        self._make_transactions(args, worker, process)

    @property
    def current_transaction_index(self):
        return self._current_transaction_index

    @timing("Execute trace processing transaction", log_level=logging.INFO)
    async def execute(self):
        self.worker.status = WorkerStatus.idle
        self.worker.trace_name = None

        for i in range(len(self._transaction_list)):
            self._current_transaction_index = i
            log.info(f"execute transaction: the {i} of {len(self._transaction_list) - 1}")
            await self._transaction_list[i].execute()

    async def commit(self):
        for t in self._transaction_list:
            await t.commit()

        if self.trace_info is not None:
            log.info(f"Processing transaction for trace {self.trace_info.trace_name} finished!")

        self.worker.status = WorkerStatus.idle
        self.worker.trace_name = None

    @timing("Rollback trace processing transaction", log_level=logging.INFO)
    async def rollback(self):
        if self._current_transaction_index >= 0:
            for i in range(self._current_transaction_index, -1, -1):
                try:
                    log.info(f"Rollback transaction: the {i}")
                    await self._transaction_list[i].rollback()
                except Exception as e:
                    error_msg = f"TraceTransactionComposition. Rollback: {type(e).__name__} {e} transaction index: {i}"
                    log.warning(error_msg)
        self.trace_meta.processed_timestamp = datetime.now().timestamp()

        self.worker.status = WorkerStatus.idle

    def _make_transactions(self, args: Namespace, worker: WorkerInfo, process: bool = True):
        self._transaction_list.append(
            GetWorkTransaction(args, self.trace_info, self.trace_meta, self.verbose_result, worker))
        if process:
            self._transaction_list.append(
                TraceProcessingTransaction(args, self.trace_info, self.trace_meta, self.verbose_result, worker))
        self._transaction_list.append(
            TraceExportTransaction(args, self.trace_info, self.trace_meta, self.verbose_result))
        self._transaction_list.append(
            ReportExportTransaction(args, self.trace_info, self.trace_meta, self.verbose_result, worker))
