# Evidence collection and analysis

## Collection

### 1. Enumerate approved vaults and certificate metadata

Repeat certificate reads for every certificate in each approved vault. Follow ARG skip_token and certificate continuation pages, retaining id in ARG projections; verify $SUB belongs to the vault. Do not read backing secrets. Pending operation not found means no retained pending operation, not a successful renewal. Record 403 and network denial separately; retry 429 according to Retry-After.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type =~ 'microsoft.keyvault/vaults' | project id,name,subscriptionId,resourceGroup" --output json
az keyvault certificate list --vault-name $VAULT --subscription $SUB --output json
az keyvault certificate show --vault-name $VAULT --name $CERT --subscription $SUB --query '{id:id,attributes:attributes,policy:policy}' --output json
az keyvault certificate pending show --vault-name $VAULT --name $CERT --subscription $SUB --output json
```

### 2. Write a local renewal and notification draft

Use the declared normalized operator artifact. The commands are saved argument arrays, never executed. Include the selected issuer procedure, current certificate policy, consumer bindings, validation of chain and expiry, and rollback to the previous still valid version. Validate certificate IDs against the approved vault list. External CA create requires an appropriate reviewed Unknown issuer CSR policy, followed by separately approved CA signing and pending merge of a verified public chain; do not send a CSR or invoke a CA automatically. Failure remains reportable even when expiry is unavailable.

```python
import json,re
from pathlib import Path
from datetime import datetime
rows=json.loads(Path('certificate-evidence.json').read_text(encoding='utf-8'))
plans=[]
for i,r in enumerate(rows):
    expiry=r.get('expires_at')
    days=(datetime.fromisoformat(expiry.replace('Z','+00:00'))-datetime.fromisoformat(r['assessed_at'].replace('Z','+00:00'))).total_seconds()/86400 if expiry else None
    if not (r.get('renewal_failed') or (days is not None and days < 30)): continue
    argv=None; merge=None; blocked=None
    if r.get('reviewed_policy') and r.get('issuer_type') in ('integrated','self_signed','external'):
        assert re.fullmatch(r'[A-Za-z0-9-]+',r['vault_name']) and re.fullmatch(r'[A-Za-z0-9-]+',r['certificate_name'])
        file='renewal-policy-'+str(i)+'.json'
        Path(file).write_text(json.dumps(r['reviewed_policy'],indent=2),encoding='utf-8')
        argv=['az','keyvault','certificate','create','--vault-name',r['vault_name'],'--name',r['certificate_name'],'--policy','@'+file]
        if r['issuer_type']=='external' and r.get('approved_signed_certificate_file'):
            merge=['az','keyvault','certificate','pending','merge','--vault-name',r['vault_name'],'--name',r['certificate_name'],'--file',r['approved_signed_certificate_file']]
    else: blocked='Issuer procedure or reviewed policy missing; owner review required'
    plans.append({'certificate_id':r['certificate_id'],'days_remaining':days,'issuer_type':r.get('issuer_type'),'owner_alias':r.get('owner_alias'),'auto_renewal_viable':r.get('auto_renewal_viable'),'create_command_argv':argv,'external_merge_command_argv':merge,'blocked_reason':blocked,'unsent_notice':'Certificate renewal review requested. Validate issuer path, consumer version rollover and rollback before expiry.','execute':False,'requires_approval':True,'applied':False})
Path('renewal-plan.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
```

## Analysis rules

1. Derive subject and issuer from certificate policy and public certificate metadata, and compute expiry from attributes.expires. Preserve null expiry and do not interpret disabled certificates as safely retired without owner confirmation.
2. Inspect lifetimeActions for AutoRenew versus EmailContacts and issuer configuration. An AutoRenew entry alone does not prove the CA integration or consumer version rollover works.
3. Flag certificates with fewer than 30 days remaining without a viable renewal path. Include existing pending operation status and error, or supplied CA failure notices, as renewal failure evidence.
4. Validate the draft against issuer type and consumer rebinding needs. Require separate approval to create a certificate version, merge a signed certificate, change lifetime policy, contact a CA or notify an owner.

## Known limits

- Pending operation metadata is not a complete renewal attempt history.
- Vault firewall or certificate data plane denial leaves renewal status unassessed; Activity Log does not reveal certificate private key or secret reads.

## Expected validation cases

- Healthy: valid certificate has a supported issuer, AutoRenew action and a recent successful version rollover.
- Finding: certificate expires in 12 days with EmailContacts only; generate a local renewal plan, no tenant changes.
- Denied or missing: pending operation read denied means renewal failure is null, not false.

## Sources

- [Key Vault certificate renewal](https://learn.microsoft.com/en-us/azure/key-vault/certificates/overview-renew-certificate) (consulted 2026-10-21).
- [Pending certificate operations](https://learn.microsoft.com/en-us/cli/azure/keyvault/certificate/pending?view=azure-cli-latest) (consulted 2026-10-21).
