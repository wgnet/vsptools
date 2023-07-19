import logging

from fastapi import APIRouter, status
from fastapi.responses import Response

__ALL__ = ["router"]

log = logging.getLogger(__name__)

router = APIRouter(
    tags=["common"],
    responses={404: {"description": "Page not found"}},
)


@router.get("/ping")
async def ping():
    return Response(status_code=status.HTTP_200_OK)
