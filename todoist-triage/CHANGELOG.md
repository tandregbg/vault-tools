# Changelog — todoist-triage

Nyast överst.

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
