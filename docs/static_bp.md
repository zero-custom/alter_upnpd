# static_bp.py — Local Static Assets Blueprint

Serves local static files (ECharts JS, favicon) via a Flask Blueprint. No application logic.

## Blueprint

Registered as `static_assets` on the Flask app with route `/static/<path:filename>`.

Files are served from `app/static/` directory via `Flask.send_from_directory()`.

### Usage

```python
from static_bp import static_bp
app.register_blueprint(static_bp)
```
