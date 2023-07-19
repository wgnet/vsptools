import asyncio
import logging
from asyncio import Task

from fastapi import APIRouter, Request
from httpx import Response
from starlette import status

from ..models.worker import WorkerInfo
from ..transactions.transactions_work_loop import transactions_work_loop

__ALL__ = ["router"]

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/worker",
    tags=["worker"],
    responses={404: {"description": "Page not found"}})


@router.get("/status", response_model=WorkerInfo)
async def get_status(request: Request):
    return request.state.data.worker


@router.get("/reset")
async def reset(request: Request):
    data = request.state.data
    task: Task = data.task
    if task:
        task.cancel()
        await task
        request.state.data.task = asyncio.create_task(transactions_work_loop(data.worker))

    return Response(status_code=status.HTTP_202_ACCEPTED)
