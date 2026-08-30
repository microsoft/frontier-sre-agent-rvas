const capabilities = [
    {
        icon: 'search-code',
        label: 'Investigate & advise',
        short: 'Natural-language operations',
        kicker: 'Ask the environment',
        situation: 'Checkout latency rises after a routine deployment. Dashboards show symptoms, but the causal change is buried across telemetry and source history.',
        prompt: '“What changed in the last hour, and why is checkout degraded?”',
        response: 'The agent queries connected telemetry, compares the incident window, correlates deployment evidence, and returns a source-cited hypothesis with next steps.',
        evidence: ['Azure Monitor', 'Application Insights', 'GitHub', 'Live reports'],
        caption: 'Grounded investigation across connected systems',
        nodes: [
            ['activity', 'Production signal', 'Latency + errors'],
            ['database-zap', 'Connected evidence', 'Metrics · logs · code'],
            ['brain-circuit', 'Root-cause hypothesis', 'Evidence cited'],
            ['clipboard-check', 'Operator decision', 'Advise before action']
        ],
        talk: 'This is not a generic chatbot answer. The response is grounded in the systems the SRE team already trusts, with citations an engineer can inspect.',
        outcomes: [['Faster triage', 'Less context hunting'], ['Grounded answers', 'Evidence over intuition']]
    },
    {
        icon: 'siren',
        label: 'Automate incidents',
        short: 'Alert-to-mitigation workflow',
        kicker: 'When the alert fires',
        situation: 'A memory alert wakes the on-call engineer. The relevant logs, deployment, incident ticket, and runbook live in four different systems.',
        prompt: 'Alert: pod memory pressure · severity 1',
        response: 'SRE Agent receives the incident, gathers correlated signals, identifies the probable change, proposes mitigations, and enriches the incident thread.',
        evidence: ['Azure Monitor Alerts', 'PagerDuty', 'ServiceNow', 'Response plans'],
        caption: 'One investigation thread from alert to controlled mitigation',
        nodes: [
            ['bell-ring', 'Incident platform', 'Alert received'],
            ['scan-search', 'Automated triage', 'Correlate signals'],
            ['stethoscope', 'Probable cause', 'Deployment linked'],
            ['shield-check', 'Mitigation gate', 'Approve or automate', true]
        ],
        talk: 'The agent does the expensive first minutes immediately: collecting context, testing a hypothesis, and preparing a mitigation while the human retains the decision boundary.',
        outcomes: [['Lower MTTR', 'Minutes matter'], ['One thread', 'Reduced tool switching']]
    },
    {
        icon: 'calendar-clock',
        label: 'Schedule operations',
        short: 'Proactive reliability work',
        kicker: 'Before an incident exists',
        situation: 'Health checks, compliance sweeps, and operational hygiene compete with urgent delivery work and are often performed inconsistently.',
        prompt: 'Every weekday at 07:00: validate service health and protection coverage.',
        response: 'A scheduled task invokes focused agent instructions, performs permitted checks, and sends results to the configured incident or notification channel.',
        evidence: ['Scheduled tasks', 'Health checks', 'Compliance', 'Notifications'],
        caption: 'Repeatable operations run on a defined schedule',
        nodes: [
            ['calendar-days', 'Schedule', 'Time + instructions'],
            ['bot', 'Custom agent', 'Focused workflow'],
            ['list-checks', 'Operational checks', 'Health · risk · drift'],
            ['send', 'Team channel', 'Actionable results']
        ],
        talk: 'Reliability improves when the routine work happens before the page. Scheduled workflows turn known operational intent into a consistent habit.',
        outcomes: [['Less toil', 'Routine work automated'], ['Earlier signals', 'Find risk before impact']]
    },
    {
        icon: 'network',
        label: 'Connect context',
        short: 'Tools your team already uses',
        kicker: 'Bring the evidence together',
        situation: 'Operational truth is fragmented across Azure telemetry, external observability, repositories, incident platforms, and team communication.',
        prompt: 'Connect the systems that explain what is happening and what changed.',
        response: 'Native connectors, managed connectors, and MCP servers let the agent retrieve permitted context from Azure and the wider operations ecosystem.',
        evidence: ['Log Analytics', 'Azure DevOps', 'Datadog', 'MCP servers'],
        caption: 'A governed context layer over the existing toolchain',
        nodes: [
            ['gauge', 'Observability', 'Azure + partner tools'],
            ['git-branch', 'Change systems', 'Repos + pipelines'],
            ['messages-square', 'Incident workflow', 'Tickets + channels'],
            ['waypoints', 'SRE Agent context', 'Connected, not copied']
        ],
        talk: 'SRE Agent does not ask teams to abandon their tools. It connects them into one investigation surface so evidence can travel with the incident.',
        outcomes: [['Shared context', 'Systems connected'], ['Fewer pivots', 'One investigation surface']]
    },
    {
        icon: 'blocks',
        label: 'Extend the engineer',
        short: 'Skills, agents, code & MCP',
        kicker: 'Encode how your team operates',
        situation: 'Every environment has specialized diagnostics, internal APIs, approved runbooks, and domain knowledge that a generic agent cannot infer.',
        prompt: 'Teach the agent our disk triage, network validation, and escalation procedure.',
        response: 'Five extension points shape the operating model: skills, custom agents, Python tools, MCP servers, and lifecycle hooks.',
        evidence: ['Skills', 'Custom agents', 'Python tools', 'MCP', 'Hooks'],
        caption: 'Composable extensions turn team practice into agent capability',
        nodes: [
            ['wrench', 'Skill or tool', 'Discrete capability'],
            ['users-round', 'Specialist agent', 'Domain reasoning'],
            ['workflow', 'Lifecycle hook', 'Policy + integration'],
            ['bot', 'SRE teammate', 'Environment-aware']
        ],
        talk: 'The value is not only what ships in the product. Teams can encode their own reliable procedures and assign them to specialists with precise tool boundaries.',
        outcomes: [['Domain depth', 'Your practices encoded'], ['Reusable operations', 'Capability as an asset']]
    },
    {
        icon: 'shield-check',
        label: 'Govern every action',
        short: 'Identity, policy & approval',
        kicker: 'Fast does not mean uncontrolled',
        situation: 'An AI system can identify a fix, but production actions must still respect ownership, least privilege, network boundaries, and approval policy.',
        prompt: 'Restart the affected workload only if policy permits and the operator approves.',
        response: 'Managed identity, Azure RBAC, network isolation, run modes, hooks, and allow/ask/deny tool policies evaluate the proposed call before execution.',
        evidence: ['Managed identity', 'Azure RBAC', 'Review mode', 'Tool policies'],
        caption: 'Every proposed tool call crosses the governance boundary',
        nodes: [
            ['lightbulb', 'Proposed action', 'Evidence-backed'],
            ['fingerprint', 'Identity + RBAC', 'Who can do what'],
            ['shield-alert', 'Policy decision', 'Allow · ask · deny', true],
            ['terminal-square', 'Audited execution', 'Controlled outcome']
        ],
        talk: 'Governance is in the execution path, not added after it. Review mode pauses write actions for approval; Autonomous mode acts only inside the permissions and policies already defined.',
        outcomes: [['Bounded autonomy', 'Policy before action'], ['Auditability', 'Actions remain traceable']]
    },
    {
        icon: 'brain-circuit',
        label: 'Reuse what worked',
        short: 'Persistent operational context',
        kicker: 'The next incident starts smarter',
        situation: 'A recurring failure is solved at 02:00, but the reasoning disappears into a ticket and the next on-call engineer starts from zero.',
        prompt: 'Have we seen this pattern before, and what resolved it safely?',
        response: 'Retained context and generated insights can preserve verified root causes, resolution steps, topology, and escalation preferences for future investigations.',
        evidence: ['Persistent memory', 'Session insights', 'Past incidents', 'Team context'],
        caption: 'Verified operational learning feeds the next investigation',
        nodes: [
            ['file-search', 'Investigation', 'Evidence + outcome'],
            ['badge-check', 'Verified lesson', 'Cause + resolution'],
            ['brain-circuit', 'Shared context', 'Pattern retained'],
            ['refresh-cw', 'Next incident', 'Better starting point']
        ],
        talk: 'The agent helps turn incident response into organizational memory, reducing dependence on whoever happened to be on call when the problem was last solved.',
        outcomes: [['Less relearning', 'Context compounds'], ['Stronger on-call', 'Knowledge survives handoff']]
    }
];

const buttonContainer = document.querySelector('#capability-buttons');
const stage = document.querySelector('#capability-stage');
let activeIndex = 0;

function icon(name) {
    return `<i data-lucide="${name}" aria-hidden="true"></i>`;
}

function renderButtons() {
    buttonContainer.innerHTML = capabilities.map((capability, index) => `
        <button class="capability-button" id="capability-tab-${index}" type="button" role="tab"
            aria-selected="${index === activeIndex}" aria-controls="capability-stage" tabindex="${index === activeIndex ? 0 : -1}" data-index="${index}">
            ${icon(capability.icon)}
            <span><strong>${capability.label}</strong><small>${capability.short}</small></span>
            <span class="capability-number">${String(index + 1).padStart(2, '0')}</span>
        </button>
    `).join('');
}

function renderStage(index, focusButton = false) {
    activeIndex = index;
    const capability = capabilities[index];
    document.querySelector('#stage-index').textContent = `${String(index + 1).padStart(2, '0')} / ${String(capabilities.length).padStart(2, '0')}`;
    document.querySelector('#stage-icon').innerHTML = icon(capability.icon);
    document.querySelector('#stage-kicker').textContent = capability.kicker;
    document.querySelector('#stage-title').textContent = capability.label;
    document.querySelector('#stage-situation').textContent = capability.situation;
    document.querySelector('#stage-prompt').textContent = capability.prompt;
    document.querySelector('#stage-response').textContent = capability.response;
    document.querySelector('#diagram-caption').textContent = capability.caption;
    document.querySelector('#stage-talk-track').textContent = capability.talk;
    document.querySelector('#stage-evidence').innerHTML = capability.evidence.map(item => `<span class="evidence-chip">${item}</span>`).join('');
    document.querySelector('#signal-diagram').innerHTML = capability.nodes.map(node => `
        <div class="diagram-node${node[3] ? ' is-guarded' : ''}">
            ${icon(node[0])}<strong>${node[1]}</strong><small>${node[2]}</small>
        </div>
    `).join('');
    document.querySelector('#stage-outcomes').innerHTML = capability.outcomes.map(outcome => `
        <div class="outcome"><strong>${outcome[0]}</strong><span>${outcome[1]}</span></div>
    `).join('');

    document.querySelectorAll('.capability-button').forEach((button, buttonIndex) => {
        const selected = buttonIndex === index;
        button.setAttribute('aria-selected', selected);
        button.tabIndex = selected ? 0 : -1;
        if (selected && focusButton) button.focus();
    });

    stage.classList.remove('stage-refresh');
    void stage.offsetWidth;
    stage.classList.add('stage-refresh');
    lucide.createIcons();
}

renderButtons();
renderStage(0);

buttonContainer.addEventListener('click', event => {
    const button = event.target.closest('.capability-button');
    if (button) renderStage(Number(button.dataset.index));
});

buttonContainer.addEventListener('keydown', event => {
    if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let nextIndex = activeIndex;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (activeIndex + 1) % capabilities.length;
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (activeIndex - 1 + capabilities.length) % capabilities.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = capabilities.length - 1;
    renderStage(nextIndex, true);
});

document.querySelector('#present-button').addEventListener('click', async () => {
    if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
    } else {
        await document.exitFullscreen();
    }
});

document.addEventListener('fullscreenchange', () => {
    const button = document.querySelector('#present-button');
    const presenting = Boolean(document.fullscreenElement);
    button.title = presenting ? 'Exit presentation mode' : 'Enter presentation mode';
    button.setAttribute('aria-label', button.title);
    button.innerHTML = icon(presenting ? 'minimize-2' : 'presentation');
    lucide.createIcons();
});

lucide.createIcons();