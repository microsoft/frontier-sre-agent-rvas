[< Previous Solution](./Solution-00.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Orient to the Database

## Purpose

* Teach metadata-first database orientation for technical and business audiences.
* Practice separating declared relationships from plausible inference.
* Expected time: 35-45 minutes.

## Mini-Lecture (8 min before challenge)

* Catalog views describe physical design but do not prove every business rule.
* Primary and foreign keys establish declared relationships and cardinality
  boundaries.
* Object names can suggest domain meaning, but names remain hypotheses until
  corroborated.
* `get_object` is efficient for one known object; bounded catalog queries are
  better for a database-wide map.
* Business and physical explanations should be related but not blended.

## Expected Student Output

* Six schema responsibilities are described.
* A Mermaid diagram includes declared customer, order, payment, inventory, and
  support relationships.
* The report includes engine, database, compatibility, and Query Store context.
* Inferred lifecycle meaning is clearly labeled.
* No sample business data is exposed unnecessarily.

## Common Issues and Hints

* **Symptom:** The diagram includes relationships based only on matching column names. **Fix:** require foreign-key catalog evidence for every solid relationship and label other links as inferred.
* **Symptom:** The answer lists tables but provides no business flow. **Fix:** ask for a second, stakeholder-focused section that traces an order through the domains.
* **Symptom:** `get_object` returns too much detail for every table. **Fix:** use bounded catalog queries for the map, then reserve `get_object` for the most important relations.
* **Symptom:** The agent claims a payment or fulfillment state transition that metadata cannot prove. **Fix:** ask it to move that statement into an "inferred meaning" section.

## Debrief Discussion Guide

* Which relationship was easiest to over-infer, and why?
* What operational question can the schema answer without reading business
  rows?
* How does schema orientation reduce time during later performance incidents?

## Success Criteria Notes

* Be strict that the Mermaid diagram uses declared constraints.
* Be flexible on the wording of schema responsibilities.
* Accept additional inferred relationships only when visibly labeled.

## Solution

Use this prompt:

```text
Using only sqlserver-mcp, orient me to the configured database.
First report engine, database, compatibility level, and Query Store state.
Then provide:
1. a business-language domain map,
2. a technical schema and relationship map,
3. a Mermaid ER diagram based only on declared primary and foreign keys,
4. a separate list of inferred business meaning.
Confirm that you made no database changes.
```

Compare completeness against the
[database model reference](../../Student/Resources/sql-server-mcp/docs/database-model.md).
Do not grade exact prose; grade evidence discipline and coverage.

