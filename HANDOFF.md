# HANDOFF — typed-judge-kit, 2026-09-21

## Состояние
Ветка `main`, **7 коммитов не запушено** (`0bad837..5ad6577`). Рабочее дерево чистое, кроме
неотслеживаемых `.DS_Store` и `.serena/`. Воркчтри не заводились. Гейты: `213 passed`,
`pytest -m stress` — 2 passed.

## Закрыто в этой сессии
| бид | что | итог |
|---|---|---|
| ov0 | overclaim понижает ready→light_edit, а не ставит heavy_edit | 185 pass |
| k55 | положительный класс по overclaim | separation 1.000 при 0.76 |
| 0py | положительные классы topic_sprawl / loose_end | separation 1.000 / 0.800 |
| p6g | влияет ли формулировка overclaim на порог | сдвиг −0.115, порог оставлен 0.76 |
| q36 | claim-vs-evidence + гейт stress | 25/25 критических; двухшаговая схема DR-63 проиграла целостному вопросу (19/25 против 25/25) |
| qei | зона сомнения → review_required | 3/14 на review; полоса по одному composite ловила 0/14 |
| sqd | claim_check на реальных парах | 1/10 ложных у целостного вопроса, 20/70 по утверждениям |

## Открыто
- **typed-judge-kit-490** (P4, backlog): порог `loose_end` 0.5 стоит ниже пустого зазора
  0.60..0.80, 3/35 ложных. Упирается в те же естественные данные — синтетику для него
  делать нельзя, в этом смысл бида.

## Ключевой факт для следующей сессии
Источники для claim_check **не нужно писать руками** — они уже лежат в
`/Users/ascurse/Documents/ObsidianSecondBrain/output/Content/drafts/<id>.md`, секция
`## Source material`, 10 из 14 черновиков. Это рабочие заметки владельца, не синтетика.
Извлекает их `source_note()` в `scripts/claim_check_drafts.py`.

## Следующая команда
```bash
cd /Users/ascurse/Documents/typed-judge-kit && git push origin main
```
Пуш не делался: по правилу проекта коммит/пуш/синк — только с явного разрешения.
