import logging

import httpx
from httpx import Response, NetworkError

from ..models.worker import WorkerInfo
from ..utils.utils import make_url

log = logging.getLogger(__name__)


class WorkerUnauthorized(BaseException):
    pass


async def go_offline(worker: WorkerInfo):
    async with httpx.AsyncClient() as client:
        try:
            response: Response = await client.post(make_url("worker", "set", "offline"), json=worker.get_id())
        except NetworkError as e:
            log.error(f"go_offline: NetworkError: {type(e).__name__}! {e}")
            return None

        if not response.is_success:
            log.warning(f"[{go_offline.__name__}]: {response.content}")
        else:
            log.info(f"Worker set offline. {worker.json()}")
