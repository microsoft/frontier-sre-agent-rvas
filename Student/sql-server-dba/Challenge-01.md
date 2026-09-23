[< Previous Challenge](./Challenge-00.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Orient to the Database

> **Capabilities added in this challenge**: Schema Discovery · Business Context · Relationship Mapping

## Introduction

Database incidents are difficult to explain when the investigator understands
tables but not the business flow they represent. Your DBA agent can now inspect
native metadata through MCP, but it must distinguish declared facts from
inferred meaning.

In this challenge, you turn the `stockOrders` catalog into both a technical
schema map and a concise explanation for an operations stakeholder.

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

Compare the result with the
[database model reference](../Resources/sql-server-mcp/docs/database-model.md)
only after the agent completes its independent discovery.

## Success Criteria

- [ ] The report identifies all six database schemas and their responsibilities
- [ ] The entity-relationship diagram uses declared primary and foreign keys rather than naming assumptions
- [ ] The business explanation follows an order through customer, payment, inventory, and support concepts
- [ ] The report separates confirmed metadata from inferred business meaning
- [ ] The agent uses only `sqlserver-mcp/*` tools and confirms that it made no changes
- [ ] **Explain to your coach** — why can a plausible relationship still be unsafe to present as a database fact?

## Learning Resources

* [SQL Server system catalog views](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/catalog-views-transact-sql)
* [View the dependencies of a stored procedure](https://learn.microsoft.com/sql/relational-databases/stored-procedures/view-the-dependencies-of-a-stored-procedure)
* [Primary and foreign key constraints](https://learn.microsoft.com/sql/relational-databases/tables/primary-and-foreign-key-constraints)

## Tips

* Ask for business and physical views as separate sections.
* Optional relationships and inferred lifecycle steps need explicit labels.
* Use `get_object` for detail on one known relation and bounded `run_query`
  calls for broader catalog evidence.

