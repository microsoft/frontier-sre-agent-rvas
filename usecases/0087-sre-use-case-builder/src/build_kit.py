"""Build sre-usecase-builder-kit.py from src/kit_*.py and the generated-tool template."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
template = (ROOT / "usecase_tool_template.py").read_text(encoding="utf-8")
assert "'''" not in template, "template must not contain triple single quotes"
assert not template.rstrip("\n").endswith("\\"), "template must not end with a backslash"
assert template.count("\ndef main(") == 1 and "__TEMPLATE_MAIN__" not in template
template = template.replace("\ndef main(", "\ndef __TEMPLATE_MAIN__(")
parts = [(ROOT / f).read_text(encoding="utf-8") for f in ("kit_1_catalog.py", "kit_2_build.py", "kit_3_blocks.py", "kit_4_ops.py", "kit_5_brand.py", "kit_6_assets.py")]
kit = "".join(parts)
assert kit.count("r'''__TEMPLATE__'''") == 1
kit = kit.replace("r'''__TEMPLATE__'''", "r'''" + template + "'''")
ast.parse(kit)
assert [l[:24] for l in kit.splitlines() if l.startswith('def main(')] == ['def main(operation: str '], 'Builder must only see the kit main()'
assert kit.find('\ndef main(') < 5000, 'kit main() must stay near the top for the Builder Test playground'
out = ROOT.parent / "manifests" / "tools" / "sre-usecase-builder-kit.py"
out.write_text(kit, encoding="utf-8", newline="\n")
print(out, len(kit.encode()), "bytes", hashlib.sha256(kit.encode()).hexdigest()[:16])
