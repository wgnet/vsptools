import logging
from abc import ABC, abstractmethod, ABCMeta

from configargparse import Namespace

from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.worker import WorkerInfo

log = logging.getLogger(__name__)


class BaseTransaction(metaclass=ABCMeta):
    @abstractmethod
    async def execute(self):
        pass

    @abstractmethod
    async def commit(self):
        pass

    @abstractmethod
    async def rollback(self):
        pass


class BaseExportanaTransaction(BaseTransaction, ABC):
    def __init__(
        self,
        args: Namespace,
        trace_info: TraceInfoWithContext,
        trace_meta: TraceMeta,
        verbose_result: VerboseResult,
        worker: WorkerInfo = None
    ):
        super().__init__()
        self._args = args
        self._trace_info = trace_info
        self._trace_meta = trace_meta
        self.verbose_result = verbose_result
        self._worker = worker
