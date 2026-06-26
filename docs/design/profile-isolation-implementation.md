# Полная изоляция профилей для per-topic routing — implementation spec

> **Назначение этого файла.** Это самодостаточное ТЗ для агента в новой сессии.
> Прочитай его целиком, затем реализуй полную изоляцию профилей на текущей ветке
> `topic-model-binding`. Здесь есть: что уже есть в коде (с `file:line`), что и где
> доделать по фазам, какие именно сиды (seams) уже написаны, полный текст уже
> найденных «граблей» из полевых тестов upstream-PR #18510, заметки по разрешению
> merge-конфликтов от автора того PR, список донорских файлов и команды, чтобы
> снять их диффы. Цель в конце — оформить PR в `NousResearch/hermes-agent`.

---

## 0. Контекст и термины

- **Репозиторий / чекаут:** `~/.hermes/hermes-agent` (editable install, `pip install -e .`,
  venv в `~/.hermes/hermes-agent/venv`). `HERMES_HOME=~/.hermes`.
- **Ветка:** `topic-model-binding`, форк `myfork` = `https://github.com/VKirill/hermes-agent`.
  Базовый upstream — `origin` = `NousResearch/hermes-agent`.
- **HEAD на момент написания:** `386457f9957e1a975c4dc7faab1d1babd763e72d` (2026-06-26).
- **Запуск/рестарт:** LaunchAgent `ai.hermes.gateway`.
  Рестарт: `launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway`.
  Изменения кода требуют рестарта; изменения значений в `config.yaml` подхватываются на лету.
- **Текущая конфигурация:** `multiplex_profiles: false` (один gateway, один бот,
  Telegram DM «топики» = forum threads). **Это ключевой факт** — см. ниже.

### Что уже реализовано на ветке (не переписывать!)

На `topic-model-binding` поверх `origin/main` уже лежит ~5000 строк, в т.ч.:

- **`feat: topic-level model binding`** — персистентный per-topic `/model` override
  (стор `topic_models`, читается `_load_topic_models()` в `gateway/slash_commands.py:187`).
- **`Feature: Persistent topic-scoped profile binding via /profile command`** — команда
  `/profile <name>` пинит топик к именованному профилю; `/profile default|reset|clear`
  снимает привязку. Обработчик: `gateway/slash_commands.py:305` `_handle_profile_command`.
  Стор привязок: `gateway/run.py` — `_topic_profile_key` (:2327), `_load_topic_profiles`
  (:2343), `_save_topic_profile` (:2356), `_remove_topic_profile` (:2367).
- **`feat(gateway): per-platform model override`** (≈ upstream PR #52515),
  **`per-channel working directories (channel_cwds)`** (≈ #43562),
  **`clarify rich options/modals/auth`** (≈ #49154),
  **`delete-on-undo`** (≈ #48401), **`/commands` inline pagination** (≈ #48289),
  русский перевод описаний команд.

**Итого:** маршрутизация «топик → профиль» и «топик → модель» уже работает как
динамические слэш-команды. **Не хватает именно изоляции** окружения профиля
(память, файлы, skills, SOUL, `.env`, sessions, процессы). Этим и занимаемся.

---

## 0A. Рабочий процесс (RUNBOOK) — выполнять строго по порядку

Меташаги вокруг фаз. Цель: не сломать работающий гейтвей, минимизировать
конфликты, выйти на чистый PR. **Сначала Шаги 1–4, только потом код (Раздел 3).**

> ## ✅ ОКРУЖЕНИЕ УЖЕ ПОДГОТОВЛЕНО (2026-06-26) — Шаги 1–4 ВЫПОЛНЕНЫ
> - worktree **`~/hermes-isolation-dev`** на ветке **`profile-isolation`** создан;
> - в него влит свежий `origin/main` (43 коммита, **0 конфликтов**) → HEAD `1bba2a57b`
>   (= вся работа `topic-model-binding` + соседа + последний апстрим);
> - **baseline зелёный:** `tests/gateway/test_telegram_topic_mode.py` — 50 passed;
> - этот план лежит в `~/hermes-isolation-dev/docs/design/profile-isolation-implementation.md`.
>
> **Отдельный venv НЕ нужен** — тесты гонять основным venv + PYTHONPATH worktree:
> ```bash
> PYTHONPATH=~/hermes-isolation-dev ~/.hermes/hermes-agent/venv/bin/python \
>   -m pytest ~/hermes-isolation-dev/tests/<...> -q -o 'addopts=' -p no:cacheprovider
> ```
> **РЕАЛИЗУЮЩЕМУ АГЕНТУ:** работай в `~/hermes-isolation-dev`, **начинай сразу с
> Фазы 0/1 (Раздел 3)**, Шаги 2–4 уже сделаны. Шаги 5–8 (выкат в живой гейтвей,
> сборка PR) — после реализации. Файл-спек `docs/design/...` — рабочая копия,
> **в feature-коммиты её НЕ добавляй** (в PR не идёт).

### Шаг 1 — зафиксировать стартовую точку и запреты

- Ветка `topic-model-binding`, форк `myfork` = `VKirill/hermes-agent`,
  апстрим `origin/main` ушёл **всего на ~5 коммитов** (merge-base свежий) —
  по содержанию мы практически на последнем Hermes, «снимать с нуля» НЕ нужно.
- ⛔ **НЕ делать** `hermes update`, `git reset --hard origin/main`,
  `git rebase origin/main`. Первые два сотрут работу; rebase попытается
  переиграть ~6342 коммита (история форка переписана). **Обновляемся ТОЛЬКО
  через `git merge`.**
- ⛔ **Не писать код в живом чекауте** `~/.hermes/hermes-agent` — из него крутится
  LaunchAgent `ai.hermes.gateway` (работающий бот).

### Шаг 2 — отдельный worktree для разработки

```bash
cd ~/.hermes/hermes-agent
git worktree add ~/hermes-isolation-dev -b profile-isolation topic-model-binding
cd ~/hermes-isolation-dev
```
- Живой гейтвей продолжает работать из основного чекаута (`topic-model-binding`),
  его файлы не трогаются. Разработка — на новой ветке `profile-isolation`.
- **venv-нюанс:** editable-install (`pip install -e .`) привязан к ОСНОВНОМУ
  чекауту, поэтому код worktree им не подхватится. Для прогона тестов worktree
  собрать свой venv:
  ```bash
  python3 -m venv .venv && .venv/bin/pip install -e . -q
  ```
  Дальше во всех командах `python` = `~/hermes-isolation-dev/.venv/bin/python`.

### Шаг 3 — подтянуть свежий апстрим ДО кода (merge, не rebase)

```bash
git fetch origin
git merge origin/main          # абсорбируем ~5 апстрим-коммитов
```
- Разрешить конфликты в core **один раз сейчас** (пока изоляции ещё нет — поверхность
  минимальна). Ожидаемые файлы: `gateway/run.py`, `gateway/session.py`,
  `hermes_cli/runtime_provider.py`, `hermes_state.py`, `tools/file_tools.py`,
  `tools/terminal_tool.py`.
- Правило разрешения (от автора #18510, Раздел 6.1): routed-поток использует
  **профильный** `SessionStore`/`SessionDB`; сохранить `_resolve_safe_cwd` +
  профильную метадату процесса.

### Шаг 4 — зелёный baseline ДО изменений

```bash
python -m pytest tests/gateway/test_telegram_topic_mode.py -q -o 'addopts='
```
Убедиться, что после мёрджа всё зелёное — это точка отсчёта.

### Шаг 5 — реализация по фазам (Раздел 3). Цикл на КАЖДУЮ фазу:

1. снять донорские диффы нужных файлов (Раздел 4, команды `gh api`);
2. реализовать фазу;
3. написать/прогнать тесты фазы (Раздел 7), `python -m pytest ... -q -o 'addopts='`;
4. коммит — Conventional Commits, по одной фазе/подзадаче;
5. **E2E-проверка фазы:** в ОСНОВНОМ чекауте `git merge profile-isolation` в
   `topic-model-binding`, затем `launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway`,
   прогнать ручной smoke (Раздел 7). После проверки можно продолжать в worktree.
- **Порядок строго: 0 → 1 → 2 → 3 → 4 → 5 → 6.** После Фаз 1 и 2 — обязательный
  ручной smoke (самые рисковые: session/DB-изоляция и запись файлов в чужой SOUL).

### Шаг 6 — ВЫКАТИТЬ наработки в ЖИВОЙ гейтвей (чтобы заработало у нас)

> Это «место назначения №1» — твой работающий бот. Отдельно и независимо от
> upstream-PR (Шаги 7–8). Когда фаза(ы) готовы и прошли smoke, переносим их в
> ветку, с которой крутится LaunchAgent:

```bash
cd ~/.hermes/hermes-agent          # живой чекаут, ветка topic-model-binding
git merge profile-isolation        # вносим свежий апстрим + изоляцию в живую ветку
venv/bin/pip install -e . -q       # подхватить новые зависимости/энтрипоинты из апстрим-мёрджа
launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway   # рестарт → код стал живым
```
- editable-install ⇒ гейтвей исполняет код прямо из рабочего дерева; после рестарта
  новый код активен, переустановка пакета не нужна (но после крупного апстрим-мёрджа
  разок прогнать `pip install -e .` — апстрим добавил модули `moa`/`projects`).
- Делать **итеративно** (после каждой проверенной фазы) или **одним заходом в конце**.
  Рекомендация: первый выкат — после того как Фазы 1 и 2 прошли smoke.
- Откат: `git reset --hard ORIG_HEAD` (вернуть ветку до мёрджа) + рестарт.

### Шаг 7 — собрать ЧИСТУЮ ветку под PR (upstream, опционально)

> «Место назначения №2» — апстрим NousResearch. На живого бота не влияет.

```bash
cd ~/.hermes/hermes-agent           # или любой отдельный клон
git fetch origin
git switch -c profile-isolation-pr origin/main
# перенести ТОЛЬКО относящиеся к фиче коммиты (foundation /profile + изоляция),
# исключив посторонние (clarify-модалки, discord, рус.переводы, /commands pagination):
git cherry-pick <foundation...> <isolation...>
```
- ⚠ cherry-pick на чистый `origin/main` даст конфликты (origin/main ушёл вперёд) —
  разрешать по правилам раздела 6.1. Прогнать полный таргетный pytest.
- **Альтернатива (часто чище): не cherry-pick'ать грязную историю, а переписать
  foundation+изоляцию свежими коммитами** прямо на `profile-isolation-pr` — особенно
  если конфликтов много.

### Шаг 7a — INCLUDE / EXCLUDE чек-лист коммитов (снимок на `3dc9cb356`, 2026-06-26)

> ⚠ Ветку активно двигает сосед-агент — **SHA сместятся**. Перед сборкой PR ПЕРЕСНЯТЬ
> список: `git log --oneline --no-merges origin/main..topic-model-binding`.
> Правило: **INCLUDE** только «per-topic profile routing + model binding + изоляция»;
> **EXCLUDE** всё, у чего есть свой апстрим-PR, и весь поток соседа-агента.

**✅ INCLUDE — наша фича (foundation), cherry-pick в хронологическом порядке (снизу вверх):**
- `54deaf089` feat: topic-level model binding — ядро
- `8b4bf618f` fix: same-token Telegram/Slack adapter conflicts in multiplexed profiles — нужен для мульти-профиля
- `5f3eb50c7` Fix: topic-specific model overrides during `/new`
- `2ddf82486` Feature: persistent topic-scoped profile binding via `/profile` ← **ГЛАВНЫЙ**
- `+` все наши коммиты изоляции из Шага 5 (Фазы 1–6)

**🟡 CONDITIONAL — включать ТОЛЬКО если без них foundation не собирается/не работает:**
- `22f8b6979` fix: `Platform.LOCAL` comparison (мелкий фикс)
- `e37958ed5` fix: keep responses in originating thread (роутинг тредов)
- per-platform model override стек: `4ee2c7d68`, `559d17b22`, `eb1af3a1e`,
  `322e5ae7b`, `1a8b8b49c` — это **апстрим-PR #52515**; по умолчанию EXCLUDE (уедет
  своим PR), но `/profile`-model-binding может на него опираться → проверить сборку,
  при необходимости INCLUDE как зависимость и упомянуть #52515 в описании.

**❌ EXCLUDE — свои апстрим-PR / постороннее / работа соседа-агента:**
- clarify-стек (#49154): `03e5fe107`, `7a98d52e2`, `9f93d7e55`, `386457f99`, `3537584ab`
- `5c9cd1158` delete-on-undo (#48401) · `314172a4c` `/commands` pagination (#48289)
- `f88a67b63` channel_cwds (#43562) · `a53483c3f` MarkdownV2 truncate guard (#52096)
- `b291d82e2` + `f5997c28d` русские переводы и тест-фиксы под них
- `6b0956cd2` reaction emojis + voice echo (#49571/#50867)
- поток соседа: `f8286f1fd` busy-input/stop-phrase · `fb4ddfad7` suggestion buttons (#51858)
  · `37bc20f18` auth-sync (#52300) · `b8150075b` skill_route (#52247)
  · `7c8d14502`+`4f799659e` checklist (#31106) · `143e36946` auto-name sessions
  · `8fe735058` session-title mixin · `e61630ef6` zero-inbox (#23102)
  · `734928a4c`+`9662a52c2`+`d38714772`+`3dc9cb356` topic icons + скриншот/фиксы

> ⚠ Заметь: `4f799659e` — это коммит соседа, в который случайно попал наш план-док;
> в PR он не идёт (EXCLUDE), а из истории `topic-model-binding` его почистим отдельно.

**Проверка после cherry-pick:** `git log --oneline origin/main..profile-isolation-pr`
должен содержать ТОЛЬКО INCLUDE-коммиты + наши изоляционные. Ни одного из EXCLUDE.

### Шаг 8 — открыть PR

```bash
git push myfork profile-isolation-pr
gh pr create --repo NousResearch/hermes-agent --base main \
  --head VKirill:profile-isolation-pr \
  --title "feat(telegram): full profile isolation for per-topic /profile routing" \
  --body-file <(printf '...')   # тело: ссылка на #18510 как источник фичи/граблей,
                                #  изоляция по слоям (Раздел 2.1), решение по кредам
```
- CI на fork-PR требует одобрения мейнтейнера (Раздел 6).
- Перед открытием — пройтись по чек-листу Раздела 8.

---

## 1. Главный вывд: машинерия изоляции УЖЕ написана, но заперта за `multiplex_profiles`

Вся тяжёлая инфраструктура изоляции существует в коде ради multiplex-режима и
полностью переиспользуема. Она просто **не подключена** к single-gateway пути,
по которому идут наши `/profile`-привязанные топики.

### 1.1. Сиды (seams), на которых всё держится

| Примитив | Где | Что делает |
|---|---|---|
| `_profile_runtime_scope(profile_home)` | `gateway/run.py:1395` | Контекст-менеджер: ставит home-override + secret-scope профиля на один ход. |
| `set_hermes_home_override(path)` / `_HERMES_HOME_OVERRIDE` | `hermes_constants.py:17,22` | **ContextVar**, подменяет `get_hermes_home()`. Покрывает **config, skills, memory, SOUL, sessions**. Не мутирует `os.environ`. Пропагируется в воркер-тред через `copy_context()`. |
| `get_hermes_home()` | `hermes_constants.py:54` | Единый источник правды для home. Уважает override. |
| `build_profile_secret_scope(home)` | `agent/secret_scope.py:197` | Возвращает dict из `<home>/.env` (**только профильные ключи**; «глобальные» env берутся из `os.environ` напрямую). |
| `set_secret_scope(mapping)` / `get_secret(name)` | `agent/secret_scope.py` | Контекст-локальный secret scope. `get_secret` при активном скоупе читает из него; при отсутствии и `multiplex_active` — **fail-closed (raises)**; при выключенном multiplex — читает `os.environ`. |
| `_resolve_profile_home_for_source(source)` | `gateway/run.py:15201` | Уже резолвит `source.profile` → `get_profile_dir(name)`, fallback на active/default. |
| `_resolve_session_agent_runtime(...)` | `gateway/run.py:3531` | Резолв модели per-platform + platform override — **уже работает независимо от scope**. |
| Агент-кэш `self._agent_cache: OrderedDict[str, tuple]` | `gateway/run.py:2821` (lock :2822) | **Ключуется по `session_key`** (get :6681, evict :14617/:16293). |

### 1.2. Почему изоляция сейчас НЕ срабатывает — две «закрытые двери»

**Дверь №1 — `_run_agent` (`gateway/run.py:15180`):**

```python
async def _run_agent(self, ...):
    # docstring: "When multiplexing is active, ... run the whole turn inside
    #  _profile_runtime_scope ... When multiplexing is off this is a
    #  transparent pass-through — zero behavior change for single-profile gateways."
    if not getattr(getattr(self, "config", None), "multiplex_profiles", False):
        return await self._run_agent_inner(...)          # ← наш путь: БЕЗ изоляции
    profile_home = self._resolve_profile_home_for_source(source)
    with _profile_runtime_scope(profile_home):           # ← вся изоляция тут, недостижима
        return await self._run_agent_inner(...)
```

При `multiplex_profiles: false` ход агента **никогда** не входит в
`_profile_runtime_scope` → `get_hermes_home()` отдаёт глобальный `~/.hermes` →
config/skills/memory/SOUL/sessions/.env все глобальные.

**Дверь №2 — `_session_key_for_source` (`gateway/run.py:3274`):**

```python
def _session_key_for_source(self, source):
    normalized = self._normalize_source_for_session_key(source)
    key = _topic_profile_key(normalized)
    persistent_profile = _load_topic_profiles().get(key)
    if persistent_profile:
        source.profile = persistent_profile             # ← привязка выставляется
    ...
    _profile = None
    if getattr(config, "multiplex_profiles", False):    # ← НО namespace берёт профиль
        if source.profile:                              #    только при multiplex
            _profile = source.profile
        ...
    return build_session_key(source, ..., profile=_profile)
```

При `multiplex_profiles: false` → `_profile = None` → session-ключ уходит в
легаси-namespace `agent:main`. А раз **агент-кэш ключуется по session_key**,
то и кэшированный агент (с его SOUL/identity), и сессии/стейт **не разделяются**
по профилю.

### 1.3. Следствие — почему это упрощает работу

`_HERMES_HOME_OVERRIDE` — ContextVar; `_profile_runtime_scope` уже перенаправляет
**config, skills, memory, SOUL, sessions** одной строкой. **Агент-кэш ключуется
по `session_key`** — значит, как только session-ключ начнёт включать профиль,
изоляция кэша агента (и его SOUL/identity, и сессий) получится **автоматически**.
Поэтому Фаза 1 (открыть обе двери для привязанных топиков) даёт ~80% изоляции
малым диффом. Остаток (Фазы 2–5) — это места, куда ContextVar **не долетает**
(исполнение тулзов, подпроцессы, import-time пути) — их upstream-PR уже нашёл и
описал (см. раздел «Грабли»).

### 1.4. Альтернативная стратегия изоляции из PR #20096 — и наш ГИБРИД

PR #20096 («channel-based profile routing», донор, см. 4A) изолирует **иначе**:
не через ContextVar home-override, а через **явный проброс `profile_name`** как
параметра через `run.py → agent → memory_tool/system_prompt/skill_utils`. Каждый
путь резолвит сам:
```python
# tools/memory_tool.py (из #20096)
def get_memory_dir(profile_name="main") -> Path:
    if not is_standard_profile(profile_name):
        return get_hermes_home() / "profiles" / profile_name / "memories"
    return get_hermes_home() / "memories"
def get_soul_path(profile_name="main") -> Path: ...
class MemoryStore:
    def __init__(self, ..., profile_name="main"): self.profile_name = profile_name
```
**Плюс:** контекствара нет → терять нечего → **грабля G2 (запись в чужой SOUL) в
принципе не возникает** на этих путях. **Минус:** больше «проводки» (profile_name
параметром через ~10 файлов).

**Наш выбор — ГИБРИД (best of both):**
- ContextVar `_profile_runtime_scope` — для широкого охвата (config, sessions,
  secret-scope) — Фаза 1, малый дифф.
- **Явный `profile_name` (паттерн #20096)** — для путей, где ContextVar теряется и
  цена ошибки максимальна: **память, SOUL, file-write тулзы** — Фазы 1/2. Надёжнее,
  чем чинить пропагацию ContextVar по всем executor-путям.

Итог: Фаза 2 перестаёт быть «почини ContextVar везде» и становится «протащи
`profile_name` в файло-пишущие тулзы» — меньше риска, понятный дифф.

---

## 2. Целевой scope изоляции (что должно быть на профиль)

Эталон — финальный scope, который довёл автор #18510 (его слова, см. раздел 6):

> Isolates routed profile state via scoped `HERMES_HOME`, runtime env, `.env`,
> `auth.json`, credential pools, sessions, tools, skills, compression, title
> generation, and auxiliary clients. Hardens fallback-provider behavior so
> routed profiles **fail closed** when scoped credentials are missing, instead
> of silently falling back to global credentials.

Разложение по слоям и текущий статус:

| Слой | Цель | Сейчас на ветке | Фаза |
|---|---|---|---|
| Config (`config.yaml`) | свой на профиль | глобальный | 1 |
| Память (`memories/MEMORY.md`) | своя | общая | 1 |
| Sessions / state (`state.db`) | свои (namespace) | легаси `agent:main` | 1 |
| SOUL.md / system prompt / identity | свой | глобальный | 1 (+ cache-bust) |
| `.env` / провайдер-креды | профильный secret-scope | глобальный `~/.hermes/.env` | 1 (+ Фаза 4 строгость) |
| Skills / toolsets | свои | общие (import-time leak) | 3 |
| Исполнение тулзов (write_file/patch/terminal/code) | под профильным HERMES_HOME | под глобальным | **2 (критично)** |
| Подпроцессы (MCP, kanban, terminal) | профильные креды/HOME | глобальные | 2 |
| Auxiliary client / provider+auth fallback | профильный резолв без `os.environ` | только per-platform model | 4 |
| Background process scoping | metadata несёт профиль | не несёт | 5 |
| Валидация/диагностика изоляции | `audit-isolation`, canonicalize, symlink-guard | нет | 6 |

---

## 2.1. Матрица покрытия (для самопроверки полноты)

### A. Все слои изоляции (объединение финального scope #18510) → фаза

| # | Слой | Фаза | Примечание |
|---|---|---|---|
| 1 | HERMES_HOME (config/skills/memory/SOUL/sessions) | 1 | через `_profile_runtime_scope` |
| 2 | `config.yaml` профиля | 1 | home-override |
| 3 | Память `memories/MEMORY.md` | 1 | home-override |
| 4 | Sessions/state — **инстанс `state.db`** | 1 | ⚠ дыра №4: путь кэшируется на импорте |
| 5 | SOUL / system prompt / identity | 1 | + cache-bust; ⚠ дыра №5: агент строить в scope |
| 6 | `.env` / runtime env | 1 | secret-scope (строго, Решение B) |
| 7 | Provider resolution | 4 | |
| 8 | `auth.json` | 4 | не пропустить |
| 9 | Credential pools | 4 | не пропустить |
| 10 | Auxiliary clients | 4 | |
| 11 | Context compression | 4 | под scope |
| 12 | Title generation | 4 | под scope |
| 13 | Fail-closed strict auth | 4 | нет тихого фолбэка на main |
| 14 | Исполнение тулзов (write_file/patch/terminal/code) | 2 | 🔴 главная грабля |
| 15 | Подпроцессы env (+ **MCP** spawn) | 2 | профильный env, не `os.environ` |
| 15a | **MCP-серверы профиля** (реестр соединений + видимость тулзов) | 3 | ✅ конфиг профиле-зависим + home/env проброшены; 🔴 `_servers` глобален по имени → ре-кей по **фингерпринту конфига** (дедуп идентичных, изоляция разных) + per-profile visibility — ОБЯЗАТЕЛЬНО (одноимённые серверы = норма) |
| 16 | Skills / toolsets | 3 | динамический резолв, не import-time |
| 17 | `/reload-mcp`, `/reload-skills` | 3 | против профильного home |
| 18 | Process registry / background scoping | 5 | metadata несёт профиль |
| 19 | Cron `deliver:` routing | 5 | резолв в профильный контекст |
| 20 | Safe-root / canonicalize / symlink-guard / `.hermes_profile.json` | 6 | |
| 21 | `hermes profile audit-isolation` | 6 | диагностика |
| 22 | `user_profile_enabled: true` дефолт | 6 | для routed-агентов |
| — | Gateway tools/MCP → профиль | **намеренно НЕ изолируем** | граница по дизайну; профиль объявляет своё; бридж = отдельный opt-in PR |

### B. Все грабли → фаза, где чинятся

| Грабля | Источник | Фаза | Как закрывается |
|---|---|---|---|
| G1: агент-кэш не бьётся на правку `SOUL.md` | 5.1.1 | 1 | раздельный session_key + identity-digest в сигнатуре кэша |
| G2: ContextVar не долетает до исполнения тулзов → запись в чужой SOUL | 5.1.2 / 5.4.3 | 2 | **явный `profile_name` (паттерн #20096)** для памяти/SOUL/file-тулзов — корень, а не симптом; subprocess-**env** из #18510 |
| G3: конфиг должен быть «минимальным», `agent.system_prompt` → фолбэк на main | 5.1.3 | 1 | проверка (е): полный декларативный конфиг работает |
| G4: skills-leak через import-time `SKILLS_DIR` | 5.3 | 3 | динамический резолв home |
| G5: background process — утечка `session_id` между профилями | 5.2 | 5 | profile identity в metadata процесса |
| G6: `/reload-mcp` `/reload-skills` бьют по глобалу | 5.2 | 3 | reload против профильного home |
| G7: FUSE deadlock на macOS облачных маунтах | 5.4.1 | — | Решение D (док: профили локально), не баг Hermes |
| G8: `user_profile_enabled` дефолт `false` | 5.4.2 | 6 | дефолт `true` в шаблоне |
| **H1 (наша находка): путь `SessionStore`/`SessionDB` кэшируется (импорт-константа)** | раздел кода | 1 | профильный инстанс БД / ленивый путь |
| **H2 (наша находка): агент конструируется вне scope** | раздел кода | 1 | scope охватывает cache-lookup + build |

> **Вывод проверки:** все 22 слоя изоляции эталона и все 8 граблей upstream-теста
> закрыты фазами 1–6 (G7 — документацией, т.к. это не баг Hermes). Дополнительно
> мы нашли 2 дыры (H1/H2), которых в публичном тексте #18510 не было явно, —
> учтены в Фазе 1. Если реализовать все фазы и пройти приёмочные кейсы раздела 7,
> изоляция профиля полная.

---

## 3. План реализации по фазам

> Делать строго по порядку. После каждой фазы — прогон тестов и ручной smoke на
> двух топиках с разными профилями. Коммиты — Conventional Commits, как в репо.

### Фаза 0 — решения и подготовка (обязательно зафиксировать до кода)

**Решение A. Условие входа в scope.** НЕ завязываться на `multiplex_profiles`.
Ввести явный признак «у этого source есть привязанный профиль, отличный от
главного». Рекомендуемый helper:

```python
def _routed_profile_for_source(self, source) -> Optional[str]:
    """Имя профиля, привязанного к топику источника, или None.
    None  → непривязанный топик: ничего не скоупим, поведение БЕЗ изменений.
    "<n>" → входим в _profile_runtime_scope(get_profile_dir(<n>)) на весь ход.
    """
    try:
        key = _topic_profile_key(self._normalize_source_for_session_key(source))
        name = (_load_topic_profiles().get(key) or "").strip()
        if not name or name in ("default", self._active_profile_name()):
            return None
        return name
    except Exception:
        return None
```

Так непривязанные топики и «General» не меняют поведение вообще (zero-regression),
а скоуп включается только для реально привязанного профиля.

**Решение B. Строгие или сливаемые креды.** `build_profile_secret_scope` —
**строгий** (только `<profile>/.env`; «глобальные» env берутся из `os.environ`
напрямую через `_is_global_env`). Значит, привязанный топик НЕ увидит ключ,
который есть в `~/.hermes/.env`, но отсутствует в `<profile>/.env` (fail-closed).
- Для текущего сетапа это ОК: рабочие ключи (`DEEPSEEK_API_KEY`, `MINIMAX_API_KEY`,
  OpenRouter, Tavily) уже продублированы во все `profiles/*/.env` (проверено ранее).
- Если хочешь поведение «профиль поверх глобального» — собирай scope как
  `{**_relevant_global_env(), **load_env_file(profile/.env)}`. **Реши явно и
  задокументируй в PR.** По умолчанию следуй upstream: строго (fail-closed) —
  это безопаснее и совпадает с эталоном.

**Решение C. `multiplex_active` не трогаем.** Оставить `set_multiplex_active(False)`
(`gateway/run.py:2710`). `get_secret` при установленном scope читает из него
независимо от этого флага; для непривязанных топиков scope не ставится → чтение
из `os.environ` как сейчас. Включать глобальный fail-closed (raise на unscoped)
НЕ надо — это сломает все не-gateway вызовы.

**Решение D. Где живёт `MEMORY.md` профиля.** macOS + облачные маунты
(iCloud/Google Drive через FUSE) → дедлок при тяжёлом I/O (см. грабли, edge case
#1). Профильные home держать **локально**, не на смонтированном облаке.

### Фаза 1 — открыть обе двери для привязанных топиков (≈80% эффекта, малый дифф)

Файлы: `gateway/run.py`.

1. **`_run_agent` (:15180)** — вместо гейта на `multiplex_profiles`:
   ```python
   routed = self._routed_profile_for_source(source)
   if routed is None:
       return await self._run_agent_inner(...)          # без изменений
   profile_home = get_profile_dir(routed)               # из hermes_cli.profiles
   with _profile_runtime_scope(profile_home):
       return await self._run_agent_inner(...)
   ```
   (Можно сохранить и старую multiplex-ветку — объединить условия: входим в scope,
   если `multiplex_profiles` ИЛИ `routed is not None`.)

2. **`_session_key_for_source` (:3296-3299)** — namespace по профилю и для
   single-gateway привязок:
   ```python
   _profile = None
   if source.profile:                                   # источник уже помечен на :3281
       _profile = source.profile                        # снять зависимость от multiplex
   elif getattr(config, "multiplex_profiles", False):
       from hermes_cli.profiles import get_active_profile_name
       _profile = get_active_profile_name() or "default"
   return build_session_key(source, ..., profile=_profile)
   ```
   **ОСТОРОЖНО:** меняется session-ключ привязанных топиков → новые сессии. Это
   ожидаемо (профиль = своя сессия), но проверь, что `/new`, авто-тайтл,
   topic-rebinding и `_record_telegram_topic_binding` (`slash_commands.py:275`)
   используют **тот же** ключ (иначе привязка будет указывать на старую сессию).

3. **SOUL-cache-busting.** Раздельный session_key уже даёт разный кэш-агент на
   профиль. Дополнительно: при правке `SOUL.md` уже живого профиля кэш не бьётся
   (грабля №1). Минимально — задокументировать воркэраунд (`/new` в топике или
   рестарт). Правильно — включить профильный home/identity-digest в сигнатуру
   кэша: смотри как #18510 «busts both the gateway agent cache and the stored
   system-prompt snapshot» (донор: `agent/agent_init.py`, `agent/system_prompt.py`,
   `tests/test_system_prompt_identity_digest.py`). См. `_refresh_agent_cache_message_count`
   (`run.py:14538`) и места evict (:14617/:16293) как точки внедрения.

4. **🔴 СКРЫТАЯ ДЫРА: `SessionStore`/`SessionDB` НЕ редиректятся home-override'ом.**
   Они конструируются один раз на старте: `self.session_store = SessionStore(...)`
   (`run.py:2738`), `self._session_db = SessionDB()` (`run.py:2900`), а дефолтный
   путь — **константа уровня импорта** `DEFAULT_DB_PATH = get_hermes_home()/"state.db"`
   (`hermes_state.py:117`). ContextVar-override их **не** перенаправит → привязанный
   топик писал бы namespaced-ключ в **глобальный** `state.db`, а не в профильный.
   **Что делать:** для routed-хода дать профильный `SessionStore`/`SessionDB`
   (вариант A: конструировать профиль-скоупленный инстанс по `get_profile_dir(name)`
   и использовать его в routed-потоке; вариант B: сделать путь БД ленивым —
   резолвить `get_hermes_home()/"state.db"` в момент доступа, а не на импорте).
   Это ровно предупреждение автора #18510 (раздел 6.1): «routed flows keep using
   the **active profile** SessionStore/SessionDB for `/new`, auto-title, rebinding».
   Затрагивает: `/new`, авто-тайтл, `_record_telegram_topic_binding`
   (`slash_commands.py:275`), handoff-поллинг по `state.db` (`run.py:6371/6405`).

5. **🔴 СКРЫТАЯ ДЫРА: агент должен СТРОИТЬСЯ внутри scope.** `AIAgent(...)`
   конструируется в нескольких местах (`run.py:9932`, `:12015`, `:16314`), а кэш
   читается и на quick-пути (`:6681`) — **вне** `_run_agent`. Если для routed-сессии
   агент соберётся до входа в `_profile_runtime_scope`, профильный `SOUL.md`/identity
   при билде НЕ подхватятся, даже с раздельным session_key. **Что делать:**
   гарантировать, что для привязанного топика **и чтение кэша, и построение агента**
   происходят внутри scope. Практичнее всего — поднять вход в scope на уровень,
   охватывающий cache-lookup+build (рассмотреть обёртку в `_handle_message_with_agent`
   `run.py:9468` или в общем пути перед `:6681`/`:16314`), а не только вокруг
   `_run_agent_inner`. Проверить ВСЕ сайты сборки `AIAgent`, ведущие к routed-сессии.

6. **Память/SOUL — взять explicit-`profile_name` из #20096 (надёжнее ContextVar).**
   Лифтнуть `get_memory_dir(profile_name)`, `get_soul_path(profile_name)`,
   `is_standard_profile` (доноры: `tools/memory_tool.py`, `hermes_constants.py` из
   #20096) и пробросить `profile_name` в `MemoryStore(...)`. Тогда память/SOUL
   изолируются явным параметром и не зависят от того, долетел ли ContextVar (см. 1.4).
   Тест-донор: `tests/gateway/test_profile_memory.py` (#20096).

**Тесты Фазы 1 (написать):** привязать топик A→profileA, B→profileB; проверить
что (а) `MEMORY.md` пишется в `profiles/<n>/memories/`, (б) session_key различен,
(в) SOUL разный, (г) непривязанный топик пишет в глобальный home (zero-regression),
(д) **сессии/тайтлы пишутся в профильный `profiles/<n>/state.db`, а не в глобальный**
(закрывает дыру №4), (е) **полностью декларативный профильный `config.yaml` с
`agent.system_prompt` НЕ откатывается на главный `~/.hermes/SOUL.md`** (грабля 5.1.3 —
раньше требовалось держать конфиг минимальным; у нас это должно работать).

### Фаза 2 — ContextVar в исполнение тулзов (КРИТИЧНО — главная грабля)

**Проблема (грабля №2, полный текст в разделе 5):** `write_file`/`patch` и другие
тулзы исполняются в контексте, куда ContextVar `_HERMES_HOME_OVERRIDE` **не
пропагируется** (тред/подпроцесс созданы без `copy_context()`), поэтому
`get_hermes_home()` внутри тулзы откатывается на глобальный `~/.hermes` →
**агент может перезаписать `~/.hermes/SOUL.md` вместо профильного**. Это
ограничение уровня `contextvars`, не баг конкретной строки.

Что делать (порт из #18510):
- Протащить активный профильный home/secret-scope **явно** во все пути исполнения
  тулзов и подпроцессов, а не полагаться на наследование ContextVar.
- Донорские файлы: `tools/process_registry.py` (метадата процесса несёт
  `agent_profile`/`agent_hermes_home`), `tools/terminal_tool.py`,
  `tools/code_execution_tool.py`, `tools/file_tools.py`,
  `tools/environments/local.py`. Подпроцессам передавать профильный env
  (из secret-scope), НЕ `dict(os.environ)`.
- **MCP-подпроцессы** профиля должны стартовать под профильным home/env. Точка:
  `tools/mcp_tool.py:2943` уже умеет `set_hermes_home_override(home_override)` —
  убедиться, что для routed-сессии туда приходит профильный home, а env spawn'а
  берётся из secret-scope, а не из `os.environ`.
- **Предпочтительный путь для файлов (из #20096): явный `profile_name`, а не починка
  ContextVar.** Для file-write тулзов протащить профильный home/`profile_name`
  параметром (как `get_memory_dir(profile_name)`/`get_soul_path(profile_name)`) —
  тогда даже если ContextVar потерян в executor-треде, путь резолвится правильно.
  Это снимает КОРЕНЬ G2, а не лечит симптом. Доноры #18510 (process_registry/
  terminal/file_tools) использовать для subprocess-**env**; для путей файлов — паттерн #20096.
- Эталонный тест-донор: `tests/test_subprocess_home_isolation.py` (572 строки).

**Проверка приёмки Фазы 2:** в привязанном топике попросить агента
`write_file("SOUL.md", ...)` / `patch` — файл должен лечь в `profiles/<n>/SOUL.md`,
а **глобальный `~/.hermes/SOUL.md` остаться нетронутым**. До фикса — воркэраунд:
писать файлы через `terminal()` (но цель — убрать необходимость воркэраунда).

### Фаза 3 — динамический резолв skills/toolsets профиля

**Проблема (грабля: «skills tooling profile leak»):** `skills_list`, `skill_view`,
slash-reload/invoke и `skill_manage` резолвили папку через **import-time
`SKILLS_DIR`** → утечка глобальных skills в привязанный профиль.

Что делать: резолвить активный профильный home **динамически** в момент вызова,
не на импорте. Доноры: `tools/skills_tool.py`, `tools/skill_manager_tool.py`,
`agent/skill_commands.py`. Тест-донор: `tests/tools/test_skills_profile_isolation.py`.

**Команды reload в routed-топике.** `/reload-mcp` (`slash_commands.py:3932` —
«reconnect MCP servers and rebuild the cached agent») и `/reload-skills`
(`slash_commands.py:3995` — «rescan skills dir») должны выполняться против
**профильного** home, а перестроение кэша агента — попасть в профильный
session_key. Проверить, что из привязанного топика они не перечитывают/не
перестраивают глобальный профиль.

**Граница по дизайну (повторить!):** gateway-level `platform_toolsets` /
`mcp_servers` **намеренно НЕ** прокидываются в привязанный профиль. Профиль обязан
объявить свои `toolsets`/`mcp_servers` в собственном `config.yaml`. Бридж
gateway-тулзов — отдельная opt-in фича с security-ревью (НЕ в этом PR).

**🔴 MCP-изоляция — отдельный сложный подпункт (проверено по коду).**
Чтобы у каждого профиля были СВОИ индивидуальные MCP-серверы — мало объявить их в
профильном `config.yaml`. Состояние кода:
- ✅ **Источник конфига профиле-зависим:** `_load_mcp_config()` (`mcp_tool.py:3080`)
  и `_enabled_mcp_servers(config)` (`agent/coding_context.py:566`) читают `mcp_servers`
  через `load_config()`/`read_raw_config()` → под home-override это **профильный**
  config. (Проверить, что `read_raw_config` уважает override.)
- ✅ **Home/env в MCP-loop пробрасывается:** `_wrap_with_home_override()`
  (`mcp_tool.py:2921`) переносит home-override в корутины общего MCP-loop; env запуска
  собирается профильно (`_build_safe_env` + secret-scope), не из `os.environ`.
- 🔴 **ГЛАВНАЯ ДЫРА — реестр соединений ГЛОБАЛЬНЫЙ по имени:**
  `_servers: Dict[str, MCPServerTask]` (`mcp_tool.py:2444`) + `_server_connect_errors`
  (`:2446`) + `_server_error_counts` (`:2465`) ключуются **только по `server_name`**,
  на один процесс-глобальный MCP-loop. → Два профиля с **одноимённым** сервером
  (оба `github`, разные токены) **коллизируют/делят одно соединение**.
- 🔴 **Глобальный tool-registry:** MCP-тулзы регистрируются в общий `tools.registry`
  по имени тула (`_register_server_tools`, `:1615/2406`) + глобальная карта
  tool→server (`:4383`). Видимость на профиль держит профильный toolset
  (`_enabled_mcp_servers` под home-override) — но сам реестр общий.

**Что делать (новая работа — прямых доноров нет):**
1. **Ключевать `_servers` (и error-карты) по ФИНГЕРПРИНТУ конфига**, а не по голому
   имени. Фингерпринт = хэш разрешённого конфига сервера (command/args/env/url/
   headers ПОСЛЕ интерполяции `${ENV}` в скоупе профиля). Тогда:
   - одинаковое имя + ИДЕНТИЧНЫЙ конфиг у профилей → один фингерпринт → **одно общее
     соединение** (эффективно — для общих серверов как `repowise`/`gitnexus`);
   - одинаковое имя + РАЗНЫЙ конфиг (разные токены через профильные `.env`) → разные
     фингерпринты → **раздельные соединения** (изоляция, как `github` work/personal).
   Решает оба кейса автоматически. (Проще, но расточительнее: ключ `(profile, name)` —
   плодит дубль-соединения даже для идентичных серверов.)
2. **Гарантировать, что routed-агент видит/вызывает только MCP-тулзы своего профиля**
   (фильтр по профильному toolset + неймспейс tool→server по фингерпринту/профилю,
   чтобы одноимённые тулзы разных соединений не затирали друг друга в глобальном
   `tools.registry`).
3. `/reload-mcp` из топика — уже целимся на профильный home (см. выше).
4. Фингерпринт/ключ удобно нести вместе с явным `profile_name` (паттерн #20096, 1.4).

**Приёмка:** два профиля, у каждого MCP-сервер с **ОДИНАКОВЫМ именем** но разным
токеном → каждый агент ходит в СВОЙ; списки тулзов на профиль не пересекаются.

**Объём (пересмотрено):** одинаковые имена серверов у нескольких профилей —
**НОРМА** (`github`/`gitnexus`/`repowise` на хосте, нужные 2–3 профилям). Текущий код
из-за guard'а «имя уже в `_servers` → не переподключать» (`mcp_tool.py:4079/4184`)
заставит профиль B молча использовать соединение/токен профиля A. Поэтому
**фингерпринт-кеинг (пункт 1) ОБЯЗАТЕЛЕН**, не опция; visibility (пункт 2) тоже.
Это работа сверх доноров #18510/#20096. Конфиг при этом простой: в `config.yaml`
каждого профиля свой блок `mcp_servers` (имена могут совпадать).

**Готовые рычаги конфига (используем как есть):** per-server флаг
`mcp_servers.<name>.enabled: true|false`; `enabled_toolsets`/`disabled_toolsets`
на профиль (`agent_init.py:179-180`); `mcp_servers.<name>.tools.include/exclude` —
сузить набор тулзов сервера. Опц. enhancement (НЕ в MVP): наследование `mcp_servers`
из главного конфига + per-profile allow-list, чтобы не дублировать определения.

**Лёгкий режим топика + per-channel toolsets — донор PR #39169.** Для топиков,
которым НЕ нужен полный профиль (одноразовый воркер): `channel_routes`-конфиг даёт
**свежую сессию на сообщение**, **урезанный тулсет на канал** и **пропуск
memory/context-файлов**. Доноры: `gateway/platforms/base.py` (+90),
`gateway/run.py` (+148), `hermes_cli/config.py` (+8); тест
`tests/gateway/test_channel_worker_routing.py`. Это комплемент к полному профилю:
профиль = «специалист с памятью», channel_route = «stateless-воркер с парой тулзов».

### Фаза 4 — строгий auth, auxiliary client, provider/title/compression scoping

Что делать (порт из #18510):
- `agent/auxiliary_client.py` (361 строк), `hermes_cli/runtime_provider.py`,
  `hermes_cli/env_loader.py`, `hermes_cli/auth.py` — провайдер/креды/**`auth.json`**/
  **credential pools** резолвятся из профиля без мутации `os.environ`. (Эталон
  #18510 явно перечисляет «`.env`, `auth.json`, credential pools, provider
  resolution, auxiliary clients» — не пропусти `auth.json` и пулы кредов.)
- **Fail-closed:** при отсутствии профильных кредов — видимая ошибка, без тихого
  фолбэка на глобальные; внешне-процессные креды в строгом режиме блокируются.
- Компрессия контекста и генерация заголовков сессии — тоже под профильным scope.

### Фаза 5 — scoping фоновых процессов

Метадата процесса (`tools/process_registry.py`) должна нести profile identity,
чтобы completion-события пересобирали **правильный** routed-source и `session_id`
не утекал между профилями. Cron-доставка с `deliver: telegram:CHAT_ID:THREAD_ID`
должна резолвиться в изолированный профильный контекст (в #18510 это
протестировано и работает). Сверься с уже имеющейся на ветке логикой
topic-binding после `/new` (`slash_commands.py:269-277`).

**Cron-ownership на профиль — донор PR #20096** (`cron/jobs.py`, +21): каждый
профиль владеет своими cron-джобами, доставка резолвится в его контекст. Лифтнуть
как образец привязки джоб к профилю.

### Фаза 6 — валидация и диагностика

- Канонизировать профильный home, **отклонять symlink/path-escape**, валидировать
  identity через `.hermes_profile.json` (как в финале #18510).
- Портировать команду **`hermes profile audit-isolation`** — детект пересечения
  профиля с main без печати секретов (донор: `hermes_cli/profiles.py`,
  `hermes_cli/main.py`). Очень полезно для приёмки.
- Дефолты профиля: ставить `user_profile_enabled: true` в шаблоне новых профилей
  (грабля: по умолчанию `false`, а для routed-агентов нужен `true`).

---

## 4. Донорские файлы из PR #18510 и как снять их диффы

PR `#18510` (`feat(telegram): route forum topics to Hermes profiles`) **открыт, но
заброшен** автором (см. раздел 6). Не мёрджить целиком (10221+/891−, 60 файлов,
конфликтует с нашим базисом). **Брать точечные хунки.** Head-ветка автора:
`ayoahha:feat/topic-profile-routing`.

Снять патч одного файла:
```bash
gh api "repos/NousResearch/hermes-agent/pulls/18510/files" --paginate \
  --jq '.[] | select(.filename=="tools/process_registry.py") | .patch'
```

Список файлов с объёмом правок (отсортировано):
```bash
gh api "repos/NousResearch/hermes-agent/pulls/18510/files" --paginate \
  --jq '.[] | "\(.additions)+/\(.deletions)-\t\(.filename)"' | sort -rn
```

Ключевые доноры по фазам:

| Фаза | Доноры (filename) | +строк |
|---|---|---|
| 1 | `gateway/run.py`, `gateway/session.py`, `agent/agent_init.py`, `agent/system_prompt.py` | 1618 / 31 / 54 / — |
| 2 | `tools/process_registry.py`, `tools/terminal_tool.py`, `tools/code_execution_tool.py`, `tools/file_tools.py`, `tools/environments/local.py` | 148 / 85 / 19 / 48 |
| 3 | `tools/skills_tool.py`, `tools/skill_manager_tool.py`, `agent/skill_commands.py` | 27 / 19 |
| 4 | `agent/auxiliary_client.py`, `hermes_cli/runtime_provider.py`, `hermes_cli/env_loader.py`, `hermes_cli/auth.py` | 361 / 229 / 49 / 103 |
| 6 | `hermes_cli/profiles.py`, `hermes_cli/main.py`, `gateway/config.py`, `gateway/platforms/base.py`, `hermes_constants.py` | 443 / 46 / 42 / 247 / 19 |
| тесты | `tests/gateway/test_topic_profile_routing.py`, `tests/test_subprocess_home_isolation.py`, `tests/tools/test_skills_profile_isolation.py`, `tests/hermes_cli/test_runtime_provider_resolution.py` | 3812 / 572 / … |
| sandbox | `scripts/setup_topic_routing_sandbox.sh` | 119 |

> ВАЖНО: у нас **другой механизм маршрутизации** (рантайм `/profile`-стор, не
> статический конфиг `telegram.topic_profiles`). Поэтому из доноров берём
> **слой изоляции** (home/secret/tools/skills/auth scoping), а **резолвер источника
> → профиль** оставляем наш (`_routed_profile_for_source` + стор). Не тащить
> `topic_profiles`-конфиг и его валидацию из `base.py` как маршрутизатор —
> только как образец canonicalize/symlink-guard для Фазы 6.

### 4A. Дополнительные доноры — PR #20096 и #39169 (всплыли в issue #10143)

**PR #20096 (`feat: channel-based profile routing`, @Burgunthy)** — 1541+/237−,
24 файла, открыт, 0 ревью. Таргетит Discord, движок платформонезависим.
**Иная стратегия изоляции — явный `profile_name` (см. 1.4).** Что брать:

| Что | Файл-донор (#20096) | Куда |
|---|---|---|
| `get_memory_dir(profile_name)`, `get_soul_path`, `is_standard_profile`, `MemoryStore(profile_name=)` | `tools/memory_tool.py`, `hermes_constants.py` | Фаза 1 (память/SOUL) |
| Движок `ProfileRoute`+specificity+forum-hierarchy | `gateway/profile_routing.py` (196) | референс (если захотим конфиг-роутинг рядом с `/profile`) |
| `profile_name` passthrough через runner/agent | `gateway/run.py` (156/170), `agent/agent_init.py`, `agent/prompt_builder.py`, `agent/skill_utils.py` | Фаза 1/2 (явная изоляция) |
| Cron-ownership на профиль | `cron/jobs.py` (+21) | Фаза 5 |
| Тесты | `tests/gateway/test_profile_memory.py` (64), `test_profile_name_passthrough.py` (232), `test_profile_routing.py` (217) | Раздел 7 |
| Тул управления профилями | `tools/profile_manager.py` (336) | бонус UX |

**PR #39169 (`feat: channel-scoped gateway worker routing`, @hedaayat)** — 367+/8−,
4 файла, открыт, обновлён 2026-06-23. НЕ полная изоляция — channel-level опции:

| Что | Файл-донор (#39169) | Куда |
|---|---|---|
| `channel_routes`: fresh-сессия/сообщение, урезанный тулсет, skip memory/context | `gateway/platforms/base.py` (90), `gateway/run.py` (148), `hermes_cli/config.py` (8) | Фаза 3 (per-channel toolsets, ephemeral) |
| Per-channel response splitters | `gateway/platforms/base.py` | бонус (оформление) |
| Тест | `tests/gateway/test_channel_worker_routing.py` (121) | Раздел 7 |

Снять патч любого файла:
```bash
gh api "repos/NousResearch/hermes-agent/pulls/20096/files" --paginate \
  --jq '.[] | select(.filename=="gateway/profile_routing.py") | .patch'
```

> ВАЖНО: #20096/#39169 — **open, 0 ревью, разной свежести.** Майним куски, не мёрджим.
> Резолвер «источник→профиль» оставляем наш (`/profile`-стор); из #20096 берём
> **стратегию явной изоляции памяти/SOUL** + тесты; из #39169 — per-channel toolsets.

---

## 5. ГРАБЛИ — полный текст полевых отчётов (читать перед кодом)

Источник — комментарии к PR #18510. Это уже наступленные грабли; экономят дни.
Ссылка на тред: https://github.com/NousResearch/hermes-agent/pull/18510

### 5.1. Первый полевой тест — @Donmeusi (2026-05-03) — три критичные проблемы

> **Test Report: Topic Profile Routing (PR #18510)** — tested with a real Telegram
> supergroup (3 topics, external profile homes, each with own `SOUL.md`, isolated
> sessions, memory). **What works:** topic→profile routing resolves correctly;
> separate `state.db` per profile; separate sessions; separate `SOUL.md`; log
> includes resolved profile name; per-profile model override works.
>
> **Issues encountered:**
>
> **1. Agent cache doesn't bust on SOUL.md changes (critical).** When a profile's
> SOUL.md is created or modified after the agent was first initialized for that
> topic, the cached agent is reused with the old (or default) identity. Neither
> `/new` nor gateway restart reliably clears this. *Workaround:* Delete the
> profile's `state.db*` files before first use, or ensure SOUL.md exists before
> the first message arrives in the topic.
>
> **2. ContextVar propagation gap in tool execution (critical).** When a routed
> agent calls tools like `write_file`, the `hermes_home_override` ContextVar is
> lost. This causes `get_hermes_home()` to fall back to the gateway's default
> `~/.hermes/` instead of the profile home. Consequence: the agent can
> accidentally write to `~/.hermes/SOUL.md` instead of the profile's SOUL.md,
> overwriting the main identity. *Workaround:* Pre-populate all profile SOUL.md
> files before starting the gateway. Avoid asking routed agents to modify their
> own identity files.
>
> **3. Profile config must stay minimal.** Adding `agent.personalities`,
> `agent.personality`, or `agent.system_prompt` to a profile config caused the
> ContextVar override to behave unpredictably. The agent loaded the main
> `~/.hermes/SOUL.md` identity despite the override being set. *Workaround:* Keep
> profile configs minimal — only `model`, `memory`, and `agent.max_turns`. Let
> `SOUL.md` handle identity exclusively.
>
> A proper fix would involve: **Including profile home path in the agent cache
> signature**; **Ensuring ContextVar propagation survives through all tool
> execution paths (not just `asyncio.to_thread`)**.

### 5.2. Раунд фиксов — @ayoahha (2026-05-04) — что закрыли

> - `SOUL.md` changes in a routed profile **bust both the gateway agent cache and
>   the stored system-prompt snapshot**, so deleting `state.db*` should no longer
>   be needed.
> - Routed profile tool execution now **keeps the active profile `HERMES_HOME`
>   across the relevant thread/executor paths**.
> - `/reload-mcp` and `/reload-skills` now reload against the routed profile home
>   when invoked from a routed topic.
> - Background process metadata now persists profile identity; completion events
>   rebuild the routed source correctly; `process` actions/listing are scoped to
>   the active profile so raw `session_id` leakage should not cross profiles.
> - Profile config isolation has regression coverage for `SOUL.md`,
>   `agent.system_prompt`, model/toolsets, `.env`, memory, sessions, process
>   notifications, and concurrent routed topics.

### 5.3. Skills-leak фикс — @ayoahha (2026-05-05)

> Fixed the reproducible profile leak in skills tooling: `skills_list`,
> `skill_view`, slash skill reload/invocation, and `skill_manage` now resolve the
> active routed profile home **dynamically instead of relying on an import-time
> `SKILLS_DIR`**.
>
> **Important behavior note:** this PR intentionally does **not** proxy gateway
> tools/MCP servers into routed profiles by default. That keeps the isolation
> boundary explicit and avoids leaking gateway secrets/capabilities into a
> specialized profile. A true gateway tool bridge should be a separate opt-in
> feature with its own security review and tests.

### 5.4. Итоговый E2E на 7 топиках — @Donmeusi (2026-05-05) — что подтвердилось и edge-cases

> Verified against latest fixes: SOUL.md cache-bust ✅ (no `state.db*` deletion
> needed); routed profile `HERMES_HOME` across thread/executor paths ✅;
> `/reload-mcp`/`/reload-skills` scoped ✅; background process metadata + routed
> source rebuild ✅ (cron `deliver: telegram:CHAT_ID:THREAD_ID` builds correct
> routed context); full config isolation (SOUL, model, toolsets, .env, memory,
> sessions) across **7 concurrent topic profiles** ✅. Full declarative profile
> configs work without falling back to main.
>
> **Edge cases discovered:**
>
> **1. FUSE Deadlock on macOS + Cloud Storage Mount.** When routed profiles write
> to cloud-mounted filesystems (macOS FUSE Google Drive, iCloud, etc.), heavy I/O
> can deadlock (`Resource deadlock avoided`). **Not a Hermes bug.** Recommendation:
> profile skills using cloud storage should use a local staging directory with sync.
>
> **2. `user_profile_enabled` Default (minor).** New profiles implicitly inherit
> `user_profile_enabled: false`. Recommendation: set `true` as explicit default in
> profile creation — cross-session user modeling is essential for routed agents.
>
> **3. ContextVar Tool Propagation (known Python limitation).** Hermes file-write
> tools (`write_file`, `patch`) execute in a separate context where ContextVar-bound
> profile routing doesn't propagate. Workaround: use `terminal()` commands for file
> writes in routed profiles. This is `contextvars`-level behavior.

---

## 6. Статус PR #18510 и заметки автора по merge-конфликтам

- **Состояние:** OPEN, `merged: false`, `mergeable_state: dirty`, метка **P3**,
  последнее обновление 2026-05-31. 0 инлайн-ревью, 20 содержательных комментов.
- **Автор снял поддержку (2026-05-31), дословно:** *«main ушёл далеко, PR стало
  тяжело держать в rebase, конфликтует по многим core-файлам, остаётся P3 без
  пути к ревью/мёрджу… Я больше не поддерживаю и не ребейзлю этот PR. Кто хочет
  фичу — заберите ветку, **cherry-pick'ните части, или закройте и перепишите
  меньшим scope'ом**».* → Наш план = именно «меньший scope поверх нашего
  `/profile`-механизма».

### 6.1. Разрешение исходных конфликтов — @ayoahha (2026-05-05) — прямо про наши файлы

> - `gateway/run.py`: current `main` added Telegram DM **topic-mode/session-binding**
>   support while this PR added topic→profile routing. **Keep both**, but make sure
>   routed profile flows keep using the **active profile** `SessionStore`/`SessionDB`
>   for `/new`, auto-title, and topic rebinding instead of falling back to the
>   global store.
> - `tools/process_registry.py`: current `main` added safe cwd recovery for deleted
>   working directories. **Keep that `_resolve_safe_cwd(...)` behavior AND preserve
>   the routed `agent_profile` / `agent_hermes_home` metadata** from this PR.

> ⚠️ Наша ветка `topic-model-binding` **построена на том самом** topic-mode/session-
> binding из `main`, поэтому при порте хунков мы упрёмся в те же два места. Держим
> правило автора: routed-поток использует профильный `SessionStore`/`SessionDB`,
> и сохраняем `_resolve_safe_cwd` + профильную метадату процесса.

### 6.2. Полный список конфликтных файлов против main — @Donmeusi (2026-05-31)

16 файлов с реальными конфликтами (для оценки объёма порта):
`gateway/platforms/telegram.py`, `gateway/run.py`, `gateway/config.py`,
`gateway/session_context.py`, `gateway/platforms/base.py`, `hermes_constants.py`,
`hermes_state.py`, `run_agent.py`, `tools/terminal_tool.py`,
`tools/skill_manager_tool.py`, `tools/environments/local.py`,
`agent/skill_commands.py`, `hermes_cli/auth.py`, `hermes_cli/runtime_provider.py`,
+ 2 тест-файла.

---

## 7. Тестирование

- **Юнит/регресс (портировать и адаптировать под наш `/profile`-стор):**
  `tests/gateway/test_topic_profile_routing.py` (изоляция SOUL/model/toolsets/.env/
  memory/sessions, конкурентные топики), `tests/test_subprocess_home_isolation.py`
  (Фаза 2), `tests/tools/test_skills_profile_isolation.py` (Фаза 3),
  `tests/hermes_cli/test_runtime_provider_resolution.py` (Фаза 4).
- **Из #20096:** `tests/gateway/test_profile_memory.py`, `test_profile_name_passthrough.py`,
  `test_profile_routing.py` (изоляция памяти/SOUL явным `profile_name`).
  **Из #39169:** `tests/gateway/test_channel_worker_routing.py` (per-channel toolsets).
- **Уже на ветке:** `tests/gateway/test_telegram_topic_mode.py` — не сломать;
  расширить кейсами привязки профиля.
- **Команды:**
  ```bash
  cd ~/.hermes/hermes-agent
  venv/bin/python -m pytest tests/gateway/test_topic_profile_routing.py \
    tests/gateway/test_telegram_topic_mode.py \
    tests/test_subprocess_home_isolation.py \
    tests/tools/test_skills_profile_isolation.py -q -o 'addopts='
  # полный прогон стадии:
  verify-dev --scope standard   # если доступно в окружении
  ```
- **Ручной smoke (обязательно перед PR):** один бот, два DM-топика →
  `/profile alpha` и `/profile beta`. Проверить независимо:
  1. `MEMORY.md` пишется в `profiles/alpha/memories/` и `profiles/beta/memories/`;
  2. разные `SOUL.md`/identity в ответах;
  3. `write_file`/`patch` в топике alpha **не трогает** глобальный `~/.hermes/SOUL.md`
     (Фаза 2 — критичный кейс);
  4. разные модели на топик (уже работает) сохраняются;
  5. **непривязанный** топик/General ведёт себя как раньше (zero-regression);
  6. `hermes profile audit-isolation` не показывает пересечений (после Фазы 6).

---

## 8. Чек-лист для PR в `NousResearch/hermes-agent`

- [ ] Реализованы Фазы 1–6 (или согласованный с мейнтейнерами под-набор);
      каждый слой изоляции покрыт тестом.
- [ ] **Zero-regression** для single-profile без привязок: непривязанные топики и
      `multiplex_profiles: false` ведут себя ровно как до изменений (вход в scope
      только при `_routed_profile_for_source(source) is not None`).
- [ ] Решение по кредам (строго vs merge) задокументировано в описании PR.
- [ ] Граница «gateway tools/MCP не прокидываются в профиль по умолчанию»
      сохранена и описана.
- [ ] Conventional Commits; в описании — ссылка на #18510 как на источник
      исходной фичи и граблей (мы делаем меньший scope поверх рантайм-`/profile`).
- [ ] В описании PR: **`Closes #10143, #4321`** (канонические feature-запросы; 8
      реакций, активный спрос) + упомянуть, что снимает спрос из #18423/#19809.
      Указать #18510/#20096/#39169 как источники донорских кусков.
- [ ] Прогон `pytest` целевых сьютов зелёный; приложить вывод.
- [ ] Ручной Telegram smoke выполнен (пункты раздела 7), особенно Фаза-2 кейс.
- [ ] Обновить `website/docs/user-guide/messaging/telegram.md` (per-topic profile
      isolation, требование объявлять toolsets/mcp в профильном `config.yaml`).
- [ ] Заметка про macOS FUSE-маунты и `user_profile_enabled: true` в доке профилей.
- [ ] Отдельно (НЕ в этом PR): opt-in gateway tool/MCP bridge для профилей —
      с security-ревью.

---

## 9. Быстрый индекс `file:line` (наша ветка)

```
gateway/run.py:1395    _profile_runtime_scope(profile_home)           # сид изоляции
gateway/run.py:2710    set_multiplex_active(...)                       # НЕ трогать (Решение C)
gateway/run.py:2821    self._agent_cache: OrderedDict[str, tuple]      # ключ = session_key
gateway/run.py:2738    self.session_store = SessionStore(...)          # ⚠ путь кэшируется (H1)
gateway/run.py:2900    self._session_db = SessionDB()                  # ⚠ путь кэшируется (H1)
gateway/run.py:6681    self._agent_cache.get(key)                      # чтение кэша (вне _run_agent)
gateway/run.py:9468    _handle_message_with_agent                      # кандидат для подъёма scope
gateway/run.py:9932/12015/16314  AIAgent(...)                          # ⚠ сайты сборки агента (H2)
hermes_state.py:117    DEFAULT_DB_PATH = get_hermes_home()/"state.db"  # ⚠ импорт-константа (H1)
gateway/slash_commands.py:3932  _handle_reload_mcp_command  / :3995 _handle_reload_skills_command
gateway/run.py:2327    _topic_profile_key / :2343 _load_topic_profiles # стор привязок
gateway/run.py:2356    _save_topic_profile / :2367 _remove_topic_profile
gateway/run.py:3274    _session_key_for_source                         # ДВЕРЬ №2 (:3296 гейт)
gateway/run.py:3531    _resolve_session_agent_runtime                  # модель уже per-profile
gateway/run.py:6681    self._agent_cache.get(key)                      # чтение кэша
gateway/run.py:14538   _refresh_agent_cache_message_count              # точка cache-bust
gateway/run.py:14617   _agent_cache.pop(session_key)  / :16293 evict
gateway/run.py:15180   _run_agent  (ДВЕРЬ №1 — гейт на multiplex)
gateway/run.py:15201   _resolve_profile_home_for_source                # уже резолвит source.profile
gateway/run.py:15216   _run_agent_inner
gateway/slash_commands.py:187  _load_topic_models                      # per-topic /model
gateway/slash_commands.py:269  topic-rebinding после /new
gateway/slash_commands.py:305  _handle_profile_command  (/profile)
hermes_constants.py:17  _HERMES_HOME_OVERRIDE ContextVar / :22 setter / :54 get_hermes_home
agent/secret_scope.py:197  build_profile_secret_scope (строгий)
agent/secret_scope.py: get_secret (fail-closed при multiplex_active) / set_multiplex_active
```

---

## 10. TL;DR для реализующего агента

1. Прочитай разделы 1, 5, 6 — там модель и все грабли.
2. Фаза 1: открой две двери (`_run_agent:15180`, `_session_key_for_source:3296`)
   через `_routed_profile_for_source(source)`; непривязанные топики не трогай.
   Это сразу даёт config/memory/sessions/SOUL/.env на профиль (кэш агента
   изолируется автоматически — он ключуется по session_key).
3. Фаза 2 — обязательна: ContextVar не долетает до исполнения тулзов → агент
   пишет в чужой `~/.hermes/SOUL.md`. Протащи профильный home/env явно
   (доноры: `process_registry/terminal_tool/code_execution_tool/file_tools/
   environments/local`). Тест-приёмка — пункт 7.3.
4. Фазы 3–6 — skills/auth/процессы/диагностика по донорам из #18510.
5. Бери из #18510 СЛОЙ ИЗОЛЯЦИИ, а резолвер «источник→профиль» оставляй наш.
6. Оформи PR по чек-листу раздела 8.
```
