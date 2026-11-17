# Test prompts

In a new chat, type `/agent`, select `fabric-chargeback-live` and send one prompt at a time. Before the tool is configured, every prompt returns a configuration message and makes no Azure call.

## 1. Full report

```text
Generate the Fabric FinOps report for the last 30 days.
```

Tool call:

```json
{"operation": "report", "period": "last_30d", "identities": "masked"}
```

**Expected:** One report call. The answer gives the total billed cost, the share consumed against switched on without use, hours on and utilization, the top actions with their value and evidence, the reservation verdict, the chargeback by workspace and the consumption by group, then the four links (report_url, snapshot_url, chargeback_csv_url, meters_csv_url) unchanged. People are masked.

## 2. Idle capacity

```text
How many hours was the capacity on without work, and what did it cost?
```

Tool call:

```json
{"operation": "summary", "period": "last_30d", "identities": "masked"}
```

**Expected:** A summary call (no files) with the idle hours and their cost, computed from the Activity Log on/off events and the billed meters.

## 3. Reservation

```text
Is a 1- or 3-year reservation worth it?
```

Tool call:

```json
{"operation": "summary", "period": "last_30d", "identities": "masked"}
```

**Expected:** The break-even point against the actual uptime, with retail prices; buy only if it pays off.

## 4. Groups and people

```text
Which resources does each user group consume, and which person consumes what?
```

Tool call:

```json
{"operation": "summary", "period": "last_30d", "identities": "masked"}
```

**Expected:** Consumption per group on the resources granted to it, with people masked; groups whose members could not be read are marked as permission pending.
