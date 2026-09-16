#!/usr/bin/env python3
"""Migrera _inbox/daglig-triage.md → _tasks.yaml (v2-schema).

Varje triage-rad bär idag fyra sorters information i en enda mening: uppgiften,
historiken, referensdata och resonemang. Medianraden är 273 tecken vilket gör
filen oläsbar manuellt. Denna migrering delar raden:

  task:   första meningen/satsen — det som ska GÖRAS (max ~120 tecken)
  notes:  allt övrigt — historik, referenser, varningar, resonemang
  detail: rader som börjar med två blanksteg (underrader) läggs i notes

Bevarar {id}-token som `triage_id` så Todoist-länkarna håller.
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
SRC = f"{VAULT}/_inbox/daglig-triage.md"

ID_RE   = re.compile(r"\{([0-9a-f]{4})\}")
DL_RE   = re.compile(r"⏰(\d{6})")
TAG_RE  = re.compile(r"^\*\*\[([^\]]+)\]\*\*\s*")
PRIO_RE = re.compile(r"\*\*(P[0-3])\.?\*\*")

def strip_md(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\*(.+?)\*", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()

def split_task(body):
    """Dela i kort uppgift + resten. Bryt vid första meningsslut efter 40 tecken."""
    plain = strip_md(body)
    if len(plain) <= 120:
        return plain, ""
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ])", plain):
        if 40 <= m.start() <= 150:
            return plain[:m.start()].rstrip(" ."), plain[m.end():]
    for sep in (" — ", " – ", ". ", " · "):
        i = plain.find(sep, 40)
        if 40 <= i <= 150:
            return plain[:i].rstrip(" ."), plain[i+len(sep):]
    cut = plain.rfind(" ", 60, 120)
    cut = cut if cut > 0 else 120
    return plain[:cut], plain[cut:].lstrip()

def main():
    lines = open(SRC, encoding="utf-8").read().splitlines()
    sec = sub = None
    tasks, nid = [], 1
    i = 0
    while i < len(lines):
        raw = lines[i]
        if raw.startswith("## "):
            sec = strip_md(raw[3:]).split("—")[0].strip(); sub = None
        elif raw.startswith("### "):
            sub = strip_md(raw[4:]).split("—")[0].strip()
        elif raw.strip().startswith("- [ ]"):
            body = raw.strip()[5:].strip()
            extra = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and not lines[j].strip().startswith("- ["):
                if lines[j].strip():
                    extra.append(strip_md(lines[j]))
                j += 1
            tid = ID_RE.search(body); dl = DL_RE.search(body); pr = PRIO_RE.search(body)
            tag = TAG_RE.match(body)
            clean = TAG_RE.sub("", body)
            clean = ID_RE.sub("", DL_RE.sub("", clean)).strip(" .·—-")
            task, rest = split_task(clean)
            notes = ([rest] if rest else []) + extra
            t = {"id": nid, "task": task}
            if tag:  t["context"] = tag.group(1)
            t["section"] = f"{sec} / {sub}" if sub and sub != sec else (sec or "")
            t["priority"] = pr.group(1) if pr else None
            t["due"] = dl.group(1) if dl else None
            t["status"] = "open"
            if tid: t["triage_id"] = tid.group(1)
            if notes: t["notes"] = notes
            tasks.append(t); nid += 1
            i = j; continue
        i += 1

    def esc(s):
        s = str(s).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    out = ["version: 2",
           f"last_updated: {date.today().strftime('%y%m%d')}  # migrerad från daglig-triage.md",
           "context: tomas-personal", "scope: personal",
           f"next_id: {nid}", "", "# Uppgifter. Prosa och referensdata ligger i notes,",
           "# aldrig i task-fältet. task ska gå att läsa i ett svep.", "", "tasks:"]
    cur = None
    for t in tasks:
        if t["section"] != cur:
            cur = t["section"]; out.append(f"\n  # --- {cur} ---")
        out.append(f"  - id: {t['id']}")
        out.append(f"    task: {esc(t['task'])}")
        if t.get("context"): out.append(f"    context: {esc(t['context'])}")
        out.append(f"    priority: {t['priority'] or 'null'}")
        out.append(f"    due: {t['due'] or 'null'}")
        out.append(f"    status: {t['status']}")
        if t.get("triage_id"): out.append(f"    triage_id: {esc(t['triage_id'])}")
        if t.get("notes"):
            out.append("    notes:")
            for n in t["notes"]:
                if n.strip(): out.append(f"      - {esc(n)}")
    dest = f"{VAULT}/_inbox/_tasks.yaml"
    open(dest, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"{len(tasks)} uppgifter → {dest}")
    lens = sorted(len(t["task"]) for t in tasks)
    print(f"task-fält: median {lens[len(lens)//2]} tecken, längsta {lens[-1]}")
    print(f"med prio: {sum(1 for t in tasks if t['priority'])}  med datum: {sum(1 for t in tasks if t['due'])}")

if __name__ == "__main__":
    main()
