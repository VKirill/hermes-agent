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

**Тесты Фазы 1 (написать):** привязать топик A→profileA, B→profileB; проверить
что (а) `MEMORY.md` пишется в `profiles/<n>/memories/`, (б) session_key различен,
(в) SOUL разный, (г) непривязанный топик пишет в глобальный home (zero-regression).

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

**Граница по дизайну (повторить!):** gateway-level `platform_toolsets` /
`mcp_servers` **намеренно НЕ** прокидываются в привязанный профиль. Профиль обязан
объявить свои `toolsets`/`mcp_servers` в собственном `config.yaml`. Бридж
gateway-тулзов — отдельная opt-in фича с security-ревью (НЕ в этом PR).

### Фаза 4 — строгий auth, auxiliary client, provider/title/compression scoping

Что делать (порт из #18510):
- `agent/auxiliary_client.py` (361 строк), `hermes_cli/runtime_provider.py`,
  `hermes_cli/env_loader.py`, `hermes_cli/auth.py` — провайдер/креды/`auth.json`
  резолвятся из профиля без мутации `os.environ`.
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
