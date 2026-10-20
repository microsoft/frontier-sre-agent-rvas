[< Previous Challenge](./Challenge-02.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-04.md)

# Challenge 03 — Prove the Cost Calculation and Precision

> **Capabilities added in this challenge**: FinOps · Retail Pricing · Evidence Labels

## Introduction

A cost answer is useful only when its units, price source, and precision are
visible. Fabric consumption is recorded in CU-seconds or CU-milliseconds while
retail prices are expressed per CU-hour, so a reliable answer must show the
conversion and its assumptions.

## Description

Use a known period and workload to validate the agent's end-to-end estimate:

- Retrieve the capacity's region and a current PAYG or one-year reservation
  rate from the Azure Retail Prices API tool.
- Independently recompute the conversion from the selected backend's native CU
  unit to CU-hours and estimated euros.
- Check that the answer includes explicit dates, source freshness, pricing
  model, region, retrieval time, and the operands in its calculation.
- Assign the precision label warranted by the source: exact, average per run,
  derived, or upper bound.
- Distinguish standalone-equivalent consumption cost from an invoice
  allocation; identify exclusions such as storage and negotiated discounts.

## Success Criteria

- [ ] A representative estimate is independently recomputed from native CU values and the retrieved regional rate.
- [ ] The agent converts CU-seconds or CU-milliseconds correctly to CU-hours before applying the rate.
- [ ] The answer labels precision and includes the time period, data freshness, pricing model, rate source, and calculation.
- [ ] The result is described as standalone-equivalent list-price cost, not an actual capacity invoice allocation.
- [ ] **Explain to your coach** — what uncertainty remains even when the CU measurement and arithmetic are exact?

## Learning Resources

- [Cost calculation and answer rules](../Resources/fabric-sre-agent/README.md#what-every-cost-answer-contains)
- [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Capacity operation events schema](https://learn.microsoft.com/fabric/real-time-hub/explore-fabric-capacity-operation-events#operation-events-schema)
- [Fabric operations](https://learn.microsoft.com/fabric/enterprise/fabric-operations)

## Tips

- FUAM `TotalCUs` is measured in CU-seconds; Capacity Events `capacityUnitMs` is measured in CU-milliseconds.
- Preserve full precision during computation and round only for display.
