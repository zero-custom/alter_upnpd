# static_bp.py — 本地静态资源 Blueprint

通过 Flask Blueprint 提供本地静态文件（ECharts JS、favicon）服务。不含应用逻辑。

## Blueprint

以 `static_assets` 名称注册到 Flask 应用，路由为 `/static/<path:filename>`。

文件从 `app/static/` 目录通过 `Flask.send_from_directory()` 提供。

### 使用

```python
from static_bp import static_bp
app.register_blueprint(static_bp)
```
