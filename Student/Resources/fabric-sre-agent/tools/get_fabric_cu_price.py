def main(region: str, currency: str = "EUR") -> dict:
    import requests
    from datetime import datetime, timezone
 
    URL = "https://prices.azure.com/api/retail/prices"
    arm_region = region.strip().lower().replace(" ", "")   # 'West Europe' -> 'westeurope'
 
    def fetch(odata_filter: str) -> list:
        items, next_url = [], URL
        params = {"currencyCode": currency, "$filter": odata_filter}
        while next_url:                                     # follow pagination
            r = requests.get(next_url, params=params, timeout=30)
            r.raise_for_status()
            body = r.json()
            items += body.get("Items", [])
            next_url, params = body.get("NextPageLink"), None   # NextPageLink already has the query
        return items
 
    # PAYG price per CU-hour
    payg_items = fetch(
        f"serviceName eq 'Microsoft Fabric' and armRegionName eq '{arm_region}' "
        f"and priceType eq 'Consumption'"
    )
    prices = [i["retailPrice"] for i in payg_items
              if i.get("meterName", "").endswith("Capacity Usage CU")
              and i.get("unitOfMeasure") == "1 Hour"]
    if not prices:
        return {"error": f"No PAYG Fabric CU price found for region '{arm_region}' in {currency}."}
    payg = max(set(prices), key=prices.count)              # most common CU price
 
    # 1-year reservation price per CU (per year)
    res_items = fetch(
        f"armSkuName eq 'Fabric_Capacity_CU_Hour' and armRegionName eq '{arm_region}' "
        f"and meterName eq 'Fabric Capacity CU'"
    )
    res_year = next((i["retailPrice"] for i in res_items
                     if i.get("reservationTerm") == "1 Year"), None)
 
    return {
        "region": arm_region,
        "currency": currency,
        "payg_per_cu_hour": payg,
        "reservation_1y_per_cu_year": res_year,
        "reservation_1y_per_cu_hour": (res_year / 8760) if res_year else None,
        "source": "Azure Retail Prices API",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
 