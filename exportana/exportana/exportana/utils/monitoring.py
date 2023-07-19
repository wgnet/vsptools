import logging
from datetime import datetime, timedelta

from prometheus_client import (
    Gauge,
    Enum,
    Histogram
)

from exportana.models.traces import ProcessedTraceReport
from exportana.models.worker import WorkerStatus

# region metrics constants
TRACES_QUEUE_SIZE_KEY = "traces_queue_size"
TRACES_QUEUE_SIZE_DESC = "Size of traces queue"

READY_TRACES_COUNT_KEY = "ready_traces_count"
READY_TRACES_COUNT_DESC = "Ready traces count"

POISONED_TRACES_COUNT_KEY = "poisoned_traces_count"
POISONED_TRACES_COUNT_DESC = "Poisoned traces count"

TRACE_KEY = "trace"
TRACE_EXECUTE_RESULT_KEY = "result"
TRACE_REPORT_KEY = "trace_execution_report"
TRACE_REPORT_DESC = "Report of trace execution"

WORKER_KEY = "worker"
WORKER_STATUS_KEY = "workers_status"
WORKER_STATUS_DESC = "Worker status"
# endregion

# region metrics instruments
worker_status_enum: Enum = Enum(
    WORKER_STATUS_KEY,
    WORKER_STATUS_DESC,
    states=[WorkerStatus.idle, WorkerStatus.working],
    labelnames=[WORKER_KEY]
)

trace_execution_histogram = Histogram(
    TRACE_REPORT_KEY,
    TRACE_REPORT_DESC,
    labelnames=[TRACE_KEY, TRACE_EXECUTE_RESULT_KEY]
)

traces_queue_size_gauge: Gauge = Gauge(TRACES_QUEUE_SIZE_KEY, TRACES_QUEUE_SIZE_DESC)
ready_traces_gauge: Gauge = Gauge(READY_TRACES_COUNT_KEY, READY_TRACES_COUNT_DESC)
poisoned_traces_gauge: Gauge = Gauge(POISONED_TRACES_COUNT_KEY, POISONED_TRACES_COUNT_DESC)
# endregion

log = logging.getLogger(__name__)


# region traces queue size metrics
def set_traces_queue_count(value: int):
    try:
        traces_queue_size_gauge.set(value)
    except Exception as e:
        log.warning(f"Prometheus monitoring. set_traces_queue_size. Something wrong {e}")


# endregion


# region worker status metric
def set_worker_status(worker_url: str, status: WorkerStatus):
    try:
        worker_status_enum.labels(worker_url).state(status)
    except Exception as e:
        log.warning(f"Prometheus monitoring. set_worker_status. Something wrong {e}")


# endregion


# region ready traces metrics
def set_ready_traces_count(value: int):
    try:
        ready_traces_gauge.set(value)
    except Exception as e:
        log.warning(f"Prometheus monitoring. set_ready_traces_count. Something wrong {e}")


# endregion


# region poisoned traces metrics
def set_poisoned_traces_count(value: int):
    try:
        poisoned_traces_gauge.set(value)
    except Exception as e:
        log.warning(f"Prometheus monitoring. set_poisoned_traces_count. Something wrong {e}")


# endregion


# region trace report result metric
def set_trace_report_result(trace_report: ProcessedTraceReport):
    try:
        if trace_report.trace_meta:
            tm = trace_report.trace_meta
            processed_timestamp = tm.processed_timestamp
            started_timestamp = tm.started_timestamp
            dt_delta: timedelta = datetime.fromtimestamp(processed_timestamp) - datetime.fromtimestamp(started_timestamp)
            processing_time_sec = dt_delta.total_seconds()
            trace_name = trace_report.trace_name
            processing_result = trace_report.result.result
            trace_execution_histogram.labels(trace_name, str(processing_result)).observe(processing_time_sec)
    except Exception as e:
        log.warning(f"Prometheus monitoring. set_trace_report_result. Something wrong {e}")
# endregion
