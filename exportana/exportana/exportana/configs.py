import logging.config
import multiprocessing
import sys
from enum import Enum
from typing import Optional

from configargparse import ArgParser, YAMLConfigFileParser

from .exporter.constants import (
    DEFAULT_ALERT_DISK_SPACE,
    DEFAULT_ALERT_FROM,
    DEFAULT_ES_DSN,
    DEFAULT_INSIGHTS_URL,
    DEFAULT_PERFANA_DSN,
    DEFAULT_SMTP,
    DEFAULT_MANAGER_URL,
    DEFAULT_ELASTICSEARCH_INDEX_PREFIX,
    INF,
    DEF_INDEX_FIELDS_LIMIT
)

__ALL__ = ["Configs"]

log = logging.getLogger(__name__)

LOG_FMT = "[%(asctime)s.%(msecs)-.3d][%(levelname)s][%(name)s]: %(message)s"
LOG_FMT_UVICORN_ACCESS = "[%(asctime)s.%(msecs)-.3d][%(levelname)s][%(name)s][%(client_addr)s][%(status_code)s]: %(request_line)s"

LOG_DATEFMT = "%m/%d/%Y-%H:%M:%S"
LOG_HANDLERS = [logging.FileHandler("exportana.log"), logging.StreamHandler(sys.stdout)]

FILENAME = "filename"
FORMATTER = "formatter"
FORMAT = "format"
DATE_TIME_FMT = "datefmt"
USE_COLORS = "use_colors"
DEFAULT = "default"
CLASS = "class"
LVL = "level"
HANDLERS = "handlers"
PREPOGATE = "propagate"
PARENTHESES = "()"

STDOUT_HANDLER = "stdout_handler"
FILE_HANDLER = "file_handler"
FILE_HANDLER_ACCESS = "file_handler_access"
LOGSTASH_HANDLER = "logstash_handler"

_log_levels = [f"{logging.DEBUG=}".split(".")[1].split("=")[0],
               f"{logging.INFO=}".split(".")[1].split("=")[0],
               f"{logging.WARNING=}".split(".")[1].split("=")[0],
               f"{logging.ERROR=}".split(".")[1].split("=")[0],
               f"{logging.CRITICAL=}".split(".")[1].split("=")[0], ]


def make_formatters() -> dict:
    formatters = {
        "": {
            PARENTHESES: "logging.Formatter",
            FORMAT: LOG_FMT,
            DATE_TIME_FMT: LOG_DATEFMT,
        },
        DEFAULT: {
            PARENTHESES: "uvicorn.logging.DefaultFormatter",
            FORMAT: LOG_FMT,
            DATE_TIME_FMT: LOG_DATEFMT,
            USE_COLORS: False,
        },
        "access": {
            PARENTHESES: "uvicorn.logging.AccessFormatter",
            FORMAT: LOG_FMT_UVICORN_ACCESS,
            DATE_TIME_FMT: LOG_DATEFMT,
            USE_COLORS: False,
        },
    }
    return formatters


def make_handlers(log_level: str, log_name: str) -> dict:
    default_file_log_handler = {
        CLASS: "logging.handlers.RotatingFileHandler",
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
        "level": logging.DEBUG,
    }

    handlers = {
        STDOUT_HANDLER: {
            FORMATTER: DEFAULT,
            CLASS: "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            LVL: log_level,
        },
        FILE_HANDLER: {
            FORMATTER: DEFAULT,
            FILENAME: f"{log_name}.log",
            **default_file_log_handler
        },
        FILE_HANDLER_ACCESS: {
            FORMATTER: "access",
            FILENAME: f"{log_name}_access.log",
            **default_file_log_handler
        },
        LOGSTASH_HANDLER: {
            CLASS: "logstash_async.handler.AsynchronousLogstashHandler",
            "host": Configs.logstash_host,
            "port": Configs.logstash_port,
            "database_path": None,
            LVL: log_level,
        }
    }
    return handlers


def make_loggers(log_level: str) -> dict:
    loggers = {
            "": {HANDLERS: [STDOUT_HANDLER, FILE_HANDLER, LOGSTASH_HANDLER], LVL: log_level},
            "uvicorn": {HANDLERS: [], LVL: log_level, PREPOGATE: True},
            "uvicorn.error": {HANDLERS: [], LVL: log_level, PREPOGATE: True},
            "uvicorn.access": {HANDLERS: [FILE_HANDLER_ACCESS], LVL: log_level, PREPOGATE: False},
        }
    return loggers


def create_logging_configs() -> dict:
    log_level = logging.getLevelName(Configs.log_level)
    log_name = f"exportana_{Configs.work_mode or 'common'}"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": make_formatters(),
        HANDLERS: make_handlers(log_level, log_name),
        "loggers": make_loggers(log_level),
    }


def int_or_none(value) -> Optional[int]:
    try:
        value = int(value)
    except ValueError:
        return None
    else:
        return value


class WorkMode(str, Enum):
    Manager = "manager"
    Worker = "worker"


def _create_parser():
    p = ArgParser(default_config_files=["exportana.conf"], config_file_parser_class=YAMLConfigFileParser)
    # region Base settings
    p.add_argument("--config", is_config_file=True, help="config file path")
    p.add_argument("--elastic", nargs="+", default=DEFAULT_ES_DSN, help="elasticsearch dsn", env_var="EXPORT_ELASTIC")
    p.add_argument(
        "--insights",
        default=DEFAULT_INSIGHTS_URL,
        help="path to unreal insights",
        env_var="EXPORT_INSIGHTS"
    )
    p.add_argument("--perfana", default=DEFAULT_PERFANA_DSN, help="perfana url", env_var="EXPORT_PERFANA")
    p.add_argument("--bitbucket", help="bitbucket url", env_var="EXPORT_BITBUCKET")
    p.add_argument("--elasticsearch-index-prefix", default=DEFAULT_ELASTICSEARCH_INDEX_PREFIX,
                   help="elasticsearch index prefix for the exportana")
    p.add_argument("-t", "--trace", help="name of the trace", env_var="EXPORT_TRACE")

    p.add_argument("--trace-sessions-dir", required=True, help="traces directory", env_var="EXPORT_TRACE_SESSIONS_DIR")

    p.add_argument("--title", help="Overrides title field in perfana", env_var="EXPORT_TITLE")
    p.add_argument("--build", help="Overrides build field in perfana", env_var="EXPORT_BUILD")
    p.add_argument("--workstation", help="Overrides workstation field in perfana", env_var="EXPORT_WORKSTATION")
    p.add_argument("--watch", help="watch directory", action="store_true", env_var="EXPORT_WATCH")
    p.add_argument("--gui", help="launch unreal insights with gui", action="store_true")
    p.add_argument("--list", help="list traces", action="store_true")
    p.add_argument("--process", help="re-process utrace with id", action="store_true")
    p.add_argument(
        "--events",
        required=True,
        help="Events to process. Available formats: 'ThreadName1:MetricName1/MetricAlias1', 'ThreadName2:MetricName2', 'ThreadName3:MetricName+/MetricAlias1'",
        action="append"
    )
    p.add_argument("--bookmark-metadata", help="additional bookmark METADATA to capture", action="append")
    p.add_argument("--normalize", help="normalize traces by bookmark events", action="append")
    p.add_argument("--trace-info", help="bookmark name with trace info")
    p.add_argument("--fix", help="re-process broken utraces", action="store_true")
    p.add_argument("--cleanup-indices", help="remove indices", action="store_true")
    p.add_argument("--smtp-server", default=DEFAULT_SMTP, help="smtp server to alert", env_var="EXPORT_SMTP")
    p.add_argument("--alert-from", default=DEFAULT_ALERT_FROM, help="alert from")
    p.add_argument("--alert-to", default=[], help="alert to", action="append")
    p.add_argument("--alert-login", default="", help="alert smtp login", env_var="EXPORT_ALERT_LOGIN")
    p.add_argument("--alert-pass", default="", help="alert smtp password", env_var="EXPORT_ALERT_PASS")
    p.add_argument("--alert-disk-space", default=DEFAULT_ALERT_DISK_SPACE, help="alert threshold (eg. 1MB, 5GB)")
    p.add_argument("--ignore", help="ignore some utraces", action="append")
    p.add_argument("--dry-run", help="test action", action="store_true")
    p.add_argument("--same-index", help="update same index for traces", action="store_false")
    p.add_argument("-d", "--dump-mapping", help="dump mapping before exporting", action="store_true")
    p.add_argument(
        "-l", "--log-level",
        default=_log_levels[1],
        choices=_log_levels,
        help="log level"
    )
    p.add_argument(
        "--log-level-ext",
        default=_log_levels[1],
        choices=_log_levels,
        help="log level for all"
    )

    p.add_argument("--logstash-host", help="logstash url")
    p.add_argument("--logstash-port", type=int, help="logstash port")

    p.add_argument("--elastic_mapping_limit", type=int, help="elastic mapping limit", default=DEF_INDEX_FIELDS_LIMIT)
    # endregion

    # region Cleanup settings
    p.add_argument("--cleanup-force", help="Force run cleanup", action="store_true")
    p.add_argument(
        "--cleanup-unprocessed",
        help="Determines if we need to clean up unprocessed traces",
        action="store_true"
    )
    p.add_argument(
        "--cleanup-interval-hours",
        help="Interval between each cleanup check",
        action="store",
        default=INF
    )
    p.add_argument(
        "--cleanup-master-days",
        help="Days until master branches will be deleted",
        action="store",
        default=INF
    )
    p.add_argument(
        "--cleanup-release-days",
        help="Days until release branches will be deleted",
        action="store",
        default=INF
    )
    p.add_argument(
        "--cleanup-branches-days",
        help="Days until feature/bugfix/hotfix branches will be deleted",
        action="store",
        default=INF
    )
    p.add_argument("--cleanup-ignore", help="Ignore traces during cleanup", action="append")
    # endregion

    # region Manager/Worker configs
    p.add_argument(
        "--work-mode",
        default=None,
        choices=list(map(lambda m: m.value, WorkMode)),
        help="Set exportana work mode",
        type=WorkMode,
        env_var="EXPORTANA_WORK_MODE"
    )
    p.add_argument(
        "--port",
        type=int_or_none,
        help="Set manager/worker port to bind REST api to",
        env_var="EXPORTANA_PORT"
    )
    p.add_argument(
        "--mongo-url",
        help="Set Manager's mongo url",
        default="mongodb://localhost:27017",
        env_var="EXPORTANA_MONGO_URL"
    )
    p.add_argument(
        "--manager-url",
        type=str,
        default=DEFAULT_MANAGER_URL,
        help="Set manager url",
        env_var="EXPORTANA_MANAGER_URL"
    )
    p.add_argument(
        "--worker-name",
        type=str,
        help="Set worker name (usually is a hostname)",
        env_var="EXPORTANA_WORKER_NAME"
    )
    p.add_argument(
        "--exportana-metrics-port",
        help="Metrics aggregator server port for prometheus",
        type=int,
        default=8000,
        env_var="EXPORTANA_METRICS_PORT"
    )
    p.add_argument(
        "--thread-pool-size",
        type=int,
        help="Set thread pool size for csv files processing",
        default=multiprocessing.cpu_count()
    )
    # endregion
    return p


_parser = _create_parser()

if not len(sys.argv) > 1:
    log.info(_parser.format_help())
    exit(1)

Configs, _ = _parser.parse_known_args()
