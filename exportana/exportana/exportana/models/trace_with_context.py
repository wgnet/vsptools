from typing import Optional

from exportana.models.traces import TraceInfo
from exportana.models.worker_configuration import WorkerConfiguration


class TraceInfoWithContext(TraceInfo):
    worker_configuration: Optional[WorkerConfiguration] = None


class TraceInProcessing(TraceInfoWithContext):
    worker_url: str = None
