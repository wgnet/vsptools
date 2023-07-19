import asyncio
import logging
from asyncio import Task
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, Request
from prometheus_client import start_http_server
from watchdog.observers.api import BaseObserver

from .configs import Configs, WorkMode
from .database.broker import MongoDatabase
from .exporter.constants import DEFAULT_PORT
from .exporter.manager import enqueue_unprocessed_traces
from .models.worker import WorkerInfo, WorkerStatus
from .routes import common, manager, worker
from .routes import metrics_receiver
from .transactions.transactions_work_loop import transactions_work_loop
from .utils.monitoring import set_ready_traces_count, set_poisoned_traces_count, set_traces_queue_count

log = logging.getLogger(__name__)


def start_app(logging_config: dict):
    uvicorn.run(
        "exportana.app:manager_factory" if Configs.work_mode == WorkMode.Manager else "exportana.app:worker_factory",
        factory=True,
        host="0.0.0.0",
        port=Configs.port or DEFAULT_PORT,
        access_log=True,
        log_config=logging_config)


def manager_factory():
    app = FastAPI(docs_url="/docs")

    app.include_router(common.router)
    app.include_router(manager.router)

    @dataclass
    class ManagerData:
        database: MongoDatabase = None

    data = ManagerData(database=MongoDatabase())

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        request.state.db = data.database
        response = await call_next(request)
        return response

    @app.on_event("startup")
    async def startup():
        data.database.init()

        await init_prometheus_target_service()

        if Configs.fix:
            await enqueue_unprocessed_traces(data.database)

    @app.on_event("shutdown")
    async def shutdown():
        log.info(f"Going offline...")

        data.database.close()

    async def init_prometheus_target_service():
        # start metrics aggregator server for prometheus
        start_http_server(addr="0.0.0.0", port=Configs.exportana_metrics_port)

        db: MongoDatabase = data.database
        async with await db.start_session() as session, session.start_transaction():
            traces_count = await db.get_queued_trace_count(session)
            set_traces_queue_count(traces_count)

            traces_count = await db.get_ready_trace_count(session)
            set_ready_traces_count(traces_count)

            traces_count = await db.get_poisoned_trace_count(session)
            set_poisoned_traces_count(traces_count)

    return app


def worker_factory():
    if not Configs.worker_name:
        log.error(f"You must specify worker name! {Configs.worker_name}")
        exit(1)

    app = FastAPI(docs_url="/docs")

    app.include_router(common.router)
    app.include_router(worker.router)
    app.include_router(metrics_receiver.router)

    worker_name = f"{Configs.worker_name}:{Configs.port or DEFAULT_PORT}"

    class Data:
        task: Task = None
        worker: WorkerInfo = None

    data = Data()

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        request.state.data = data
        response = await call_next(request)
        return response

    @app.on_event("startup")
    async def startup():
        data.worker = WorkerInfo(url=worker_name, status=WorkerStatus.idle)
        data.task = asyncio.create_task(transactions_work_loop(data.worker))

    @app.on_event("shutdown")
    async def shutdown():
        SLEEP_TIME_SEC = 5
        log.info(f"Going offline...")
        data.task.cancel()
        while not data.task.done():
            log.info(f"Closing of the app in progress...")
            await asyncio.sleep(SLEEP_TIME_SEC)

    return app
