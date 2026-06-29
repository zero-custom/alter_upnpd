# soap_xml.py — SOAP XML Parsing & Serialization

SOAP envelope parsing and response building for UPnP control messages. No Flask dependency — pure lxml operations.

## Module Constants

| Constant | Value | Description |
|---|---|---|
| `NS` | `{s, u, p}` | XML namespace shortcuts for SOAP envelope and UPnP services. |
| `PORT_MIN` | `1` | Minimum valid port number. |
| `PORT_MAX` | `65535` | Maximum valid port number. |
| `MAX_SOAP_BODY` | `102400` (100KB) | Maximum allowed SOAP request body size. |
| `NS_SOAP_ENV` | `http://schemas.xmlsoap.org/soap/envelope/` | SOAP 1.1 envelope namespace. |
| `NS_SOAP_ENC` | `http://schemas.xmlsoap.org/soap/encoding/` | SOAP 1.1 encoding namespace. |
| `NS_UPNP_ERR` | `urn:schemas-upnp-org:control-1-0` | UPnP error namespace. |

## SoapBodyParser

Static methods only. No instance state.

### Parsing Methods

| Method | Description |
|---|---|
| `parse_action_from_header(header_value)` | Extracts action name from `SOAPACTION` header (e.g. `"urn:...:WANIPConnection:1#AddPortMapping"` → `"AddPortMapping"`). |
| `extract_service_urn(soapaction_header)` | Extracts service URN from SOAPACTION header (e.g. `"urn:...:WANIPConnection:1"`). |
| `parse_body(xml_data)` | Parses SOAP XML body into `{action: str, params: dict}`. Security: entity resolution disabled, network access disabled. Empty dict on failure. |

### Response Building Methods

| Method | Description |
|---|---|
| `build_success_response(action_name, return_values, service_urn)` | Builds SOAP 1.1 success envelope `<{ns}{ActionName}Response>` with optional return values. |
| `build_error_response(fault_string, error_code)` | Builds SOAP 1.1 fault envelope. With `error_code`: includes UPnPError detail. Without: plain fault string. |
| `validate_port(port)` | Returns `True` if `PORT_MIN <= port <= PORT_MAX`. |

### Usage

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
