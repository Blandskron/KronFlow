"""Dedicated CLI worker process for durable ActionOutbox dispatch and scheduled campaigns."""

import argparse
import logging
import signal
import threading

from app.core.config import get_settings
from app.core.database import SessionLocal, create_public_tables
from app.services.outbox_dispatcher import StdlibOutboxTransport, run_worker_cycle


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("operational-worker")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KronFlow Operational ActionOutbox worker")
    parser.add_argument("--once", action="store_true", help="Run a single polling cycle across active tenants and exit")
    args = parser.parse_args(argv)

    settings = get_settings()
    create_public_tables()
    transport = StdlibOutboxTransport(settings)

    stop_event = threading.Event()

    def _request_stop(signum, _frame):
        logger.info("Received signal %s; stopping operational-worker cleanly", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    logger.info("operational-worker started (once=%s, poll=%.2fs)", args.once, settings.worker_poll_interval_seconds)
    while not stop_event.is_set():
        summary = run_worker_cycle(SessionLocal, settings=settings, transport=transport)
        if summary["claimed"] or summary["promoted_campaigns"] or summary["tenants_failed"]:
            logger.info("worker_cycle %s", summary)
        if args.once:
            break
        stop_event.wait(max(0.1, settings.worker_poll_interval_seconds))

    logger.info("operational-worker exited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
