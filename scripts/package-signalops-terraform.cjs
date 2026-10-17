const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.resolve(__dirname, '..');
const deployment = path.join(root, 'SRE SignalOps', 'Deployment', 'Terraform', 'infra');
const resources = path.join(root, 'Student', 'Resources');
const defaultDestination = path.join(root, '_site', 'sre-signalops', 'Deployment', 'Terraform', 'infra');
const skippedDirectories = new Set(['node_modules', 'bin', 'obj', 'build', 'dist', 'coverage', '.git', '.azure', '.terraform', 'logs']);
const sourceExtension = /\.(?:cs|csproj|js|jsx|cjs|mjs|ts|tsx|css|html|conf|sh|svg|png|jpe?g|gif|ico|webp|woff2?|ttf|txt)$/i;

function packageTerraform(destination = defaultDestination) {
    const manifest = {};
    function copy(source, relative) {
        if (!fs.lstatSync(source).isFile()) throw new Error(`Expected a regular source file: ${source}`);
        const target = path.join(destination, relative);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.copyFileSync(source, target);
        manifest[relative.split(path.sep).join('/')] = crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex');
    }
    function walk(source, relative, accept) {
        for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
            if (entry.isSymbolicLink()) throw new Error(`Source symlinks are not publishable: ${entry.name}`);
            if (entry.isDirectory()) {
                if (!skippedDirectories.has(entry.name)) walk(path.join(source, entry.name), path.join(relative, entry.name), accept);
            } else if (entry.isFile() && accept(entry.name)) {
                copy(path.join(source, entry.name), path.join(relative, entry.name));
            }
        }
    }
    for (const name of ['main.tf', 'agent.tf', 'variables.tf', 'outputs.tf', 'providers.tf', 'terraform.tf', 'LICENSE', '.gitignore']) {
        copy(path.join(deployment, name), name);
    }
    walk(path.join(deployment, 'modules', 'workload'), path.join('modules', 'workload'),
        name => (/\.tf$/.test(name) && !/(?:^|_)override\.tf$/.test(name)) || /\.yaml$/.test(name));
    walk(path.join(deployment, 'scripts'), 'scripts', name => /\.(?:ps1|sh)$/.test(name));
    copy(path.join(root, 'SRE SignalOps', 'Scripts', 'Get-SignalOpsContext.ps1'), path.join('scripts', 'Get-SignalOpsContext.ps1'));
    copy(path.join(root, 'SRE SignalOps', 'Scripts', 'Register-SignalOpsAgent.ps1'), path.join('scripts', 'Register-SignalOpsAgent.ps1'));
    walk(path.join(root, 'SRE SignalOps', 'Config'), 'config', name => /\.(?:json|md)$/.test(name));
    walk(path.join(deployment, 'tests'), 'tests', name => /\.tftest\.hcl$/.test(name));

    const applicationDirectories = [
        'grubify/GrubifyApi', 'grubify/grubify-frontend',
        ...['lisbon-parking-api', 'berlin-parking-api', 'berlin-mcp-server', 'chaos-control',
            'vm-health-control', 'madrid-parking-api', 'paris-parking-api', 'shared']
            .map(name => `parking-manager/backend/${name}`)
    ];
    for (const directory of applicationDirectories) {
        walk(path.join(resources, ...directory.split('/')), path.join('apps', ...directory.split('/')),
            name => sourceExtension.test(name) || /^(?:Dockerfile|\.dockerignore|package(?:-lock)?\.json|appsettings\.json|tsconfig\.json|manifest\.json)$/.test(name));
    }
    fs.writeFileSync(path.join(destination, 'source-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
    return manifest;
}

if (require.main === module) {
    const manifest = packageTerraform();
    console.log(`Packaged ${Object.keys(manifest).length} curated Terraform and application source files.`);
}
module.exports = { packageTerraform };
