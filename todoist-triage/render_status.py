#!/usr/bin/env python3
"""Nulägesbild per relation — hårda fakta räknade, bilden skriven.

Två lager, medvetet delade:

  SKRIPTET räknar det tidskritiska — förfallna poster, nästa möte, dagar sedan
  senaste kontakt, takt över månader. Determinism där determinism hör: en modell
  räknar inte dagar till torsdag.

  MODELLEN skriver bilden — läget, det olösta, teman över tid. Det är prosaarbete
  och kan inte listas fram; 100 insikter i datumordning är en databas, inte en bild.

Standard är Ollama lokalt (gemma4:26b på Studion, ~60 s/mapp). Materialet är
konfidentiellt och lämnar aldrig nätet.

    render_status.py <mapp>              en mapp
    render_status.py --window [dagar]    aktiva ±N dagar (standard 7)
    render_status.py --stale [dagar]     tystnade — listar bara
    render_status.py --recent [dagar]    aktiva — listar bara
    render_status.py --facts <mapp>      bara faktalagret, ingen modell

Miljö: OLLAMA_HOST (standard http://localhost:11434), OLLAMA_MODEL (gemma4:26b).
         Peka OLLAMA_HOST mot den maskin som faktiskt kör modellen.
"""
import os, re, sys, glob, json, subprocess
from collections import Counter, defaultdict
from datetime import date

VAULT = next((p for p in (
    os.environ.get("VAULT_ROOT"),
    os.path.expanduser("~/workspace/Tomas"),
    os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Tomas"),
) if p and os.path.isdir(p)), None)
if not VAULT: raise SystemExit("hittar ingen vault — sätt VAULT_ROOT")

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL  = os.environ.get("OLLAMA_MODEL", "gemma4:26b")

# Insikter om KÄLLAN (odiariserat, ASR-fel) är metadata om materialet, inte om
# relationen. De ska aldrig med i bilden.
ASR = re.compile(r"diarisera|transkri|Deep Thought|talaretikett|turindelning|ASR|felhör", re.I)

def yload(p):
    try:
        import yaml; return yaml.safe_load(open(p, encoding="utf-8")) or {}
    except Exception: return {}

def d6(s):
    s = str(s or "")
    if len(s) != 6 or not s.isdigit(): return None
    try: return date(2000+int(s[:2]), int(s[2:4]), int(s[4:6]))
    except ValueError: return None

def mlab(ym):
    m = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]
    return m[int(ym[2:4])-1]

def gather(abs_f):
    """Allt material + de uträknade fakta som en modell inte ska gissa."""
    today = date.today()
    meta = yload(f"{abs_f}/_meta.yaml")
    ins  = yload(f"{abs_f}/_insights.yaml").get("insights") or []
    tasks = [t for t in (yload(f"{abs_f}/_tasks.yaml").get("tasks") or [])
             if t.get("status") in (None, "open", "in_progress")]
    conv = []
    cl = f"{abs_f}/CHANGELOG.md"
    if os.path.exists(cl):
        tech = re.compile(r"\b(Normalize|Compile|schemamigrering)", re.I)
        for l in open(cl, encoding="utf-8"):
            if not l.startswith("- **"): continue
            m = re.match(r"- \*\*(\d{6}):\s*([^*]+)\*\*\s*[-–—]*\s*(.*)", l.strip())
            if m and not tech.search(m.group(2)) and d6(m.group(1)):
                conv.append((d6(m.group(1)), m.group(2).strip(),
                             re.sub(r"\*\([^)]*\)", "", m.group(3))))
    dated = sorted(os.path.basename(f)[:6] for f in glob.glob(f"{abs_f}/*.md")
                   if re.match(r"^\d{6}-", os.path.basename(f)))
    rel = [i for i in ins
           if not ASR.search(f"{i.get('summary','')} " + " ".join(str(t) for t in (i.get("tags") or [])))]
    return dict(meta=meta, ins=ins, ins_rel=rel, tasks=tasks, conv=conv,
                dated=dated, today=today,
                senaste=d6(dated[-1]) if dated else None,
                forsta=d6(dated[0]) if dated else None,
                months=sorted(Counter(x[:4] for x in dated).items())[-9:])

def facts_block(g, name):
    """Det tidskritiska — uträknat, aldrig gissat."""
    today, L = g["today"], []
    huvud = []
    m = g["meta"]
    if m.get("relationship"): huvud.append(f"**{m['relationship']}**")
    if m.get("role"):
        huvud.append(f"{m['role']}" + (f", {m['employer']}" if m.get("employer") else ""))
    if m.get("classification"): huvud.append(f"*{m['classification']}*")
    if g["senaste"]:
        a = (today - g["senaste"]).days
        huvud.append(f"senast **{g['senaste'].strftime('%-d/%-m')}**" +
                     (" *(idag)*" if a == 0 else f" *({a} dgr sedan)*" if a > 0
                      else f" *(bokat om {-a} dgr)*"))
    if huvud: L += [" · ".join(huvud), ""]

    if g["months"] and len(g["months"]) >= 3:
        sen = g["months"][-1][1]
        snitt = sum(v for _, v in g["months"][:-1]) / max(len(g["months"])-1, 1)
        if sen < snitt * 0.5:
            L += [f"⚠ **Takten har fallit** — {sen} denna månad mot {snitt:.1f} i snitt.", ""]

    forfallna = [t for t in g["tasks"] if d6(t.get("due")) and d6(t["due"]) < today]
    if forfallna:
        L += ["**Förfallet:**", ""]
        for t in sorted(forfallna, key=lambda t: str(t.get("due"))):
            dd = d6(t["due"])
            L.append(f"- [ ] {t.get('task') or t.get('title','?')} — "
                     f"**{(today-dd).days} dgr sen** *({dd.strftime('%-d/%-m')})*")
        L.append("")
    ovr = [t for t in g["tasks"] if t not in forfallna]
    if ovr:
        L += ["**Öppet:**", ""]
        for t in ovr:
            dd = d6(t.get("due"))
            L.append(f"- [ ] {t.get('task') or t.get('title','?')}" +
                     (f" *({dd.strftime('%-d/%-m')})*" if dd else ""))
        L.append("")
    return L

def build_prompt(g, name):
    rader = []
    for i in sorted(g["ins_rel"], key=lambda x: str(x.get("date")), reverse=True):
        rader.append(f"- {i.get('date')} [{i.get('type')}] {i.get('summary')}")
        if i.get("rationale"): rader.append(f"    varför: {str(i['rationale'])[:220]}")
    samtal = [f"- {d.strftime('%y%m%d')}: {t} | {b[:300]}" for d, t, b in g["conv"][:14]]
    return f"""Du skriver en NULÄGESBILD inför ett möte med {name}.

Skriv INTE en lista — skriv en bild i prosa. Svara på: var står relationen, vad är
olöst eller oenigt, vilka teman har utvecklats över tid.

Krav:
- Svenska, korrekt å ä ö. Inga emojis.
- Gruppera efter TEMA, aldrig efter datum.
- Namnge uttryckligen det som är olöst eller där parterna är oense.
- Citera konkreta detaljer (belopp, namn, datum) bara där de bär betydelse.
- Hitta inte på något som inte står i underlaget.
- Rubriker exakt: ## Läget · ## Det olösta · ## Teman över tid · ## Inför nästa samtal
- Högst 45 rader totalt. Hellre tätt än uttömmande.

INSIKTER ({len(g['ins_rel'])}):
{chr(10).join(rader)}

SAMTAL (senaste {len(samtal)}):
{chr(10).join(samtal)}"""

def ask_ollama(prompt):
    req = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                      "keep_alive": "20m", "options": {"temperature": 0.3, "num_ctx": 16384}})
    p = subprocess.run(["curl", "-s", "--max-time", "900", "-X", "POST",
                        f"{OLLAMA}/api/generate", "-H", "Content-Type: application/json",
                        "-d", req], capture_output=True, text=True)
    if p.returncode != 0: return None, "curl misslyckades"
    try:
        d = json.loads(p.stdout)
        return d.get("response", "").strip(), d.get("total_duration", 0)/1e9
    except Exception as e:
        return None, str(e)

def render(folder, facts_only=False):
    abs_f = folder if os.path.isabs(folder) else os.path.join(VAULT, folder)
    if not os.path.isdir(abs_f): return None
    slug = os.path.basename(abs_f.rstrip("/"))
    rel  = os.path.relpath(abs_f, VAULT)
    g = gather(abs_f)
    name = g["meta"].get("display_name") or slug
    if not (g["ins_rel"] or g["conv"]):
        return None

    L = [f"# Nuläge: {name}", ""]
    L += facts_block(g, name)

    bild, tid = (None, 0)
    if not facts_only:
        bild, tid = ask_ollama(build_prompt(g, name))
    if bild:
        L += ["---", "", bild, ""]
    elif not facts_only:
        # Modellen föll bort. Återanvänd förra bilden hellre än att lämna ett tomt
        # block — en åldrad bild är mer värd än ingen, så länge det står att den är det.
        aldre = None
        if os.path.exists(f"{abs_f}/.status/current.md"):
            g0 = open(f"{abs_f}/.status/current.md", encoding="utf-8").read()
            m0 = re.search(r"^## Läget\b.*?(?=^## Omfång)", g0, re.M | re.S)
            if m0: aldre = m0.group(0).rstrip()
        if aldre:
            L += ["---", "",
                  f"> ⚠ **Modellen svarade inte ({tid:.0f}s).** Bilden nedan är från "
                  f"föregående körning — fakta ovan är färska.", "", aldre, ""]
        else:
            L += ["---", "", f"*(modellen svarade inte efter {tid:.0f}s — "
                  f"kör `render_status.py {rel}` igen)*", ""]

    m = g["months"]
    L += ["---", "", "## Omfång", "",
          f"**{len(g['dated'])} dokument** " +
          (f"{g['forsta'].strftime('%-d/%-m %Y')} → {g['senaste'].strftime('%-d/%-m %Y')}"
           if g["dated"] else "") +
          f"  ·  **{len(g['ins_rel'])} insikter**" +
          (f" *(+{len(g['ins'])-len(g['ins_rel'])} om källmaterialet)*"
           if len(g['ins']) > len(g['ins_rel']) else "") +
          f"  ·  **{len(g['conv'])} samtal**", ""]
    if m: L += ["`" + "  ".join(f"{mlab(y)} {n}" for y, n in m) + "`", ""]
    relp = g["meta"].get("related") or []
    if relp:
        L += ["**Runt personen:** " + " · ".join(
            f"{r.get('name')} ({r.get('relation')})" +
            (f" *hörs som {', '.join(r['aliases'])}*" if r.get("aliases") else "")
            for r in relp if isinstance(r, dict)), ""]

    head = ["---", "typ: status",
            f"write_ownership: {'script' if facts_only else 'llm+script'}",
            "placement: per_folder",
            f"modell: {MODEL if bild else 'ingen'}",
            f"uppdaterad: {g['today'].strftime('%y%m%d')}", "---", "",
            "> **Fakta uträknade, bilden skriven.** Läs inför möte — parsa aldrig som källa.",
            f"> Underlag: `{rel}`. Skriv om efter varje samtal.", ""]
    out = f"{abs_f}/.status"; os.makedirs(out, exist_ok=True)
    dest = f"{out}/current.md"
    # En handskriven vy (write_ownership: llm utan +script) är gjord med en starkare
    # modell och får aldrig skrivas över av en batchkörning. Skyddet gäller även när
    # den lokala modellen faller bort — annars byts en bra bild mot ett tomt block.
    if os.path.exists(dest):
        gammal = open(dest, encoding="utf-8").read()
        if re.search(r"^write_ownership:\s*llm\s*$", gammal, re.M):
            return dest, len(g["dated"]), len(g["ins_rel"]), len(g["conv"]), -1
    open(dest, "w", encoding="utf-8").write("\n".join(head + L) + "\n")
    return dest, len(g["dated"]), len(g["ins_rel"]), len(g["conv"]), tid

def all_folders():
    t = sorted(glob.glob(f"{VAULT}/_contacts/*/") +
               glob.glob(f"{VAULT}/sonetel/meetings/management/*/"))
    return [x for x in t if not os.path.basename(x.rstrip("/")).startswith(".")]

def survey(f):
    name = os.path.basename(f.rstrip("/"))
    dated = sorted(os.path.basename(x)[:6] for x in glob.glob(f"{f}/*.md")
                   if re.match(r"^\d{6}-", os.path.basename(x)))
    ins = yload(f"{f}/_insights.yaml").get("insights") or []
    return name, (d6(dated[-1]) if dated else None), len(dated), len(ins)

def cmd_survey(mode, days):
    today = date.today(); rows = []
    for f in all_folders():
        name, last, nd, ni = survey(f)
        if not last:
            if mode == "stale": rows.append((None, name, nd, ni)); continue
            continue
        age = (today - last).days
        if mode == "stale" and age >= days: rows.append((age, name, nd, ni))
        if mode == "recent" and abs(age) <= days: rows.append((age, name, nd, ni))
    utan = [r for r in rows if r[0] is None]
    med = sorted((r for r in rows if r[0] is not None), key=lambda r: r[0],
                 reverse=(mode == "stale"))
    rub = f"TYSTNADE — {days}+ dagar" if mode == "stale" else f"AKTIVA — ±{days} dagar"
    print(f"{rub} ({len(med)} st)\n")
    for age, name, nd, ni in med:
        w = (f"om {-age} dgr" if age < 0 else "idag" if age == 0
             else "igår" if age == 1 else f"{age} dgr")
        print(f"  {w:>9}  {name:<34} {nd:>3} dok  {ni:>3} insikter")
    if utan:
        print(f"\nUTAN DATERAT UNDERLAG ({len(utan)}): " + ", ".join(n for _, n, _, _ in utan))
    print("\n(läser bara — inga filer skrivna)")

def main():
    a = sys.argv[1:]
    if not a: print(__doc__); return
    if a[0] in ("--stale", "--recent"):
        d = int(a[1]) if len(a) > 1 and a[1].isdigit() else (90 if a[0] == "--stale" else 7)
        cmd_survey(a[0][2:], d); return
    facts_only = a[0] == "--facts"
    if facts_only: a = a[1:]
    if a and a[0] == "--window":
        days = int(a[1]) if len(a) > 1 and a[1].isdigit() else 7
        today = date.today()
        targets = [f for f in all_folders()
                   if (lambda l: l and abs((today - l).days) <= days)(survey(f)[1])]
        print(f"±{days} dagar: {len(targets)} mappar\n")
    elif a:
        targets = a
    else:
        print(__doc__); return
    for t in targets:
        r = render(t, facts_only)
        if r:
            dest, nd, ni, nc, tid = r
            ts = f"  {tid:.0f}s" if tid else ""
            print(f"  {os.path.relpath(dest, VAULT)}  ({nd} dok, {ni} insikter, {nc} samtal){ts}")
        else:
            print(f"  {t}: hoppad (inget underlag)")

if __name__ == "__main__":
    main()
