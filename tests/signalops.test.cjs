const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const zlib = require('node:zlib');

const root = path.resolve(__dirname, '..');
const track = path.join(root, 'SRE SignalOps');
const terraform = path.join(track, 'Deployment', 'Terraform', 'infra');

function loadBoard() {
    const elements = new Map();
    const element = () => ({
        dataset: {},
        children: [],
        appendChild(child) { this.children.push(child); },
        prepend(child) { this.children.unshift(child); },
        get childElementCount() { return this.children.length; },
        addEventListener() {}
    });
    const context = vm.createContext({
        document: {
            getElementById(id) {
                if (!elements.has(id)) elements.set(id, element());
                return elements.get(id);
            },
            querySelectorAll: () => [],
            addEventListener() {},
            createElement: element
        },
        sessionStorage: { getItem: () => null },
        URL,
        window: { location: { href: 'https://example.test/track/signalops/missions.html' } }
    });
    vm.runInContext(fs.readFileSync(path.join(root, 'web', 'signalops', 'signalops.js'), 'utf8'), context);
    return { elements, evaluate: expression => vm.runInContext(expression, context) };
}

test('board displays all twelve missions in order without an archive', () => {
    const { elements, evaluate } = loadBoard();
    assert.equal(elements.get('orientation-grid').childElementCount, 1);
    assert.equal(elements.get('challenge-grid').childElementCount, 12);
    assert.equal(elements.has('archive-grid'), false);
    assert.equal(elements.has('bicep-grid'), false);
    assert.equal(elements.get('coach-list').childElementCount, 16);
    const expected = Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, '0'));
    assert.deepEqual(JSON.parse(evaluate('JSON.stringify(missions.map(mission => mission[0]))')), expected);
    assert.deepEqual(elements.get('challenge-grid').children.map(card => card.innerHTML.match(/class="number">(\d+)/)[1]), expected);
    const html = fs.readFileSync(path.join(root, 'web', 'signalops', 'index.html'), 'utf8');
    assert.doesNotMatch(html, /archive|bicep-grid/i);
});

test('deployment overviews use matching Prepare Deploy Verify structure and distinct coverage', () => {
    const html = fs.readFileSync(path.join(root, 'web', 'signalops', 'index.html'), 'utf8');
    const cards = [...html.matchAll(/<article class="challenge-card phase-deploy deployment-card">([\s\S]*?)<\/article>/g)];
    assert.equal(cards.length, 2);
    for (const [index, card] of cards.entries()) {
        assert.deepEqual([...card[1].matchAll(/<li><strong>([^<]+)<\/strong>/g)].map(match => match[1]), ['Prepare', 'Deploy', 'Verify']);
        assert.equal((card[1].match(/class="open-reader"/g) || []).length, 1);
        const guide = fs.readFileSync(path.join(track, 'Deployment', index ? 'Bicep' : 'Terraform', 'README.md'), 'utf8');
        assert.deepEqual([...guide.matchAll(/^## (.+)$/gm)].map(match => match[1]), ['Prepare', 'Deploy', 'Verify']);
    }
    assert.match(cards[0][1], /Full lab/);
    assert.match(cards[1][1], /Core lab/);
    const css = fs.readFileSync(path.join(root, 'web', 'signalops', 'signalops.css'), 'utf8');
    assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.challenge-grid,\s*\.deployment-grid\s*\{\s*grid-template-columns: 1fr;/);
});

test('mission categories use clear labels with matching styles and documentation', () => {
    const { elements, evaluate } = loadBoard();
    const expected = new Map([
        ['Foundation', ['01', '02']],
        ['Connections & Routing', ['03', '04', '08']],
        ['Incident Response', ['05', '06', '07', '12']],
        ['Dependencies & Networking', ['09', '10', '11']]
    ]);
    const missions = JSON.parse(evaluate('JSON.stringify(missions)'));
    const css = fs.readFileSync(path.join(root, 'web', 'signalops', 'signalops.css'), 'utf8');
    const html = fs.readFileSync(path.join(root, 'web', 'signalops', 'index.html'), 'utf8');
    const readme = fs.readFileSync(path.join(track, 'README.md'), 'utf8');
    const cards = elements.get('challenge-grid').children;
    for (const [category, numbers] of expected) {
        assert.deepEqual(missions.filter(mission => mission[1] === category).map(mission => mission[0]), numbers);
        const className = `phase-${category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
        assert.ok(css.includes(`.challenge-card.${className}`), category);
        assert.equal(cards.filter(card => card.className === `challenge-card ${className}`).length, numbers.length);
        for (const number of numbers) {
            assert.ok(readme.includes(`| [${number}](./Missions/Challenge-${number}.md) | ${category} |`), number);
        }
        assert.ok(html.includes(`<strong>${category.replaceAll('&', '&amp;')}</strong>`), category);
    }
    const categoryList = html.match(/<ul class="journey-steps">([\s\S]*?)<\/ul>/);
    assert.ok(categoryList, 'Categories are an unordered list, not sequential phases');
    assert.equal((categoryList[1].match(/<li>/g) || []).length, 4);
    assert.match(html, /Follow mission numbers, not category order/);
    assert.doesNotMatch(html, />Phases<|>Wire<|>Operate<|>Trace</);
    assert.doesNotMatch(readme, /\| Phase \||\| (?:Bootstrap|Wire|Operate|Trace) \|/);
});

test('reader resolves every registered document and keeps Bicep navigation separate', () => {
    const { evaluate } = loadBoard();
    const entries = evaluate('[...studentFiles, ...bicepFiles, ...terraformFiles, ...deploymentFiles, ...missionFiles, ...coachFiles]');
    for (const entry of entries) {
        const relative = entry.file.replace('../sre-signalops/', '');
        assert.ok(fs.existsSync(path.join(track, relative)), entry.file);
        assert.ok(evaluate(`findEntry(normalizedPath(${JSON.stringify(entry.file)}))`), entry.file);
        if (relative.startsWith('Coach/')) {
            assert.deepEqual(fs.readFileSync(path.join(root, '_site', 'sre-signalops', relative)),
                fs.readFileSync(path.join(track, relative)), `Publish ${relative}`);
        }
    }
    assert.equal(evaluate('bicepFiles.length'), 4);
    assert.equal(evaluate("findEntry(normalizedPath(bicepFiles[1].file)).files === bicepFiles"), true);
    assert.equal(evaluate("findEntry(normalizedPath(studentFiles[1].file)).files === missionFiles"), true);
    assert.equal(evaluate('missionFiles.length'), 13);
    assert.equal(evaluate('terraformFiles.length'), 1);
    assert.equal(evaluate("coachFiles.filter(entry => entry.file.includes('/Coach/Deployment/')).length"), 3);
    assert.equal(evaluate("coachFiles.filter(entry => entry.file.includes('/Coach/Missions/')).length"), 12);
    for (const mission of JSON.parse(evaluate('JSON.stringify(missions)'))) {
        const [number, , title] = mission;
        const document = fs.readFileSync(path.join(track, 'Missions', `Challenge-${number}.md`), 'utf8');
        assert.match(document, new RegExp(`^# Challenge ${number} — `, 'm'));
        assert.ok(document.includes(` — ${title}`), number);
        const coach = fs.readFileSync(path.join(track, 'Coach', 'Missions', `Solution-${number}.md`), 'utf8');
        assert.ok(coach.includes(`Challenge ${number}: ${title}`), number);
    }
});

test('Bicep guides are independent of Terraform and upstream workshop links', () => {
    const guides = [
        ...fs.readdirSync(path.join(track, 'Deployment', 'Bicep')).map(file => path.join(track, 'Deployment', 'Bicep', file)),
        ...['Solution-00.md', 'Solution-01.md', 'Solution-02.md'].map(file => path.join(track, 'Coach', 'Deployment', file)),
        path.join(track, 'Coach', 'Customer-Demo-00-02.md')
    ];
    for (const file of guides) {
        assert.doesNotMatch(fs.readFileSync(file, 'utf8'), /terraform|frontier-sre-agent-rvas|MCAPS|b1e100ca-fff5-4e0e-9847-2e44bf47b68c|16b3c013-d300-468d-ac64-7eda0820b6d3|proudhill-f504bbcd/i, file);
    }
});

test('Bicep metadata and service sources belong to the local SignalOps project', () => {
    for (const file of ['main.bicep', 'backup.bicep']) {
        const template = fs.readFileSync(path.join(track, 'infra', file), 'utf8');
        assert.match(template, /solution:\s*'sre-signalops'/);
        assert.doesNotMatch(template, /frontier-sre-agent-rvas|repository:\s*'/);
    }
    const manifest = fs.readFileSync(path.join(track, 'azure.yaml'), 'utf8');
    const projects = [...manifest.matchAll(/^\s+project:\s*(.+)$/gm)].map(match => match[1].trim());
    assert.equal(projects.length, 2);
    for (const project of projects) {
        assert.doesNotMatch(project, /https?:|git::/);
        const directory = path.resolve(track, project);
        assert.ok(directory.startsWith(`${root}${path.sep}`), project);
        assert.ok(fs.existsSync(directory), project);
    }
    for (const file of ['Customer-Demo-00-02.md', 'Capability-Briefing-Notes.md', 'Grubify-Lab-Briefing-Notes.md']) {
        assert.doesNotMatch(fs.readFileSync(path.join(track, 'Coach', file), 'utf8'), /frontier-sre-agent-rvas/);
        assert.deepEqual(fs.readFileSync(path.join(root, '_site', 'sre-signalops', 'Coach', file)),
            fs.readFileSync(path.join(track, 'Coach', file)), `Publish the cleaned ${file}`);
    }
});

test('reorganized student documents have valid relative Markdown links', () => {
    const directories = ['Deployment', path.join('Deployment', 'Terraform'), path.join('Deployment', 'Bicep'), 'Missions',
        'Coach', path.join('Coach', 'Deployment'), path.join('Coach', 'Missions'), 'Scripts'];
    const files = ['README.md', 'Lab-Details.md'].map(file => path.join(track, file));
    files.push(...['Customer-Demo-00-02.md', 'Capability-Briefing-Notes.md', 'Grubify-Lab-Briefing-Notes.md']
        .map(file => path.join(track, 'Coach', file)));
    for (const directory of directories) {
        files.push(...fs.readdirSync(path.join(track, directory))
            .filter(file => file.endsWith('.md'))
            .map(file => path.join(track, directory, file)));
    }
    for (const file of files) {
        const markdown = fs.readFileSync(file, 'utf8');
        for (const match of markdown.matchAll(/\[[^\]]*\]\((\.[^)\s]+)\)/g)) {
            const target = match[1].split('#')[0];
            assert.ok(fs.existsSync(path.resolve(path.dirname(file), target)), `${path.relative(root, file)} -> ${target}`);
        }
    }
});

test('Terraform deployment is hosted in SignalOps without external guide redirects', () => {
    const folder = path.join(track, 'Deployment', 'Terraform');
    const guide = fs.readFileSync(path.join(folder, 'README.md'), 'utf8');
    assert.doesNotMatch(guide, /https:\/\/github\.com\/microsoft\/frontier-sre-agent-rvas|Student\/Challenge/);
    assert.match(guide, /\]\(signalops-terraform\.tar\.gz\)/);
    const configuration = fs.readFileSync(path.join(folder, 'infra', 'main.tf'), 'utf8');
    assert.match(configuration, /source\s*=\s*"\.\/modules\/workload"/);
    assert.doesNotMatch(configuration, /Coach\/Solutions|\.\.\/|git::/);
    const compute = fs.readFileSync(path.join(folder, 'infra', 'modules', 'workload', 'compute.tf'), 'utf8');
    assert.doesNotMatch(compute, /admin_password\s*=\s*"/);
});

test('published Terraform package includes local module dependencies, not local deployment data', () => {
    const published = path.join(root, '_site', 'sre-signalops', 'Deployment', 'Terraform');
    const archive = path.join(published, 'signalops-terraform.tar.gz');
    assert.ok(fs.existsSync(archive), 'Run make build-web before checking the downloadable package');
    const files = execFileSync('tar', ['-tzf', path.basename(archive)], { cwd: published, encoding: 'utf8' }).trim().split(/\r?\n/);
    for (const required of [
        'infra/main.tf', 'infra/variables.tf', 'infra/LICENSE',
        'infra/agent.tf', 'infra/scripts/Build-Images.ps1', 'infra/scripts/Complete-Lab.ps1',
        'infra/scripts/Get-SignalOpsContext.ps1', 'infra/config/handler.json',
        'infra/apps/grubify/grubify-frontend/nginx.conf',
        'infra/apps/grubify/grubify-frontend/public/manifest.json',
        'infra/apps/parking-manager/backend/shared/chaosMiddleware.js',
        'infra/apps/parking-manager/backend/madrid-parking-api/server.js',
        'infra/apps/parking-manager/backend/paris-parking-api/package-lock.json',
        'infra/modules/workload/main.tf',
        'infra/modules/workload/templates/demo-lab-web-cloud-init.yaml',
        'infra/modules/workload/templates/demo-lab-client-cloud-init.yaml',
        'infra/modules/workload/templates/demo-lab-nva-cloud-init.yaml'
    ]) {
        assert.ok(files.includes(required), required);
        assert.ok(fs.existsSync(path.join(published, required)), required);
    }
    for (const file of files) {
        assert.doesNotMatch(file, /(?:^|\/)(?:\.terraform|node_modules|bin|obj|build|dist|\.azure|\.env)(?:\/|\.|$)|\.tfstate|\.tfvars|\.tfplan|\.(?:pfx|pem|key|crt)$|(?:^|\/)(?:.*_)?override\.tf/);
        assert.match(file, /^infra\//);
    }
    const manifest = JSON.parse(fs.readFileSync(path.join(published, 'infra', 'source-manifest.json'), 'utf8'));
    const regularFiles = files.filter(file => !file.endsWith('/') && file !== 'infra/source-manifest.json');
    assert.equal(regularFiles.length, Object.keys(manifest).length);
    for (const [relative, expected] of Object.entries(manifest)) {
        const packaged = fs.readFileSync(path.join(published, 'infra', relative));
        assert.equal(crypto.createHash('sha256').update(packaged).digest('hex'), expected, relative);
        const original = relative.startsWith('apps/')
            ? path.join(root, 'Student', 'Resources', relative.slice(5))
            : ['scripts/Get-SignalOpsContext.ps1', 'scripts/Register-SignalOpsAgent.ps1'].includes(relative)
                ? path.join(track, 'Scripts', path.basename(relative))
                : relative.startsWith('config/')
                    ? path.join(track, 'Config', relative.slice(7))
                : path.join(terraform, relative);
        assert.deepEqual(packaged, fs.readFileSync(original), `${relative} must match its maintained source`);
    }
});

test('Terraform fixes CORS, explicit NVA egress, and all seven private image pulls', () => {
    const workload = path.join(terraform, 'modules', 'workload');
    const food = fs.readFileSync(path.join(workload, 'sample-food-containerapps.tf'), 'utf8');
    assert.match(food, /AllowedOrigins__0[\s\S]*?local\.sample_food_names\.frontend_container_app[\s\S]*?sample_food\.default_domain/);
    assert.doesNotMatch(food, /placeholder\.invalid|ignore_changes/);
    const parking = fs.readFileSync(path.join(workload, 'parking-apps.tf'), 'utf8');
    assert.equal((`${food}\n${parking}`.match(/registry\s*\{/g) || []).length, 7);
    assert.equal((parking.match(/SystemAssigned, UserAssigned/g) || []).length, 5);
    const network = fs.readFileSync(path.join(workload, 'network.tf'), 'utf8');
    assert.match(network, /resource "azurerm_route" "hub_nva_default_egress"[\s\S]*?address_prefix\s*=\s*"0\.0\.0\.0\/0"[\s\S]*?azurerm_firewall\.hub/);
    assert.match(network, /resource "azurerm_subnet_route_table_association" "hub_nva_egress"/);
    const compute = fs.readFileSync(path.join(workload, 'compute.tf'), 'utf8');
    assert.match(compute, /azurerm_route\.hub_nva_default_egress/);
    assert.match(compute, /azurerm_subnet_route_table_association\.hub_nva_egress/);
    for (const file of fs.readdirSync(workload).filter(name => name.endsWith('.tf'))) {
        assert.doesNotMatch(fs.readFileSync(path.join(workload, file), 'utf8'), /frontier-sre-agent-rvas|dm-chelupati|placeholder\.invalid/);
    }
    const variables = fs.readFileSync(path.join(terraform, 'variables.tf'), 'utf8');
    assert.match(variables, /@sha256:/);
});

test('agent configuration is self-contained and approval gated with usable investigation tools', () => {
    const config = path.join(track, 'Config');
    const handler = JSON.parse(fs.readFileSync(path.join(config, 'handler.json'), 'utf8'));
    const plan = JSON.parse(fs.readFileSync(path.join(config, 'response-plan.json'), 'utf8'));
    assert.equal(plan.properties.handlingAgent, handler.name);
    assert.equal(plan.properties.agentMode, 'Review');
    assert.equal(plan.properties.isEnabled, true);
    assert.deepEqual(plan.properties.priorities, ['Sev0', 'Sev1', 'Sev2', 'Sev3', 'Sev4']);
    assert.equal(plan.properties.titleContains, 'grubify');
    assert.equal(handler.properties.enableSkills, false);
    assert.ok(handler.properties.tools.includes('SearchMemory'));
    assert.ok(handler.properties.tools.includes('QueryLogAnalyticsByWorkspaceId'));
    assert.equal(fs.readdirSync(path.join(config, 'knowledge')).length, 4);
    assert.doesNotMatch(JSON.stringify(handler), /frontier-sre-agent-rvas|dm-chelupati/);
    assert.deepEqual(handler.properties.handoffs, ['network-traffic-analyst']);
    for (const file of ['handler.json', 'network.json', 'cost.json']) {
        const specialist = JSON.parse(fs.readFileSync(path.join(config, file), 'utf8'));
        assert.equal(specialist.properties.agentType, 'Review');
        if (file !== 'handler.json') assert.ok(!specialist.properties.tools.includes('RunAzCliWriteCommands'));
    }
});

test('all operational missions retain required structure and use local configuration', () => {
    for (let number = 1; number <= 12; number++) {
        const name = `Challenge-${String(number).padStart(2, '0')}.md`;
        const text = fs.readFileSync(path.join(track, 'Missions', name), 'utf8').replace(/\r\n/g, '\n');
        let previous = -1;
        for (const section of ['Introduction', 'Description', 'Success Criteria', 'Learning Resources']) {
            const index = text.indexOf(`\n## ${section}\n`);
            assert.ok(index > previous, `${name}: missing or out-of-order ${section}`);
            previous = index;
        }
        assert.match(text.split('\n')[0], /\*\*\[Home\]/);
        const criteria = text.split('## Success Criteria')[1].split('\n## ')[0];
        assert.match(criteria, /Explain to your coach/);
        assert.ok((criteria.match(/^- \[ \]/gm) || []).length >= 3, name);
        const resources = text.split('## Learning Resources')[1].split('\n## ')[0];
        assert.ok((resources.match(/\]\(https:\/\/learn\.microsoft\.com/g) || []).length >= 3, name);
        assert.doesNotMatch(text, /frontier-sre-agent-rvas|dm-chelupati|Student[\\/]Resources[\\/]azure-sre-agent-config|source scenario|Start-Process \$AGENT/);
        const blocks = [...text.matchAll(/^```powershell\s*\r?\n([\s\S]*?)^```/gm)].map(match => match[1]);
        assert.ok(blocks.every(block => !block.includes('Authorization: ******')), name);
    }
    const hook = fs.readFileSync(path.join(track, 'azure.yaml'), 'utf8');
    assert.match(hook, /DEPLOY_CONNECTORS[\s\S]*Register-SignalOpsAgent\.ps1/);
    const mission10 = fs.readFileSync(path.join(track, 'Missions', 'Challenge-08.md'), 'utf8');
    assert.doesNotMatch(mission10, /alert-signalopscore|title text `food`|`Sev1` and title/);
    const mission14 = fs.readFileSync(path.join(track, 'Missions', 'Challenge-12.md'), 'utf8');
    assert.doesNotMatch(mission14, /at least three/i);
    assert.match(mission14, /Zero issues or fewer than three/);
    const board = JSON.parse(loadBoard().evaluate('JSON.stringify(missions)'));
    for (const number of ['07', '12']) {
        const title = board.find(mission => mission[0] === number)[2];
        assert.ok(fs.readFileSync(path.join(track, 'Missions', `Challenge-${number}.md`), 'utf8').includes(` — ${title}`));
        for (const relative of ['README.md', 'Missions/README.md', 'Coach/README.md']) {
            assert.ok(fs.readFileSync(path.join(track, relative), 'utf8').includes(title), relative);
        }
    }
});

test('backup integration is separate from core and requires explicit operator inputs', () => {
    const core = fs.readFileSync(path.join(track, 'infra', 'main.bicep'), 'utf8');
    assert.doesNotMatch(core, /vm-backup\.bicep|backup-approval-gate\.bicep|teamsGroupId|backupVmResourceGroup/);
    const addon = fs.readFileSync(path.join(track, 'infra', 'backup.bicep'), 'utf8');
    for (const parameter of ['teamsGroupId', 'teamsChannelId', 'backupVmResourceGroup', 'backupVmName', 'logAnalyticsWorkspaceName', 'applicationInsightsName']) {
        assert.match(addon, new RegExp(`param ${parameter} string\\r?\\n`));
    }
    const coach = fs.readFileSync(path.join(track, 'Coach', 'Missions', 'Solution-07.md'), 'utf8');
    assert.doesNotMatch(coach, /b1e100ca|rg-signalopscore|3d89f679|azd up/);
    assert.match(coach, /--config "\$backup_config"/);
    assert.match(coach, /dotnet publish/);
    assert.doesNotMatch(fs.readFileSync(path.join(track, 'azure.yaml'), 'utf8'), /host: function/);
});

test('mission examples and presenter wrappers pass mocked behavior and scope checks', () => {
    const result = execFileSync('pwsh', ['-NoProfile', '-NonInteractive', '-File', path.join(__dirname, 'signalops-missions.tests.ps1')], {
        cwd: root, encoding: 'utf8', maxBuffer: 1024 * 1024
    });
    assert.match(result, /Offline mission behavior checks passed/);
});

function powershell(command) {
    return execFileSync('pwsh', ['-NoProfile', '-NonInteractive', '-Command', command], {
        cwd: root, encoding: 'utf8', maxBuffer: 1024 * 1024
    });
}

test('Bicep presenter guards accept only the selected environment subscription', () => {
    const result = powershell(`
        $ErrorActionPreference = 'Stop'
        $tokens = $null; $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            (Resolve-Path '.\\SRE SignalOps\\Scripts\\Invoke-SignalOpsDemo.ps1').Path,
            [ref]$tokens, [ref]$errors)
        if ($errors) { throw ($errors | Out-String) }
        $functions = $ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -in @('Invoke-Native', 'Assert-AzdSubscription')
        }, $false)
        foreach ($definition in $functions) { . ([scriptblock]::Create($definition.Extent.Text)) }
        $script:Target = 'subscription-a'
        $script:NativeExit = 0
        function az { $global:LASTEXITCODE = 0; 'subscription-a' }
        function azd { $global:LASTEXITCODE = $script:NativeExit; $script:Target }
        Assert-AzdSubscription
        $script:Target = 'subscription-b'
        $rejected = $false
        try { Assert-AzdSubscription } catch {
            if ($_.Exception.Message -notmatch 'do not match') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'Cross-subscription deployment was not rejected.' }
        $script:Target = ''
        $rejected = $false
        try { Assert-AzdSubscription } catch {
            if ($_.Exception.Message -notmatch 'do not match') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'An empty environment subscription was not rejected.' }
        $script:NativeExit = 7
        $rejected = $false
        try { Assert-AzdSubscription } catch {
            if ($_.Exception.Message -notmatch 'exit code 7') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'A failed environment lookup was not rejected.' }
        'Bicep environment guard checks passed.'
    `);
    assert.match(result, /Bicep environment guard checks passed/);
    const runner = fs.readFileSync(path.join(track, 'Scripts', 'Invoke-SignalOpsDemo.ps1'), 'utf8');
    assert.equal((runner.match(/^\s+Assert-AzdSubscription$/gm) || []).length, 3);
    assert.doesNotMatch(runner, /MCAPS|ca-food-frontend|frontier-sre-agent-rvas/);
    assert.match(runner, /Get-AzdValue 'FRONTEND_URL'/);
});

test('PowerShell automation parses and dry-run modes perform no Azure operations', () => {
    powershell(`
        $ErrorActionPreference = 'Stop'
        $files = @(Get-ChildItem -LiteralPath '.\\SRE SignalOps\\Deployment\\Terraform\\infra\\scripts' -Filter '*.ps1' -Recurse)
        $files += Get-ChildItem -LiteralPath '.\\SRE SignalOps\\Scripts' -Filter '*.ps1'
        foreach ($file in $files) {
            $tokens = $null; $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            if ($errors) { throw ($errors | Out-String) }
        }
    `);
    const images = JSON.parse(powershell("& '.\\SRE SignalOps\\Deployment\\Terraform\\infra\\scripts\\Build-Images.ps1' -RegistryName signalopstest -RegistryResourceGroup rg-test -PlanOnly"));
    assert.equal(images.length, 7);
    assert.equal(new Set(images.map(image => image.Key)).size, 7);
    const result = JSON.parse(powershell("& '.\\SRE SignalOps\\Deployment\\Terraform\\infra\\scripts\\Complete-Lab.ps1' -ValidateOnly"));
    assert.equal(result.AzureOperations, 0);
    assert.equal(result.Mode, 'Review');
    assert.equal(result.KnowledgeFiles.length, 4);
});

test('VM payloads preserve server/shared layout and JavaScript is syntactically valid', () => {
    const payloads = JSON.parse(powershell(`
        . '.\\SRE SignalOps\\Deployment\\Terraform\\infra\\scripts\\Common.ps1'
        @{ madrid = (New-LabVmPayload madrid); paris = (New-LabVmPayload paris) } | ConvertTo-Json -Compress
    `));
    for (const city of ['madrid', 'paris']) {
        const files = JSON.parse(zlib.gunzipSync(Buffer.from(payloads[city], 'base64')).toString('utf8'));
        for (const required of [`${city}-parking-api/server.js`, `${city}-parking-api/package-lock.json`, 'shared/chaosMiddleware.js']) {
            const file = files.find(entry => entry.path === required);
            assert.ok(file, required);
            assert.deepEqual(Buffer.from(file.content, 'base64'),
                fs.readFileSync(path.join(root, 'Student', 'Resources', 'parking-manager', 'backend', required)));
        }
        assert.ok(files.every(file => !/\.env|\.pfx|node_modules/.test(file.path)));
    }
    const packagedBackend = path.join(root, '_site', 'sre-signalops', 'Deployment', 'Terraform', 'infra', 'apps', 'parking-manager', 'backend');
    for (const directory of fs.readdirSync(packagedBackend)) {
        for (const file of fs.readdirSync(path.join(packagedBackend, directory)).filter(name => name.endsWith('.js'))) {
            execFileSync(process.execPath, ['--check', path.join(packagedBackend, directory, file)]);
        }
    }
    const bash = process.platform === 'win32' ? 'C:\\Program Files\\Git\\bin\\bash.exe' : 'bash';
    execFileSync(bash, ['-n', path.join(terraform, 'scripts', 'templates', 'install-paris.sh')]);
});

test('missions use explicit deployment context rather than copied live resource names', () => {
    for (const number of ['01', '02', '03', '04', '05', '06', '08']) {
        const guide = fs.readFileSync(path.join(track, 'Missions', `Challenge-${number}.md`), 'utf8');
        assert.doesNotMatch(guide, /azd env get-value|b1e100ca-fff5-4e0e-9847-2e44bf47b68c|edc738c9/);
        assert.match(guide, /\$Lab\./);
    }
});

test('image build, completion, and both deployment contexts pass mocked behavior and failure checks', () => {
    const output = execFileSync('pwsh', ['-NoProfile', '-NonInteractive', '-File', path.join(__dirname, 'signalops-automation.tests.ps1')], {
        cwd: root, encoding: 'utf8', maxBuffer: 1024 * 1024
    });
    assert.match(output, /Offline automation behavior checks passed/);
});
