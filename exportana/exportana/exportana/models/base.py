import abc
import functools
from enum import Enum
from typing import TypeVar, Union, Any, List

from pydantic import BaseModel


class VerboseResult(BaseModel):
    result: bool = None
    errors: List[str] = None

    def __init__(self, result: bool = None, *args, **data: Any) -> None:
        super().__init__(**data)
        self.result = result
        self.errors = data["errors"] if "errors" in data else list(filter(None.__ne__, args))

    def __bool__(self):
        return self.result is True


class DBModel(BaseModel, metaclass=abc.ABCMeta, allow_population_by_field_name=True):
    @abc.abstractmethod
    def get_id(self) -> dict:
        pass

    @abc.abstractmethod
    def get_data(self) -> dict:
        pass


AnyDBModel = TypeVar("AnyDBModel", bound="DBModel")


def get_id(obj: Union[AnyDBModel, str]) -> dict:
    if isinstance(obj, str):
        return {"_id": obj}
    elif isinstance(obj, DBModel):
        return obj.get_id()
    else:
        return {}


@functools.total_ordering
class OrderedEnum(Enum):
    @classmethod
    @functools.lru_cache(None)
    def _member_list(cls):
        return list(cls)

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            member_list = self.__class__._member_list()
            return member_list.index(self) < member_list.index(other)
        return NotImplemented
