#!/usr/bin/env python3
"""Generera _inbox/daglig-triage.md ur _tasks.yaml.

YAML är sanningen. Markdown är en LÄSVY — kort, skannbar, utan prosa.
Detaljer bor i notes i YAML och visas inte här; vyn svarar bara på
"vad gör jag nu?".
"""
import yaml, sys
import os
from datetime import date, timedelta

# Vaultsökvägen är maskinberoende (användarnamnet skiljer mellan Macarna).
# Ordning: VAULT_ROOT ur miljön, sedan de kända platserna under $HOME.
VAULT = next((p for p in (
    os.environ.get("VAULT_ROOT"),
    os.path.expanduser("~/workspace/Tomas"),
    os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Tomas"),
) if p and os.path.isdir(p)), None)
if not VAULT:
    raise SystemExit("hittar ingen vault — sätt VAULT_ROOT")
SRC  = f"{VAULT}/_inbox/_tasks.yaml"
DEST = f"{VAULT}/_inbox/daglig-triage.md"
RAM  = f"{VAULT}/_inbox/_frame.md"        # handskriven kontext, klistras in orört

def d(s):
    if not s: return None
    s = str(s)
    try: return date(2000+int(s[:2]), int(s[2:4]), int(s[4:6]))
    except Exception: return None

def main():
    doc = yaml.safe_load(open(SRC, encoding="utf-8"))
    tasks = [t for t in doc["tasks"] if t.get("status") == "open"]
    today = date.today(); tomorrow = today + timedelta(days=1)

    forfallna = sorted((t for t in tasks if d(t.get("due")) and d(t["due"]) < today),
                       key=lambda t: d(t["due"]))
    idag      = [t for t in tasks if d(t.get("due")) == today]
    imorgon   = [t for t in tasks if d(t.get("due")) == tomorrow]
    p0p1      = [t for t in tasks if t.get("priority") in ("P0","P1")
                 and not d(t.get("due"))]
    veckan    = sorted((t for t in tasks if d(t.get("due"))
                        and tomorrow < d(t["due"]) <= today + timedelta(days=7)),
                       key=lambda t: d(t["due"]))

    L = [f"# Daglig triage — {today.strftime('%-d %B %Y').lower()}", "",
         "> **Genererad ur [`_tasks.yaml`](_tasks.yaml) — redigera inte här.**",
         "> Lägg till och ändra i YAML:en, kör sedan `python3 ~/bin/todoist-triage/render_triage.py`.",
         "> Detaljer, historik och referenser ligger i `notes:` per uppgift — inte i denna vy.", ""]

    try:
        ram = open(RAM, encoding="utf-8").read().strip()
        if ram: L += [ram, ""]
    except FileNotFoundError:
        pass

    def block(rubrik, rows, visa_datum=False):
        if not rows: return
        L.append(f"## {rubrik}")
        L.append("")
        for t in rows:
            p = f"`{t['priority']}` " if t.get("priority") else ""
            ctx = f"**{t['context']}** — " if t.get("context") else ""
            dd = d(t.get("due"))
            datum = f" *({dd.strftime('%-d/%-m')})*" if visa_datum and dd else ""
            n = f" · {len(t['notes'])} not" if t.get("notes") else ""
            L.append(f"- [ ] {p}{ctx}{t['task']}{datum} `#{t['id']}`{n}")
        L.append("")

    if forfallna:
        L += ["## FÖRFALLNA", ""]
        for t in forfallna:
            dd = d(t["due"]); sen = (today - dd).days
            ctx = f"**{t['context']}** — " if t.get("context") else ""
            L.append(f"- [ ] {ctx}{t['task']} — **{sen} dgr sen** *({dd.strftime('%-d/%-m')})* `#{t['id']}`")
        L.append("")

    block("IDAG", idag)
    block("IMORGON", imorgon)
    block("PRIO — utan datum", p0p1)
    block("DENNA VECKA", veckan, visa_datum=True)

    ovrigt = len(tasks) - len(forfallna) - len(idag) - len(imorgon) - len(p0p1) - len(veckan)
    L += ["---", "",
          f"**{len(tasks)} öppna uppgifter totalt.** Denna vy visar "
          f"{len(tasks)-ovrigt}; de övriga **{ovrigt}** saknar datum och prio — "
          f"se [`_tasks.yaml`](_tasks.yaml).", "",
          "*Att sätta prio eller datum lyfter en uppgift hit. "
          "En uppgift utan datum kan aldrig vara P0/P1 "
          "(se [`_config/priority.md`](../_config/priority.md)).*"]

    open(DEST, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"{DEST}: {len(L)} rader ({len(tasks)} öppna, {len(tasks)-ovrigt} i vyn)")

if __name__ == "__main__":
    main()
