# Frontier Azure SRE Agent Solution

## Introduction

The Frontier Azure SRE Agent Solution is a comprehensive framework designed to enhance the reliability, scalability, and performance of applications deployed on Microsoft Azure. This solution provides a set of tools, best practices, and automation scripts that enable Site Reliability Engineers (SREs) to effectively monitor, manage, and optimize their cloud infrastructure using Azure SRE agent.

## Workshop Challenges

Ten hands-on challenges: configure the SRE Agent building blocks, then trigger and observe 6 autonomous scenarios.
Open `web/index.html` in a browser for the interactive UI (coach mode: **Shift+C**).

| # | Challenge | Type | Key Concept |
|---|-----------|------|-------------|
| [00](Student/Challenge-00.md) | Prerequisites & Lab Setup | Setup | Terraform deploy, `make config-sre-agent`, GitHub OAuth |
| [01](Student/Challenge-01.md) | Skills & Knowledge Docs | Config | Write a skill YAML + knowledge doc, apply, verify |
| [02](Student/Challenge-02.md) | Subagents & Incident Filters | Config | Write a subagent + incident filter, verify routing |
| [03](Student/Challenge-03.md) | Connectors, Repos & Scheduled Tasks | Config | Connector chain, scheduled task, manual trigger |
| [04](Student/Challenge-04.md) | Autonomous App Incident Response | Scenario | `aca-app-incident-handler`, 5xx detection & remediation |
| [05](Student/Challenge-05.md) | Code Correlation & GitHub Integration | Scenario | Inline code-analyzer, GitHub PR via OAuth |
| [06](Student/Challenge-06.md) | Proactive Workflow Automation | Scenario | `issue-triager`, scheduled GitHub triage |
| [07](Student/Challenge-07.md) | IaaS Service Recovery | Scenario | `iaas-vm-incident-handler`, VM run-command |
| [08](Student/Challenge-08.md) | Network Diagnostics (Interactive) | Scenario | UDR asymmetry, Traffic Analytics KQL |
| [09](Student/Challenge-09.md) | Autonomous NSG Remediation | Scenario | NSG deny flow, autonomous rule removal |
| [10](Student/Challenge-10.md) | Build Your Own Production-Ready SRE Agent | Capstone | Design, implement & demo a custom agent for your own use case |

**Coaches:** see [Coach/README.md](Coach/README.md) for solution guides, mini-lectures, and debrief discussion guides.


## Contributors

Thanks to everyone who has contributed!

<a href="https://github.com/microsoft/frontier-sre-agent-rvas/graphs/contributors">
  <img src="https://contributors-img.web.app/image?repo=microsoft/frontier-sre-agent-rvas" />
</a>
