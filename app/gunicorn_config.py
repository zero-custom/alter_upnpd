import os
from config import GunicornConfig

bind = f"0.0.0.0:{os.environ.get('LISTEN_PORT', '5000')}"
workers = GunicornConfig.WORKERS
worker_class = "sync"
timeout = GunicornConfig.TIMEOUT
graceful_timeout = GunicornConfig.GRACEFUL_TIMEOUT
keepalive = GunicornConfig.KEEPALIVE

def on_starting(server):
    import app as app_mod
    app_mod.setup_logging()

def post_worker_init(worker):
    import app as app_mod
    app_mod.lifecycle.start()

def worker_exit(server, worker):
    import app as app_mod
    app_mod.lifecycle.stop()
