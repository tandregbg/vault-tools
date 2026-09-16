# Changelog — vault-tools

Nyast överst. Per-verktygs-historik ligger kvar i respektive mapp
(`todoist-triage/CHANGELOG.md`); denna fil bär lagret som helhet.

## 2026-09-16

### Repot skapat

- **`vault-tools` samlar integrationslagret.** `todoist-triage` och
  `vault-machines` flyttades in från `~/bin` med **historiken bevarad**
  (subtree-merge). `vault-pane` tillkom som nytt verktyg.
- **Gränsen mot core-skills skriven i README:** skills körs *inuti* en session,
  vault-tools körs *mot* valvet utifrån. En skill kan inte starta en session —
  den är instruktioner som laddas IN i en som redan kör.
- **`.gitignore` lades in FÖRE någon kod**, så `.env` med Todoist-token aldrig
  kunde råka spåras.

### dt-pane → vault-pane

Namnbyte. `dt-` läste som Deep Thought, men verktyget blev källagnostiskt i och
med cachekontraktet — det tar transkript från vilken MCP som helst och kör dem
genom core-skills. Namnet beskriver nu rörelsen, inte den första källan.

Miljövariablerna följde med: `DT_VAULT` → `VAULT_ROOT`, `DT_CACHE` →
`VAULT_PANE_CACHE`, `DT_SAFE` → `VAULT_PANE_SAFE`. Cachen flyttade till
`~/.cache/vault-pane`.

### vault-pane — andra källan

- **`klang` tillagd som känd källa.** Klang.ai exponerar en MCP (OAuth/PKCE) med
  `list-conversations` + `get-conversation`, där den senare ger AI-summering och
  varje källas fulla transkript.
- **Kontraktet höll utan en rad ändrad logik** — bara ett namn i `KANDA_KALLOR`
  och en rad i tabellen. Uppslagningen hittade Klang-filen på både källnamn och
  Klangs eget id, eftersom den redan läser hela frontmattern. Det var precis
  poängen: vault-pane läser filer, inte MCP:er.
- **`--list` krävde valvroten** trots att den bara läser cachen, så den som inte
  satt `VAULT_ROOT` fick ett fel om något kommandot inte rör. Kontrollen flyttad
  till där den faktiskt behövs.

### vault-pane — cachekontraktet

- **`CACHE-CONTRACT.md`:** formatet på `~/.cache/vault-pane/` är nu deklarerat, så
  **vilken transkriptkälla som helst kan fylla cachen**. Kedjan
  `källa → cache → vault-pane → claude → /transcript` kan bytas ledvis; cachen är
  enda kopplingen.
- **`källa:` är enda fältet som valideras**, och varnar utan att stoppa — en
  trasig producent ska synas, men filen kan vara användbar ändå. Värdet
  normaliseras (gemener + bindestreck) så kontraktet inte blir en
  stavningsfälla. Det fångade direkt att cachefilen sa `Deep Thought` mot
  kontraktets `deep-thought`.
- **Core-skills kan inte vara basen för detta:** skillen tar EN fil och laddas
  först när sessionen redan kört igång. Kontraktet hör hos konsumenten av cachen.

### vault-pane — nytt

- Slår upp ett Deep Thought-transkript i `~/.cache/vault-pane` på filnamn **eller**
  frontmatter (DOC-id, originalfilnamn, titel, talare, kontext) och öppnar en
  cmux-pane som kör `/transcript [deltagare] <fil>`.
- **Hämtar inte själv.** MCP:n är kopplad till Claude-sessionen, inte till
  skalet — en session skriver transkriptet till cachen, vault-pane öppnar det.
- PWD sätts till **valvroten**, inte filens mapp, så skillens rules-walk
  (Step 0.5, `_insights.yaml`-kedjan) hittar hela kedjan.
- Kör med `--dangerously-skip-permissions` som default: `/transcript` skriver
  många filer och en fråga per skrivning gör panen obrukbar. `--safe` eller
  `VAULT_PANE_SAFE=1` kräver frågor.

**Fyra fel som kostade tid och är värda att minnas:**

1. **`cmux send` tar `--surface`, inte `--pane`.** Med `--pane` tolkades flaggan
   som *text* och ekades ut i terminalen — kommandot kördes aldrig.
2. **Att tysta stdout dolde felet.** Utskriften kom från stderr, och tystningen
   gjorde att det såg ut som om inget hände i stället för att visa vad som gick fel.
3. **`set -u` mot tom array** spränger i bash 3.2 (macOS systembash):
   `"${ARR[@]}"` kräver `${ARR[@]+"${ARR[@]}"}`.
4. **Test som kör hela skriptet öppnar riktiga panes.** En matchningsslinga över
   fem söksträngar startade fyra Claude-sessioner. Därav `--dry-run`.

### todoist-triage — completed-loggen

- **Sync återskapade tasks användaren just bockat av.** `/tasks/completed` gav
  `next_cursor=None` trots fullt svar; när loggen passerat 200 poster föll
  *dagens* completions utanför och lästes aldrig hem. 14 avbockningar ignorerades,
  8 tasks återskapades. Bytt till `by_completion_date` med 30-dagarsfönster.
- **Andra buggen bakom den:** nya endpointen bär id:t i `id`, inte `task_id`.
  Första fixen läste därför noll completions och hade gjort saken värre.
  Extraktionen tar nu emot båda fältnamnen.
- `import_inbox.py`: bindestreck krävs inte längre i `_capture.md`.
- `render_status.py`: omskriven — skriptet räknar det tidskritiska, modellen
  skriver bilden. Handskrivna vyer (`write_ownership: llm`) skrivs inte över.
