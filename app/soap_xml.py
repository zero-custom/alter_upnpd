import logging
from typing import Any, Dict, Optional

from lxml import etree

logger = logging.getLogger("alter_upnpd.soap_xml")

NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "u": "urn:schemas-upnp-org:service:WANIPConnection:1",
    "p": "urn:schemas-upnp-org:service:WANPPPConnection:1",
}

PORT_MIN = 1
PORT_MAX = 65535
MAX_SOAP_BODY = 100 * 1024

NS_SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SOAP_ENC = "http://schemas.xmlsoap.org/soap/encoding/"
NS_UPNP_ERR = "urn:schemas-upnp-org:control-1-0"


class SoapBodyParser:
    @staticmethod
    def parse_action_from_header(header_value: str) -> Optional[str]:
        if not header_value:
            return None
        stripped = header_value.strip().strip('"')
        if "#" in stripped:
            return stripped.split("#")[-1]
        return stripped if stripped else None

    @staticmethod
    def extract_service_urn(soapaction_header: str) -> Optional[str]:
        stripped = soapaction_header.strip().strip('"')
        if "#" in stripped:
            return stripped.split("#")[0]
        return None

    @staticmethod
    def parse_body(xml_data: str) -> Dict[str, Any]:
        if len(xml_data) > MAX_SOAP_BODY:
            logger.warning("SOAP body too large: %d bytes", len(xml_data))
            return {}
        try:
            p = etree.XMLParser(resolve_entities=False, no_network=True)
            root = etree.fromstring(xml_data.encode(), p)
            body = root.find(".//s:Body", namespaces=NS)
            if body is None:
                return {}

            action = body[0].tag.split("}")[-1] if "}" in body[0].tag else body[0].tag

            params = {}
            for elem in body[0]:
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                params[tag] = elem.text or ""

            return {"action": action, "params": params}
        except Exception as e:
            logger.error("Failed to parse SOAP body: %s", e)
            return {}

    @staticmethod
    def build_success_response(
        action_name: str,
        return_values: Optional[Dict[str, Any]] = None,
        service_urn: Optional[str] = None,
    ) -> str:
        ns = service_urn or "urn:schemas-upnp-org:service:WANIPConnection:1"

        root = etree.Element(f"{{{NS_SOAP_ENV}}}Envelope")
        root.set(f"{{{NS_SOAP_ENC}}}encodingStyle", NS_SOAP_ENC)

        body = etree.SubElement(root, f"{{{NS_SOAP_ENV}}}Body")
        response = etree.SubElement(body, f"{{{ns}}}{action_name}Response")

        if return_values:
            for key, value in return_values.items():
                elem = etree.SubElement(response, f"{{{ns}}}{key}")
                if value is not None:
                    elem.text = str(value)

        return '<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(root, encoding="unicode")

    @staticmethod
    def _upnp_error_detail(error_code: int, error_description: str) -> etree.Element:
        detail = etree.Element("detail")
        upnp_error = etree.SubElement(detail, f"{{{NS_UPNP_ERR}}}UPnPError")
        ec = etree.SubElement(upnp_error, "errorCode")
        ec.text = str(error_code)
        ed = etree.SubElement(upnp_error, "errorDescription")
        ed.text = error_description
        return detail

    @staticmethod
    def build_error_response(
        fault_string: str,
        error_code: Optional[int] = None,
    ) -> str:
        root = etree.Element(f"{{{NS_SOAP_ENV}}}Envelope")
        root.set(f"{{{NS_SOAP_ENC}}}encodingStyle", NS_SOAP_ENC)

        body = etree.SubElement(root, f"{{{NS_SOAP_ENV}}}Body")
        fault = etree.SubElement(body, f"{{{NS_SOAP_ENV}}}Fault")

        code = etree.SubElement(fault, "faultcode")
        string = etree.SubElement(fault, "faultstring")

        if error_code is not None:
            code.text = f"{{{NS_SOAP_ENV}}}Client"
            string.text = "UPnPError"
            fault.append(SoapBodyParser._upnp_error_detail(error_code, fault_string))
        else:
            code.text = "s:Client"
            string.text = fault_string

        return '<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(root, encoding="unicode")

    @staticmethod
    def validate_port(port: int) -> bool:
        return PORT_MIN <= port <= PORT_MAX
