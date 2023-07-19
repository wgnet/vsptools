from typing import List

from pydantic import BaseModel

from ..configs import Configs


class WorkerConfiguration(BaseModel, allow_population_by_field_name=True, arbitrary_types_allowed=True):
    elastic: List[str] = Configs.elastic
    perfana: str = Configs.perfana
