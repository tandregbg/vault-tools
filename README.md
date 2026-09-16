# vault-tools

Integrationer **mot** Obsidian-valvet — verktyg som läser och skriver valvet
utifrån, på begäran.

## Gränsen mot core-skills

Detta är den avgörande skillnaden, och den är värd att läsa innan något nytt
läggs till här:

| | core-skills | vault-tools |
|---|---|---|
| Körs | **inuti** en Claude-session | **mot** valvet, från skalet |
| Form | instruktioner (`SKILL.md`) | skript (bash, python) |
| Startar | ingenting — laddas in | kan starta en session |
| Beroenden | ska funka för vem som helst | får kräva cmux, API-tokens, en viss maskin |
| Publikt | ja, med push-guard | nej — bär valvspecifika sökvägar och namn |

**En skill kan inte starta en session.** Det är inte en begränsning i
implementationen utan i vad en skill *är*: instruktioner som laddas IN i en
session som redan körs. Allt som behöver starta något hör hemma här.

## Vad som hör hit

Ett verktyg hör hit när det **integrerar mot något andra också kör** — Todoist,
Deep Thought, Claude Code, cmux — och skulle vara användbart för någon med
samma stack efter att sökvägen bytts ut.

Att ett skript läser valvet räcker inte. Verktyg som beskriver en enskild
maskinpark eller ett enskilt nät är en *miljö*, inte en integration, och hör
hemma någon annanstans.

## Verktygen

| Mapp | Vad | Kör |
|---|---|---|
| **`todoist-triage/`** | Tvåvägs-sync `_tasks.yaml` ↔ Todoist, plus genererade vyer | `sync.py sync --yes` |
| **`dt-pane/`** | Transkript → ny cmux-pane som kör `/transcript`. Källagnostisk via [`CACHE-CONTRACT.md`](dt-pane/CACHE-CONTRACT.md) | `dt-pane lunch anna+erik` |

Varje mapp har egen README med detaljerna.

## Installation

Skripten körs från `~/bin`. Symlinka in dem:

```bash
ln -sf ~/repos/vault-tools/dt-pane/dt-pane ~/bin/dt-pane
ln -sf ~/repos/vault-tools/todoist-triage ~/bin/todoist-triage
```

Sätt valvroten i din miljö — repots default är en gissning:

```bash
export DT_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/MittValv"
```

## Hemligheter

**Inga tokens i repot.** `.gitignore` blockerar `.env*` och lades in före någon
kod kom in. Todoist-token bor i `todoist-triage/.env` (chmod 600), som aldrig
har varit spårad.

Samma regel som valvet: nya credentials → 1Password + referens-stub.

## Valvsökvägen

Flera skript hade hårdkodat en absolut hemkatalog och sprack på den andra
maskinen, där användarnamnet är ett annat. Nya skript ska läsa valvroten ur miljön med en
rimlig default:

```bash
VAULT="${DT_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Tomas}"
```

## Licens

MIT — se [LICENSE](LICENSE).

## Status

Personliga verktyg, publicerade för att arkitekturen kan vara användbar för
andra som kör samma stack. De löser mina problem först; inga garantier, inget
supportåtagande. Issues och PR:er är välkomna men kan bli liggande.
