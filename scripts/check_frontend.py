"""Catch frontend wiring mistakes before anyone opens a browser. No dependencies, runs in CI.

    python scripts/check_frontend.py

Checks:
  1. Every JavaScript file parses (uses Node, which is on GitHub's runners).
  2. Every import in frontend/js points to a file that exists.
  3. Every CSS/JS file that index.html loads exists.
  4. Every menu link (data-route) has a matching route in main.js, and every route is a real view.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
problems: list[str] = []


def problem(message: str) -> None:
    problems.append(message)
    print(f"FAIL  {message}")


js_files = sorted((FRONTEND / "js").rglob("*.js"))

# 1. syntax
node = shutil.which("node")
if node:
    for path in js_files:
        result = subprocess.run(
            [node, "--input-type=module", "--check"], input=path.read_text(encoding="utf-8"),
            capture_output=True, text=True,
        )
        if result.returncode:
            problem(f"{path.relative_to(FRONTEND)} does not parse: {result.stderr.strip().splitlines()[0]}")
else:
    print("WARN  node not found, skipping the syntax check")

# 2. imports resolve
for path in js_files:
    for target in re.findall(r"""from\s+["']([^"']+)["']""", path.read_text(encoding="utf-8")):
        if not target.startswith((".", "/")):
            continue  # a package import; there are none today
        resolved = (FRONTEND / target.lstrip("/")) if target.startswith("/") else (path.parent / target)
        if not resolved.resolve().is_file():
            problem(f"{path.relative_to(FRONTEND)} imports {target}, which does not exist")

# 3. files that index.html loads
index = (FRONTEND / "index.html").read_text(encoding="utf-8")
for target in re.findall(r"""(?:href|src)=["'](/[^"']+)["']""", index):
    if target.startswith("//") or target.startswith("/docs"):
        continue
    if not (FRONTEND / target.lstrip("/")).is_file():
        problem(f"index.html loads {target}, which does not exist")

# 4. menu links and routes
main = (FRONTEND / "js" / "main.js").read_text(encoding="utf-8")
routes_match = re.search(r"const routes = \{([^}]*)\}", main)
if not routes_match:
    problem("main.js has no `const routes = { ... }`")
    routes = set()
else:
    routes = {name.strip() for name in routes_match.group(1).split(",") if name.strip()}

for link in sorted(set(re.findall(r'data-route="([^"]+)"', index))):
    if link not in routes:
        problem(f'index.html has a menu link data-route="{link}" but main.js has no such route')

imported = dict(re.findall(r"""import\s+(\w+)\s+from\s+["']\./views/(\w+)\.js["']""", main))
for route in sorted(routes):
    view = FRONTEND / "js" / "views" / f"{imported.get(route, route)}.js"
    if not view.is_file():
        problem(f"route '{route}' has no view file")
        continue
    text = view.read_text(encoding="utf-8")
    for needed in ("title:", "subtitle:", "mount("):
        if needed not in text:
            problem(f"{view.relative_to(FRONTEND)} is missing `{needed}` (every view needs a title, subtitle and mount)")

if problems:
    print(f"\n{len(problems)} problem(s) found.")
    sys.exit(1)
print(f"OK  {len(js_files)} JavaScript files, {len(routes)} routes, index.html links all fine.")
