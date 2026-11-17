"""Standalone read-only PythonFunctionTool for general Defender for Cloud evidence."""

import csv
import html
import io
import json
import math
import os
import re
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from uuid import UUID, uuid4

SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
TENANT_ID = "<YOUR_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_AGENT_CLIENT_ID>"
ARM_ORIGIN = "https://management.azure.com"
ARC_API_VERSION = "2022-12-27"
PRICING_API_VERSION = "2024-01-01"
ARG_API_VERSION = "2022-10-01"
MAX_PAGES = 200
MAX_SOURCE_ROWS = 50000
MAX_MACHINES = 1000

# BEGIN STANDALONE REPORT HELPERS
# Kept identical in both files: each deployed Python tool is self-contained.
OUTPUT_DIRECTORY = Path("arc-defender-reports")
TRANSPORT_BUDGET_BYTES = 3500
MAX_ARTIFACT_BYTES = 4_800_000
MAX_DECODED_NODES = 2_000_000
MAX_DECODED_STRING_UNITS = 64_000_000
LOGO_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAggAAABUCAYAAADnL8/GAAAQWUlEQVR4nO3dC7Rt1RgH8P9BL1KpW2bo4RV5P0OKIjU9eol7"
    "SWlgJnnTS1So9CB6jBrITF495UquzK7yVl7VQBIKeTWTKJSKusbX+E5jW3vOtdfee+291ln7/xvjjLp7n732XuecudY3v/nN"
    "OedWrFgBIiIiol73+r9/ERERETFAICIiohRmEIiIiKgPAwQiIiLqwwCBiIiI+jBAICIioj4MEIiIiKgPAwQiIiLqwwCBiIiI"
    "+twHNTDOLpjlGKMPc01/BiIiorabG3Wp5YUUFOQwWCAiIqpxiKELwUGXzoOIiKjRDEKXb6jMJhAREY2QQehycDAL50dERFR7"
    "gDArN89ZOU8iIqJBOM2RiIiIhg8QZq1XPWvnS0RENHSAMKs3y1k9byIionkcYiAiIqI+DBCIiIioeoAw62n2WT9/IiKabcwg"
    "EBERUR8GCERERNSHAQIRERH1YYBAREREfRggEBERUR8GCERERNTnPpiw6AOmzTg79fckIiLqEmYQiIiIqA8DBCIiIpr+EAMN"
    "ZpydA/BkAC8AsDWAhwBYF8DaAP4L4F8A/gzg1wB+COCr0YefVf3ZGmcfBGA7/XoUgPUALAJwC4AbAFwL4CIAIfrwk2F+Z8ZZ"
    "+Wz3K/mWf8r7RR9uG+KYuwH47IBv2z368LkRPo+4C8A/ANwM4JcALgWwNPrw46qfsfCeOwD4Usm3bBp9uGrIY+bO4zIAm0Uf"
    "7qx4nHMB7Fh4+M7owz1t3zj7bQBbJl5+O4ANog83DHiPAwAclXjqSgCPjz7Iz7uOc19tmL+jptrEgPfdSNu4fD0GwDr6vvcF"
    "8G8ANwH4A4BfaVu/MPrwq4VyftQtDBCaDwxeDuC9erHI/Y5W1cb9BAC7ADjaOLtx9OHaAcffGMD7AeyWyRatDOABADbR4OQo"
    "4+w3ARwYffh+PWeJ+wN4IYAvDvGaJZgs+VmspV9ywd5Wztk4+yMAe0UfLh/yePLzLbMrgENQj6cA2AfAB1GfD8iNIvH4KgBe"
    "r88nGWfvDeCNmacPGzY4mLSm2oRx9jkA3qN/azmr65d0EJ4FYA997YnRh7e0+fyomxoJEOosImyiCLIO2pDPAfDUEQ8xN+D4"
    "ctE+Vi8Iw9gKwCXG2Q8BeFdNF/glVQME4+xaAy6ik/R06bUZZxdHH6p+3jUAbD/g215ZY4Ag3meclYzH1XUcLPpwgXFWsidP"
    "Szy9t3H26OiDZLJSdgKwYeLxXwA4Gy3SRJswzq6j2TAJkkf1gIrv1aY2Tx3AGoQGGGclvfjjMYKDsmPPGWePB3DSCBeKXvtJ"
    "2t04u1INH2t746ykUKvYeczPXUfQfIZxNpfRKXqZZnjKPMI4K8FHXVYDcDLqdUTm8Qfr7yTnrW3PHjTVJvR3ftmYwcFCbfPU"
    "AQwQpkwvGufr2OMkHFxy0R6WjF1/pIbjSHDwkoaHFz4F4BT973kA/lTyvauU3DCrDC/clhlmqNPWxllX4/GkVuGKzHPJ9LZx"
    "9okAJHVeJPUWZ6E9pt4mjLOPlfqBTHZlFto8dQADhCnSwqFzB/Q4fwrgUAAv0pTvfPGiRPcynpLtlRlnt9V6hhwpcjwIwPMB"
    "yMVdMhlSYFZWQPdm46zUSQzjklFu/MbZRfrZeg1bD5Czd/TBRR9eE32Qi+AGABZrEWXKi3X4oOzzSu/6uYmnUgWLS4yzdbe3"
    "Dxln16/jQNEH2d78yMzTWxpnn7RAswdTbxPGWSkIXAag7O/nQq3veIwWI0tR5oO0xuS1AD4J4O9tPD+aHSxSnK7j9SKQIpXF"
    "b4g+LC25oBxjnN1Qi8buShSLSYoxdxOS8cWDog93FB7/pnFWxi0PB7B/5rVH6ph3pcp5HX+WIqteLzLO3j/6kLshQwswi3+T"
    "V2mQVCu9IX7eOCsp2b7ZEPo5ttBsT86uiZ+3zDb5WiIgWl/Her+O+ki9xon6c6vDWVrg9ohMFuF1hbF1qa0oklkhZ6IFGmwT"
    "0gOXGqMUyVy9KvrwrcRztwK4ToPiU42zewN4deb30bY2Tx3EAGFKtAeWu5D/Vm4e0YffDzqOfs/uiadekbuQyAUr+rB/yTH/"
    "I70K4+zqmYr0h+vNIHUjTfl54jHJmsh0wNNKXrckMc1OekCTJDfFj2n1eJFUkw87vBA0mMsFFOMECHckxphfapzduWpRZRm5"
    "GRhnZbqiTzy9q3F2/+jDjfrv12stRNHhbckeNNEmdNglN5x0jWRjog8SBAykN/bU76KNbZ46iEMM03NAZuaB3AR3qhIcDJCb"
    "aiY9ugOH+Iy5i9cwY+iSDfnjMMMMxtkHJtL1357036hW58u881wPPck4+ziddlp0jk4/lbUVinbRjMWoZOjir4nHTzLOrol6"
    "fCbz85AAz/X0XKV3WyTz9c9AezTRJt5V0s53rBocLMA2Tx3EAGEK9IIqC5akfCL68NMxjy9rDWyWefrYRIoxKfogC9ScWjIO"
    "XTXjJDfBLyQe306nMaa8PPH3ePaUZjTkZlj8reQ1qSzOTT3Zg9T5rzVmRbuke1O9wvU1nTw27VnmjvVG/VveWWs4UtmDVqSk"
    "m2gT+v+5Odw++pDKrHWlzVMHMUCYjs1K5jJLentcUkmea8iy1sIwpMI/ZfVMjzllpUxPcmWdN48K2QXp2UvafKJTrrTQUBZL"
    "yg39pF4zlxl/P09vsLkAAZnXVbVq9OHUzDCFM85KjUMdPgHg+sTjG2qR256J52Qo6HS0RxNtQupucgHwR1GvtrV56iAGCNOR"
    "K7KLNfUqZCnVlKt7xoyrkmxGbgy5asX8StGHH+iY68BhBuOsjPU/u/Dw1/SzT/pvNLcioRRTfifz3FaZHvQ9F2ZdHveKzJoQ"
    "qXqHKqT3Pj/+LwVtvSRoOdk4O2hNhoF0OePcVDepI9mqzdmDBtuE1B+kXF9n9qClbZ46iOmj6ZB9FVJ+U9PxZXpgStlc/6To"
    "w7+NszdnMh659ymav6mfqcvL9tpGKuALF7HFiXHbiazCp1MNpQJf1qN4Z2Ja5bxTS9K0u2UCiuWJgEFqFYrDGTuNWPx1988o"
    "+nCNcVZWZjym8PwjZZVFHQcf10d1fFqm4PV6XWLY5+oBxadNaKJNyPTGyu3cOPt2XfmwimujDxu3uM1TBzGD0GyAMHCec0W5"
    "RZfKphSWkY2MUgZtgjRv/mZ/eiYofemArMIdul5EneQiKFMbpZf7FwBfKQkOYm5uuXF2lcxslC9HH6QQrVfdwwy9QdRxAGTv"
    "iKJ9MmsWDEWno55QsV6jbdmDptrEuiPUsnSlzVMHMUCYjvnUcNGoqeaiO2o+/ihFe32iD7KbX6oAc0lhT4pisdUF0Qcp+GuC"
    "vK8teX/Zd2HNKuO+0QcZYkjtxLetLgo1Mr0hS29+vuahNwA7RYsJx3VChRvONS3MHjTVJnJBUtVlxhd8m6duYYAwHbkxQSmQ"
    "q0NuO14z7IF0HfZcQWXptr8ZqWLFrXRaY27qY1PL9Mq6+ZsP2P42NbwgW+jmdg1LZRHkJj72SnW65Xdqm+Wn6PCJWDHG8f9e"
    "obju8JKNnJrURJtITUEV83/rdWpzm6eOYIAwHTeUbOKTW1lxGJIST3nUCPPjn1BSm5Ks6h/gzMRN6t5a7IZEuv62kqrqSblc"
    "e+PPjD7IKpBJxtm1M9MUJQ17qwxhFL9K5qOPM5uhl6yGJ5maovcbZx+qs0HG8WEZninJHrR1IZ0m2oQMXaU8OvOesv7ADwpf"
    "l3egzVNHsEhxej3TnFdneoHDuLhkzFoK4j49xLFeXFIkNXRRZfThd8ZZ2Zth8+L7GGe/nNhi+PwByzGP6jhNAa/QG570jmVB"
    "o4ujD7mLbdHiGtdl2MI4u0H0IbdIUyVSSKmbNn23EPCvpkMEY9W5RB/+YpyVgtE9Ek+f0tLsQVNtIlUTAv297KDbPt8j+nBW"
    "MVumM3r+sJDbPHUHMwjT8X1NQyNTVDZWClLHunOrob2j6mInxlnpCe+Vefqi0T9hcphhSy0SnJvS8MKB0Yd9ow/7RR8OiT7I"
    "YjJLhwgOcsMLo5rTpXLHFn24RPdkKJIdNJ9Rw1vk6jFymYXGNdQmLi0Zs9+/zkWHFkCbpw5ggDAFuniOVM2nLNJNg8atFs4t"
    "cStzs2VKXBUy5So35HEyRnd2ooBrbd21rtetugte62gxZTELMq46l7J9N4DfJR7fBLNrqm1C96DIzb55XGJaKjrc5qkDGCBM"
    "zxElBWPSm/5elelpxtlNjbNn6a6OxQV/cj26g42zh+Z6FbK4jnH2xMwKeWK5Lnw0cpo60xt5XmKqYHEBoLZ4VWaNfek1nlLh"
    "qzgFUjxJfp91fLjowy0lPcFZ1USbkJ1Wc8MubzPOymJWdU0dbG2bp25opAYh+lzBd3dJZbzc2EvSyhL1X2acXa5bDF+psx9W"
    "1QVYnqr7OcxPCTygcPzrjbNH60I5KQdL5bxx9lMAfqhp40W6guEeJdvTygVoX9TT25G968s0NXuhaoCQcnD04auDXiz1Bpnz"
    "f+UQvb1S0YflxtlPZ+oFZk4TbULG7I2zsnz6mzOvlRvyjsZZWc56uRZ6yiJFa+isph3afH40W1ikOF176bLLuWVS5zQIyG3s"
    "NMhhOuac2xDo0SMURO6p0+nGtVSnzOWWApbCxIE32iYYZyU42zRzIf1GxcMsm3SAoN6hGwZNYmpd036uM0PKXBd9kIxck21i"
    "Hw34ez9Hr/V0hdHiKqNda/O0wHGIYYqiD7Ja2Y4Vq5RHOf5dOq6dq3AehlyID4g+nFbjuUtmJOdLugdAG+WKE78+xGdeVjLV"
    "Nbcr36hrF+R6rwvdwwA8fMCXTO1stE3oEt07D5i91Pk2TwsfA4Qpiz78Uqf2fWdCx79Jd9zLbeFahWwBu0v0IbeRUd1FVa0d"
    "XtAVCXPDQrnC0z7RB5lP/osJr4kw/17n6E6Y1FCb0L1GpKj14zX9Em5foG2eFjAGCA3Qor2tdQ2Eq0Y4xE9K1k6/uwcTfZAZ"
    "AtvoFMuqpOdzkmz6E32YxA1mWeZz35TY6KgttilZna4sIzJMFmGJbiJVpzeVTE+cOU20CdmbI/rwBh3zP2/EVS2v1RkqpdNV"
    "W9zmaQGbeA2CcTIcSpm19D9rnD1NexrP1z3eH6KFRGtq471Fd2iTHfOkqvjC6EOl1daiDzJz4CIdQ7c6a2ADHQOVhXRu1FUe"
    "ZU71BbJcsAYvEyHpeOPsuRoY9Tq3ZOfEthYnXhl9kIv3sAHCfpktdbeuc9559OE646wUmvm6jtkFTbSJ6MPFWpi4kbbz5+rq"
    "hevodN9VtQf/T23rkmn6mc4kuKLt50fdNbdiRTqorVAM1HnRh9S0NiIios7jEAMRERH1YYBAREREfRggEBERUR8GCERERNSH"
    "AQIRERFVDxBmvYJ/1s+fiIhmGzMIRERE1IcBAhEREQ0XIMxqmn1Wz5uIiKhyBmHWbpazdr5EREQpHGIgIiKi0QKEWelVz8p5"
    "EhER1ZZB6PrNs+vnR0REVMtujmW6tNMjAwMiIqKaahC6clPtynkQERG1IoOwkDMKDAqIiIimFCAQERFRt3CaIxEREfVhgEBE"
    "RER9GCAQERFRHwYIRERE1IcBAhEREfVhgEBERER9GCAQERFRHwYIREREhKL/AetR3nSEuN+CAAAAAElFTkSuQmCC"
)
PROVIDERS = ("all", "onprem", "gcp", "azure", "aws", "unknown")
ENVIRONMENTS = ("all", "Production", "Preproduction", "Dev", "DMZ", "Backup", "Unknown")
CONNECTIVITY = ("all", "Connected", "Disconnected", "Expired", "Unknown")
MDE_FILTERS = ("all", "failed-extension", "missing-extension", "unverified", "healthy", "unhealthy")
SEVERITIES = ("all", "Critical", "High", "Medium", "Low", "Informational", "Unknown")
VIEWS = (
    "inventory", "findings", "actions", "resource_details", "posture",
    "attack_paths", "software", "controls", "compliance", "vulnerabilities",
)
RISKS = ("all", "Critical", "High", "Medium", "Low", "Not evaluated", "Unknown")
FINDING_STATUSES = (
    "all", "Unhealthy", "Healthy", "NotApplicable", "Active", "Resolved", "Dismissed", "Unknown",
)
ASSOCIATIONS = ("all", "arc", "context")
SEVERITY_ORDER = {
    "Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Informational": 4, "Unknown": 5,
}
CAPABILITY_MATRIX = [
    {
        "feature": "MDE integration / agent-based vulnerability assessment",
        "scope": "P1 and P2; supported OS, onboarding and healthy endpoint telemetry required.",
        "caveat": "An extension in Succeeded state is not a verified healthy MDE sensor.",
    },
    {
        "feature": "Agentless machine scanning",
        "scope": "P2 in supported Azure / AWS / GCP environments, with platform prerequisites.",
        "caveat": "Not generic agentless scanning of standalone on-premises Arc servers.",
    },
    {
        "feature": "Just-in-time VM access",
        "scope": "Supported Azure and AWS VM scenarios.",
        "caveat": "Do not promise JIT for on-premises or GCP Arc servers.",
    },
    {
        "feature": "OS baselines / file integrity monitoring",
        "scope": "Validate the current support matrix, OS and required extensions / MDE configuration.",
        "caveat": "Buying P2 alone does not verify feature readiness or correct configuration.",
    },
    {
        "feature": "Defender CSPM / Defender for SQL",
        "scope": "Separate plans and licensing; SQL coverage also needs appropriate SQL onboarding.",
        "caveat": "Servers P2 does not include every cloud posture or database protection feature.",
    },
    {
        "feature": "Secure Score / regulatory compliance / attack paths",
        "scope": "Collected as explicitly labeled subscription context; CSPM/platform prerequisites apply.",
        "caveat": "Not Arc-only Secure Score, automatic certification or proof of an Arc attack path.",
    },
]
DEFENDER_REFERENCE = "https://learn.microsoft.com/azure/defender-for-cloud/defender-for-servers-overview"


class EvidenceError(RuntimeError):
    def __init__(self, code, message, source="", http_status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.http_status = http_status

    def as_dict(self):
        result = {"code": self.code, "message": self.message, "source": self.source}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value, maximum=240):
    if not isinstance(value, (str, int, float, bool)):
        return ""
    return "".join(c for c in str(value) if c >= " " or c in "\n\t")[:maximum]


def _get(mapping, key, default=None):
    if not isinstance(mapping, dict):
        return default
    target = key.casefold()
    for actual, value in mapping.items():
        if isinstance(actual, str) and actual.casefold() == target:
            return value
    return default


def _enum(value, choices, field):
    if not isinstance(value, str):
        raise EvidenceError("invalid_parameter", f"{field} must be a string.", "parameters")
    for choice in choices:
        if choice.casefold() == value.casefold():
            return choice
    raise EvidenceError(
        "invalid_parameter", f"{field} must be one of: {', '.join(choices)}.", "parameters"
    )


def _validate_parameters(operation, view, provider, environment, resource_group,
                         server_name, connectivity, mde, severity, limit, offset,
                         risk="all", status="all", association="all", resource_type=""):
    params = {
        "operation": _enum(operation, ("report", "query"), "operation"),
        "view": _enum(view, VIEWS, "view"),
        "provider": _enum(provider, PROVIDERS, "provider"),
        "environment": _enum(environment, ENVIRONMENTS, "environment"),
        "connectivity": _enum(connectivity, CONNECTIVITY, "connectivity"),
        "mde": _enum(mde, MDE_FILTERS, "mde"),
        "severity": _enum(severity, SEVERITIES, "severity"),
        "risk": _enum(risk, RISKS, "risk"),
        "status": _enum(status, FINDING_STATUSES, "status"),
        "association": _enum(association, ASSOCIATIONS, "association"),
    }
    if not isinstance(resource_group, str) or len(resource_group) > 90:
        raise EvidenceError("invalid_parameter", "resource_group must be at most 90 characters.", "parameters")
    if resource_group and not re.fullmatch(r"[\w.()\-]+", resource_group, flags=re.UNICODE):
        raise EvidenceError("invalid_parameter", "resource_group contains invalid characters.", "parameters")
    if not isinstance(server_name, str) or len(server_name) > 80:
        raise EvidenceError("invalid_parameter", "server_name must be at most 80 characters.", "parameters")
    if any(ord(c) < 32 for c in server_name):
        raise EvidenceError("invalid_parameter", "server_name must not contain control characters.", "parameters")
    if not isinstance(resource_type, str) or len(resource_type) > 180 or (
        resource_type and not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]+(?:/[A-Za-z0-9_-]+)*", resource_type)
    ):
        raise EvidenceError("invalid_parameter", "resource_type must be an exact observed provider/type or native kind.", "parameters")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if type(offset) is not int or not 0 <= offset <= 50000:
        raise EvidenceError("invalid_parameter", "offset must be an integer from 0 to 50000.", "parameters")
    params.update({
        "resource_group": resource_group, "server_name": server_name,
        "limit": limit, "offset": offset, "resource_type": resource_type.casefold(),
    })
    if params["operation"] == "query":
        context_view = params["view"] in ("posture", "controls", "compliance")
        if context_view and any(params[key] not in ("all", "") for key in (
            "provider", "environment", "resource_group", "server_name", "connectivity",
            "mde", "risk", "status", "severity", "association", "resource_type",
        )):
            raise EvidenceError(
                "invalid_parameter", "Subscription posture/controls/compliance views do not accept Arc filters.",
                "parameters",
            )
        if params["association"] != "all" and params["view"] not in ("attack_paths", "software"):
            raise EvidenceError("invalid_parameter", "association is for attack_paths or software only.", "parameters")
        if params["view"] in ("software", "attack_paths") and (
            params["severity"] != "all" or params["status"] != "all"
            or params["view"] == "software" and params["risk"] != "all"
        ):
            raise EvidenceError(
                "invalid_parameter", "software has no recommendation risk/status; attack_paths accepts native risk only.",
                "parameters",
            )
    if params["operation"] == "report" and (
        params["view"] != "inventory" or params["provider"] != "all"
        or params["environment"] != "all" or params["connectivity"] != "all"
        or params["mde"] != "all" or params["severity"] != "all"
        or params["risk"] != "all" or params["status"] != "all" or params["association"] != "all"
        or resource_group or server_name or resource_type or offset != 0 or limit != 25
    ):
        raise EvidenceError(
            "invalid_parameter",
            "report always exports the complete configured scope. Use query for filters, views and paging.",
            "parameters",
        )
    return params


def _plain_text(value, maximum=8000):
    if not isinstance(value, str):
        return ""
    return _text(html.unescape(re.sub(r"<[^>]*>", " ", value)), maximum).strip()


def _safe_link(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value) or len(value) > 8000:
        return ""
    if value.startswith("portal.azure.com/"):
        value = "https://" + value
    if not re.match(r"^https://(?:portal\.azure\.com|learn\.microsoft\.com|support\.microsoft\.com)/", value):
        return ""
    if re.search(r"(?:[?&/])(?:token|secret|password|sig|code)=", value, re.IGNORECASE):
        return ""
    return value


def _native_risk(value):
    if value is None or value == "":
        return "Not evaluated"
    return next((r for r in RISKS[1:] if r.casefold() == str(value).casefold()), "Unknown")


def _is_actionable(finding):
    return finding["status"].casefold() in ("unhealthy", "active", "new", "inprogress")


def _counts(rows, key):
    return dict(sorted(Counter(row.get(key, "Unknown") for row in rows).items()))


def _group_recommendations(findings):
    groups = {}
    for finding in findings:
        if finding["category"] != "Recommendation":
            continue
        key = (finding.get("recommendation_id", finding["title"]), finding["risk_level"], finding["status"])
        group = groups.setdefault(key, {
            "recommendation_id": key[0], "title": finding["title"], "risk_level": key[1],
            "status": key[2], "technical_severity": finding["technical_severity"],
            "category": finding.get("recommendation_category", "Unknown"),
            "records": 0, "resource_ids": [], "server_names": [],
            "remediation": finding.get("remediation", ""), "portal_url": finding.get("portal_url", ""),
            "provenance": finding["provenance"], "reference_utc": finding["reference_utc"],
        })
        group["records"] += 1
        if finding["resource_id"] not in group["resource_ids"]:
            group["resource_ids"].append(finding["resource_id"])
            group["server_names"].append(finding["server_name"])
    for group in groups.values():
        group["affected_resources"] = len(group["resource_ids"])
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Not evaluated": 4, "Unknown": 5}
    return sorted(groups.values(), key=lambda g: (
        not (g["status"] == "Unhealthy"), order[g["risk_level"]], -g["affected_resources"], g["title"]
    ))


def _failure(exc, provenance):
    return {
        "status": "error", "provenance": provenance,
        "coverage": {"status": "unavailable"}, "error": exc.as_dict(),
    }


def _highest_severity(findings):
    return min(
        (f["severity"] for f in findings), key=lambda s: SEVERITY_ORDER[s], default="Unknown"
    )


def _enrich_inventory(inventory, findings, provenance):
    by_id = {row["resource_id"]: [] for row in inventory}
    for finding in findings:
        by_id[finding["resource_id"]].append(finding)
    for row in inventory:
        observed = by_id[row["resource_id"]]
        reasons = []
        urgent = any(
            f["category"] == "Alert" and f["severity"] in ("Critical", "High")
            and f["status"].casefold() in ("active", "new", "inprogress")
            for f in observed
        )
        high_finding = any(
            f.get("risk_level", "Not evaluated") in ("Critical", "High") and _is_actionable(f)
            for f in observed
        )
        if urgent:
            reasons.append("Active high-severity Defender alert: analyst investigation required.")
        is_arc = row.get("resource_type", "microsoft.hybridcompute/machines") == "microsoft.hybridcompute/machines"
        is_compute = is_arc or row.get("resource_type") in (
            "microsoft.compute/virtualmachines", "microsoft.compute/virtualmachinescalesets",
        )
        if is_arc and row["connectivity"] != "Connected":
            reasons.append("Arc is not confirmed Connected; endpoint visibility may be stale or unavailable.")
        if is_compute and row["mde_extension"] in ("Failed", "Missing", "Unknown"):
            reasons.append(f"MDE extension state is {row['mde_extension']}; installation needs review.")
        if row["sensor_health"] == "Unhealthy":
            reasons.append("The separate sensor-health source reports Unhealthy.")
        if high_finding:
            reasons.append("Defender native Critical/High risk requires owner review; technical severity is separate.")
        if is_compute and row["servers_plan"] != "P2":
            reasons.append(f"Effective Servers plan is {row['servers_plan']}; review the intended baseline.")
        if is_compute and row["sensor_health"] == "Unknown":
            reasons.append("MDE sensor health is unverified; extension success is not health evidence.")
        if row["provider"] == "unknown":
            reasons.append("Hosting provider/location is unverified; N/A does not mean on-premises.")
        high_gap = (
            is_arc and row["connectivity"] in ("Expired", "Disconnected")
            or is_compute and row["mde_extension"] in ("Failed", "Missing")
            or row["sensor_health"] == "Unhealthy"
            or is_compute and row["servers_plan"] == "Free"
        )
        row.update({
            "observed_findings": len(observed),
            "highest_observed_severity": _highest_severity(observed),
            "recommendation_records": sum(f["category"] == "Recommendation" for f in observed),
            "recommendation_status_counts": _counts(
                [f for f in observed if f["category"] == "Recommendation"], "status"
            ),
            "recommendation_risk_counts": _counts(
                [f for f in observed if f["category"] == "Recommendation" and _is_actionable(f)], "risk_level"
            ),
            "distinct_recommendations": len({
                f.get("recommendation_id", f["finding_id"])
                for f in observed if f["category"] == "Recommendation"
            }),
            "priority": (
                "Immediate review" if urgent else
                "High priority" if high_gap or high_finding else
                "Verify coverage" if reasons else "No observed gap"
            ),
            "priority_reasons": reasons or [
                "No gap observed in the collected scope at the stated time; this is not zero-risk assurance."
            ],
            "provenance": provenance,
        })
    priorities = {"Immediate review": 0, "High priority": 1, "Verify coverage": 2, "No observed gap": 3}
    inventory.sort(key=lambda r: (priorities[r["priority"]], r["server_name"].casefold(), r["resource_id"]))
    findings.sort(key=lambda f: (
        SEVERITY_ORDER[f["severity"]], f["server_name"].casefold(), f["category"], f["finding_id"]
    ))


def _source_summaries(sources):
    result = []
    for source in sources:
        compact = {key: value for key, value in source.items() if key != "errors"}
        errors = source.get("errors", [])
        compact.update({
            "errors": errors[:3], "errors_total": len(errors),
            "errors_returned": min(len(errors), 3), "errors_has_more": len(errors) > 3,
        })
        result.append(compact)
    return result


def _response_bytes(response):
    # Match the sandbox's default JSON serialization, not a smaller custom encoder.
    return len(json.dumps(response, allow_nan=False).encode("utf-8"))


def _check_transport_budget(response):
    if _response_bytes(response) > TRANSPORT_BUDGET_BYTES:
        raise EvidenceError(
            "transport_budget_exceeded",
            "The structured response exceeds the safe sandbox stdout budget. Full evidence remains in report artifacts.",
            "response_transport",
        )
    return response


def _compact_action(action):
    reasons = {
        "investigate-alerts": "Active Critical/High alerts need analyst review.",
        "restore-arc": "Expired/Disconnected Arc creates a visibility blind spot.",
        "review-mde": "Missing/failed MDE installation or independently unhealthy sensor.",
        "review-findings": "Native Critical/High risk findings need owner review; severity is separate.",
        "review-remaining-findings": "Validate other indexed findings and old evaluations before remediation.",
        "review-plan": "Free/unknown protection or P1/P2 baseline needs review.",
        "verify-health": "ARM installation does not verify current MDE sensor health.",
        "restore-sources": "Unavailable evidence is Unknown, not zero findings.",
        "review-attack-paths": "Review observed native High/Critical paths and source-recommended breaks.",
        "review-critical-cves": "Critical technical CVE evidence requires patch review; native risk is separate.",
        "review-demo-chains": "Review SIMULATED illustrative chains; not real Defender/customer detections.",
    }
    return {
        "action_id": action["action_id"], "priority": action["priority"],
        "reason": reasons[action["action_id"]], "affected_resources": action["affected_resources"],
        "sources": action["sources"], "provenance": action["provenance"],
    }


def _transport_envelope(snapshot):
    summary = snapshot["summary"]
    counts = {key: summary[key] for key in (
        "resources", "servers", "connected", "mde_extension_succeeded", "sensor_verified_healthy",
        "sensor_unverified", "servers_p2", "by_provider",
        "source_observed_actionable_findings",
    )}
    sources = {}
    errors = []
    for source in snapshot["sources"]:
        sources[source["name"]] = source["status"]
        for error in source.get("errors", []):
            item = {"source": source["name"], "code": error["code"]}
            if "http_status" in error:
                item["http_status"] = error["http_status"]
            errors.append(item)
    if snapshot["provenance"] == "SIMULATED":
        scope = {
            "description": "SIMULATED 200-server fixture", "customer_facts_verified": False,
            "azure_called": False, "token_acquired": False,
        }
    else:
        scope = {key: snapshot["scope"][key] for key in ("subscription_id", "tenant_id")}
    return {
        "status": snapshot["status"], "provenance": snapshot["provenance"],
        "reference_utc": snapshot["reference_utc"], "scope": scope,
        "coverage": {
            "status": snapshot["coverage"]["status"], "inventory_pagination_completed": True,
            "unknown_sources": [s["name"] for s in snapshot["sources"] if s["status"] != "complete"],
            "sensor_health_is_separate_from_extension": True,
            "subscription_secure_score_collected": snapshot["coverage"]["subscription_secure_score_collected"],
        },
        "summary": counts, "sources": sources,
        "posture_summary": {
            "classic_score_percentage": next(
                (score.get("percentage") for score in snapshot["posture"]["scores"] if score.get("name") == "ascScore"), None
            ),
            "paths_context": summary["attack_paths_subscription_context"] if sources.get("attack_paths") == "complete" else None,
            "paths_arc_related": summary["attack_paths_arc_related"] if sources.get("attack_paths") == "complete" else None,
            "embedded_cve_occurrences": summary["embedded_cve_records"],
            "distinct_cve_ids": summary["distinct_embedded_cves"],
            "resource_cve_pairs": summary["distinct_resource_cve_pairs"],
            "critical_cve_occurrences": summary["embedded_cve_technical_severity_counts"].get("Critical", 0),
        },
        "source_errors": {
            "total": len(errors), "samples": errors[:1],
            "returned": min(len(errors), 1), "has_more": len(errors) > 1,
        },
        "response_budget_bytes": TRANSPORT_BUDGET_BYTES,
        "qualification": (
            "Native risk != severity; subscription context is not Arc-only. "
            "Unknown/empty sources are not zero risk. Full detail and embedded CVEs are in the snapshot."
        ),
    }


def _summary(inventory, findings, sources):
    counts = lambda key: dict(sorted(Counter(row[key] for row in inventory).items()))
    category_source = {
        "Recommendation": "defender_recommendations",
        "Vulnerability": "defender_vulnerabilities",
        "Alert": "defender_alerts",
    }
    source_lookup = {source["name"]: source for source in sources}
    finding_counts = {}
    for category, source_name in category_source.items():
        source = source_lookup[source_name]
        finding_counts[category] = (
            sum(f["category"] == category and _is_actionable(f) for f in findings)
            if source["status"] == "complete" else None
        )
    return {
        "servers": sum(r.get("resource_type", "microsoft.hybridcompute/machines") in (
            "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
            "microsoft.compute/virtualmachinescalesets",
        ) for r in inventory),
        "resources": len(inventory),
        "resource_type_counts": _counts(inventory, "resource_type"),
        "arm_resource_type_counts": _counts(
            [r for r in inventory if r.get("inventory_source") == "ARM/Resource Graph inventory"], "resource_type"
        ),
        "connected": sum(r["connectivity"] == "Connected" for r in inventory),
        "mde_extension_succeeded": sum(r["mde_extension"] == "Succeeded" for r in inventory),
        "sensor_verified_healthy": sum(r["sensor_health"] == "Healthy" for r in inventory),
        "sensor_unverified": sum(r["sensor_health"] == "Unknown" for r in inventory),
        "servers_p2": sum(r["servers_plan"] == "P2" for r in inventory),
        "by_provider": counts("provider"), "by_environment": counts("environment"),
        "by_os": counts("os"), "by_connectivity": counts("connectivity"),
        "by_mde_extension": counts("mde_extension"), "by_sensor_health": counts("sensor_health"),
        "by_servers_plan": counts("servers_plan"), "by_priority": counts("priority"),
        "source_observed_actionable_findings": finding_counts,
        "observed_findings_received": len(findings),
        "recommendation_status_counts": _counts(
            [f for f in findings if f["category"] == "Recommendation"], "status"
        ),
        "recommendation_risk_counts": _counts(
            [f for f in findings if f["category"] == "Recommendation" and _is_actionable(f)], "risk_level"
        ),
        "distinct_recommendations": len({
            f.get("recommendation_id", f["finding_id"]) for f in findings if f["category"] == "Recommendation"
        }),
        "hosts_with_unhealthy_recommendations": len({
            f["resource_id"] for f in findings if f["category"] == "Recommendation" and _is_actionable(f)
        }),
        "unknown_or_partial_sources": sum(s["status"] != "complete" for s in sources),
        "qualification": (
            "Counts describe this snapshot only. Null means unavailable/partial, not zero. "
            "Empty successfully paginated Arc-matched findings are not proof of zero risk. "
            "Resource Graph is indexed, may lag and does not verify current MDE sensor health."
        ),
    }


def _actions(inventory, findings, sources, provenance):
    by_id = {r["resource_id"]: r for r in inventory}
    definitions = [
        (
            "investigate-alerts", "Immediate review", "Investigate active high-severity alerts",
            "Defender reports an active Critical/High alert. A security analyst must validate and respond.",
            {f["resource_id"] for f in findings if (
                f["category"] == "Alert" and f["severity"] in ("Critical", "High")
                and f["status"].casefold() in ("active", "new", "inprogress")
            )}, ["defender_alerts"],
        ),
        (
            "restore-arc", "High priority", "Restore Arc connectivity before trusting freshness",
            "Disconnected/Expired Arc hosts create a visibility blind spot; installation alone is insufficient.",
            {r["resource_id"] for r in inventory if r["connectivity"] in ("Expired", "Disconnected")},
            ["arc_inventory"],
        ),
        (
            "review-mde", "High priority", "Repair MDE onboarding and verify the sensor",
            "Missing/failed extensions or independently unhealthy sensors require owner investigation.",
            {r["resource_id"] for r in inventory if (
                r["mde_extension"] in ("Failed", "Missing") or r["sensor_health"] == "Unhealthy"
            )}, ["arc_extensions", "mde_sensor_health"],
        ),
        (
            "review-findings", "High priority", "Review recommendations with native High/Critical risk",
            "Use Defender risk.level and owners; technical severity and CVSS are separate, not substituted.",
            {f["resource_id"] for f in findings if (
                f["category"] != "Alert" and f.get("risk_level") in ("Critical", "High")
                and f["status"].casefold() == "unhealthy"
            )}, ["defender_recommendations", "defender_vulnerabilities"],
        ),
        (
            "review-plan", "Verify coverage", "Confirm the effective protection baseline",
            "Free/unknown plans are coverage gaps; P1 versus P2 is an explicit licensing decision.",
            {r["resource_id"] for r in inventory if r["servers_plan"] != "P2"
             and r.get("resource_type", "microsoft.hybridcompute/machines") in (
                 "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
                 "microsoft.compute/virtualmachinescalesets",
             )},
            ["effective_servers_plan"],
        ),
        (
            "verify-health", "Verify coverage", "Obtain separate, current MDE sensor-health evidence",
            "ARM provisioning and WDATP integration do not prove that an endpoint sensor is healthy.",
            {r["resource_id"] for r in inventory if r["sensor_health"] == "Unknown"},
            ["mde_sensor_health"],
        ),
        (
            "review-remaining-findings", "Verify coverage", "Validate remaining indexed security findings",
            "Lower/unknown-severity unhealthy findings still need owner review; old evaluations may need revalidation.",
            {f["resource_id"] for f in findings if (
                f["category"] != "Alert" and f.get("risk_level") not in ("Critical", "High")
                and f["status"].casefold() == "unhealthy"
            )}, ["defender_recommendations", "defender_vulnerabilities"],
        ),
    ]
    result = []
    for action_id, priority, title, reason, resource_ids, source_names in definitions:
        if not resource_ids:
            continue
        names = sorted(by_id[rid]["server_name"] for rid in resource_ids)
        result.append({
            "action_id": action_id, "priority": priority, "title": title, "reason": reason,
            "affected_resources": len(resource_ids),
            "affected_servers": sum(
                by_id[rid].get("resource_type", "microsoft.hybridcompute/machines") in (
                    "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
                    "microsoft.compute/virtualmachinescalesets",
                ) for rid in resource_ids
            ),
            "server_sample": names[:5],
            "sample_returned": min(len(names), 5), "sample_has_more": len(names) > 5,
            "sources": source_names, "provenance": provenance,
        })
    # Unconfigured sensor telemetry already has its own verification action.
    unavailable = [
        s["name"] for s in sources if s["status"] != "complete" and s["name"] != "mde_sensor_health"
    ]
    if unavailable and inventory:
        result.append({
            "action_id": "restore-sources", "priority": "Verify coverage",
            "title": "Resolve unavailable or partial evidence sources",
            "reason": "Missing evidence is Unknown, not zero findings. Review source errors with an authorized operator.",
            "affected_resources": len(inventory),
            "affected_servers": sum(r.get("resource_type", "microsoft.hybridcompute/machines") in (
                "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
                "microsoft.compute/virtualmachinescalesets",
            ) for r in inventory), "server_sample": [],
            "sample_returned": 0, "sample_has_more": bool(inventory),
            "sources": unavailable, "provenance": provenance,
        })
    return result


def _review_actions(snapshot, inventory, findings):
    base = _actions(inventory, findings, snapshot["sources"], snapshot["provenance"])
    ids = {r["resource_id"] for r in inventory}
    paths = [p for p in snapshot["attack_paths"] if (
        p["risk_level"] in ("Critical", "High") and set(p.get("resource_ids", p["arc_resource_ids"])) & ids
    )]
    higher = []
    if paths:
        path_resources = {rid for p in paths for rid in p.get("resource_ids", p["arc_resource_ids"])}
        demo = snapshot["provenance"] == "SIMULATED"
        higher.append({
            "action_id": "review-demo-chains" if demo else "review-attack-paths",
            "priority": "High priority",
            "title": "Review illustrative SIMULATED chains" if demo else "Review observed High/Critical attack paths first",
            "reason": (
                "SIMULATED teaching chains only: examine exposure/trust and illustrative proposed breaks."
                if demo else
                "Defender reports High/Critical native paths. Review the actual entry/target, risk factors, "
                "linked assessments and source-recommended breaks before changes."
            ),
            "affected_resources": len(path_resources), "affected_servers": sum(
                r["resource_id"] in path_resources and r.get("resource_type") in (
                    "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
                    "microsoft.compute/virtualmachinescalesets",
                ) for r in inventory
            ),
            "affected_paths": len(paths), "path_ids": [p["path_id"] for p in paths],
            "risk_factors": sorted({factor for p in paths for factor in p["risk_factors"]}),
            "source_recommended_breaks": sorted({p["remediation"] for p in paths if p["remediation"]}),
            "scope": "SIMULATED illustrative Arc" if demo else "Subscription context",
            "sources": ["attack_paths"], "provenance": snapshot["provenance"],
            "server_sample": [], "sample_returned": 0, "sample_has_more": bool(path_resources),
        })
    critical = [v for v in snapshot["vulnerabilities"] if (
        v["technical_severity"] == "Critical" and v["resource_id"] in ids
    )]
    if critical:
        resource_ids = {v["resource_id"] for v in critical}
        higher.append({
            "action_id": "review-critical-cves", "priority": "High priority",
            "title": "Review source Critical CVEs and patch evidence",
            "reason": (
                "Embedded source CVEs have Critical technical severity. Validate source fix status, affected "
                "software/KB evidence and change impact; do not relabel native recommendation risk as Critical."
            ),
            "affected_resources": len(resource_ids), "affected_servers": sum(
                r["resource_id"] in resource_ids and r.get("resource_type") in (
                    "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
                    "microsoft.compute/virtualmachinescalesets",
                ) for r in inventory
            ),
            "cve_occurrences": len(critical), "distinct_cve_ids": len({v["cve_id"] for v in critical}),
            "native_risk_counts": _counts(
                [f for f in findings if f["finding_id"] in {v["finding_id"] for v in critical}], "risk_level"
            ),
            "sources": ["defender_recommendations.additionalData.CvesDetails"],
            "provenance": snapshot["provenance"], "scope": "Resource-level source evidence",
            "server_sample": [], "sample_returned": 0, "sample_has_more": bool(resource_ids),
        })
    immediate = [a for a in base if a["action_id"] == "investigate-alerts"]
    remaining = [a for a in base if a["action_id"] != "investigate-alerts"]
    remaining.sort(key=lambda a: (
        {"review-findings": 0, "restore-arc": 1, "review-mde": 2}.get(a["action_id"], 3)
    ))
    return immediate + higher + remaining


def _matches(row, params):
    if params.get("resource_type") and row.get("resource_type", "") != params["resource_type"]:
        return False
    if params["provider"] != "all" and row["provider"] != params["provider"]:
        return False
    if params["environment"] != "all" and row["environment"] != params["environment"]:
        return False
    if params["connectivity"] != "all" and row["connectivity"] != params["connectivity"]:
        return False
    if params["resource_group"] and row["resource_group"].casefold() != params["resource_group"].casefold():
        return False
    if params["server_name"] and params["server_name"].casefold() not in row["server_name"].casefold():
        return False
    mde = params["mde"]
    if mde == "failed-extension" and row["mde_extension"] != "Failed":
        return False
    if mde == "missing-extension" and row["mde_extension"] != "Missing":
        return False
    if mde == "unverified" and row["sensor_health"] != "Unknown":
        return False
    if mde == "healthy" and row["sensor_health"] != "Healthy":
        return False
    if mde == "unhealthy" and row["sensor_health"] != "Unhealthy":
        return False
    return True


def _query(snapshot, params):
    inventory = [r for r in snapshot["inventory"] if _matches(r, params)]
    selected_ids = {r["resource_id"] for r in inventory}
    findings = [f for f in snapshot["findings"] if (
        f["resource_id"] in selected_ids
        and (params["severity"] == "all" or f["severity"] == params["severity"])
        and (params["risk"] == "all" or f["risk_level"] == params["risk"])
        and (params["status"] == "all" or f["status"] == params["status"])
    )]
    if any(params[key] != "all" for key in ("severity", "risk", "status")):
        finding_ids = {f["resource_id"] for f in findings}
        inventory = [r for r in inventory if r["resource_id"] in finding_ids]
    if params["view"] == "inventory":
        query_fields = (
            "provenance", "server_name", "resource_id", "resource_group", "provider", "environment", "resource_type",
            "connectivity", "mde_extension", "sensor_health",
            "servers_plan", "plan_inherited", "priority",
            "observed_findings", "highest_observed_severity",
        )
        items = [{key: row[key] for key in query_fields} for row in inventory]
    elif params["view"] == "findings":
        query_fields = (
            "provenance", "server_name", "resource_id", "finding_id", "category",
            "technical_severity", "risk_level", "status", "title", "source",
            "recommendation_category", "assessment_type",
        )
        items = [{key: row[key] for key in query_fields} for row in findings]
    elif params["view"] == "actions":
        items = [
            _compact_action(action)
            for action in _review_actions(snapshot, inventory, findings)
        ]
    else:
        items = _section_query(snapshot, params, inventory, findings)
    offset, limit = params["offset"], params["limit"]
    page_candidates = items[offset:offset + limit]
    response = _transport_envelope(snapshot)
    all_source_statuses = response["sources"]
    view_sources = {
        "attack_paths": ("attack_paths",),
        "controls": ("secure_score_controls", "subscription_secure_score"),
        "posture": ("subscription_secure_score", "secure_score_controls", "risk_secure_score",
                    "attack_paths", "subscription_plans"),
        "compliance": ("compliance_standards", "compliance_controls", "compliance_assessments"),
        "software": ("software_inventory",),
        "vulnerabilities": ("defender_recommendations", "defender_vulnerabilities"),
        "resource_details": ("resource_inventory", "defender_recommendations", "arc_inventory",
                             "compute_extensions", "arc_extensions", "aks_security_profiles",
                             "software_inventory", "mde_sensor_health"),
        "inventory": ("resource_inventory", "arc_inventory", "arc_extensions",
                      "compute_extensions", "mde_sensor_health"),
        "findings": ("defender_recommendations", "defender_vulnerabilities", "defender_alerts"),
        "actions": ("attack_paths", "defender_recommendations", "defender_alerts",
                    "arc_inventory", "arc_extensions", "compute_extensions", "mde_sensor_health"),
    }
    response["sources"] = {
        name: all_source_statuses[name] for name in view_sources[params["view"]] if name in all_source_statuses
    }
    response.update({
        "view": params["view"],
        "filters": {
            k: v for k, v in params.items()
            if k not in ("operation", "view", "limit", "offset") and v not in ("all", "")
        },
        "summary_scope": "unfiltered_snapshot",
        "matched_servers": sum(r.get("resource_type", "microsoft.hybridcompute/machines") in (
            "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
            "microsoft.compute/virtualmachinescalesets",
        ) for r in inventory),
        "matched_resources": len(inventory),
        "matched_by_provider": dict(sorted(Counter(row["provider"] for row in inventory).items())),
        "matched_status_counts": _counts(findings, "status"),
        "matched_unhealthy_native_risks": _counts(
            [f for f in findings if f["category"] == "Recommendation" and _is_actionable(f)], "risk_level"
        ),
        "sources_total": len(all_source_statuses), "sources_returned": len(response["sources"]),
        "sources_has_more": len(response["sources"]) < len(all_source_statuses),
        "result_scope": (
            "Resource-level evidence" if params["view"] in ("inventory", "findings", "resource_details", "actions", "vulnerabilities")
            else "Subscription context; explicit Arc association where present"
        ),
        "total_matched": len(items), "requested_limit": limit, "offset": offset,
        "returned": 0, "has_more": offset < len(items),
        "next_offset": offset if offset < len(items) else None,
        "transport_capped": False, "items": [],
    })
    _check_transport_budget(response)

    def update_page():
        returned = len(response["items"])
        more = offset + returned < len(items)
        response.update({
            "returned": returned, "has_more": more,
            "next_offset": offset + returned if more else None,
        })

    for item in page_candidates:
        response["items"].append(item)
        update_page()
        if _response_bytes(response) > TRANSPORT_BUDGET_BYTES:
            response["items"].pop()
            response["transport_capped"] = True
            update_page()
            break
    if page_candidates and not response["items"]:
        raise EvidenceError(
            "query_item_exceeds_budget",
            "One evidence row cannot fit the safe stdout budget. Generate a report and inspect its full JSON snapshot.",
            "response_transport",
        )
    return _check_transport_budget(response)


def _section_query(snapshot, params, inventory, findings):
    ids = {r["resource_id"] for r in inventory}
    view = params["view"]
    if view == "resource_details":
        return [{
            "provenance": snapshot["provenance"], "server_name": r["server_name"],
            "resource_id": r["resource_id"], "location": r.get("location", "Unknown"),
            "os": r["os"], "os_version": r.get("os_version", "Unknown"),
            "parent_resource_id": r.get("parent_resource_id", ""),
            "inventory_source": r.get("inventory_source", "SIMULATED"),
            "tags": r.get("tags", {}), "recommendation_status_counts": r["recommendation_status_counts"],
            "recommendation_risk_counts": r["recommendation_risk_counts"],
            "software_records": r.get("software_records", 0), "extensions": r.get("extensions", []),
            "fim_configuration": r.get("fim_configuration", "Not verified"),
            "embedded_cve_records": r.get("embedded_cve_records", 0),
            "aks_monitoring_configured": r.get("aks_defender_monitoring_enabled"),
        } for r in inventory]
    if view == "vulnerabilities":
        return [{
            k: f.get(k) for k in (
                "server_name", "cve_id", "technical_severity", "fix_status",
                "fixed_version", "software_name", "risk_level", "source", "provenance",
            )
        } for f in snapshot["vulnerabilities"] if (
            f["resource_id"] in ids
            and (params["severity"] == "all" or f["technical_severity"] == params["severity"])
            and (params["risk"] == "all" or f["risk_level"] == params["risk"])
        )]
    if view == "posture":
        return snapshot["posture"]["scores"] + [{
            "scope": "Subscription context", "section": "attack_paths",
            "paths": len(snapshot["attack_paths"]),
            "arc_related": sum(bool(p["arc_resource_ids"]) for p in snapshot["attack_paths"]),
            "provenance": snapshot["provenance"],
        }]
    if view == "controls":
        return [{
            k: row.get(k) for k in (
                "title", "current", "maximum", "potential_score_gain", "healthy",
                "unhealthy", "not_applicable", "scope", "provenance",
            )
        } for row in snapshot["posture"]["controls"]]
    if view == "compliance":
        return snapshot["compliance"]["standards"]
    constrained = any(params[k] not in ("all", "") for k in (
        "provider", "environment", "resource_group", "server_name", "connectivity", "mde", "resource_type",
    ))
    rows = snapshot["attack_paths"] if view == "attack_paths" else snapshot["software"]
    selected = []
    for row in rows:
        arc_ids = row.get("arc_resource_ids", [])
        if params["association"] == "arc" and not arc_ids:
            continue
        if params["association"] == "context" and arc_ids:
            continue
        resource_ids = row.get("resource_ids", arc_ids)
        if constrained and not (set(resource_ids) & ids):
            continue
        if view == "attack_paths":
            if params["risk"] != "all" and row["risk_level"] != params["risk"]:
                continue
            selected.append({
                "path_id": row["path_id"], "title": row["title"], "risk_level": row["risk_level"],
                "association": row["association"], "entry_point": row["entry_point"]["name"],
                "target": row["target"]["name"], "entities": len(row["entities"]),
                "edges": len(row["edges"]), "risk_factors": row["risk_factors"],
                "recommended_break": _text(row["remediation"], 200),
                "scope": row["scope"], "provenance": row["provenance"],
                "full_graph_in_snapshot": True,
                "nodes": [{
                    "name": node["name"], "type": node["type"], "resource_id": node["resource_id"],
                } for node in row["entities"]],
                "connections": [{
                    "from": next(node["name"] for node in row["entities"] if node["entity_id"] == edge["source"]),
                    "to": next(node["name"] for node in row["entities"] if node["entity_id"] == edge["target"]),
                    "label": edge["label"],
                } for edge in row["edges"]],
            })
        else:
            selected.append({k: row.get(k) for k in (
                "server_name", "software_name", "version", "vendor", "known_vulnerabilities",
                "end_of_support_status", "association", "scope", "provenance",
            )})
    return selected


def _csv_cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        text = "'" + text
    return text


def _csv_document(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow([_csv_cell(row.get(field)) for field in fields])
    return output.getvalue()


INVENTORY_CSV_FIELDS = (
    "provenance", "reference_utc", "server_name", "resource_id", "resource_group",
    "provider", "provider_evidence", "environment", "os", "connectivity",
    "last_status_change_utc", "mde_extension", "extension_evidence", "sensor_health",
    "sensor_evidence", "servers_plan", "plan_inherited", "plan_source",
    "priority", "priority_reasons", "observed_findings", "highest_observed_severity",
    "location", "tags", "recommendation_status_counts", "recommendation_risk_counts",
    "extensions", "fim_configuration",
)
FINDING_CSV_FIELDS = (
    "provenance", "reference_utc", "server_name", "resource_id", "resource_group",
    "provider", "environment", "category", "severity", "technical_severity", "risk_level", "status", "title",
    "finding_id", "source", "evidence", "source_time_utc", "first_evaluation_utc",
    "recommendation_category", "remediation", "portal_url", "patch", "cve_details",
)


def _safe_json(value):
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )


def _check_snapshot_expansion(data, strings):
    """Preflight all expanded nodes/cell work and UTF-16 string units without building rows."""
    def invalid(message):
        raise EvidenceError("invalid_encoding", message, "artifact_encoding")

    def add(total, child, copies=1):
        nodes = total[0] + child[0] * copies
        units = total[1] + child[1] * copies
        if nodes > MAX_DECODED_NODES or units > MAX_DECODED_STRING_UNITS:
            raise EvidenceError(
                "encoding_expansion_exceeded",
                "Snapshot exceeds the bounded decoded expansion budget; no evidence was truncated.",
                "artifact_encoding",
            )
        return nodes, units

    def string(index):
        if type(index) is not int or not 0 <= index < len(strings):
            invalid("Invalid snapshot string reference.")
        return strings[index]

    def units(value):
        return len(value.encode("utf-16-le", "surrogatepass")) // 2

    def node(value, depth=0):
        if depth > 100:
            invalid("Snapshot nesting exceeds the safety bound.")
        if value is None or type(value) in (bool, int):
            return 1, 0
        if type(value) is float:
            if not math.isfinite(value):
                invalid("Snapshot contains a non-finite number.")
            return 1, 0
        if not isinstance(value, list) or not value or type(value[0]) is not int:
            invalid("Invalid encoded snapshot node.")
        tag = value[0]
        if tag == 0 and len(value) == 2:
            return add((0, 0), (1, units(string(value[1]))))
        if tag == 4 and len(value) == 1:
            return None
        if tag == 5 and len(value) == 2 and isinstance(value[1], str):
            if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value[1]):
                invalid("Invalid encoded snapshot float.")
            if not math.isfinite(float(value[1])):
                invalid("Snapshot contains a non-finite number.")
            return 1, 0
        if tag == 1 and len(value) == 2 and isinstance(value[1], list) and len(value[1]) % 2 == 0:
            total, seen = (1, 0), set()
            for offset in range(0, len(value[1]), 2):
                key, child = string(value[1][offset]), node(value[1][offset + 1], depth + 1)
                if key in seen or child is None:
                    invalid("Encoded object has a duplicate key or missing-value marker.")
                seen.add(key)
                total = add(add(total, (1, units(key))), child)
            return total
        if tag == 2 and len(value) == 2 and isinstance(value[1], list):
            total = (1, 0)
            for encoded in value[1]:
                child = node(encoded, depth + 1)
                if child is None:
                    invalid("Encoded array contains a missing-value marker.")
                total = add(total, child)
            return total
        if tag == 3 and len(value) == 4:
            count, fields, columns = value[1:]
            if (
                type(count) is not int or not 0 <= count <= 9_007_199_254_740_991
                or not isinstance(fields, list) or not isinstance(columns, list) or len(fields) != len(columns)
            ):
                invalid("Invalid snapshot column table.")
            total = add((1, 0), (1 + len(fields), 0), count)
            keys = [string(index) for index in fields]
            if len(set(keys)) != len(keys):
                invalid("Snapshot table has duplicate keys.")
            for key, encoded in zip(keys, columns):
                child, present = column(encoded, count, depth + 1)
                total = add(add(total, child), (0, units(key)), present)
            return total
        invalid("Unknown encoded snapshot node tag or shape.")

    def column(value, count, depth):
        if not isinstance(value, list) or not value or type(value[0]) is not int:
            invalid("Invalid encoded snapshot column.")
        tag = value[0]
        if tag == 0 and len(value) == 2:
            child = node(value[1], depth)
            return (add((0, 0), child, count), count) if child is not None else ((0, 0), 0)
        if tag == 1 and len(value) == 2 and isinstance(value[1], list) and len(value[1]) == count:
            total, present = (0, 0), 0
            for encoded in value[1]:
                child = node(encoded, depth)
                if child is not None:
                    total, present = add(total, child), present + 1
            return total, present
        if tag == 2 and len(value) == 2 and isinstance(value[1], list):
            total, present, covered = (0, 0), 0, 0
            for run in value[1]:
                if (
                    not isinstance(run, list) or len(run) != 2 or type(run[0]) is not int
                    or not 1 <= run[0] <= count - covered
                ):
                    invalid("Invalid snapshot run length.")
                child = node(run[1], depth)
                if child is not None:
                    total, present = add(total, child, run[0]), present + run[0]
                covered += run[0]
            if covered != count:
                invalid("Snapshot runs do not cover the complete table.")
            return total, present
        if tag == 3 and len(value) == 3 and isinstance(value[2], list):
            default = node(value[1], depth)
            total, present, seen = (0, 0), 0, set()
            for pair in value[2]:
                if (
                    not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                    or not 0 <= pair[0] < count or pair[0] in seen
                ):
                    invalid("Invalid snapshot sparse position.")
                seen.add(pair[0])
                child = node(pair[1], depth)
                if child is not None:
                    total, present = add(total, child), present + 1
            if default is not None:
                total = add(total, default, count - len(seen))
                present += count - len(seen)
            return total, present
        invalid("Unknown encoded snapshot column tag or shape.")

    cost = node(data)
    if cost is None:
        invalid("Restored snapshot must be an object.")
    return add((0, 0), cost)


def _pack_snapshot(snapshot):
    """Lossless recursive key/string dictionary with exact constant/run/sparse columns."""
    strings, lookup = [], {}
    missing = object()

    def invalid(message):
        raise EvidenceError("invalid_encoding", message, "artifact_encoding")

    def intern(value):
        if value not in lookup:
            lookup[value] = len(strings)
            strings.append(value)
        return lookup[value]

    def encode(value, depth=0):
        if depth > 100:
            invalid("Snapshot nesting exceeds the safety bound.")
        if value is missing:
            return [4]
        if value is None or type(value) in (bool, int):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                invalid("Snapshot contains a non-finite number.")
            return [5, repr(value)]
        if isinstance(value, str):
            return [0, intern(value)]
        if isinstance(value, dict):
            fields = []
            for key, child in value.items():
                if not isinstance(key, str):
                    invalid("Snapshot object keys must be strings.")
                fields.extend((intern(key), encode(child, depth + 1)))
            return [1, fields]
        if isinstance(value, list):
            if len(value) >= 4 and all(isinstance(row, dict) for row in value):
                fields = {key for row in value for key in row}
                if any(not isinstance(key, str) for key in fields):
                    invalid("Snapshot table keys must be strings.")
                fields = sorted(fields)
                return [3, len(value), [intern(key) for key in fields], [
                    column([row.get(key, missing) for row in value], depth + 1) for key in fields
                ]]
            return [2, [encode(child, depth + 1) for child in value]]
        invalid("Snapshot contains an unsupported JSON value.")

    def column(values, depth):
        encoded = [encode(value, depth) for value in values]
        fingerprints = [json.dumps(value, separators=(",", ":"), allow_nan=False) for value in encoded]
        if len(set(fingerprints)) == 1:
            return [0, encoded[0]]
        runs = []
        for index, value in enumerate(encoded):
            if index and fingerprints[index] == fingerprints[index - 1]:
                runs[-1][0] += 1
            else:
                runs.append([1, value])
        default = Counter(fingerprints).most_common(1)[0][0]
        first = fingerprints.index(default)
        sparse = [[index, value] for index, value in enumerate(encoded) if fingerprints[index] != default]
        return min(
            ([1, encoded], [2, runs], [3, encoded[first], sparse]),
            key=lambda value: len(json.dumps(value, separators=(",", ":"), allow_nan=False)),
        )

    if not isinstance(snapshot, dict) or any(key not in snapshot for key in ("provenance", "reference_utc", "summary")):
        invalid("Normalized snapshot metadata is missing.")
    encoded = encode(snapshot)
    _check_snapshot_expansion(encoded, strings)
    return {
        "schema_version": "2.2", "encoding": "dictionary-columns-v2",
        "provenance": snapshot["provenance"], "reference_utc": snapshot["reference_utc"],
        "summary": snapshot["summary"], "strings": strings, "data": encoded,
    }


def _unpack_snapshot(document):
    """Restore complete evidence from ordinary, historical v1 or current v2 JSON."""
    def invalid(message):
        raise EvidenceError("invalid_encoding", message, "artifact_encoding")

    if not isinstance(document, dict):
        invalid("Snapshot document must be an object.")
    if "encoding" not in document:
        return document
    if document["encoding"] not in ("dictionary-columns-v1", "dictionary-columns-v2"):
        invalid("Unsupported snapshot encoding.")
    strings = document.get("strings")
    if not isinstance(strings, list) or any(not isinstance(s, str) for s in strings) or "data" not in document:
        invalid("Invalid snapshot string dictionary or missing data.")
    missing = object()

    def string(index):
        if type(index) is not int or not 0 <= index < len(strings):
            invalid("Invalid snapshot string reference.")
        return strings[index]

    def legacy(value, depth=0):
        if depth > 100:
            invalid("Snapshot nesting exceeds the safety bound.")
        if isinstance(value, str) and value.startswith("~"):
            if value.startswith("~~"):
                return value[1:]
            if not re.fullmatch(r"~[0-9]+", value):
                invalid("Invalid compact string reference.")
            try:
                index = int(value[1:])
            except ValueError:
                invalid("Invalid compact string reference.")
            return string(index)
        if isinstance(value, dict):
            if set(value) == {"$s"}:
                return string(value["$s"])
            if set(value) == {"$table", "rows"}:
                columns, rows = value["$table"], value["rows"]
                if (
                    not isinstance(columns, list) or any(not isinstance(c, str) for c in columns)
                    or len(set(columns)) != len(columns) or not isinstance(rows, list)
                ):
                    invalid("Invalid snapshot column table.")
                result = []
                for row in rows:
                    if not isinstance(row, list) or len(row) != len(columns):
                        invalid("Snapshot row/column counts differ.")
                    result.append({
                        key: legacy(cell, depth + 1) for key, cell in zip(columns, row)
                        if not (isinstance(cell, dict) and set(cell) == {"$missing"} and cell["$missing"] is True)
                    })
                return result
            if any(key in value for key in ("$s", "$table", "$missing")):
                invalid("Invalid reserved v1 codec marker.")
            return {key: legacy(child, depth + 1) for key, child in value.items()}
        if isinstance(value, list):
            return [legacy(child, depth + 1) for child in value]
        return value

    def decode(value, depth=0):
        if depth > 100:
            invalid("Snapshot nesting exceeds the safety bound.")
        if value is None or type(value) in (bool, int):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                invalid("Snapshot contains a non-finite number.")
            return value
        if not isinstance(value, list) or not value or type(value[0]) is not int:
            invalid("Invalid encoded snapshot node.")
        tag = value[0]
        if tag == 0 and len(value) == 2:
            return string(value[1])
        if tag == 4 and len(value) == 1:
            return missing
        if tag == 5 and len(value) == 2 and isinstance(value[1], str):
            if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value[1]):
                invalid("Invalid encoded snapshot float.")
            number = float(value[1])
            if not math.isfinite(number):
                invalid("Snapshot contains a non-finite number.")
            return number
        if tag == 1 and len(value) == 2 and isinstance(value[1], list) and len(value[1]) % 2 == 0:
            result = {}
            for offset in range(0, len(value[1]), 2):
                key, child = string(value[1][offset]), decode(value[1][offset + 1], depth + 1)
                if key in result or child is missing:
                    invalid("Encoded object has a duplicate key or missing-value marker.")
                result[key] = child
            return result
        if tag == 2 and len(value) == 2 and isinstance(value[1], list):
            result = [decode(child, depth + 1) for child in value[1]]
            if any(child is missing for child in result):
                invalid("Encoded array contains a missing-value marker.")
            return result
        if tag == 3 and len(value) == 4:
            count, fields, columns = value[1:]
            if (
                type(count) is not int or not 0 <= count <= 9_007_199_254_740_991
                or not isinstance(fields, list) or not isinstance(columns, list) or len(fields) != len(columns)
            ):
                invalid("Invalid snapshot column table.")
            keys = [string(index) for index in fields]
            if len(set(keys)) != len(keys):
                invalid("Snapshot table has duplicate keys.")
            rows = [{} for _ in range(count)]
            for key, encoded in zip(keys, columns):
                for row, child in zip(rows, decode_column(encoded, count, depth + 1)):
                    if child is not missing:
                        row[key] = child
            return rows
        invalid("Unknown encoded snapshot node tag or shape.")

    def decode_column(value, count, depth):
        if not isinstance(value, list) or not value or type(value[0]) is not int:
            invalid("Invalid encoded snapshot column.")
        tag = value[0]
        if tag == 0 and len(value) == 2:
            return [decode(value[1], depth) for _ in range(count)]
        if tag == 1 and len(value) == 2 and isinstance(value[1], list) and len(value[1]) == count:
            return [decode(child, depth) for child in value[1]]
        if tag == 2 and len(value) == 2 and isinstance(value[1], list):
            result = []
            for run in value[1]:
                if (
                    not isinstance(run, list) or len(run) != 2 or type(run[0]) is not int
                    or not 1 <= run[0] <= count - len(result)
                ):
                    invalid("Invalid snapshot run length.")
                result.extend(decode(run[1], depth) for _ in range(run[0]))
            if len(result) != count:
                invalid("Snapshot runs do not cover the complete table.")
            return result
        if tag == 3 and len(value) == 3 and isinstance(value[2], list):
            overrides = {}
            for pair in value[2]:
                if (
                    not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                    or not 0 <= pair[0] < count or pair[0] in overrides
                ):
                    invalid("Invalid snapshot sparse position.")
                overrides[pair[0]] = pair[1]
            return [decode(overrides.get(index, value[1]), depth) for index in range(count)]
        invalid("Unknown encoded snapshot column tag or shape.")

    if document["encoding"] == "dictionary-columns-v2":
        _check_snapshot_expansion(document["data"], strings)
    restored = legacy(document["data"]) if document["encoding"] == "dictionary-columns-v1" else decode(document["data"])
    if not isinstance(restored, dict):
        invalid("Restored snapshot must be an object.")
    return restored


_TONES = {
    "critical": "crit", "high": "high", "medium": "med", "low": "low", "informational": "info",
    "immediate review": "crit", "high priority": "high", "verify coverage": "med", "no observed gap": "info",
    "failed": "crit", "passed": "ok", "healthy": "ok", "complete": "ok", "partial": "med", "unavailable": "high",
}


def _rich_sections(snapshot):
    esc = lambda value: html.escape(str(value) if value is not None else "Unknown", quote=True)
    number = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    pill = lambda value, prefix="", extra="": (
        '<span class="pill ' + extra + _TONES.get(str(value).casefold(), "muted") + '">'
        + esc(prefix + ("Unknown" if value is None else str(value))) + "</span>"
    )
    breakable = lambda value: re.sub(r"([/._])", r"\1<wbr>", esc(value))

    def table(headers, rows, pills=(), plain=False, label=""):
        numeric = {i for i in range(len(headers)) if rows and all(number(r[i]) or r[i] is None for r in rows)
                   and any(number(r[i]) for r in rows)}
        cell = lambda i, v: (pill(v) if i in pills and v not in (None, "") else esc(v))
        return (
            '<div class="table-wrap' + (" plain" if plain else "") + '" data-page="25" tabindex="0" role="region" aria-label="'
            + esc(label or headers[0] + " table") + ', horizontally scrollable"><table><thead><tr>'
            + "".join('<th scope="col"' + (' class="n"' if i in numeric else "") + ">" + esc(h) + "</th>"
                      for i, h in enumerate(headers))
            + "</tr></thead><tbody>" + ("".join(
                "<tr>" + "".join(("<td class=\"n\">" if i in numeric else "<td>") + cell(i, v) + "</td>"
                                 for i, v in enumerate(row)) + "</tr>" for row in rows
            ) or '<tr><td class="nil" colspan="' + str(len(headers)) + '">No rows returned by this source.</td></tr>')
            + "</tbody></table></div>"
        )

    def head(level, anchor, title, note, tools=""):
        return (
            '<div class="sh' + (" sh3" if level == 3 else "") + '"><div><h' + str(level)
            + (' id="' + anchor + '"' if anchor else "") + ">" + title + "</h" + str(level) + "><p>" + note
            + "</p></div>" + ('<div class="tools">' + tools + "</div>" if tools else "") + "</div>"
        )

    export = lambda key, label: (
        '<button type="button" class="btn ghost dl" data-export-section="' + key + '">' + label + "</button>"
    )
    scalar = lambda value: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    def observed(observations):
        if not isinstance(observations, dict):
            return scalar(observations)
        parts = [
            key + ": " + (", ".join(f + " " + scalar(v) for f, v in value.items()) if isinstance(value, dict)
                          else scalar(value))
            for key, value in observations.items() if value not in (None, "", [], {})
        ]
        return "; ".join(parts) or "None returned"

    summary = snapshot["summary"]
    statuses = summary["recommendation_status_counts"]
    source_lookup = {s["name"]: s for s in snapshot["sources"]}

    def availability(name):
        return source_lookup.get(name, {}).get("status", "unavailable")

    simulated = snapshot["provenance"] == "SIMULATED"
    scores = snapshot["posture"]["scores"]
    score = next((s for s in scores if s.get("name") == "ascScore"), scores[0] if scores else {})
    percentage = score.get("percentage")
    score_label = f"{percentage * 100:.2f}%" if percentage is not None else "Unknown"
    context_label = "SIMULATED illustrative posture" if simulated else "Subscription posture"
    executive = [
        (context_label + (" · illustrative baseline ratio" if simulated else " · classic Secure Score"), score_label,
         "SIMULATED healthy baseline share, not native Defender Secure Score." if simulated
         else "Observed subscription context, not an Arc-only score."),
        ("Unhealthy recommendation records", statuses.get("Unhealthy", 0),
         f"{summary['distinct_recommendations']} distinct definitions; records are resource/recommendation pairs."),
        ("Attack paths · context / Arc-related",
         f"{summary['attack_paths_subscription_context']} / {summary['attack_paths_arc_related']}"
         if availability("attack_paths") == "complete" else "Unknown",
         "Observed graph association only. Illustrative synthetic chains are not customer topology."),
        ("Embedded CVE evidence", summary["embedded_cve_records"],
         f"{summary['distinct_embedded_cves']} distinct IDs; zero standalone subassessments is not zero CVEs."),
    ]
    def bar_list(counts, order):
        names = [r for r in order if counts.get(r)] + sorted(r for r in counts if r not in order and counts[r])
        widest = max([counts[r] for r in names] or [1])
        return "".join(
            '<li class="brow"><span><i class="sw ' + _TONES.get(r.casefold(), "muted") + '"></i>' + esc(r)
            + '</span><span class="bt"><i class="' + _TONES.get(r.casefold(), "muted") + '" style="width:'
            + f"{max(2.0, counts[r] * 100 / widest):.1f}" + '%"></i></span><b>' + esc(counts[r]) + "</b></li>"
            for r in names
        ) or '<li class="empty">None in the collected scope; not zero-risk assurance.</li>'

    unhealthy = [f for f in snapshot["findings"] if f["category"] == "Recommendation" and _is_actionable(f)]
    risk_bars = bar_list(summary.get("recommendation_risk_counts") or {}, RISKS[1:])
    technical_bars = bar_list(Counter(f["technical_severity"] for f in unhealthy), SEVERITIES[1:])
    status_chips = "".join("<span>" + esc(k) + " <b>" + esc(v) + "</b></span>" for k, v in sorted(statuses.items()))
    upper = [
        '<section id="posture" aria-labelledby="posture-h">' + head(
            2, "posture-h", "Posture and risk",
            "Native Defender risk and technical severity are independent. Healthy / Unhealthy / NotApplicable "
            "statuses are retained; counts never combine them as active risk. Retrieval time is not evaluation freshness.")
        + '<div class="grid2"><div class="card"><h3>Subscription context</h3><p class="sub">'
        + ("SIMULATED context for the demo fixture." if simulated else "Observed for the configured subscription.")
        + '</p><dl class="tiles">'
        + "".join('<div class="tile"><dt>' + esc(label) + '</dt><dd class="v">' + esc(value) + '</dd><dd class="n">'
                  + esc(note) + "</dd></div>" for label, value, note in executive)
        + '</dl></div><div class="card"><h3>Unhealthy recommendation records</h3>'
        + '<p class="sub">The same ' + esc(len(unhealthy)) + " records seen through native <code>risk.level</code> "
        "and through technical severity: two independent dimensions.</p>"
        + '<h4 class="mini">Native risk</h4><ul class="bars">' + risk_bars + "</ul>"
        + '<h4 class="mini">Technical severity</h4><ul class="bars">' + technical_bars + "</ul>"
        + '<p class="chips status-chips"><span class="k">Recommendation statuses</span>'
        + (status_chips or "<span>None returned</span>") + "</p></div></div>"
        + head(3, "", "Secure Score controls · subscription context",
               "Potential gain is control max minus current, not the guaranteed gain from one host. Control counts "
               "span the subscription; score availability: " + esc(availability("subscription_secure_score")) + ".",
               export("controls", "Export controls CSV"))
        + table(
            ("Control", "Current / max", "Potential gain", "Healthy", "Unhealthy", "Not applicable"),
            [(c["title"], f"{c['current']} / {c['maximum']}", c["potential_score_gain"],
              c["healthy"], c["unhealthy"], c["not_applicable"])
             for c in snapshot["posture"]["controls"]], label="Secure Score controls",
        ),
    ]
    if snapshot["posture"]["risk_score_observations"]:
        upper.append(
            '<details class="more"><summary>Native risk-score observations (no invented percentage)</summary>'
            + table(("Category", "Native numerator", "Native denominator"), [
                (r["assessment_category"], r["native_numerator"], r["native_denominator"])
                for r in snapshot["posture"]["risk_score_observations"]
            ], plain=True, label="Native risk-score observations")
            + "<p>These opaque native values are not converted into a percentage.</p></details>"
        )
    upper.append("</section>")
    upper.append(
        '<section id="attack-paths" aria-labelledby="paths-h">' + head(
            2, "paths-h", "Illustrative simulated attack chains" if simulated else "Observed Defender attack paths",
            ("Fictional Arc on-premises/GCP teaching chains, not Defender detections or customer topology."
             if simulated else
             "Actual fixed-subscription context, not Arc-only paths. An empty edge set is preserved; no hops are invented.")
            + " Source: " + esc(availability("attack_paths")) + ".", export("attack_paths", "Export attack paths CSV"))
        + '<div class="paths">'
    )
    for path in snapshot["attack_paths"]:
        lookup = {node["entity_id"]: node for node in path["entities"]}
        nodes = "".join(
            '<div class="graph-node"><strong>' + esc(node["name"]) + "</strong><span>"
            + breakable(node["type"]) + "</span></div>" for node in path["entities"]
        )
        edges = "".join(
            "<li>" + esc(lookup[edge["source"]]["name"]) + " &rarr; "
            + esc(lookup[edge["target"]]["name"]) + ": " + esc(edge["label"]) + "</li>"
            for edge in path["edges"]
        ) or "<li>No connections returned by this source; entry point and target may be the same entity.</li>"
        related = [r for r in snapshot["subscription_recommendations"] if r["finding_id"].casefold() in path["assessment_ids"]]
        upper.append(
            '<article class="path-panel"><div class="path-head"><h3>' + esc(path["title"]) + "</h3>"
            + pill(path["risk_level"], "Native risk: ", "dot ") + '</div><p class="path-meta">'
            + esc(path["association"]) + " · " + esc(path["scope"]) + '</p><p class="path-ends">Entry: <b>'
            + esc(path["entry_point"]["name"]) + "</b> · Target: <b>" + esc(path["target"]["name"]) + "</b></p>"
            + '<div class="graph-nodes" role="group" aria-label="Observed graph entities">' + nodes + "</div>"
            + '<details><summary>Connections, insights and recommended breaks</summary><ul class="edges">' + edges
            + '</ul><p class="chips"><span class="k">Risk factors</span>'
            + ("".join("<span>" + esc(f) + "</span>" for f in path["risk_factors"]) or "<span>None returned</span>")
            + "</p><p>" + esc(path["story"]) + "</p><p><strong>Break / review:</strong> " + esc(path["remediation"]) + "</p>"
            + table(("Insight", "Observed values"), [
                (i["title"], observed(i["observations"])) for i in path["insights"]
            ], plain=True, label="Attack path insights")
            + "<p>Linked assessment IDs: " + str(len(path["assessment_ids"]))
            + "; details available: " + str(len(related)) + ".</p>"
            + table(("Linked recommendation", "Status", "Native risk", "Remediation"), [
                (r["title"], r["status"], r["risk_level"], r["remediation"]) for r in related
            ], pills=(2,), plain=True, label="Linked recommendations") + "</details></article>"
        )
    if not snapshot["attack_paths"]:
        upper.append('<p class="empty card">No paths returned. Unavailable is Unknown, not proof of no exploitable path.</p>')
    upper.append("</div></section>")
    kinds = {}
    for row in snapshot["inventory"]:
        kind = row.get("resource_kind", "Arc servers")
        value = kinds.setdefault(kind, {"resources": 0, "unhealthy": 0, "high": 0})
        value["resources"] += 1
        value["unhealthy"] += row["recommendation_status_counts"].get("Unhealthy", 0) > 0
        value["high"] += sum(row["recommendation_risk_counts"].get(k, 0) for k in ("High", "Critical"))
    lower = [
        '<section id="resource-detail" aria-labelledby="resources-h">' + head(
            2, "resources-h", "Resource posture by service",
            "ARM inventory and Defender indexed-only dependent assets are labeled separately. "
            "No assessment is not a healthy-resource verdict.")
        + table(("Service group", "Inventory resources", "Resources with unhealthy recommendations",
                 "High/Critical native-risk records"),
                [(k, v["resources"], v["unhealthy"], v["high"]) for k, v in sorted(kinds.items())],
                label="Resource posture by service")
        + '<div class="picker"><label for="detail-resource">Resource details</label><select id="detail-resource">'
        + "".join('<option value="' + esc(r["resource_id"]) + '">' + esc(r["server_name"])
                  + " · " + esc(r.get("resource_kind", "Arc servers")) + "</option>" for r in snapshot["inventory"])
        + '</select><p class="hint">Select a resource, or a name in the ledger, to inspect ownership, recommendations, '
        'patches and software.</p></div><div id="detail-content" class="resource-panel" aria-live="polite"></div></section>',
        '<section id="software" aria-labelledby="software-h">' + head(
            2, "software-h", "Software and embedded vulnerability evidence",
            "Software source: " + esc(availability("software_inventory"))
            + ". Inventory rows are observations, not a complete installed-software audit of hosts with no rows. "
            "Embedded CvesDetails are kept separately from standalone subassessments.",
            export("software", "Export software CSV") + export("vulnerabilities", "Export source CVE evidence CSV"))
        + table(("Resource", "Software", "Version", "Vendor", "Known vulnerabilities", "Association"), [
            (s["server_name"], s["software_name"], s["version"], s["vendor"], s["known_vulnerabilities"], s["association"])
            for s in snapshot["software"]
        ], label="Software inventory")
        + '<details class="more"><summary>Embedded vulnerability counts and provenance</summary><p class="chips">'
        + ("".join(pill(k, "", "dot ").replace("</span>", " · " + esc(v) + "</span>")
                   for k, v in _counts(snapshot["vulnerabilities"], "technical_severity").items())
           or "<span>None returned</span>")
        + "</p><p>Occurrences: " + str(len(snapshot["vulnerabilities"])) + "; distinct IDs: "
        + str(summary["distinct_embedded_cves"])
        + ". Real CVEs only when returned by the live source; simulation uses DEMO-VA IDs.</p></details></section>",
        '<section id="compliance" aria-labelledby="compliance-h">' + head(
            2, "compliance-h", "Compliance observations, not certification",
            "Passed, failed, skipped and unsupported controls remain separate. Scope is subscription; "
            "no automatic ENS/GDPR certification is claimed.",
            export("compliance", "Export compliance controls CSV"))
        + table(("Standard", "State", "Passed", "Failed", "Skipped", "Unsupported"), [
            (r["name"], r["state"], r.get("passedControls"), r.get("failedControls"),
             r.get("skippedControls"), r.get("unsupportedControls"))
            for r in snapshot["compliance"]["standards"]
        ], pills=(1,), label="Compliance standards")
        + '<details class="more"><summary>Observed compliance controls and assessments</summary>'
        + table(("Control", "State", "Description", "Passed / failed / skipped assessments"), [
            (r["name"], r["state"], r.get("description", ""),
             f"{r.get('passedAssessments')} / {r.get('failedAssessments')} / {r.get('skippedAssessments')}")
            for r in snapshot["compliance"]["controls"]
        ], pills=(1,), plain=True, label="Compliance controls")
        + "<p>Assessment records: " + str(len(snapshot["compliance"]["assessments"])) + ".</p></details></section>",
    ]
    plans = head(
        3, "", "Observed protection plans",
        "Configured paid plans do not prove runtime health or all feature coverage. "
        "ACA source recommendations do not prove Defender for Containers runtime protection.",
    ) + table(("Plan", "Tier", "Subplan", "Source coverage"), [
        (r["name"], r["pricing_tier"], r["sub_plan"], r["coverage"]) for r in snapshot["plans"]
    ], label="Observed protection plans")
    return {"upper": "".join(upper), "lower": "".join(lower), "plans": plans}


def _render_html(snapshot):
    escape = lambda value: html.escape("" if value is None else str(value), quote=True)
    simulated = snapshot["provenance"] == "SIMULATED"
    title = "SIMULATED hybrid posture" if simulated else "Defender for Cloud posture"
    subtitle = (
        "Retail-inspired on-premises / GCP demo. Synthetic assumptions, never customer measurements."
        if simulated else "Read-only security evidence across the configured subscription's Azure services and dependent assessed assets."
    )
    notice = (
        "SIMULATED DEMO · 200 fictional servers · no Azure calls, tokens or customer measurements"
        if simulated else "LIVE SUBSCRIPTION SNAPSHOT · native risk is separate from severity · indexed evidence can lag"
    )
    pill = lambda value, prefix="", extra="": (
        '<span class="pill ' + extra + _TONES.get(str(value).casefold(), "muted") + '">'
        + escape(prefix + str(value)) + "</span>"
    )
    source_rows = []
    for source in snapshot["sources"]:
        errors = "; ".join(e["message"] for e in source.get("errors", []))
        source_rows.append(
            "<tr><td>" + escape(source["name"]) + "</td><td>" + pill(source["status"]) + "</td><td>"
            + escape(source["records"] if source.get("records") is not None else "Unknown")
            + "</td><td>" + escape(source["note"]) + (" " + escape(errors) if errors else "")
            + "</td></tr>"
        )
    action_rows = "".join(
        '<li><div><h3>' + escape(action["title"]) + "</h3><p>" + escape(action["reason"])
        + '</p></div><div class="act-meta">' + pill(action["priority"], "", "dot ") + "<span><b>"
        + str(action["affected_resources"]) + "</b> affected resources</span>"
        + ('<span class="src">Source: ' + re.sub(r"([.])", r"\1<wbr>", escape(", ".join(action.get("sources", []))))
           + "</span>" if action.get("sources") else "") + "</div></li>"
        for action in snapshot["actions"]
    ) or '<li class="none">No action derived from the collected evidence; this is not zero-risk assurance.</li>'
    capabilities = "".join(
        "<tr><th scope=\"row\">" + escape(item["feature"]) + "</th><td>" + escape(item["scope"])
        + "</td><td>" + escape(item["caveat"]) + "</td></tr>" for item in CAPABILITY_MATRIX
    )
    summary = snapshot["summary"]
    inventory = snapshot["inventory"]
    arc_total = sum(r.get("resource_type", "microsoft.hybridcompute/machines") == "microsoft.hybridcompute/machines"
                    for r in inventory)
    metric_definitions = [
        ("Arc demo servers" if simulated else "Resources in evidence", len(inventory), "",
         "ARM inventory / indexed-only assets are distinguished; no unverified portal parity"),
        ("Connected" if simulated else "Arc connected", summary["connected"], f"of {arc_total} Arc",
         "Arc connectivity only; not reachability of the whole compute estate"),
        ("MDE extension succeeded", summary["mde_extension_succeeded"], f"of {summary['servers']} servers",
         "Observed Arc/Compute provisioning, not independently verified sensor health"),
        ("Sensor verified healthy", summary["sensor_verified_healthy"], f"of {summary['servers']} servers",
         "Unknown is not healthy"),
        ("Effective Servers P2" if simulated else "Arc effective Servers P2", summary["servers_p2"], f"of {arc_total} Arc",
         "Per-Arc pricing reads only; broader subscription plans are separate, not health proof"),
    ]
    metrics = "".join(
        '<div class="kpi"><dt>' + escape(label) + '</dt><dd class="v">' + str(count)
        + ("<small>" + escape(scope) + "</small>" if scope else "") + '</dd><dd class="n">' + escape(note) + "</dd></div>"
        for label, count, scope, note in metric_definitions
    )
    levels = (("Immediate review", "crit"), ("High priority", "high"), ("Verify coverage", "med"), ("No observed gap", "info"))
    verdicts = {"Immediate review": "Action required", "High priority": "Needs attention",
                "Verify coverage": "Verify coverage", "No observed gap": "No observed gap"}
    priorities = summary.get("by_priority") or {}
    counted = [(name, tone, priorities.get(name, 0)) for name, tone in levels if priorities.get(name)]
    total = sum(count for _, _, count in counted)
    verdict, verdict_tone = (verdicts[counted[0][0]], counted[0][1]) if counted else ("No resources in evidence", "info")
    verdict_note = (
        "Resources: " + " · ".join(f"{count} {name.lower()}" for name, _, count in counted) + "."
        if counted else "Nothing returned for the configured scope; not proof of zero risk."
    )
    if verdict == "No observed gap":
        verdict_note += " No observed gap is not zero-risk assurance."
    distribution = (
        '<div class="dist"><p class="cap"><span>Resources by review priority</span><span>' + str(total)
        + ' resources</span></p><div class="track" role="img" aria-label="Resources by review priority: '
        + escape(verdict_note) + '">' + "".join(
            '<i class="' + tone + '" style="width:' + f"{count * 100 / total:.2f}" + '%"></i>' for _, tone, count in counted
        ) + '</div><p class="legend">' + "".join(
            '<span><i class="' + tone + '"></i>' + escape(name) + " <b>" + str(count) + "</b></span>"
            for name, tone, count in counted
        ) + "</p></div>" if total else ""
    )
    statuses = summary["recommendation_status_counts"]
    paths_known = any(s["name"] == "attack_paths" and s["status"] == "complete" for s in snapshot["sources"])
    keyline = (
        "<b>" + str(len(inventory)) + "</b> resources in evidence, " + str(summary["servers"]) + " of them servers · <b>"
        + str(statuses.get("Unhealthy", 0)) + "</b> unhealthy recommendation records · <b>"
        + (str(summary["attack_paths_subscription_context"]) + "</b> attack paths ("
           + str(summary["attack_paths_arc_related"]) + " Arc-related)" if paths_known else "Unknown</b> attack paths")
        + " · <b>" + str(summary["embedded_cve_records"]) + "</b> embedded CVE occurrences."
    )
    sections = _rich_sections(snapshot)
    nav = "".join('<a href="#' + anchor + '">' + label + "</a>" for anchor, label in (
        ("actions", "Actions"), ("posture", "Posture"), ("attack-paths", "Attack paths"), ("evidence", "Evidence"),
        ("resource-detail", "Resources"), ("software", "Software / CVEs"), ("compliance", "Compliance"),
        ("source-coverage", "Sources"),
    ))
    replacements = {
        "TITLE": escape(title), "SUBTITLE": escape(subtitle), "NOTICE": escape(notice),
        "NOTICE_CLASS": "sim" if simulated else "live",
        "PROVENANCE": escape(snapshot["provenance"]), "TIME": escape(snapshot["reference_utc"]),
        "SCOPE": escape(snapshot["scope"]["description"]), "COVERAGE": escape(snapshot["coverage"]["status"]),
        "LOGO": (
            '<img class="brand-logo" src="data:image/png;base64,' + LOGO_BASE64
            + '" alt="Company logo (placeholder)" width="520" height="84">' if simulated
            else '<div class="neutral-brand">Security evidence<br><span>Defender for Cloud + SRE Agent</span></div>'
        ),
        "BODY_CLASS": "sim" if simulated else "live", "NAV": nav, "KEYLINE": keyline,
        "SOURCES_DONE": str(sum(s["status"] == "complete" for s in snapshot["sources"])),
        "SOURCES_TOTAL": str(len(snapshot["sources"])),
        "VERDICT": escape(verdict), "VERDICT_TONE": verdict_tone, "VERDICT_NOTE": escape(verdict_note),
        "DIST": distribution, "UPPER": sections["upper"], "LOWER": sections["lower"], "PLANS": sections["plans"],
        "PRINT_TITLE": re.sub(r"[^0-9A-Za-z :.\-]", "", title + " - " + snapshot["provenance"] + " - "
                              + str(snapshot["reference_utc"]).replace("T", " ").replace("Z", " UTC")),
        "METRICS": metrics, "ACTIONS": action_rows, "INVENTORY": "",
        "FINDINGS": "", "SOURCES": "".join(source_rows), "CAPABILITIES": capabilities,
        "DATA": _safe_json(_pack_snapshot(snapshot)),
        "MAX_DECODED_NODES": str(MAX_DECODED_NODES),
        "MAX_DECODED_STRING_UNITS": str(MAX_DECODED_STRING_UNITS),
        "UNKNOWN_SOURCES": str(summary["unknown_or_partial_sources"]),
        "QUALIFICATION": escape(summary["qualification"]), "REFERENCE": DEFENDER_REFERENCE,
    }
    document = r"""<!doctype html>
<html lang="en">
<!-- Azure SRE Agent report family: slim bar, verdict-first hero, KPI cards, prioritised actions,
one evidence explorer with shared filters, then coverage and boundaries. LIVE uses the neutral navy
theme; SIMULATED keeps its green theme, serif headline and placeholder logo. Read-only, offline. -->
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'">
<title>@@TITLE@@</title>
<style>
:root {--ink:#20352b;--title:#0d2a1d;--muted:#4a6155;--line:#d9e5dd;--line2:#b8cbbf;--paper:#f2f6f3;
 --soft:#edf3ef;--hover:#f6faf7;--brand:#0a3022;--accent:#176347;--link:#14603f;--focus:#b54708;
 --display:"Palatino Linotype",Georgia,serif;--sans:"Aptos","Segoe UI",system-ui,-apple-system,sans-serif;
 --hero-ink:#f3faf5;--hero-muted:#cfe4d6;--hero-line:rgba(222,255,233,.26);
 --shadow:0 1px 2px rgba(16,40,28,.05),0 4px 14px rgba(16,40,28,.06);
 --crit:#b42318;--crit-bg:#fee4e2;--crit-bar:#d92d20;--high:#b93815;--high-bg:#ffead5;--high-bar:#ef6820;
 --med:#93370d;--med-bg:#fef0c7;--med-bar:#f79009;--low:#175cd3;--low-bg:#d1e9ff;--low-bar:#2e90fa;
 --info:#344054;--info-bg:#eaecf0;--info-bar:#98a2b3;--ok:#067647;--ok-bg:#dcfae6;--ok-bar:#17b26a}
body.live {--ink:#1d2e48;--title:#0f2240;--muted:#4a5d78;--line:#dbe3ee;--line2:#bfcde0;--paper:#f2f5f9;
 --soft:#edf2f8;--hover:#f6f9fc;--brand:#13294b;--accent:#174b91;--link:#175cd3;--focus:#175cd3;
 --display:var(--sans);--hero-ink:#f3f7ff;--hero-muted:#c9d7ed;--hero-line:rgba(214,228,255,.26)}
* {box-sizing:border-box} [hidden] {display:none!important}
html {scrollbar-color:var(--line2) transparent;-webkit-text-size-adjust:100%}
body {margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);
 font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
::selection {background:#d1e9ff;color:#101828}
button,input,select {font:inherit;color:inherit} button {cursor:pointer}
a {color:var(--link);text-underline-offset:3px} :focus-visible {outline:3px solid var(--focus);outline-offset:2px}
code,.mono {font:12.5px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace}
.skip {position:absolute;left:12px;top:-80px;z-index:40;border:2px solid var(--accent);padding:10px 14px;border-radius:10px;background:#fff;
 color:var(--title);font-weight:700} .skip:focus {top:10px}
.bar {position:sticky;top:0;z-index:30;display:flex;flex-wrap:wrap;align-items:center;gap:6px 20px;
 padding:10px clamp(16px,4vw,40px);background:#fff;border-bottom:1px solid var(--line)}
.brand {display:flex;align-items:center;min-width:0;flex:none}
.brand-logo {display:block;width:auto;height:34px;max-width:230px}
.neutral-brand {position:relative;padding-left:42px;font-size:15px;font-weight:700;line-height:1.3;color:var(--title)}
.neutral-brand::before {content:"";position:absolute;left:0;top:50%;width:32px;height:32px;margin-top:-16px;
 border-radius:9px;background:var(--accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z'/%3E%3Cpath d='m9 12 2 2 4-4'/%3E%3C/svg%3E") center/19px no-repeat}
.neutral-brand span {font-size:12.5px;font-weight:600;color:var(--muted)}
.bar nav {display:flex;gap:2px;min-width:0;overflow-x:auto;scrollbar-width:none}
.bar nav a {padding:8px 11px;border-radius:9px;font-size:14px;font-weight:600;color:var(--muted);text-decoration:none;white-space:nowrap}
.bar nav a:hover {background:var(--soft);color:var(--title)} .bar nav a:focus-visible {outline-offset:-3px}
.acts {display:flex;align-items:center;gap:10px;margin-left:auto;flex:none}
.tag {padding:5px 11px;border:1px solid var(--line2);border-radius:999px;font-size:12.5px;font-weight:600;color:var(--muted);white-space:nowrap}
.btn {display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;padding:0 15px;
 border:1px solid var(--accent);border-radius:10px;background:var(--accent);color:#fff;font-size:14px;font-weight:700;
 text-decoration:none;white-space:nowrap;transition:background-color .15s ease}
.btn:hover {background:var(--brand);border-color:var(--brand)} .btn.ghost {background:#fff;border-color:var(--line2);color:var(--title)}
.btn.ghost:hover {background:var(--soft)}
.btn.dl::before,.btn.pr::before {content:"";width:16px;height:16px;flex:none;background:currentColor;
 -webkit-mask:var(--icon) center/contain no-repeat;mask:var(--icon) center/contain no-repeat}
.btn.dl {--icon:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 4v11m-5-5 5 5 5-5M5 20h14'/%3E%3C/svg%3E")}
.btn.pr {--icon:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v7H7z'/%3E%3C/svg%3E")}
.hero {position:relative;overflow:hidden;padding:clamp(28px,4.4vw,52px) clamp(16px,4vw,40px) 96px;color:var(--hero-ink);
 background:linear-gradient(120deg,#0a3022 0%,#0c4e33 55%,#176347 100%)}
.live .hero {background:linear-gradient(120deg,#0f2240 0%,#163a63 62%,#174b91 100%)}
.hero::after {content:"";position:absolute;width:760px;height:760px;right:-220px;top:-380px;border-radius:50%;
 background:radial-gradient(closest-side,rgba(255,255,255,.09),rgba(255,255,255,0));pointer-events:none}
.hero-in {position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px 48px;
 align-items:start;max-width:1320px;margin:0 auto}
.hero h1 {margin:0 0 12px;font:700 clamp(32px,3.5vw,44px)/1.08 var(--display);letter-spacing:-.02em;text-wrap:balance;color:#fff}
.lead {max-width:62ch;margin:0 0 10px;font-size:17px;line-height:1.5}
.sum {max-width:75ch;margin:0;color:var(--hero-muted)} .sum b {color:#fff}
.meta {display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.meta span {padding:5px 11px;border:1px solid var(--hero-line);border-radius:999px;font-size:12.5px;color:var(--hero-muted);white-space:nowrap}
.meta .on {border-color:rgba(255,255,255,.55);color:#fff;font-weight:700}
.verdict {padding:20px 22px;border:1px solid var(--hero-line);border-radius:18px;background:rgba(0,12,8,.28)}
.verdict .k {margin:0 0 4px;font-size:13px;font-weight:600;color:var(--hero-muted)}
.verdict strong {display:block;font:700 28px/1.15 var(--display);color:#fff}
.verdict strong.crit {color:#fda29b} .verdict strong.high {color:#fdb022} .verdict strong.med {color:#fedf89}
.verdict strong.ok {color:#a6f4c5} .verdict strong.info {color:#fff}
.verdict p {margin:8px 0 0;font-size:14px;color:var(--hero-muted)} .verdict .cov {padding-top:10px;border-top:1px solid var(--hero-line)}
.verdict .cov b {color:#fff}
.dist {grid-column:1/-1} .dist .cap {display:flex;justify-content:space-between;gap:12px;margin:0 0 8px;font-size:13px;color:var(--hero-muted)}
.track {display:flex;height:12px;overflow:hidden;border-radius:999px;background:var(--hero-line)} .track i {display:block;height:100%}
.legend {display:flex;flex-wrap:wrap;gap:6px 20px;margin:10px 0 0;font-size:13.5px;color:var(--hero-muted)}
.legend span {display:inline-flex;align-items:center;gap:7px} .legend b {color:#fff}
.legend i {display:inline-block;width:10px;height:10px;border-radius:3px}
.track .crit,.legend .crit,.bt .crit,.sw.crit {background:var(--crit-bar)} .track .high,.legend .high,.bt .high,.sw.high {background:var(--high-bar)}
.track .med,.legend .med,.bt .med,.sw.med {background:var(--med-bar)} .track .low,.legend .low,.bt .low,.sw.low {background:var(--low-bar)}
.track .info,.legend .info,.bt .info,.sw.info,.bt .muted,.sw.muted {background:var(--info-bar)}
.page {max-width:1400px;margin:0 auto;padding:0 clamp(16px,4vw,40px) 40px}
.kpis {position:relative;z-index:2;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:-58px 0 0}
.kpi {display:flex;flex-direction:column;min-width:0;padding:18px 20px;border:1px solid var(--line);border-radius:16px;
 background:#fff;box-shadow:var(--shadow)}
.kpi dt {order:2;margin-top:10px;font-size:14px;font-weight:700;color:var(--title)}
.kpi dd {margin:0} .kpi .v {order:1;font:700 38px/1 var(--display);letter-spacing:-.02em;color:var(--title)}
.kpi .v small {margin-left:6px;font:600 14px/1 var(--sans);letter-spacing:0;color:var(--muted)}
.kpi .n {order:3;margin-top:6px;font-size:13px;line-height:1.45;color:var(--muted)}
.notice {display:flex;gap:10px;align-items:flex-start;margin:18px 0 0;padding:11px 16px;border-radius:12px;font-size:14px;font-weight:700}
.notice::before {content:"";width:18px;height:18px;margin-top:1px;flex:none;background:currentColor;
 -webkit-mask:var(--icon) center/contain no-repeat;mask:var(--icon) center/contain no-repeat;
 --icon:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3 2 20h20zM12 10v4M12 17h.01'/%3E%3C/svg%3E")}
.notice.sim {border:1px solid #fedf89;background:repeating-linear-gradient(135deg,#fffaeb 0 12px,#fef0c7 12px 24px);color:#7a2e0e}
.notice.live {border:1px solid var(--line);background:#fff;color:var(--title)}
.notice.live::before {--icon:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M12 11v5M12 8h.01'/%3E%3C/svg%3E")}
.scope {max-width:75ch;margin:8px 0 0;font-size:14px;color:var(--muted)}
section {margin-top:46px;scroll-margin-top:84px}
.sh {display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:10px 24px;margin:0 0 14px}
.sh h2 {margin:0;font:700 24px/1.2 var(--display);letter-spacing:-.01em;color:var(--title)}
.sh h3 {margin:0;font-size:18px;line-height:1.3;color:var(--title)} .sh3 {margin-top:30px;scroll-margin-top:84px}
.sh p {max-width:75ch;margin:5px 0 0;font-size:14px;color:var(--muted)}
.tools {display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.card {min-width:0;padding:20px 22px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow)}
.card h3 {margin:0 0 4px;font-size:17px;color:var(--title)} .card .sub {margin:0 0 14px;font-size:13.5px;color:var(--muted)}
.grid2 {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px}
.tiles {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px;margin:0}
.tile {padding:14px 16px;border-radius:12px;background:var(--soft)} .tile dt {font-size:13px;font-weight:700;color:var(--muted)}
.tile dd {margin:0} .tile .v {margin:6px 0 4px;font:700 28px/1.05 var(--display);color:var(--title)}
.tile .n {font-size:12.5px;line-height:1.45;color:var(--muted)}
.bars {display:grid;gap:9px;margin:0 0 8px;padding:0;list-style:none}
.card .mini {margin:16px 0 8px;font-size:13px;font-weight:700;color:var(--muted)}
.brow {display:grid;grid-template-columns:minmax(110px,32%) 1fr minmax(40px,auto);gap:12px;align-items:center;font-size:14px}
.brow b {text-align:right} .bt {height:12px;overflow:hidden;border-radius:999px;background:var(--soft)}
.bt i {display:block;height:100%;min-width:3px;border-radius:999px}
.sw {display:inline-block;width:9px;height:9px;margin-right:8px;border-radius:50%;vertical-align:1px}
.chips {display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0}
.chips span {padding:2px 9px;border-radius:8px;background:var(--soft);font-size:12.5px;overflow-wrap:anywhere}
.chips .k {padding-left:0;background:none;font-weight:700;color:var(--muted)}
.pill {display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:12.5px;font-weight:700;
 line-height:1.5;white-space:nowrap}
.pill.dot::before {content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.chips .pill {border-radius:999px}
.pill.crit {background:var(--crit-bg);color:var(--crit)} .pill.high {background:var(--high-bg);color:var(--high)}
.pill.med {background:var(--med-bg);color:var(--med)} .pill.low {background:var(--low-bg);color:var(--low)}
.pill.info {background:var(--info-bg);color:var(--info)} .pill.ok {background:var(--ok-bg);color:var(--ok)}
.pill.muted {background:var(--soft);color:var(--muted)} .pill.line {background:#fff;box-shadow:inset 0 0 0 1px var(--line2);color:var(--ink)}
.nil {color:var(--muted)}
.actions {margin:0;padding:4px 22px;list-style:none;counter-reset:act;border:1px solid var(--line);border-radius:16px;
 background:#fff;box-shadow:var(--shadow)}
.actions li {display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:6px 18px;align-items:start;padding:16px 0;
 border-top:1px solid var(--line)} .actions li:first-child {border-top:0}
.actions li::before {counter-increment:act;content:counter(act);display:grid;place-items:center;width:30px;height:30px;
 border-radius:50%;background:var(--soft);font-weight:700;color:var(--title)}
.actions li.none::before {content:none} .actions h3 {margin:3px 0 4px;font-size:16px;color:var(--title)}
.actions p {max-width:75ch;margin:0;font-size:14px;color:var(--muted)}
.act-meta {display:grid;justify-items:end;gap:5px;min-width:190px;font-size:13.5px;text-align:right}
.act-meta .src {max-width:32ch;font-size:12.5px;color:var(--muted)}
.paths {display:grid;gap:14px}
.path-panel {padding:18px 22px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow);overflow-wrap:anywhere}
.path-head {display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px}
.path-head h3 {margin:0;font-size:17px;color:var(--title)}
.path-meta {margin:6px 0 2px;font-size:13.5px;color:var(--muted)} .path-ends {margin:0 0 12px;font-size:14px}
.graph-nodes {display:flex;flex-wrap:wrap;gap:10px}
.graph-node {min-width:0;max-width:320px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--soft)}
.graph-node strong {display:block;font-size:14px;color:var(--title)}
.graph-node span {display:block;font:12.5px/1.45 ui-monospace,"Cascadia Mono",Consolas,monospace;color:var(--muted)}
details {margin-top:12px} summary {cursor:pointer;font-weight:700;color:var(--link)}
.path-panel details {padding-top:10px;border-top:1px solid var(--line)} .path-panel details p {max-width:90ch;font-size:14px}
.edges {margin:10px 0;padding-left:20px;font-size:14px} .edges li {margin:3px 0}
details.more {padding:12px 0 0} details.more p {font-size:14px}
.table-wrap {overflow-x:auto;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);
 background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/36px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/36px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) right/14px 100% no-repeat scroll,#fff}
.table-wrap.plain,.records .table-wrap {margin:12px 0;border-width:1px 0;border-radius:0;box-shadow:none}
table {width:100%;min-width:640px;border-collapse:collapse;font-size:13.5px}
#inventory-table {min-width:1080px} #findings-table {min-width:920px} #groups-table {min-width:780px}
caption {padding:10px 14px;caption-side:top;text-align:left;font-size:13px;color:var(--muted)}
th {padding:10px 14px;border-bottom:1px solid var(--line);background:var(--soft);color:var(--title);font-size:12.5px;
 font-weight:700;text-align:left;vertical-align:middle}
td {padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td,tbody tr:last-child th {border-bottom:0} tbody tr:hover {background:var(--hover)}
tbody th {background:transparent;font-size:13.5px;vertical-align:top}
td.n,th.n {text-align:right;white-space:nowrap} tr.pg {display:none}
th button {display:inline-flex;align-items:center;gap:6px;min-height:28px;padding:0;border:0;background:none;font-weight:700;color:inherit}
th button:hover {color:var(--link)}
th[aria-sort] button::after {content:"";border:5px solid transparent}
th[aria-sort=ascending] button::after {margin-top:-5px;border-bottom-color:currentColor}
th[aria-sort=descending] button::after {margin-top:5px;border-top-color:currentColor}
td small {display:block;font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
#findings-table td:last-child small {overflow-wrap:normal}
.rlink {padding:0;border:0;background:none;color:var(--link);font-weight:700;text-align:left;text-decoration:underline;
 text-decoration-color:var(--line2);text-underline-offset:3px;overflow-wrap:anywhere}
.rlink:hover {text-decoration-color:currentColor}
td details {margin-top:6px;max-width:70ch} td details p {margin:6px 0;font-size:13px;color:var(--muted)}
.more-row {display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin:10px 2px 0;
 font-size:13.5px;color:var(--muted)} .more-row p {margin:0}
.filters-card {padding:18px 20px}
.filters {display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px 16px}
.filters .wide {grid-column:span 2}
label {display:block;margin-bottom:6px;font-size:13px;font-weight:700;color:var(--title)}
input,select {width:100%;min-height:42px;padding:0 12px;border:1px solid var(--line2);border-radius:10px;background:#fff;color:var(--ink)}
input::placeholder {color:#5b6b63;opacity:1} .live input::placeholder {color:#5a6a80}
.fcount {margin:14px 0 0;padding-top:12px;border-top:1px solid var(--line);font-size:14px;color:var(--muted)}
.fcount output {font-weight:700;color:var(--title)}
.empty {margin:12px 0 0;color:var(--muted);font-size:14px}
details.records {margin-top:24px;padding:16px 20px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow)}
details.records > summary {font-size:15px} details.records .sh3 {margin-top:16px}
.picker {max-width:640px;margin-top:24px} .hint {margin:6px 0 0;font-size:13.5px;color:var(--muted)}
.resource-panel {margin-top:14px;padding:20px 22px;border:1px solid var(--line);border-radius:16px;background:#fff;
 box-shadow:var(--shadow);overflow-wrap:anywhere}
.rhead {display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px 20px}
.resource-panel h3 {margin:0;font-size:20px;color:var(--title)} .resource-panel h4 {margin:20px 0 4px;font-size:15px;color:var(--title)}
.rid {margin:6px 0 0;font:12.5px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;color:var(--muted);overflow-wrap:normal;word-break:normal}
.facts {display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,250px),1fr));gap:14px 24px;margin:18px 0 0;
 padding:16px 0 0;border-top:1px solid var(--line)}
.facts dt {font-size:12.5px;font-weight:700;color:var(--muted)} .facts dd {margin:3px 0 0;font-size:14px}
.flist {margin:8px 0 14px;padding:0;list-style:none;border-top:1px solid var(--line)}
.flist li {padding:12px 0;border-bottom:1px solid var(--line)} .flist strong {display:block;margin-bottom:6px;color:var(--title)}
.flist p {max-width:90ch;margin:6px 0 0;font-size:14px;color:var(--muted)}
.resource-panel > p {font-size:14px;color:var(--muted)}
footer {max-width:1400px;margin:0 auto;padding:26px clamp(16px,4vw,40px) 44px;font-size:13.5px;color:var(--muted)}
footer p {max-width:100ch;margin:0 0 8px}
.sim h1,.sim .sh h2,.sim .kpi .v,.sim .tile .v,.sim .verdict strong {font-family:"Palatino Linotype",Georgia,serif}
@media (prefers-reduced-motion:no-preference) {html {scroll-behavior:smooth}}
@media (prefers-reduced-motion:reduce) {* {transition:none!important}}
@media (max-width:1320px) {.bar nav {order:3;flex-basis:100%;margin:0 -8px} section,.sh3 {scroll-margin-top:124px}}
@media (max-width:1100px) {.kpis {grid-template-columns:repeat(3,minmax(0,1fr))} .hero-in {grid-template-columns:1fr}}
@media (max-width:760px) {.bar {position:static} .tag {display:none} .kpis {grid-template-columns:repeat(2,minmax(0,1fr))}
 .kpi .v {font-size:32px} .filters .wide {grid-column:auto} .actions li {grid-template-columns:auto minmax(0,1fr)}
 .act-meta {grid-column:2;justify-items:start;text-align:left} .brow {grid-template-columns:1fr auto} .brow .bt {grid-column:1/-1;grid-row:2}}
@media (max-width:440px) {.btn.pr .lbl {display:none} .btn.pr {padding:0 12px} .brand-logo {height:28px;max-width:170px}
 .neutral-brand {font-size:14px} .kpi {padding:14px 16px} .kpi .v {font-size:28px} .kpi .v small {display:block;margin:6px 0 0}}
@page {size:A4;margin:14mm 12mm 16mm;
 @bottom-left {content:"@@PRINT_TITLE@@";font:9px "Segoe UI",sans-serif;color:#667085}
 @bottom-right {content:"Page " counter(page) " of " counter(pages);font:9px "Segoe UI",sans-serif;color:#667085}}
@media print {* {-webkit-print-color-adjust:exact;print-color-adjust:exact}
 html,body {background:#fff;font-size:12px} .skip,.bar nav,.acts .btn,.tools,.filters-card,.more-row button,#groups-more,#findings-more,
 .picker,#detail-content,details.records,.pgnote {display:none!important}
 .bar {position:static;padding:0 0 10px;border:0} .hero {padding:22px 24px 72px;border-radius:14px} .hero::after {display:none}
 .hero-in {grid-template-columns:minmax(0,1fr) 230px;gap:14px 26px} .hero h1 {font-size:30px} .lead {font-size:13.5px}
 .verdict strong {font-size:21px} .page,footer {padding-left:0;padding-right:0}
 .kpis {grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:-52px} .kpi {padding:12px 14px;box-shadow:none}
 .kpi .v {font-size:26px} .kpi .v small {display:block;margin:5px 0 0} .kpi .n {font-size:12px} section {margin-top:22px}
 .sh {break-after:avoid;break-inside:avoid} .sh + * {break-before:avoid} .sh h2 {font-size:19px} .card,.kpi,.tile,.path-panel,.actions li,tr,.verdict,.graph-node,.brow {break-inside:avoid}
 .card,.path-panel,.actions,.table-wrap {box-shadow:none} .table-wrap {overflow:visible;background:#fff}
 table,#inventory-table,#findings-table,#groups-table {min-width:0!important;font-size:12px} th,td {padding:5px 7px}
 thead {display:table-header-group} tr.pg {display:table-row!important} .grid2 {grid-template-columns:1fr 1fr}
 details > summary {color:var(--title)}}
</style></head>
<body class="@@BODY_CLASS@@"><a class="skip" href="#main">Skip to report</a>
<header class="bar"><div class="brand">@@LOGO@@</div>
<nav aria-label="Report sections">@@NAV@@</nav>
<div class="acts"><span class="tag">Read-only</span><button class="btn pr" type="button" data-print aria-label="Print or save as PDF"><span class="lbl">Print / PDF</span></button></div></header>
<main id="main"><div class="hero"><div class="hero-in"><div class="hero-copy">
<h1>@@TITLE@@</h1><p class="lead">@@SUBTITLE@@</p><p class="sum">@@KEYLINE@@</p>
<div class="meta"><span class="on">@@PROVENANCE@@ data</span><span>Reference UTC: @@TIME@@</span>
<span>@@SOURCES_DONE@@ of @@SOURCES_TOTAL@@ sources complete</span></div></div>
<aside class="verdict" aria-label="Verdict"><p class="k">Verdict</p><strong class="@@VERDICT_TONE@@">@@VERDICT@@</strong>
<p>@@VERDICT_NOTE@@</p><p class="cov"><b>Coverage: @@COVERAGE@@</b> · @@UNKNOWN_SOURCES@@ source(s) unknown or partial.
Verify gaps before claiming protection.</p></aside>
@@DIST@@</div></div>
<div class="page">
<dl class="kpis" aria-label="Evidence counts">@@METRICS@@</dl>
<p class="notice @@NOTICE_CLASS@@">@@NOTICE@@</p><p class="scope">@@SCOPE@@</p>
<section id="actions" aria-labelledby="actions-h"><div class="sh"><div><h2 id="actions-h">What to review first</h2>
<p>Evidence-based ordering, not a fabricated risk score. Each action names its evidence source and affected resources.</p></div></div>
<ol class="actions">@@ACTIONS@@</ol></section>
@@UPPER@@
<section id="evidence" aria-labelledby="evidence-h"><div class="sh"><div><h2 id="evidence-h">Evidence explorer</h2>
<p>These filters drive the grouped recommendations, the resource ledger and the finding records below.
CSV buttons export every match, not only the rows on screen.</p></div>
<div class="tools"><button id="reset" class="btn ghost" type="button">Reset filters</button>
<button id="snapshot-json" class="btn ghost dl" type="button">Export full snapshot JSON</button></div></div>
<div class="card filters-card" role="search" aria-label="Evidence filters"><div class="filters">
<div class="wide"><label for="search">Resource or resource group</label><input id="search" type="search" placeholder="Search resource / group"></div>
<div><label for="provider">Hosting provider</label><select id="provider"><option value="">All locations</option>
<option value="onprem">On-premises</option><option value="gcp">GCP</option><option value="azure">Azure</option>
<option value="aws">AWS</option><option value="unknown">Unverified location</option></select></div>
<div><label for="environment">Environment</label><select id="environment"><option value="">All environments</option>
<option>Production</option><option>Preproduction</option><option>Dev</option><option>DMZ</option>
<option>Backup</option><option>Unknown</option></select></div>
<div><label for="connectivity">Arc connectivity</label><select id="connectivity"><option value="">All states</option>
<option>Connected</option><option>Disconnected</option><option>Expired</option><option>Unknown</option></select></div>
<div><label for="mde">Endpoint evidence</label><select id="mde"><option value="">All evidence</option>
<option value="failed-extension">Failed MDE extension</option><option value="missing-extension">Missing MDE extension</option>
<option value="unverified">Sensor health unverified</option><option value="healthy">Sensor verified healthy</option>
<option value="unhealthy">Sensor unhealthy</option></select></div>
<div><label for="resource-type">Exact resource type</label><select id="resource-type">
<option value="">All resource types</option></select></div>
<div><label for="risk">Native risk</label><select id="risk"><option value="">All risks</option>
<option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
<option>Not evaluated</option><option>Unknown</option></select></div>
<div><label for="severity">Finding severity</label><select id="severity"><option value="">All severities</option>
<option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
<option>Informational</option><option>Unknown</option></select></div>
<div><label for="finding-status">Status</label><select id="finding-status"><option value="">All statuses</option>
<option>Unhealthy</option><option>Healthy</option><option>NotApplicable</option><option>Active</option></select></div></div>
<p class="fcount"><output id="inventory-count" aria-live="polite"></output></p></div>
<div class="sh sh3" id="recommendations"><div><h3>Recommendations grouped by native risk and status</h3>
<p>Distinct definitions and affected resources are not the same as finding records. Native risk never falls back to technical severity.</p></div>
<div class="tools"><button type="button" class="btn ghost dl" data-export-section="recommendation_groups">Export grouped recommendations CSV</button></div></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="Grouped recommendations, horizontally scrollable">
<table id="groups-table"><thead><tr><th scope="col">Recommendation / remediation</th><th scope="col">Native risk</th>
<th scope="col">Technical severity</th><th scope="col">Status</th><th scope="col" class="n">Records</th>
<th scope="col" class="n">Resources</th></tr></thead><tbody></tbody></table></div>
<div class="more-row"><p id="groups-count" aria-live="polite"></p>
<button id="groups-more" class="btn ghost" type="button">Show more grouped recommendations</button></div>
<div class="sh sh3" id="ledger"><div><h3>Resource evidence ledger</h3>
<p>MDE installation and verified sensor health are separate columns. Select a resource name for its full evidence.</p></div>
<div class="tools"><button id="inventory-csv" class="btn dl" type="button">Export filtered resource CSV</button></div></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="Server table, horizontally scrollable">
<table id="inventory-table"><caption>@@PROVENANCE@@ resource inventory at @@TIME@@</caption>
<thead><tr><th scope="col"><button type="button" data-sort="0">Resource</button></th>
<th scope="col"><button type="button" data-sort="1">Service group</button></th>
<th scope="col"><button type="button" data-sort="2">Environment</button></th>
<th scope="col"><button type="button" data-sort="3">OS</button></th>
<th scope="col"><button type="button" data-sort="4">Arc state</button></th>
<th scope="col"><button type="button" data-sort="5">MDE extension</button></th>
<th scope="col"><button type="button" data-sort="6">Sensor health</button></th>
<th scope="col"><button type="button" data-sort="7">Servers plan</button></th>
<th scope="col"><button type="button" data-sort="8">Priority / evidence</button></th></tr></thead><tbody>@@INVENTORY@@</tbody></table></div>
<div class="more-row"><p id="ledger-count" class="pgnote" aria-live="polite"></p>
<button id="ledger-more" class="btn ghost" type="button">Show all resources</button></div>
<p class="empty" id="inventory-empty" hidden>No resources match these filters. Reset filters to see the full scope.</p>
<details class="records"><summary>All resource-level finding records and exports (including healthy / not applicable)</summary>
<div class="sh sh3"><div><h3>Source-observed security findings</h3><p>@@QUALIFICATION@@</p></div>
<div class="tools"><button id="findings-csv" class="btn dl" type="button">Export filtered findings CSV</button></div></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="Findings table, horizontally scrollable">
<table id="findings-table"><caption>@@PROVENANCE@@ findings joined to exact resource IDs</caption>
<thead><tr><th scope="col"><button type="button" data-sort="0">Server</button></th>
<th scope="col"><button type="button" data-sort="1">Category</button></th>
<th scope="col"><button type="button" data-sort="2">Native risk / technical severity / status</button></th>
<th scope="col">Finding / evidence</th><th scope="col">Source</th></tr></thead><tbody>@@FINDINGS@@</tbody></table></div>
<div class="more-row"><output id="findings-count" aria-live="polite"></output>
<button id="findings-more" class="btn ghost" type="button">Show more finding records</button></div>
<p class="empty" id="findings-empty" hidden>No Arc-matched findings returned for these filters.
Check source coverage below; empty results do not mean zero risk.</p></details></section>
@@LOWER@@
<section id="source-coverage" aria-labelledby="sources-h"><div class="sh"><div><h2 id="sources-h">Source coverage and limitations</h2>
<p>Every source is listed with its status. Unavailable or partial evidence stays Unknown, never zero.</p></div></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="Source coverage, horizontally scrollable">
<table><caption>@@PROVENANCE@@ evidence availability</caption><thead><tr>
<th scope="col">Source</th><th scope="col">Status</th><th scope="col">Records</th>
<th scope="col">Meaning / unavailable evidence</th></tr></thead><tbody>@@SOURCES@@</tbody></table></div>
@@PLANS@@
<div class="sh sh3"><div><h3>Capability boundaries, not blanket promises</h3>
<p>Validate deployment requirements and separate licences against current official documentation.</p></div></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="Capability boundaries, horizontally scrollable">
<table><thead><tr><th scope="col">Feature</th><th scope="col">Applicability</th><th scope="col">Boundary</th></tr></thead>
<tbody>@@CAPABILITIES@@</tbody></table></div></section>
</div></main>
<footer><p>@@PROVENANCE@@ · @@TIME@@ · No cloud changes, customer security certification, cost ROI or incident-loss claims.
Subscription Secure Score and graphs are not Arc-only metrics; compliance is not certification.</p>
<p><a href="@@REFERENCE@@" target="_blank" rel="noopener noreferrer">Microsoft Defender for Servers: current feature matrix</a>
· Report generated by Azure SRE Agent · Read-only</p></footer>
<noscript><p>JavaScript is disabled. Full snapshot tables remain readable; use the companion CSV/JSON files for export.</p></noscript>
<script type="application/json" id="report-data">@@DATA@@</script>
<script>
"use strict";
const documentData = JSON.parse(document.getElementById("report-data").textContent);
function unpackSnapshot(doc) {
  const fail = message => {throw new Error(message);};
  const maxNodes = @@MAX_DECODED_NODES@@, maxStringUnits = @@MAX_DECODED_STRING_UNITS@@;
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  if (!object(doc)) fail("Snapshot document must be an object");
  if (!Object.hasOwn(doc, "encoding")) return doc;
  if (!["dictionary-columns-v1","dictionary-columns-v2"].includes(doc.encoding)
      || !Array.isArray(doc.strings) || doc.strings.some(value => typeof value !== "string")
      || !Object.hasOwn(doc, "data")) fail("Unsupported snapshot encoding or incomplete dictionary/data");
  const string = index => {
    if (!Number.isSafeInteger(index) || index < 0 || index >= doc.strings.length)
      fail("Invalid evidence string reference");
    return doc.strings[index];
  };
  const missing = Symbol("missing");
  function legacy(value, depth=0) {
    if (depth > 100) fail("Snapshot nesting exceeds the safety bound");
    if (typeof value === "string" && value.startsWith("~")) {
      if (value.startsWith("~~")) return value.slice(1);
      if (!/^~[0-9]+$/u.test(value)) fail("Invalid compact string reference");
      return string(Number(value.slice(1)));
    }
    if (Array.isArray(value)) return value.map(child => legacy(child,depth+1));
    if (object(value)) {
      const keys = Object.keys(value);
      if (keys.length === 1 && Object.hasOwn(value,"$s")) return string(value.$s);
      if (keys.length === 2 && Object.hasOwn(value,"$table") && Object.hasOwn(value,"rows")) {
        if (!Array.isArray(value.$table) || value.$table.some(key => typeof key !== "string")
            || new Set(value.$table).size !== value.$table.length || !Array.isArray(value.rows))
          fail("Invalid evidence table");
        return value.rows.map(row => {
          if (!Array.isArray(row) || row.length !== value.$table.length) fail("Invalid evidence table row");
          return Object.fromEntries(value.$table.flatMap((key,index) => {
            const cell = row[index];
            return object(cell) && cell.$missing === true && Object.keys(cell).length === 1
              ? [] : [[key,legacy(cell,depth+1)]];
          }));
        });
      }
      if (["$s","$table","$missing"].some(key => Object.hasOwn(value,key))) fail("Invalid reserved v1 codec marker");
      return Object.fromEntries(Object.entries(value).map(([key,child]) => [key,legacy(child,depth+1)]));
    }
    return value;
  }
  function node(value, depth=0) {
    if (depth > 100) fail("Snapshot nesting exceeds the safety bound");
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) fail("Non-finite snapshot number");
      return value;
    }
    if (!Array.isArray(value) || !Number.isInteger(value[0])) fail("Invalid encoded snapshot node");
    const tag = value[0];
    if (tag === 0 && value.length === 2) return string(value[1]);
    if (tag === 4 && value.length === 1) return missing;
    if (tag === 5 && value.length === 2 && typeof value[1] === "string") {
      if (!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/u.test(value[1]))
        fail("Invalid encoded snapshot float");
      const number = Number(value[1]);
      if (!Number.isFinite(number)) fail("Non-finite snapshot number");
      return number;
    }
    if (tag === 1 && value.length === 2 && Array.isArray(value[1]) && value[1].length % 2 === 0) {
      const result = Object.create(null);
      for (let i=0; i<value[1].length; i+=2) {
        const key = string(value[1][i]), child = node(value[1][i+1],depth+1);
        if (Object.hasOwn(result,key) || child === missing) fail("Duplicate or missing object key");
        result[key] = child;
      }
      return result;
    }
    if (tag === 2 && value.length === 2 && Array.isArray(value[1])) {
      const result = value[1].map(child => node(child,depth+1));
      if (result.includes(missing)) fail("Missing marker in an array");
      return result;
    }
    if (tag === 3 && value.length === 4) {
      const [count,fields,columns] = value.slice(1);
      if (!Number.isSafeInteger(count) || count < 0 || !Array.isArray(fields)
          || !Array.isArray(columns) || fields.length !== columns.length) fail("Invalid evidence table");
      const keys = fields.map(string);
      if (new Set(keys).size !== keys.length) fail("Duplicate evidence table key");
      const rows = Array.from({length:count}, () => Object.create(null));
      columns.forEach((encoded,i) => column(encoded,count,depth+1).forEach((child,j) => {
        if (child !== missing) rows[j][keys[i]] = child;
      }));
      return rows;
    }
    fail("Unknown encoded snapshot node tag or shape");
  }
  function column(value, count, depth) {
    if (!Array.isArray(value) || !Number.isInteger(value[0])) fail("Invalid encoded snapshot column");
    const tag = value[0];
    if (tag === 0 && value.length === 2) return Array.from({length:count}, () => node(value[1],depth));
    if (tag === 1 && value.length === 2 && Array.isArray(value[1]) && value[1].length === count)
      return value[1].map(child => node(child,depth));
    if (tag === 2 && value.length === 2 && Array.isArray(value[1])) {
      const result = [];
      for (const run of value[1]) {
        if (!Array.isArray(run) || run.length !== 2 || !Number.isSafeInteger(run[0])
            || run[0] < 1 || run[0] > count-result.length) fail("Invalid evidence run length");
        for (let i=0; i<run[0]; i++) result.push(node(run[1],depth));
      }
      if (result.length !== count) fail("Incomplete evidence runs");
      return result;
    }
    if (tag === 3 && value.length === 3 && Array.isArray(value[2])) {
      const overrides = new Map();
      for (const pair of value[2]) {
        if (!Array.isArray(pair) || pair.length !== 2 || !Number.isSafeInteger(pair[0])
            || pair[0] < 0 || pair[0] >= count || overrides.has(pair[0])) fail("Invalid sparse evidence position");
        overrides.set(pair[0],pair[1]);
      }
      return Array.from({length:count}, (_,i) => node(overrides.has(i) ? overrides.get(i) : value[1],depth));
    }
    fail("Unknown encoded snapshot column tag or shape");
  }
  function addCost(total, child, copies=1) {
    const nodes = total[0]+child[0]*copies, units = total[1]+child[1]*copies;
    if (nodes > maxNodes || units > maxStringUnits) fail("Snapshot exceeds the bounded decoded expansion budget");
    return [nodes,units];
  }
  function measure(value, depth=0) {
    if (depth > 100) fail("Snapshot nesting exceeds the safety bound");
    if (value === null || typeof value === "boolean") return [1,0];
    if (typeof value === "number") {
      if (!Number.isFinite(value)) fail("Non-finite snapshot number");
      return [1,0];
    }
    if (!Array.isArray(value) || !Number.isInteger(value[0])) fail("Invalid encoded snapshot node");
    const tag = value[0];
    if (tag === 0 && value.length === 2) return addCost([0,0],[1,string(value[1]).length]);
    if (tag === 4 && value.length === 1) return null;
    if (tag === 5 && value.length === 2 && typeof value[1] === "string") {node(value,depth); return [1,0];}
    if (tag === 1 && value.length === 2 && Array.isArray(value[1]) && value[1].length % 2 === 0) {
      let total = [1,0]; const seen = new Set();
      for (let i=0; i<value[1].length; i+=2) {
        const key = string(value[1][i]), child = measure(value[1][i+1],depth+1);
        if (seen.has(key) || child === null) fail("Duplicate or missing object key");
        seen.add(key); total = addCost(addCost(total,[1,key.length]),child);
      }
      return total;
    }
    if (tag === 2 && value.length === 2 && Array.isArray(value[1])) {
      let total = [1,0];
      for (const encoded of value[1]) {
        const child = measure(encoded,depth+1);
        if (child === null) fail("Missing marker in an array");
        total = addCost(total,child);
      }
      return total;
    }
    if (tag === 3 && value.length === 4) {
      const [count,fields,columns] = value.slice(1);
      if (!Number.isSafeInteger(count) || count < 0 || !Array.isArray(fields)
          || !Array.isArray(columns) || fields.length !== columns.length) fail("Invalid evidence table");
      let total = addCost([1,0],[1+fields.length,0],count);
      const keys = fields.map(string);
      if (new Set(keys).size !== keys.length) fail("Duplicate evidence table key");
      columns.forEach((encoded,i) => {
        const [child,present] = measureColumn(encoded,count,depth+1);
        total = addCost(addCost(total,child),[0,keys[i].length],present);
      });
      return total;
    }
    fail("Unknown encoded snapshot node tag or shape");
  }
  function measureColumn(value, count, depth) {
    if (!Array.isArray(value) || !Number.isInteger(value[0])) fail("Invalid encoded snapshot column");
    const tag = value[0];
    if (tag === 0 && value.length === 2) {
      const child = measure(value[1],depth);
      return child === null ? [[0,0],0] : [addCost([0,0],child,count),count];
    }
    if (tag === 1 && value.length === 2 && Array.isArray(value[1]) && value[1].length === count) {
      let total = [0,0], present = 0;
      for (const encoded of value[1]) {
        const child = measure(encoded,depth);
        if (child !== null) {total = addCost(total,child); present++;}
      }
      return [total,present];
    }
    if (tag === 2 && value.length === 2 && Array.isArray(value[1])) {
      let total = [0,0], present = 0, covered = 0;
      for (const run of value[1]) {
        if (!Array.isArray(run) || run.length !== 2 || !Number.isSafeInteger(run[0])
            || run[0] < 1 || run[0] > count-covered) fail("Invalid evidence run length");
        const child = measure(run[1],depth);
        if (child !== null) {total = addCost(total,child,run[0]); present += run[0];}
        covered += run[0];
      }
      if (covered !== count) fail("Incomplete evidence runs");
      return [total,present];
    }
    if (tag === 3 && value.length === 3 && Array.isArray(value[2])) {
      const fallback = measure(value[1],depth), seen = new Set();
      let total = [0,0], present = 0;
      for (const pair of value[2]) {
        if (!Array.isArray(pair) || pair.length !== 2 || !Number.isSafeInteger(pair[0])
            || pair[0] < 0 || pair[0] >= count || seen.has(pair[0])) fail("Invalid sparse evidence position");
        seen.add(pair[0]);
        const child = measure(pair[1],depth);
        if (child !== null) {total = addCost(total,child); present++;}
      }
      if (fallback !== null) {total = addCost(total,fallback,count-seen.size); present += count-seen.size;}
      return [total,present];
    }
    fail("Unknown encoded snapshot column tag or shape");
  }
  if (doc.encoding === "dictionary-columns-v2") {
    const cost = measure(doc.data);
    if (cost === null) fail("Restored snapshot must be an object");
    addCost([0,0],cost);
  }
  const restored = doc.encoding === "dictionary-columns-v1" ? legacy(doc.data) : node(doc.data);
  if (!object(restored)) fail("Restored snapshot must be an object");
  return restored;
}
const snapshot = unpackSnapshot(documentData);
const servers = new Map(snapshot.inventory.map(row => [row.resource_id, row]));
let findingLimit = 50, groupLimit = 50, ledgerLimit = 50, filteredFindings = [], filteredGroups = [];
const filterIds = ["search", "provider", "environment", "connectivity", "mde", "severity",
 "risk", "finding-status", "resource-type"];
const TONE = {"Critical":"crit","High":"high","Medium":"med","Low":"low","Informational":"info",
 "Immediate review":"crit","High priority":"high","Verify coverage":"med","No observed gap":"info",
 "Active":"crit","Failed":"crit","Unhealthy":"crit","Missing":"high","Expired":"high","Disconnected":"high",
 "Free":"high","Healthy":"ok"};
const QUIET = new Set(["Not applicable","Not observed","Unknown","Not evaluated","NotApplicable","Not verified"]);
function matches(row) {
  const search = document.getElementById("search").value.trim().toLowerCase();
  if (search && !(row.server_name + " " + row.resource_group).toLowerCase().includes(search)) return false;
  for (const field of ["provider", "environment", "connectivity"]) {
    const value = document.getElementById(field).value;
    if (value && row[field] !== value) return false;
  }
  const mde = document.getElementById("mde").value;
  const type = document.getElementById("resource-type").value;
  if (type && row.resource_type !== type) return false;
  if (mde === "failed-extension" && row.mde_extension !== "Failed") return false;
  if (mde === "missing-extension" && row.mde_extension !== "Missing") return false;
  if (mde === "unverified" && row.sensor_health !== "Unknown") return false;
  if (mde === "healthy" && row.sensor_health !== "Healthy") return false;
  if (mde === "unhealthy" && row.sensor_health !== "Unhealthy") return false;
  return true;
}
function chip(value, prefix, extra) {
  const node = textElement("span", (prefix || "") + (value == null ? "Unknown" : value));
  node.className = "pill " + (extra || "") + (TONE[value] || "muted"); return node;
}
function valueNode(value) {
  if (TONE[value]) return chip(value);
  const node = textElement("span", value); if (QUIET.has(String(value))) node.className = "nil"; return node;
}
function statusNode(value, prefix) {
  const node = textElement("span", (prefix || "") + (value == null ? "Unknown" : value));
  node.className = value === "Healthy" ? "pill ok" : value === "Active" ? "pill crit"
    : prefix ? "pill muted" : QUIET.has(String(value)) ? "nil" : "";
  return node;
}
function cell(...children) {
  const td = document.createElement("td"); children.forEach(child => td.appendChild(child)); return td;
}
function nameCell(name, group, id) {
  const main = id ? textElement("button", name) : textElement("strong", name);
  if (id) {main.type = "button"; main.className = "rlink"; main.dataset.rid = id;}
  return cell(main, textElement("small", group));
}
function applyFilters() {
  const selected = new Set(snapshot.inventory.filter(matches).map(row => row.resource_id));
  const severity = document.getElementById("severity").value;
  const risk = document.getElementById("risk").value;
  const status = document.getElementById("finding-status").value;
  let visibleServers = 0;
  const inventoryBody = document.querySelector("#inventory-table tbody");
  inventoryBody.replaceChildren();
  snapshot.inventory.filter(item => selected.has(item.resource_id)).forEach(item => {
    const row = document.createElement("tr"); row.dataset.id = item.resource_id;
    row.appendChild(nameCell(item.server_name, item.resource_group, item.resource_id));
    [item.resource_kind || "Arc servers",item.environment,item.os,item.connectivity,item.mde_extension,
      item.sensor_health,item.servers_plan].forEach(value => row.appendChild(cell(valueNode(value))));
    row.appendChild(cell(chip(item.priority, "", "dot ")));
    inventoryBody.appendChild(row); visibleServers++;
  });
  filteredFindings = snapshot.findings.filter(item => selected.has(item.resource_id)
    && (!severity || item.technical_severity === severity) && (!risk || item.risk_level === risk)
    && (!status || item.status === status));
  filteredGroups = snapshot.recommendation_groups.filter(group =>
    group.resource_ids.some(id => selected.has(id)) && (!risk || group.risk_level === risk)
    && (!status || group.status === status) && (!severity || group.technical_severity === severity));
  renderPagedTables(); pageLedger();
  document.getElementById("inventory-count").textContent =
    visibleServers + " of " + snapshot.inventory.length + " resources · " + snapshot.provenance;
  document.getElementById("inventory-empty").hidden = visibleServers !== 0;
  document.getElementById("findings-empty").hidden = filteredFindings.length !== 0;
}
function pageLedger() {
  const rows = Array.from(document.querySelectorAll("#inventory-table tbody tr")), more = document.getElementById("ledger-more");
  rows.forEach((row, index) => row.classList.toggle("pg", index >= ledgerLimit));
  more.hidden = rows.length <= ledgerLimit; more.textContent = "Show all " + rows.length + " resources";
  document.getElementById("ledger-count").textContent = "Showing " + Math.min(ledgerLimit, rows.length) + " of "
    + rows.length + " matched resources. CSV exports ALL matches.";
}
document.getElementById("ledger-more").addEventListener("click", () => {ledgerLimit = Infinity; pageLedger();});
function csvCell(value) {
  let text = value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (/^[\s]*[=+\-@]/u.test(text) || /^[\t\r\n]/u.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function download(content, mime, filename) {
  const url = URL.createObjectURL(new Blob([content], {type:mime}));
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportCsv(rows, fields, filename) {
  const lines = [fields.map(csvCell).join(",")];
  rows.forEach(row => lines.push(fields.map(field => csvCell(row[field])).join(",")));
  download("\ufeff" + lines.join("\r\n"), "text/csv;charset=utf-8", filename);
}
document.getElementById("inventory-csv").addEventListener("click", () => {
  const rows = Array.from(document.querySelectorAll("#inventory-table tbody tr"))
    .filter(row => !row.hidden).map(row => servers.get(row.dataset.id));
  exportCsv(rows, snapshot.inventory_csv_fields, snapshot.provenance + "-arc-servers-filtered.csv");
});
document.getElementById("findings-csv").addEventListener("click", () => {
  exportCsv(filteredFindings, snapshot.finding_csv_fields, snapshot.provenance + "-findings-filtered.csv");
});
document.getElementById("snapshot-json").addEventListener("click", () =>
  download(JSON.stringify(documentData), "application/json", snapshot.provenance + "-snapshot.json"));
const typeSelector = document.getElementById("resource-type");
Array.from(new Set(snapshot.inventory.map(r => r.resource_type || "microsoft.hybridcompute/machines")))
 .sort().forEach(value => {const option = document.createElement("option");
  option.value = value; option.textContent = value; typeSelector.appendChild(option);});
function textElement(tag, text) {
  const node = document.createElement(tag); node.textContent = String(text == null ? "Unknown" : text); return node;
}
function renderPagedTables() {
  const findingsBody = document.querySelector("#findings-table tbody");
  findingsBody.replaceChildren();
  filteredFindings.slice(0,findingLimit).forEach(finding => {
    const row = document.createElement("tr"), state = document.createElement("div");
    state.className = "chips";
    [chip(finding.risk_level, "Native: ", "dot "), chip(finding.technical_severity, "Technical: ", "line "),
      statusNode(finding.status)].forEach(node => state.appendChild(node));
    row.appendChild(nameCell(finding.server_name, finding.resource_group));
    row.appendChild(cell(textElement("span", finding.category)));
    row.appendChild(cell(state));
    row.appendChild(cell(textElement("span", finding.title)));
    row.appendChild(cell(textElement("small", finding.source)));
    findingsBody.appendChild(row);
  });
  document.getElementById("findings-count").textContent =
    "Showing " + Math.min(findingLimit,filteredFindings.length) + " of " + filteredFindings.length
    + " matched findings (" + snapshot.findings.length + " total). CSV exports ALL matches.";
  document.getElementById("findings-more").hidden = findingLimit >= filteredFindings.length;
  const groupsBody = document.querySelector("#groups-table tbody");
  groupsBody.replaceChildren();
  filteredGroups.slice(0,groupLimit).forEach(group => {
    const row = document.createElement("tr"), first = document.createElement("td");
    first.appendChild(textElement("strong", group.title));
    const details = document.createElement("details"); details.appendChild(textElement("summary", "Remediation and resources"));
    details.appendChild(textElement("p", group.remediation));
    details.appendChild(textElement("p", group.server_names.join(", "))); first.appendChild(details); row.appendChild(first);
    row.appendChild(cell(chip(group.risk_level, "", "dot ")));
    row.appendChild(cell(chip(group.technical_severity, "", "line ")));
    row.appendChild(cell(statusNode(group.status)));
    [group.records,group.affected_resources].forEach(value => {
      const td = cell(textElement("span", value)); td.className = "n"; row.appendChild(td);
    });
    groupsBody.appendChild(row);
  });
  document.getElementById("groups-count").textContent =
    "Showing " + Math.min(groupLimit,filteredGroups.length) + " of " + filteredGroups.length
    + " matched groups. CSV exports ALL matches.";
  document.getElementById("groups-more").hidden = groupLimit >= filteredGroups.length;
}
document.getElementById("findings-more").addEventListener("click", () => {findingLimit += 50; renderPagedTables();});
document.getElementById("groups-more").addEventListener("click", () => {groupLimit += 50; renderPagedTables();});
function idNode(text) {
  const node = document.createElement("p"), parts = String(text).split("/");
  node.className = "rid";
  parts.forEach((part, index) => {
    node.appendChild(document.createTextNode(part + (index < parts.length - 1 ? "/" : "")));
    if (index < parts.length - 1) node.appendChild(document.createElement("wbr"));
  });
  return node;
}
function chipList(entries) {
  const node = document.createElement("div"); node.className = "chips";
  if (!entries.length) node.appendChild(textElement("span", "None observed"));
  entries.forEach(entry => node.appendChild(textElement("span", entry)));
  return node;
}
function renderResource() {
  const root = document.getElementById("detail-content");
  root.replaceChildren();
  const resource = servers.get(document.getElementById("detail-resource").value);
  if (!resource) {root.appendChild(textElement("p", "No resource evidence available.")); return;}
  const head = document.createElement("div"), titles = document.createElement("div"), badges = document.createElement("div");
  head.className = "rhead"; badges.className = "chips";
  titles.appendChild(textElement("h3", resource.server_name));
  titles.appendChild(idNode(resource.resource_id));
  if (String(resource.resource_id).startsWith("/subscriptions/")) {
    const portal = textElement("a", "Open in Azure portal");
    portal.href = "https://portal.azure.com/#@/resource" + resource.resource_id;
    portal.target = "_blank"; portal.rel = "noopener noreferrer"; titles.appendChild(portal);
  }
  badges.appendChild(chip(resource.priority, "", "dot "));
  badges.appendChild(textElement("span", resource.resource_kind || "Arc servers"));
  badges.appendChild(textElement("span", resource.resource_group));
  head.appendChild(titles); head.appendChild(badges); root.appendChild(head);
  const facts = document.createElement("dl"); facts.className = "facts";
  const pairs = object => Object.entries(object || {}).map(([key,value]) => key + ": " + value);
  const observations = {
    "Inventory source": resource.inventory_source || "SIMULATED fixture",
    "Resource type": resource.resource_type || "microsoft.hybridcompute/machines",
    "Azure location (not physical Arc hosting)": resource.location,
    "OS / version": resource.os + " / " + (resource.os_version || "Unknown"),
    "Ownership tags": chipList(pairs(resource.tags)),
    "Recommendation statuses": chipList(pairs(resource.recommendation_status_counts)),
    "Unhealthy native risks": chipList(pairs(resource.recommendation_risk_counts)),
    "MDE installation / sensor": resource.mde_extension + " / " + resource.sensor_health,
    "Extensions": chipList((resource.extensions || []).map(e => e.name + " · " + e.state)),
    "FIM configuration": resource.fim_configuration || "Not verified",
    "AKS monitoring configured (not health)": resource.aks_defender_monitoring_enabled,
    "Software rows observed": resource.software_records,
    "Embedded CVE occurrences": resource.embedded_cve_records
  };
  Object.entries(observations).forEach(([key,value]) => {
    const box = document.createElement("div"), dd = document.createElement("dd");
    if (value instanceof Node) dd.appendChild(value); else dd.textContent = String(value == null ? "Unknown" : value);
    box.appendChild(textElement("dt", key)); box.appendChild(dd); facts.appendChild(box);
  });
  root.appendChild(facts);
  const findings = snapshot.findings.filter(f => f.resource_id === resource.resource_id);
  root.appendChild(textElement("h4", "Finding records"));
  root.appendChild(textElement("p", findings.length + " finding records, all statuses. Showing first 30; complete evidence is exported."));
  const list = document.createElement("ul"); list.className = "flist";
  findings.slice(0,30).forEach(finding => {
    const item = document.createElement("li"), tags = document.createElement("div");
    tags.className = "chips";
    [statusNode(finding.status, "Status: "), chip(finding.risk_level, "Native risk: ", "dot "),
      chip(finding.technical_severity, "Technical severity: ", "line ")].forEach(node => tags.appendChild(node));
    item.appendChild(textElement("strong", finding.title)); item.appendChild(tags);
    item.appendChild(textElement("p", finding.remediation || "Remediation not supplied by this source."));
    const patch = finding.patch || {}, versions = (patch.detected_versions || []).join(", ");
    const evidence = [["Software", patch.software_name], ["Detected", versions], ["Fixed", patch.fixed_version],
      ["KB", patch.kb], ["Patch", patch.patch_name], ["Max CVSS", patch.maximum_cvss], ["Reboot", patch.reboot_behavior],
      ["Published", patch.published_utc], ["Scanner", patch.scanner], ["Rule", patch.rule_category]]
      .filter(([,value]) => value && value !== "Not supplied").map(([key,value]) => key + ": " + value);
    if (evidence.length) item.appendChild(chipList(evidence));
    [patch.reason, patch.threat_exposure].filter(Boolean).forEach(text => item.appendChild(textElement("p", text)));
    if (finding.portal_url) {
      const link = textElement("a", "Review native recommendation");
      link.href = finding.portal_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      item.appendChild(link);
    }
    list.appendChild(item);
  });
  root.appendChild(list);
  const tools = document.createElement("div"); tools.className = "tools";
  const exportButton = textElement("button", "Export all findings for this resource");
  exportButton.type = "button"; exportButton.className = "btn ghost dl"; exportButton.addEventListener("click",
    () => exportCsv(findings, snapshot.finding_csv_fields, snapshot.provenance + "-resource-findings.csv"));
  tools.appendChild(exportButton);
  const cves = snapshot.vulnerabilities.filter(v => v.resource_id === resource.resource_id);
  const cveButton = textElement("button", "Export all embedded CVEs for this resource");
  cveButton.type = "button"; cveButton.className = "btn ghost dl"; cveButton.addEventListener("click", () => exportCsv(cves,
    ["provenance","reference_utc","server_name","cve_id","technical_severity","fix_status","fixed_version","source"],
    snapshot.provenance + "-resource-cves.csv"));
  tools.appendChild(cveButton);
  root.appendChild(tools);
}
document.getElementById("detail-resource").addEventListener("change", renderResource);
document.querySelector("#inventory-table tbody").addEventListener("click", event => {
  const button = event.target.closest("button[data-rid]");
  if (!button) return;
  const selector = document.getElementById("detail-resource");
  selector.value = button.dataset.rid; renderResource();
  document.getElementById("resource-detail").scrollIntoView({block:"start"});
  selector.focus({preventScroll:true});
});
document.querySelectorAll("[data-export-section]").forEach(button => button.addEventListener("click", () => {
  const key = button.dataset.exportSection;
  let rows = key === "controls" ? snapshot.posture.controls
    : key === "compliance" ? snapshot.compliance.controls : snapshot[key];
  if (key === "recommendation_groups") {
    rows = filteredGroups;
  }
  const fields = rows.length ? Object.keys(rows[0]) : ["provenance","reference_utc"];
  exportCsv(rows, fields, snapshot.provenance + "-" + key + ".csv");
}));
document.getElementById("reset").addEventListener("click", () => {
  filterIds.forEach(id => {document.getElementById(id).value = "";});
  findingLimit = 50; groupLimit = 50; ledgerLimit = 50; applyFilters();
});
filterIds.forEach(id => document.getElementById(id).addEventListener("input", applyFilters));
document.querySelectorAll("button[data-sort]").forEach(button => button.addEventListener("click", () => {
  const table = button.closest("table"), th = button.closest("th"), column = Number(button.dataset.sort);
  const ascending = th.getAttribute("aria-sort") !== "ascending";
  table.querySelectorAll("th").forEach(header => header.removeAttribute("aria-sort"));
  th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
  if (table.id === "findings-table") {
    const field = ["server_name","category","risk_level","title","source"][column];
    filteredFindings.sort((a,b) => String(a[field]).localeCompare(String(b[field]),
      undefined, {numeric:true,sensitivity:"base"}) * (ascending ? 1 : -1));
    renderPagedTables(); return;
  }
  const rows = Array.from(table.tBodies[0].rows);
  rows.sort((a,b) => a.cells[column].textContent.localeCompare(b.cells[column].textContent,
    undefined, {numeric:true,sensitivity:"base"}) * (ascending ? 1 : -1));
  rows.forEach(row => table.tBodies[0].appendChild(row));
  if (table.id === "inventory-table") pageLedger();
}));
document.querySelectorAll("[data-print]").forEach(button => button.addEventListener("click", () => window.print()));
document.querySelectorAll(".table-wrap[data-page]").forEach(wrap => {
  const limit = Number(wrap.dataset.page), rows = Array.from(wrap.querySelectorAll("tbody tr"));
  if (rows.length <= limit) return;
  rows.slice(limit).forEach(row => row.classList.add("pg"));
  const bar = document.createElement("div"), note = textElement("p", "Showing " + limit + " of " + rows.length + " rows.");
  const button = textElement("button", "Show all " + rows.length + " rows");
  bar.className = "more-row"; note.className = "pgnote"; button.type = "button"; button.className = "btn ghost";
  button.addEventListener("click", () => {rows.forEach(row => row.classList.remove("pg")); bar.remove();});
  bar.appendChild(note); bar.appendChild(button); wrap.after(bar);
});
const openedForPrint = [];
addEventListener("beforeprint", () => document.querySelectorAll(".path-panel details:not([open]),details.more:not([open])")
  .forEach(details => {details.open = true; openedForPrint.push(details);}));
addEventListener("afterprint", () => openedForPrint.splice(0).forEach(details => {details.open = false;}));
applyFilters();
renderResource();
</script></body></html>"""
    return re.sub(r"@@([A-Z_]+)@@", lambda match: replacements[match.group(1)], document)


def _finish_snapshot(inventory, findings, sources, provenance, reference, scope, assumptions=None, context=None):
    context = context or {}
    for finding in findings:
        finding.setdefault("technical_severity", finding["severity"])
        finding.setdefault("risk_level", "Not evaluated")
        finding.setdefault("recommendation_id", finding["finding_id"].rsplit("/", 1)[-1])
        finding.setdefault("remediation", "")
        finding.setdefault("recommendation_category", finding["category"])
        finding.setdefault("assessment_type", "SIMULATED" if provenance == "SIMULATED" else "Unknown")
        finding.setdefault("cve_details", [])
        finding.setdefault("patch", {})
    _enrich_inventory(inventory, findings, provenance)
    partial = any(source["status"] != "complete" for source in sources)
    for row in inventory + findings:
        row["reference_utc"] = reference
        row["provenance"] = provenance
    snapshot = {
        "schema_version": "2.0", "status": "partial" if partial else "success",
        "provenance": provenance, "reference_utc": reference, "scope": scope,
        "coverage": {
            "status": "partial" if partial else "complete",
            "inventory_pagination_completed": True, "inventory_servers": len(inventory),
            "sensor_health_is_separate_from_extension": True,
            "scope_is_arc_only": provenance == "SIMULATED", "inventory_scope_is_arc_only": provenance == "SIMULATED",
            "subscription_secure_score_collected": bool(context.get("posture", {}).get("scores")),
            "context_metrics_are_not_arc_scores": True,
        },
        "summary": _summary(inventory, findings, sources),
        "sources": sources, "inventory": inventory, "findings": findings,
        "actions": _actions(inventory, findings, sources, provenance),
        "capability_matrix": CAPABILITY_MATRIX, "feature_reference": DEFENDER_REFERENCE,
        "inventory_csv_fields": list(INVENTORY_CSV_FIELDS),
        "finding_csv_fields": list(FINDING_CSV_FIELDS),
        "recommendation_groups": _group_recommendations(findings),
        "posture": context.get("posture", {"scores": [], "controls": [], "risk_score_observations": []}),
        "attack_paths": context.get("attack_paths", []),
        "software": context.get("software", []),
        "plans": context.get("plans", []),
        "compliance": context.get("compliance", {"standards": [], "controls": [], "assessments": []}),
        "subscription_recommendations": context.get("subscription_recommendations", []),
        "vulnerabilities": [],
    }
    for finding in findings:
        for cve in finding["cve_details"]:
            snapshot["vulnerabilities"].append({
                **cve, "finding_id": finding["finding_id"], "resource_id": finding["resource_id"],
                "server_name": finding["server_name"], "software_name": finding["patch"].get("software_name", ""),
                "risk_level": finding["risk_level"], "source": finding["source"] + ".additionalData.CvesDetails",
                "provenance": provenance, "reference_utc": reference,
            })
    for row in inventory:
        row["software_records"] = sum(row["resource_id"] == s["resource_id"] for s in snapshot["software"])
        row["attack_path_records"] = sum(
            row["resource_id"] in p.get("resource_ids", p["arc_resource_ids"]) for p in snapshot["attack_paths"]
        )
        row["embedded_cve_records"] = sum(v["resource_id"] == row["resource_id"] for v in snapshot["vulnerabilities"])
    snapshot["summary"].update({
        "embedded_cve_records": len(snapshot["vulnerabilities"]),
        "distinct_embedded_cves": len({v["cve_id"] for v in snapshot["vulnerabilities"]}),
        "distinct_resource_cve_pairs": len({(v["resource_id"], v["cve_id"]) for v in snapshot["vulnerabilities"]}),
        "embedded_cve_technical_severity_counts": _counts(snapshot["vulnerabilities"], "technical_severity"),
        "attack_paths_subscription_context": len(snapshot["attack_paths"]),
        "attack_paths_arc_related": sum(bool(p["arc_resource_ids"]) for p in snapshot["attack_paths"]),
        "software_records_subscription_context": len(snapshot["software"]),
        "software_records_arc_related": sum(bool(s["arc_resource_ids"]) for s in snapshot["software"]),
    })
    snapshot["actions"] = _review_actions(snapshot, inventory, findings)
    if assumptions is not None:
        snapshot["synthetic_assumptions"] = assumptions
    return snapshot


def _artifact_directory():
    try:
        root = Path.cwd().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise EvidenceError(
            "unsafe_artifact_root", "Could not resolve the runtime working root.", "artifact_storage"
        ) from exc
    if root == Path(root.anchor) or not root.is_dir():
        raise EvidenceError(
            "unsafe_artifact_root", "Runtime cwd must be an existing non-filesystem-root directory.", "artifact_storage"
        )
    if OUTPUT_DIRECTORY != Path("arc-defender-reports"):
        raise EvidenceError(
            "unsafe_artifact_directory", "Only the fixed arc-defender-reports subdirectory is allowed.", "artifact_storage"
        )
    try:
        directory = (root / OUTPUT_DIRECTORY).resolve()
    except (OSError, RuntimeError) as exc:
        raise EvidenceError(
            "unsafe_artifact_directory", "Could not resolve the runtime-owned export directory.", "artifact_storage"
        ) from exc
    if directory == root or not directory.is_relative_to(root):
        raise EvidenceError(
            "unsafe_artifact_directory", "Resolved report directory escapes the runtime working root.", "artifact_storage"
        )
    return root, directory


def _write_report(snapshot):
    if not isinstance(LOGO_BASE64, str) or len(LOGO_BASE64) < 100:
        raise EvidenceError("asset_missing", "The approved embedded logo is missing.", "report_renderer")
    root, directory = _artifact_directory()
    prefix = (
        ("arc-demo-" if snapshot["provenance"] == "SIMULATED" else "defender-")
        + snapshot["reference_utc"].replace(":", "").replace("-", "") + "-" + uuid4().hex[:8]
    )
    paths = {
        "report_path": directory / (prefix + ".html"),
        "csv_path": directory / (prefix + "-servers.csv"),
        "findings_csv_path": directory / (prefix + "-findings.csv"),
        "snapshot_path": directory / (prefix + "-snapshot.json"),
    }
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(snapshot_document.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        snapshot_document = json.dumps(
            _pack_snapshot(snapshot), ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
    documents = {
        "report_path": _render_html(snapshot),
        "csv_path": _csv_document(snapshot["inventory"], INVENTORY_CSV_FIELDS),
        "findings_csv_path": _csv_document(snapshot["findings"], FINDING_CSV_FIELDS),
        "snapshot_path": snapshot_document,
    }
    for name in ("report_path", "snapshot_path"):
        if len(documents[name].encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise EvidenceError(
                "artifact_size_exceeded",
                "Complete evidence cannot fit the safe 4800000-byte plain HTML/JSON sharing limit; no data was truncated.",
                "artifact_storage",
            )
    written = []
    temporary_paths = []
    try:
        directory.mkdir(exist_ok=True)
        resolved = directory.resolve(strict=True)
        if resolved != directory or not resolved.is_relative_to(root):
            raise EvidenceError(
                "unsafe_artifact_directory", "Export directory changed scope after creation.", "artifact_storage"
            )
        for key, path in paths.items():
            descriptor, temporary = tempfile.mkstemp(prefix=prefix + "-", suffix=".tmp", dir=directory)
            temporary_paths.append(Path(temporary))
            encoding = "utf-8-sig" if key.endswith("csv_path") else "utf-8"
            with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
                stream.write(documents[key])
            os.replace(temporary, path)
            temporary_paths.remove(Path(temporary))
            written.append(path)
    except OSError as exc:
        cleanup_failed = False
        for path in written + temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                cleanup_failed = True
        message = "Could not atomically write the report artifacts. Check sandbox storage access."
        if cleanup_failed:
            message += " Cleanup also failed; inspect the named run artifacts before retrying."
        raise EvidenceError("artifact_write_failed", message, "artifact_storage") from exc
    response = _transport_envelope(snapshot)
    response.update({
        "top_actions": [{
            "action_id": action["action_id"], "priority": action["priority"],
            "affected_resources": action["affected_resources"],
            **({"affected_paths": action["affected_paths"]} if "affected_paths" in action else {}),
        } for action in snapshot["actions"][:3]],
        "actions_total": len(snapshot["actions"]), "actions_returned": min(len(snapshot["actions"]), 3),
        "actions_has_more": len(snapshot["actions"]) > 3,
        **{key: str(path) for key, path in paths.items()},
    })
    return _check_transport_budget(response)
# END STANDALONE REPORT HELPERS


ARG_QUERIES = {
    "defender_recommendations": (
        "securityresources | where type =~ 'microsoft.security/assessments' "
        "| project id, name, type, properties"
    ),
    "defender_vulnerabilities": (
        "securityresources | where type =~ 'microsoft.security/assessments/subassessments' "
        "| project id, name, type, properties"
    ),
}
CONTEXT_ARG_TYPES = {
    "attack_paths": "microsoft.security/attackpaths",
    "software_inventory": "microsoft.security/softwareinventories",
    "secure_score_controls": "microsoft.security/securescores/securescorecontrols",
    "risk_secure_score": "microsoft.security/risksecurescore",
    "compliance_controls": "microsoft.security/regulatorycompliancestandards/regulatorycompliancecontrols",
    "compliance_assessments": (
        "microsoft.security/regulatorycompliancestandards/regulatorycompliancecontrols/"
        "regulatorycomplianceassessments"
    ),
}
ARG_QUERIES.update({
    name: "securityresources | where type =~ '" + resource_type + "' | project id, name, type, properties"
    for name, resource_type in CONTEXT_ARG_TYPES.items()
})
ARG_QUERIES["resource_inventory"] = (
    "resources | project id, name, type, resourceGroup, location, tags"
)
ARG_QUERIES["compute_extensions"] = (
    "resources | where type in~ ('microsoft.compute/virtualmachines/extensions', "
    "'microsoft.compute/virtualmachinescalesets/extensions') "
    "| project id, name, type, properties=bag_pack('type', properties.type, "
    "'virtualMachineExtensionType', properties.virtualMachineExtensionType, "
    "'publisher', properties.publisher, 'provisioningState', properties.provisioningState)"
)
ARG_QUERIES["aks_security_profiles"] = (
    "resources | where type =~ 'microsoft.containerservice/managedclusters' "
    "| project id, name, type, properties=bag_pack('securityProfile', properties.securityProfile)"
)


def _native_number(value, source, integer=False):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise EvidenceError("invalid_response", "Source returned an invalid numeric observation.", source)
    if integer and type(value) is not int:
        raise EvidenceError("invalid_response", "Source count must be an integer.", source)
    return value


def _native_array(value, source):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise EvidenceError("invalid_response", "Source contains malformed encoded evidence.", source) from exc
    if not isinstance(value, list) or len(value) > 5000:
        raise EvidenceError("invalid_response", "Source evidence must be a bounded array.", source)
    return value


def _context_properties(record, source, subscription_id):
    resource_id = _get(record, "id")
    if (
        not isinstance(resource_id, str)
        or not resource_id.casefold().startswith("/subscriptions/" + subscription_id.casefold() + "/")
    ):
        raise EvidenceError("scope_mismatch", "Context record is outside the fixed subscription.", source)
    props = _get(record, "properties")
    if not isinstance(props, dict):
        raise EvidenceError("invalid_response", "Context properties are missing.", source)
    return props


def _resource_id(value, subscription_id):
    if not isinstance(value, str):
        return None
    value = unquote(value).casefold().rstrip("/")
    if (
        not (value == "/subscriptions/" + subscription_id.casefold()
             or value.startswith("/subscriptions/" + subscription_id.casefold() + "/"))
        or any(c in value for c in "\\?#") or any(ord(c) < 32 for c in value)
        or any(segment in (".", "..") for segment in value.split("/"))
    ):
        return None
    return value


def _assessment_resource_id(record, subscription_id):
    props = _get(record, "properties", {})
    details = _get(props, "resourceDetails", {})
    for key in ("Id", "ResourceId", "AzureResourceId", "NativeResourceId"):
        candidate = _resource_id(_get(details, key), subscription_id)
        if candidate:
            return candidate
    identifiers = _get(props, "resourceIdentifiers", [])
    if isinstance(identifiers, list):
        for identifier in identifiers:
            candidate = _resource_id(_get(identifier, "azureResourceId"), subscription_id)
            if candidate:
                return candidate
    additional = _get(props, "additionalData", {})
    candidate = _resource_id(_get(_get(additional, "resourceDetails", {}), "Id"), subscription_id)
    if candidate:
        return candidate
    parent = str(_get(record, "id", "")).casefold().split("/providers/microsoft.security/assessments/")[0]
    if "/resourcegroups/" in parent:
        return _resource_id(parent, subscription_id)
    return None


def _assessed_parent(record, resource_id, known_ids, subscription_id):
    additional = _get(_get(record, "properties", {}), "additionalData", {})
    explicit = _resource_id(_get(additional, "parentResource"), subscription_id)
    if explicit in known_ids:
        return explicit
    parents = [
        known for known in known_ids if (
            resource_id.startswith(known + "/securityentitydata/") or resource_id.startswith(known + "___")
        )
    ]
    if len(parents) == 1:
        return parents[0]
    return ""


def _resource_kind(resource_type):
    if resource_type.endswith("/extensions"):
        return "Resource extensions"
    if resource_type.startswith(("sqlonmachine", "sqlserverdatabase", "sqldatabase")):
        return "SQL dependent assets"
    if "container" in resource_type and "/securityentitydata/" in resource_type:
        return "Container dependent assets"
    kinds = (
        ("microsoft.hybridcompute/machines", "Arc servers"),
        ("microsoft.compute/virtualmachinescalesets", "VM scale sets"),
        ("microsoft.compute/virtualmachines", "Virtual machines"),
        ("microsoft.containerservice/managedclusters", "AKS"),
        ("microsoft.app/containerapps", "Container Apps"),
        ("microsoft.keyvault/vaults", "Key Vault"),
        ("microsoft.storage/storageaccounts", "Storage"),
        ("microsoft.web/sites", "App Service"),
        ("microsoft.containerregistry/registries", "Container Registry"),
        ("microsoft.sql/", "SQL"),
        ("microsoft.azurearcdata/", "Arc SQL"),
        ("microsoft.dbfor", "Databases"),
        ("microsoft.network/", "Network"),
    )
    return next((
        title for prefix, title in kinds
        if resource_type == prefix or prefix.endswith("/") and resource_type.startswith(prefix)
    ), "Other resources")


def _resource_row(resource, subscription_id, indexed_only=False):
    resource_id = _resource_id(_get(resource, "id"), subscription_id)
    if resource_id is None:
        raise EvidenceError("scope_mismatch", "Inventory has an invalid or out-of-scope resource ID.", "resource_inventory")
    tags = _get(resource, "tags", {})
    resource_type = _text(_get(resource, "type"), 240).casefold() or "unknown"
    parts = resource_id.split("/")
    group = parts[4] if len(parts) > 4 and parts[3] == "resourcegroups" else "Unknown"
    return {
        "resource_id": resource_id, "server_name": _text(_get(resource, "name"), 200) or parts[-1],
        "resource_group": group, "resource_type": resource_type, "resource_kind": _resource_kind(resource_type),
        "parent_resource_id": resource_id.rsplit("/", 2)[0] if resource_type.count("/") > 1 else "",
        "inventory_source": "Defender indexed only" if indexed_only else "ARM/Resource Graph inventory",
        "location": _text(_get(resource, "location"), 100) or "Unknown",
        "provider": "azure", "provider_evidence": "Azure resource ID; physical Arc hosting is handled separately.",
        "environment": "Unknown", "os": "Not observed", "os_version": "Not observed",
        "tags": {
            key: _text(value, 160) for key in (
                "Entorno", "Responsable", "Departamento", "Proyecto", "CentroCoste", "environment", "env"
            ) if (value := _get(tags, key)) is not None
        },
        "connectivity": "Not applicable", "last_status_change_utc": None,
        "last_status_change_note": "Arc connectivity applies only to Arc machines.",
        "mde_extension": "Not observed" if resource_kind_is_compute(resource_type) else "Not applicable",
        "extension_evidence": "No per-resource endpoint provisioning check; inventory presence is not sensor health.",
        "sensor_health": "Unknown" if resource_kind_is_compute(resource_type) else "Not applicable",
        "sensor_evidence": "Independent endpoint telemetry is not configured.",
        "servers_plan": "Unknown" if resource_kind_is_compute(resource_type) else "Not applicable",
        "plan_inherited": None, "plan_source": "Separate subscription plans below; not endpoint readiness.",
        "extensions": [], "fim_configuration": "Not verified",
        "fim_evidence": "No observed per-host FIM configuration; entitlement is not readiness.",
    }


def resource_kind_is_compute(resource_type):
    return resource_type in (
        "microsoft.hybridcompute/machines", "microsoft.compute/virtualmachines",
        "microsoft.compute/virtualmachinescalesets",
    )


def _patch_evidence(props, metadata, source):
    additional = _get(props, "additionalData", {})
    if not isinstance(additional, dict):
        raise EvidenceError("invalid_response", "Finding additionalData must be an object.", source)
    details = []
    for cve in _native_array(_get(additional, "CvesDetails"), source):
        if not isinstance(cve, dict):
            raise EvidenceError("invalid_response", "Embedded CVE details must be objects.", source)
        cve_id = _text(_get(cve, "CveId"), 80)
        if not re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", cve_id):
            raise EvidenceError("invalid_response", "Embedded source CVE identifier is invalid.", source)
        details.append({
            "cve_id": cve_id,
            "technical_severity": next((
                s for s in SEVERITIES[1:]
                if s.casefold() == str(_get(cve, "Severity", "")).casefold()
            ), "Unknown"),
            "fix_status": _text(_get(cve, "FixStatus"), 80) or "Unknown",
            "fixed_version": _text(_get(cve, "FixedVersion"), 100) or "Not supplied",
        })
    versions = _native_array(_get(additional, "DetectedSoftwareVersions"), source)
    kb = _text(_get(additional, "Kbid"), 40)
    if kb and not re.fullmatch(r"(?:KB)?[0-9]{5,10}", kb, re.IGNORECASE):
        raise EvidenceError("invalid_response", "Source KB identifier is invalid.", source)
    patch = {
        "software_name": _text(_get(additional, "SoftwareName"), 160),
        "vendor": _text(_get(additional, "SoftwareVendor"), 160),
        "detected_versions": [_text(v, 100) for v in versions],
        "fixed_version": _text(_get(additional, "FixedVersion"), 160) or "Not supplied",
        "maximum_cvss": _text(_get(additional, "MaxCvssScore"), 30),
        "kb": ("KB" + kb.upper().removeprefix("KB")) if kb else "",
        "patch_name": _text(_get(additional, "PatchName"), 300),
        "published_utc": _parsed_time(_get(additional, "PublishedDateTime")),
        "reboot_behavior": _text(_get(additional, "RebootBehavior"), 100),
        "scanner": _text(_get(additional, "ScannerName", _get(additional, "ScannerType")), 100),
        "rule_category": _text(_get(additional, "RuleCategory"), 100),
        "reason": _plain_text(_get(additional, "Reason"), 2000),
        "threat_exposure": _plain_text(_get(additional, "ThreatExposure"), 4000),
        "source": source + ".additionalData",
    }
    return patch, details


def _graph_entity(entity, source):
    if not isinstance(entity, dict):
        raise EvidenceError("invalid_response", "Attack-path entity must be an object.", source)
    internal_id = _text(_get(entity, "entityInternalId"), 200)
    if not internal_id:
        raise EvidenceError("invalid_response", "Attack-path entity lacks its graph ID.", source)
    resource_id = _text(_get(_get(entity, "entityIdentifiers", {}), "azureResourceId"), 1500)
    return {
        "entity_id": internal_id, "name": _text(_get(entity, "entityName"), 200) or internal_id,
        "type": _text(_get(entity, "entityType"), 160) or "Unknown",
        "resource_id": resource_id.casefold().rstrip("/"),
    }


def _normalize_attack_paths(records, inventory, subscription_id, reference):
    known = {r["resource_id"] for r in inventory if r.get("resource_type") == "microsoft.hybridcompute/machines"}
    result = []
    for record in records:
        source = "attack_paths"
        props = _context_properties(record, source, subscription_id)
        graph = _get(props, "graphComponent", {})
        if not isinstance(graph, dict):
            raise EvidenceError("invalid_response", "Attack graph must be an object.", source)
        entities = [_graph_entity(e, source) for e in _native_array(_get(graph, "entities"), source)]
        lookup = {e["entity_id"]: e for e in entities}
        if len(lookup) != len(entities):
            raise EvidenceError("invalid_response", "Attack graph repeats entity IDs.", source)
        endpoints = {}
        for field, id_field in (
            ("entryPoint", "entryPointEntityInternalId"), ("target", "targetEntityInternalId"),
        ):
            explicit = _get(props, field)
            if explicit is not None:
                entity = _graph_entity(explicit, source)
                if entity["entity_id"] not in lookup:
                    raise EvidenceError("invalid_response", "Attack endpoint is absent from the observed graph.", source)
                if entity != lookup[entity["entity_id"]]:
                    raise EvidenceError("invalid_response", "Attack endpoint conflicts with the graph.", source)
            else:
                entity = lookup.get(_text(_get(props, id_field), 200))
                if entity is None:
                    raise EvidenceError("invalid_response", "Attack endpoint cannot be resolved.", source)
            endpoints[field] = entity
        edges = []
        for edge in _native_array(_get(graph, "connections"), source):
            if not isinstance(edge, dict):
                raise EvidenceError("invalid_response", "Attack edge must be an object.", source)
            left = _text(_get(edge, "sourceEntityInternalId"), 200)
            right = _text(_get(edge, "targetEntityInternalId"), 200)
            if left not in lookup or right not in lookup:
                raise EvidenceError("invalid_response", "Attack edge references a missing entity.", source)
            edges.append({"source": left, "target": right, "label": _text(_get(edge, "title"), 200)})
        insights = []
        for insight in _native_array(_get(graph, "insights"), source):
            if not isinstance(insight, dict):
                raise EvidenceError("invalid_response", "Attack insight must be an object.", source)
            entity_id = _text(_get(insight, "entityInternalId"), 200)
            if entity_id not in lookup:
                raise EvidenceError("invalid_response", "Attack insight references a missing entity.", source)
            observed = {}
            additional = _get(insight, "additionalData", {})
            for key in ("exposedToInternet", "highRiskVulnerabilityInsights"):
                detail = _get(additional, key, {})
                if isinstance(detail, dict):
                    observed[key] = {
                        field: _get(detail, field) for field in (
                            "trustedExposure", "exposureWidth", "hasHighOrCritical", "maxCvssScore"
                        ) if _get(detail, field) is not None
                    }
            insights.append({
                "entity_id": entity_id, "title": _text(_get(insight, "title"), 180),
                "observations": observed,
            })
        assessment_ids = set()
        for mapping in (_get(props, "assessments", {}), _get(graph, "assessments", {})):
            if not isinstance(mapping, dict):
                raise EvidenceError("invalid_response", "Attack assessment mapping must be an object.", source)
            for nested in mapping.values():
                if isinstance(nested, dict):
                    for candidate in nested:
                        if isinstance(candidate, str) and "/providers/microsoft.security/assessments/" in candidate.casefold():
                            assessment_ids.add(candidate.casefold())
        arc_ids = sorted({e["resource_id"] for e in entities if e["resource_id"] in known})
        steps = _get(props, "attackPathSteps", {})
        if not isinstance(steps, dict):
            raise EvidenceError("invalid_response", "Attack steps must be a source mapping.", source)
        result.append({
            "path_id": _text(_get(record, "name"), 200),
            "title": _plain_text(_get(props, "displayName"), 300),
            "description": _plain_text(_get(props, "description")),
            "risk_level": _native_risk(_get(props, "riskLevel")),
            "risk_factors": [_text(v, 160) for v in _native_array(_get(props, "riskFactors"), source)],
            "entry_point": endpoints["entryPoint"], "target": endpoints["target"],
            "entities": entities, "edges": edges, "insights": insights,
            "steps": [_plain_text(v, 1000) for v in steps.values()],
            "assessment_ids": sorted(assessment_ids),
            "story": _plain_text(_get(props, "attackStory")),
            "remediation": _plain_text(_get(props, "manualRemediationSteps")),
            "partial_graph": _get(props, "isPartialAttackPath") is True,
            "arc_resource_ids": arc_ids,
            "resource_ids": sorted({e["resource_id"] for e in entities if e["resource_id"]}),
            "association": "Arc-related" if arc_ids else "Other subscription resources",
            "scope": "Subscription context; not an Arc-only graph",
            "source": source, "reference_utc": reference, "provenance": "LIVE",
        })
    return sorted(result, key=lambda p: (RISKS.index(p["risk_level"]), p["path_id"]))


def _normalize_software(records, inventory, subscription_id, reference):
    known = {r["resource_id"] for r in inventory if r.get("resource_type") == "microsoft.hybridcompute/machines"}
    result = []
    for record in records:
        props = _context_properties(record, "software_inventory", subscription_id)
        resource_id = _text(_get(props, "azureVmId"), 1500).casefold().rstrip("/")
        if not resource_id.startswith("/subscriptions/" + subscription_id + "/"):
            raise EvidenceError("scope_mismatch", "Software resource is outside the fixed subscription.", "software_inventory")
        arc_ids = [resource_id] if resource_id in known else []
        result.append({
            "software_id": _text(_get(record, "id"), 1800), "resource_id": resource_id,
            "server_name": resource_id.rsplit("/", 1)[-1],
            "software_name": _text(_get(props, "softwareName"), 200),
            "version": _text(_get(props, "version"), 120), "vendor": _text(_get(props, "vendor"), 120),
            "os": _text(_get(props, "osPlatform"), 120),
            "known_vulnerabilities": _native_number(_get(props, "numberOfKnownVulnerabilities"), "software_inventory", True),
            "end_of_support_status": _text(_get(props, "endOfSupportStatus"), 100) or "Unknown",
            "end_of_support_utc": _parsed_time(_get(props, "endOfSupportDate")),
            "first_seen_utc": _parsed_time(_get(props, "firstSeenAt")),
            "arc_resource_ids": arc_ids,
            "resource_ids": [resource_id],
            "association": "Arc-related" if arc_ids else "Other subscription resources",
            "scope": "Arc machine" if arc_ids else "Subscription context",
            "source": "software_inventory", "provenance": "LIVE", "reference_utc": reference,
        })
    return sorted(result, key=lambda s: (s["server_name"], s["software_name"], s["version"]))


def _normalize_context(records, source, subscription_id, reference):
    result = []
    for record in records:
        props = _context_properties(record, source, subscription_id)
        row = {
            "id": _text(_get(record, "id"), 1800), "name": _text(_get(record, "name"), 200),
            "scope": "Subscription context", "source": source, "reference_utc": reference, "provenance": "LIVE",
        }
        if source in ("subscription_secure_score", "secure_score_controls"):
            score = _get(props, "score", {})
            row.update({
                "title": _text(_get(props, "displayName"), 200),
                "current": _native_number(_get(score, "current"), source),
                "maximum": _native_number(_get(score, "max"), source),
                "percentage": _native_number(_get(score, "percentage"), source),
            })
            if (
                row["percentage"] is not None and row["percentage"] > 1
                or row["current"] is not None and row["maximum"] is not None and row["current"] > row["maximum"]
            ):
                raise EvidenceError("invalid_response", "Classic score observation is inconsistent.", source)
            if source == "secure_score_controls":
                definition = _get(_get(props, "definition", {}), "properties", {})
                row.update({
                    "potential_score_gain": (
                        round(row["maximum"] - row["current"], 4)
                        if row["maximum"] is not None and row["current"] is not None else None
                    ),
                    "healthy": _native_number(_get(props, "healthyResourceCount"), source, True),
                    "unhealthy": _native_number(_get(props, "unhealthyResourceCount"), source, True),
                    "not_applicable": _native_number(_get(props, "notApplicableResourceCount"), source, True),
                    "assessment_definition_ids": [
                        _text(_get(a, "id"), 500) for a in _native_array(_get(definition, "assessmentDefinitions"), source)
                    ],
                })
        elif source == "risk_secure_score":
            row.update({
                "assessment_category": _text(_get(props, "assessmentCategory"), 100),
                "native_numerator": _native_number(_get(props, "secureScoreNumerator"), source),
                "native_denominator": _native_number(_get(props, "secureScoreDenominator"), source),
                "qualification": "Native observations only; no unverified ratio or percentage is derived.",
            })
        elif source == "subscription_plans":
            row.update({
                "pricing_tier": _text(_get(props, "pricingTier"), 60) or "Unknown",
                "sub_plan": _text(_get(props, "subPlan"), 120),
                "coverage": _text(_get(props, "resourcesCoverageStatus"), 100) or "Unknown",
                "extensions": [
                    {"name": _text(_get(e, "name"), 100), "enabled": _get(e, "isEnabled")}
                    for e in _native_array(_get(props, "extensions"), source)
                ],
            })
        else:
            row.update({"state": _text(_get(props, "state"), 100) or "Unknown"})
            for field in (
                "passedControls", "failedControls", "skippedControls", "unsupportedControls",
                "passedAssessments", "failedAssessments", "skippedAssessments",
                "passedResources", "failedResources", "skippedResources",
            ):
                if _get(props, field) is not None:
                    row[field] = _native_number(_get(props, field), source, True)
            row["description"] = _plain_text(_get(props, "description"), 2000)
        result.append(row)
    return result


def _validate_config():
    values = {}
    for name, value in (
        ("SUBSCRIPTION_ID", SUBSCRIPTION_ID), ("TENANT_ID", TENANT_ID),
        ("MANAGED_IDENTITY_CLIENT_ID", MANAGED_IDENTITY_CLIENT_ID),
    ):
        try:
            if not isinstance(value, str) or str(UUID(value)) != value.casefold():
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise EvidenceError(
                "configuration_required", f"Set {name} to the correct GUID before deployment.", "configuration"
            ) from exc
        values[name] = value.casefold()
    return values


def _get_token(client_id):
    try:
        from azure.identity import ManagedIdentityCredential, CredentialUnavailableError
        from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
    except ImportError as exc:
        raise EvidenceError(
            "dependency_missing", "The live tool requires azure-identity and its Azure Core dependency.", "identity"
        ) from exc
    try:
        with ManagedIdentityCredential(client_id=client_id) as credential:
            token = credential.get_token(ARM_ORIGIN + "/.default").token
    except (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError) as exc:
        raise EvidenceError(
            "authentication_failed", "Managed identity could not acquire the ARM token. Verify the assigned Client ID.",
            "identity",
        ) from exc
    if not isinstance(token, str) or not token:
        raise EvidenceError("authentication_failed", "Managed identity returned no ARM token.", "identity")
    return token


class ArmClient:
    def __init__(self, token):
        try:
            import requests
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "The live tool requires requests.", "http_client") from exc
        self.requests = requests
        self.session = requests.Session()
        self.session.headers.update({"Authorization": "Bearer " + token, "Accept": "application/json"})

    def close(self):
        self.session.close()

    def request(self, method, url, source, body=None):
        parsed = urlsplit(url)
        if (
            method not in ("GET", "POST") or parsed.scheme != "https"
            or parsed.netloc.casefold() != "management.azure.com" or parsed.fragment
            or parsed.username or parsed.password or len(url) > 16384
        ):
            raise EvidenceError("unsafe_endpoint", "Only fixed public ARM endpoints are allowed.", source)
        if method == "POST" and parsed.path.casefold() != "/providers/microsoft.resourcegraph/resources":
            raise EvidenceError("unsafe_endpoint", "POST is allowed only for the fixed read-only Resource Graph query.", source)
        for attempt in range(3):
            try:
                response = self.session.request(
                    method, url, json=body, timeout=(10, 30), allow_redirects=False,
                )
            except self.requests.RequestException as exc:
                raise EvidenceError("transport_failed", "ARM transport failed; no response was accepted.", source) from exc
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                delay = response.headers.get("Retry-After", "")
                time.sleep(min(int(delay), 5) if re.fullmatch(r"[0-9]{1,4}", delay) else attempt + 1)
                continue
            if response.status_code != 200:
                raise EvidenceError(
                    "api_failed", f"{source} returned HTTP {response.status_code}; this source is unavailable.",
                    source, response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise EvidenceError("invalid_response", "ARM returned invalid JSON.", source) from exc
            if not isinstance(payload, dict):
                raise EvidenceError("invalid_response", "ARM response must be a JSON object.", source)
            return payload
        raise EvidenceError("api_failed", "ARM retries were exhausted.", source)


def _validated_next_link(link, initial_url, source):
    if not isinstance(link, str) or not link or len(link) > 16384:
        raise EvidenceError("invalid_pagination", "Invalid ARM nextLink.", source)
    parsed, initial = urlsplit(link), urlsplit(initial_url)
    if (
        parsed.scheme != "https" or parsed.netloc.casefold() != "management.azure.com"
        or parsed.fragment or parsed.username or parsed.password
        or unquote(parsed.path).casefold() != unquote(initial.path).casefold()
        or "\\" in parsed.path or any(p in (".", "..") for p in unquote(parsed.path).split("/"))
    ):
        raise EvidenceError("invalid_pagination", "ARM nextLink changed origin or resource scope.", source)
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise EvidenceError("invalid_pagination", "Malformed nextLink query.", source) from exc
    expected_version = dict(parse_qsl(initial.query)).get("api-version")
    keys = [key.casefold() for key, _ in query]
    if (
        len(keys) != len(set(keys))
        or any(key not in ("api-version", "$skiptoken", "skiptoken", "$skip", "$top") for key in keys)
        or next((v for k, v in query if k.casefold() == "api-version"), None) != expected_version
    ):
        raise EvidenceError("invalid_pagination", "ARM nextLink changed API version or paging parameters.", source)
    return link


def _list_arm(client, url, source):
    rows, seen_links, seen_ids = [], set(), set()
    next_url = url
    for _ in range(MAX_PAGES):
        if next_url in seen_links:
            raise EvidenceError("invalid_pagination", "ARM pagination repeated a page.", source)
        seen_links.add(next_url)
        payload = client.request("GET", next_url, source)
        page = payload.get("value")
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise EvidenceError("invalid_response", "ARM list must contain an array of objects.", source)
        for row in page:
            row_id = _get(row, "id")
            if not isinstance(row_id, str) or not row_id:
                raise EvidenceError("invalid_response", "ARM list row is missing its resource ID.", source)
            key = row_id.casefold().rstrip("/")
            if key in seen_ids:
                raise EvidenceError("invalid_pagination", "ARM pagination repeated a resource ID.", source)
            seen_ids.add(key)
        rows.extend(page)
        if len(rows) > MAX_SOURCE_ROWS:
            raise EvidenceError("scope_too_large", "Source exceeded the safety bound; no truncated success is returned.", source)
        link = payload.get("nextLink")
        if link is None:
            return rows, len(seen_links)
        if not page:
            raise EvidenceError("invalid_pagination", "Empty ARM page has a continuation link.", source)
        next_url = _validated_next_link(link, url, source)
    raise EvidenceError("invalid_pagination", "ARM pagination exceeded the page safety bound.", source)


def _query_arg(client, source, subscription_id):
    url = ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API_VERSION
    rows, seen_tokens, seen_ids = [], set(), set()
    skip_token, expected_total = None, None
    for page_number in range(1, MAX_PAGES + 1):
        options = {"$top": 1000, "resultFormat": "objectArray"}
        if skip_token is not None:
            options["$skipToken"] = skip_token
        payload = client.request("POST", url, source, {
            "subscriptions": [subscription_id], "query": ARG_QUERIES[source], "options": options,
        })
        page, count, total = payload.get("data"), payload.get("count"), payload.get("totalRecords")
        if (
            not isinstance(page, list) or any(not isinstance(row, dict) for row in page)
            or type(count) is not int or count != len(page)
            or type(total) is not int or total < 0
        ):
            raise EvidenceError("invalid_response", "Resource Graph paging shape/counts are invalid.", source)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise EvidenceError(
                "snapshot_changed", "Resource Graph total changed between pages; rerun for coherent evidence.", source
            )
        for row in page:
            row_id = _get(row, "id")
            if not isinstance(row_id, str) or not row_id:
                raise EvidenceError("invalid_response", "Resource Graph row is missing its ID.", source)
            key = row_id.casefold().rstrip("/")
            if key in seen_ids:
                raise EvidenceError("invalid_pagination", "Resource Graph repeated a resource ID.", source)
            seen_ids.add(key)
        rows.extend(page)
        if len(rows) > MAX_SOURCE_ROWS:
            raise EvidenceError("scope_too_large", "Resource Graph exceeded the safety bound.", source)
        next_token = payload.get("$skipToken")
        truncated = str(payload.get("resultTruncated", "")).casefold()
        if truncated not in ("true", "false"):
            raise EvidenceError("invalid_response", "Resource Graph omitted a valid truncation flag.", source)
        # ARG can advertise a token even when resultTruncated is 'false'.
        if next_token is not None:
            if (
                not isinstance(next_token, str) or not next_token or len(next_token) > 8192
                or next_token in seen_tokens or not page
            ):
                raise EvidenceError("invalid_pagination", "Resource Graph continuation token is invalid/repeated.", source)
            seen_tokens.add(next_token)
            skip_token = next_token
            continue
        if truncated == "true" or len(rows) != expected_total:
            raise EvidenceError("invalid_pagination", "Resource Graph ended before all declared records were read.", source)
        return rows, page_number
    raise EvidenceError("invalid_pagination", "Resource Graph pagination exceeded the safety bound.", source)


def _arc_id(value, subscription_id, allow_child=False):
    if not isinstance(value, str) or "\\" in value or "?" in value or "#" in value:
        return None
    decoded = unquote(value).rstrip("/")
    if (
        any(c in decoded for c in "\\?#") or any(ord(c) < 32 for c in decoded)
        or any(p in (".", "..") for p in decoded.split("/"))
    ):
        return None
    pattern = (
        r"^(/subscriptions/([0-9a-f-]{36})/resourcegroups/([^/]+)/providers/"
        r"microsoft\.hybridcompute/machines/([^/]+))"
    )
    suffix = r"(?:/providers/microsoft\.security/[^?]*|)$" if allow_child else r"$"
    match = re.fullmatch(pattern + suffix, decoded, flags=re.IGNORECASE)
    if not match or match.group(2).casefold() != subscription_id.casefold():
        return None
    return match.group(1).casefold()


def _joined_arc_ids(record, known_ids, subscription_id):
    candidates = [_get(record, "id")]
    containers = {
        "resourcedetails", "resourceidentifiers", "resources", "entities", "additionaldata",
        "assessedresource", "resource", "resourcemetadata",
    }
    identifiers = {"id", "resourceid", "azureresourceid", "assessedresourceid", "resourceuri"}

    def visit(value, depth=0):
        if depth > 8:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    continue
                if key.casefold() in identifiers and isinstance(item, str):
                    candidates.append(item)
                elif key.casefold() in containers:
                    visit(item, depth + 1)

    properties = _get(record, "properties", {})
    if isinstance(properties, dict):
        for key, value in properties.items():
            if isinstance(key, str) and key.casefold() in containers:
                visit(value)
    result = set()
    for candidate in candidates:
        resource_id = _arc_id(candidate, subscription_id, allow_child=True)
        if resource_id in known_ids:
            result.add(resource_id)
    return sorted(result)


def _source(name, status, reference, records=None, note="", errors=None, **extra):
    return {
        "name": name, "status": status, "reference_utc": reference, "records": records,
        "note": note, "errors": errors or [], **extra,
    }


def _parsed_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _inventory_row(machine, subscription_id, reference):
    resource_id = _arc_id(_get(machine, "id"), subscription_id)
    if resource_id is None:
        raise EvidenceError("scope_mismatch", "Arc inventory contained an out-of-scope/invalid resource ID.", "arc_inventory")
    props = _get(machine, "properties")
    if not isinstance(props, dict):
        raise EvidenceError("invalid_response", "Arc machine properties are missing.", "arc_inventory")
    parts = unquote(_get(machine, "id")).rstrip("/").split("/")
    provider_raw = _text(_get(_get(props, "cloudMetadata", {}), "provider"), 60)
    provider_map = {
        "gcp": "gcp", "google": "gcp", "googlecloud": "gcp",
        "aws": "aws", "amazon": "aws", "azure": "azure",
        "onprem": "onprem", "onpremises": "onprem", "on-premises": "onprem",
    }
    provider = provider_map.get(provider_raw.casefold(), "unknown")
    provider_evidence = (
        "Arc cloudMetadata.provider: " + provider_raw if provider != "unknown"
        else "Arc cloudMetadata.provider is absent/N/A/unrecognized; physical or cloud location is not verified."
    )
    tags = _get(machine, "tags", {})
    environment_raw = _text(_get(tags, "environment", _get(tags, "env", _get(tags, "Entorno", ""))), 50)
    aliases = {
        "prod": "Production", "produccion": "Production", "producci\u00f3n": "Production",
        "preprod": "Preproduction", "preproduccion": "Preproduction",
        "development": "Dev", "desarrollo": "Dev", "test": "Preproduction",
    }
    environment = aliases.get(environment_raw.casefold())
    if environment is None:
        environment = next(
            (e for e in ENVIRONMENTS[1:] if e.casefold() == environment_raw.casefold()), "Unknown"
        )
    state_raw = _text(_get(props, "status"), 40)
    state = next((s for s in CONNECTIVITY[1:] if s.casefold() == state_raw.casefold()), "Unknown")
    last_change = _parsed_time(_get(props, "lastStatusChange"))
    return {
        "resource_id": resource_id, "server_name": parts[8], "resource_group": parts[4],
        "resource_type": "microsoft.hybridcompute/machines", "resource_kind": "Arc servers",
        "inventory_source": "ARM/Resource Graph inventory", "parent_resource_id": "",
        "provider": provider, "provider_evidence": provider_evidence, "environment": environment,
        "os": _text(_get(props, "osName", _get(props, "osType", "Unknown")), 100) or "Unknown",
        "os_version": _text(_get(props, "osVersion"), 100) or "Unknown",
        "location": _text(_get(machine, "location"), 100) or "Unknown",
        "tags": {
            key: _text(value, 160) for key in (
                "Entorno", "Responsable", "Departamento", "Proyecto", "CentroCoste", "environment", "env"
            ) if (value := _get(tags, key)) is not None
        },
        "connectivity": state, "last_status_change_utc": last_change,
        "last_status_change_note": (
            "Source status-change timestamp, not an MDE heartbeat." if last_change
            else "Status-change time is missing/invalid; no heartbeat time is inferred."
        ),
        "mde_extension": "Unknown", "extension_evidence": "Extension source not yet collected.",
        "sensor_health": "Unknown",
        "sensor_evidence": "No independent MDE sensor-health API is configured. ARM extension state is not sensor health.",
        "servers_plan": "Unknown", "plan_inherited": None, "plan_source": "Unknown",
        "extensions": [], "fim_configuration": "Not verified",
        "fim_evidence": "Servers plan/MDE extension does not verify enabled per-host FIM configuration.",
        "reference_utc": reference, "provenance": "LIVE",
    }


def _inspect_machine(token, row, reference):
    client = ArmClient(token)
    sources = {}
    safe_id = "/".join(quote(segment, safe="") for segment in row["resource_id"].split("/"))
    try:
        try:
            extensions, pages = _list_arm(
                client, ARM_ORIGIN + safe_id + "/extensions?api-version=" + ARC_API_VERSION, "arc_extensions"
            )
            mde_extensions = []
            normalized_extensions = []
            for extension in extensions:
                extension_id = _get(extension, "id", "")
                if not extension_id.casefold().startswith(row["resource_id"] + "/extensions/"):
                    raise EvidenceError("scope_mismatch", "Extension belongs to an unexpected machine.", "arc_extensions")
                props = _get(extension, "properties")
                if not isinstance(props, dict):
                    raise EvidenceError("invalid_response", "Extension properties are missing.", "arc_extensions")
                extension_type = _text(_get(props, "type", _get(extension, "name")), 100)
                publisher = _text(_get(props, "publisher"), 100)
                normalized_extensions.append({
                    "name": extension_type, "publisher": publisher,
                    "state": _text(_get(props, "provisioningState"), 80) or "Unknown",
                })
                if extension_type.casefold() in ("mde.windows", "mde.linux") and (
                    publisher.casefold() != "microsoft.azure.azuredefenderforservers"
                ):
                    raise EvidenceError(
                        "invalid_response", "MDE extension publisher could not be verified.", "arc_extensions"
                    )
                if extension_type.casefold() in ("mde.windows", "mde.linux") and (
                    publisher.casefold() == "microsoft.azure.azuredefenderforservers"
                ):
                    state = _text(_get(props, "provisioningState"), 40)
                    if state.casefold() == "failed":
                        mde_extensions.append("Failed")
                    elif state.casefold() == "succeeded":
                        mde_extensions.append("Succeeded")
                    else:
                        mde_extensions.append("Unknown")
            row["mde_extension"] = (
                "Missing" if not mde_extensions else
                "Failed" if "Failed" in mde_extensions else
                "Unknown" if "Unknown" in mde_extensions else "Succeeded"
            )
            row["extensions"] = normalized_extensions
            row["extension_evidence"] = (
                f"ARM extension provisioning: {row['mde_extension']}. "
                "Extension settings and unfiltered instance-view messages are deliberately not exported."
            )
            sources["arc_extensions"] = {"status": "complete", "pages": pages, "records": len(extensions)}
        except EvidenceError as exc:
            row["extension_evidence"] = "Extension source unavailable; Missing is not inferred."
            sources["arc_extensions"] = {"status": "unavailable", "error": exc.as_dict(), "records": None}
        try:
            payload = client.request(
                "GET",
                ARM_ORIGIN + safe_id + "/providers/Microsoft.Security/pricings/VirtualMachines"
                + "?api-version=" + PRICING_API_VERSION,
                "effective_servers_plan",
            )
            props = _get(payload, "properties")
            if not isinstance(props, dict):
                raise EvidenceError("invalid_response", "Effective pricing properties are missing.", "effective_servers_plan")
            tier, plan = _get(props, "pricingTier"), _get(props, "subPlan")
            if tier == "Free":
                row["servers_plan"] = "Free"
            elif tier == "Standard" and plan in ("P1", "P2"):
                row["servers_plan"] = plan
            else:
                raise EvidenceError("invalid_response", "Effective Servers pricing could not be resolved.", "effective_servers_plan")
            inherited = _get(props, "inherited")
            if isinstance(inherited, str) and inherited.casefold() in ("true", "false"):
                inherited = inherited.casefold() == "true"
            if not isinstance(inherited, bool):
                raise EvidenceError("invalid_response", "Effective pricing omitted valid inheritance evidence.", "effective_servers_plan")
            row["plan_inherited"] = inherited
            row["plan_source"] = "Resource-scoped Microsoft.Security/pricings/VirtualMachines"
            sources["effective_servers_plan"] = {"status": "complete", "records": 1}
        except EvidenceError as exc:
            row.update({"servers_plan": "Unknown", "plan_inherited": None, "plan_source": "Unavailable"})
            sources["effective_servers_plan"] = {"status": "unavailable", "error": exc.as_dict(), "records": None}
    finally:
        client.close()
    return row, sources


def _normalize_findings(records, source, inventory, subscription_id, reference, arc_only=True):
    known = {row["resource_id"]: row for row in inventory}
    category = {
        "defender_recommendations": "Recommendation",
        "defender_vulnerabilities": "Vulnerability", "defender_alerts": "Alert",
    }[source]
    findings, matched, unmatched, non_actionable, sql_descendants = [], 0, 0, 0, 0
    for record in records:
        props = _get(record, "properties", {})
        details = _get(props, "resourceDetails", {})
        resource_type = _text(_get(details, "resourceType"), 100).casefold()
        assessed_type = _text(_get(_get(props, "additionalData", {}), "assessedResourceType"), 100).casefold()
        record_id = _text(_get(record, "id"), 1500).casefold()
        if arc_only and (
            resource_type.startswith(("sqlonmachine", "microsoft.sql/", "microsoft.azurearcdata/"))
            or assessed_type.startswith(("sqldatabase", "sqlserverdatabase", "sqlonmachine"))
            or "/providers/microsoft.azurearcdata/" in record_id
            or "/providers/microsoft.sql/" in record_id
        ):
            sql_descendants += 1
            continue
        if arc_only:
            ids = _joined_arc_ids(record, known, subscription_id)
        else:
            resource_id = _assessment_resource_id(record, subscription_id)
            ids = [resource_id] if resource_id in known else []
        if not ids:
            unmatched += 1
            continue
        matched += 1
        props = _get(record, "properties")
        if not isinstance(props, dict):
            raise EvidenceError("invalid_response", "Arc-matched finding properties are missing.", source)
        status_value = _get(props, "status", {})
        state = (
            _get(status_value, "code", "Unknown") if isinstance(status_value, dict)
            else _text(status_value, 60) or "Unknown"
        )
        if not isinstance(state, str) or not state:
            raise EvidenceError("invalid_response", "Arc-matched finding has invalid status evidence.", source)
        if category == "Alert":
            state = _text(_get(props, "status", "Unknown"), 60) or "Unknown"
            if state.casefold() in ("resolved", "dismissed"):
                non_actionable += 1
        elif str(state).casefold() in ("healthy", "notapplicable"):
            non_actionable += 1
        metadata = _get(props, "metadata", {})
        severity_raw = _text(_get(props, "severity", _get(metadata, "severity", "Unknown")), 40)
        severity = next(
            (s for s in SEVERITIES[1:] if s.casefold() == severity_raw.casefold()), "Unknown"
        )
        title = _text(_get(
            props, "displayName", _get(props, "alertDisplayName", _get(metadata, "displayName", category))
        ), 180) or category
        first_evaluation = _parsed_time(_get(status_value, "firstEvaluationDate"))
        source_time = _parsed_time(_get(
            props, "timeGenerated", _get(props, "reportedTime", _get(status_value, "statusChangeDate"))
        ))
        source_label = "ARM Security alerts" if category == "Alert" else "Resource Graph"
        risk = _get(props, "risk", {})
        patch, cve_details = _patch_evidence(props, metadata, source)
        for resource_id in ids:
            row = known[resource_id]
            raw_resource_data = _get(props, "resourceAdditionalData")
            if raw_resource_data:
                if isinstance(raw_resource_data, str):
                    try:
                        raw_resource_data = json.loads(raw_resource_data)
                    except ValueError as exc:
                        raise EvidenceError("invalid_response", "Malformed resourceAdditionalData JSON.", source) from exc
                if not isinstance(raw_resource_data, dict):
                    raise EvidenceError("invalid_response", "resourceAdditionalData must be an object.", source)
                os_details = _get(raw_resource_data, "MachineOsDetails", {})
                observed_os = _text(_get(os_details, "OsName"), 160)
                if observed_os and row["os"] in ("Not observed", "Unknown"):
                    row["os"] = observed_os
            findings.append({
                "finding_id": _text(_get(record, "id"), 1500),
                "resource_id": resource_id, "server_name": row["server_name"],
                "resource_group": row["resource_group"], "provider": row["provider"],
                "resource_type": row.get("resource_type", "microsoft.hybridcompute/machines"),
                "parent_resource_id": row.get("parent_resource_id", ""),
                "environment": row["environment"], "category": category, "severity": severity,
                "technical_severity": severity,
                "risk_level": _native_risk(_get(risk, "level")),
                "risk_source": "properties.risk.level (not metadata.severity)",
                "risk_factors": [_text(v, 200) for v in _native_array(_get(risk, "riskFactors"), source)],
                "recommendation_id": _text(_get(record, "name"), 200) or _get(record, "id").rsplit("/", 1)[-1],
                "recommendation_category": _text(
                    _get(metadata, "recommendationCategory", _get(metadata, "securityIssue")), 160
                ) or "Unknown",
                "description": _plain_text(_get(metadata, "description")),
                "assessment_type": _text(_get(metadata, "assessmentType"), 100) or "Unknown",
                "management_provider": _text(_get(metadata, "managementProvider"), 100),
                "remediation": _plain_text(_get(metadata, "remediationDescription")),
                "portal_url": _safe_link(_get(_get(props, "links", {}), "azurePortal")),
                "patch": patch, "cve_details": cve_details,
                "status": _text(state, 60), "title": title, "source": source,
                "source_time_utc": source_time,
                "first_evaluation_utc": first_evaluation,
                "evidence": (
                    f"{source_label} exact resource-ID match; source status {state}. "
                    "Retrieval time is not evaluation freshness or a current sensor-health check."
                ),
                "reference_utc": reference, "provenance": "LIVE",
            })
    return findings, {
        "arc_matched_records": matched, "excluded_unmatched_records": unmatched,
        "excluded_sql_descendant_records": sql_descendants, "non_actionable_records": non_actionable,
    }


def _subscription_recommendations(records, subscription_id, reference):
    result = []
    for record in records:
        props = _context_properties(record, "defender_recommendations", subscription_id)
        details = _get(props, "resourceDetails", {})
        candidate = _get(details, "Id", _get(details, "ResourceId"))
        if not isinstance(candidate, str):
            candidate = record["id"].split("/providers/Microsoft.Security/assessments/")[0]
        if _resource_id(candidate, subscription_id) is None:
            continue
        metadata = _get(props, "metadata", {})
        result.append({
            "finding_id": _text(record["id"], 1800).casefold(),
            "resource_id": _text(candidate, 1500).casefold().rstrip("/"),
            "recommendation_id": _text(_get(record, "name"), 200),
            "title": _plain_text(_get(props, "displayName"), 300),
            "status": _text(_get(_get(props, "status", {}), "code"), 80) or "Unknown",
            "risk_level": _native_risk(_get(_get(props, "risk", {}), "level")),
            "technical_severity": _text(_get(metadata, "severity"), 80) or "Unknown",
            "remediation": _plain_text(_get(metadata, "remediationDescription")),
            "portal_url": _safe_link(_get(_get(props, "links", {}), "azurePortal")),
            "scope": "Subscription context; includes other resources and SQL descendants",
            "source": "defender_recommendations", "reference_utc": reference, "provenance": "LIVE",
        })
    return result


def _collect_context(client, subscription_id, reference, inventory):
    context = {
        "posture": {"scores": [], "controls": [], "risk_score_observations": []},
        "attack_paths": [], "software": [], "plans": [],
        "compliance": {"standards": [], "controls": [], "assessments": []},
    }
    targets = {
        "attack_paths": (context, "attack_paths"),
        "software_inventory": (context, "software"),
        "secure_score_controls": (context["posture"], "controls"),
        "risk_secure_score": (context["posture"], "risk_score_observations"),
        "compliance_controls": (context["compliance"], "controls"),
        "compliance_assessments": (context["compliance"], "assessments"),
    }
    sources = []
    for source, (target, key) in targets.items():
        try:
            rows, pages = _query_arg(client, source, subscription_id)
            if source == "attack_paths":
                normalized = _normalize_attack_paths(rows, inventory, subscription_id, reference)
            elif source == "software_inventory":
                normalized = _normalize_software(rows, inventory, subscription_id, reference)
            else:
                normalized = _normalize_context(rows, source, subscription_id, reference)
            target[key] = normalized
            sources.append(_source(
                source, "complete", reference, len(rows),
                "Fixed subscription context, all ARG pages read; explicit Arc association where observed.",
                pages=pages,
            ))
        except EvidenceError as exc:
            sources.append(_source(
                source, "unavailable", reference,
                note="Subscription context source unavailable; no count or healthy state is inferred.",
                errors=[exc.as_dict()],
            ))
    rest_paths = {
        "subscription_secure_score": ("secureScores", "2020-01-01", context["posture"], "scores"),
        "subscription_plans": ("pricings", "2024-01-01", context, "plans"),
        "compliance_standards": (
            "regulatoryComplianceStandards", "2019-01-01-preview", context["compliance"], "standards"
        ),
    }
    for source, (path, version, target, key) in rest_paths.items():
        try:
            rows, pages = _list_arm(
                client, ARM_ORIGIN + "/subscriptions/" + subscription_id
                + "/providers/Microsoft.Security/" + path + "?api-version=" + version, source,
            )
            target[key] = _normalize_context(rows, source, subscription_id, reference)
            sources.append(_source(
                source, "complete", reference, len(rows),
                "Read-only fixed subscription context; not an Arc-only metric or certification.", pages=pages,
            ))
        except EvidenceError as exc:
            sources.append(_source(
                source, "unavailable", reference, note="Context API unavailable; values remain Unknown.",
                errors=[exc.as_dict()],
            ))
    return context, sources


def _collect_live(config, reference):
    token = _get_token(config["MANAGED_IDENTITY_CLIENT_ID"])
    client = ArmClient(token)
    subscription_id = config["SUBSCRIPTION_ID"]
    sources = []
    try:
        subscription = client.request(
            "GET", ARM_ORIGIN + "/subscriptions/" + subscription_id + "?api-version=2022-12-01", "scope_validation"
        )
        if (
            str(_get(subscription, "subscriptionId", "")).casefold() != subscription_id
            or str(_get(subscription, "tenantId", "")).casefold() != config["TENANT_ID"]
        ):
            raise EvidenceError("scope_mismatch", "Subscription/tenant do not match the fixed configuration.", "scope_validation")
        if _get(subscription, "state", "Enabled") != "Enabled":
            raise EvidenceError("scope_unavailable", "Configured subscription is not Enabled.", "scope_validation")
        resources, resource_pages = _query_arg(client, "resource_inventory", subscription_id)
        inventory_by_id = {
            row["resource_id"]: row for resource in resources
            for row in [_resource_row(resource, subscription_id)]
        }
        sources.append(_source(
            "resource_inventory", "complete", reference, len(resources),
            "Complete fixed-subscription Resources inventory; no secret values or arbitrary workload configuration.",
            pages=resource_pages,
        ))
        machines, pages = _list_arm(
            client, ARM_ORIGIN + "/subscriptions/" + subscription_id
            + "/providers/Microsoft.HybridCompute/machines?api-version=" + ARC_API_VERSION, "arc_inventory",
        )
        if len(machines) > MAX_MACHINES:
            raise EvidenceError("scope_too_large", "More than 1000 Arc servers; use a reviewed narrower tool configuration.", "arc_inventory")
        arc_inventory = [_inventory_row(machine, subscription_id, reference) for machine in machines]
        if len({row["resource_id"] for row in arc_inventory}) != len(arc_inventory):
            raise EvidenceError(
                "invalid_pagination", "Arc inventory repeated a canonical resource ID.", "arc_inventory"
            )
        sources.append(_source(
            "arc_inventory", "complete", reference, len(arc_inventory),
            "ARM subscription inventory; all pages read. Connected is Arc status, not MDE sensor health.",
            pages=pages,
        ))
        inspections = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            inspections = list(executor.map(
                lambda row: _inspect_machine(token, row, reference), arc_inventory,
            ))
        for row, _ in inspections:
            row.update({
                "resource_type": "microsoft.hybridcompute/machines", "resource_kind": "Arc servers",
                "inventory_source": "ARM/Resource Graph inventory", "parent_resource_id": "",
            })
            inventory_by_id[row["resource_id"]] = row
        inventory = list(inventory_by_id.values())
        for name in ("arc_extensions", "effective_servers_plan"):
            statuses = [details[name] for _, details in inspections]
            errors = [
                {**detail["error"], "resource_id": row["resource_id"]}
                for row, details in inspections for detail in [details[name]] if "error" in detail
            ]
            sources.append(_source(
                name, "partial" if errors and len(errors) < len(arc_inventory) else "unavailable" if errors else "complete",
                reference, sum(s["records"] or 0 for s in statuses) if not errors else None,
                "Per-known-Arc-resource ARM read. Failed reads stay Unknown, never Missing or Free.",
                errors=errors, resources_checked=len(statuses), resources_available=len(statuses) - len(errors),
            ))
        try:
            integration = client.request(
                "GET", ARM_ORIGIN + "/subscriptions/" + subscription_id
                + "/providers/Microsoft.Security/settings/WDATP?api-version=2022-05-01", "mde_integration",
            )
            enabled = _get(_get(integration, "properties", {}), "enabled")
            if not isinstance(enabled, bool):
                raise EvidenceError("invalid_response", "WDATP setting omitted a boolean enabled value.", "mde_integration")
            sources.append(_source(
                "mde_integration", "complete", reference, 1,
                "Subscription WDATP integration setting only; not endpoint onboarding/health proof.", enabled=enabled,
            ))
        except EvidenceError as exc:
            sources.append(_source(
                "mde_integration", "unavailable", reference, note="Subscription integration setting is Unknown.",
                errors=[exc.as_dict()], enabled=None,
            ))
        findings = []
        subscription_recommendations = []
        for source in ("defender_recommendations", "defender_vulnerabilities"):
            try:
                records, pages = _query_arg(client, source, subscription_id)
                for record in records:
                    candidate = _assessment_resource_id(record, subscription_id)
                    if candidate and candidate not in inventory_by_id:
                        details = _get(_get(record, "properties", {}), "resourceDetails", {})
                        row = _resource_row({
                            "id": candidate, "name": _get(details, "ResourceName", candidate.rsplit("/", 1)[-1]),
                            "type": _get(details, "ResourceType", "Defender/indexedAsset"),
                        }, subscription_id, indexed_only=True)
                        row["parent_resource_id"] = _assessed_parent(
                            record, candidate, inventory_by_id, subscription_id
                        )
                        inventory_by_id[candidate] = row
                inventory = list(inventory_by_id.values())
                normalized, join_counts = _normalize_findings(
                    records, source, inventory, subscription_id, reference, arc_only=False
                )
                if source == "defender_recommendations":
                    subscription_recommendations = _subscription_recommendations(records, subscription_id, reference)
                findings.extend(normalized)
                sources.append(_source(
                    source, "complete", reference, len(records),
                    "Fixed subscription-scoped SecurityResources query; all pages read. "
                    "Exact in-subscription IDs, including explicitly indexed-only assets; empty results are not assurance.",
                    pages=pages, actionable_arc_findings=sum(_is_actionable(f) for f in normalized), **join_counts,
                ))
            except EvidenceError as exc:
                sources.append(_source(
                    source, "unavailable", reference, note="No trustworthy count is available for this finding source.",
                    errors=[exc.as_dict()], actionable_arc_findings=None,
                ))
        try:
            records, pages = _list_arm(
                client, ARM_ORIGIN + "/subscriptions/" + subscription_id
                + "/providers/Microsoft.Security/alerts?api-version=2022-01-01", "defender_alerts",
            )
            normalized, join_counts = _normalize_findings(
                records, "defender_alerts", inventory, subscription_id, reference, arc_only=False
            )
            findings.extend(normalized)
            sources.append(_source(
                "defender_alerts", "complete", reference, len(records),
                "Documented subscription ARM alerts API; all pages read, exact known resource-ID association. "
                "Empty returned alerts are not proof of zero risk.",
                pages=pages, actionable_arc_findings=sum(_is_actionable(f) for f in normalized), **join_counts,
            ))
        except EvidenceError as exc:
            sources.append(_source(
                "defender_alerts", "unavailable", reference,
                note="No trustworthy count is available for the ARM alerts source.",
                errors=[exc.as_dict()], actionable_arc_findings=None,
            ))
        context, context_sources = _collect_context(client, subscription_id, reference, inventory)
        context["subscription_recommendations"] = subscription_recommendations
        sources.extend(context_sources)
        for source in ("compute_extensions", "aks_security_profiles"):
            try:
                records, pages = _query_arg(client, source, subscription_id)
                for record in records:
                    props = _context_properties(record, source, subscription_id)
                    resource_id = _resource_id(_get(record, "id"), subscription_id)
                    if source == "compute_extensions":
                        parent = resource_id.rsplit("/extensions/", 1)[0]
                        if parent not in inventory_by_id:
                            continue
                        row = inventory_by_id[parent]
                        extension_type = _text(
                            _get(props, "type", _get(props, "virtualMachineExtensionType")), 120
                        )
                        state = _text(_get(props, "provisioningState"), 80) or "Unknown"
                        publisher = _text(_get(props, "publisher"), 160)
                        row["extensions"].append({"name": extension_type, "publisher": publisher, "state": state})
                        if extension_type.casefold() in ("mde.linux", "mde.windows") and (
                            publisher.casefold() == "microsoft.azure.azuredefenderforservers"
                        ):
                            row["mde_extension"] = state if state in ("Succeeded", "Failed") else "Unknown"
                            row["extension_evidence"] = "Compute ARG extension provisioning; not independent sensor health."
                    elif resource_id in inventory_by_id:
                        monitored = _get(_get(_get(
                            _get(props, "securityProfile", {}), "defender", {}
                        ), "securityMonitoring", {}), "enabled")
                        inventory_by_id[resource_id]["aks_defender_monitoring_enabled"] = (
                            monitored if isinstance(monitored, bool) else None
                        )
                sources.append(_source(
                    source, "complete", reference, len(records),
                    "Allowlisted installation/configuration fields only; not runtime sensor or workload health.", pages=pages,
                ))
            except EvidenceError as exc:
                sources.append(_source(
                    source, "unavailable", reference, note="Configuration source unavailable; do not infer readiness.",
                    errors=[exc.as_dict()],
                ))
        sources.append(_source(
            "mde_sensor_health", "unavailable", reference,
            note="Independent MDE sensor-health telemetry is not configured. Reader/ARM extensions cannot verify it.",
        ))
        return _finish_snapshot(
            inventory, findings, sources, "LIVE", reference,
            {
                "subscription_id": subscription_id, "tenant_id": config["TENANT_ID"],
                "description": "General Defender for Cloud in one fixed Enabled subscription; ARM and indexed-only assets labeled.",
                "hosting_location_verified_only_from_explicit_provider": True,
                "arm_resource_count": len(resources), "arc_machine_count": len(arc_inventory),
            },
            context=context,
        )
    finally:
        client.close()


def main(operation: str = "report", view: str = "inventory", provider: str = "all",
         environment: str = "all", resource_group: str = "", server_name: str = "",
         connectivity: str = "all", mde: str = "all", severity: str = "all",
         limit: int = 25, offset: int = 0, risk: str = "all", status: str = "all",
         association: str = "all", resource_type: str = "") -> dict:
    """Report general Defender for Cloud posture or query fixed-scope normalized evidence."""
    try:
        params = _validate_parameters(
            operation, view, provider, environment, resource_group, server_name,
            connectivity, mde, severity, limit, offset, risk, status, association, resource_type,
        )
        config = _validate_config()
        snapshot = _collect_live(config, _utc_now())
        return _write_report(snapshot) if params["operation"] == "report" else _query(snapshot, params)
    except EvidenceError as exc:
        return _failure(exc, "LIVE")
