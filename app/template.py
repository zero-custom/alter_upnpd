import logging
import os
import threading
from typing import Callable

from jinja2 import Template

logger = logging.getLogger("alter_upnpd.template")


class TemplateRenderer:
    def __init__(self, xml_dir: str):
        self._xml_dir = xml_dir
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._vars: dict[str, Callable] = {}

    def set_var(self, name: str, fn: Callable) -> None:
        self._vars[name] = fn

    def render(self, template_name: str) -> str:
        filepath = os.path.join(self._xml_dir, template_name)
        if not os.path.exists(filepath):
            return "404 Not Found"

        mtime = os.path.getmtime(filepath)

        with self._lock:
            cached = self._cache.get(template_name)
            if cached and cached["mtime"] == mtime:
                template = cached["template"]
            else:
                with open(filepath, "r") as f:
                    template = Template(f.read())
                self._cache[template_name] = {"template": template, "mtime": mtime}
                logger.info("Loaded template: %s (mtime=%s)", template_name, mtime)

        context_fn = self._vars.get(template_name)
        context = context_fn() if context_fn else {}
        return template.render(**context)
