import os
import shutil
import subprocess
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
import requests

logger = logging.getLogger("GliNetClient")

class GliNetClient:
    def __init__(self, ip: str, username: str = "root", password: str = "", timeout: int = 10):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.sid: Optional[str] = None
        self._openssl_path = self._find_openssl()

    def _find_openssl(self) -> Optional[str]:
        # 1. System PATH
        p = shutil.which("openssl")
        if p and os.path.exists(p):
            return p
        
        # 2. Known Windows Git / Cygwin / Mingw locations
        candidates = [
            r"C:\Program Files\Git\usr\bin\openssl.exe",
            r"C:\Program Files (x86)\Git\usr\bin\openssl.exe",
            r"C:\msys64\usr\bin\openssl.exe",
            r"C:\cygwin64\bin\openssl.exe"
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _compute_pw_crypt(self, alg: int, salt: str, password: str) -> str:
        """Compute salted password hash via openssl passwd or SSH fallback."""
        if self._openssl_path:
            try:
                cmd = [self._openssl_path, "passwd", f"-{alg}", "-salt", salt, password]
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
                return res.decode().strip()
            except Exception as e:
                logger.warning(f"Local openssl failed: {e}. Trying router SSH fallback...")

        # SSH fallback: execute openssl on router directly
        try:
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.ip, username=self.username, password=self.password, timeout=self.timeout)
            # escape password safely
            cmd = f"openssl passwd -{alg} -salt '{salt}' '{password}'"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode().strip()
            ssh.close()
            if out:
                return out
        except Exception as e:
            logger.error(f"SSH fallback for password hashing failed: {e}")

        raise RuntimeError("Could not compute password crypt hash (openssl not available locally or via SSH)")

    def login(self) -> bool:
        """Authenticate with GL.iNet router via challenge-response RPC."""
        url = f"http://{self.ip}/rpc"
        try:
            # Step 1: Challenge
            challenge_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "challenge",
                "params": {"username": self.username}
            }
            r = self.session.post(url, json=challenge_payload, timeout=self.timeout)
            if r.status_code != 200:
                logger.error(f"Challenge HTTP error: {r.status_code}")
                return False

            res = r.json().get("result")
            if not res or "nonce" not in res:
                logger.error(f"Invalid challenge response: {r.text}")
                return False

            alg = res["alg"]
            salt = res["salt"]
            nonce = res["nonce"]

            # Step 2: Compute pw crypt hash
            pw_crypt = self._compute_pw_crypt(alg, salt, self.password)

            # Step 3: Compute final login hash: sha256(username:pw:nonce)
            to_hash = f"{self.username}:{pw_crypt}:{nonce}"
            login_hash = hashlib.sha256(to_hash.encode()).hexdigest()

            # Step 4: Login
            login_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "login",
                "params": {
                    "username": self.username,
                    "hash": login_hash
                }
            }
            r_login = self.session.post(url, json=login_payload, timeout=self.timeout)
            login_data = r_login.json().get("result")
            if not login_data or "sid" not in login_data:
                logger.error(f"Login rejected: {r_login.text}")
                return False

            self.sid = login_data["sid"]
            self.session.cookies.set("Admin-Token", self.sid)
            logger.info("Successfully authenticated with GL.iNet gateway.")
            return True

        except Exception as e:
            logger.error(f"Failed to login to {self.ip}: {e}")
            return False

    def _request(self, method: str, path: str, **kwargs) -> Optional[requests.Response]:
        """Send authenticated request to router with auto-relogin on 401/403."""
        if not self.sid:
            if not self.login():
                return None

        url = f"http://{self.ip}{path}"
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if resp.status_code in (401, 403):
                logger.info("Session expired or rejected, re-authenticating...")
                if self.login():
                    resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                else:
                    return None
            return resp
        except Exception as e:
            logger.error(f"HTTP request to {url} failed: {e}")
            return None

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Fetch AdGuard Home status from GL.iNet router."""
        resp = self._request("GET", "/control/status")
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_clients(self) -> List[Dict[str, Any]]:
        """Fetch discovered and configured clients from AdGuard Home."""
        resp = self._request("GET", "/control/clients")
        if resp and resp.status_code == 200:
            data = resp.json()
            # combine auto_clients and persistent clients
            auto_clients = data.get("auto_clients", []) or []
            persistent_clients = data.get("clients", []) or []
            return auto_clients + persistent_clients
        return []

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """Fetch aggregated AdGuard stats (top domains, top clients, blocked ratio)."""
        resp = self._request("GET", "/control/stats")
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_querylog(self, limit: int = 200, older_than: Optional[str] = None, search: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch query log entries with optional pagination and search filter."""
        params: Dict[str, Any] = {"limit": limit}
        if older_than:
            params["older_than"] = older_than
        if search:
            params["search"] = search

        resp = self._request("GET", "/control/querylog", params=params)
        if resp and resp.status_code == 200:
            return resp.json()
        return None
