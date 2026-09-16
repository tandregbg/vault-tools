# Changelog — todoist-triage

Nyast överst.

## 2026-09-16

- **Completed-loggen läste fel — sync återskapade tasks som just bockats av.**
  `/tasks/completed` svarade `next_cursor=None` trots full sida (200 rader), så
  när loggen passerat 200 poster föll de **nyaste** completions utanför fönstret
  och lästes aldrig hem. Sync tolkade dem som "saknas i Todoist" och skapade om
  dem. Bytt till `/tasks/completed/by_completion_date` med 30-dagarsfönster
  (`COMPLETED_WINDOW_DAYS`) — den sorterar nyast först och paginerar korrekt.
- **Andra buggen bakom den:** nya endpointen bär id:t i `id`, den gamla i
  `task_id`. Första versionen av fixen läste därför **noll** completions och
  hade gjort saken värre — allt hade sett obockat ut. `except Exception:
  return set()` svalde det tyst. Extraktionen tar nu emot båda fältnamnen.
- `import_inbox.py`: **bindestreck krävs inte längre** i capture-filen. Att
  kräva syntax av en friformsyta motverkar dess syfte; rubriker, instruktioner
  och korta fragment hoppas fortfarande över.
- `render_status.py`: omskriven i två lager — **skriptet räknar** det
  tidskritiska (förfallet, nästa möte, dagar sedan kontakt, takt), **modellen
  skriver** bilden. En lista med insikter i datumordning är en databas, inte ett
  nuläge. Handskrivna vyer (`write_ownership: llm`) skrivs inte över.

## 2026-09-07

- **YAML-migrering.** `_tasks.yaml` ersatte markdown som sanning; läsvyn blev
  genererad (438 → 41 rader). Markdownen hade 273 teckens medianrad och gick
  inte att läsa manuellt. State-nycklarna behöll `id:`-prefixet, så 117 av 119
  Todoist-länkar höll genom migreringen.
- **Datumkontroll `⏰YYMMDD`** + varning för felaktig veckorubrik. Prosadatum går
  inte att kontrollera; en token är data. Auditen som föranledde det hittade sju
  förfallna rubriker och elva passerade deadlines, några upp till 40 dagar gamla.
- Kolumnen "Efter Indien" omdöpt till "Senare" — villkoret var uppfyllt, namnet
  vilseledde.

## 2026-08-23

- **`{id}`-token (4 hex) ersatte textbaserad identitet.** Identiteten var
  tidigare `[tag]` + tre första orden i titeln, så varje omformulering skapade
  en ny identitet och därmed en dubblett. Det bet ~5 gånger på en dag innan
  roten åtgärdades.
- **Completions läses från completed-loggen**, inte från "saknas bland öppna" —
  en task kan saknas för att den raderats eller flyttats. Falska bockar borta.
- **Orphan-städning bytte CLOSE → DELETE.** En close hamnar i completed-loggen
  och läses tillbaka som "användaren blev klar", vilket gjorde städning till en
  självförstärkande loop.

## 2026-07-27

- **`sync` blev det kompletta tvåvägskommandot.** Det gör nu båda riktningarna i
  ett svep: hämtar Todoist-bockar → `[x]` i triagen (reconcile-halvan via
  `_pull_completions`), sedan speglar ut triagen (skapa/flytta/stäng). Rätt
  ordning garanterad så en just-bockad rad inte återskapas. `sync` är nu standard
  i INDEX.md + README; `push`/`reconcile` är delmängder.
- **`line_key` → `[tag]` + titel-stub.** Nyckeln byggs på radens `[tag]` plus de
  tre första orden i titeln. Löser dubblettproblemet vid **textredigering** (taggen
  är stabil) *och* tag-kollision (två rader med samma tagg får olika stub). State
  migrerades två gånger (tag-only → tag+stub).
- **`line_key_matches` (reconcile) rättad** att använda tag+stub — matchade tidigare
  bara på titel och slutade fungera efter tag-fixen.
- Champagneglas-buggen (två `[Fest · inköp]`-rader kolliderade till en nyckel) löst
  av tag+stub.

## 2026-07-26

- **Kolumn-routning per veckodag.** `### IDAG` → Idag, `### IMORGON` → Imorgon, andra
  namngivna veckodagar (TISDAG…) → Denna vecka (tidigare felaktigt Imorgon).
- **"Efter semestern"-kolumn** (egen Todoist-sektion). Både `### Efter semestern`
  (under SENARE) och `### Efter sommaren` (under UPPFÖLJNINGAR) routas dit — de betydde
  samma sak men hamnade i olika kolumner.

## Tidigare (juli)

- Grund: `push` (triage → Todoist, board-kolumner), `reconcile` (Todoist → triage,
  avbockat/nytt/klart-i-triagen), `status` (läs-bart). State-fil i vaulten för
  cross-Mac-synk. Sektioner + token via config/env, aldrig hårdkodat.
