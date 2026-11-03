#!/usr/bin/env bash
# Tests for usecases.sh. Run: usecases/_framework/tests/run.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SH="$HERE/../usecases.sh"
FX="$HERE/fixtures"
pass=0; fail=0
start=$(date +%s)

check() { # name, command...
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then pass=$((pass + 1)); echo "ok   $name"; else fail=$((fail + 1)); echo "FAIL $name"; fi
}
fails() { ! "$@"; }

check "valid fixtures validate" "$SH" --root "$FX/valid" validate
for c in id-mismatch unknown-domain built-no-products bad-tool-schema missing-status status-mismatch validated-no-tests idea-with-components tool-only domain-mismatch bad-package; do
  check "invalid: $c fails" fails "$SH" --root "$FX/invalid/$c" validate
done

# Failure messages name the folder and the rule.
out="$("$SH" --root "$FX/invalid/id-mismatch" validate 2>&1)"
check "id-mismatch message names folder and rule" grep -q 'FAIL \[some-folder\] id "other-id" must equal' <<<"$out"
out="$("$SH" --root "$FX/invalid/built-no-products" validate 2>&1)"
check "built-no-products message" grep -q 'built use case requires products' <<<"$out"

out="$("$SH" --root "$FX/invalid/status-mismatch" validate 2>&1)"
check "status-mismatch message" grep -q 'status "validated" does not match the files (they support "idea")' <<<"$out"
out="$("$SH" --root "$FX/invalid/missing-status" validate 2>&1)"
check "missing-status message" grep -q 'missing required field: status' <<<"$out"

out="$("$SH" --root "$FX/invalid/validated-no-tests" validate 2>&1)"
check "validated-no-tests message" grep -q 'status "validated" does not match the files (they support "built")' <<<"$out"
out="$("$SH" --root "$FX/invalid/idea-with-components" validate 2>&1)"
check "idea-with-components message" grep -q 'status "idea" does not match the files (they support "built")' <<<"$out"
out="$("$SH" --root "$FX/invalid/tool-only" validate 2>&1)"
check "tool-only message" grep -q 'a tool needs a skill or a subagent' <<<"$out"

out="$("$SH" --root "$FX/invalid/domain-mismatch" validate 2>&1)"
check "domain-mismatch message" grep -q 'domain "management" must equal the parent folder "security"' <<<"$out"

# Index: declared status and derived components.
json="$("$SH" --root "$FX/valid" index)"
check "index count is 3" jq -e '.count == 3' <<<"$json"
check "validated status exposed" jq -e '.usecases[] | select(.id=="validated-fixture") | .status=="validated" and (has("maturity") | not)' <<<"$json"
check "idea status exposed" jq -e '.usecases[] | select(.id=="idea-fixture") | .status=="idea"' <<<"$json"
check "components detected" jq -e '.usecases[] | select(.id=="validated-fixture") | .components | .skill and .subagent and .task and .permissions and .tests and .sampleReport and (.tool=="generate-fixture.py")' <<<"$json"
check "domains listed" jq -e '(.domains | length) == 8' <<<"$json"
check "grant GUID is not a failure" "$SH" --root "$FX/valid" validate

# new scaffolds a valid folder and refuses to overwrite.
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
check "new creates a folder" "$SH" --root "$tmp" new management my-case
check "new rejects an unknown domain" fails "$SH" --root "$tmp" new nope other-case
check "new rejects an id used in another domain" fails "$SH" --root "$tmp" new security my-case
check "new output validates" "$SH" --root "$tmp" validate
check "new refuses overwrite" fails "$SH" --root "$tmp" new management my-case
check "new sets domain" grep -q '^domain: management$' "$tmp/management/my-case/usecase.yaml"
check "index path includes the domain" jq -e '.usecases[] | select(.id=="validated-fixture") | .path | endswith("/identity-access/validated-fixture")' <<<"$json"
check "new sets id" grep -q '^id: my-case$' "$tmp/management/my-case/usecase.yaml"

# portal-blocks and deploy dry-run.
out="$("$SH" --root "$FX/valid" portal-blocks validated-fixture 2>&1)"
check "portal-blocks prints the task" grep -q 'Scheduled task: monthly-task-prompt.md' <<<"$out"
out="$("$SH" --root "$FX/valid" portal-blocks idea-fixture 2>&1)"
check "portal-blocks reports missing components" grep -q 'Not present' <<<"$out"
out="$("$SH" --root "$FX/valid" deploy validated-fixture --endpoint https://example.test --dry-run 2>&1)"
check "deploy dry-run puts tool, skill, agent" bash -c "grep -q 'tools/fixture' <<<\"\$1\" && grep -q 'skills/validated-fixture' <<<\"\$1\" && grep -q 'agents/validated-fixture' <<<\"\$1\"" _ "$out"

out="$("$SH" --root "$FX/invalid/bad-package" validate 2>&1)"
check "bad-package version message" grep -q 'package: version must look like 1.2.3' <<<"$out"
check "bad-package apiVersion message" grep -q 'package: apiVersion must be' <<<"$out"
check "bad-package missing contents message" grep -q 'does not exist' <<<"$out"

# manifests/ layout from the template deploys, and diff/verify work against a stubbed API.
out="$("$SH" --root "$tmp" deploy my-case --endpoint https://example.test --dry-run 2>&1)"
check "manifests layout deploys" bash -c "grep -q 'tools/example' <<<\"\$1\" && grep -q 'skills/example' <<<\"\$1\" && grep -q 'scheduledtasks/example-monthly-check' <<<\"\$1\"" _ "$out"
bin="$tmp/bin"; mkdir -p "$bin"
printf '#!/usr/bin/env bash\necho token\n' >"$bin/az"
cat >"$bin/curl" <<'STUB'
#!/usr/bin/env bash
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2 ;; http*) url="$1"; shift ;; *) shift ;; esac; done
case "$url" in
  */skills/example) body='{"properties":{"description":"stale"}}'; code=200 ;;
  */skills|*/agents|*/tools) body='[{"name":"example"}]'; code=200 ;;
  */scheduledtasks) body='[{"name":"example-monthly-check"}]'; code=200 ;;
  *) body='{}'; code=404 ;;
esac
if [ -n "$out" ]; then printf '%s' "$body" >"$out"; printf '%s' "$code"; else printf '%s' "$body"; fi
STUB
chmod +x "$bin/az" "$bin/curl"
out="$(PATH="$bin:$PATH" "$SH" --root "$tmp" diff my-case --endpoint https://example.test 2>&1)"
check "diff reports changed and new" bash -c "grep -q 'CHANGED skills/example' <<<\"\$1\" && grep -q 'NEW     tools/example' <<<\"\$1\"" _ "$out"
sed -i 's/^skills: .*/skills: [example]/' "$tmp/management/my-case/tests/expected-config.yaml"
check "verify passes when resources exist" env PATH="$bin:$PATH" "$SH" --root "$tmp" verify my-case --endpoint https://example.test
sed -i 's/^skills: .*/skills: [other]/' "$tmp/management/my-case/tests/expected-config.yaml"
check "verify fails when a resource is missing" fails env PATH="$bin:$PATH" "$SH" --root "$tmp" verify my-case --endpoint https://example.test

out="$("$SH" deploy databricks-dependency-configuration-review --endpoint https://example.test --dry-run 2>&1)"
check "tool code_file is inlined as functionCode" bash -c "grep -q 'tools/generate-databricks-dependency-report.*functionCode' <<<\"\$1\" && ! grep -q 'code_file' <<<\"\$1\"" _ "$out"

echo "elapsed: $(( $(date +%s) - start ))s; passed $pass, failed $fail"
[ "$fail" -eq 0 ]
