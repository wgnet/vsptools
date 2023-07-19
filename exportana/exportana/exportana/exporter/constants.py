DEFAULT_ES_DSN = ["http://127.0.0.1:9200"]
DEFAULT_PERFANA_DSN = "http://127.0.0.1:5050"
DEFAULT_INSIGHTS_URL = "UnrealInsights-Win64-Shipping.exe"
INSIGHTS_BINARY = "UnrealInsights-Win64-Shipping.exe"
DEFAULT_SMTP = "smtp.local.net"
DEFAULT_PORT = 30000
DEFAULT_MANAGER_URL = f"http://localhost:{DEFAULT_PORT}"
DEFAULT_ALERT_FROM = "exportana@localhost"
DEFAULT_ALERT_TO = ""
DEFAULT_ALERT_DISK_SPACE = "5120MB"  # MB
IS_SERVER_KEY = "is_server"
METADATA_PREFIX = "METADATA"
METADATA_DELIMITER = ":"
UTRACE_EXT = ".utrace"
UTRACE_LIVE_EXT = ".live"
LOCALHOST = "localhost"
URL = "url"
INF = "inf"
PATH_DELIMITER = "/"

RECONNECT_TIMEOUT_SEC = 10

DEFAULT_ELASTICSEARCH_INDEX_PREFIX = "prf"

# region keys
NAME_KEY = "Name"
TIMESTAMP_KEY = "Timestamp"
# endregion

# region bookmark data keys & values
FRAME_START_KEY = "FrameStart"
FRAME_END_KEY = "FrameEnd"

DOC_TYPE_KEY = "doc_type"
RAW_DATA_KEY = "perfana_metrics"

DOC_TYPE_BUDGET = "budget"
DOC_TYPE_METRIC = "metric"
SETTINGS_KEY = "settings"

# region index settings
KEY_SETTINGS = "settings"
KEY_INDEX = "index"
KEY_MAPPING = "mapping"
KEY_TOTAL_FIELDS = "total_fields"
KEY_LIMIT = "limit"

DEF_INDEX_FIELDS_LIMIT = 2000
# region keys trace meta
KEY_TRACE_ID = "TraceId"
KEY_TRACE_NAME = "TraceName"
KEY_TRACE_SIZE = "TraceSize"
KEY_TIME_STAMP = "TimeStamp"
# endregion
