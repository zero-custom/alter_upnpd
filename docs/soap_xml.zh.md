# soap_xml.py — SOAP XML 解析与序列化

UPnP 控制消息的 SOAP 信封解析和响应构建。无 Flask 依赖——纯 lxml 操作。

## 模块常量

| 常量 | 值 | 说明 |
|---|---|---|
| `NS` | `{s, u, p}` | SOAP 信封和 UPnP 服务的 XML 命名空间缩写。 |
| `PORT_MIN` | `1` | 最小有效端口号。 |
| `PORT_MAX` | `65535` | 最大有效端口号。 |
| `MAX_SOAP_BODY` | `102400` (100KB) | SOAP 请求体最大大小。 |
| `NS_SOAP_ENV` | `http://schemas.xmlsoap.org/soap/envelope/` | SOAP 1.1 信封命名空间。 |
| `NS_SOAP_ENC` | `http://schemas.xmlsoap.org/soap/encoding/` | SOAP 1.1 编码命名空间。 |
| `NS_UPNP_ERR` | `urn:schemas-upnp-org:control-1-0` | UPnP 错误命名空间。 |

## SoapBodyParser

仅包含静态方法，无实例状态。

### 解析方法

| 方法 | 说明 |
|---|---|
| `parse_action_from_header(header_value)` | 从 `SOAPACTION` 头中提取动作名称（如 `"urn:...:WANIPConnection:1#AddPortMapping"` → `"AddPortMapping"`）。 |
| `extract_service_urn(soapaction_header)` | 从 SOAPACTION 头中提取服务 URN。 |
| `parse_body(xml_data)` | 解析 SOAP XML 正文为 `{action: str, params: dict}`。安全措施：禁用实体解析，禁用网络访问。失败返回空 dict。 |

### 响应构建方法

| 方法 | 说明 |
|---|---|
| `build_success_response(action_name, return_values, service_urn)` | 构建 SOAP 1.1 成功信封 `<{ns}{ActionName}Response>`，带可选返回值。 |
| `build_error_response(fault_string, error_code)` | 构建 SOAP 1.1 错误信封。提供 `error_code` 时包含 UPnPError 细节；否则仅包含错误描述。 |
| `validate_port(port)` | 检查端口是否在有效范围内（`PORT_MIN` ~ `PORT_MAX`）。 |

### 使用示例

```python
action = SoapBodyParser.parse_action_from_header(
    'urn:schemas-upnp-org:service:WANIPConnection:1#AddPortMapping'
)
body = SoapBodyParser.parse_body(xml_data)
# body == {"action": "AddPortMapping", "params": {"NewExternalPort": "8080", ...}}

response = SoapBodyParser.build_success_response("AddPortMapping", {
    "NewExternalPort": "8080",
    "NewInternalPort": "80",
})
```
