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

## Vad som hör hit — och inte

Testet är **vad verktyget integrerar mot**, inte om det råkar läsa valvet.

| | hör hit | hör inte hit |
|---|---|---|
| Integrerar mot | Deep Thought, Claude Code, core-skills, Todoist, cmux | maskinparken, nätet, tmux, VPN |
| Vore användbart för | någon annan med samma stack, efter byte av sökväg | ingen annan — det är en miljö, inte en integration |
| Valvet är | arbetsmaterialet | råkar vara där konfigen bor |

Därför ligger `align`, `lxc-helper`, `sync-hosts` och `tmux-save` **inte** här,
trots att de läser `_infrastructure/vm-inventory.yaml`. De beskriver en
personlig maskinpark. `todoist-triage` och `dt-pane` beskriver integrationer
mot verktyg andra också kör.

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

## Vad som medvetet INTE ligger här

`vault-machines` bröts ut till ett eget lokalt repo. `machines.txt` är en
komplett karta över en intern infrastruktur — kundnamn kopplade till IP-adresser
och driftdetaljer om andras system. Det kan inte ligga publikt, och enligt
inträdeskravet ovan beskriver det dessutom en **maskinpark**, inte en
integration.

Samma princip gäller framåt: allt som bär kundnamn, interna adresser eller
personuppgifter hör i ett lokalt repo, inte här.

## Historik

`todoist-triage` flyttades hit från `~/bin` med historiken bevarad
(subtree-merge), så `git log` når hela vägen tillbaka till dess första commit.

## Licens

MIT — se [LICENSE](LICENSE).

## Status

Personliga verktyg, publicerade för att arkitekturen kan vara användbar för
andra som kör samma stack. De löser mina problem först; inga garantier, inget
supportåtagande. Issues och PR:er är välkomna men kan bli liggande.
