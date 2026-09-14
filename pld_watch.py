#!/usr/bin/env python3
"""pld-watch - EU Product Liability Directive (EU) 2024/2853 exposure screen.

From 9 December 2026 the new Product Liability Directive treats software, SaaS
and AI systems as "products" under no-fault strict liability. Two things it
makes relevant as evidence of defectiveness:

  * a component you ship that can no longer receive security updates, and
  * a failure to supply the updates needed to keep a product safe.

pld-watch finds the runtimes and frameworks in a project that are already past
their upstream end-of-life date, using the public endoflife.date catalogue.

Engineering tooling, not legal advice.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

__version__ = "1.0.0"
EOL_API = "https://endoflife.date/api/v1/products"
# Article 2(1) as published read "after 9 December 2026". Corrigendum 2026/90364
# (OJ L, 2026/90364, 7.5.2026) corrected it to "after 8 December 2026":
#   http://data.europa.eu/eli/dir/2024/2853/corrigendum/2026-05-07/oj
# Articles 20, 21 and 22(1) (repeal, transposition, entry into force) still say
# 9 December 2026. The scope sentence is the one that decides whether a product
# you place on the market is caught, so that is the date this tool counts to.
PLD_APPLIES = date(2026, 12, 8)
PLD_TRANSPOSITION = date(2026, 12, 9)
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "pld-watch"


def _c(code: str, s: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return s
    return f"\033[{code}m{s}\033[0m"


def red(s): return _c("31;1", s)
def green(s): return _c("32;1", s)
def yellow(s): return _c("33;1", s)
def dim(s): return _c("2", s)
def bold(s): return _c("1", s)


def fetch(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"pld-watch/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def eol_product(slug: str, refresh: bool = False, max_age_h: int = 24) -> dict | None:
    """Fetch one product's release table, cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{slug}.json"
    if f.exists() and not refresh:
        age = (datetime.now(timezone.utc).timestamp() - f.stat().st_mtime) / 3600
        if age < max_age_h:
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
    try:
        raw = fetch(f"{EOL_API}/{slug}")
    except Exception:
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                return None
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    body = d.get("result", d)
    try:
        f.write_text(json.dumps(body))
    except Exception:
        pass
    return body


# ---------------------------------------------------------------- detection

# Maps a thing we can detect in a repo -> an endoflife.date product slug.
RUNTIME_SLUGS = {
    "nodejs": "nodejs", "python": "python", "go": "go", "ruby": "ruby",
    "php": "php", "java": "java", "dotnet": "dotnet", "rust": "rust",
}
FRAMEWORK_SLUGS = {
    # npm
    "next": "nextjs", "react": "react", "angular": "angular", "vue": "vue",
    "nuxt": "nuxt", "express": "express",
    # pypi
    "django": "django", "flask": "flask", "fastapi": "fastapi", "numpy": "numpy",
    # other ecosystems
    "rails": "rails", "laravel": "laravel", "symfony": "symfony",
    "spring-boot": "spring-boot",
}


def _major_minor(v: str) -> str:
    """First major[.minor] in a version string.

    Handles the range syntaxes people actually write: '^12.0.0', '~3.2',
    '>=16 <18', 'v1.19', '3.7-slim'. Returns '' when there is no version.
    """
    m = re.search(r"(\d+)(?:\.(\d+))?", v.strip())
    if not m:
        return ""
    return f"{m.group(1)}.{m.group(2)}" if m.group(2) else m.group(1)


def detect(root: Path) -> list[dict]:
    """Return [{kind, name, slug, version, source}] found in the project."""
    found: list[dict] = []

    def add(kind, name, slug, version, source):
        v = _major_minor(str(version))
        if v:
            found.append({"kind": kind, "name": name, "slug": slug,
                          "version": v, "source": source})

    nvmrc = root / ".nvmrc"
    if nvmrc.is_file():
        add("runtime", "Node.js", "nodejs", nvmrc.read_text().strip(), ".nvmrc")

    pyv = root / ".python-version"
    if pyv.is_file():
        add("runtime", "Python", "python", pyv.read_text().strip(), ".python-version")

    gomod = root / "go.mod"
    if gomod.is_file():
        m = re.search(r"^go\s+(\d+\.\d+)", gomod.read_text(errors="replace"), re.M)
        if m:
            add("runtime", "Go", "go", m.group(1), "go.mod")

    pj = root / "package.json"
    if pj.is_file():
        try:
            d = json.loads(pj.read_text(errors="replace"))
        except Exception:
            d = {}
        eng = (d.get("engines") or {}).get("node")
        if eng:
            add("runtime", "Node.js", "nodejs", re.sub(r"[^\d.]", " ", eng).split()[0]
                if re.search(r"\d", eng) else "", "package.json engines.node")
        deps = {}
        deps.update(d.get("dependencies") or {})
        deps.update(d.get("devDependencies") or {})
        for name, ver in deps.items():
            slug = FRAMEWORK_SLUGS.get(name)
            if slug and re.search(r"\d", str(ver)):
                add("framework", name, slug, re.sub(r"[^\d.]", " ", str(ver)).split()[0],
                    "package.json")

    for req in ("requirements.txt", "requirements-dev.txt"):
        p = root / req
        if p.is_file():
            for line in p.read_text(errors="replace").splitlines():
                m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([0-9][0-9A-Za-z.\-]*)", line)
                if not m:
                    continue
                slug = FRAMEWORK_SLUGS.get(m.group(1).lower())
                if slug:
                    add("framework", m.group(1), slug, m.group(2), req)

    df = root / "Dockerfile"
    if df.is_file():
        for line in df.read_text(errors="replace").splitlines():
            m = re.match(r"^\s*FROM\s+([A-Za-z0-9_./-]+):([0-9][0-9A-Za-z.\-]*)", line, re.I)
            if not m:
                continue
            base, tag = m.group(1).split("/")[-1].lower(), m.group(2)
            slug = RUNTIME_SLUGS.get(base) or FRAMEWORK_SLUGS.get(base)
            if slug:
                add("runtime", base, slug, tag, "Dockerfile FROM")

    # de-dup on (slug, version)
    seen, out = set(), []
    for f in found:
        k = (f["slug"], f["version"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def assess(items: list[dict], refresh: bool = False) -> list[dict]:
    """Attach EOL status from endoflife.date."""
    today = date.today()
    out = []
    for it in items:
        prod = eol_product(it["slug"], refresh=refresh)
        rec = dict(it, status="unknown", eol_date=None, latest=None)
        if not prod:
            out.append(rec)
            continue
        releases = prod.get("releases") or []
        match = None
        for rel in releases:
            if str(rel.get("name", "")) == it["version"]:
                match = rel
                break
        if match is None:
            for rel in releases:
                if it["version"].startswith(str(rel.get("name", "")) + "."):
                    match = rel
                    break
        if releases:
            live = [r for r in releases if not r.get("isEol")]
            if live:
                rec["latest"] = str(live[0].get("name"))
        if match is None:
            rec["status"] = "unknown"
        else:
            eol = match.get("eolFrom")
            rec["eol_date"] = eol
            if match.get("isEol"):
                rec["status"] = "eol"
            elif eol:
                try:
                    d = datetime.strptime(eol, "%Y-%m-%d").date()
                    days = (d - today).days
                    rec["status"] = "eol" if days < 0 else ("soon" if days <= 180 else "supported")
                    rec["days_to_eol"] = days
                except Exception:
                    rec["status"] = "supported"
            else:
                rec["status"] = "supported"
        out.append(rec)
    return out


# ------------------------------------------------------------------ output

def render(rows: list[dict], root: Path) -> int:
    eol = [r for r in rows if r["status"] == "eol"]
    soon = [r for r in rows if r["status"] == "soon"]
    ok = [r for r in rows if r["status"] == "supported"]
    unk = [r for r in rows if r["status"] == "unknown"]

    print()
    print(bold(f"pld-watch v{__version__}"))
    print("EU Product Liability Directive (EU) 2024/2853 - update-supportability screen")
    print()
    print(f"  Scope    {root}")
    print(f"  Found    {len(rows)} runtime/framework version(s)")
    days = (PLD_APPLIES - date.today()).days
    print(f"  PLD      applies from {PLD_APPLIES.isoformat()} "
          f"({days} days away)" if days >= 0 else f"  PLD      in force since {PLD_APPLIES.isoformat()}")
    print()
    print("  " + "-" * 68)

    if eol:
        print()
        print(red(f"  {len(eol)} COMPONENT(S) PAST UPSTREAM END-OF-LIFE"))
        print()
        for r in eol:
            print(f"    {bold(r['name'])} {r['version']}   {dim('(' + r['source'] + ')')}")
            print(f"      upstream EOL   {r['eol_date'] or 'yes'}"
                  + (f"   latest supported: {r['latest']}" if r.get("latest") else ""))
        print()
        print("  Why this matters under the PLD:")
        print("  A component past end-of-life receives no security updates. From")
        print("  9 December 2026, software placed on the EU market is a 'product'")
        print("  under strict liability, and the inability to supply the updates")
        print("  needed to keep it safe is capable of being treated as evidence")
        print("  that the product is defective. That is a civil-liability exposure,")
        print("  separate from any regulatory reporting duty.")
    if soon:
        print()
        print(yellow(f"  {len(soon)} approaching end-of-life (within 180 days)"))
        for r in soon:
            print(f"    {r['name']} {r['version']}  EOL {r['eol_date']} "
                  f"({r.get('days_to_eol','?')} days)")
    if ok and not eol and not soon:
        print()
        print(green("  Nothing detected past end-of-life."))
        for r in ok:
            print(f"    {r['name']} {r['version']}  supported"
                  + (f" (EOL {r['eol_date']})" if r["eol_date"] else ""))
    if unk:
        print()
        print(dim(f"  {len(unk)} component(s) had no matching release in the catalogue:"))
        for r in unk:
            print(dim(f"    {r['name']} {r['version']} ({r['slug']})"))

    print()
    print("  " + "-" * 68)
    print(dim("  Source: endoflife.date public catalogue. This is engineering"))
    print(dim("  tooling, not legal advice, and not a compliance determination."))
    print(dim("  Whether a product is defective is decided by a court on the"))
    print(dim("  facts, not by a scanner."))
    print()
    return 1 if eol else 0


def cmd_scan(a) -> int:
    root = Path(a.path).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    items = detect(root)
    if not items:
        print(f"\nNo runtime or framework versions found under {root}\n")
        print("pld-watch looks at: .nvmrc, .python-version, go.mod, package.json")
        print("(engines + known frameworks), requirements*.txt, Dockerfile FROM.\n")
        return 2
    rows = assess(items, refresh=a.refresh)
    if a.json:
        print(json.dumps({
            "tool": "pld-watch", "version": __version__,
            "scanned": str(root),
            "pld_applies": PLD_APPLIES.isoformat(),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "components": rows,
            "eol_count": sum(1 for r in rows if r["status"] == "eol"),
            "disclaimer": "Engineering tooling, not legal advice.",
        }, indent=2))
        return 1 if any(r["status"] == "eol" for r in rows) else 0
    return render(rows, root)


def cmd_clock(a) -> int:
    days = (PLD_APPLIES - date.today()).days
    print()
    print(bold("EU Product Liability Directive (EU) 2024/2853"))
    print()
    print(f"  Applies to products placed on the EU market from  {PLD_APPLIES.isoformat()}")
    print(f"  (Art. 2(1) as corrected by Corrigendum 2026/90364;")
    print(f"   Arts. 20-22 transposition/repeal date is {PLD_TRANSPOSITION.isoformat()})")
    if days > 0:
        print(f"  Days remaining                                    {days}")
    else:
        print(f"  In force ({abs(days)} days ago)")
    print()
    print("  What changes:")
    print("    - software, SaaS and AI systems are 'products'")
    print("    - liability is no-fault: a claimant proves defect, damage, causation")
    print("    - the 'later defect' defence is narrowed where the manufacturer")
    print("      retains control through updates")
    print("    - failure to supply security updates can evidence defectiveness")
    print()
    print(dim("  Not legal advice. Read the Directive and take advice on scope."))
    print()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="pld-watch",
        description="EU Product Liability Directive 2024/2853 update-supportability screen.",
        epilog="Engineering tooling, not legal advice. https://github.com/ntoledo319/pld-watch")
    p.add_argument("--version", action="version", version=f"pld-watch {__version__}")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="find components past upstream end-of-life")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--json", action="store_true", help="machine-readable output, for CI")
    s.add_argument("--refresh", action="store_true", help="bypass the local cache")
    s.set_defaults(fn=cmd_scan)
    c = sub.add_parser("clock", help="days until the PLD applies")
    c.set_defaults(fn=cmd_clock)
    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        p.print_help()
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
