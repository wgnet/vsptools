import logging
import logging.config
import os

from .app import start_app
from .configs import Configs, create_logging_configs, WorkMode
from .utils.cleanup import CleanupTracesInfo, schedule_cleanup_traces


def main():
    logging_config = create_logging_configs()
    logging.config.dictConfig(logging_config)

    trace_sessions_dir = Configs.trace_sessions_dir
    if not trace_sessions_dir or not os.path.isdir(trace_sessions_dir) or not os.path.exists(trace_sessions_dir):
        raise Exception(f"{Configs.trace_sessions_dir} doesn't exist")
    # region Cleanup traces
    if Configs.work_mode == WorkMode.Manager:
        schedule_cleanup_traces(
            CleanupTracesInfo(
                force_cleanup=Configs.cleanup_force,
                cleanup_unprocessed=Configs.cleanup_unprocessed,
                trace_sessions_dir=Configs.trace_sessions_dir,
                cleanup_ignore=Configs.cleanup_ignore,
                cleanup_master_days=float(Configs.cleanup_master_days),
                cleanup_release_days=float(Configs.cleanup_release_days),
                cleanup_branches_days=float(Configs.cleanup_branches_days),
                cleanup_interval_hours=float(Configs.cleanup_interval_hours)
            )
        )
    # endregion

    # region Start service
    if Configs.work_mode is not None:
        start_app(logging_config=logging_config)
        exit(0)
    # endregion
    exit(-1)
