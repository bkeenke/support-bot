# Widget API

Base URL: `https://widget.your-domain.com`

Все защищённые эндпоинты требуют заголовок `X-Session-Id`.

---

## POST /widget/session

Создать сессию или вернуть существующую. Вызывается один раз — `session_id` сохраняется на клиенте.

**Запрос**
```http
POST /widget/session
Content-Type: application/json
```
```json
{
  "user_id": 7
}
```

| Поле | Тип | Обязательно | Описание |
| --- | --- | --- | --- |
| `user_id` | int | ✓ | ID пользователя в SHM |

**Ответ 200**
```json
{
  "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "is_new": true
}
```

| Поле | Описание |
| --- | --- |
| `session_id` | UUID сессии — передавать в `X-Session-Id` на все последующие запросы |
| `is_new` | `true` — сессия только что создана, `false` — уже существовала |

**Ошибки**

| Код | Причина |
| --- | --- |
| 400 | `user_id` не передан |
| 404 | Пользователь не найден в SHM (если настроен `GET_ID_URL`) |

---

## POST /widget/message

Отправить текстовое сообщение в чат поддержки. Создаёт форум-топик при первом обращении.

**Запрос**
```http
POST /widget/message
Content-Type: application/json
X-Session-Id: <session_id>
```
```json
{
  "text": "Не работает впн, помогите"
}
```

| Поле | Тип | Обязательно | Описание |
| --- | --- | --- | --- |
| `text` | string | ✓ | Текст сообщения, максимум 4096 символов |

**Ответ 200**
```json
{
  "ok": true
}
```

**Ошибки**

| Код | Причина |
| --- | --- |
| 400 | Пустой или слишком длинный текст |
| 401 | Отсутствует или неверный `X-Session-Id` |
| 429 | Слишком много сообщений (лимит: 20 сообщений/минуту на сессию) |
| 500 | Не удалось создать топик или ошибка Telegram API |

---

## POST /widget/upload

Отправить фото или PDF-файл в чат поддержки.

**Запрос**
```http
POST /widget/upload
Content-Type: multipart/form-data
X-Session-Id: <session_id>

file=<binary>
```

| Поле | Описание |
| --- | --- |
| `file` | Файл: изображение (`image/*`) или PDF. Максимум 10 МБ. |


**Ответ 200**
```json
{
  "ok": true
}
```

**Ошибки**

| Код | Причина |
| --- | --- |
| 400 | Поле `file` отсутствует или файл > 10 МБ |
| 401 | Отсутствует или неверный `X-Session-Id` |
| 413 | Файл слишком большой (nginx отклонил до сервера) |
| 429 | Слишком много загрузок (лимит: 10 файлов/минуту на сессию) |
| 500 | Ошибка Telegram API |

---

## GET /widget/messages

Получить историю переписки (сообщения пользователя + ответы поддержки). Использовать polling — вызывать раз в 2–5 секунд пока открыт чат.

**Запрос**
```http
GET /widget/messages?offset=0
X-Session-Id: <session_id>
```

| Параметр | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `offset` | int | 0 | Сколько сообщений уже получено. Передавать `total` из предыдущего ответа |

**Ответ 200**
```json
{
  "messages": [
    {
      "ts": 1749123400,
      "from": "user",
      "text": "Не работает интернет"
    },
    {
      "ts": 1749123456,
      "from": "support",
      "text": "Добрый день! Уже проверяем."
    },
    {
      "ts": 1749123600,
      "from": "support",
      "text": "Смотрите скриншот",
      "photo_url": "/widget/file/AgACAgI...?sid=3fa85f64-..."
    },
    {
      "ts": 1749123700,
      "from": "support",
      "file_url": "/widget/file/BQACAgI...?sid=3fa85f64-...",
      "file_name": "инструкция.pdf"
    },
    {
      "ts": 1749123800,
      "from": "user",
      "photo_url": "/widget/file/AgACAgI...?sid=3fa85f64-..."
    }
  ],
  "total": 5,
  "offset": 0
}
```

| Поле | Описание |
| --- | --- |
| `messages` | Массив сообщений начиная с `offset` |
| `total` | Общее количество сообщений — передавать как `offset` в следующем запросе |
| `offset` | `offset` из запроса (эхо) |

**Поля сообщения**

| Поле | Тип | Описание |
| --- | --- | --- |
| `ts` | int | Unix timestamp |
| `from` | string | `"user"` — сообщение пользователя, `"support"` — ответ поддержки |
| `text` | string? | Текст (может отсутствовать если только фото/файл) |
| `photo_url` | string? | Относительный URL фото через прокси-эндпоинт |
| `file_url` | string? | Относительный URL файла через прокси-эндпоинт |
| `file_name` | string? | Имя файла (только для документов) |

> `photo_url` и `file_url` возвращаются как относительные пути вида `/widget/file/{file_id}?sid={session_id}`. При запросе браузер должен подставить origin сервера. Токен бота клиенту не передаётся.

**Ошибки**

| Код | Причина |
| --- | --- |
| 401 | Отсутствует или неверный `X-Session-Id` |

---

## GET /widget/file/{file_id}

Прокси для загрузки файлов из Telegram. URL формируется сервером автоматически и возвращается в полях `photo_url` / `file_url` эндпоинта `/widget/messages`. Напрямую конструировать не нужно.

**Запрос**
```http
GET /widget/file/{file_id}?sid={session_id}
```

| Параметр | Описание |
| --- | --- |
| `file_id` | Telegram file_id (из `photo_url` / `file_url` в `/widget/messages`) |
| `sid` | session_id (из `/widget/session`) |

**Ответ 200** — бинарный поток файла с `Content-Type` оригинала.

**Ошибки**

| Код | Причина |
| --- | --- |
| 401 | `sid` отсутствует или сессия невалидна |
| 404 | Файл не найден в Telegram (file_id устарел) |
| 502 | Ошибка при загрузке файла из Telegram |

---

## GET /widget.js

Встраиваемый JS-виджет.

```html
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7">
</script>
```

### Атрибуты

| Атрибут | Обязательно | Описание |
| --- | --- | --- |
| `data-user-id` | ✓ | ID пользователя в SHM |
| `data-api` | — | Base URL API, если отличается от origin скрипта |
| `data-lang` | — | Язык: `ru` (по умолчанию) или `en` |
| `data-color-primary` | — | Основной цвет виджета (кнопка, шапка, исходящие сообщения). По умолчанию `#2563eb` |
| `data-color-primary-dark` | — | Цвет при hover. По умолчанию автоматически темнее `data-color-primary` на 15% |
| `data-color-primary-light` | — | Фон иконок при hover. По умолчанию очень светлый тинт основного цвета |

### Примеры

```html
<!-- Зелёный -->
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7"
        data-color-primary="#16a34a">
</script>

<!-- Фиолетовый с кастомным hover -->
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7"
        data-color-primary="#7c3aed"
        data-color-primary-dark="#5b21b6">
</script>
```

### window.__SW (альтернатива до загрузки скрипта)

```html
<script>
  window.__SW = {
    userId: '7',
    colorPrimary: '#dc2626',
  };
</script>
<script src="https://widget.your-domain.com/widget.js"></script>
```

Поддерживаемые ключи: `api`, `userId`, `lang`, `colorPrimary`, `colorPrimaryDark`, `colorPrimaryLight`.

---

## Полный пример (curl)

```bash
BASE="https://widget.your-domain.com"

# 1. Создать сессию
SID=$(curl -s -X POST "$BASE/widget/session" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 7}' | jq -r .session_id)

echo "Session: $SID"

# 2. Отправить текстовое сообщение
curl -s -X POST "$BASE/widget/message" \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: $SID" \
  -d '{"text": "Не работает интернет"}' | jq

# 3. Загрузить файл (фото или PDF)
curl -s -X POST "$BASE/widget/upload" \
  -H "X-Session-Id: $SID" \
  -F "file=@/path/to/screenshot.png" | jq

# 4. Получить всю историю (offset=0)
curl -s "$BASE/widget/messages?offset=0" \
  -H "X-Session-Id: $SID" | jq

# 5. Следующий polling — передаём total как offset
TOTAL=$(curl -s "$BASE/widget/messages?offset=0" \
  -H "X-Session-Id: $SID" | jq -r .total)

curl -s "$BASE/widget/messages?offset=$TOTAL" \
  -H "X-Session-Id: $SID" | jq

# 6. Скачать файл через прокси (URL берём из поля photo_url / file_url)
curl -s "$BASE/widget/file/AgACAgI...?sid=$SID" -o photo.jpg
```

---

## Polling: правильная реализация

Ключевой момент: `total` из ответа — это общее количество **всех** сообщений (и от пользователя, и от поддержки). Передавать его как `offset` в следующем запросе, чтобы получать только новые.

```javascript
let offset = 0;

async function poll() {
  const res = await fetch(`/widget/messages?offset=${offset}`, {
    headers: { 'X-Session-Id': sessionId },
  });
  const data = await res.json();

  data.messages.forEach(msg => {
    // msg.from === 'user' | 'support'
    renderMessage(msg);
  });

  offset = data.total;   // ← всегда синхронизируем с сервером
}

setInterval(poll, 3000);
```

> **Дубли:** если сообщение пользователя показано локально сразу после отправки, при следующем poll оно вернётся в истории с `"from": "user"`. Фильтруй его на стороне клиента, сравнивая timestamp с локально отправленными сообщениями (погрешность клиент/сервер — до 3 секунд).

---

## Rate limits

| Лимит | Значение |
| --- | --- |
| Сообщений на сессию | 20 / минуту |
| Загрузок файлов на сессию | 10 / минуту |

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `WIDGET_API_HOST` | `0.0.0.0` | Хост HTTP-сервера |
| `WIDGET_API_PORT` | `8080` | Порт HTTP-сервера |
| `WIDGET_CORS_ORIGINS` | _(все)_ | Разрешённые домены через запятую. Пусто = разрешить всем. Пример: `bill.bakasov.kg,app.bakasov.kg` |
| `GET_ID_URL` | — | URL проверки пользователя: `GET {url}?user_id=7` → 200 если существует |
| `GET_DATA_URL` | — | URL данных пользователя: `GET {url}?user_id=7` → `{"full_name": "...", "login": "..."}` |
