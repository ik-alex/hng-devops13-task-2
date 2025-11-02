# #!/usr/bin/env python3
# """
# Blue/Green Deployment Log Watcher and Alert System
# Enhanced version with robust parsing and error/failover detection.
# """

# import io
# import os
# import re
# import time
# import json
# import logging
# from collections import deque
# from datetime import datetime, timezone
# import requests

# # ------------------- Configuration -------------------
# LOG_PATH = os.environ.get("NGINX_LOG_PATH", "/var/log/nginx/access.log")
# SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")
# ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", "2.0"))  # %
# WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "200"))  # requests
# ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
# MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "0") == "1"
# MIN_FLIP_CONFIRM = int(os.environ.get("MIN_FLIP_CONFIRM", "3"))

# # ------------------- Logging Setup -------------------
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
# )
# logger = logging.getLogger("watcher")

# # ------------------- Runtime State -------------------
# last_seen_pool = None
# flip_candidate = None
# flip_count = 0
# last_failover_alert_ts = 0
# last_error_alert_ts = 0
# window = deque(maxlen=WINDOW_SIZE)
# window_error_count = 0

# # ------------------- Regex Parser -------------------
# LOG_PATTERN = re.compile(
#     r'\[([^\]]+)\]\s+'
#     r'(?:method=(\S+)\s+)?'
#     r'(?:uri=(\S+)\s+)?'
#     r'(?:status=(\d+)\s+)?'
#     r'(?:pool=(\S+)\s+)?'
#     r'(?:release=(\S+)\s+)?'
#     r'(?:upstream_addr=(\S+)\s+)?'
#     r'(?:upstream_status=(\S+)\s+)?'
#     r'(?:request_time=(\S+)\s+)?'
#     r'(?:upstream_response_time=(\S+)\s+)?'
#     r'(?:client=(\S+))?'
# )


# def parse_log_line(line: str):
#     """Parse standard Nginx access log line with custom fields"""
#     match = LOG_PATTERN.search(line)
#     if not match:
#         return None
#     return {
#         "timestamp": match.group(1),
#         "method": match.group(2) or "-",
#         "uri": match.group(3) or "-",
#         "status": match.group(4) or "-",
#         "pool": match.group(5) or "-",
#         "release": match.group(6) or "-",
#         "upstream_addr": match.group(7) or "-",
#         "upstream_status": match.group(8) or "-",
#         "request_time": match.group(9) or "0",
#         "upstream_response_time": match.group(10) or "0",
#         "client": match.group(11) or "-",
#     }


# # ------------------- Slack Alert -------------------
# def post_slack(message, level="warning", context=None):
#     """Send alert message to Slack"""
#     if not SLACK_WEBHOOK:
#         logger.warning("SLACK_WEBHOOK_URL not configured; would send: %s", message)
#         return

#     emoji = ":rotating_light:" if level == "critical" else ":warning:"
#     payload = {"text": f"{emoji} {message}"}
#     if context:
#         payload["attachments"] = [{"text": context}]

#     try:
#         r = requests.post(SLACK_WEBHOOK, json=payload, timeout=5)
#         if r.status_code >= 400:
#             logger.error("Slack post failed: %s %s", r.status_code, r.text)
#         else:
#             logger.info("Slack alert posted successfully")
#     except Exception as e:
#         logger.exception("Error posting to Slack: %s", e)


# # ------------------- Helpers -------------------
# def is_5xx(status):
#     try:
#         s = int(status)
#         return 500 <= s < 600
#     except Exception:
#         return False


# # ------------------- Core Logic -------------------
# def handle_record(rec):
#     """Process parsed log record and perform alert logic"""
#     global last_seen_pool, flip_candidate, flip_count
#     global last_failover_alert_ts, last_error_alert_ts, window_error_count

#     pool = rec.get("pool") or rec.get("x_app_pool") or "-"
#     status = rec.get("status") or rec.get("upstream_status") or "0"
#     ts = rec.get("timestamp") or datetime.now(timezone.utc).isoformat()

#     # Update sliding window
#     error_flag = 1 if is_5xx(status) else 0
#     if len(window) == WINDOW_SIZE:
#         window_error_count -= window[0]
#     window.append(error_flag)
#     window_error_count += error_flag

#     total = len(window)
#     error_rate = (window_error_count / total * 100) if total > 0 else 0.0

#     # --- Failover detection ---
#     if last_seen_pool is None and pool != "-":
#         last_seen_pool = pool
#         logger.info("Initial pool detected: %s", pool)
#     elif pool != "-" and pool != last_seen_pool:
#         if flip_candidate is None or flip_candidate != pool:
#             flip_candidate = pool
#             flip_count = 1
#         else:
#             flip_count += 1

#         if flip_count >= MIN_FLIP_CONFIRM:
#             now = time.time()
#             if not MAINTENANCE_MODE and (now - last_failover_alert_ts > ALERT_COOLDOWN_SEC):
#                 context = (
#                     f"Failover detected: {last_seen_pool} → {pool} at {ts}\n"
#                     f"Recent error rate: {error_rate:.2f}% (window={total})"
#                 )
#                 post_slack("Traffic pool switch detected", level="critical", context=context)
#                 last_failover_alert_ts = now
#             logger.warning("Failover confirmed: %s → %s", last_seen_pool, pool)
#             last_seen_pool = pool
#             flip_candidate = None
#             flip_count = 0

#     # --- Error rate check ---
#     if total >= min(WINDOW_SIZE, 20):
#         if error_rate > ERROR_RATE_THRESHOLD:
#             now = time.time()
#             if not MAINTENANCE_MODE and (now - last_error_alert_ts > ALERT_COOLDOWN_SEC):
#                 ctx = f"High 5xx rate: {error_rate:.2f}% over last {total} requests (threshold {ERROR_RATE_THRESHOLD}%)"
#                 post_slack("High error rate detected", level="warning", context=ctx)
#                 last_error_alert_ts = now


# def follow(file_path):
#     """Tail the log file continuously (like tail -f)"""
#     with open(file_path, "r", errors="ignore") as fh:
#         try:
#             fh.seek(0, 2)
#         except (OSError, io.UnsupportedOperation):
#             pass

#         while True:
#             line = fh.readline()
#             if not line:
#                 time.sleep(0.2)
#                 continue
#             yield line.strip()


# # ------------------- Main Loop -------------------
# def main():
#     logger.info("=" * 60)
#     logger.info("🔍 Blue/Green Log Watcher Started")
#     logger.info("=" * 60)
#     logger.info("Log File: %s", LOG_PATH)
#     logger.info("Error Rate Threshold: %.2f%%", ERROR_RATE_THRESHOLD)
#     logger.info("Window Size: %d", WINDOW_SIZE)
#     logger.info("Alert Cooldown: %d sec", ALERT_COOLDOWN_SEC)
#     logger.info("Maintenance Mode: %s", "ON" if MAINTENANCE_MODE else "OFF")
#     logger.info("Slack: %s", "Configured ✅" if SLACK_WEBHOOK else "NOT Configured ❌")
#     logger.info("=" * 60)

#     while not os.path.exists(LOG_PATH):
#         logger.warning("Waiting for log file: %s", LOG_PATH)
#         time.sleep(2)

#     for line in follow(LOG_PATH):
#         rec = parse_log_line(line)
#         if rec:
#             handle_record(rec)


# if __name__ == "__main__":
#     try:
#         main()
#     except KeyboardInterrupt:
#         logger.info("Watcher stopped by user")
#     except Exception as e:
#         logger.exception("Fatal error in watcher: %s", e)


#!/usr/bin/env python3
"""
Blue/Green Deployment Log Watcher and Alert System
Monitors Nginx logs for failover events, error spikes, and upstream issues.
Sends alerts to Slack with cooldowns and maintenance mode support.
"""

import os
import io
import re
import time
import json
import requests
from collections import deque
from typing import Dict, Optional

# -------------------- CONFIG --------------------
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
ERROR_RATE_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "2.0"))
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "200"))
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))
NGINX_LOG_FILE = os.getenv("NGINX_LOG_PATH", "/var/log/nginx/access.log")
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "0") == "1"
MIN_FLIP_CONFIRM = int(os.getenv("MIN_FLIP_CONFIRM", "3"))
ACTIVE_POOL = os.getenv("ACTIVE_POOL", "blue")

# -------------------- STATE --------------------
last_seen_pool: Optional[str] = None
pool_history = deque(maxlen=MIN_FLIP_CONFIRM)
request_window = deque(maxlen=WINDOW_SIZE)
last_alert_times: Dict[str, float] = {}

# -------------------- LOG PARSING --------------------
LOG_PATTERN = re.compile(
    r'\[([^\]]+)\] '
    r'(?:method=(\S+) )?'
    r'(?:uri=(\S+) )?'
    r'(?:status=(\d+) )?'
    r'(?:pool=(\S+) )?'
    r'(?:release=(\S+) )?'
    r'(?:upstream_addr=(\S+) )?'
    r'(?:upstream_status=(\S+) )?'
    r'(?:request_time=(\S+) )?'
    r'(?:upstream_response_time=(\S+) )?'
    r'(?:client=(\S+))?'
)

def parse_log_line(line: str) -> Optional[Dict[str, str]]:
    match = LOG_PATTERN.search(line)
    if not match:
        return None
    return {
        "timestamp": match.group(1),
        "method": match.group(2) or "-",
        "uri": match.group(3) or "-",
        "status": match.group(4) or "0",
        "pool": match.group(5) or "-",
        "release": match.group(6) or "-",
        "upstream_addr": match.group(7) or "-",
        "upstream_status": match.group(8) or "-",
        "request_time": match.group(9) or "0",
        "upstream_response_time": match.group(10) or "0",
        "client": match.group(11) or "-"
    }

# -------------------- SLACK ALERT --------------------
def send_slack_alert(alert_type: str, message: str, details: Dict[str, str]):
    if not SLACK_WEBHOOK_URL or MAINTENANCE_MODE:
        return
    now = time.time()
    if alert_type in last_alert_times and now - last_alert_times[alert_type] < ALERT_COOLDOWN_SEC:
        return
    payload = {
        "attachments": [{
            "color": "#ff0000" if "error" in alert_type.lower() else "#ffa500",
            "title": f"🚨 {alert_type}",
            "text": message,
            "fields": [{"title": k, "value": v, "short": True} for k, v in details.items()],
            "footer": "Blue/Green Monitoring",
            "ts": int(now)
        }]
    }
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code == 200:
            last_alert_times[alert_type] = now
            print(f"✅ Slack alert sent: {alert_type}")
        else:
            print(f"❌ Slack alert failed: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ Slack alert error: {e}")

# -------------------- FAILOVER & ERROR LOGIC --------------------
def check_failover(current_pool: str, log_entry: Dict[str, str]):
    global last_seen_pool
    pool_history.append(current_pool)
    if last_seen_pool is None:
        last_seen_pool = current_pool
        print(f"📍 Initial pool detected: {current_pool}")
        return
    # Confirm pool flip
    if len(pool_history) == MIN_FLIP_CONFIRM and len(set(pool_history)) == 1:
        new_pool = pool_history[-1]
        if new_pool != last_seen_pool:
            print(f"🔄 FAILOVER DETECTED: {last_seen_pool} → {new_pool}")
            send_slack_alert(
                "Failover Detected",
                f"Traffic switched from *{last_seen_pool}* → *{new_pool}*",
                {
                    "Previous Pool": last_seen_pool,
                    "Current Pool": new_pool,
                    "Release": log_entry.get("release", "unknown"),
                    "Upstream": log_entry.get("upstream_addr", "unknown"),
                    "Timestamp": log_entry.get("timestamp", "unknown")
                }
            )
            last_seen_pool = new_pool

def check_error_rate(status_code: int):
    request_window.append(status_code)
    if len(request_window) < WINDOW_SIZE:
        return
    error_count = sum(1 for s in request_window if s >= 500)
    error_rate = error_count / len(request_window) * 100
    if error_rate > ERROR_RATE_THRESHOLD:
        print(f"⚠️ HIGH ERROR RATE: {error_rate:.2f}% ({error_count}/{len(request_window)})")
        send_slack_alert(
            "High Error Rate",
            f"Error rate exceeded threshold: *{error_rate:.2f}%*",
            {"Error Rate": f"{error_rate:.2f}%", "Threshold": f"{ERROR_RATE_THRESHOLD}%", "Window": str(WINDOW_SIZE)}
        )

def check_partial_failover(upstream_status: str, log_entry: Dict[str, str]):
    statuses = [s.strip() for s in upstream_status.split(",") if s.strip()]
    if any(s.startswith("5") for s in statuses):
        send_slack_alert(
            "Partial Failover Detected",
            f"Upstream errors: `{upstream_status}`",
            {
                "Pool": log_entry.get("pool", "unknown"),
                "Release": log_entry.get("release", "unknown"),
                "Upstream": log_entry.get("upstream_addr", "unknown"),
                "Timestamp": log_entry.get("timestamp", "unknown")
            }
        )

# -------------------- FILE TAILING --------------------
def tail_log(file_path: str):
    """Tail a file safely even if non-seekable (Docker mounts)."""
    while not os.path.exists(file_path):
        print(f"⏳ Waiting for log file: {file_path}")
        time.sleep(2)
    with open(file_path, "r") as f:
        try:
            f.seek(0, 2)
        except (io.UnsupportedOperation, OSError):
            pass  # non-seekable stream
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line.strip()

# -------------------- MAIN LOOP --------------------
def main():
    print("="*60)
    print("🔍 Blue/Green Log Watcher Started")
    print(f"📊 Log File: {NGINX_LOG_FILE}")
    print(f"⚠️ Error Threshold: {ERROR_RATE_THRESHOLD}% | Window: {WINDOW_SIZE}")
    print(f"⏱ Alert Cooldown: {ALERT_COOLDOWN_SEC} sec | Maintenance: {MAINTENANCE_MODE}")
    print(f"📍 Initial Active Pool: {ACTIVE_POOL}")
    print("="*60)
    for line in tail_log(NGINX_LOG_FILE):
        log_entry = parse_log_line(line)
        if not log_entry:
            continue
        current_pool = log_entry.get("pool", "").strip()
        status_code = int(log_entry.get("status", "0"))
        upstream_status = log_entry.get("upstream_status", "").strip()

        check_failover(current_pool, log_entry)
        check_error_rate(status_code)
        check_partial_failover(upstream_status, log_entry)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("👋 Watcher stopped by user")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        raise
