# webui_render.py — WebUI HTML/JS 渲染

使用 PyWebIO 组件（卡片、表格、弹窗）和 ECharts JS 渲染 GOST WebUI 仪表板。数据准备依赖 `webui_format`。

## 主要函数

| 函数 | 说明 |
|---|---|
| `render_dashboard(client, cs)` | 主仪表板渲染函数：摘要卡片、映射表、每端口详情弹窗、聚合图表。 |
| `_render_table(mappings, stats)` | 渲染端口映射表，显示每端口的速率、连接数、流量和操作按钮。 |
| `_build_echarts_html(cs)` | 构建 ECharts 折线图，x 轴使用 `type: "time"`（毫秒时间戳，非格式化字符串）。支持降采样和 dataZoom 默认展示最近 1 小时。 |
| `_delete_selected(client, selected_names)` | 批量删除处理器：通过弹窗确认后逐个删除选中的映射。 |

## UI 组件

| 组件 | 说明 |
|---|---|
| 摘要卡片 | 4 张卡片展示映射数、活跃连接、总流量、错误数。 |
| 映射表 | 可排序表格，显示端口、协议、客户端、速率、连接数、流量、时长、操作。 |
| 详情弹窗 | 每端口弹出窗口，展示 ECharts 折线图 + per-service 统计。 |
| 聚合图表 | ECharts 面积图，展示聚合的入站/出站速率和连接数。 |
| 添加表单 | 添加新端口映射的输入表单。 |
| 工具栏 | 刷新开关、自动刷新指示器、删除选中按钮。 |

## 依赖

- PyWebIO（`put_*`、`use_scope`、`popup`）
- pyecharts（`Line`、`opts`、`JsCode`）
- ECharts JS（从本地 `/static/js/echarts.min.js` 提供，通过 `static_bp`）

## 说明

- ECharts 通过 RequireJS 从 `_ECHARTS_CDN_JS` 配置的本地路径 `/static/js/echarts.min.js` 加载，无 CDN fallback。
- 图表使用 LTTB 风格降采样（`_downsample`，阈值 1000 点）以优化大数据集的性能。此前为死代码——`display_max` 现已与 `max_history` 解耦。
- CSS 内联在 `_CUSTOM_CSS` 中（无外部样式表依赖）。

## 时间轴

所有 ECharts 图表（主聚合图 + 各端口详情图）均使用 `type: "time"` x 轴：

- **数据格式**：毫秒级 Unix 时间戳（`int(p.timestamp * 1000)`），传入 `add_xaxis()`。
- **标签格式化**：ECharts 根据缩放级别自动格式化轴标签——放大时显示时间，缩小时显示日期+时间。无需手动调用 `_fmt_time()`。
- **跨午夜处理**：原生时间轴消除了分类轴在 `HH:MM:SS` 字符串跨日重复时导致的折线失真问题。
- **详情图表**：`_TABLE_INIT_SCRIPT` 中的内联 JS 采用相同的 `type:'time'` 模式，时间戳来自 `window._portData`（存储为秒，渲染时转换为毫秒）。
