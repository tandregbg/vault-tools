# dt-pane

Öppnar ett Deep Thought-transkript i en ny cmux-pane och kör `/transcript` där.

```bash
dt-pane lunch anna+erik
```

## Arbetsdelningen

**dt-pane hämtar inte själv.** MCP-servern är kopplad till Claude-sessionen,
inte till skalet — ett skript kan inte anropa `get_source_transcript`.

```
Du (i en session):  "hämta veckans projektmöte till dt-cachen"
      ↓  sessionen skriver ~/.cache/dt-pane/YYMMDD-<slug>.md med frontmatter
Du (i skalet):      dt-pane webapp anna+erik
      ↓  ny pane, cd till valvroten, claude, /transcript
```

Du skriver alltså **aldrig** ett DOC-id till dt-pane om du inte vill — men det
funkar, eftersom matchningen läser frontmattern.

## Uppslagning

Matchar i två steg, senaste först: **filnamn**, sedan **frontmattern**
(`document_id`, `filnamn`, `titel`, `talare`, `kontext`).

Alla dessa hittar samma fil:

```bash
dt-pane lunch
dt-pane 260916_114054
dt-pane DOC_20260916_124609_266f3a0d_ae9fba9f
dt-pane T1K
```

## Flaggor

| Flagga | Gör |
|---|---|
| `-n`, `--dry-run` | visar träff, PWD, claude-kommando och prompt — **öppnar inget** |
| `--list`, `-l` | vad ligger i cachen |
| `--safe` | kräv behörighetsfrågor (default är att skippa dem) |
| `-p`, `--print` | headless: kör klart och dör, ingen pane |
| `--direction` | `left\|right\|up\|down` (default `right`) |
| `--` | allt efter skickas vidare till `claude` |

Miljö: `DT_VAULT` (valvrot) · `DT_CACHE` (default `~/.cache/dt-pane`) ·
`DT_SAFE=1` (samma som `--safe`).

## Två designval

**PWD = valvroten, inte filens mapp.** `/transcript` går uppåt från CWD och
samlar `_insights.yaml` (Step 0.5, rules-walk). Startar panen i `$HOME` hittar
den inga regler.

**`--dangerously-skip-permissions` som default.** `/transcript` skriver
summering, `_insights.yaml`, CHANGELOG och `.transcripts/` — en fråga per
skrivning gör panen obrukbar. Men flaggan gäller **hela sessionen**, inte bara
den körningen: panen kan skriva var som helst i valvet. Därav `--safe`.

## Fyra fel som kostade tid

1. **`cmux send` tar `--surface`, inte `--pane`.** Med `--pane` blev flaggan
   tolkad som *text* och ekades ut i terminalen; kommandot kördes aldrig.
   Panens surface slås upp med `list-pane-surfaces`.
2. **Att tysta stdout dolde felet** — utskriften kom från stderr, så tystningen
   gjorde att det såg ut som om inget hände.
3. **`set -u` mot tom array** spränger i bash 3.2 på macOS:
   `"${ARR[@]}"` måste skrivas `${ARR[@]+"${ARR[@]}"}`.
4. **Test som kör hela skriptet öppnar riktiga panes.** En matchningsslinga över
   fem söksträngar startade fyra Claude-sessioner. Använd `-n`.

## Cachen — källagnostisk

Formatet är ett **kontrakt**: [`CACHE-CONTRACT.md`](CACHE-CONTRACT.md). Vilken
transkriptkälla som helst kan fylla cachen så länge frontmattern följer det —
dt-pane läser filer, inte en viss MCP.

`källa:` är enda fältet som valideras. Okänd eller saknad källa **varnar men
stoppar inte**, så en trasig producent syns i stället för att tyst leverera
dåliga filer.

`~/.cache/dt-pane/*.md`. Rå transportyta — råmaterialet hamnar ändå i
`.transcripts/` när `/transcript` kört, så cachen kan sopas fritt.
