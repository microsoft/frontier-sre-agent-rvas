#!/usr/bin/env bash
# Build tooling for the use-case framework. See usecases/README.md.
#
#   usecases.sh [--root DIR] validate
#   usecases.sh [--root DIR] index [-o FILE] [--readme]
#   usecases.sh [--root DIR] portal-blocks <id|path> [-o FILE]
#   usecases.sh [--root DIR] new <domain> <slug>   (creates the next NNNN-<slug> folder)
#   usecases.sh [--root DIR] deploy <id|path> --endpoint URL [--subscription ID] [--dry-run]
#   usecases.sh [--root DIR] diff <id|path> --endpoint URL [--subscription ID]
#   usecases.sh [--root DIR] verify <id|path> --endpoint URL [--subscription ID]
#
# Requires: bash, jq, python3 with PyYAML (or yq) for YAML parsing.
set -uo pipefail

FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_USECASES="$(cd "$FRAMEWORK_DIR/.." && pwd)"
TAXONOMY="$FRAMEWORK_DIR/taxonomy.yaml"
ROOT="${USECASES_ROOT:-$REPO_USECASES}"

README_START='<!-- usecases:index:start -->'
README_END='<!-- usecases:index:end -->'

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"; }

# Converts YAML files to one JSON object keyed by file path. One process for all files.
yaml_to_json() {
  if python3 -c 'import yaml' 2>/dev/null; then
    python3 - "$@" <<'PY'
import json, sys, yaml
out = {}
for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as f:
            out[path] = {"data": yaml.safe_load(f)}
    except Exception as e:
        out[path] = {"error": str(e).splitlines()[0]}
json.dump(out, sys.stdout)
PY
  elif command -v yq >/dev/null 2>&1; then
    local first=1 p
    printf '{'
    for p in "$@"; do
      [ $first -eq 1 ] || printf ','
      first=0
      printf '%s:' "$(jq -Rn --arg p "$p" '$p')"
      if d="$(yq -o=json '.' "$p" 2>&1)"; then printf '{"data":%s}' "$d"
      else printf '{"error":%s}' "$(jq -Rn --arg e "$d" '$e')"; fi
    done
    printf '}'
  else
    die "need python3 with PyYAML, or yq, to parse YAML"
  fi
}

# Use cases live at ROOT/<NNNN-slug>. Names that start with "_" are skipped.
folders() {
  local d
  for d in "$ROOT"/*/; do
    d="${d%/}"
    case "$(basename "$d")" in _*) continue ;; esac
    echo "$d"
  done
}

has_glob() { compgen -G "$1" >/dev/null; }

# Package layout keeps deployable files under manifests/; older use cases keep them at the folder root.
base_dir() { if [ -d "$1/manifests" ]; then echo "$1/manifests"; else echo "$1"; fi; }

# Prints a JSON object describing the components found in a folder.
components_json() {
  local d="$1" b readme=false skill=false skillCount=0 sub=false tool="" schema=false task=false perm=false tests=false sample=false images=false s
  b="$(base_dir "$d")"
  if [ "$b" != "$d" ]; then
    [ -f "$d/README.md" ] && readme=true
    for s in "$b"/skills/*/SKILL.md; do [ -f "$s" ] && { skill=true; skillCount=$((skillCount + 1)); }; done
    has_glob "$b/subagents/*.yaml" && sub=true
    for s in "$b"/tools/*.yaml; do [ -f "$s" ] && { tool="$(basename "$s")"; break; }; done
    has_glob "$b/scheduled-tasks/*.yaml" && task=true
    has_glob "$d/permissions/grant-*" && perm=true
    [ -d "$d/tests" ] && tests=true
    [ -d "$d/sample-report" ] && sample=true
    [ -d "$d/images" ] && images=true
    jq -n --argjson skill "$skill" --argjson skillCount "$skillCount" --argjson sub "$sub" \
      --arg tool "$tool" --argjson task "$task" --argjson perm "$perm" \
      --argjson tests "$tests" --argjson sample "$sample" --argjson images "$images" --argjson readme "$readme" \
      '{readme:$readme, skill:$skill, skillCount:$skillCount, subagent:$sub, tool:(if $tool=="" then false else $tool end),
        toolSchema:false, task:$task, permissions:$perm, tests:$tests, sampleReport:$sample, images:$images, package:true}'
    return
  fi
  [ -f "$d/README.md" ] && readme=true
  [ -f "$b/SKILL.md" ] && { skill=true; skillCount=$((skillCount + 1)); }
  for s in "$b"/skills/*/SKILL.md; do [ -f "$s" ] && { skill=true; skillCount=$((skillCount + 1)); }; done
  [ -f "$b/subagent-instructions-and-prompts.md" ] && sub=true
  for s in "$b"/generate-*.py; do [ -f "$s" ] && { tool="$(basename "$s")"; break; }; done
  [ -f "$b/tool-parameters.schema.json" ] && schema=true
  has_glob "$b/*-task-prompt.md" && task=true
  has_glob "$b/grant-*" && perm=true
  [ -d "$d/tests" ] && tests=true
  [ -d "$d/sample-report" ] && sample=true
  [ -d "$d/images" ] && images=true
  jq -n --argjson skill "$skill" --argjson skillCount "$skillCount" --argjson sub "$sub" \
    --arg tool "$tool" --argjson schema "$schema" --argjson task "$task" --argjson perm "$perm" \
    --argjson tests "$tests" --argjson sample "$sample" --argjson images "$images" --argjson readme "$readme" \
    '{readme:$readme, skill:$skill, skillCount:$skillCount, subagent:$sub, tool:(if $tool=="" then false else $tool end),
      toolSchema:$schema, task:$task, permissions:$perm, tests:$tests, sampleReport:$sample, images:$images}'
}

maturity_of() {
  jq -r 'if (.skill or .subagent) then (if (.tests and .sampleReport) then "validated" else "built" end) else "idea" end' <<<"$1"
}

# Rules -----------------------------------------------------------------------

rule_fail() { echo "FAIL [$1] $2"; FAILS=$((FAILS + 1)); }
rule_warn() { echo "WARN [$1] $2"; }

rule_fields() { # folder, yaml-entry-json, taxonomy-json, components-json
  local f="$1" y="$2" t="$3" c="$4" msg m
  [[ "$f" =~ ^[0-9]{4}-[a-z0-9][a-z0-9-]*$ ]] || rule_fail "$f" "folder name must be <NNNN>-<slug>, for example 0001-my-use-case"
  m="$(maturity_of "$c")"
  if jq -e 'has("error")' >/dev/null <<<"$y"; then
    rule_fail "$f" "usecase.yaml is not valid YAML: $(jq -r '.error' <<<"$y")"; return
  fi
  local data; data="$(jq -c '.data // {}' <<<"$y")"
  if ! jq -e 'type == "object"' >/dev/null <<<"$data"; then rule_fail "$f" "usecase.yaml must be a mapping"; return; fi
  while IFS= read -r msg; do [ -n "$msg" ] && rule_fail "$f" "$msg"; done < <(
    jq -r --arg f "$f" --argjson t "$t" --argjson c "$c" --arg m "$m" '
      def missing($k): (.[$k] == null or .[$k] == "" or .[$k] == []);
      (if missing("id") then "missing required field: id"
       elif .id != $f then "id \"\(.id)\" must equal the folder name \"\($f)\"" else empty end),
      (["title","summary","domain","trigger","status"][] as $k | select(missing($k)) | "missing required field: \($k)"),
      (.domain as $v | if $v != null and (($t.domain | has($v)) | not) then "domain \"\($v)\" is not in taxonomy" else empty end),
      (if .trigger != null then
         (if (.trigger | type) != "array" then "trigger must be a list"
          else (.trigger[] | select(. as $v | ($t.trigger | index($v)) == null) | "trigger \"\(.)\" is not in taxonomy") end)
       else empty end),
      (.status as $v | if $v != null and (($t.status | index($v)) == null) then "status \"\($v)\" is not in taxonomy"
         elif $v != null and $v != $m then "status \"\($v)\" does not match the files (they support \"\($m)\")" else empty end),
      (.autonomy as $v | if $v != null and (($t.autonomy | index($v)) == null) then "autonomy \"\($v)\" is not in taxonomy" else empty end),
      (.timeSaved as $v | if $v != null and (($t.timeSaved | index($v)) == null) then "timeSaved \"\($v)\" is not in taxonomy" else empty end),
      (.source.type? as $v | if $v != null and (($t.sourceType | index($v)) == null) then "source.type \"\($v)\" is not in taxonomy" else empty end),
      (if ($c.skill or $c.subagent) or .status == "built" or .status == "validated" then
         ((if missing("products") then "built use case requires products" else empty end),
          (if missing("autonomy") then "built use case requires autonomy" else empty end))
       else empty end)
    ' <<<"$data"
  )
}

rule_components() { # folder, dir, components-json
  local f="$1" d="$2" c="$3" b
  b="$(base_dir "$d")"
  if [ "$b" != "$d" ]; then
    jq -e '.skillCount > 5' >/dev/null <<<"$c" && rule_fail "$f" "more than 5 skills (SRE Agent allows 5 active skills per agent)"
    return
  fi
  if [ -f "$b/tool-parameters.schema.json" ]; then
    jq -e . "$b/tool-parameters.schema.json" >/dev/null 2>&1 || rule_fail "$f" "tool-parameters.schema.json is not valid JSON"
  fi
  jq -e '.tool != false and (.toolSchema | not)' >/dev/null <<<"$c" && rule_fail "$f" "generate-*.py needs tool-parameters.schema.json"
  jq -e '.tool == false and .toolSchema' >/dev/null <<<"$c" && rule_fail "$f" "tool-parameters.schema.json needs a generate-*.py tool"
  jq -e '.skillCount > 5' >/dev/null <<<"$c" && rule_fail "$f" "more than 5 skills (SRE Agent allows 5 active skills per agent)"
  if jq -e '.tool != false and ((.skill or .subagent) | not)' >/dev/null <<<"$c"; then
    rule_fail "$f" "a tool needs a skill or a subagent (SKILL.md or subagent-instructions-and-prompts.md)"
  fi
}

# A use case that builds its tool from src/ must keep the checked-in build in sync.
rule_build() { # folder, dir
  [ -f "$2/src/build_tool.py" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  python3 "$2/src/build_tool.py" --check >/dev/null 2>&1 || rule_fail "$1" "built tool is stale; run python3 src/build_tool.py"
}

rule_package() { # folder, dir, yaml-entry-json
  local f="$1" d="$2" y="$3" msg p
  jq -e '.data.package != null' >/dev/null <<<"$y" 2>&1 || return 0
  while IFS= read -r msg; do [ -n "$msg" ] && rule_fail "$f" "package: $msg"; done < <(
    jq -r '
      .data.package as $p |
      if ($p | type) != "object" then "must be a mapping" else
        (["version","apiVersion","contents"][] as $k | select($p[$k] == null) | "missing required field: \($k)"),
        ($p.version // empty | select((type != "string") or (test("^[0-9]+\\.[0-9]+\\.[0-9]+$") | not)) | "version must look like 1.2.3"),
        ($p.apiVersion // empty | select(. != "azuresre.ai/v1" and . != "azuresre.ai/v2") | "apiVersion must be azuresre.ai/v1 or azuresre.ai/v2"),
        ($p | keys[] | select(IN("version","apiVersion","requires","parameters","contents") | not) | "unknown field: \(.)"),
        (($p.contents // {}) | if type != "object" then "contents must be a mapping" else
           (keys[] | select(IN("skills","subagents","tools","scheduledTasks","permissions") | not) | "unknown contents key: \(.)"),
           (to_entries[] | select(.value | type != "array") | "contents.\(.key) must be a list") end)
      end' <<<"$y" 2>/dev/null
  )
  while IFS= read -r p; do
    [ -n "$p" ] && [ ! -e "$d/$p" ] && rule_fail "$f" "package: contents lists \"$p\" but it does not exist"
  done < <(jq -r '(.data.package.contents // {}) | if type == "object" then [.[] | arrays[] | strings] else [] end | .[]' <<<"$y" 2>/dev/null)
}

rule_secrets() { # folder, dir
  local f="$1" d="$2" hit
  while IFS= read -r hit; do
    [ -n "$hit" ] && rule_fail "$f" "possible secret: $hit"
  done < <(grep -rInE --exclude-dir=images --exclude-dir=sample-report \
    -e 'AccountKey=[A-Za-z0-9+/=]{8,}' \
    -e 'client_secret["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9~._-]{8,}' \
    -e '[?&]sig=[A-Za-z0-9%+/=]{20,}' "$d" 2>/dev/null | cut -c1-160 | sed "s#^$d/##")
  while IFS= read -r hit; do
    [ -n "$hit" ] && rule_warn "$f" "GUID outside a grant-* file: $hit"
  done < <(grep -rInE --exclude-dir=images --exclude-dir=sample-report --exclude='grant-*' \
    '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' "$d" 2>/dev/null | cut -c1-120 | sed "s#^$d/##")
}

# Builds the index JSON (without generatedAt) after loading all folders.
build_records() {
  local dirs=() d files=() yj tj recs="[]" f c m y rec
  while IFS= read -r d; do dirs+=("$d"); done < <(folders)
  tj="$(yaml_to_json "$TAXONOMY")" || return 1
  TAXONOMY_JSON="$(jq -c --arg p "$TAXONOMY" '.[$p].data' <<<"$tj")"
  for d in "${dirs[@]}"; do [ -f "$d/usecase.yaml" ] && files+=("$d/usecase.yaml"); done
  if [ ${#files[@]} -gt 0 ]; then yj="$(yaml_to_json "${files[@]}")" || return 1; else yj='{}'; fi
  RECORDS_FILE="$(mktemp)"
  : >"$RECORDS_FILE"
  for d in "${dirs[@]}"; do
    f="$(basename "$d")"
    c="$(components_json "$d")"
    m="$(maturity_of "$c")"
    if [ -f "$d/usecase.yaml" ]; then y="$(jq -c --arg p "$d/usecase.yaml" '.[$p]' <<<"$yj")"
    else y='{"error":"usecase.yaml is missing"}'; fi
    jq -cn --arg f "$f" --arg d "$d" --argjson y "$y" --argjson c "$c" --arg m "$m" \
      '{folder:$f, dir:$d, entry:$y, components:$c, maturity:$m}' >>"$RECORDS_FILE"
  done
}

readme_block() { # reads index JSON on stdin
  jq -r '
    "| ID | Title | Domain | Status |",
    "|----|-------|--------|--------|",
    (.usecases[] | "| [\(.id)](\(.id)/) | \(.title) | \(.domain) | \(.status) |")'
}

# Replaces the marker block in README with $2 (file with block text).
readme_apply() { # readme, blockfile -> prints new content
  awk -v s="$README_START" -v e="$README_END" -v bf="$2" '
    $0 == s { print; while ((getline line < bf) > 0) print line; skip = 1; next }
    $0 == e { skip = 0 }
    !skip { print }' "$1"
}

cmd_validate() {
  need jq
  FAILS=0
  build_records || exit 1
  local count=0 line f d y c seen=""
  while IFS= read -r line; do
    f="$(jq -r .folder <<<"$line")"; d="$(jq -r .dir <<<"$line")"
    y="$(jq -c .entry <<<"$line")"; c="$(jq -c .components <<<"$line")"
    count=$((count + 1))
    rule_fields "$f" "$y" "$TAXONOMY_JSON" "$c"
    rule_components "$f" "$d" "$c"
    rule_package "$f" "$d" "$y"
    rule_build "$f" "$d"
    rule_secrets "$f" "$d"
    local id; id="$(jq -r '.data.id // empty' <<<"$y")"
    if [ -n "$id" ]; then
      case " $seen " in *" $id "*) rule_fail "$f" "duplicate id \"$id\"" ;; esac
      seen="$seen $id"
    fi
  done <"$RECORDS_FILE"

  local readme="$ROOT/README.md"
  if [ "$FAILS" -eq 0 ] && [ -z "${SKIP_README_CHECK:-}" ] && [ -f "$readme" ] && grep -qF "$README_START" "$readme"; then
    local bf; bf="$(mktemp)"
    build_index_json | readme_block >"$bf"
    if ! diff -q <(readme_apply "$readme" "$bf") "$readme" >/dev/null; then
      rule_fail "README.md" "generated index block is stale; run: usecases.sh index --readme"
    fi
    rm -f "$bf"
  fi
  rm -f "$RECORDS_FILE"
  if [ "$FAILS" -gt 0 ]; then echo "validate: $FAILS failure(s) in $count use case(s)"; exit 1; fi
  echo "validate: $count use case(s) OK"
}

build_index_json() {
  jq -s --argjson t "$TAXONOMY_JSON" --arg root "$(basename "$ROOT")" '
    {
      count: length,
      domains: ($t.domain | to_entries | map({slug: .key, label: .value.label, color: .value.color})),
      usecases: (map(
        (.entry.data + {
          path: "\($root)/\(.folder)",
          components: (.components | {skill, subagent, tool, task, permissions, tests, sampleReport, images}),
          readme: (if .components.readme then "\($root)/\(.folder)/README.md" else null end)
        })) | sort_by(.id))
    }' "$RECORDS_FILE"
}

cmd_index() {
  local out="" readme=false
  while [ $# -gt 0 ]; do
    case "$1" in
      -o) out="${2:-}"; shift 2 ;;
      --readme) readme=true; shift ;;
      *) die "index: unknown argument $1" ;;
    esac
  done
  local vout
  vout="$(SKIP_README_CHECK=1 cmd_validate)" || { echo "$vout"; exit 1; }
  build_records || exit 1
  local json; json="$(build_index_json | jq --arg g "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{generatedAt:$g} + .')"
  if [ -n "$out" ]; then mkdir -p "$(dirname "$out")"; printf '%s\n' "$json" >"$out"; else printf '%s\n' "$json"; fi
  if $readme; then
    local readme_file="$ROOT/README.md" bf; bf="$(mktemp)"
    [ -f "$readme_file" ] && grep -qF "$README_START" "$readme_file" || die "README.md is missing the $README_START marker"
    readme_block <<<"$json" >"$bf"
    readme_apply "$readme_file" "$bf" >"$readme_file.tmp" && mv "$readme_file.tmp" "$readme_file"
    rm -f "$bf"
  fi
  rm -f "$RECORDS_FILE"
}

resolve_dir() {
  local arg="${1:-}"
  [ -n "$arg" ] || die "missing use case folder"
  if [ -d "$arg" ]; then (cd "$arg" && pwd)
  elif [ -d "$ROOT/$arg" ] && [ -f "$ROOT/$arg/usecase.yaml" ]; then echo "$ROOT/$arg"
  else
    local hit; hit="$(compgen -G "$ROOT/[0-9][0-9][0-9][0-9]-$arg/usecase.yaml" | head -n1)"
    [ -n "$hit" ] || die "use case folder not found: $arg"
    dirname "$hit"
  fi
}

fence() { # label, file
  printf '### %s\n\n' "$1"
  printf '````%s\n' "${3:-}"; cat "$2"; printf '\n````\n\n'
}

cmd_portal_blocks() {
  need jq
  local dir out="" arg=""
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="${2:-}"; shift 2 ;; *) arg="$1"; shift ;; esac
  done
  dir="$(resolve_dir "$arg")"
  local c; c="$(components_json "$dir")"
  local base; base="$(base_dir "$dir")"
  render_package() {
    local f kind found
    printf '# Portal blocks: %s\n\n' "$(basename "$dir")"
    for f in "$dir"/permissions/grant-*; do [ -f "$f" ] && fence "Permissions: $(basename "$f")" "$f" powershell; done
    jq -e '.permissions | not' >/dev/null <<<"$c" && printf '### Permissions\n\nNot present.\n\n'
    for kind in tools:Tool skills:Skill subagents:Subagent scheduled-tasks:"Scheduled task"; do
      found=false
      if [ "${kind%%:*}" = skills ]; then
        for f in "$base"/skills/*/SKILL.md; do
          [ -f "$f" ] && { found=true; fence "Skill: ${f#$base/}" "$f" markdown; }
        done
      else
        for f in "$base/${kind%%:*}"/*.yaml; do
          [ -f "$f" ] && { found=true; fence "${kind#*:}: ${f#$base/}" "$f" yaml; }
        done
      fi
      $found || printf '### %s\n\nNot present.\n\n' "${kind#*:}"
    done
  }
  render() {
    local f t s
    printf '# Portal blocks: %s\n\n' "$(basename "$dir")"
    for f in "$base"/grant-*; do [ -f "$f" ] && { fence "Permissions: $(basename "$f")" "$f" powershell; continue; }; done
    jq -e '.permissions | not' >/dev/null <<<"$c" && printf '### Permissions\n\nNot present.\n\n'
    t="$(jq -r '.tool // empty' <<<"$c")"
    if [ -n "$t" ]; then
      fence "Tool: $t" "$base/$t" python
      [ -f "$base/tool-parameters.schema.json" ] && fence "Tool parameters: tool-parameters.schema.json" "$base/tool-parameters.schema.json" json
    else printf '### Tool\n\nNot present.\n\n'; fi
    if [ -f "$base/SKILL.md" ]; then fence "Skill: SKILL.md" "$base/SKILL.md" markdown; fi
    for s in "$base"/skills/*/SKILL.md; do [ -f "$s" ] && fence "Skill: ${s#$base/}" "$s" markdown; done
    jq -e '.skill | not' >/dev/null <<<"$c" && printf '### Skill\n\nNot present.\n\n'
    if [ -f "$base/subagent-instructions-and-prompts.md" ]; then fence "Subagent: subagent-instructions-and-prompts.md" "$base/subagent-instructions-and-prompts.md" markdown
    else printf '### Subagent\n\nNot present.\n\n'; fi
    local found=false
    for f in "$base"/*-task-prompt.md; do [ -f "$f" ] && { found=true; fence "Scheduled task: $(basename "$f")" "$f" markdown; }; done
    $found || printf '### Scheduled task\n\nNot present.\n\n'
  }
  if [ "$base" != "$dir" ]; then render() { render_package; }; fi
  if [ -n "$out" ]; then render >"$out"; else render; fi
}

cmd_new() {
  need jq
  local domain="${1:-}" slug="${2:-}"
  [ -n "$domain" ] && [ -n "$slug" ] || die "usage: new <domain> <slug>"
  local tj; tj="$(yaml_to_json "$TAXONOMY")" || exit 1
  jq -e --arg p "$TAXONOMY" --arg k "$domain" '.[$p].data.domain | has($k)' >/dev/null <<<"$tj" \
    || die "unknown domain \"$domain\"; choose one of: $(jq -r --arg p "$TAXONOMY" '.[$p].data.domain | keys | join(", ")' <<<"$tj")"
  [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "slug must be lowercase letters, digits and hyphens"
  compgen -G "$ROOT/[0-9][0-9][0-9][0-9]-$slug" >/dev/null && die "slug \"$slug\" is already used; slugs must be unique"
  local last=0 d n
  for d in "$ROOT"/[0-9][0-9][0-9][0-9]-*/; do
    [ -d "$d" ] || continue
    n="$(basename "$d")"; n=$((10#${n:0:4})); [ "$n" -gt "$last" ] && last="$n"
  done
  local id; id="$(printf '%04d-%s' $((last + 1)) "$slug")"
  local dest="$ROOT/$id"
  [ ! -e "$dest" ] || die "$dest already exists; refusing to overwrite"
  [ -d "$REPO_USECASES/_template" ] || die "template not found"
  mkdir -p "$ROOT"
  cp -r "$REPO_USECASES/_template" "$dest"
  local title; title="$(echo "${slug//-/ }" | sed 's/^./\U&/')"
  sed -i -e "s/^id: .*/id: $id/" -e "s/^title: .*/title: $title/" -e "s/^domain: .*/domain: $domain/" "$dest/usecase.yaml"
  sed -i -e "1s/.*/# $title/" "$dest/README.md"
  echo "Created $dest. Fill in the files, then run: usecases.sh validate"
}

# Builds request bodies from manifests/ YAML and sends them through put() of cmd_deploy.
deploy_package() {
  local f yj name body skillfile first rest
  for f in "$base"/tools/*.yaml; do
    [ -f "$f" ] || continue
    yj="$(yaml_to_json "$f")" || exit 1
    local codefile; codefile="$(jq -r --arg p "$f" '.[$p].data.spec.code_file // empty' <<<"$yj")"
    if [ -n "$codefile" ]; then
      [ -f "$(dirname "$f")/$codefile" ] || die "$f: code_file $codefile not found"
      jq --arg p "$f" --rawfile c "$(dirname "$f")/$codefile" '.[$p].data.spec |= (del(.code_file) + {functionCode:$c}) | .' <<<"$yj" >"$tmp/yj.json"
      yj="$(cat "$tmp/yj.json")"
    fi
    jq --arg p "$f" '.[$p].data as $m | {name:$m.metadata.name, type:"ExtendedAgentTool", tags:null,
      properties:(({dependencies:[], authEnabled:false, authScopes:null, connector:null, attributes:[], toolMode:"Auto"} + $m.spec)
        | .parameters = [(.parameters // [])[] | {value:null, required:false} + .])}' <<<"$yj" >"$tmp/body.json"
    put tools "$(jq -r .name "$tmp/body.json")" "$tmp/body.json"
  done
  for f in "$base"/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    local sdir; sdir="$(dirname "$f")"
    awk 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit} NR>1{print}' "$f" >"$tmp/fm.yaml"
    [ -s "$tmp/fm.yaml" ] || die "$f: SKILL.md needs YAML frontmatter with name and description"
    yj="$(yaml_to_json "$tmp/fm.yaml")" || exit 1
    local extra="[]" e
    while IFS= read -r e; do
      extra="$(jq -c --arg p "${e#$sdir/}" --rawfile c "$e" '. + [{filePath:$p, content:$c}]' <<<"$extra")"
    done < <(find "$sdir" -type f ! -name SKILL.md | sort)
    jq --arg p "$tmp/fm.yaml" --arg d "$(basename "$sdir")" --rawfile c "$f" --argjson x "$extra" '.[$p].data as $m |
      {name:($m.name // $d), type:"Skill", tags:null, properties:{description:($m.description // ""),
       tools:($m.tools // []), skillContent:$c, additionalFiles:$x}}' <<<"$yj" >"$tmp/body.json"
    put skills "$(jq -r .name "$tmp/body.json")" "$tmp/body.json"
  done
  for f in "$base"/subagents/*.yaml; do
    [ -f "$f" ] || continue
    yj="$(yaml_to_json "$f")" || exit 1
    jq --arg p "$f" '.[$p].data as $m | $m.spec as $s |
      {name:$m.metadata.name, type:"ExtendedAgent", tags:null, properties:{
        description:($s.description // ""), instructions:($s.system_prompt // $s.instructions // ""),
        handoffDescription:($s.handoff_description // $s.handoffDescription // ""), handoffs:($s.handoffs // []),
        tools:($s.tools // []), mcpTools:($s.mcp_tools // $s.mcpTools // []), connectors:[],
        allowParallelToolCalls:false, agentsAsTools:[], maxReflectionCount:0, criticPromptPath:"", criticOnHandOff:false,
        customReflectionNote:"", commonPrompts:[], disableDocumentRetrieval:true, enableHandoffPromptOverride:false,
        userPromptOverride:null, handoffPromptOverride:null, instructionsOverride:null, commonTools:[],
        temperature:($s.temperature // null), llmModelName:null, enableVanillaMode:false,
        enableSkills:($s.enable_skills // $s.enableSkills // false), addSystemSkills:false,
        allowedSkills:($s.allowed_skills // $s.allowedSkills // []), outputType:null, hooks:null, permissions:null}}' <<<"$yj" >"$tmp/body.json"
    put agents "$(jq -r .name "$tmp/body.json")" "$tmp/body.json"
  done
  for f in "$base"/scheduled-tasks/*.yaml; do
    [ -f "$f" ] || continue
    yj="$(yaml_to_json "$f")" || exit 1
    jq --arg p "$f" '.[$p].data as $m | $m.spec as $s |
      {name:$m.metadata.name, type:"ScheduledTask", tags:[], properties:({
        name:$m.metadata.name, description:($s.description // ""), cronExpression:($s.cronExpression // $s.schedule // ""),
        agentPrompt:($s.agentPrompt // $s.prompt // ""), agentMode:($s.agentMode // $s.mode // "Review"),
        isEnabled:($s.isEnabled // $s.enabled // true), timeZone:($s.timeZone // $s.time_zone // "UTC")}
        + (if ($s.agent // "") == "" then {} else {agent:$s.agent} end))}' <<<"$yj" >"$tmp/body.json"
    put scheduledtasks "$(jq -r .name "$tmp/body.json")" "$tmp/body.json"
  done
}

cmd_deploy() {
  need jq; need curl
  local arg="" endpoint="" sub="" dry=false diff=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --endpoint) endpoint="${2:-}"; shift 2 ;;
      --subscription) sub="${2:-}"; shift 2 ;;
      --dry-run) dry=true; shift ;;
      --diff) diff=true; shift ;;
      *) arg="$1"; shift ;;
    esac
  done
  [ -n "$endpoint" ] || die "deploy: --endpoint is required"
  endpoint="${endpoint%/}"
  local dir; dir="$(resolve_dir "$arg")"
  local folder; folder="$(basename "$dir")"
  local name; name="$(echo "$folder" | sed -E 's/^[0-9]+-//')"
  local yj summary c
  yj="$(yaml_to_json "$dir/usecase.yaml")" || exit 1
  summary="$(jq -r --arg p "$dir/usecase.yaml" '.[$p].data.summary // ""' <<<"$yj")"
  c="$(components_json "$dir")"
  local base; base="$(base_dir "$dir")"

  local token=""
  if ! $dry; then
    need az
    local args=(account get-access-token --resource https://azuresre.ai --query accessToken -o tsv)
    [ -n "$sub" ] && args+=(--subscription "$sub")
    token="$(az "${args[@]}")" || die "could not get an access token; run az login"
  fi

  put() { # kind name body-file
    local url="$endpoint/api/v2/extendedAgent/$1/$2"
    if $diff; then
      local live code
      live="$(mktemp)"
      code="$(curl -sS -o "$live" -w '%{http_code}' "$url" -H "Authorization: Bearer $token")" || die "GET $1/$2 failed"
      if [ "$code" = "404" ]; then echo "NEW     $1/$2 (not on the agent)"
      elif [ "$code" -ge 300 ]; then die "GET $1/$2 failed with HTTP $code"
      else
        local changed
        changed="$(jq -rn --slurpfile l "$3" --slurpfile r "$live" '[ $l[0].properties | to_entries[] | select(.value != ($r[0].properties[.key])) | .key ] | join(",")')"
        if [ -z "$changed" ]; then echo "SAME    $1/$2"; else echo "CHANGED $1/$2 (fields: $changed)"; fi
      fi
      rm -f "$live"
      return 0
    fi
    if $dry; then
      echo "[dry-run] PUT $url ($(wc -c <"$3") bytes) keys: $(jq -r '[.properties | keys[]] | join(",")' "$3")"
      return 0
    fi
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$url" -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' --data-binary @"$3")" || die "PUT $1/$2 failed"
    [ "$code" -lt 300 ] || die "PUT $1/$2 failed with HTTP $code"
    echo "OK  $1/$2 ($code)"
  }

  local tmp; tmp="$(mktemp -d)"; trap 'rm -rf "${tmp:-}"' RETURN
  if [ "$base" != "$dir" ]; then deploy_package; return $?; fi
  local tool="" toolname=""
  tool="$(jq -r '.tool // empty' <<<"$c")"
  if [ -n "$tool" ]; then
    toolname="${tool#generate-}"; toolname="${toolname%.py}"
    [ -f "$base/tool-parameters.schema.json" ] || die "tool-parameters.schema.json is missing"
    jq -n --arg n "$toolname" --arg d "$summary" --rawfile code "$base/$tool" \
      --slurpfile s "$base/tool-parameters.schema.json" '
      ($s[0].required // []) as $req |
      {name:$n, type:"ExtendedAgentTool", tags:null, properties:{
        type:"PythonFunctionTool", functionCode:$code, timeoutSeconds:300, dependencies:[],
        authEnabled:false, authScopes:null, connector:null, description:$d,
        parameters:(($s[0].properties // {}) | to_entries | map({
          name:.key, type:(.value.type // "string"), required:(.key as $k | $req | index($k) != null),
          value:null, description:(.value.description // $d)})),
        attributes:[], toolMode:"Auto"}}' >"$tmp/tool.json"
    put tools "$toolname" "$tmp/tool.json"
  fi

  local skills=() s sname
  [ -f "$base/SKILL.md" ] && skills+=("$base/SKILL.md")
  for s in "$base"/skills/*/SKILL.md; do [ -f "$s" ] && skills+=("$s"); done
  local allowed="[]"
  for s in "${skills[@]}"; do
    if [ "$s" = "$base/SKILL.md" ]; then sname="$name"; else sname="$(basename "$(dirname "$s")")"; fi
    jq -n --arg n "$sname" --arg d "$summary" --arg t "$toolname" --rawfile c "$s" '
      {name:$n, type:"Skill", tags:null, properties:{description:$d, tools:(if $t=="" then [] else [$t] end),
       skillContent:$c, additionalFiles:[]}}' >"$tmp/skill.json"
    put skills "$sname" "$tmp/skill.json"
    allowed="$(jq -c --arg n "$sname" '. + [$n]' <<<"$allowed")"
  done

  if [ -f "$base/subagent-instructions-and-prompts.md" ]; then
    jq -n --arg n "$name" --arg d "$summary" --arg t "$toolname" --argjson a "$allowed" \
      --rawfile i "$base/subagent-instructions-and-prompts.md" '
      {name:$n, type:"ExtendedAgent", tags:null, properties:{
        instructions:$i, handoffDescription:$d, handoffs:[], tools:(if $t=="" then [] else [$t] end),
        mcpTools:[], connectors:[], allowParallelToolCalls:false, agentsAsTools:[], maxReflectionCount:0,
        criticPromptPath:"", criticOnHandOff:false, customReflectionNote:"", commonPrompts:[],
        disableDocumentRetrieval:true, enableHandoffPromptOverride:false, userPromptOverride:null,
        handoffPromptOverride:null, instructionsOverride:null, commonTools:[], temperature:null,
        llmModelName:null, enableVanillaMode:false, enableSkills:true, addSystemSkills:false,
        allowedSkills:$a, outputType:null, hooks:null, permissions:null}}' >"$tmp/agent.json"
    put agents "$name" "$tmp/agent.json"
  fi
  $diff || echo "Scheduled tasks are not deployed by this command; use portal-blocks for the task prompt."
}

cmd_diff() { cmd_deploy --diff "$@"; }

# Checks that the resources listed in tests/expected-config.yaml exist on the live agent.
cmd_verify() {
  need jq; need curl; need az
  local arg="" endpoint="" sub=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --endpoint) endpoint="${2:-}"; shift 2 ;;
      --subscription) sub="${2:-}"; shift 2 ;;
      *) arg="$1"; shift ;;
    esac
  done
  [ -n "$endpoint" ] || die "verify: --endpoint is required"
  endpoint="${endpoint%/}"
  local dir; dir="$(resolve_dir "$arg")"
  local exp="$dir/tests/expected-config.yaml"
  [ -f "$exp" ] || die "verify: $exp not found"
  local ej; ej="$(yaml_to_json "$exp")" || exit 1
  jq -e --arg p "$exp" '.[$p].data | type == "object"' >/dev/null <<<"$ej" || die "verify: $exp is not a mapping"
  local args=(account get-access-token --resource https://azuresre.ai --query accessToken -o tsv)
  [ -n "$sub" ] && args+=(--subscription "$sub")
  local token; token="$(az "${args[@]}")" || die "could not get an access token; run az login"
  local missing=0 key route name list
  for key in skills:skills subagents:agents tools:tools scheduledTasks:scheduledtasks; do
    route="${key#*:}"; key="${key%%:*}"
    list="$(jq -r --arg p "$exp" --arg k "$key" '.[$p].data[$k] // [] | .[]' <<<"$ej")"
    [ -n "$list" ] || continue
    local live; live="$(curl -sSf "$endpoint/api/v2/extendedAgent/$route" -H "Authorization: Bearer $token")" \
      || die "could not list $route"
    while IFS= read -r name; do
      if jq -e --arg n "$name" '(if type == "array" then . else (.value // .items // []) end) | any(.name == $n)' >/dev/null <<<"$live"; then
        echo "OK      $route/$name"
      else
        echo "MISSING $route/$name"; missing=$((missing + 1))
      fi
    done <<<"$list"
  done
  [ "$missing" -eq 0 ] || { echo "verify: $missing resource(s) missing"; exit 1; }
  echo "verify: all expected resources found"
}

main() {
  if [ "${1:-}" = "--root" ]; then ROOT="$(cd "${2:-}" && pwd)" || die "root not found"; shift 2; fi
  local cmd="${1:-}"; [ $# -gt 0 ] && shift
  case "$cmd" in
    validate) cmd_validate "$@" ;;
    index) cmd_index "$@" ;;
    portal-blocks) cmd_portal_blocks "$@" ;;
    new) cmd_new "$@" ;;
    deploy) cmd_deploy "$@" ;;
    diff) cmd_diff "$@" ;;
    verify) cmd_verify "$@" ;;
    ""|-h|--help|help) sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
