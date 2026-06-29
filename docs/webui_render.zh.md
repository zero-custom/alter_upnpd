# webui_render.py — WebUI HTML/JS 渲染

使用 PyWebIO 组件（卡片、表格、弹窗）和 ECharts JS 渲染 GOST WebUI 仪表板。数据准备依赖 `webui_format`。

## 主要函数

| 函数 | 说明 |
|---|---|
| `render_dashboard(client, cs)` | 主仪表板渲染函数：摘要卡片、映射表、每端口详情弹窗、聚合图表。 |
| `_render_table(mappings, stats)` | 渲染端口映射表，显示每端口的速率、连接数、流量和操作按钮。 |
| `_build_echarts_html(cs)` | 构建 ECharts 折线图（入站/出站速率、连接数），含所有端口及聚合视图。 |
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

- ECharts 通过 RequireJS 加载，`_ECHARTS_CDN_JS` 中包含 CDN fallback 路径。
- 图表使用 LTTB 风格降采样（`_downsample`）以优化大数据集的性能。
- CSS 内联在 `_CUSTOM_CSS` 中（无外部样式表依赖）。
