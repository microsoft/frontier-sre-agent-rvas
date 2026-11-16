---
title: Orient to the Database
summary: Turn catalog metadata into a business map while keeping declared relationships separate from inferred domain meaning.
phase: Discover
group: Investigations
tags:
- schema
- relationships
highlight: false
---

# Challenge 01 — Orient to the Database

> **Capabilities added in this challenge**: Schema Discovery · Business Context · Relationship Mapping

## Purpose

* Produce an entity-relationship diagram from catalog metadata in which every link cites a declared constraint.
* Label each relationship you infer from names or structure as an inference, not a fact.
* Expected time: 35-45 minutes.

## Introduction

Use the DBA agent to map the `stockOrders` schema and explain its business flow
to an operations stakeholder. Keep relationships declared in metadata apart from
business meaning inferred from names or structure.

## Description

Use the SQL Server DBA custom agent to:

* Identify the database engine, version, compatibility level, and Query Store
  state before interpreting metadata
* Describe the catalog, sales, inventory, support, reference, and lab domains
* Map primary keys, foreign keys, optional relationships, and important indexes
* Produce a Mermaid entity-relationship diagram based only on declared
  constraints
* Explain the customer-to-order-to-inventory-to-support flow in plain language
* Label business meaning that cannot be proven from database metadata

Open the
[database model reference](../resources/sql-server-mcp/docs/database-model.md)
only after the agent finishes its own discovery.

### Solution steps

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

Compare coverage against the
[database model reference](../resources/sql-server-mcp/docs/database-model.md).
Judge evidence discipline and coverage, not exact wording.

## Success Criteria

- [ ] The report identifies all six database schemas and their responsibilities
- [ ] The entity-relationship diagram uses declared primary and foreign keys rather than naming assumptions
- [ ] The business explanation follows an order through customer, payment, inventory, and support concepts
- [ ] The report separates confirmed metadata from inferred business meaning
- [ ] The agent uses only `sqlserver-mcp/*` tools and confirms that it made no changes
- [ ] **Explain in your own words** (two or three written sentences) — why can a plausible relationship still be unsafe to present as a database fact?

## Learning Resources

* [SQL Server system catalog views](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/catalog-views-transact-sql)
* [View the dependencies of a stored procedure](https://learn.microsoft.com/sql/relational-databases/stored-procedures/view-the-dependencies-of-a-stored-procedure)
* [Primary and foreign key constraints](https://learn.microsoft.com/sql/relational-databases/tables/primary-and-foreign-key-constraints)

## Tips

* Ask for business and physical views as separate sections.
* Optional relationships and inferred lifecycle steps need explicit labels.
* Use `get_object` for detail on one known relation and bounded `run_query`
  calls for broader catalog evidence.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Catalog views describe physical design but do not prove every business rule.
* Primary and foreign keys establish declared relationships and cardinality
  boundaries.
* Object names can suggest domain meaning, but names remain hypotheses until
  corroborated.
* `get_object` is efficient for one known object; bounded catalog queries are
  better for a database-wide map.
* Business and physical explanations should be related but not blended.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* Six schema responsibilities are described.
* A Mermaid diagram includes declared customer, order, payment, inventory, and
  support relationships.
* The report includes engine, database, compatibility, and Query Store context.
* Inferred lifecycle meaning is clearly labeled.
* No sample business data is exposed unnecessarily.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** The diagram includes relationships based only on matching column names. **Fix:** require foreign-key catalog evidence for every solid relationship and label other links as inferred.
* **Symptom:** The answer lists tables but provides no business flow. **Fix:** ask for a second, stakeholder-focused section that traces an order through the domains.
* **Symptom:** `get_object` returns too much detail for every table. **Fix:** use bounded catalog queries for the map, then reserve `get_object` for the most important relations.
* **Symptom:** The agent claims a payment or fulfillment state transition that metadata cannot prove. **Fix:** ask it to move that statement into an "inferred meaning" section.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which relationship was easiest to over-infer, and why?
* What operational question can the schema answer without reading business
  rows?
* How does schema orientation reduce time during later performance incidents?

</details>
