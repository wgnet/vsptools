import asyncio
import logging
import os
import subprocess
from asyncio import CancelledError
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import url2pathname

import paramiko
from configargparse import Namespace

from .base_transaction import BaseExportanaTransaction
from .exceptions.environment_exception import EnvironmentException
from .exceptions.trace_exception import TraceException
from ..exporter.constants import INSIGHTS_BINARY, UTRACE_EXT
from ..models.base import VerboseResult
from ..models.trace_meta import TraceMeta
from ..models.trace_with_context import TraceInfoWithContext
from ..models.worker import WorkerStatus, WorkerInfo
from ..routes import metrics_receiver

log = logging.getLogger(__name__)


class TraceProcessingTransaction(BaseExportanaTransaction):
    def __init__(self, args: Namespace, trace_info: TraceInfoWithContext, trace_meta: TraceMeta,
                 verbose_result: VerboseResult, worker: WorkerInfo):
        super().__init__(args, trace_info, trace_meta, verbose_result, worker)

    async def execute(self):
        self._worker.status = WorkerStatus.working

        self._trace_meta.started_timestamp = datetime.now().timestamp()
        log.info("Receiving metrics from Unreal Insights")
        self._prepare_trace_processing()
        try:
            insights_url_parsed = urlparse(self._args.insights)
        except Exception as e:
            error_msg = f"Bad insights url: {self._args.insights}. {type(e).__name__}: {e}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise EnvironmentException(error_msg)

        metrics_receiver.flush_metrics()

        await self._start_trace_processing(insights_url_parsed)

    async def commit(self):
        return

    async def rollback(self):
        return

    def _prepare_trace_processing(self):
        full_trace_path = os.path.join(self._args.trace_sessions_dir, f"{self._trace_info.trace_name}{UTRACE_EXT}")
        if not os.path.exists(full_trace_path):
            error_msg = f"Export failed, trace not found: '{self._trace_info.trace_name}'! Full path: '{full_trace_path}'"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise EnvironmentException(error_msg)

    async def _start_trace_processing(self, insights_url_parsed):
        DELAY_SEC = 1
        run_args = f"-OpenTraceId={self._hash_djb2(self._trace_info.trace_name)}," \
                   "-events," \
                   "-VSPPerfCollector," \
                   "-VSPRemoteReportPosting," \
                   f"-AutoQuit," \
                   f"-TraceSessionsDir={self._args.trace_sessions_dir}".split(",")

        if not self._args.gui:
            log.info(f"GUI disabled")
            run_args.append("-nullrhi")

        if insights_url_parsed.scheme == "file":
            # support windows UNC
            if insights_url_parsed.netloc:
                insights_path = r"\\" + url2pathname(insights_url_parsed.netloc + insights_url_parsed.path)
            else:
                insights_path = url2pathname(insights_url_parsed.path)

            run_args.insert(0, insights_path)
            log.info(f"Run: {' '.join(run_args)}")

            process = subprocess.Popen(run_args)
            try:
                while process.poll() is None:
                    await asyncio.sleep(DELAY_SEC)
            except CancelledError as e:
                process.kill()
                raise e

            if process.returncode != 0:
                error_msg = f"Trace processing error. Process return code is {process.returncode}."
                self.verbose_result.result = False
                self.verbose_result.errors.append(error_msg)
                raise TraceException(error_msg)

        elif insights_url_parsed.scheme == "ssh":
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                insights_url_parsed.hostname,
                username=insights_url_parsed.username,
                password=insights_url_parsed.password
            )
            run_str = " ".join(*([INSIGHTS_BINARY] + run_args))

            log.info(f"Run: {run_str}")

            _, stdout, stderr = client.exec_command(run_str)
            for line in stdout:
                line.strip("\n")
                log.debug(line)

            client.close()
        else:
            error_msg = f"Unknown scheme: {insights_url_parsed.scheme}"
            self.verbose_result.result = False
            self.verbose_result.errors.append(error_msg)
            raise Exception(error_msg)

    @staticmethod
    def _hash_djb2(name: str) -> int:
        """Returns hash of the trace name that matches with the unreal one"""
        h = 5381
        for x in name:
            h = ((h << 5) + h) + ord(x)
        return h & 0xFFFFFFFF
