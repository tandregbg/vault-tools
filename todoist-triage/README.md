# todoist-triage

Tvåvägs-sync mellan `_inbox/daglig-triage.md` och ett Todoist-board.
Lokal integration (inte en core-skill). Körs manuellt.

## Modellen (omlagd 260907 — YAML är sanningen)

```
_inbox/_capture.md   →  _inbox/_tasks.yaml  →  daglig-triage.md  (läsvy)
   (skriv fritt)          (SANNINGEN)              ↓
                                              Todoist (spegel)
```

| Fil | Roll | Redigeras |
|---|---|---|
| **`_tasks.yaml`** | **Sanningen.** 189 uppgifter, v2-schema | **Ja — här** |
| `_capture.md` | Inflöde. En rad per uppgift, importeras och töms | Ja |
| `_frame.md` | Handskriven kontext som klistras in i vyn | Ja |
| `daglig-triage.md` | **Genererad läsvy** — 41 rader | **Nej** |

**Varför:** markdown-triagen växte till 438 rader där medianraden var **273 tecken** och
56 % av filen inte var uppgifter. Varje rad bar fyra sorters information samtidigt —
uppgift, historik, referensdata, resonemang. Den var inte läsbar manuellt.

I YAML ligger uppgiften i `task:` *(median 87 tecken)* och allt övrigt i `notes:`.
Läsvyn visar bara det som har datum eller P0/P1.

### Kommandon

```bash
python3 ~/bin/todoist-triage/import_inbox.py    # _capture.md → _tasks.yaml
python3 ~/bin/todoist-triage/render_triage.py   # _tasks.yaml → daglig-triage.md
python3 ~/bin/todoist-triage/sync.py sync --yes # _tasks.yaml → Todoist
```

**Capture-syntax:** `- [Sonetel] Verifiera siffran !P0 ⏰260917`
`@tagg` eller `[Tagg]` → context · `!P0`–`!P3` → priority · `⏰YYMMDD` → due

### Vad som syncas till Todoist

**Bara poster med datum eller P0/P1.** En post utan båda hör inte i Todoist — den är
referens eller bevakning och stannar i YAML. *(42 av 189 är i scope.)*

Det var tidigare implicit genom vilka markdown-block `parse_actionable` läste; nu är
regeln explicit i `parse_actionable_yaml`.

**Triagen är sanning. Todoist speglar.** Du bestämmer struktur i triagen (vilken
dag/grupp en rad hör till) och bockar av i Todoist. Verktyget håller dem i takt.

- Triage-block → Todoist-kolumn:
  `### IDAG` → **Idag** · `### IMORGON` → **Imorgon** · block som heter "Denna vecka"
  eller bär en veckodag (TISDAG, ONSDAG…) → **Denna vecka** · `## UPPFÖLJNINGAR` →
  **Uppföljningar** · rad med väntar-ord → **Väntar**.
  `## EJ DENNA VECKA / SENARE` → **Senare** *(egen kolumn sedan 260830; hette "Efter Indien" till 260907)*.
  *(Kolumnerna "Efter semestern"/"Efter Färöarna" togs bort 260823 — allt inflyttat i
  Denna vecka.)*

  **Varför SENARE fick egen kolumn:** tidigare pushades bara ett "Efter semestern"-underblock,
  så 9 rader i *Efter Indien* var osynliga i Todoist. Tavlan visade alltså inte vad som
  medvetet var framflyttat — det syntes bara i triagen. Nu pushas hela sektionen.

### Vad som ligger UTANFÖR syncen (avsiktligt)

Sync äger inte hela triagen. Två slags undantag:

**Triage-block som inte pushas.** Bara `## PRIO`, `## UPPFÖLJNINGAR` och
`## EJ DENNA VECKA` (dess "Efter semestern"-underblock) är i scope. Varje annan
`## `-rubrik faller utanför — mötesförberedelser, styrelserubriker och
`## 🔁 VECKORUTIN`. Veckorutinen ska INTE till Todoist: den är en återkommande
checklista som nollställs varje vecka, och skulle annars skapa nya tasks vid varje
nollställning. Rader i sådana block behöver inga `{id}` — sync stämplar dem aldrig.

**Todoist-sektioner som inte läses.** `Goa` och `Links` underhålls för hand
(`Links` är linkedin-fetchs inflöde). Sync varken skapar, flyttar eller stänger där.

Följden: `status` visar normalt **fler öppna tasks i Todoist än state-länkar**.
Det är väntat, inte drift. Verkliga föräldralösa är bara sådana som ligger i en
*ägd* sektion utan länk.

### Identitet: `{id}`-token (ändrat 260823)

Varje actionable triage-rad bär ett **stabilt 4-hex-id sist på raden**, t.ex. `{a3f9}`.
**Sync stämplar nya rader automatiskt** — du behöver aldrig sätta dem själv.

```markdown
- [ ] **[Kontakt · Weber]** Återkoppla till Alexander Weber om klockan. {7e75}
```

Identiteten är **id:t, inte texten**. Du kan formulera om raden hur mycket du vill —
även byta `[taggen]` — utan att länken bryts.

> **Varför:** tidigare var identiteten `[tag]` + de tre första orden i titeln. Varje
> omformulering skapade då en ny identitet → dubblett i Todoist. Det bet ~5 gånger på
> en dag innan roten åtgärdades.

### Förfallodatum sätts från kolumnen (nytt 260826)

Kolumnen **är** schemat, så tasken bär matchande förfallodatum och Todoists egna
**Idag/Kommande**-filter stämmer med triagen.

| Kolumn | Förfallodatum |
|---|---|
| **Idag** | dagens datum |
| **Imorgon** | morgondagens |
| Denna vecka · Uppföljningar · Väntar | **inget** — de är hinkar, inte dagar |

Sätts vid tre tillfällen: när tasken **skapas**, när den **flyttas** till en annan kolumn,
och i en **backfill** som varje sync kör (så äldre tasks fylls i, och en rad som ligger
kvar i Idag över midnatt får det nya datumet).

**Ett handsatt datum skrivs aldrig över.** Sätter du 29/8 på en Idag-rad står det kvar —
din dag vinner över kolumnens. Backfillen rör bara tasks helt utan datum.

*Varför inte datera Denna vecka: allt skulle förfalla samma dag och skrika samtidigt.*

### Datumkontroll — ⏰YYMMDD (nytt 260907)

Varje `sync` och `status` rapporterar **förfallna deadlines** och en **felaktig
veckorubrik** innan något annat händer.

```markdown
- [ ] **[inkClub · returnera toner]** Ångerköp, order 2013371257. {1836} ⏰260914
```

Token sist på raden, `⏰` + `YYMMDD`. Ogiltiga datum ignoreras tyst.
Rapporten är **läsande** — sync ändrar aldrig triagen utifrån den.

> **Varför:** auditen 260907 hittade sju förfallna rubriker och elva passerade
> deadlines som legat oupptäckta i upp till 40 dagar. Veckorutinen fanns men kördes
> inte under en resvecka. En kontroll som går vid varje sync kräver att ingen kommer ihåg den.
>
> **Prosadatum går inte att kontrollera** — "före avresan sön 30/8" är text. `⏰260830` är data.

**Rubriker bör inte bära datum.** `## DENNA VECKA (v.34)` gick sönder eftersom
veckonumret satt i rubriken; kontrollen varnar när `(v.NN)` inte matchar dagens vecka.
Bäst är att utelämna det — veckoankaret överst räcker.

### CLOSE vs DELETE — viktig regel

- **CLOSE** en task bara när den **faktiskt är gjord**. En close hamnar i Todoists
  completed-logg, och reconcile läser den loggen som "användaren blev klar" → bockar
  `[x]` på triage-raden.
- **DELETE** för att städa bort dubbletter/rester. En delete hamnar *inte* i loggen och
  kan därför aldrig misstolkas som en completion.

Bryter man mot detta uppstår en självförstärkande loop: städning läses som "klart",
triage-rader bockas felaktigt, och varje ny sync upprepar det.

## Kommandon

```bash
cd ~/bin/todoist-triage
python3 sync.py sync [--yes]   # STANDARD — full tvåvägs, säg bara "sync"
python3 sync.py status         # läs-bart: vad är i synk (ändrar inget)
python3 sync.py push [--yes]   # bara skapa (delmängd av sync)
python3 sync.py reconcile      # bara bockar, med frågor per steg
```

### `sync` (standard)

Gör allt i ett svep, i rätt ordning:

0. **Stämpla:** actionable triage-rader utan `{id}` får ett.
1. **Todoist → triage:** tasks som ligger i Todoists **completed-logg** får `[x]` på
   sin triage-rad. Att en task bara *saknas* bland de öppna räcker inte — den kan ha
   raderats eller flyttats.
2. **triage → Todoist:** skapar saknade tasks, **flyttar** felplacerade till rätt
   kolumn (det `push` aldrig gör — nödvändigt vid dagsrullning), **raderar**
   föräldralösa dubbletter (delete, inte close — se regeln ovan).

Idempotent: kör två gånger → andra gången säger "inget att synka".

## Konfiguration

- **Sektioner + project_id:** `_config/base.yaml` → `integrations.todoist`
  (i den iCloud-synkade vaulten, delas mellan Macar).
- **Token:** `~/bin/todoist-triage/.env` → `TODOIST_TOKEN=…` (chmod 600, aldrig i vaulten).
- **Triage-sökväg:** läses från `_inbox/_inbox.yaml` (registrerat working_doc).
- **State** (länkarna som gör det till en riktig sync): `_config/integrations/todoist-state.json`
  i vaulten, så push på en Mac + sync på en annan delar samma minne.

## Vardagsflöde

- Flytta rader mellan grupper / lägg till nya **i triagen** → `sync`.
- Bocka av **i Todoist** → `sync` (hämtar hem bockarna).
- Formulera om en rad hur du vill — `{id}` bär identiteten, texten är fri.
- **Rör inte `{id}`-token** när du redigerar. Raderar du det blir raden en ny task;
  kopierar du en rad med allt inklusive id:t får du två rader med samma identitet.

## Kända kanter

- Klipp-och-klistra av en rad tar med `{id}` → två rader delar identitet. Radera id:t
  på kopian, så stämplar nästa `sync` ett nytt.
- Completed-loggen läses **30 dagar bakåt** via `by_completion_date`. Bockar du av
  något äldre än så läses det inte hem — höj `COMPLETED_WINDOW_DAYS` i `sync.py`.
- `reconcile` fristående gör samma sak som sync-steg 1, men frågar per steg. Vid
  tveksamhet: kör `sync`.

## Historik

- **260907** — **YAML-migrering:** `_tasks.yaml` ersatte markdown som sanning; `daglig-triage.md`
  blev genererad läsvy (438 → 41 rader); `_capture.md` som inflöde; state-nycklarna behöll
  `id:`-prefixet så 117 av 119 Todoist-länkar höll genom migreringen.
- **260916** — **completed-loggen läste fel**: `/tasks/completed` gav `next_cursor=None`
  trots fullt svar, så när loggen passerat 200 poster föll dagens avbockningar utanför.
  Sync tolkade dem som "saknas" och **skapade om 8 tasks** som just bockats av. Bytt till
  `by_completion_date` + 30-dagarsfönster. Andra buggen bakom den: nya endpointen bär id:t
  i `id`, inte `task_id` — extraktionen tar nu emot båda.
- **260907** — datumkontroll `⏰YYMMDD` + varning för felaktig veckorubrik; kolumnen
  "Efter Indien" omdöpt till "Senare" (villkoret uppfyllt, namnet vilseledde).
- **260823** — `{id}`-token ersatte text-baserad identitet (dubblettbuggen);
  completions läses från completed-loggen istället för "saknas bland öppna"
  (falska bockar); orphan-städning bytte CLOSE → DELETE.
