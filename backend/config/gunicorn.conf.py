"""Production Gunicorn configuration.

Run: `gunicorn -c config/gunicorn.conf.py config.wsgi`

Tuned for a small VPS handling tens of concurrent users:
- one worker per CPU core ×2 + 1, each with 2 threads, so requests never
  queue behind one another (no more "server busy" stalls from a single worker)
- timeouts tuned so a slow upstream (SMTP/Razorpay/Redis) never hangs a worker
- graceful reload + periodic worker recycling to avoid memory leaks
- overridable via env so the same file works on a 1-core box or a bigger one
"""
import multiprocessing
import os

# -------------------------------------------------------------------- bind
# Listen on localhost only; nginx (or another reverse proxy) terminates TLS
# and forwards here. Change GUNICORN_BIND to 0.0.0.0:8000 for containers.
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")

# -------------------------------------------------------------- concurrency
# 2×CPU + 1 workers. 30-40 concurrent users are comfortably served by 3-5
# workers; the extra thread per worker absorbs slow I/O waits cheaply.
workers = int(os.getenv("GUNICORN_WORKERS", str(multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")

# Every worker handles a request only up to this many; then it restarts and
# picks up fresh code, so memory bloat and slowly leaked sockets self-heal.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = 50

# ----------------------------------------------------------------- timeouts
# Hard cap for a single request (a worker stuck on a slow SMTP/Gateway call
# is reclaimed instead of wedging the whole queue).
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
# Time allowed for a worker to finish after SIGTERM during reload/restart.
graceful_timeout = 30
# Keep-alive for the nginx->gunicorn connection (reuses the backend socket).
keepalive = 5

# ------------------------------------------------------------- process mgmt
# Reload workers on code change (dev convenience; on a VPS run under systemd
# this is safe too — it only applies on SIGHUP).
reload = os.getenv("GUNICORN_RELOAD", "False").lower() in ("1", "true")
# New workers finish startup before old ones are torn down.
preload_app = True

# --------------------------------------------------------------------- logs
# Structured-ish plain logs to stdout/stderr; journald/nginx captures them.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(L)s'
