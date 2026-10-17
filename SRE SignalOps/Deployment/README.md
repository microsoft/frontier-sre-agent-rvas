**[Home](../README.md)** | [Missions](../Missions/README.md)

# Deployment

Choose a deployment path before beginning the operational missions. These paths
have different resource coverage; they are not interchangeable deployments.

| Path | Coverage | Start here |
|---|---|---|
| Terraform | Full lab workload, including hub-spoke networking, VMs, Grubify, and Parking Manager | [Terraform deployment](./Terraform/README.md) |
| Bicep with azd | Isolated SignalOps Grubify workload, SRE Agent, telemetry connectors, and incident routing | [Bicep deployment](./Bicep/README.md) |

Both guides use the same **Prepare → Deploy → Verify** journey:

1. **Prepare:** confirm tools, access, subscription, quota, and resource ownership.
2. **Deploy:** review the planned scope, then provision the selected environment.
3. **Verify:** check applications, telemetry, agent scope, specialists, response
   plan, and the observed baseline before beginning missions 01–12.

Terraform includes a completion script; Bicep uses stages 00–02. These deployment
stage numbers are independent of mission numbers. Both paths use the shared
SignalOps specialist configuration and mission context helper. Never mix
ownership between deployment tools.

Matching guide structure does not mean matching infrastructure. The Bicep core
does not create a hub-spoke network or VM tiers. VM, backup, and networking
missions still require their stated live prerequisites or a labeled evidence
pack, whichever path you choose.
