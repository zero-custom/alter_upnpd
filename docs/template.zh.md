# template.py — Jinja2 XML 模板渲染器

基于 mtime 缓存失效的线程安全 Jinja2 模板渲染器。无 Flask 依赖。

## TemplateRenderer

### 构造参数

| 参数 | 说明 |
|---|---|
| `xml_dir` | 包含 XML 模板文件的目录路径。 |

### 方法

| 方法 | 说明 |
|---|---|
| `set_var(name, fn)` | 注册一个可调用对象，为模板提供渲染上下文。每次渲染时调用。 |
| `render(template_name)` | 渲染模板：从 `xml_dir/{template_name}` 加载，按 mtime 缓存，若注册了上下文函数则调用。文件不存在时返回 `"404 Not Found"`。 |

### 缓存策略

模板缓存在 `_cache` 字典中，以 `mtime` 作为键。渲染时若文件的 mtime 未变化，则复用已编译的模板；若 mtime 不同，则重新加载并更新缓存。

### 线程安全

缓存访问通过 `threading.Lock`（`_lock`）保护。

### 使用示例

```python
renderer = TemplateRenderer("/path/to/xml/")
renderer.set_var("rootDesc.xml", lambda: {"LOCAL_IP": "192.168.1.1", "LOCAL_PORT": 5000})
xml_output = renderer.render("rootDesc.xml")
```
