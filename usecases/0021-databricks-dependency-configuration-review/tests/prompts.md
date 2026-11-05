# Test prompts

Adapted from the upstream `subagent-instructions-and-prompts.md`. Replace `<APPROVED_DATABRICKS_WORKSPACE_NAME>` with an approved workspace. Before the tool is configured, report and query prompts return `configuration_required`.

## Copy-ready chat prompts (Spanish & English)

Use the actual approved workspace name privately once configured. Before the
colleague session is completed, running any report/query prompt will honestly
return `configuration_required` without making network calls.

### 1. List configured workspaces (no authentication or network calls)

```json
{"operation":"list_workspaces"}
```

### 2. Full dependency & configuration report (Spanish)

```text
@databricks-dependency-live Genera la revisión completa de dependencias y
configuración de Azure Databricks para <APPROVED_DATABRICKS_WORKSPACE_NAME> con
operation=report. Profundiza en el mapa de dependencias (OBSERVED, INFERRED y
UNKNOWN) entre el workspace ARM, VNet/NSG/Private Link, Access Connector,
clústeres, pools, políticas, jobs y DAG de tareas, pipelines Lakeflow/DLT, SQL
Warehouses, Unity Catalog (metastore, catálogos, esquemas, storage credentials,
external locations, conexiones) y Key Vault / Storage asociados. Cubre buenas
prácticas, seguridad, FinOps y optimización con los cinco pilares WAF. Entrega
inmediatamente los cuatro archivos (HTML, JSON completo, CSV de hallazgos y CSV
de dependencias). No inicies clústeres ni SQL Warehouses ni cambies nada.
```

```json
{"operation":"report","workspace_name":"<APPROVED_DATABRICKS_WORKSPACE_NAME>"}
```

### 3. Full dependency & configuration report (English)

```text
@databricks-dependency-live Run the complete Azure Databricks dependency map
and configuration review for <APPROVED_DATABRICKS_WORKSPACE_NAME> using
operation=report. Cover the deep dependency graph (OBSERVED native joins,
explicit INFERRED URI targets and UNKNOWN runtime lineage blind spots), best
practices, security, FinOps and optimization across the five WAF pillars.
Deliver all four generated files (HTML, full snapshot JSON, findings CSV and
dependencies CSV) and disclose source coverage and limitations. Do not start
compute or modify any resource.
```

```json
{"operation":"report","workspace_name":"<APPROVED_DATABRICKS_WORKSPACE_NAME>"}
```

### 4. Multi-workspace report

```json
{"operation":"report","workspace_names":"<APPROVED_DATABRICKS_WORKSPACE_NAME>,<APPROVED_SECOND_WORKSPACE_NAME>"}
```

### 5. Grounded questions on the dependency map (`view="dependencies"`)

```text
@databricks-dependency-live Usa query con view=dependencies y
classification=OBSERVED para <APPROVED_DATABRICKS_WORKSPACE_NAME>. ¿Qué
relaciones exactas están confirmadas entre tareas de Jobs, clústeres, SQL
Warehouses, pipelines declarativos, Storage Credentials, External Locations y
recursos ARM asociados? Indica los campos de join y las fuentes de cada arista.
```

```json
{"operation":"query","view":"dependencies","workspace_name":"<APPROVED_DATABRICKS_WORKSPACE_NAME>","classification":"OBSERVED","limit":25}
```

```text
@databricks-dependency-live Usa query con view=dependencies y
classification=INFERRED. ¿Qué cuentas de almacenamiento ADLS Gen2 o Key Vaults
están referenciados por URI/hostname en Unity Catalog o en el workspace pero no
tienen lectura directa en el inventario ARM?
```

```json
{"operation":"query","view":"dependencies","workspace_name":"<APPROVED_DATABRICKS_WORKSPACE_NAME>","classification":"INFERRED","limit":25}
```

```text
@databricks-dependency-live Usa query con view=dependencies y
classification=UNKNOWN. ¿Qué dependencias quedan explícitamente como UNKNOWN
(por ejemplo linaje dinámico de tablas/columnas en system.access.table_lineage
o código interno de notebooks) y por qué no se infieren ni se arranca un SQL
Warehouse para consultarlas?
```

```json
{"operation":"query","view":"dependencies","workspace_name":"<APPROVED_DATABRICKS_WORKSPACE_NAME>","classification":"UNKNOWN","limit":25}
```

### 6. Grounded questions on findings, coverage and FinOps

```text
@databricks-dependency-live Usa query/findings con area=security y
status=failed. Prioriza únicamente los riesgos observados con su recurso,
configuración, fuente, hora UTC y recomendación oficial de Microsoft Learn.
```

```json
{"operation":"query","view":"findings","area":"security","status":"failed","limit":15}
```

```text
@databricks-dependency-live Usa query/findings con area=finops y query/finops.
¿Qué jobs productivos están atados a clústeres All-Purpose (existing_cluster_id),
qué clústeres o SQL Warehouses carecen de autoterminación acotada y qué costes
ARM reales tienen moneda y ResourceId verificados sin inventar ahorros DBU?
```

```json
{"operation":"query","view":"finops","limit":15}
```

```text
@databricks-dependency-live Usa query/coverage para comprobar qué fuentes ARM,
Workspace REST y Unity Catalog respondieron complete, partial, denied o
not_configured, incluyendo el modo de autenticación cross-tenant configurado.
```

```json
{"operation":"query","view":"coverage","limit":25}
```
