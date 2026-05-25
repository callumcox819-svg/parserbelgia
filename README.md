# parserbelgia

Парсер [2dehands.be](https://www.2dehands.be/) и [Ricardo.ch](https://www.ricardo.ch/) с выгрузкой в JSON (формат void-parser) и Telegram-ботом.

## Установка

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy config.example.py config.py
```

В `config.py` укажите `BOT_TOKEN` от [@BotFather](https://t.me/BotFather).

### Railway (обязательно)

`config.py` в `.gitignore` — **Railway его не кладёт в контейнер**, даже если файл виден на GitHub.

В проекте Railway → **Variables**:

| Variable | Значение |
|----------|----------|
| `BOT_TOKEN` | токен от @BotFather |
| `PROXY` | `socks5://user:pass@host:1080` или `http://...` |
| `DATABASE_PATH` | опционально, по умолчанию `/app/data/bot.db` на Railway |

### База данных (не терять после деплоя)

На Railway контейнер **без volume** стирается при каждом деплое.

1. В проекте Railway: **Volume** → Create → mount path **`/app/data`**
2. Привязать volume к сервису бота
3. Redeploy

В логах должно быть: `Database: /app/data/bot.db`

Локально БД: `data/bot.db`
| `DEFAULT_LIMIT` | `50` (опционально) |

Сохранить → **Redeploy**.

Токен в открытом `config.py` на GitHub = скомпрометирован → `/revoke` в BotFather и новый токен только в Variables.

## CLI

```bash
python parse_2dehands.py --url "https://www.2dehands.be/q/iphone/" --limit 50
python parse_2dehands.py --url "https://www.2dehands.be/l/telecommunicatie/" -o output/result.json
```

При необходимости BE/EU прокси:

```bash
# в config.py: PROXY = "http://user:pass@host:port"
```

## Telegram-бот

```bash
python bot.py
```

### Railway Variables

| Variable | Описание |
|----------|----------|
| `BOT_TOKEN` | Токен бота |
| `ADMIN_IDS` | Ваш Telegram ID (`@userinfobot`) |
| `PROXY` | Прокси по умолчанию (опционально) |
| `RICARDO_REQUEST_DELAY` | Пауза между запросами Ricardo, сек (по умолчанию `2.5`) |
| `PARSE_REQUEST_DELAY` | Пауза для 2dehands, сек (по умолчанию `0.8`) |

### Возможности

- `/start` — главное меню (команда слева в Telegram)
- **Запустить парсер** — JSON по выбранным категориям
- **Настройки** — площадка (2dehands / Ricardo), категории, лимит JSON (1–500), прокси
- **Ricardo** — медленные запросы (~2.5 с), нужен **CH** residential прокси
- **Админ панель** — выдать/убрать доступ, статистика
- Бот **закрыт** до выдачи доступа админом
- **Чёрный список продавцов** отдельно у каждого пользователя (не дублируются у вас; у других — могут)

Если объявлений меньше лимита — отдаётся всё, что найдено.

## Формат JSON

```json
{
  "items": [
    {
      "item_title": "...",
      "item_photo": "https://images.2dehands.com/...",
      "item_price": "€ 45,00",
      "item_link": "https://link.2dehands.be/m...",
      "item_person_name": "...",
      "created_date": "Vandaag",
      "location": "Antwerpen",
      ...
    }
  ]
}
```

## Репозиторий

https://github.com/callumcox819-svg/parserbelgia
