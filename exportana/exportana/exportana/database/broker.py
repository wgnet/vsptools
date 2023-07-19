import logging
from datetime import datetime
from enum import Enum
from typing import Optional, List, Type, Union

from motor.core import AgnosticDatabase, AgnosticCollection, AgnosticClient
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.client_session import ClientSession

from ..configs import Configs
from ..models.base import DBModel, AnyDBModel, get_id
from ..models.trace_with_context import TraceInfoWithContext, TraceInProcessing
from ..models.traces import ProcessedTraceInfo, TraceInfo

__ALL__ = ["MongoDatabase"]

log = logging.getLogger(__name__)

DATABASE = "exportana"


class DBName(str, Enum):
    queued_traces = "queued_traces"
    traces_in_processing = "traces_in_processing"
    ready_traces = "ready_traces"
    poisoned_traces = "poisoned_traces"


class MongoDatabase:
    _client: AgnosticClient = None
    _database: AgnosticDatabase = None
    # region tables
    _queued_traces: AgnosticCollection = None
    _traces_in_processing: AgnosticCollection = None
    _ready_traces: AgnosticCollection = None
    _poisoned_traces: AgnosticCollection = None

    # endregion

    # region Base methods

    def init(self):
        self._client: AgnosticClient = AsyncIOMotorClient(host=Configs.mongo_url)
        self._database: AgnosticDatabase = self._client[DATABASE]

        self._queued_traces: AgnosticCollection = self._database[DBName.queued_traces]
        self._traces_in_processing: AgnosticCollection = self._database[DBName.traces_in_processing]
        self._ready_traces: AgnosticCollection = self._database[DBName.ready_traces]
        self._poisoned_traces: AgnosticCollection = self._database[DBName.poisoned_traces]

    def close(self):
        self._client.close()

    async def start_session(self) -> ClientSession:
        return await self._client.start_session()

    # endregion

    # region Find any doc
    @staticmethod
    async def _find_doc(collection: AgnosticCollection,
                        doc_filter: Union[str, dict],
                        parse_to_class: Type[DBModel] = None,
                        session: ClientSession = None) -> Optional[AnyDBModel]:
        result: Optional[DBModel] = await collection.find_one(doc_filter, session=session)
        if result is None:
            return None
        return parse_to_class.parse_obj(result) if parse_to_class else result

    @staticmethod
    async def _find_doc_sorted_by(collection: AgnosticCollection,
                                  doc_filter: Union[str, dict],
                                  field_name: str,
                                  parse_to_class: Type[DBModel] = None,
                                  session: ClientSession = None) -> Optional[AnyDBModel]:
        resultLst = None
        try:
            cursor = collection.find(doc_filter, session=session).sort(field_name, 1).limit(1)
            resultLst = await cursor.to_list(None)
        except Exception as e:
            log.error(f"_find_doc_sorted_by: {type(e).__name__}: {e}")

        if not resultLst:
            return None
        result = resultLst[0]
        return parse_to_class.parse_obj(result) if parse_to_class else result

    async def find_queued_trace(self, trace: Union[str, DBModel], session: ClientSession = None) -> Optional[TraceInfoWithContext]:
        return await self._find_doc(self._queued_traces, get_id(trace), TraceInfoWithContext, session)

    async def find_processing_trace(self, worker_url: Union[str, DBModel], session: ClientSession = None) -> Optional[TraceInProcessing]:
        traces_in_processing: List[TraceInProcessing] = await self._get_all_docs(self._traces_in_processing, TraceInProcessing, session)
        for trace in traces_in_processing:
            if trace.worker_url == worker_url:
                return trace
        return None

    async def find_processing_trace_by_name(self, trace_name: Union[str, DBModel], session: ClientSession = None) -> Optional[TraceInProcessing]:
        traces_in_processing: List[TraceInProcessing] = await self._get_all_docs(self._traces_in_processing, TraceInProcessing, session)
        for trace in traces_in_processing:
            if trace.trace_name == trace_name:
                return trace
        return None

    async def find_ready_trace(self, trace: Union[str, DBModel], session: ClientSession = None) -> Optional[ProcessedTraceInfo]:
        return await self._find_doc(self._ready_traces, get_id(trace), ProcessedTraceInfo, session)

    async def find_poisoned_trace(self, trace: Union[str, DBModel],
                                  session: ClientSession = None) -> Optional[ProcessedTraceInfo]:
        return await self._find_doc(self._poisoned_traces, get_id(trace), ProcessedTraceInfo, session)

    async def extract_trace_from_queue(self, session: ClientSession = None) -> Optional[TraceInfoWithContext]:
        trace = await self._find_doc_sorted_by(self._queued_traces, {}, "creation_date", TraceInfoWithContext, session)
        if trace:
            await self.remove_queued_trace(trace, session)
        return trace

    # endregion

    # region Get all docs
    @staticmethod
    async def _get_all_docs(collection: AgnosticCollection,
                            parse_to_class: Type[DBModel] = None,
                            session: ClientSession = None) -> List[AnyDBModel]:
        result: List[AnyDBModel] = []
        async for doc in collection.find(session=session):
            try:
                result.append(parse_to_class.parse_obj(doc) if parse_to_class else doc)
            except BaseException as e:
                log.warning(f"_get_all_docs: {type(e).__name__} {e}")
        return result

    async def get_queued_traces(self, session: ClientSession = None) -> List[TraceInfoWithContext]:
        return await self._get_all_docs(self._queued_traces, TraceInfoWithContext, session)

    async def get_ready_traces(self, session: ClientSession = None) -> List[ProcessedTraceInfo]:
        return await self._get_all_docs(self._ready_traces, ProcessedTraceInfo, session)

    async def get_poisoned_traces(self, session: ClientSession = None) -> List[ProcessedTraceInfo]:
        return await self._get_all_docs(self._poisoned_traces, ProcessedTraceInfo, session)

    # endregion

    # region Set doc, added if missing
    @staticmethod
    async def _set_doc(collection: AgnosticCollection, data: DBModel, session: ClientSession = None):
        await collection.replace_one(filter=data.get_id(), replacement=data.get_data(), upsert=True, session=session)

    async def set_queued_trace(self, trace: TraceInfoWithContext, session: ClientSession = None):
        await self._set_doc(self._queued_traces, trace, session)

    async def set_processing_trace(self, trace: TraceInProcessing, session: ClientSession = None):
        await self._set_doc(self._traces_in_processing, trace, session)

    async def set_ready_trace(self, trace: ProcessedTraceInfo, session: ClientSession = None):
        await self._set_doc(self._ready_traces, trace, session)

    async def set_poisoned_trace(self, trace: ProcessedTraceInfo, session: ClientSession = None):
        await self._set_doc(self._poisoned_traces, trace, session)

    # endregion

    # region Remove doc
    @staticmethod
    async def _remove_doc(collection: AgnosticCollection, data: DBModel, session: ClientSession = None):
        await collection.delete_one(filter=data.get_id(), session=session)

    async def remove_queued_trace(self, trace: TraceInfoWithContext, session: ClientSession = None):
        await self._remove_doc(self._queued_traces, trace, session)

    async def remove_processing_trace(self, worker_url: str, session: ClientSession = None):
        traces_in_processing: List[TraceInProcessing] = await self._get_all_docs(self._traces_in_processing, TraceInProcessing, session)
        for trace in traces_in_processing:
            if trace.worker_url == worker_url:
                await self._remove_doc(self._traces_in_processing, trace, session)
                break

    @staticmethod
    async def _get_docs_count(collection: AgnosticCollection, session: ClientSession = None) -> int:
        return await collection.count_documents({}, session=session)

    async def get_queued_trace_count(self, session: ClientSession = None) -> int:
        return await self._get_docs_count(self._queued_traces, session)

    async def get_poisoned_trace_count(self, session: ClientSession = None) -> int:
        return await self._get_docs_count(self._poisoned_traces, session)

    async def get_ready_trace_count(self, session: ClientSession = None) -> int:
        return await self._get_docs_count(self._ready_traces, session)

    async def remove_ready_trace(self, trace: TraceInfo, session: ClientSession = None):
        await self._remove_doc(self._ready_traces, trace, session)
    # endregion
