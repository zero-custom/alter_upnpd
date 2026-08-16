# webui.py — GOST 监控面板

基于 PyWebIO + ECharts 的仪表板，嵌入在 Flask 应用中（路由 `/`）。提供端口映射的实时监控、增删操作和流量图表。

## 数据来源

| 来源 | 说明 |
|---|---|
| GostClient.get_port_mappings() | 端口映射列表（协议、端口、状态、实时速率、连接数） |
| GostClient.get_summary_stats() | 聚合统计（通过 Prometheus metrics 计算总带宽、连接数、错误数） |

## 布局

| 区域 | 说明 |
|---|---|
| Summary | 四张概览卡片：映射数 / 活动连接 / 总量 / 错误数 |
| Chart | 总流量趋势折线图（入站带宽、出站带宽、连接数），默认展示最近 1 小时，支持拖拽缩放 |
| Table | 端口映射表格，含展开行显示各端口独立图表 |
| Add Form | 折叠添加映射表单（External Port / Protocol / Internal Client / Internal Port / Description / Lease） |

## 主要函数

| 函数 | 说明 |
|---|---|
| main() | 入口点：初始化 PyWebIO 页面，渲染初始状态，启动后台刷新线程 |
| _refresh() | 定时刷新：拉取最新映射和统计，增量更新表格（JS cell patch）或全量重绘 |
| _record_data_points() | 从 Prometheus counter 增量计算带宽，按时间序列存储到 `_history` |
| _build_echarts_html() | 使用 pyecharts 构建 ECharts 折线图 HTML，支持降采样和 dataZoom |
| _render_table() | 渲染映射表格，预置隐藏的端口图表容器，JS 在展开时移入 |
| _update_table_data() | 仅更新表格中变化的单元格值（JS innerHTML patch，避免闪烁） |
| _handle_add() | 处理添加映射表单提交，验证端口范围，调用 GostClient |

## 图表规格

| 属性 | 值 |
|---|---|
| 渲染引擎 | pyecharts (ECharts 6.x) |
| 滑动时间窗 | `EnvConfig.gost_webui_window_seconds`（默认 172800 = 48 小时）。只展示从现在往前该时间长度内的数据，新数据进入后超出窗口的旧数据被顶出，形成滑动窗口 |
| 显示上限 | `EnvConfig.gost_webui_history_points` 经 `min(., 1000)` 派生（默认 1000 点） |
| 采样方式 | 时间窗内**指数衰减采样**：越接近现在采样率越高、越久远越低。分段 0–4h / 4–12h / 12–28h / 28–48h，配额权重 4:2:1:1（最近 4h 占一半点数） |
| 刷新间隔 | `EnvConfig.gost_webui_refresh_interval`（默认 10 秒） |
| 曲线样式 | 直线（`is_smooth=False`），无数据点标记（`is_symbol_show=False`） |
| X 轴 | ECharts `type: "time"`，毫秒级 Unix 时间戳（自动格式化标签：放大显示时间，缩小显示日期+时间） |
| 缩放 | dataZoom 默认展示最近 1 小时 |
| 配色 | 入站蓝色、出站绿色、连接数橙色 |
| 图表加载 | ECharts 从本地 `/static/js/echarts.min.js` 加载；无外部 CDN 依赖（pywebio `cdn=False`）。 |

## 刷新机制

- 后台线程每 10 秒调用 `_refresh()`
- 使用 `_REFRESH_LOCK` 防止并发刷新
- 映射数量不变时仅 patch 表格中变化的单元格（DL/UL 速度、连接数、流量）
- 映射数量变化时全量重绘并恢复选中状态
- `SessionNotFoundException` 导致线程安全退出（页面关闭后停止）

## 表格扩展行

每行左侧的 ▶ 触发器展开一个详情行，显示该端口的独立流量图表：
- 图表预渲染到隐藏容器（`visibility:hidden; position:absolute`）
- 展开时 JS 将 DOM 节点移入详情行
- `echarts.resize()` 确保容器尺寸正确

## 表格样式

- **斑马纹交替**：JS `_applyZebra()` 在详情行插入后运行，用独立 `dataIdx` 计数器（排除非数据行）对偶数数据行交替设置 `background-color: #edf2f7`
- **标题行**：主标题和二级标题行统一 `background: #e9ecef`，无单元格边框
- **页脚行**：`background: #fafafa`，上方边框
- **详情行**：`colSpan = 16`（来自 `_countTableCols()`，修正 PyWebIO `cells.length = 14`），内部 div `width:100%;box-sizing:border-box`
- **CSS 优先级**：规则以 `.markdown-body` 为前缀，覆盖 Yeti 主题默认样式

## 批量删除

通过复选框选择多个映射，点击底部 "Delete" 按钮批量删除，调用 `GostClient.delete_port_mappings_batch()`。

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `GOST_WEBUI_REFRESH_INTERVAL` | `10` | 仪表板刷新间隔（秒） |
| `GOST_WEBUI_HISTORY_POINTS` | `8640` | 每端口存储的数据点上限（同时作为显示降采样上限的基数，`min(.,1000)` 为渲染点数） |
| `GOST_WEBUI_WINDOW_SECONDS` | `172800` | 图表滑动时间窗（秒）。只显示从现在往前该时长内的数据，越近采样越密，超出窗口的旧数据被顶出 |
| `GOST_API_URL` | `http://127.0.0.1:8000` | GOST API 地址 |
| `GOST_METRICS_URL` | `""` | Prometheus metrics URL（空则自动发现） |
