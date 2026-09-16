#!/usr/bin/env python3
"""
Todoist <-> daglig-triage sync (local integration, NOT core-skills).

Two levels, both with a human gate:
  push       - level 1: mirror today/tomorrow actionable triage items to Todoist
               (board project, columns Idag/Imorgon). Preview before creating.
  reconcile  - level 2: read Todoist back; for tasks completed there, ASK before
               marking the matching triage line [x]. Never auto-merges.

Config comes from the vault's _config/base.yaml (integrations.todoist).
Token comes from ~/bin/todoist-triage/.env (TODOIST_TOKEN) - never the vault.
Triage file path is read from _inbox/_inbox.yaml (registered working_doc),
so a rename that updates the registration keeps working.

CLOSE vs DELETE (important — this caused a re-tick loop once):
  - A Todoist CLOSE puts the task in the COMPLETED log. reconcile reads that log
    as "the user finished it" and ticks the matching triage row [x].
  - So: only CLOSE a task when it genuinely IS done (the user checked it, or the
    triage row is [x]). To remove a duplicate/leftover, DELETE it — a delete does
    NOT enter the completed log, so it won't be misread as a completion.
  - Any external cleanup script MUST follow the same rule: delete duplicates,
    never close them.

Usage:
  sync.py sync [--yes]        # THE everyday command — full two-way mirror:
                              #   pull Todoist completions → tick triage [x],
                              #   then create missing + MOVE mis-columned +
                              #   close orphan duplicates. Just say "sync".
  sync.py push [--yes]        # create-only (subset of sync); rarely needed
  sync.py reconcile [--yes]   # completions-only, with per-step prompts
  sync.py status             # read-only: what's here vs there
"""
import sys, os, json, re, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.todoist.com/api/v1"

# "Links"-sektionen ägs av linkedin-fetch (LinkedIn-URL:er att processa), INTE av
# triage-synken. Sync ignorerar den så länkarna aldrig speglas som uppgifter.
LINKS_SECTION = "6hGvGP5vH9g3RPXH"

# --- vault discovery -------------------------------------------------------
VAULT = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Tomas"
)
BASE_CFG = os.path.join(VAULT, "_config", "base.yaml")
INBOX_YAML = os.path.join(VAULT, "_inbox", "_inbox.yaml")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_token():
    envp = os.path.join(HERE, ".env")
    if not os.path.exists(envp):
        die(f"missing {envp} (TODOIST_TOKEN=...)")
    for line in open(envp):
        if line.startswith("TODOIST_TOKEN="):
            return line.split("=", 1)[1].strip()
    die("TODOIST_TOKEN not found in .env")


def tiny_yaml_get(path, *keys):
    """Minimal nested-scalar reader; avoids a yaml dependency for a few keys."""
    if not os.path.exists(path):
        die(f"missing config {path}")
    lines = open(path).read().splitlines()
    depth = 0
    target = list(keys)
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key = raw.strip().split(":", 1)[0].strip().strip('"')
        if depth < len(target) and key == target[depth]:
            rest = raw.strip().split(":", 1)[1] if ":" in raw.strip() else ""
            # strip inline comment, whitespace, quotes
            rest = rest.split("#", 1)[0].strip().strip('"').strip("'").strip()
            if depth == len(target) - 1:
                return rest or None
            depth += 1
    return None


def triage_path():
    # read the registered working_doc filename from _inbox.yaml
    fname = "daglig-triage.md"
    if os.path.exists(INBOX_YAML):
        for line in open(INBOX_YAML):
            m = re.search(r"file:\s*(\S*triage\S*\.md)", line)
            if m:
                fname = m.group(1)
                break
    return os.path.join(VAULT, "_inbox", fname)


# --- HTTP ------------------------------------------------------------------
def api(method, path, token, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        die(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:200]}")


def results(d):
    return d.get("results", d) if isinstance(d, dict) else d


SV_DAYS = ["mån", "tis", "ons", "tors", "fre", "lör", "sön"]


def refresh_section_labels(token, sect):
    """Rename Idag/Imorgon sections to carry today's/tomorrow's real date, so a
    label never lies after midnight. 'Denna vecka' keeps its plain name."""
    import datetime
    d = datetime.date.today()
    t = d + datetime.timedelta(days=1)
    labels = {
        "Idag": f"Idag ({SV_DAYS[d.weekday()]} {d.day}/{d.month})",
        "Imorgon": f"Imorgon ({SV_DAYS[t.weekday()]} {t.day}/{t.month})",
    }
    for key, sid in (("Idag", sect.get("Idag")), ("Imorgon", sect.get("Imorgon"))):
        if sid:
            api("POST", f"/sections/{sid}", token, {"name": labels[key]})


# --- triage parsing --------------------------------------------------------
IDAG_RE = re.compile(r"idag", re.I)
IMORGON_RE = re.compile(r"imorgon|imorron|torsdag", re.I)

# Rows blocked on someone else — "doesn't affect me yet". These go to their own
# Väntar column so they stop cluttering the active lists. Matched against the
# WHOLE line (not the clipped title), since the wait-word often sits after a dash.
WAIT_RE = re.compile(
    r"\b(väntar|inväntar|avvaktar|bevaka[r]?)\b|inget svar(\s+än)?|håller koll",
    re.I,
)


# Lines that are status-with-a-remainder or pure pointers, not actions.
# Anchored at the very start and word-bounded: a line must BEGIN with the status
# word. Avoids false positives like "Verifiera resync/rebuild klar" (an action
# that merely contains "klar").
SKIP_HEAD = re.compile(
    r"^\**(BETALD|KLART|KLAR|GENOMFÖRD|Allt om|Senare|Mobile app|Planerna)\b",
    re.I,
)


# Sub-blocks inside "## DENNA VECKA" that are actual week work. Everything else
# in that section (GOA-UPPDRAGET, the Sonetel watch-lists, MIN prioritetslista)
# is reference material for meetings and stays out of Todoist.
THISWEEK_SUBS = ("admin/rester", "ungarna", "familj", "möten att verifiera",
                 "ekonomi / fakturor")

ID_RE = re.compile(r"\{([0-9a-f]{4})\}")   # stable identity token: {a3f9}

# Structured deadline token: ⏰260910 (YYMMDD). Prose dates ("före avresan 30/8")
# cannot be checked mechanically — this can, on every sync.
#
# Why: the 260907 audit found seven stale headings and eleven passed deadlines
# that had sat unnoticed for up to 40 days. The weekly routine existed but was
# skipped during a travel week. A check that runs on every sync needs nobody to
# remember it.
DEADLINE_RE = re.compile(r"⏰(\d{6})")


def extract_deadline(line):
    """Return date from a ⏰YYMMDD token, or None. Invalid dates are ignored."""
    m = DEADLINE_RE.search(line)
    if not m:
        return None
    from datetime import datetime
    try:
        return datetime.strptime(m.group(1), "%y%m%d").date()
    except ValueError:
        return None


WEEK_RE = re.compile(r"\(\s*v\.\s*(\d{1,2})\s*\)", re.I)


def check_dates(text):
    """Warn about passed ⏰-deadlines and a stale (v.NN) heading.

    Returns (overdue, week_warning). Reports only — never edits the triage.
    An open row whose deadline has passed is the single failure mode that cost
    the most in the audit, so it is surfaced before anything else in a sync.
    """
    from datetime import date
    today = date.today()
    overdue, week_warning = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("- [ ]"):
            continue
        d = extract_deadline(line)
        if d and d < today:
            title = re.sub(r"[*_`]", "", line[5:].strip())
            title = ID_RE.sub("", DEADLINE_RE.sub("", title)).strip(" .·—-")
            overdue.append(((today - d).days, d, title[:70]))
    want = today.isocalendar()[1]
    for raw in text.splitlines():
        if raw.startswith("## ") and "DENNA VECKA" in raw:
            m = WEEK_RE.search(raw)
            if m and int(m.group(1)) != want:
                week_warning = (int(m.group(1)), want)
            break
    overdue.sort(reverse=True)
    return overdue, week_warning


def report_dates_yaml():
    """Datumkontroll mot _tasks.yaml — förfallna deadlines på öppna uppgifter."""
    import yaml
    from datetime import date
    doc = yaml.safe_load(open(tasks_yaml_path(), encoding="utf-8"))
    today = date.today()
    over = []
    for t in doc.get("tasks", []):
        if t.get("status") != "open" or not t.get("due"):
            continue
        d = str(t["due"])
        try:
            dd = date(2000 + int(d[:2]), int(d[2:4]), int(d[4:6]))
        except ValueError:
            continue
        if dd < today:
            over.append(((today - dd).days, dd, t["task"][:70], t["id"]))
    over.sort(reverse=True)
    if over:
        print(f"  \u26a0 {len(over)} förfallna deadlines:")
        for days, dd, task, tid in over[:10]:
            print(f"      {dd.strftime('%-d/%-m')} ({days} dgr sen)  #{tid} {task}")
        if len(over) > 10:
            print(f"      … och {len(over) - 10} till")
    return bool(over)


def report_dates(text):
    """Print the date audit. Called at the top of sync and status."""
    overdue, week = check_dates(text)
    if week:
        print(f"  \u26a0 rubriken säger v.{week[0]} — det är v.{week[1]}")
    if overdue:
        print(f"  \u26a0 {len(overdue)} förfallna deadlines:")
        for days, d, title in overdue[:10]:
            print(f"      {d.strftime('%-d/%-m')} ({days} dgr sen)  {title}")
        if len(overdue) > 10:
            print(f"      … och {len(overdue) - 10} till")
    return bool(overdue or week)


def extract_id(line):
    """Return the {xxxx} id token in a triage line, or None."""
    m = ID_RE.search(line)
    return m.group(1) if m else None


def gen_id(existing):
    """Generate a fresh 4-hex-char id not in `existing`. Deterministic-free:
    derived from a counter + content hash so it needs no Math.random/Date."""
    import hashlib
    seed = 0
    while True:
        h = hashlib.sha1(f"{len(existing)}-{seed}".encode()).hexdigest()[:4]
        if h not in existing:
            return h
        seed += 1


def line_key(title, tag="", tid=None):
    """Stable identity for a triage line.

    If the line carries an explicit **{id} token** (tid), THAT is the identity —
    text can be reworded freely without breaking the match. This is the reliable
    path. Falls back to the old tag+title-stub hash only for un-stamped lines
    (which sync stamps on first push, so the fallback is transitional)."""
    import hashlib
    if tid:
        return f"id:{tid}"
    stub = " ".join(re.sub(r"\s+", " ", title.lower()).strip().split()[:3])
    basis = f"{tag.strip().lower()}|{stub}" if tag.strip() else title.lower()
    norm = re.sub(r"\s+", " ", basis).strip()
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def stamp_ids(text):
    """Insert a {xxxx} stable-id token into any actionable '- [ ]' line that
    lacks one. Returns (new_text, changed:bool). An actionable line here = an
    open bullet carrying a leading **[tag]** (all real triage rows have one).
    The id goes at the END of the line so it never collides with [tags]/[links].
    Idempotent: lines that already have {id} are untouched."""
    existing = set(ID_RE.findall(text))
    out, changed = [], False
    for line in text.split("\n"):
        s = line.rstrip()
        is_actionable = (re.match(r"\s*- \[ \] \*\*\[", s) is not None)
        if is_actionable and not ID_RE.search(s):
            new = gen_id(existing)
            existing.add(new)
            s = f"{s} {{{new}}}"
            changed = True
        out.append(s if s else line)
    return "\n".join(out), changed


def tasks_yaml_path():
    """_inbox/_tasks.yaml — sanningen sedan 260907 (YAML ersatte markdown)."""
    import os
    return os.path.join(os.path.dirname(triage_path()), "_tasks.yaml")


def yaml_done_keys():
    """state-nycklar för poster som YAML markerat done.

    Sync stängde tidigare aldrig en task när sanningen sa klar — bara triage→Todoist
    för öppna poster och Todoist→triage för avbockningar. En post som bockades i
    YAML låg därför kvar i Todoist i all evighet (upptäckt 260910: Berget AI).
    """
    import yaml
    doc = yaml.safe_load(open(tasks_yaml_path(), encoding="utf-8"))
    out = []
    for t in doc.get("tasks", []):
        if t.get("status") not in ("done", "cancelled"):
            continue
        out.append(f"id:{t['triage_id']}" if t.get("triage_id") else f"id:y{t['id']:03d}")
    return out


def parse_actionable_yaml():
    """Läs uppgifter ur _tasks.yaml istället för markdown.

    Returnerar samma form som parse_actionable — [(key, section, title)] —
    så resten av sync-logiken är oförändrad.

    Kolumnval: due-datum styr Idag/Imorgon, väntar-ord ger Väntar,
    P0/P1 utan datum ger Denna vecka, allt annat Senare.
    """
    import yaml
    from datetime import date, timedelta
    doc = yaml.safe_load(open(tasks_yaml_path(), encoding="utf-8"))
    today, tomorrow = date.today(), date.today() + timedelta(days=1)
    out = []
    for t in doc.get("tasks", []):
        if t.get("status") != "open":
            continue
        title = t["task"]
        if t.get("context"):
            title = f"{t['context']} — {title}"
        d = t.get("due")
        dd = None
        if d:
            d = str(d)
            try:
                dd = date(2000 + int(d[:2]), int(d[2:4]), int(d[4:6]))
            except ValueError:
                dd = None
        blob = " ".join([title] + [str(n) for n in (t.get("notes") or [])])
        if dd and dd < today:
            # FÖRST — "dd <= today+7" fångar annars även förflutna datum, vilket
            # gjorde grenen nedan oåtkomlig. Förfallet slår även väntar-regeln:
            # en post som passerat sitt datum har redan kostat något, oavsett
            # om den väntar på någon annan.
            sec = "Förfallet"
        elif WAIT_RE.search(blob):
            sec = "Väntar"
        elif dd == today:
            sec = "Idag"
        elif dd == tomorrow:
            sec = "Imorgon"
        elif dd and dd <= today + timedelta(days=7):
            sec = "Denna vecka"
        elif t.get("priority") in ("P0", "P1"):
            sec = "Denna vecka"
        else:
            # Utan datum och utan P0/P1 hör posten inte i Todoist. Före
            # YAML-migreringen låg dessa utanför syncen genom att ligga i
            # block som parse_actionable inte läste; nu måste regeln vara
            # explicit — annars skapas 72 tasks av referensmaterial.
            sec = None
        if sec is None:
            continue
        # state-nycklarna bär prefixet "id:" — behåll formatet så de 119
        # befintliga Todoist-länkarna håller genom YAML-migreringen
        key = f"id:{t['triage_id']}" if t.get("triage_id") else f"id:y{t['id']:03d}"
        out.append((key, sec, title))
    return out


def parse_actionable(text):
    """
    Only open '- [ ]' bullets inside genuinely actionable blocks (PRIO + the
    '### Denna vecka' sub-block). Excludes meeting-prep / economy-reconcile /
    board rubrics. Returns [(key, section, title)].
    """
    out = []
    section = None      # "prio" | "followups" | "later" | None — set by ## headings
    sub_day = None      # column hint from a ### sub-heading inside PRIO
    later_active = False # inside SENARE, only the "Efter semestern" sub-block counts
    fu_later = False    # inside UPPFÖLJNINGAR, an "Efter sommaren/semestern" sub-block
                        # routes to the Efter semestern column, not Uppföljningar
    tw_active = False   # inside DENNA VECKA, only THISWEEK_SUBS sub-blocks push
    fu_thisweek = False # inside UPPFÖLJNINGAR, a "Denna vecka"-named sub-block routes
                        # to the Denna vecka column (folded-in post-vacation)
    for line in text.splitlines():
        h = line.strip()
        # A ## heading (re)selects the section. ### sub-headings NEVER change the
        # section — so IDAG / Denna vecka / E-post / Personer all stay in scope.
        if h.startswith("## "):
            if h.startswith("## PRIO"):
                section = "prio"
            elif h.startswith("## UPPFÖLJNINGAR"):
                section = "followups"
            elif h.startswith("## EJ DENNA VECKA"):
                # Only a "### Efter semestern" sub-block inside SENARE is pushed
                # (to Väntar). Everything else here (husbil, hemautomation, …)
                # stays out of Todoist — gated by later_active below.
                section = "later"
            elif h.startswith("## DENNA VECKA"):
                # Own branch, tested AFTER "EJ DENNA VECKA" so the negation wins
                # its own rows. NOT the whole section: it also holds reference
                # lists (GOA agenda items, the Sonetel watch-lists) that are
                # deliberately NOT week tasks. Only the sub-blocks in
                # THISWEEK_SUBS below are pushed — see tw_active.
                section = "thisweek"
            else:
                section = None
            sub_day = None
            tw_active = False
            later_active = False
            fu_later = False
            fu_thisweek = False
            continue
        # Inside DENNA VECKA: only genuine week-work sub-blocks push. The
        # section also carries reference lists (GOA agenda, Sonetel watch-lists,
        # "MIN prioritetslista") that are context for meetings, not tasks —
        # pushing them buried the real list under ~30 rows.
        if h.startswith("### ") and section == "thisweek":
            hl = h.lower()
            tw_active = any(w in hl for w in THISWEEK_SUBS)
            continue
        if section == "thisweek" and not tw_active:
            continue
        # Inside SENARE: every sub-block pushes now (260830). Previously only an
        # "Efter semestern" block did, which left 9 rows in "Senare" invisible
        # in Todoist — the board did not show what was deliberately postponed.
        if h.startswith("### ") and section == "later":
            later_active = True
            continue
        # Inside UPPFÖLJNINGAR: a "Denna vecka"-named sub-block routes to the Denna
        # vecka column; an "Efter sommaren/semestern" sub-block routes to the Efter
        # semestern column (same bucket as SENARE's), not Uppföljningar.
        if h.startswith("### ") and section == "followups":
            hl = h.lower()
            fu_thisweek = "denna vecka" in hl
            fu_later = (not fu_thisweek) and re.search(r"efter (sommaren|semester)", hl) is not None
            continue
        # ### sub-heading inside PRIO routes its rows by day-word in the heading:
        #   "IDAG" -> Idag · "IMORGON" -> Imorgon · any OTHER named weekday
        #   (TISDAG, ONSDAG…) -> Denna vecka (it's further out than tomorrow).
        # Rows themselves need not repeat the day-word.
        if h.startswith("### ") and section == "prio":
            hl = h.lower()
            if "idag" in hl:
                sub_day = "Idag"
            elif re.search(r"imorgon|imorron", hl):
                sub_day = "Imorgon"
            elif "denna vecka" in hl or "admin/rester" in hl:
                sub_day = "Denna vecka"
            elif re.search(r"söndag|måndag|tisdag|onsdag|torsdag|fredag|lördag", hl):
                sub_day = "Denna vecka"
            else:
                sub_day = None
            continue
        if section is None:
            continue
        # In SENARE only rows under an active "Efter semestern" sub-block count.
        if section == "later" and not later_active:
            continue
        followups = section == "followups"
        m = re.match(r"- \[ \] (.+)", h)
        if not m:
            continue
        content = m.group(1)
        body = re.sub(r"^\*\*\[[^\]]*\]\*\*\s*", "", content)
        body = re.sub(r"^\[[^\]]*\]\s*", "", body).lstrip("* ")
        if SKIP_HEAD.match(body) or SKIP_HEAD.match(content):
            continue
        # The leading [tag] carries the identity (who/what). For followups it's
        # the only reliable label — "Placeholder"/"Samtal genomfört" alone are
        # useless — so keep the tag as a prefix there. For PRIO/week the action
        # text is self-explanatory, so the tag is dropped as before.
        tagm = re.match(r"\*\*\[([^\]]+)\]\*\*|\[([^\]]+)\]", content)
        tag = (tagm.group(1) or tagm.group(2)).strip() if tagm else ""
        body = ID_RE.sub("", content)   # drop {id} so it never leaks into the title
        body = re.sub(r"\*\*|`", "", body)
        body = re.sub(r"^\[[^\]]*\]\s*", "", body)
        body = re.sub(r"\[|\]", "", body)
        body = re.split(r"\.\s|\s[—–]\s|\s--\s|\s\(", body)[0]
        body = re.sub(r"\s+", " ", body).strip().rstrip(".:")
        if followups and tag:
            # tag already names the person/topic; append the short body only if
            # it adds something beyond a generic placeholder word
            generic = body.lower() in ("placeholder", "samtal genomfört", "")
            title = tag if generic else f"{tag}: {body}"
        else:
            title = body
        if not title:
            continue
        tid = extract_id(content)   # {a3f9} stable id if present, else None
        if WAIT_RE.search(content):
            # Blocked on someone else — this wins over any block placement. A row
            # that says "väntar på X" is not this week's work wherever it sits;
            # without this it stayed in Denna vecka and buried the active list.
            sec = "Väntar"
        elif sub_day == "Denna vecka":
            # a PRIO sub-block explicitly named "Denna vecka" routes there.
            sec = "Denna vecka"
        elif fu_thisweek:
            # UPPFÖLJNINGAR sub-block folded into the current week
            sec = "Denna vecka"
        elif section == "later" or fu_later:
            # SENARE = medvetet framflyttat. Egen kolumn sedan 260830 så tavlan
            # visar vad som ligger på is, i stället för att blanda in det i veckan.
            sec = "Senare"
        elif IDAG_RE.search(content) or sub_day == "Idag":
            sec = "Idag"
        elif IMORGON_RE.search(content) or sub_day == "Imorgon":
            sec = "Imorgon"
        elif WAIT_RE.search(content):
            # blocked on someone else — route out of the active lists
            sec = "Väntar"
        elif followups:
            sec = "Uppföljningar"
        else:
            sec = "Denna vecka"
        out.append((line_key(title, tag, tid), sec, title))
    return out


# --- state (the memory that makes it a real sync) --------------------------
# Lives in the VAULT (iCloud-synced) so push on one Mac and reconcile on the
# other share the same link memory. Only task IDs, no secrets - safe to sync.
# (.env with the token stays LOCAL and machine-bound - never in the vault.)
STATE_PATH = os.path.join(VAULT, "_config", "integrations", "todoist-state.json")


def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {"links": {}}   # key -> {task_id, section, title}


def save_state(st):
    json.dump(st, open(STATE_PATH, "w"), ensure_ascii=False, indent=2)


def sections_cfg():
    return {
        "Förfallet": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "forfallet"),
        "Idag": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "idag"),
        "Imorgon": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "imorgon"),
        "Denna vecka": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "denna_vecka"),
        "Uppföljningar": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "uppfoljningar"),
        "Väntar": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "vantar"),
        "Senare": tiny_yaml_get(BASE_CFG, "integrations", "todoist", "sections", "senare"),
        # Efter semestern + Efter Färöarna borttagna 17/8 (hemma — inflyttade i Denna vecka)
    }


def due_for_section(sec):
    """Due date implied by a triage column, as YYYY-MM-DD — or None.

    The column IS the schedule, so the task carries the matching due date and
    Todoist's own Today/Upcoming filters work. Only the day-bound columns get a
    date; Denna vecka / Uppföljningar / Väntar are deliberately undated (they
    are buckets, not days — dating them would make everything scream at once).

    A manually set due date on an existing task is never overwritten (see
    _apply_due): the human's date wins over the column's.
    """
    from datetime import date, timedelta   # date only — no clock (resume-safe)
    today = date.today()
    if sec == "Idag":
        return today.isoformat()
    if sec == "Imorgon":
        return (today + timedelta(days=1)).isoformat()
    return None


def _apply_due(token, tid, sec, existing=None):
    """Set the column's due date on a task. Returns True if it wrote.

    Skips when the column implies no date, and when the task already carries a
    due date that differs from the column's — that is a hand-set date and it is
    not ours to clobber.
    """
    want = due_for_section(sec)
    if not want:
        return False
    have = (existing or {}).get("due") or {}
    have_date = have.get("date")
    if have_date == want:
        return False
    if have_date and existing is not None and have_date > want:
        return False          # future hand-set date — leave it alone
    api("POST", f"/tasks/{tid}", token, {"due_date": want})
    return True


def live_tasks(token, pid):
    """All open tasks in the project — FOLLOWING PAGINATION.

    The API returns 50 per page by default and hands back a `next_cursor`.
    Without following it, tasks beyond the first page look "not live" — so a
    row linked to one of them gets recreated on every sync, forever, and the
    fresh task lands on the invisible page too. That loop appeared the day the
    project crossed 50 open tasks. Always drain the cursor.
    """
    out, cursor = {}, None
    while True:
        path = f"/tasks?project_id={pid}&limit=200"
        if cursor:
            path += f"&cursor={cursor}"
        raw = api("GET", path, token)
        for t in results(raw):
            out[t["id"]] = t
        cursor = raw.get("next_cursor") if isinstance(raw, dict) else None
        if not cursor:
            return out


# --- commands --------------------------------------------------------------
def cmd_push(token, yes):
    pid = tiny_yaml_get(BASE_CFG, "integrations", "todoist", "project_id")
    sect = sections_cfg()
    if not pid:
        die("no project_id in base.yaml")
    refresh_section_labels(token, sect)
    st = load_state()
    items = parse_actionable_yaml()
    live = live_tasks(token, pid)

    # An item is already handled if state links its key to a task that STILL
    # exists in Todoist (even if you split/renamed/moved it there - the link,
    # not the title, is what counts). Prune dead links so a re-added item works.
    for k in list(st["links"]):
        if st["links"][k]["task_id"] not in live:
            del st["links"][k]

    plan = [(k, sec, title) for k, sec, title in items if k not in st["links"]]
    print(f"\nFörhandsgranskning — {len(plan)} nya tasks (av {len(items)} i triagen):\n")
    for _, sec, title in plan:
        print(f"  [{sec}]  {title}")
    if not plan:
        print("  (allt är redan pushat — state känner igen det, även delat/flyttat i Todoist)")
        return
    if not yes:
        if input("\nSkapa dessa i Todoist? [j/N] ").strip().lower() not in ("j", "y"):
            print("Avbrutet — inget skapat.")
            return
    for k, sec, title in plan:
        body = {"content": title, "project_id": pid, "section_id": sect.get(sec)}
        due = due_for_section(sec)
        if due:
            body["due_date"] = due          # column = schedule, so Todoist filters work
        r = api("POST", "/tasks", token, body)
        st["links"][k] = {"task_id": r["id"], "section": sec, "title": title}
        print(f"  + {sec}: {title}")
    save_state(st)
    print("\nKlart.")


def cmd_reconcile(token, yes):
    """Two-way check, using state + the reliable active-tasks endpoint only.
    A linked task that is no longer active = you completed (or deleted) it in
    Todoist -> propose [x] on its triage line. A live task with no state link =
    you added it in Todoist -> report for manual add. No completed-endpoint."""
    pid = tiny_yaml_get(BASE_CFG, "integrations", "todoist", "project_id")
    tp = triage_path()
    triage = open(tp).read()
    lines = triage.splitlines()
    st = load_state()
    live = live_tasks(token, pid)          # active tasks only
    linked_ids = {v["task_id"] for v in st["links"].values()}

    # (1) links whose task has vanished from the active list -> done in Todoist
    gone = {k: v for k, v in st["links"].items() if v["task_id"] not in live}
    to_check = []
    for k, v in gone.items():
        for i, line in enumerate(lines):
            if line.strip().startswith("- [ ]") and line_key_matches(line, k):
                to_check.append((v["title"], k, i))
                break

    # (2) active tasks with no state link -> added by you in Todoist.
    #     Skip the "Links" section — that's linkedin-fetch's inflow, not triage.
    untracked = [t for tid, t in live.items()
                 if tid not in linked_ids and t.get("section_id") != LINKS_SECTION]

    # (3) triage line now [x] (or gone) but its task is still OPEN in Todoist
    #     -> you closed it on the triage side; Todoist needs cleaning up.
    open_keys = {k for k, _, _ in parse_actionable(triage)}
    stale = []
    for k, v in st["links"].items():
        if v["task_id"] in live and k not in open_keys:
            stale.append((v["title"], k, v["task_id"]))

    if not to_check and not untracked and not stale:
        print("Inget att stämma av — triage och Todoist är i synk.")
        return

    if to_check:
        print(f"\n① Klara i Todoist → föreslår [x] i triagen ({len(to_check)}):")
        for title, _, _ in to_check:
            print(f"    ✓ {title}")
    if untracked:
        print(f"\n② Nytt i Todoist (finns ej i triagen) — lägg till för hand ({len(untracked)}):")
        for t in untracked:
            print(f"    + {t.get('content')}")
    if stale:
        print(f"\n③ Klart i TRIAGEN men fortfarande öppet i Todoist ({len(stale)}):")
        for title, _, _ in stale:
            print(f"    ✗ {title}")

    if to_check:
        if yes or input("\nMarkera ①-raderna [x] i triagen? [j/N] ").strip().lower() in ("j", "y"):
            for _, k, i in to_check:
                lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
                st["links"].pop(k, None)   # link is done, forget it
            open(tp, "w").write("\n".join(lines) + ("\n" if triage.endswith("\n") else ""))
            save_state(st)
            print(f"  → {len(to_check)} rader markerade. Kör /inbox triage refresh för arkivering.")
        else:
            print("  → ① hoppades över.")
    if stale:
        if yes or input("\nStäng ③ i Todoist (de är klara i triagen)? [j/N] ").strip().lower() in ("j", "y"):
            for title, k, tid in stale:
                api("POST", f"/tasks/{tid}/close", token)
                st["links"].pop(k, None)
                print(f"    → stängd i Todoist: {title}")
            save_state(st)
        else:
            print("  → ③ hoppades över.")
    if untracked:
        print("\n② hanteras för hand — säg till om du vill att jag lägger in dem i triagen.")


# Hur långt bakåt completed-loggen läses. 30 dgr täcker varje rimlig lucka
# mellan två syncar utan att svaret blir stort.
#
# ⚠ Varför tidsfönster och inte bara limit=200 (bet skarpt 260916):
# /tasks/completed returnerar projektets logg utan ordningsgaranti och gav
# next_cursor=None trots fullt svar (200 rader). När loggen passerat 200 poster
# föll dagens completions utanför — sync läste dem aldrig hem, tolkade dem som
# "saknas i Todoist" och SKAPADE OM 8 tasks som just bockats av.
# /tasks/completed/by_completion_date sorterar nyast först OCH paginerar korrekt.
COMPLETED_WINDOW_DAYS = 30


def _completed_task_ids(token, pid):
    """Task-ids that appear in Todoist's COMPLETED log (genuinely checked off).
    This is the authority for 'the user completed it' — distinct from a task
    merely being absent from the open list (which also happens on delete or when
    a task is closed for cleanup). Returns a set of task_ids. Fail-soft: empty
    set on API error, so a transient failure never mass-ticks the triage."""
    since = (datetime.now(timezone.utc)
             - timedelta(days=COMPLETED_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    until = (datetime.now(timezone.utc)
             + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        out, cursor = set(), None
        while True:
            path = (f"/tasks/completed/by_completion_date?project_id={pid}"
                    f"&since={since}&until={until}&limit=200")
            if cursor:
                path += f"&cursor={cursor}"
            raw = api("GET", path, token)
            items = raw.get("items", raw.get("results", raw)) if isinstance(raw, dict) else raw
            # by_completion_date bär id:t i "id"; den gamla /tasks/completed
            # bar det i "task_id". Ta emot båda så fältnamnet aldrig tystar
            # hela inläsningen igen.
            out |= {x.get("task_id") or x.get("id")
                    for x in (items or []) if (x.get("task_id") or x.get("id"))}
            cursor = raw.get("next_cursor") if isinstance(raw, dict) else None
            if not cursor:
                return out
    except Exception:
        return set()


def _pull_completions(token, live, st, completed_ids):
    """Todoist → triage half. Tick a '- [ ]' line ONLY when its linked task is in
    the COMPLETED log (completed_ids) — i.e. the user genuinely checked it off in
    Todoist. A task that is merely absent from `live` (deleted, or closed for
    cleanup) is NOT treated as done: its link is pruned but the triage row is left
    untouched. This is the fix for the loop where closing a task for housekeeping
    was misread as 'user completed it'. Still key-matched, never title-guessed."""
    tp = triage_path()
    triage = open(tp).read()
    lines = triage.splitlines()
    gone = {k: v for k, v in st["links"].items() if v["task_id"] not in live}
    ticked = []
    for k, v in gone.items():
        genuinely_done = v["task_id"] in completed_ids
        if genuinely_done:
            for i, line in enumerate(lines):
                if line.strip().startswith("- [ ]") and line_key_matches(line, k):
                    lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
                    ticked.append(v["title"])
                    break
        st["links"].pop(k, None)   # link resolved either way (done or gone)
    if ticked:
        open(tp, "w").write("\n".join(lines) + ("\n" if triage.endswith("\n") else ""))
    return ticked


def cmd_sync(token, yes):
    """Full two-way mirror in one shot — the everyday command.

    Todoist → triage first: tasks you completed in Todoist tick their triage
    line (the reconcile half).  Then triage → Todoist: create missing, MOVE
    mis-columned tasks (push never moves — this is what a day-roll needs), and
    close orphan duplicates. Order matters: pull completions BEFORE mirroring
    out, so a just-ticked row isn't recreated.
    """
    pid = tiny_yaml_get(BASE_CFG, "integrations", "todoist", "project_id")
    sect = sections_cfg()
    if not pid:
        die("no project_id in base.yaml")
    refresh_section_labels(token, sect)
    # stamp {id} into any un-stamped actionable line FIRST — makes identity stable
    # regardless of later text edits (fixes the recurring duplicate/miss problem).
    report_dates_yaml()
    st = load_state()
    live = live_tasks(token, pid)
    id2sec = {v: k for k, v in sect.items()}

    # --- Todoist → triage: pull completions (reconcile half) ---
    # A task is "done" only if it's in the COMPLETED log, not merely absent from
    # live — so closing a task for cleanup no longer ticks its triage row.
    completed_ids = _completed_task_ids(token, pid)
    ticked = _pull_completions(token, live, st, completed_ids)

    # --- YAML done → stäng i Todoist ---
    # CLOSE, inte DELETE: posten ÄR gjord, så completed-loggen är rätt plats. Den
    # motsatta regeln (delete vid städning) gäller dubbletter och rester.
    stangda = []
    for k in yaml_done_keys():
        v = st["links"].get(k)
        if not v or v.get("task_id") not in live:
            continue
        api("POST", f"/tasks/{v['task_id']}/close", token)
        stangda.append(v.get("title", k)[:60])
        del st["links"][k]
    if stangda:
        print(f"  STÄNGDA i Todoist ({len(stangda)}) — YAML säger klar:")
        for t in stangda:
            print(f"    ✓ {t}")
        save_state(st)
        live = live_tasks(token, pid)

    # re-read triage AFTER ticking, so the mirror-out below sees the new [x]s
    items = parse_actionable_yaml()

    # prune links whose task no longer exists in Todoist
    for k in list(st["links"]):
        if st["links"][k]["task_id"] not in live:
            del st["links"][k]

    key2sec = {k: sec for k, sec, _ in items}
    key2title = {k: title for k, sec, title in items}
    triage_titles = set(key2title.values())

    # (1) CREATE — triage keys with no live link
    creates = [(k, sec, t) for k, sec, t in items if k not in st["links"]]
    # (2) MOVE — linked task sits in a different column than the triage says
    moves = []
    for k, sec, title in items:
        link = st["links"].get(k)
        if not link:
            continue
        t = live.get(link["task_id"])
        if t and id2sec.get(t.get("section_id")) != sec:
            moves.append((link["task_id"], sec, title,
                          id2sec.get(t.get("section_id"), "?")))
    # (2b) DUE-DATES — every task in a day-bound column carries that day's date,
    #      so Todoist's own Today/Upcoming filters line up with the triage columns.
    #      Runs every sync: backfills older tasks AND rolls the date over at
    #      midnight. Only touches undated tasks — a hand-set date is the human's.
    due_fixes = []
    for _k, _sec, _title in items:
        _link = st["links"].get(_k)
        _want = due_for_section(_sec)
        if not _link or not _want:
            continue
        _t = live.get(_link["task_id"])
        if not _t:
            continue
        _have = (_t.get("due") or {}).get("date")
        # Undated -> take the column's date. Dated with a PAST date while the row
        # still sits in a day-bound column -> roll it forward: a leftover from
        # yesterday is today's work, not an overdue task. A FUTURE date is
        # hand-set (e.g. Airalo pinned to Saturday) and is never touched.
        if not _have or _have < _want:
            due_fixes.append((_link["task_id"], _sec, _title))

    # (3) CLOSE ORPHANS — a live task not linked to any current triage key, whose
    #     title matches a triage title (a stale reworded/duplicate leftover).
    linked_ids = {v["task_id"] for v in st["links"].values()}
    orphans = [t for tid, t in live.items()
               if tid not in linked_ids and t.get("content") in triage_titles]

    if ticked:
        print(f"\n  BOCKADE (klara i Todoist → [x] i triagen) ({len(ticked)}):")
        for t in ticked:
            print(f"    ✓ {t[:50]}")

    if not creates and not moves and not orphans and not due_fixes:
        # completions already ticked + links pruned above; persist and finish.
        save_state(st)
        if ticked:
            print("\nKlart — bockningar hämtade; Todoist speglar redan triagen i övrigt.")
        else:
            print("Inget att synka — Todoist speglar redan triagen.")
        return

    print(f"\nSYNK — triagen är sanning ({len(items)} aktiva rader):")
    if creates:
        print(f"\n  SKAPA ({len(creates)}):")
        for _, sec, t in creates:
            print(f"    + [{sec}] {t[:50]}")
    if moves:
        print(f"\n  FLYTTA till rätt kolumn ({len(moves)}):")
        for _, sec, t, cur in moves:
            print(f"    ~ {t[:44]:46} {cur} → {sec}")
    if orphans:
        print(f"\n  STÄNG dubbletter/kvarvarande ({len(orphans)}):")
        for t in orphans:
            print(f"    × {t.get('content')[:50]}")

    if not yes:
        if input("\nGenomför synken? [j/N] ").strip().lower() not in ("j", "y"):
            print("Avbrutet — inget ändrat.")
            return

    for k, sec, title in creates:
        body = {"content": title, "project_id": pid, "section_id": sect.get(sec)}
        due = due_for_section(sec)
        if due:
            body["due_date"] = due          # column = schedule, so Todoist filters work
        r = api("POST", "/tasks", token, body)
        st["links"][k] = {"task_id": r["id"], "section": sec, "title": title}
        print(f"    + {sec}: {title}")
    for tid, sec, title, _cur in moves:
        api("POST", f"/tasks/{tid}/move", token, {"section_id": sect.get(sec)})
        # Pass the live task so a HAND-SET date survives the move. Without it we
        # clobbered a deliberate date (Airalo was pinned to Sat and a Denna-vecka
        # -> Idag move rewrote it to today). The column only dates undated tasks.
        _apply_due(token, tid, sec, live.get(tid))
        # keep state's recorded section in step
        for k, v in st["links"].items():
            if v["task_id"] == tid:
                v["section"] = sec
        print(f"    ~ {title} → {sec}")
    for _tid, _sec, _ in due_fixes:
        _apply_due(token, _tid, _sec)
    if due_fixes:
        print(f"    ⏱ {len(due_fixes)} tasks fick datum från sin kolumn")
    for t in orphans:
        # DELETE, not close: orphans are reworded/duplicate leftovers, NOT things
        # the user completed. A close would put them in the completed log, where
        # _pull_completions would later misread them as done and re-tick the
        # triage — the exact loop we fixed. Delete keeps them out of that log.
        api("DELETE", f"/tasks/{t['id']}", token)
        print(f"    × borttagen (dubblett): {t.get('content')}")
    save_state(st)
    print("\nKlart — Todoist speglar triagen.")


def line_key_matches(line, k):
    """True if this '- [ ]' line's key == k. Prefers the explicit {id} token
    (stable across rewording); falls back to tag+title-stub for un-stamped lines.
    Mirrors parse_actionable's key derivation exactly."""
    content = line.strip()[5:].strip()          # after '- [ ]'
    tid = extract_id(content)
    if tid:
        return line_key("", "", tid) == k
    tagm = re.match(r"\*\*\[([^\]]+)\]\*\*|\[([^\]]+)\]", content)
    tag = (tagm.group(1) or tagm.group(2)).strip() if tagm else ""
    title = ID_RE.sub("", content)
    title = re.sub(r"\*\*|`", "", title)
    title = re.sub(r"^\[[^\]]*\]\s*", "", title)
    title = re.sub(r"\[|\]", "", title)
    title = re.split(r"\.\s|\s[—–]\s|\s--\s|\s\(", title)[0]
    title = re.sub(r"\s+", " ", title).strip().rstrip(".:")
    return line_key(title, tag) == k


def cmd_status(token):
    pid = tiny_yaml_get(BASE_CFG, "integrations", "todoist", "project_id")
    st = load_state()
    report_dates_yaml()
    items = parse_actionable_yaml()
    live = live_tasks(token, pid)
    linked = sum(1 for k, _, _ in items if k in st["links"]
                 and st["links"][k]["task_id"] in live)
    print(f"Triage actionable: {len(items)}  |  varav pushade (state-länkade): {linked}")
    print(f"Öppna tasks i Todoist: {len(live)}  |  state-länkar: {len(st['links'])}")
    for k, sec, title in items:
        mark = "✓" if k in st["links"] and st["links"][k]["task_id"] in live else "·"
        print(f"  {mark} [{sec}] {title}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    yes = "--yes" in sys.argv
    token = load_token()
    if cmd == "push":
        cmd_push(token, yes)
    elif cmd == "reconcile":
        cmd_reconcile(token, yes)
    elif cmd == "sync":
        cmd_sync(token, yes)
    elif cmd == "status":
        cmd_status(token)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
