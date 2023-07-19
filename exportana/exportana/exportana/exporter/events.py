from enum import Enum
from typing import List, Optional, Tuple, Set

from .constants import PATH_DELIMITER
from ..utils.compatibility import removesuffix, removeprefix


class NamingType(str, Enum):
    simple = ""
    append = "+"
    wildcard = "*"

    def __repr__(self):
        return self.name

    @staticmethod
    def determine_type(name):
        if NamingType.append in name:
            return NamingType.append
        elif NamingType.wildcard in name:
            return NamingType.wildcard
        return NamingType.simple


class Event:
    thread: Tuple[str, str] = None
    thread_type: NamingType = None

    key: Tuple[str, str] = None
    key_type: NamingType = None

    _alias: str = None

    def __init__(self, thread: str, key: str, alias: Optional[str] = None):
        self.thread_type = NamingType.determine_type(thread)
        if self.thread_type is NamingType.wildcard:
            raise KeyError(f"Wildcard is not supported in thread name")
        if self.thread_type is NamingType.append:
            parts = thread.split(NamingType.append, 1)
            self.thread = (parts[0], parts[1])
        else:
            self.thread = (thread, "")

        self.key_type = NamingType.determine_type(key)
        if self.key_type is NamingType.simple:
            self.key = (key, "")
        else:
            parts = key.split(self.key_type, 1)
            self.key = (parts[0], parts[1])

        alias = alias or key
        if self.key_type is NamingType.wildcard:
            self._alias = alias if NamingType.wildcard in alias else f"{alias} - *"
        else:
            self._alias = alias

    def __repr__(self):
        return f"{self.thread=} {self.thread_type=} {self.key=} {self.key_type=} {self._alias=}"

    def get_alias(self, thread: str, key: str) -> str:
        if self.thread_type == NamingType.append:
            if not thread.startswith(self.thread[0]) or not thread.endswith(self.thread[1]):
                raise KeyError(f"Event thread and external_thread doesn't match! {self.thread=} != {thread=}")

        if self.key_type is NamingType.append:
            return f"{self._alias}"
        elif self.key_type is NamingType.wildcard:
            wildcard_key = removesuffix(removeprefix(key, self.key[0]), self.key[1])
            return self._alias.replace(NamingType.wildcard, wildcard_key, 1)
        else:
            return f"{self._alias}"

    def is_compatible(self, thread: str, key: str) -> bool:
        if self.thread_type == NamingType.append:
            if not thread.startswith(self.thread[0]) or not thread.endswith(self.thread[1]):
                return False
        else:
            if self.thread[0] != thread:
                return False

        if self.key_type is NamingType.simple:
            return self.key[0] == key
        else:
            return key.startswith(self.key[0]) and key.endswith(self.key[1])


class Events:
    """
    This is an alias to `Dict[str, Dict[str, str]]` but with handy `add_event` and `fill` functions
    """

    _events: Set[Event] = set()

    def __init__(self, events: List[str]) -> None:
        self.fill(events)

    def __repr__(self):
        return f"{len(self._events)} Events"

    def add_event(self, event_str: str):
        name, *alias = event_str.split(PATH_DELIMITER, 1)
        alias = alias[0] if alias else name
        if ":" not in name:
            raise ValueError(
                f"Event name must contain event thread name, but current name is '{name}' E.g. 'ThreadName:EventName'"
            )
        thread, name = name.split(":", 1)

        self._events.add(Event(thread=thread, key=name, alias=alias))

    def fill(self, event_strings: List[str]):
        for event in event_strings:
            self.add_event(event)

    def find_event(self, thread: str, key: str) -> Optional[Event]:
        for event in self._events:
            if event.is_compatible(thread, key):
                return event
        return None

    def find_all_events(self, thread: str, key: str) -> List[Event]:
        result: List[Event] = list()
        for event in self._events:
            if event.is_compatible(thread, key):
                result.append(event)
        return result
