from config import Config

bind = f"0.0.0.0:{Config.LISTEN_PORT}"
workers = Config.WSGI_WORKERS
worker_class = "sync"
timeout = Config.WSGI_TIMEOUT
graceful_timeout = Config.WSGI_GRACEFUL_TIMEOUT
keepalive = Config.WSGI_KEEPALIVE

def on_starting(server):
    import app as app_mod
    app_mod.setup_logging()

def post_worker_init(worker):
    import app as app_mod
    app_mod.init_background_services()

def worker_exit(server, worker):
    import app as app_mod
    app_mod.shutdown_background_services()
