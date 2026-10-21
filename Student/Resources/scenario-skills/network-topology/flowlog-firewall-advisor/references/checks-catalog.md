# Checks catalog

How this skill classifies what it finds. Severity reflects blast radius and
likelihood, not the effort to fix.

## Severity bands

| Band | Meaning | Typical response |
|---|---|---|
| Critical | Traffic that would let an attacker move or administer across a trust boundary, or a rule so broad it is effectively any to any | Confirm intent before the policy is written, not after |
| High | Traffic that will work on day one and break later, or that crosses the boundary to a sensitive service | Needs an owner and a decision |
| Medium | Broader reach than the evidence strictly supports | Review, usually keep with a narrower scope |
| Low | Ordinary service traffic between known endpoints | Accept |
| Info | Excluded from the rules, recorded so the exclusion is visible | No action, but do not hide it |

## Checks

### Management ports across a boundary

**Critical.** Any of 22, 23, 512, 513, 514, 3389, 5985 or 5986 in a proposed rule.
Administrative access reaching across the virtual network boundary, or between
subnets, is the finding a security team acts on first. A rule that permits it should
be a deliberate decision with a named owner, never a by product of what the capture
happened to see.

### Effectively any to any

**Critical.** More than 64 distinct ports pooled into a single rule. At that width the
rule has stopped describing a service and started describing a host. Usually a sign
that a scanner, a health probe sweep, or an ephemeral port range has been mistaken for
service traffic.

### Public egress with no service tag

**High.** A rule leaving the virtual network to a public address where Traffic
Analytics did not resolve a service tag. The rule pins IP literals, and the addresses
behind software as a service change without notice. It will work when deployed and
fail silently weeks later. Where the destination is really a fully qualified domain
name, an application rule is the correct instrument and this skill cannot produce one.

### Database ports crossing the boundary

**High.** Any of 1433, 3306, 5432, 1521, 27017, 6379, 9200, 5984 or 11211 crossing the
virtual network boundary. Either a private endpoint is missing, or data is genuinely
leaving the boundary and that should be a conscious decision.

### Source broader than the evidence

**Medium.** The rule's source is a subnet rather than specific hosts, because enough
hosts in one /24 were observed that the analysis collapsed them. The rule now permits
addresses never seen. This is the only place the analysis widens anything, and it is
always listed explicitly.

### Fan out

**Medium.** One source reaching more than eight destinations. Legitimate for a
gateway or a scanner, worth a question for anything else.

### Service traffic between known endpoints

**Low.** A small port set between specific hosts. The bulk of a healthy result.

## Exclusions, always reported

These never become rules. They are counted and stated so their absence is a decision
rather than an oversight.

### Connections already blocked

Flow logs record a verdict at each evaluation point, so one blocked connection appears
twice: allowed leaving the source, denied arriving at the destination. Trusting the
allowed record produces a rule permitting traffic the current policy blocks, widening
access at cutover while looking correct. Any connection denied anywhere is excluded
everywhere and reported separately.

### Platform traffic

The host endpoint at 168.63.129.16, the instance metadata service at 169.254.169.254,
link local, loopback and multicast. Delivered by the platform, not routed through a
firewall. A rule for them consumes the policy budget for no effect.

### Below the flow threshold

Connections seen fewer times than the minimum. Single probes and scan noise. The
threshold is a parameter and the excluded count is always reported, because one
observation of a quarterly job is still a real dependency.

## Policy budget

An Azure Firewall policy permits 20,000 unique source and destination combinations in
network rules, counted as `protocolCount * sourceCount * destinationCount * ceil(portCount / 14)`,
summed across every rule. Flow log derived rules exceed this easily. The total is
calculated and reported, and a breach is raised as the first method note rather than
left for a deployment to discover.

Ways down, in order of preference: raise the minimum flow count, narrow the scope to
one direction, then accept subnet level granularity.

The tool expands destination port ranges before grouping the port count in blocks of 14. Existing policy rules consume additional budget. The proposed rules are a draft: use isolated staging tests and owner approval before a controlled deployment, not an imaginary universal non enforcing mode.

## Sources

- [Azure Firewall limits](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-firewall-limits), verified: the divisor is 14 with rounding upward.
