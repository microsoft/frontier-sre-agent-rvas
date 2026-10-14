[< Previous Solution](./Solution-02.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Prove the Cost Calculation and Precision

## Purpose

- Test unit conversion and regional pricing with independently reproducible operands.
- Reinforce that CU-based retail estimates are not invoice allocation.
- Expected time: 30–40 minutes.

## Mini-Lecture (6 min before challenge)

- FUAM `TotalCUs` is CU-seconds, so divide by 3,600 for CU-hours.
- Capacity Events `capacityUnitMs` is CU-milliseconds; divide by 1,000, then by 3,600.
- The price tool is the only approved rate source; negotiated customer rates are not reflected.
- “Exact CU” can still yield only an estimated standalone-equivalent cost.

## Expected Student Output

- A reproducible calculation using the correct native source unit.
- A price model, region, source, retrieval time, and visible price rate.
- A precision label, explicit date interval, and caveat on standalone cost.

## Common Issues and Hints

- **Symptom:** Capacity Events estimate is 1,000 times too high. **Fix:** convert CU-milliseconds to CU-seconds before converting to CU-hours.
- **Symptom:** FUAM conversion is divided by 1,000. **Fix:** `TotalCUs` already uses CU-seconds; divide by 3,600.
- **Symptom:** The agent uses a price from a web page or memory. **Fix:** require the approved Azure Retail Prices API tool and the timestamped result.
- **Symptom:** The report calls the estimate “the bill.” **Fix:** distinguish measured CU multiplied by retail price from the invoice's billing mode and allocation rules.

## Debrief Discussion Guide

- Why does exact operation CU not mean exact customer invoice share?
- What happens when one period spans capacities or regions with different rates?
- Which assumptions need to be stated when estimating savings?

## Success Criteria Notes

- Be strict on unit conversion and independently checked arithmetic.
- Accept PAYG or one-year reservation if the requested/default model is explicit.
- Round only the displayed values; compute totals from unrounded values.

## Solution

Expected formula:

```text
FUAM:            CU-hours = TotalCUs / 3,600
Capacity Events: CU-hours = capacityUnitMs / 1,000 / 3,600
Cost:            CU-hours × regional €/CU-hour
```

Every cost answer should end with its calculation block and state that it is
standalone-equivalent at retail list price.
