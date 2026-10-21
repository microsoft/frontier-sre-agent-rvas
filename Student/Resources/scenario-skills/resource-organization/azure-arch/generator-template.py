from pathlib import Path
import json
import re
import os
import sys
import pandas as pd
for _parent in Path(__file__).resolve().parents:
    _tools = _parent / "shared" / "tools"
    if (_tools / "azure_http.py").is_file():
        sys.path.insert(0, str(_tools))
        break
import azure_http as requests

# Copy this template into the active thread workspace before running it.
THREAD_DIR = Path(os.environ.get("SRE_ARCH_OUTPUT", "azure-landing-zone"))
XLSX_PATH = Path(os.environ.get("SRE_ARCH_INVENTORY", "inventory.xlsx"))
REGION = os.environ.get("SRE_ARCH_REGION", "westeurope")
HOURS_PER_MONTH = float(os.environ.get("SRE_ARCH_HOURS", "730"))
SUBSCRIPTION_LAYOUT = os.environ.get("SRE_ARCH_ENVIRONMENTS", "prod,dev,test,acceptance").split(",")
USE_V2_DATA_DISKS = os.environ.get("SRE_ARCH_PREMIUM_V2_DATA", "").lower() == "true"

VM_SKU_PATTERN = re.compile(r"^Standard_([DE])(\d+)([a-z]*)_v(\d+)$", re.IGNORECASE)

price_cache = {}
vm_sku_cache = {}


def paged_items(filter_expr: str):
    url = "https://prices.azure.com/api/retail/prices"
    params = {"$filter": filter_expr}
    items = []
    headers = {"User-Agent": "Azure-SRE-Agent/1.0"}
    while True:
        resp = requests.get(url, params=params, timeout=90, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        items.extend(payload.get("Items", []))
        next_link = payload.get("NextPageLink")
        if not next_link:
            break
        url = next_link
        params = None
    return items


def ensure_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def parse_vm_sku_spec(sku_name):
    match = VM_SKU_PATTERN.match(str(sku_name or ""))
    if not match:
        return None
    family = match.group(1).upper()
    cpu = int(match.group(2))
    suffix = match.group(3).lower()
    version = int(match.group(4))
    if "s" not in suffix:
        return None
    ram_multiplier = 8 if family == "E" else 4
    return {
        "sku": str(sku_name),
        "family": family,
        "cpu": cpu,
        "ram_gb": cpu * ram_multiplier,
        "version": version,
        "suffix": suffix,
    }


def available_vm_catalog():
    if REGION in vm_sku_cache:
        return vm_sku_cache[REGION]
    try:
        items = paged_items(f"armRegionName eq '{REGION}' and serviceName eq 'Virtual Machines'")
        catalog = {}
        for item in items:
            meter_name = str(item.get("meterName", "")).lower()
            sku_name = str(item.get("skuName", "")).lower()
            product_name = str(item.get("productName", "")).lower()
            unit = str(item.get("unitOfMeasure", "")).lower()
            if str(item.get("type", "")).lower() != "consumption":
                continue
            if "hour" not in unit:
                continue
            if "spot" in meter_name or "low priority" in meter_name or "spot" in sku_name or "low priority" in sku_name:
                continue
            if "windows" in product_name:
                continue
            spec = parse_vm_sku_spec(item.get("armSkuName"))
            if not spec:
                continue
            catalog[spec["sku"]] = spec
        if catalog:
            vm_sku_cache[REGION] = list(catalog.values())
            return vm_sku_cache[REGION]
    except Exception as error:
        raise RuntimeError(f"Retail VM catalog unavailable for {REGION}; no fallback sizing or deployability assertion.") from error
    raise RuntimeError(f"No usable retail VM catalog for {REGION}; sizing is not assessed.")


def best_price(
    service_name,
    arm_sku=None,
    meter_name_contains=None,
    meter_name_excludes=None,
    product_name_contains=None,
    product_name_excludes=None,
    sku_name_contains=None,
    sku_name_excludes=None,
    require_unit_contains=None,
    pricing_type="Consumption",
    prefer_nonzero=True,
):
    key = (
        service_name,
        arm_sku,
        tuple(ensure_list(meter_name_contains)),
        tuple(ensure_list(meter_name_excludes)),
        tuple(ensure_list(product_name_contains)),
        tuple(ensure_list(product_name_excludes)),
        tuple(ensure_list(sku_name_contains)),
        tuple(ensure_list(sku_name_excludes)),
        require_unit_contains,
        pricing_type,
        prefer_nonzero,
    )
    if key in price_cache:
        return price_cache[key]

    filters = [f"armRegionName eq '{REGION}'", f"serviceName eq '{service_name}'"]
    if arm_sku:
        filters.append(f"armSkuName eq '{arm_sku}'")
    items = paged_items(" and ".join(filters))

    meter_terms = [term.lower() for term in ensure_list(meter_name_contains)]
    meter_excludes = [term.lower() for term in ensure_list(meter_name_excludes)]
    product_terms = [term.lower() for term in ensure_list(product_name_contains)]
    product_excludes = [term.lower() for term in ensure_list(product_name_excludes)]
    sku_terms = [term.lower() for term in ensure_list(sku_name_contains)]
    sku_excludes = [term.lower() for term in ensure_list(sku_name_excludes)]
    unit_term = str(require_unit_contains or "").lower()
    normalized_pricing_type = str(pricing_type or "").lower()

    candidates = []
    for item in items:
        meter_name = str(item.get("meterName", "")).lower()
        product_name = str(item.get("productName", "")).lower()
        sku_name = str(item.get("skuName", "")).lower()
        unit = str(item.get("unitOfMeasure", "")).lower()
        item_type = str(item.get("type", "")).lower()
        if product_terms and not all(term in product_name for term in product_terms):
            continue
        if product_excludes and any(term in product_name for term in product_excludes):
            continue
        if sku_terms and not all(term in sku_name for term in sku_terms):
            continue
        if sku_excludes and any(term in sku_name for term in sku_excludes):
            continue
        if meter_terms and not all(term in meter_name for term in meter_terms):
            continue
        if meter_excludes and any(term in meter_name for term in meter_excludes):
            continue
        if unit_term and unit_term not in unit:
            continue
        if normalized_pricing_type and item_type != normalized_pricing_type:
            continue
        if item.get("unitPrice") is None:
            continue
        if prefer_nonzero and float(item.get("unitPrice", 0) or 0) <= 0:
            continue
        candidates.append(item)

    if not candidates:
        raise RuntimeError(f"No price found for {key}")

    candidates.sort(key=lambda i: (float(i.get("unitPrice", 0)), i.get("meterName", ""), i.get("productName", "")))
    price_cache[key] = candidates[0]
    return candidates[0]


def vm_price_item(arm_sku, os_type, include_ahb=False):
    windows_pricing = os_type == "windows" and not include_ahb
    return best_price(
        "Virtual Machines",
        arm_sku=arm_sku,
        product_name_contains="Windows" if windows_pricing else None,
        product_name_excludes=None if windows_pricing else "Windows",
        sku_name_excludes=["Spot", "Low Priority"],
        meter_name_excludes=["Spot", "Low Priority"],
        require_unit_contains="hour",
    )


def monthly(price_item, units=1.0, hours=HOURS_PER_MONTH):
    unit = str(price_item.get("unitOfMeasure", "")).lower()
    price = float(price_item["unitPrice"])
    if "hour" in unit:
        return price * units * hours
    return price * units


def normalize_os(value):
    text = str(value or "").lower()
    if "linux" in text or "centos" in text:
        return "linux"
    return "windows"


def choose_family(row):
    server_type = str(row["Server Type"]).lower()
    cpu = max(int(row["CPU"]), 1)
    ram = int(row["RAM"])
    if "database" in server_type:
        return "E"
    if ram / cpu >= 6:
        return "E"
    return "D"


def choose_sku(row):
    family = row["vm_family"]
    cpu_needed = int(row["CPU"])
    ram_needed = int(row["RAM"])
    catalog = available_vm_catalog()
    candidates = [s for s in catalog if s["family"] == family and s["cpu"] >= cpu_needed and s["ram_gb"] >= ram_needed]
    if not candidates:
        candidates = [s for s in catalog if s["cpu"] >= cpu_needed and s["ram_gb"] >= ram_needed]
    if not candidates:
        raise ValueError(f"No catalog VM meets CPU={cpu_needed}, RAM={ram_needed}; manual sizing required.")
    candidates.sort(key=lambda s: (-int(s.get("version", 0)), s["cpu"], s["ram_gb"], s.get("suffix", "")))
    return candidates[0]


def disk_profile(row):
    server_type = str(row["Server Type"]).lower()
    app = str(row["Application Name"]).lower()
    ram = int(row["RAM"])
    os_disk_capacity_gib = 128 if ram <= 16 else 256
    os_disk_fallback_sku = "P10 LRS Disk" if ram <= 16 else "P20 LRS Disk"
    data_disk_count = 0
    data_disk_capacity_gib = 0
    data_disk_fallback_sku = ""
    if "database" in server_type:
        if "hana" in app or "sap" in app:
            os_disk_capacity_gib = 512
            os_disk_fallback_sku = "P30 LRS Disk"
            data_disk_count = 4
            data_disk_capacity_gib = 512
            data_disk_fallback_sku = "P30 LRS Disk"
        elif ram >= 64:
            os_disk_capacity_gib = 256
            os_disk_fallback_sku = "P20 LRS Disk"
            data_disk_count = 2
            data_disk_capacity_gib = 512
            data_disk_fallback_sku = "P30 LRS Disk"
        else:
            os_disk_capacity_gib = 256
            os_disk_fallback_sku = "P20 LRS Disk"
            data_disk_count = 1
            data_disk_capacity_gib = 256
            data_disk_fallback_sku = "P20 LRS Disk"
    elif "application server" in server_type and ram >= 32:
        data_disk_count = 1
        data_disk_capacity_gib = 128
        data_disk_fallback_sku = "P10 LRS Disk"
    return pd.Series([
        os_disk_capacity_gib,
        os_disk_fallback_sku,
        data_disk_count,
        data_disk_capacity_gib,
        data_disk_fallback_sku,
    ])


def premium_ssd_v2_price_item():
    return best_price(
        "Storage",
        product_name_contains="Premium SSD v2",
        meter_name_contains="Provisioned Capacity",
        require_unit_contains="month",
        pricing_type="Consumption",
    )


def disk_monthly(capacity_gib, fallback_price_item, premium_v2_price_item=None, disk_count=1, disk_role="os"):
    if capacity_gib <= 0 or disk_count <= 0:
        return 0.0, "none"
    if disk_role not in ("os", "data"):
        raise ValueError("disk_role must be os or data.")
    if premium_v2_price_item is not None and disk_role == "data":
        return monthly(premium_v2_price_item, units=float(capacity_gib) * float(disk_count)), "Premium SSD v2"
    return monthly(fallback_price_item, units=float(disk_count)), "Premium SSD Managed Disks"


def build_reliability_recommendations(df):
    critical_servers = int((df["Server Type"].astype(str).str.contains("database|production|sap", case=False, regex=True)).sum())
    recommendations = [
        {
            "Category": "Well-Architected alignment",
            "Recommendation": "Use zone-aware landing-zone patterns and avoid single points of failure in shared services where the region supports it.",
            "Why": "Improves workload resilience and aligns the architecture to the reliability pillar.",
        },
        {
            "Category": "Workload reliability",
            "Recommendation": f"Review the {critical_servers} critical or stateful servers for zone redundancy, clustering, or paired-instance design instead of single-VM placement.",
            "Why": "Critical application and data tiers usually need higher availability than a single VM can provide.",
        },
        {
            "Category": "Backup and recovery",
            "Recommendation": "Enable backup policies, restore validation, and documented recovery tests for business-critical workloads.",
            "Why": "Backups only improve reliability if restore paths are tested regularly.",
        },
        {
            "Category": "Monitoring and alerting",
            "Recommendation": "Enable Service Health alerts, Activity Log alerts, action groups, and workload alerts for the target subscription.",
            "Why": "Subscription-level alerts reduce detection time for platform incidents and control-plane changes.",
        },
        {
            "Category": "Security readiness",
            "Recommendation": "Enable Microsoft Defender for Cloud on the target subscription and review plan coverage before cutover.",
            "Why": "Defender for Cloud improves secure posture visibility and should be part of landing-zone readiness.",
        },
    ]
    return pd.DataFrame(recommendations)


def main():
    THREAD_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(XLSX_PATH)
    df.columns = [c.strip() for c in df.columns]
    work = df.copy()
    work["os_type"] = work["Operating System"].map(normalize_os)
    work["vm_family"] = work.apply(choose_family, axis=1)
    work["recommended"] = work.apply(choose_sku, axis=1)
    work["recommended_sku"] = work["recommended"].map(lambda x: x["sku"])
    work["recommended_cpu"] = work["recommended"].map(lambda x: x["cpu"])
    work["recommended_ram_gb"] = work["recommended"].map(lambda x: x["ram_gb"])
    work["recommended_version"] = work["recommended"].map(lambda x: x.get("version"))
    work[["os_disk_capacity_gib", "os_disk_fallback_sku", "data_disk_count", "data_disk_capacity_gib", "data_disk_fallback_sku"]] = work.apply(disk_profile, axis=1)

    shared_price_items = {
        "bastion_basic": best_price("Azure Bastion", sku_name_contains="Basic", meter_name_contains="Gateway", meter_name_excludes="Additional", require_unit_contains="hour"),
        "azure_firewall": best_price("Azure Firewall", sku_name_contains="Standard", meter_name_contains="Deployment", require_unit_contains="hour"),
        "vpn_gateway": best_price("VPN Gateway", sku_name_contains="VpnGw2", meter_name_contains="VpnGw2", require_unit_contains="hour"),
        "app_gateway_waf": best_price("Application Gateway", product_name_contains="Application Gateway WAF v2", meter_name_contains="Fixed Cost", require_unit_contains="hour"),
        "log_analytics_ingestion": best_price("Log Analytics", sku_name_contains="Analytics Logs", meter_name_contains="Data Ingestion"),
        "backup_protected_instance": best_price("Backup", sku_name_contains="Azure VM", meter_name_contains="Protected Instance", require_unit_contains="month"),
        "disk_p10": best_price("Storage", meter_name_contains="P10 LRS Disk", meter_name_excludes="Mount", product_name_contains="Premium SSD Managed Disks"),
        "disk_p20": best_price("Storage", meter_name_contains="P20 LRS Disk", meter_name_excludes="Mount", product_name_contains="Premium SSD Managed Disks"),
        "disk_p30": best_price("Storage", meter_name_contains="P30 LRS Disk", meter_name_excludes="Mount", product_name_contains="Premium SSD Managed Disks"),
    }

    premium_v2_item = None
    if USE_V2_DATA_DISKS:
        premium_v2_item = premium_ssd_v2_price_item()

    price_trace_rows = []
    vm_rows = []
    for _, row in work.iterrows():
        vm_item = vm_price_item(row["recommended_sku"], row["os_type"], include_ahb=False)
        vm_item_ahb = vm_price_item(row["recommended_sku"], row["os_type"], include_ahb=True)
        os_disk_fallback_item = shared_price_items["disk_p10"] if row["os_disk_fallback_sku"] == "P10 LRS Disk" else shared_price_items["disk_p20"] if row["os_disk_fallback_sku"] == "P20 LRS Disk" else shared_price_items["disk_p30"]
        os_disk_monthly, os_disk_model = disk_monthly(row["os_disk_capacity_gib"], os_disk_fallback_item, premium_v2_price_item=premium_v2_item, disk_count=1)
        data_disk_monthly = 0.0
        data_disk_model = "none"
        if int(row["data_disk_count"]) > 0:
            data_disk_fallback_item = shared_price_items["disk_p10"] if row["data_disk_fallback_sku"] == "P10 LRS Disk" else shared_price_items["disk_p20"] if row["data_disk_fallback_sku"] == "P20 LRS Disk" else shared_price_items["disk_p30"]
            data_disk_monthly, data_disk_model = disk_monthly(
                row["data_disk_capacity_gib"],
                data_disk_fallback_item,
                premium_v2_price_item=premium_v2_item,
                disk_role="data",
                disk_count=int(row["data_disk_count"]),
            )
        vm_monthly = monthly(vm_item)
        vm_monthly_ahb = monthly(vm_item_ahb)
        total_monthly = vm_monthly + os_disk_monthly + data_disk_monthly
        total_monthly_ahb = vm_monthly_ahb + os_disk_monthly + data_disk_monthly
        vm_rows.append({
            "Application Name": row["Application Name"],
            "Server Type": row["Server Type"],
            "OS Type": row["os_type"],
            "Recommended Azure VM SKU": row["recommended_sku"],
            "Selected SKU Version": row["recommended_version"],
            "VM Monthly USD": round(vm_monthly, 2),
            "VM Monthly USD with AHB": round(vm_monthly_ahb, 2),
            "OS Disk Model": os_disk_model,
            "OS Disk Monthly USD": round(os_disk_monthly, 2),
            "Data Disk Model": data_disk_model,
            "Data Disks Monthly USD": round(data_disk_monthly, 2),
            "Estimated Monthly USD": round(total_monthly, 2),
            "Estimated Monthly USD with AHB": round(total_monthly_ahb, 2),
            "AHB Savings USD": round(total_monthly - total_monthly_ahb, 2),
        })
        price_trace_rows.extend([
            {
                "Resource": row["Application Name"],
                "Category": "VM PAYG",
                "Meter": vm_item.get("meterName"),
                "Product": vm_item.get("productName"),
                "ArmSku": vm_item.get("armSkuName"),
                "UnitPrice": vm_item.get("unitPrice"),
                "UnitOfMeasure": vm_item.get("unitOfMeasure"),
            },
            {
                "Resource": row["Application Name"],
                "Category": "VM AHB",
                "Meter": vm_item_ahb.get("meterName"),
                "Product": vm_item_ahb.get("productName"),
                "ArmSku": vm_item_ahb.get("armSkuName"),
                "UnitPrice": vm_item_ahb.get("unitPrice"),
                "UnitOfMeasure": vm_item_ahb.get("unitOfMeasure"),
            },
        ])

    vm_cost_df = pd.DataFrame(vm_rows)
    shared = pd.DataFrame([
        {"Component": "Azure Bastion Basic", "Estimated Monthly USD": round(monthly(shared_price_items["bastion_basic"]), 2), "Estimated Monthly USD with AHB": round(monthly(shared_price_items["bastion_basic"]), 2)},
        {"Component": "Azure Firewall Standard", "Estimated Monthly USD": round(monthly(shared_price_items["azure_firewall"]), 2), "Estimated Monthly USD with AHB": round(monthly(shared_price_items["azure_firewall"]), 2)},
        {"Component": "VPN Gateway VpnGw2", "Estimated Monthly USD": round(monthly(shared_price_items["vpn_gateway"]), 2), "Estimated Monthly USD with AHB": round(monthly(shared_price_items["vpn_gateway"]), 2)},
        {"Component": "Application Gateway WAF v2", "Estimated Monthly USD": round(monthly(shared_price_items["app_gateway_waf"]), 2), "Estimated Monthly USD with AHB": round(monthly(shared_price_items["app_gateway_waf"]), 2)},
    ])
    shared["AHB Savings USD"] = 0.0
    for name, item in shared_price_items.items():
        price_trace_rows.append({
            "Resource": name,
            "Category": "Shared service",
            "Meter": item.get("meterName"),
            "Product": item.get("productName"),
            "ArmSku": item.get("armSkuName"),
            "UnitPrice": item.get("unitPrice"),
            "UnitOfMeasure": item.get("unitOfMeasure"),
        })
    if premium_v2_item is not None:
        price_trace_rows.append({
            "Resource": "Premium SSD v2",
            "Category": "Storage preference",
            "Meter": premium_v2_item.get("meterName"),
            "Product": premium_v2_item.get("productName"),
            "ArmSku": premium_v2_item.get("armSkuName"),
            "UnitPrice": premium_v2_item.get("unitPrice"),
            "UnitOfMeasure": premium_v2_item.get("unitOfMeasure"),
        })

    summary = pd.DataFrame([
        {"Category": "VM estate", "Estimated Monthly USD": round(vm_cost_df["Estimated Monthly USD"].sum(), 2), "Estimated Monthly USD with AHB": round(vm_cost_df["Estimated Monthly USD with AHB"].sum(), 2)},
        {"Category": "Shared landing services", "Estimated Monthly USD": round(shared["Estimated Monthly USD"].sum(), 2), "Estimated Monthly USD with AHB": round(shared["Estimated Monthly USD with AHB"].sum(), 2)},
    ])
    summary["AHB Savings USD"] = (summary["Estimated Monthly USD"] - summary["Estimated Monthly USD with AHB"]).round(2)
    baseline_total = round(summary["Estimated Monthly USD"].sum(), 2)
    ahb_total = round(summary["Estimated Monthly USD with AHB"].sum(), 2)
    summary.loc[len(summary)] = {
        "Category": "Total estimated monthly (USD)",
        "Estimated Monthly USD": baseline_total,
        "Estimated Monthly USD with AHB": ahb_total,
        "AHB Savings USD": round(baseline_total - ahb_total, 2),
    }

    reliability_df = build_reliability_recommendations(work)
    assumptions = pd.DataFrame([
        {"Area": "Region", "Assumption": f"{REGION} retail list pricing; {HOURS_PER_MONTH} compute hours per month."},
        {"Area": "Environment layout", "Assumption": f"Proposed environments: {', '.join(SUBSCRIPTION_LAYOUT)}. This does not multiply the modeled inventory or shared services."},
        {"Area": "Pricing source", "Assumption": "Azure Retail Prices API, consumption/list prices."},
        {"Area": "VM selection", "Assumption": "Retail catalog candidates prefer newer versions meeting estimated CPU and RAM. Retail meters do not prove regional or subscription deployability, quota, capacity, certifications or actual VM capabilities."},
        {"Area": "Storage", "Assumption": "OS disks always use Premium SSD managed disks, never Premium SSD v2. Data disks use v2 only with SRE_ARCH_PREMIUM_V2_DATA=true after region, zone and VM compatibility review. V2 costs model capacity only, excluding additional provisioned IOPS and throughput."},
        {"Area": "Sizing", "Assumption": "Disk counts and capacities and D/E RAM multipliers are planning heuristics, not measured workload requirements. Validate actual disk capacity, latency, IOPS and throughput before approval."},
        {"Area": "Exclusions", "Assumption": "Not a full bill: excludes backup storage and instance costs, logs ingestion and retention, bandwidth, transactions, variable gateway capacity, support, taxes, reservations and negotiated discounts."},
        {"Area": "Licensing", "Assumption": "AHB scenario assumes all eligible Windows Server VMs use Azure Hybrid Benefit and therefore pay the base compute rate."},
        {"Area": "Framework", "Assumption": "Architecture guidance is aligned to Azure Well-Architected Framework pillars with emphasis on reliability and security readiness."},
        {"Area": "Subscription readiness", "Assumption": "Enable Microsoft Defender for Cloud, Service Health alerts, and Activity Log alerts for each target subscription before migration."},
        {"Area": "Diagram generation", "Assumption": "Create the landing-zone diagram separately with the draw.io MCP server using the modeled target Azure architecture from this workbook output."},
    ])
    price_trace_df = pd.DataFrame(price_trace_rows)

    cost_xlsx = THREAD_DIR / f"azure-{REGION}-cost-estimate.xlsx"
    cost_csv = THREAD_DIR / f"azure-{REGION}-cost-summary.csv"
    with pd.ExcelWriter(cost_xlsx, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        shared.to_excel(writer, sheet_name="SharedServices", index=False)
        vm_cost_df.to_excel(writer, sheet_name="VMEstimate", index=False)
        assumptions.to_excel(writer, sheet_name="Assumptions", index=False)
        price_trace_df.to_excel(writer, sheet_name="PriceTrace", index=False)
        reliability_df.to_excel(writer, sheet_name="Recommendations", index=False)
    summary.to_csv(cost_csv, index=False)

    metadata = {
        "assessment_status": "Partial",
        "sources": [
            {"title": "Retail Prices API", "url": "https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices"},
            {"title": "Managed disk types", "url": "https://learn.microsoft.com/en-us/azure/virtual-machines/disks-types"},
        ],
        "serverCount": int(len(df)),
        "monthlyTotalUsd": baseline_total,
        "monthlyTotalUsdWithAhb": ahb_total,
        "ahbSavingsUsd": round(baseline_total - ahb_total, 2),
        "notes": assumptions["Assumption"].tolist(),
        "reliabilityRecommendations": reliability_df["Recommendation"].tolist(),
        "subscriptionLayout": SUBSCRIPTION_LAYOUT,
        "subscriptionReminders": [
            "Enable Microsoft Defender for Cloud on each target subscription.",
            "Enable Service Health alerts and Activity Log alerts with action groups for each target subscription.",
        ],
        "wellArchitectedAlignment": [
            "Security",
            "Reliability",
            "Operational Excellence",
            "Performance Efficiency",
            "Cost Optimization",
        ],
        "diagramGeneration": {
            "owner": "drawio-mcp",
            "expectedArtifact": f"azure-{REGION}-landing-zone.drawio",
            "instruction": "Create the draw.io artifact separately from the modeled target Azure architecture. Do not infer currently deployed Azure resources.",
        },
    }
    metadata_path = THREAD_DIR / f"azure-{REGION}-estimate-metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(cost_xlsx)
    print(cost_csv)
    print(metadata_path)


if __name__ == "__main__":
    main()
