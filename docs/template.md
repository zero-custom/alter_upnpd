# template.py — Jinja2 XML Template Renderer

Thread-safe Jinja2 template renderer with mtime-based cache invalidation. No Flask dependency.

## TemplateRenderer

### Constructor

| Param | Description |
|---|---|
| `xml_dir` | Directory path containing XML template files. |

### Methods

| Method | Description |
|---|---|
| `set_var(name, fn)` | Registers a callable that provides the render context for a template. Called on every render. |
| `render(template_name)` | Renders a template: loads from `xml_dir/{template_name}`, caches by mtime, invokes the context function if registered. Returns `"404 Not Found"` if the file doesn't exist. |

### Caching

Templates are cached in `_cache` dict with `mtime` key. On render, if the file's mtime hasn't changed, the cached compiled template is reused. If mtime differs, the template is reloaded and the cache updated.

### Thread Safety

Cache access is guarded by `threading.Lock` (`_lock`).

### Usage

```python
renderer = TemplateRenderer("/path/to/xml/")
renderer.set_var("rootDesc.xml", lambda: {"LOCAL_IP": "192.168.1.1", "LOCAL_PORT": 5000})
xml_output = renderer.render("rootDesc.xml")
```
