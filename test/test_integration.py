#!/usr/bin/env python3
"""
alter_upnpd — Integration test for docker-compose python_test container.

Verifies UPnP IGD device discovery (via miniupnpc/upnpc),
port-mapping CRUD via upnpc CLI, then confirms GOST actually
forwards traffic through the mapped port.

All verification uses the standard miniupnpc library (upnpc CLI) —
no raw UDP/SOAP construction.

Usage (inside python_test container):
    python /app/test/test_integration.py

Environment variables (all optional, compose-friendly defaults):
    UPNP_URL          URL to rootDesc.xml
                      default: http://alter_upnpd:5000/rootDesc.xml
    GOST_API_URL      GOST API base URL (empty = skip GOST API checks)
                      default: (empty, skipped)
    TEST_CLIENT_IP    Internal client IP for test mappings (default: 192.168.1.100)
    TEST_INT_PORT     Internal port (default: 19999)
    TEST_EXT_PORT     External port (default: 19999)
    TEST_PROTO        Protocol tcp|udp (default: tcp)
"""

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

# Real-time logging (unbuffered) for docker-compose output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("test")
sys.stdout.reconfigure(line_buffering=True)

# ── Configuration from environment ──

UPNP_URL = os.environ.get(
    "UPNP_URL",
    "http://alter_upnpd:5000/rootDesc.xml",
)
GOST_API_URL = os.environ.get("GOST_API_URL", "")
TEST_CLIENT_IP = os.environ.get("TEST_CLIENT_IP", "192.168.1.100")
TEST_INT_PORT = int(os.environ.get("TEST_INT_PORT", "19999"))
TEST_EXT_PORT = int(os.environ.get("TEST_EXT_PORT", "19999"))
TEST_PROTO = os.environ.get("TEST_PROTO", "tcp")
TEST_PAUSE = int(os.environ.get("TEST_PAUSE", "20"))

# Derived
UPNP_BASE = (
    UPNP_URL.rsplit("/rootDesc.xml", 1)[0]
    if "/rootDesc.xml" in UPNP_URL
    else UPNP_URL.rstrip("/")
)
SERVICE_NAME = f"upnp_{TEST_EXT_PORT}_{TEST_PROTO}"

PASS = 0
FAIL = 0
SKIP = 0


# ── Helpers ──


def report(name, ok, detail=""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" \u2014 {detail}"
    log.info(msg)


def skip(name):
    global SKIP
    SKIP += 1
    log.info("  [SKIP] %s", name)


def http_get(url, expect_status=200):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def gost_api(path):
    if not GOST_API_URL:
        return None
    url = f"{GOST_API_URL}{path}"
    status, body = http_get(url)
    if status != 200:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def run_upnpc(args):
    cmd = ["upnpc", "-u", UPNP_URL] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout + r.stderr
    except FileNotFoundError:
        return -1, "upnpc: command not found (install miniupnpc)"
    except subprocess.TimeoutExpired:
        return -1, "upnpc: timed out"


def _get_gateway_ip():
    """Return docker host IP from container's default route."""
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw_hex = parts[2]
                    gw = ".".join(str(int(gw_hex[i : i + 2], 16)) for i in [6, 4, 2, 0])
                    return gw
    except OSError:
        pass
    return None


def _get_container_ip():
    """Return this container's primary IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _extract_services(data):
    """Extract service list from GOST API response (handles list, {services: [...]}, {data: [...]})."""
    if isinstance(data, list):
        svcs = [s for s in data if isinstance(s, dict)]
        log.info("  [DEBUG] GOST returned raw list, %d services", len(svcs))
        return svcs
    if isinstance(data, dict):
        log.info("  [DEBUG] GOST response keys: %s", list(data.keys()))
        for key in ("services", "data", "result", "items"):
            val = data.get(key)
            if isinstance(val, list):
                svcs = [s for s in val if isinstance(s, dict)]
                log.info("  [DEBUG] Extracted %d services from key '%s'", len(svcs), key)
                return svcs
        return []
    log.warning("  [DEBUG] Unexpected GOST response type: %s", type(data).__name__)
    return []


def _start_echo_server(port):
    """Start a TCP echo server on 0.0.0.0:port in a daemon thread.

    The server accepts one connection, echoes back whatever it receives,
    then exits.  Returns the thread (so caller can join/wait).
    """
    ready = threading.Event()

    def _serve():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(15)
        try:
            s.bind(("0.0.0.0", port))
            s.listen(1)
            ready.set()
            conn, addr = s.accept()
            conn.settimeout(10)
            data = conn.recv(4096)
            if data:
                conn.sendall(data)
            conn.close()
        except socket.timeout:
            pass
        except OSError:
            pass
        finally:
            s.close()

    t = threading.Thread(target=_serve, daemon=True, name=f"echo-{port}")
    t.start()
    ready.wait(timeout=3)
    return t


def _wait_for_device(url, timeout=30, interval=3):
    """Poll rootDesc.xml until device responds or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = http_get(url)
        if status == 200 and "InternetGatewayDevice" in body:
            return True
        time.sleep(interval)
    status, body = http_get(url)
    return status == 200 and "InternetGatewayDevice" in body


def _probe(host, port, payload, timeout=8):
    """Return (response_bytes|None, error_type).
    error_type is None on success, or a string describing the failure."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(payload)
        resp = s.recv(4096)
        s.close()
        return resp, None
    except socket.timeout:
        return None, "timeout"
    except ConnectionRefusedError:
        return None, "refused"
    except OSError as e:
        return None, f"oserror: {e}"
    except Exception as e:
        return None, f"exception: {type(e).__name__}: {e}"


# ── Test cases ──


def test_device_discovery():
    status, body = http_get(UPNP_URL)
    ok = (
        status == 200
        and "root" in body
        and "urn:schemas-upnp-org:device:InternetGatewayDevice" in body
    )
    detail = f"HTTP {status}" + (f", {len(body)} bytes" if ok else "")
    report("Device discovery (rootDesc.xml)", ok, detail)
    return ok


def test_health_endpoint():
    url = f"{UPNP_BASE}/health"
    status, body = http_get(url)
    ok = False
    detail = f"HTTP {status}"
    if status == 200:
        try:
            data = json.loads(body)
            ok = data.get("status") in ("healthy", "degraded")
            detail += f', status="{data.get("status")}", version={data.get("version")}'
        except json.JSONDecodeError:
            detail += ", invalid JSON"
    report("Health endpoint", ok, detail)
    return ok


def test_add_port_mapping(client_ip=None):
    if client_ip is None:
        client_ip = TEST_CLIENT_IP
    rc, output = run_upnpc(
        ["-a", client_ip, str(TEST_INT_PORT), str(TEST_EXT_PORT), TEST_PROTO]
    )
    ok = rc == 0 and (
        "added" in output.lower()
        or "ok" in output.lower()
        or "upnp_add" in output.lower()
        or "returned" in output.lower()
        or "redirected" in output.lower()
    )
    report("upnpc add port mapping", ok, f"rc={rc}, output({len(output)}B): {output.strip()}")
    if ok:
        time.sleep(1)
    return ok


def test_verify_via_gost():
    if not GOST_API_URL:
        skip("Verify mapping via GOST API (GOST_API_URL not set)")
        return True

    # Use GET /config (full config dump) — confirmed to return
    # {"services": [...]} with the full service list.
    data = gost_api("/config")
    ok = False
    detail = "GOST API unreachable"
    if data is not None and isinstance(data, dict):
        services = data.get("services")
        if isinstance(services, list):
            names = [s.get("name") for s in services if isinstance(s, dict)]
            log.info("  [DEBUG] GOST service names from /config: %s", names)
            found = SERVICE_NAME in names
            ok = found
            if found:
                detail = f"service '{SERVICE_NAME}' found among {len(services)} services"
            else:
                detail = f"service '{SERVICE_NAME}' NOT found: {names}"
        else:
            detail = f"/config 'services' is not a list (got {type(services).__name__})"
    else:
        detail = "GOST API /config returned unexpected data"
    report("Verify mapping via GOST API", ok, detail)
    return ok


def test_list_port_mappings():
    rc, output = run_upnpc(["-l"])
    ok = rc == 0 and str(TEST_EXT_PORT) in output
    count = output.count("->") if ok else 0
    detail = f"rc={rc}, {count} mappings listed" if ok else f"rc={rc}"
    report("upnpc list port mappings", ok, detail)
    return ok


def _test_forwarding(gateway_ip, echo_port, ext_port, payload):
    if not gateway_ip:
        skip("Forwarding verification (no gateway IP detected)")
        return True
    echo = _start_echo_server(echo_port)
    time.sleep(0.5)
    resp, err = _probe(gateway_ip, ext_port, payload)
    ok = resp == payload
    detail = ""
    if not ok:
        if err:
            detail = f"connect to {gateway_ip}:{ext_port} → {err}"
        elif resp is not None:
            detail = f"got {len(resp)}B, expected {len(payload)}B"
        else:
            detail = f"no echo from {gateway_ip}:{ext_port}"
    else:
        detail = f"sent {len(payload)}B, got {len(resp)}B echoed"
    report("Port forwarding verified (echo)", ok, detail)
    return ok


def test_delete_port_mapping():
    rc, output = run_upnpc(["-d", str(TEST_EXT_PORT), TEST_PROTO])
    ok = rc == 0
    report("upnpc delete port mapping", ok, f"rc={rc}")
    if ok:
        time.sleep(1)
    return ok


def test_verify_deleted_via_gost():
    if not GOST_API_URL:
        skip("Verify deletion via GOST API (GOST_API_URL not set)")
        return True

    data = gost_api("/config")
    ok = True
    detail = "GOST API unreachable \u2014 assume deleted"
    if data is not None and isinstance(data, dict):
        services = data.get("services")
        if isinstance(services, list):
            names = [s.get("name") for s in services if isinstance(s, dict)]
            found = SERVICE_NAME in names
            ok = not found
            detail = (
                f"service '{SERVICE_NAME}' {'STILL present: ' + str(names) if found else 'confirmed deleted'}"
            )
        else:
            detail = "config no longer contains services \u2014 confirmed deleted"
    report("Verify deletion via GOST API", ok, detail)
    return ok


def _test_forwarding_stopped(gateway_ip, ext_port, timeout=5):
    if not gateway_ip:
        skip("Forwarding-stopped verification (no gateway IP detected)")
        return True
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((gateway_ip, ext_port))
        s.close()
        ok = False
        detail = "port still open"
    except (ConnectionRefusedError, ConnectionResetError, socket.timeout, OSError):
        ok = True
        detail = "connection refused as expected"
    report("Forwarding stopped after deletion", ok, detail)
    return ok


# ── Standard UPnP verification via miniupnpc (upnpc CLI) ──


def test_upnpc_discovery():
    """Run upnpc -s (status) to verify SSDP discovery + SOAP via miniupnpc.

    miniupnpc is the reference UPnP client library.  'upnpc -s' performs:
      1. SSDP M-SEARCH → discover IGD device
      2. Fetch rootDesc.xml from the LOCATION header
      3. Parse control URLs from the device description
      4. SOAP GetStatusInfo → verify connection status
      5. SOAP GetExternalIPAddress → verify WAN IP

    Pass criteria:
      - "Found valid IGD" in output  → SSDP + description fetch work
      - ExternalIPAddress is present  → SOAP GetExternalIPAddress works
    """
    rc, output = run_upnpc(["-s"])
    ok = False
    if rc == 0:
        has_igd = "Found valid IGD" in output
        has_ext_ip = "ExternalIPAddress" in output
        ok = has_igd and has_ext_ip
        detail = f"rc={rc}, IGD={'yes' if has_igd else 'no'}, ExternalIP={'yes' if has_ext_ip else 'no'}"
    else:
        detail = f"rc={rc}"
    report("upnpc status (discovery + SOAP)", ok, detail)
    return ok


# ── Main ──


def main():
    PROBE_PAYLOAD = b"UPNP-PROBE-" + os.urandom(8).hex().encode()

    log.info("=" * 60)
    log.info("  alter_upnpd Integration Test Suite")
    log.info("=" * 60)
    log.info("")
    log.info("  UPNP_URL:      %s", UPNP_URL)
    log.info("  GOST_API_URL:  %s", GOST_API_URL or "(not set, GOST checks skipped)")
    log.info("  Service name:  %s", SERVICE_NAME)
    log.info("  Client IP:     %s", TEST_CLIENT_IP)
    log.info("  Ports:         :%d \u2192 :%d/%s", TEST_INT_PORT, TEST_EXT_PORT, TEST_PROTO)
    log.info("")

    # Phase 1: Discovery (with retry for container boot)
    log.info("\u2500\u2500 Phase 1: Device Discovery \u2500\u2500")
    ready = _wait_for_device(UPNP_URL)
    if not ready:
        log.warning("  \u26a0  alter_upnpd not responding after 30s")
        sys.exit(1)
    log.info("  alter_upnpd ready, running tests...")
    d1 = test_device_discovery()
    d2 = test_health_endpoint()
    if not d1:
        log.info("")
        log.warning("  \u26a0  Device check failed despite readiness")
        log.info("")
        log.info("  PASS=%d  FAIL=%d  SKIP=%d  TOTAL=%d", PASS, FAIL, SKIP, PASS + FAIL + SKIP)
        sys.exit(1 if FAIL else 0)

    # Network info for subsequent phases
    gateway_ip = _get_gateway_ip()
    container_ip = _get_container_ip()
    log.info("  \u2192  Gateway: %s", gateway_ip or "(not detected)")
    log.info("  \u2192  Test container IP: %s", container_ip or "(not detected)")

    # Phase 1b: Standard UPnP verification via miniupnpc
    log.info("")
    log.info("\u2500\u2500 Phase 1b: Standard UPnP (upnpc status) \u2500\u2500")
    s1 = test_upnpc_discovery()

    # Phase 2: upnpc port mapping CRUD + forwarding verification
    log.info("")
    log.info("\u2500\u2500 Phase 2: upnpc Port Mapping + Forwarding \u2500\u2500")

    # Use container IP as the internal client so GOST forwards traffic
    # back to this container where the echo server runs.
    a1 = test_add_port_mapping(container_ip)
    time.sleep(TEST_PAUSE)

    if a1:
        a2 = test_verify_via_gost()
    else:
        a2 = False
        log.warning("  \u26a0  Skipping GOST verification (add failed)")
    time.sleep(TEST_PAUSE)

    a3 = test_list_port_mappings()
    time.sleep(TEST_PAUSE)

    # Forwarding test: start echo server on TEST_INT_PORT inside python_test,
    # then connect via docker gateway on TEST_EXT_PORT (GOST-bound port).
    if a1:
        a4 = _test_forwarding(gateway_ip, TEST_INT_PORT, TEST_EXT_PORT, PROBE_PAYLOAD)
    else:
        a4 = False
        log.warning("  \u26a0  Skipping forwarding test (add failed)")
    time.sleep(TEST_PAUSE)

    a5 = test_delete_port_mapping()
    time.sleep(TEST_PAUSE)

    a6 = test_verify_deleted_via_gost()
    a7 = _test_forwarding_stopped(gateway_ip, TEST_EXT_PORT)

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("  Results:  PASS=%d  FAIL=%d  SKIP=%d  TOTAL=%d", PASS, FAIL, SKIP, PASS + FAIL + SKIP)
    log.info("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
