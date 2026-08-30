const missions = [
    ['00', 'Bootstrap', 'Launch the Workload', 'Deploy Grubify with azd and validate the application from PowerShell.', '20–30 min', ['azd', 'PowerShell', 'Container Apps']],
    ['01', 'Bootstrap', 'Establish the Agent Core', 'Create the SRE Agent control plane and persist a reusable PowerShell context.', '15–20 min', ['Azure CLI', 'RBAC', 'Agent']],
    ['02', 'Bootstrap', 'Connect Ground Truth', 'Attach source, knowledge, and observability context without exposing credentials.', '20–25 min', ['GitHub', 'Knowledge', 'Telemetry']],
    ['03', 'Bootstrap', 'Arm the Operator', 'Load operational skills and verify read, write, and approval boundaries.', '20–25 min', ['Skills', 'Safety', 'PowerShell']],
    ['04', 'Wire', 'Discover Connected Systems', 'Inventory live connectors and prove which external systems are reachable.', '15–20 min', ['MCP', 'Connectors', 'Discovery']],
    ['05', 'Wire', 'Discover Specialist Agents', 'Inspect specialist identities, tool grants, and routing boundaries.', '15–20 min', ['Subagents', 'Routing', 'Least privilege']],
    ['06', 'Wire', 'Understand Response Plans', 'Trace an alert from filter match through investigation, approval, and validation.', '20–25 min', ['Response plans', 'Incidents', 'Automation']],
    ['07', 'Trace', 'Map the Application Dependency Graph', 'Build an evidence-backed service map before diagnosing a failure.', '20–25 min', ['App Insights', 'Topology', 'Dependencies']],
    ['08', 'Trace', 'Investigate a Network Security Failure', 'Find the NSG decision that blocks an application dependency.', '25–30 min', ['NSG', 'Flow Logs', 'Blast radius']],
    ['09', 'Trace', 'Investigate a Routing Black Hole', 'Use effective routes and next-hop evidence to expose asymmetric routing.', '25–30 min', ['UDR', 'Next hop', 'Routing']],
    ['10', 'Operate', 'Heartbeat Triage and Deep RCA', 'Separate symptom from cause and defend an evidence-backed RCA.', '20–25 min', ['Heartbeat', 'Triage', 'RCA']],
    ['11', 'Operate', 'Context That Learns', 'Compare grounded responses and preserve one verified operational lesson.', '20–25 min', ['Knowledge', 'Grounding', 'Learning']],
    ['12', 'Operate', 'Proactive Tenant Optimization', 'Turn cost, utilization, risk, and coverage signals into ranked action.', '20–25 min', ['Resource Graph', 'Advisor', 'FinOps']],
    ['13', 'Operate', 'Backup-to-Teams Resilience', 'Connect protection evidence, approval, communication, and service validation.', '20–25 min', ['Azure Backup', 'Teams', 'RTO / RPO']]
];

const studentFiles = missions.map(mission => ({ file: `../sre-signalops/Challenge-${mission[0]}.md`, title: mission[2] }));
const coachFiles = missions.map(mission => ({ file: `../sre-signalops/Coach/Solution-${mission[0]}.md`, title: mission[2] }));

const challengeGrid = document.getElementById('challenge-grid');
const coachList = document.getElementById('coach-list');

missions.forEach((mission, index) => {
    const [number, phase, title, summary, duration, tags] = mission;
    const article = document.createElement('article');
    article.className = `challenge-card phase-${phase.toLowerCase()}`;
    article.innerHTML = `<div class="card-meta"><span class="number">${number}</span><span class="duration">${duration}</span></div>
        <p class="card-label">${phase}</p><h3>${title}</h3><p>${summary}</p>
        <ul class="tags" aria-label="Capabilities">${tags.map(tag => `<li>${tag}</li>`).join('')}</ul>
        <button class="open-reader" data-kind="student" data-index="${index}">Open mission <span aria-hidden="true">→</span></button>`;
    challengeGrid.appendChild(article);

    const coachButton = document.createElement('button');
    coachButton.className = 'coach-row open-reader';
    coachButton.dataset.kind = 'coach';
    coachButton.dataset.index = index;
    coachButton.innerHTML = `<span>Solution ${number}</span><strong>${title}</strong><span aria-hidden="true">→</span>`;
    coachList.appendChild(coachButton);
});

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

async function renderEntry() {
    const entry = activeFiles[activeIndex];
    const isCoach = activeFiles === coachFiles;

    readerKind.textContent = isCoach ? 'Coach guide' : `Challenge ${missions[activeIndex][0]}`;
    readerTitle.textContent = entry.title;
    previousButton.disabled = activeIndex === 0;
    nextButton.disabled = activeIndex === activeFiles.length - 1;
    content.innerHTML = '<div class="reader-loading">Loading document…</div>';
    document.querySelector('.reader-body').scrollTop = 0;

    try {
        const response = await fetch(entry.file);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        content.innerHTML = DOMPurify.sanitize(marked.parse(await response.text()));
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