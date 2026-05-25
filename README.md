# parserbelgia

Парсер объявлений [2dehands.be](https://www.2dehands.be/) с выгрузкой в JSON (формат void-parser) и Telegram-ботом.

## Установка

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy config.example.py config.py
```

В `config.py` укажите `BOT_TOKEN` от [@BotFather](https://t.me/BotFather).

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

Отправьте боту ссылку на поиск или категорию — он вернёт JSON-файл.

Команда: `/parse https://www.2dehands.be/q/iphone/ 30`

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
