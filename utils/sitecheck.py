# utils/sitecheck.py — is each client site up, and when does its TLS certificate expire?
# Results are cached in-process for 5 minutes so the admin overview stays fast.
import datetime as dt
import socket
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_cache: dict[str, tuple[float, dict]] = {}
TTL = 300


def _cert_days(host: str):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=5) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            exp = dt.datetime.strptime(s.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
    return (exp - dt.datetime.utcnow()).days


def check(host: str) -> dict:
    hit = _cache.get(host)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    out = {"host": host, "up": False, "status": None, "ms": None, "cert_days": None, "error": None}
    t0 = time.time()
    try:
        req = urllib.request.Request(f"https://{host}/", headers={"User-Agent": "HapiTech-SiteCheck/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            out["status"] = r.status
            out["up"] = 200 <= r.status < 400
    except urllib.error.HTTPError as e:
        out["status"] = e.code
    except Exception as e:
        out["error"] = type(e).__name__
    out["ms"] = int((time.time() - t0) * 1000)
    try:
        out["cert_days"] = _cert_days(host)
    except Exception:
        pass
    _cache[host] = (time.time(), out)
    return out


def check_many(hosts):
    hosts = list(dict.fromkeys(h for h in hosts if h))
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(check, hosts))
