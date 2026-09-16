#!/usr/bin/env python3
"""Importera nya uppgifter FRÅN _inbox till _tasks.yaml.

Två inflöden:

  1. _inbox/_capture.md  — friformsyta. Skriv/klistra en rad per uppgift,
     kör importen, raden flyttas in i YAML och tas bort ur capture-filen.
     Detta är den ursprungliga tanken med _inbox som dörr: släpp in, routa ut.

  2. _inbox/*.md         — filer registrerade i _inbox.yaml med status "new"
     listas som kandidater (importeras inte automatiskt — de kan vara
     transkript eller referensmaterial, inte uppgifter).

Syntax i _capture.md (allt utom texten är valfritt):

  - Ring Oliwer om dödsboet @ekonomi !P1 ⏰260910
  - [Sonetel] Verifiera betalande-siffran !P0 ⏰260917

  @tagg   → context      !P0..!P3 → priority      ⏰YYMMDD → due
  [Text]  → context (alternativ form)
"""
import re, sys, os
import os
from datetime import date

# Vaultsökvägen är maskinberoende (användarnamnet skiljer mellan Macarna).
# Ordning: VAULT_ROOT ur miljön, sedan de kända platserna under $HOME.
VAULT = next((p for p in (
    os.environ.get("VAULT_ROOT"),
    os.path.expanduser("~/workspace/Tomas"),
    os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Tomas"),
) if p and os.path.isdir(p)), None)
if not VAULT:
    raise SystemExit("hittar ingen vault — sätt VAULT_ROOT")
YAML_PATH = f"{VAULT}/_inbox/_tasks.yaml"
CAPTURE   = f"{VAULT}/_inbox/_capture.md"

PRIO_RE = re.compile(r"!\s*(P[0-3])\b", re.I)
DUE_RE  = re.compile(r"⏰\s*(\d{6})")
AT_RE   = re.compile(r"@([\w\-åäöÅÄÖ/]+)")
BR_RE   = re.compile(r"^\[([^\]]+)\]\s*")

def esc(s):
    s = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

def parse(line):
    t = line.strip().lstrip("-*").strip()
    if not t or t.startswith("#"):
        return None
    prio = PRIO_RE.search(t); due = DUE_RE.search(t)
    ctx = None
    m = BR_RE.match(t)
    if m:
        ctx = m.group(1); t = BR_RE.sub("", t)
    else:
        a = AT_RE.search(t)
        if a: ctx = a.group(1)
    t = PRIO_RE.sub("", DUE_RE.sub("", AT_RE.sub("", t)))
    t = re.sub(r"\s+", " ", t).strip(" .·—-")
    if not t: return None
    return {"task": t, "context": ctx,
            "priority": prio.group(1).upper() if prio else None,
            "due": due.group(1) if due else None}

def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(CAPTURE):
        open(CAPTURE, "w", encoding="utf-8").write(
            "# Capture — en rad per uppgift\n\n"
            "Skriv fritt, kör sedan `python3 ~/bin/todoist-triage/import_inbox.py`.\n"
            "Rader som importeras tas bort härifrån.\n\n"
            "Syntax: `@tagg` kontext · `!P1` prio · `⏰260910` datum\n\n")
        print(f"Skapade {CAPTURE} — skriv uppgifter där och kör igen.")
        return

    lines = open(CAPTURE, encoding="utf-8").read().splitlines()
    nya, behall = [], []
    # Bindestreck krävs INTE. En rad man skrivit i en capture-fil är en uppgift —
    # att kräva rätt syntax av en friformsyta motverkar dess syfte. Rubriker,
    # instruktioner och tomrader hoppas; allt annat läses som uppgift.
    hoppa = ("#", ">", "|", "Skriv fritt", "Syntax:", "Rader som importeras")
    for l in lines:
        t = l.strip()
        if not t or t.startswith(hoppa) or len(t) < 12:
            behall.append(l); continue
        p = parse(l)
        if p: nya.append(p)
        else: behall.append(l)

    if not nya:
        print("Inget att importera från _capture.md.")
    else:
        y = open(YAML_PATH, encoding="utf-8").read()
        m = re.search(r"^next_id:\s*(\d+)", y, re.M)
        nid = int(m.group(1)) if m else 1
        block = [f"\n  # --- Importerat {date.today().strftime('%y%m%d')} ---"]
        for p in nya:
            block.append(f"  - id: {nid}")
            block.append(f"    task: {esc(p['task'])}")
            if p["context"]: block.append(f"    context: {esc(p['context'])}")
            block.append(f"    priority: {p['priority'] or 'null'}")
            block.append(f"    due: {p['due'] or 'null'}")
            block.append("    status: open")
            block.append(f"    created: {date.today().strftime('%y%m%d')}")
            print(f"  + [{nid}] {p['task'][:60]}"
                  + (f"  {p['priority']}" if p['priority'] else "")
                  + (f"  ⏰{p['due']}" if p['due'] else ""))
            nid += 1
        if dry:
            print(f"\n(dry-run — {len(nya)} rader skulle importeras)")
            return
        y = re.sub(r"^next_id:\s*\d+", f"next_id: {nid}", y, count=1, flags=re.M)
        y = re.sub(r"^last_updated:.*$", f"last_updated: {date.today().strftime('%y%m%d')}",
                   y, count=1, flags=re.M)
        open(YAML_PATH, "w", encoding="utf-8").write(y.rstrip("\n") + "\n" + "\n".join(block) + "\n")
        open(CAPTURE, "w", encoding="utf-8").write("\n".join(behall).rstrip("\n") + "\n")
        print(f"\n{len(nya)} importerade → _tasks.yaml")

    # kandidatfiler i _inbox
    try:
        import yaml as _y
        inv = _y.safe_load(open(f"{VAULT}/_inbox/_inbox.yaml", encoding="utf-8"))
        kand = [i for i in inv.get("items", []) if i.get("status") == "new"]
        if kand:
            print(f"\n{len(kand)} oprocessade filer i _inbox.yaml:")
            for i in kand:
                print(f"  · {i.get('file')} ({i.get('type')})")
            print("  → routa med /inbox eller /transcript; importeras inte hit automatiskt.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
