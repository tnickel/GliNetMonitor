import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("Database")

class Database:
    def __init__(self, db_path: str = "glinet_monitor.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            c = conn.cursor()

            # Clients table
            c.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    ip TEXT PRIMARY KEY,
                    name TEXT,
                    source TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    total_queries INTEGER DEFAULT 0,
                    unique_domains INTEGER DEFAULT 0
                )
            """)

            # Queries log table
            c.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    client_ip TEXT,
                    client_name TEXT,
                    domain TEXT,
                    query_type TEXT,
                    status TEXT,
                    reason TEXT,
                    elapsed_ms REAL,
                    cached INTEGER DEFAULT 0,
                    upstream TEXT,
                    UNIQUE(timestamp, client_ip, domain, query_type)
                )
            """)

            # Pre-aggregated client domain statistics
            c.execute("""
                CREATE TABLE IF NOT EXISTS client_domains (
                    client_ip TEXT,
                    domain TEXT,
                    count INTEGER DEFAULT 0,
                    blocked_count INTEGER DEFAULT 0,
                    first_accessed TEXT,
                    last_accessed TEXT,
                    PRIMARY KEY (client_ip, domain)
                )
            """)

            # Indexes for fast querying
            c.execute("CREATE INDEX IF NOT EXISTS idx_queries_client_ip ON queries(client_ip)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_queries_domain ON queries(domain)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_client_domains_count ON client_domains(client_ip, count DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_client_domains_last ON client_domains(client_ip, last_accessed DESC)")

            conn.commit()

    def update_clients_metadata(self, client_list: List[Dict[str, Any]]):
        """Update or insert client metadata from AdGuard/network discovery."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            for cl in client_list:
                ip = cl.get("ip")
                if not ip:
                    continue
                name = cl.get("name") or ip
                source = cl.get("source") or "discovery"

                c.execute("""
                    INSERT INTO clients (ip, name, source, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET
                        name = CASE WHEN excluded.name != excluded.ip AND excluded.name != '' THEN excluded.name ELSE clients.name END,
                        source = excluded.source,
                        last_seen = excluded.last_seen
                """, (ip, name, source, now, now))
            conn.commit()

    def insert_queries(self, queries: List[Dict[str, Any]]) -> int:
        """Batch insert query log entries and update client_domains aggregations."""
        if not queries:
            return 0

        inserted_count = 0
        with self._get_connection() as conn:
            c = conn.cursor()

            for q in queries:
                timestamp = q.get("time")
                client_ip = q.get("client")
                if not timestamp or not client_ip:
                    continue

                client_name = q.get("client_info", {}).get("name") or client_ip
                question = q.get("question", {})
                domain = question.get("name", "").lower().strip()
                query_type = question.get("type", "A")
                status = q.get("status", "NOERROR")
                reason = q.get("reason", "")
                is_blocked = 1 if "BlackList" in reason or "Block" in reason or status == "NXDOMAIN" else 0
                try:
                    elapsed_ms = float(q.get("elapsedMs", 0))
                except (ValueError, TypeError):
                    elapsed_ms = 0.0
                cached = 1 if q.get("cached", False) else 0
                upstream = q.get("upstream", "")

                try:
                    c.execute("""
                        INSERT INTO queries (timestamp, client_ip, client_name, domain, query_type, status, reason, elapsed_ms, cached, upstream)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (timestamp, client_ip, client_name, domain, query_type, status, reason, elapsed_ms, cached, upstream))
                    
                    if c.rowcount > 0:
                        inserted_count += 1

                        # Update client_domains aggregate
                        c.execute("""
                            INSERT INTO client_domains (client_ip, domain, count, blocked_count, first_accessed, last_accessed)
                            VALUES (?, ?, 1, ?, ?, ?)
                            ON CONFLICT(client_ip, domain) DO UPDATE SET
                                count = client_domains.count + 1,
                                blocked_count = client_domains.blocked_count + excluded.blocked_count,
                                last_accessed = MAX(client_domains.last_accessed, excluded.last_accessed)
                        """, (client_ip, domain, is_blocked, timestamp, timestamp))

                        # Ensure client exists in clients table
                        c.execute("""
                            INSERT INTO clients (ip, name, source, first_seen, last_seen, total_queries)
                            VALUES (?, ?, 'querylog', ?, ?, 1)
                            ON CONFLICT(ip) DO UPDATE SET
                                last_seen = MAX(clients.last_seen, excluded.last_seen),
                                total_queries = clients.total_queries + 1
                        """, (client_ip, client_name, timestamp, timestamp))

                except sqlite3.IntegrityError:
                    # Duplicate entry, skip
                    pass

            # Update unique domain counts for updated clients
            c.execute("""
                UPDATE clients
                SET unique_domains = (
                    SELECT COUNT(*) FROM client_domains WHERE client_domains.client_ip = clients.ip
                ),
                total_queries = (
                    SELECT COALESCE(SUM(count), 0) FROM client_domains WHERE client_domains.client_ip = clients.ip
                )
            """)

            conn.commit()

        return inserted_count

    def get_summary(self) -> Dict[str, Any]:
        """Get global KPI metrics."""
        with self._get_connection() as conn:
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) FROM queries")
            total_queries = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM clients WHERE total_queries > 0")
            active_clients = c.fetchone()[0]

            c.execute("SELECT COUNT(DISTINCT domain) FROM client_domains")
            unique_domains = c.fetchone()[0]

            c.execute("SELECT COALESCE(SUM(blocked_count), 0) FROM client_domains")
            blocked_queries = c.fetchone()[0]

            c.execute("SELECT AVG(elapsed_ms) FROM queries WHERE elapsed_ms > 0")
            avg_latency = round(c.fetchone()[0] or 0.0, 1)

            return {
                "total_queries": total_queries,
                "active_clients": active_clients,
                "unique_domains": unique_domains,
                "blocked_queries": blocked_queries,
                "avg_latency_ms": avg_latency
            }

    def get_clients(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all clients with query counts, unique domain count, and last activity."""
        with self._get_connection() as conn:
            c = conn.cursor()
            query = """
                SELECT ip, name, source, first_seen, last_seen, total_queries, unique_domains
                FROM clients
                WHERE total_queries > 0
            """
            params = []
            if search:
                query += " AND (ip LIKE ? OR name LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            query += " ORDER BY total_queries DESC, last_seen DESC"
            c.execute(query, params)
            return [dict(row) for row in c.fetchall()]

    def get_client_domains(self, client_ip: str, search: Optional[str] = None, 
                           filter_status: str = "all", sort_by: str = "count", 
                           limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get web addresses visited by a specific client, with frequency counts and percentages."""
        with self._get_connection() as conn:
            c = conn.cursor()

            # Client details
            c.execute("SELECT ip, name, total_queries, unique_domains, first_seen, last_seen FROM clients WHERE ip = ?", (client_ip,))
            client_row = c.fetchone()
            client_info = dict(client_row) if client_row else {"ip": client_ip, "name": client_ip, "total_queries": 0, "unique_domains": 0}

            total_client_queries = client_info.get("total_queries", 0)

            where_clauses = ["client_ip = ?"]
            params: List[Any] = [client_ip]

            if search:
                where_clauses.append("domain LIKE ?")
                params.append(f"%{search.lower()}%")

            if filter_status == "blocked":
                where_clauses.append("blocked_count > 0")
            elif filter_status == "allowed":
                where_clauses.append("blocked_count = 0")

            where_str = " AND ".join(where_clauses)

            # Count total matching domains
            c.execute(f"SELECT COUNT(*) FROM client_domains WHERE {where_str}", params)
            total_matching = c.fetchone()[0]

            order_col = "count DESC"
            if sort_by == "domain":
                order_col = "domain ASC"
            elif sort_by == "last_accessed":
                order_col = "last_accessed DESC"
            elif sort_by == "blocked":
                order_col = "blocked_count DESC"

            query_sql = f"""
                SELECT domain, count, blocked_count, first_accessed, last_accessed
                FROM client_domains
                WHERE {where_str}
                ORDER BY {order_col}
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            c.execute(query_sql, params)
            rows = c.fetchall()

            domains = []
            for r in rows:
                cnt = r["count"]
                pct = round((cnt / total_client_queries * 100), 2) if total_client_queries > 0 else 0
                domains.append({
                    "domain": r["domain"],
                    "count": cnt,
                    "blocked_count": r["blocked_count"],
                    "percentage": pct,
                    "first_accessed": r["first_accessed"],
                    "last_accessed": r["last_accessed"],
                    "is_blocked": bool(r["blocked_count"] > 0)
                })

            return {
                "client": client_info,
                "total_domains": total_matching,
                "domains": domains
            }

    def get_network_top_domains(self, limit: int = 50, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the most frequently called web addresses across all computers, including client counts."""
        with self._get_connection() as conn:
            c = conn.cursor()
            where = ""
            params: List[Any] = []
            if search:
                where = "WHERE domain LIKE ?"
                params.append(f"%{search.lower()}%")

            query = f"""
                SELECT 
                    domain, 
                    SUM(count) as total_count,
                    SUM(blocked_count) as total_blocked,
                    COUNT(DISTINCT client_ip) as client_count,
                    MAX(last_accessed) as last_accessed
                FROM client_domains
                {where}
                GROUP BY domain
                ORDER BY total_count DESC
                LIMIT ?
            """
            params.append(limit)
            c.execute(query, params)
            return [dict(r) for r in c.fetchall()]

    def get_recent_activity(self, client_ip: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch the latest live DNS requests for the ticker/stream."""
        with self._get_connection() as conn:
            c = conn.cursor()
            if client_ip:
                c.execute("""
                    SELECT timestamp, client_ip, client_name, domain, query_type, status, reason, elapsed_ms, cached
                    FROM queries
                    WHERE client_ip = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (client_ip, limit))
            else:
                c.execute("""
                    SELECT timestamp, client_ip, client_name, domain, query_type, status, reason, elapsed_ms, cached
                    FROM queries
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
            return [dict(r) for r in c.fetchall()]

    def get_hourly_activity(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get query counts grouped by hour for time series charts."""
        with self._get_connection() as conn:
            c = conn.cursor()
            # SQLite strftime for ISO timestamp
            c.execute("""
                SELECT 
                    strftime('%Y-%m-%d %H:00', timestamp) as hour_slot,
                    COUNT(*) as query_count,
                    COUNT(DISTINCT client_ip) as active_clients
                FROM queries
                GROUP BY hour_slot
                ORDER BY hour_slot DESC
                LIMIT ?
            """, (hours,))
            rows = c.fetchall()
            return [dict(r) for r in reversed(rows)]
