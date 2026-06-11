# gunicorn_config.py — Gunicorn WSGI 配置

用于生产部署的 Gunicorn 服务器配置。单工作进程，同步模式。

| 设置 | 值 |
|---|---|
| `bind` | `0.0.0.0:{LISTEN_PORT}`（从环境变量读取，默认 8000） |
| `workers` | 1 |
| `worker_class` | `sync` |
| `timeout` | 30s |
| `graceful_timeout` | 10s |
| `keepalive` | 5s |

## 生命周期钩子

| 钩子 | 动作 |
|---|---|
| `on_starting` | 调用 `app.setup_logging()` 配置日志。 |
| `post_worker_init` | 调用 `app.init_background_services()` 启动 SSDP、STUN 和租期清理线程。 |
| `worker_exit` | 调用 `app.shutdown_background_services()` 发送 SSDP byebye 并等待线程结束。 |

## 为什么只有一个 Worker

UPnP IGD 状态（SSDP 套接字、STUN 线程）是每个进程独有的。多个 Worker 会各自尝试绑定 SSDP 多播套接字（只有一个能成功）并重复执行定时任务。单 Worker 加 `sync` 模式是正确的部署方式。
