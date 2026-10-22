import time
import threading
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from glinet_client import GliNetClient
from database import Database

logger = logging.getLogger("Collector")

class DataCollector:
    def __init__(self, client: GliNetClient, db: Database, poll_interval: int = 5, backfill_limit: int = 1000):
        self.client = client
        self.db = db
        self.poll_interval = poll_interval
        self.backfill_limit = backfill_limit
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        
        # State tracking
        self.last_poll_time: Optional[str] = None
        self.last_error: Optional[str] = None
        self.total_collected: int = 0
        self.is_router_online: bool = False

    def start(self):
        """Start the background collector thread."""
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Collector thread started.")

    def stop(self):
        """Stop the background collector thread."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Collector thread stopped.")

    def sync_now(self) -> Dict[str, Any]:
        """Trigger an immediate manual sync."""
        return self._poll_step()

    def _backfill(self):
        """Backfill existing querylog items from router buffer up to backfill_limit."""
        logger.info(f"Starting querylog backfill (target: {self.backfill_limit})...")
        total_backfilled = 0
        oldest_ts = None
        batch_size = 200

        while total_backfilled < self.backfill_limit and self.is_running:
            try:
                res = self.client.get_querylog(limit=batch_size, older_than=oldest_ts)
                if not res:
                    break

                items = res.get("data", [])
                if not items:
                    break

                inserted = self.db.insert_queries(items)
                total_backfilled += len(items)
                self.total_collected += inserted

                new_oldest = res.get("oldest")
                if not new_oldest or new_oldest == oldest_ts:
                    break
                oldest_ts = new_oldest

                if len(items) < batch_size:
                    break

            except Exception as e:
                logger.error(f"Error during backfill: {e}")
                break

        logger.info(f"Backfill complete: processed {total_backfilled} items.")

    def _poll_step(self) -> Dict[str, Any]:
        """Execute one polling iteration."""
        now_str = datetime.now().isoformat()
        self.last_poll_time = now_str
        new_items_count = 0

        try:
            # 1. Update client metadata
            clients = self.client.get_clients()
            if clients:
                self.db.update_clients_metadata(clients)

            # 2. Fetch latest queries
            log_res = self.client.get_querylog(limit=100)
            if log_res:
                items = log_res.get("data", [])
                new_items_count = self.db.insert_queries(items)
                self.total_collected += new_items_count
                self.is_router_online = True
                self.last_error = None
            else:
                self.is_router_online = False
                self.last_error = "Could not fetch querylog from router"

            return {
                "success": True,
                "timestamp": now_str,
                "new_queries": new_items_count,
                "total_collected": self.total_collected,
                "router_online": self.is_router_online
            }

        except Exception as e:
            self.last_error = str(e)
            self.is_router_online = False
            logger.error(f"Collector poll step failed: {e}")
            return {
                "success": False,
                "timestamp": now_str,
                "error": str(e),
                "router_online": False
            }

    def _run_loop(self):
        """Worker loop that executes backfill and periodic polling."""
        # Initial login & discovery
        if self.client.login():
            self.is_router_online = True
            # Backfill existing logs
            self._backfill()
        else:
            self.last_error = "Initial router login failed"

        while self.is_running:
            self._poll_step()
            time.sleep(self.poll_interval)

    def get_status(self) -> Dict[str, Any]:
        """Return collector health status."""
        return {
            "is_running": self.is_running,
            "router_online": self.is_router_online,
            "last_poll_time": self.last_poll_time,
            "total_collected": self.total_collected,
            "last_error": self.last_error,
            "poll_interval": self.poll_interval
        }
