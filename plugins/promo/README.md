# Плагин МАЯК — Hermes dashboard

Личный promo-pipeline Кирилла Вечкасова. Плагин для Hermes dashboard.

## Структура

```
plugins/promo/
├── api/
│   └── plugin_api.py          # FastAPI router: /api/plugins/promo/*
└── dashboard/
    ├── manifest.json          # манифест для Hermes
    └── index.js               # UI (vanilla JS через window.__HERMES_PLUGIN_SDK__)
```

## Endpoints

- `GET /api/plugins/promo/sources` — список источников
- `POST /api/plugins/promo/sources` — добавить
- `DELETE /api/plugins/promo/sources/<id>` — удалить
- `GET /api/plugins/promo/sessions` — текущая сессия интервьюера
- `GET /api/plugins/promo/weekly` — последний weekly plan
- `GET /api/plugins/promo/drafts` — черновики за 7 дней

## Хранилище

Источники: `~/.hermes/profiles/personal_promo/state/promo-sources.yaml`
Сессии: `~/Work/apps/promo-daemon/state.json`
Журналы: `~/MarketingClients/kirill-vechkasov-personal-brand/journal/`