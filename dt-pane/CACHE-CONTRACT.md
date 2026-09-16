# Cachekontraktet

Formatet på filerna i `~/.cache/dt-pane/`. **Vilken transkriptkälla som helst
kan fylla cachen** — dt-pane läser filer, inte en viss MCP.

## Varför ett kontrakt

Kedjan är `källa → cache → dt-pane → claude → /transcript`. Varje led kan bytas
oberoende, och cachen är den enda kopplingen mellan dem. Så länge en producent
skriver enligt detta format fungerar dt-pane utan en rad ändrad kod.

Skillen (`/transcript`) tar **en fil** och frågar aldrig varifrån den kom. Den
kan därför inte vara basen för det här — den laddas först när sessionen redan
kört igång. Kontraktet hör hemma här, hos konsumenten av cachen.

## Filnamn

```
YYMMDD-<slug>.md
```

Samma konvention som valvet: datumprefix alltid, å/ä/ö behålls. Slugen är fri
men bör bära det du faktiskt söker på — `260916-samtal-anna-erik-lunch.md`.

## Frontmatter

Hela frontmattern är **sökbar** — dt-pane matchar först på filnamn, sedan på
vilket fält som helst här. Därför är ett rikt huvud inte pynt utan funktion.

```yaml
---
källa: deep-thought            # OBLIGATORISK — vilken producent som skrev filen
document_id: DOC_2026..._ab12  # källans egen id, oavsett format
titel: Lunch med Erik
filnamn: 260916_114054.m4a     # originalets namn, ofta det man minns
inspelad: 2026-09-16 11:40
längd: 63 min
variant: named                 # named | diarized | plain
talare: Anna, Erik
kontext: projekt-x
---
```

### Fälten

| Fält | Krav | Varför |
|---|---|---|
| **`källa`** | **ja** | Enda fältet dt-pane *validerar*. Okänd källa varnar (`--list` visar den, körning fortsätter) så en trasig producent syns i stället för att tyst ge dåliga filer |
| `document_id` | bör | Gör `dt-pane DOC_...` möjligt. Formatet är källans ensak — Deep Thought har två olika |
| `filnamn` | bör | Man minns oftare `260916_114054` än en titel |
| `titel`, `talare`, `kontext` | bör | Det man faktiskt söker på: `dt-pane lunch`, `dt-pane projekt-x` |
| `variant` | om relevant | `named` har talarnamn, `diarized` bara `SPEAKER_NN`. Avgör om summeringen kan säga vem som sa vad |
| `inspelad`, `längd` | frivilligt | Läsbarhet i `--list` |

Egna fält är tillåtna och blir sökbara automatiskt. Deep Thought har t.ex.
`has_actions` och `llm_keywords` värda att ta med.

## Kroppen

Råtranskriptet som text. Ingen struktur krävs — `/transcript` läser det som
det är. Talarprefix (`Namn: replik`) om varianten är `named`.

## Kända källor

| `källa:` | Verktyg som ger texten |
|---|---|
| `deep-thought` | `get_source_transcript` (MCP, nås bara inifrån en Claude-session) |

Värdet normaliseras före jämförelse — `Deep Thought`, `deep thought` och
`deep-thought` är samma producent. Kontraktet ska inte vara en stavningsfälla.

Lägg till rader här när en ny producent tillkommer. Listan är dokumentation för
människor och sessioner — dt-pane varnar bara för värden som inte står här.

## Att skriva en ny producent

1. Hämta transkriptet, hur som helst
2. Skriv `~/.cache/dt-pane/YYMMDD-<slug>.md` med frontmattern ovan
3. Sätt `källa:` till ett namn som står i tabellen — lägg till raden om den saknas

Inget mer. dt-pane behöver inte veta att du finns.

## Livslängd

Cachen är **transportyta, inte arkiv**. När `/transcript` kört hamnar
råmaterialet i valvets `.transcripts/` (läs-spärrat), så cachefilen kan sopas
fritt. Inget här är sanningskälla.
