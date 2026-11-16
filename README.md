# GitLab Event Bot v2.0

Принимает вебхуки GitLab (push, merge request, pipeline) и пересылает их в топик Telegram-супергруппы.
Сообщения о merge request и pipeline — это **одно сообщение**, которое редактируется при смене статуса.

Стек: **FastAPI + Starlette**, **SQLAlchemy 2 (async) + Alembic**, PostgreSQL, Redis, httpx,
[sqladmin](https://github.com/aminalaee/sqladmin) для админ-панели.

Фреймворка для бота и polling **нет**: Telegram присылает обновления на `POST /api/telegram/webhook`
(адрес регистрируется при старте), а ответы отправляются через Bot API с помощью httpx. Это один
процесс, поэтому остановка uvicorn останавливает всё. Если Telegram недоступен или токен неверный,
API всё равно запускается, а причина пишется в лог.

## Установка

Нужны: Python 3.11+, PostgreSQL, Redis, токен бота от [@BotFather](https://t.me/botfather)
и Telegram-супергруппа с включёнными топиками.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # заполните его (local.env тоже читается)
alembic upgrade head        # создать таблицы
uvicorn app.main:app        # запуск
```

После запуска:

| Адрес | Что это |
|---|---|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/api/openapi.json` | схема OpenAPI |
| `/api/health` | проверка работоспособности |
| `/admin` | админ-панель (нужен `ADMIN_PASSWORD`) |

## Настройка

Все параметры задаются переменными окружения или в `.env` (см. `.env.example`).

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота (обязательно) |
| `PROJECT_URL` | публичный **https**-адрес сервиса, без `/` в конце |
| `WEBHOOK_SECRET` | secret_token вебхука Telegram; пусто = без проверки (для GitLab не используется) |
| `TELEGRAM_ADMIN_IDS` | Telegram ID администраторов бота: `123,456` или `[123, 456]` |
| `DATABASE_URL` или `DB_*` | подключение к PostgreSQL |
| `REDIS_URL` | подключение к Redis |
| `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` | админ-панель; пока `ADMIN_PASSWORD` пуст, панель отключена |

### Вебхук Telegram

При старте приложение вызывает `setWebhook` с адресом `PROJECT_URL/api/telegram/webhook`, а имя бота
узнаёт через `getMe`. Поэтому `PROJECT_URL` должен быть публичным **https**-адресом (для локальной
разработки используйте туннель: ngrok или cloudflared). Если адрес пуст или не https, приложение
запускается без регистрации вебхука: бот не получает команды, но события GitLab пересылаются.

`WEBHOOK_SECRET` допускает только символы `A-Z a-z 0-9 _ -` (ограничение Telegram). Сгенерировать:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Вебхук GitLab

Проект или группа → Settings → Webhooks:

- URL: `https://your-domain.com/api/gitlab/webhook` (без `/` в конце)
- Signing token: GitLab генерирует его сам (`whsec_...`); скопируйте и добавьте в админке: **Webhook Signing Tokens** → Create. Пока нет активных токенов, подпись не проверяется
- Triggers: Push events, Merge request events, Pipeline events

Проект создаётся в базе автоматически при первом событии.

## Использование

### Администраторы бота

Команды в группах доступны только администраторам бота. Укажите свой Telegram ID в `TELEGRAM_ADMIN_IDS`
(они создаются при старте) или добавьте администратора в админ-панели.

### Привязка группы

1. В нужной группе (в том топике, куда должны приходить события) администратор отправляет `/register`.
2. В админ-панели открывает **Projects**, выбирает проект и указывает **Telegram Group**. Там же
   настраивается, какие поля показывать в сообщениях.
3. В группе отправляет `/start`, после чего бот начинает присылать события.

### Команды

В группе (только администраторы бота):

| Команда | Действие |
|---|---|
| `/register` | запомнить группу и топик |
| `/start` | включить отправку сообщений |
| `/stop` | выключить отправку сообщений |

В личном чате с ботом:

| Команда | Действие |
|---|---|
| `/start` | бот просит GitLab ID разработчика; после этого в сообщениях он упоминается через `@` |

Ожидание ID длится 5 минут. ID вводится только цифрами.

### Какие события отправляются

- **Push** — одно сообщение на каждый push.
- **Merge request** — открыт, обновлён, одобрен, влит, закрыт и т. д. Сообщение редактируется, пока MR не
  будет влит или закрыт; после этого повторное открытие создаст новое сообщение.
- **Pipeline** — pending, running, success, failed, canceled, skipped, manual. Одно сообщение на
  pipeline, редактируется при смене статуса.

## Разработка

```bash
pip install -r requirements-dev.txt
pytest                                  # тесты используют SQLite и fakeredis
alembic revision --autogenerate -m "…"  # после изменения app/models.py
alembic upgrade head
```

Команды `make run`, `make migrate`, `make test` делают то же самое.

```
app/
  main.py        приложение FastAPI, lifespan (регистрирует вебхук Telegram, завершение работы)
  config.py      настройки из окружения
  models.py      модели SQLAlchemy
  admin.py       админ-панель sqladmin
  api/           HTTP-маршруты: вебхук GitLab, вебхук Telegram, health
  telegram/      клиент Bot API (httpx), модели обновлений, обработчики команд
  schemas/       модели payload GitLab → ParsedEvent, общие модели ответов
  services/      форматирование сообщений, отправка/редактирование, обработка событий
alembic/         миграции
tests/           тесты
```

## Переход с v1 (Django)

В v2 новая схема базы (её создаёт `alembic upgrade head`) с теми же именами таблиц. Используйте новую
базу или сначала удалите старые таблицы Django, затем перенесите нужные данные (проекты, группы,
пользователей, администраторов). Что изменилось:

- aiogram и polling убраны: Telegram работает только через вебхук.
- Сообщения в HTML вместо Markdown: имена веток и пользователей больше не ломают разметку.
- Статус `pending` у pipeline больше не задерживается: первое событие отправляет сообщение, остальные его редактируют.
- Группа должна быть активна (`/start`), иначе события только сохраняются. `/stop` теперь действительно
  останавливает отправку (в v1 логика была перевёрнута).
- Разработчик сопоставляется с пользователем GitLab по GitLab ID; подпись `webhook-signature` проверяется по токенам из админки.
- Пути без `/` в конце: `/api/gitlab/webhook`, `/api/telegram/webhook`, `/api/health`.
- `POST /api/webhook/` удалён: вебхук Telegram регистрируется при старте.
- Duration показывается только у pipeline.
