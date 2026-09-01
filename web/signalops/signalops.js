const missions = [
    ['00', 'Bootstrap', 'Deploy the Workload with azd', 'Create the isolated food application and workspace-backed observability from Bicep.', '30–40 min', ['azd', 'Bicep', 'Container Apps']],
    ['01', 'Bootstrap', 'Deploy the Agent Core with azd', 'Add the SRE Agent, managed identity, governed RBAC, and managed resource scope.', '20–30 min', ['azd provision', 'RBAC', 'Agent']],
    ['02', 'Bootstrap', 'Deploy Evidence Connectors with azd', 'Add Azure telemetry connectors and prove the resulting evidence-plane ground truth.', '20–25 min', ['Connectors', 'Knowledge', 'Telemetry']],
    ['03', 'Bootstrap', 'Investigate and Recover a Grubify Memory Incident', 'Trigger a real Grubify memory incident, follow Azure Monitor and SRE Agent evidence, then recover and verify.', '30–40 min', ['Alerts', 'Memory', 'RCA']],
    ['04', 'Bootstrap', 'Build Grubify Knowledge and Incident Memory', 'Upload approved Grubify knowledge, verify indexing, and inspect memory-first specialist instructions.', '20–30 min', ['Agent Memory', 'Knowledge', 'Indexing']],
    ['05', 'Wire', 'Investigate an Evidence Blind Spot', 'Validate each telemetry source, classify a failed or stale read, and choose a safe fallback or escalation.', '20–25 min', ['Evidence', 'Freshness', 'Escalation']],
    ['06', 'Wire', 'Route a Cross-Domain Incident', 'Compare live specialists with desired state, then route application and network evidence without losing ownership.', '20–25 min', ['Routing', 'Handoffs', 'Ownership']],
    ['07', 'Wire', 'Exercise a Guarded HTTP-Error Response', 'Verify HTTP-error routing, gather current evidence, and exercise proposal-only stop and recovery criteria.', '25–30 min', ['HTTP errors', 'Routing', 'Recovery']],
    ['08', 'Trace', 'Scope Impact with Dependency Evidence', 'Bound the affected Grubify user journey and identify the next discriminating check.', '20–25 min', ['Dependencies', 'Blast radius', 'Telemetry']],
    ['09', 'Trace', 'Investigate a Network Security Failure', 'Find the NSG decision that blocks an application dependency.', '25–30 min', ['NSG', 'Flow Logs', 'Blast radius']],
    ['10', 'Trace', 'Investigate a Routing Black Hole', 'Use effective routes and next-hop evidence to expose asymmetric routing.', '25–30 min', ['UDR', 'Next hop', 'Routing']],
    ['11', 'Operate', 'Heartbeat Triage and Deep RCA', 'Separate symptom from cause and defend an evidence-backed RCA.', '20–25 min', ['Heartbeat', 'Triage', 'RCA']],
    ['12', 'Operate', 'Improve the Next Heartbeat Response', 'Replay the incident with verified context while keeping current evidence authoritative.', '20–25 min', ['Context', 'Learning', 'Evidence']],
    ['13', 'Operate', 'Resolve a Critical Assurance Risk', 'Find a critical preventive issue and define owned remediation, rollback, and validation.', '20–25 min', ['Assurance', 'Prevention', 'Governance']],
    ['14', 'Operate', 'Resolve a Backup Assurance Incident', 'Triage recoverability risk, communicate impact, and validate service after recovery.', '20–25 min', ['Azure Backup', 'Communication', 'Recovery']]
];

const contentVersion = '9';

const labDetails = {
    number: 'LAB',
    phase: 'Orient',
    title: 'Understand Grubify',
    summary: 'Learn the application, Azure architecture, evidence flow, and expected normal state before deploying anything.',
    duration: '15–20 min',
    tags: ['Application', 'Architecture', 'Baseline']
};

const studentFiles = [
    { file: '../sre-signalops/Lab-Details.md', title: labDetails.title, label: 'Lab details' },
    ...missions.map(mission => ({ file: `../sre-signalops/Challenge-${mission[0]}.md`, title: mission[2], label: `Mission ${mission[0]}` }))
];
const coachFiles = [
    { file: '../sre-signalops/Coach/Lab-Details.md', title: labDetails.title, label: 'Lab details' },
    ...missions.map(mission => ({ file: `../sre-signalops/Coach/Solution-${mission[0]}.md`, title: mission[2], label: `Solution ${mission[0]}` }))
];

const challengeGrid = document.getElementById('challenge-grid');
const coachList = document.getElementById('coach-list');

function createChallengeCard(number, phase, title, summary, duration, tags, index, buttonLabel) {
    const article = document.createElement('article');
    article.className = `challenge-card phase-${phase.toLowerCase()}`;
    article.innerHTML = `<div class="card-meta"><span class="number">${number}</span><span class="duration">${duration}</span></div>
        <p class="card-label">${phase}</p><h3>${title}</h3><p>${summary}</p>
        <ul class="tags" aria-label="Topics">${tags.map(tag => `<li>${tag}</li>`).join('')}</ul>
        <button class="open-reader" data-kind="student" data-index="${index}">${buttonLabel} <span aria-hidden="true">→</span></button>`;
    challengeGrid.appendChild(article);
}

createChallengeCard(labDetails.number, labDetails.phase, labDetails.title, labDetails.summary, labDetails.duration, labDetails.tags, 0, 'Open lab details');

missions.forEach((mission, index) => {
    const [number, phase, title, summary, duration, tags] = mission;
    createChallengeCard(number, phase, title, summary, duration, tags, index + 1, 'Open mission');

    const coachButton = document.createElement('button');
    coachButton.className = 'coach-row open-reader';
    coachButton.dataset.kind = 'coach';
    coachButton.dataset.index = index + 1;
    coachButton.innerHTML = `<span>Solution ${number}</span><strong>${title}</strong><span aria-hidden="true">→</span>`;
    coachList.appendChild(coachButton);
});

const labCoachButton = document.createElement('button');
labCoachButton.className = 'coach-row open-reader';
labCoachButton.dataset.kind = 'coach';
labCoachButton.dataset.index = 0;
labCoachButton.innerHTML = `<span>Lab details</span><strong>${labDetails.title}</strong><span aria-hidden="true">→</span>`;
coachList.prepend(labCoachButton);

const reader = document.getElementById('reader');
const overlay = document.getElementById('reader-overlay');
const content = document.getElementById('reader-content');
const readerTitle = document.getElementById('reader-title');
const readerKind = document.getElementById('reader-kind');
const previousButton = document.getElementById('reader-prev');
const nextButton = document.getElementById('reader-next');
const closeButton = document.getElementById('reader-close');
const coachToggle = document.getElementById('coach-toggle');
const coachGuides = document.getElementById('coach-guides');
const backgroundRegions = document.querySelectorAll('.site-header, main, footer');

let activeFiles = studentFiles;
let activeIndex = 0;
let returnFocus = null;

function normalizedPath(file) {
    return new URL(file, window.location.href).pathname;
}

function findEntry(path) {
    const studentIndex = studentFiles.findIndex(entry => normalizedPath(entry.file) === path);
    if (studentIndex >= 0) return { files: studentFiles, index: studentIndex };

    const coachIndex = coachFiles.findIndex(entry => normalizedPath(entry.file) === path);
    if (coachIndex >= 0) return { files: coachFiles, index: coachIndex };

    return null;
}

async function renderMermaidDiagrams() {
    if (!window.mermaid) return;

    const blocks = [...content.querySelectorAll('pre code.language-mermaid')];
    if (blocks.length === 0) return;

    const diagrams = blocks.map((block, index) => {
        const figure = document.createElement('figure');
        figure.className = 'reader-diagram';

        const diagram = document.createElement('div');
        diagram.className = 'mermaid';
        diagram.id = `mission-diagram-${activeIndex}-${index}`;
        diagram.textContent = block.textContent;
        figure.appendChild(diagram);
        block.parentElement.replaceWith(figure);
        return diagram;
    });

    try {
        await window.mermaid.run({ nodes: diagrams });
    } catch (error) {
        diagrams.forEach(diagram => {
            if (!diagram.querySelector('svg')) {
                diagram.className = 'reader-diagram-error';
                diagram.textContent = `Diagram unavailable: ${error.message}`;
            }
        });
    }
}

async function renderEntry() {
    const entry = activeFiles[activeIndex];
    const isCoach = activeFiles === coachFiles;

    readerKind.textContent = isCoach ? `Coach · ${entry.label}` : entry.label;
    readerTitle.textContent = entry.title;
    previousButton.disabled = activeIndex === 0;
    nextButton.disabled = activeIndex === activeFiles.length - 1;
    content.innerHTML = '<div class="reader-loading">Loading document…</div>';
    document.querySelector('.reader-body').scrollTop = 0;

    try {
        const documentUrl = new URL(entry.file, window.location.href);
        documentUrl.searchParams.set('v', contentVersion);
        const response = await fetch(documentUrl);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        content.innerHTML = DOMPurify.sanitize(marked.parse(await response.text()));
        await renderMermaidDiagrams();
        content.querySelectorAll('a[href]').forEach(link => {
            const href = link.getAttribute('href');
            if (!href) return;

            const resolvedUrl = new URL(href, new URL(entry.file, window.location.href));
            if (resolvedUrl.pathname.endsWith('/sre-signalops/README.md') || resolvedUrl.pathname.endsWith('/sre-signalops/Coach/README.md')) {
                link.href = '#challenges';
                link.addEventListener('click', event => {
                    event.preventDefault();
                    closeReader();
                    document.getElementById('challenges').scrollIntoView();
                });
                return;
            }
            if (resolvedUrl.pathname.endsWith('.md')) {
                link.addEventListener('click', event => {
                    const match = findEntry(resolvedUrl.pathname);
                    if (!match) {
                        link.href = resolvedUrl.href;
                        return;
                    }
                    event.preventDefault();
                    activeFiles = match.files;
                    activeIndex = match.index;
                    renderEntry();
                });
                link.href = resolvedUrl.href;
            } else if (resolvedUrl.protocol === 'http:' || resolvedUrl.protocol === 'https:') {
                link.href = resolvedUrl.href;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
            }
        });
    } catch (error) {
        const message = document.createElement('p');
        message.className = 'reader-error';
        message.textContent = `Unable to load ${entry.file}: ${error.message}`;
        content.replaceChildren(message);
    }
}

function openReader(kind, index, trigger) {
    activeFiles = kind === 'coach' ? coachFiles : studentFiles;
    activeIndex = index;
    returnFocus = trigger;
    reader.classList.add('open');
    overlay.classList.add('open');
    reader.setAttribute('aria-hidden', 'false');
    backgroundRegions.forEach(region => { region.inert = true; });
    document.body.style.overflow = 'hidden';
    renderEntry();
    closeButton.focus();
}

function closeReader() {
    reader.classList.remove('open');
    overlay.classList.remove('open');
    reader.setAttribute('aria-hidden', 'true');
    backgroundRegions.forEach(region => { region.inert = false; });
    document.body.style.overflow = '';
    if (returnFocus) returnFocus.focus();
}

document.querySelectorAll('.open-reader').forEach(button => {
    button.addEventListener('click', () => {
        openReader(button.dataset.kind, Number(button.dataset.index), button);
    });
});

previousButton.addEventListener('click', () => {
    if (activeIndex > 0) {
        activeIndex -= 1;
        renderEntry();
    }
});

nextButton.addEventListener('click', () => {
    if (activeIndex < activeFiles.length - 1) {
        activeIndex += 1;
        renderEntry();
    }
});

closeButton.addEventListener('click', closeReader);
overlay.addEventListener('click', closeReader);

coachToggle.addEventListener('change', () => {
    coachGuides.hidden = !coachToggle.checked;
    sessionStorage.setItem('signalOpsCoachMode', coachToggle.checked ? 'on' : 'off');
    if (coachToggle.checked) coachGuides.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

if (sessionStorage.getItem('signalOpsCoachMode') === 'on') {
    coachToggle.checked = true;
    coachGuides.hidden = false;
}

document.addEventListener('keydown', event => {
    if (!reader.classList.contains('open')) return;
    if (event.key === 'Escape') closeReader();
    if (event.key === 'Tab') {
        const focusable = [...reader.querySelectorAll('a[href], button:not([disabled])')];
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
    if (event.key === 'ArrowLeft' && activeIndex > 0) {
        activeIndex -= 1;
        renderEntry();
    }
    if (event.key === 'ArrowRight' && activeIndex < activeFiles.length - 1) {
        activeIndex += 1;
        renderEntry();
    }
});