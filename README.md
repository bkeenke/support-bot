# Support Bot

[![License](https://img.shields.io/github/license/tonmendon/ton-subdomain)](https://github.com/tonmendon/ton-subdomain/blob/main/LICENSE)
[![Telegram Bot](https://img.shields.io/badge/Bot-grey?logo=telegram)](https://core.telegram.org/bots)
[![Python](https://img.shields.io/badge/Python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Redis](https://img.shields.io/badge/Redis-Yes?logo=redis&color=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-blue?logo=docker&logoColor=white)](https://www.docker.com/)

**Support Bot** is a Telegram bot for customer support. All user messages land in separate forum topics in your group, keeping conversations organized. It supports blocking users, silent mode, and — optionally — a **web widget** that lets website visitors write to support directly from any page without opening Telegram.

**About Limits**:
<blockquote>
Specific limits are not specified in the documentation, but the community has shared some rough numbers.
<br>
• Limit on topic creation per minute <b>~20</b>.
<br>
• Limit on the total number of topics <b>~1M</b>.
</blockquote>

---

## Web Widget

The bot includes a built-in HTTP API and an embeddable JS widget. Visitors on your website can chat with support and receive replies — all messages appear in the same Telegram group as regular bot conversations.

### How it works

1. User opens your site → widget loads from `GET /widget.js`
2. Widget calls `POST /widget/session` with the user's ID from your system
3. First message creates a forum topic in the group: `User 123`
4. Support replies in the topic → widget polls `GET /widget/messages` every 3 seconds
5. Photos and files are proxied through `GET /widget/file/{file_id}` — the bot token is never exposed to the browser

### Embed

```html
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7">
</script>
```

The script tag can be placed anywhere in the page. It injects a floating chat button automatically.

### Attributes

| Attribute | Required | Description |
| --- | --- | --- |
| `data-user-id` | ✓ | User ID in your system (SHM) |
| `data-api` | — | API base URL if different from the script origin |
| `data-lang` | — | Interface language: `ru` (default) or `en` |
| `data-color-primary` | — | Main color — button, header, outgoing bubbles. Default `#2563eb` |
| `data-color-primary-dark` | — | Hover color. Default: auto-darkened by 15% |
| `data-color-primary-light` | — | Icon hover background. Default: auto-tinted |

### Color examples

```html
<!-- Green -->
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7"
        data-color-primary="#16a34a">
</script>

<!-- Purple with custom hover -->
<script src="https://widget.your-domain.com/widget.js"
        data-user-id="7"
        data-color-primary="#7c3aed"
        data-color-primary-dark="#5b21b6">
</script>
```

You can also configure via `window.__SW` before the script loads:

```html
<script>
  window.__SW = { colorPrimary: '#dc2626' };
</script>
<script src="https://widget.your-domain.com/widget.js" data-user-id="7"></script>
```

### nginx setup (required for HTTPS and file uploads)

The bot serves the widget API on port `8080` internally. Use nginx as a reverse proxy so the widget loads over HTTPS.

```nginx
server {
    listen 443 ssl;
    server_name widget.your-domain.com;

    # SSL config here ...

    client_max_body_size 20m;   # allow file uploads up to 10 MB

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Group commands for web sessions

`/information` works in web widget topics and shows:

- SHM User ID
- Name and login (if `GET_DATA_URL` is configured)
- Session creation date
- A button to open the user in SHM admin panel (if `SHM_API_URL` is set)

### Full API reference

See [api.md](api.md) for all endpoints, request/response formats, curl examples, and polling implementation guide.

---

## Bot commands

<details>
<summary><b>Admin commands (DEV_ID, DEV_IDS)</b></summary>

- `/newsletter` — open the newsletter menu. Works in private chats only.

</details>

<details>
<summary><b>Group topic commands</b></summary>

- `/ban` — block or unblock a user
- `/silent` — enable or disable silent mode (messages won't be forwarded to the user)
- `/information` — show user info (works for both Telegram and web widget sessions)

</details>


## Usage

<details>
<summary><b>Preparation</b></summary>

1. Create a bot via [@BotFather](https://t.me/BotFather) and save the token (`BOT_TOKEN`).
2. Create a Telegram group and enable topics in the group settings.
3. Add the bot to the group as an admin with rights to manage topics.
4. Get the group ID via [@my_id_bot](https://t.me/my_id_bot) and save it as `BOT_GROUP_ID`.
5. Optionally configure widget integration — see environment variables below.
6. Optionally customize bot texts in `app/bot/utils/texts.py`.

</details>

<details>
<summary><b>Installation</b></summary>

You need a server with Docker. For hosting options see [Recommended Hosting Provider](#recommended-hosting-provider).

1. Clone the repository:

    ```bash
    git clone https://github.com/bkeenke/support-bot.git
    ```

2. Change into the directory:

    ```bash
    cd support-bot
    ```

3. Copy the environment file:

    ```bash
    cp .env.example .env
    ```

4. Configure environment variables:

    ```bash
    nano .env
    ```

5. Start:

    ```bash
    docker compose up --build -d
    ```

</details>

---

## Environment Variables Reference

<details>
<summary>Click to expand</summary>

### Bot

| Variable | Type | Description | Example |
| --- | --- | --- | --- |
| `BOT_TOKEN` | `str` | Bot token from [@BotFather](https://t.me/BotFather) | `123456:qweRTY` |
| `BOT_DEV_ID` | `int` | Telegram user ID of the developer / admin | `123456789` |
| `BOT_GROUP_ID` | `str` | Group ID where the bot operates | `-100123456789` |
| `BOT_EMOJI_ID` | `str` | Custom emoji ID for forum topic icons | `5417915203100613993` |
| `SHM_API_URL` | `str` | Base URL for the SHM admin panel (user info button) | `https://bill.example.com/index.php?m=clients&action=show` |

### Redis

| Variable | Type | Description | Example |
| --- | --- | --- | --- |
| `REDIS_HOST` | `str` | Redis hostname | `redis` |
| `REDIS_PORT` | `int` | Redis port | `6379` |
| `REDIS_DB` | `int` | Redis database number | `1` |

### Web Widget API

| Variable | Default | Description |
| --- | --- | --- |
| `WIDGET_API_HOST` | `0.0.0.0` | Host for the HTTP server |
| `WIDGET_API_PORT` | `8080` | Port for the HTTP server |
| `WIDGET_CORS_ORIGINS` | _(all)_ | Allowed origins, comma-separated. Empty = allow all. Example: `bill.example.com,app.example.com` |
| `GET_ID_URL` | — | URL to verify a user exists: `GET {url}?user_id=7` → 200 if valid. Session creation is blocked if the user is not found. |
| `GET_DATA_URL` | — | URL to fetch user data: `GET {url}?user_id=7` → `{"full_name": "...", "login": "..."}`. Used to populate the `/information` command. |

</details>

<details>
<summary>List of supporting custom emoji ID's</summary>

`5434144690511290129` - 📰

`5312536423851630001` - 💡

`5312016608254762256` - ⚡️

`5377544228505134960` - 🎙

`5418085807791545980` - 🔝

`5370870893004203704` - 🗣

`5420216386448270341` - 🆒

`5379748062124056162` - ❗️

`5373251851074415873` - 📝

`5433614043006903194` - 📆

`5357315181649076022` - 📁

`5309965701241379366` - 🔎

`5309984423003823246` - 📣

`5312241539987020022` - 🔥

`5312138559556164615` - ❤️

`5377316857231450742` - ❓

`5350305691942788490` - 📈

`5350713563512052787` - 📉

`5309958691854754293` - 💎

`5350452584119279096` - 💰

`5309929258443874898` - 💸

`5377690785674175481` - 🪙

`5310107765874632305` - 💱

`5377438129928020693` - ⁉️

`5309950797704865693` - 🎮

`5350554349074391003` - 💻

`5409357944619802453` - 📱

`5312322066328853156` - 🚗

`5312486108309757006` - 🏠

`5310029292527164639` - 💘

`5310228579009699834` - 🎉

`5377498341074542641` - ‼️

`5312315739842026755` - 🏆

`5408906741125490282` - 🏁

`5368653135101310687` - 🎬

`5310045076531978942` - 🎵

`5420331611830886484` - 🔞

`5350481781306958339` - 📚

`5357107601584693888` - 👑

`5375159220280762629` - ⚽️

`5384327463629233871` - 🏀

`5350513667144163474` - 📺

`5357121491508928442` - 👀

`5357185426392096577` - 🫦

`5310157398516703416` - 🍓

`5310262535021142850` - 💄

`5368741306484925109` - 👠

`5348436127038579546` - ✈️

`5357120306097956843` - 🧳

`5310303848311562896` - 🏖

`5350424168615649565` - ⛅️

`5413625003218313783` - 🦄

`5350699789551935589` - 🛍

`5377478880577724584` - 👜

`5431492767249342908` - 🛒

`5350497316203668441` - 🚂

`5350422527938141909` - 🛥

`5418196338774907917` - 🏔

`5350648297189023928` - 🏕

`5309832892262654231` - 🤖

`5350751634102166060` - 🪩

`5377624166436445368` - 🎟

`5386395194029515402` - 🏴

`5350387571199319521` - 🗳

`5357419403325481346` - 🎓

`5368585403467048206` - 🔭

`5377580546748588396` - 🔬

`5377317729109811382` - 🎶

`5382003830487523366` - 🎤

`5357298525765902091` - 🕺

`5357370526597653193` - 💃

`5357188789351490453` - 🪖

`5348227245599105972` - 💼

`5411138633765757782` - 🧪

`5386435923204382258` - 👨

`5377675010259297233` - 👶

`5386609083400856174` - 🤰

`5368808634392257474` - 💅

`5350548830041415279` - 🏛

`5355127101970194557` - 🧮

`5386379624773066504` - 🖨

`5377494501373780436` - 👮

`5350307998340226571` - 🩺

`5310094636159607472` - 💊

`5310139157790596888` - 💉

`5377468357907849200` - 🧼

`5418115271267197333` - 🪪

`5372819184658949787` - 🛃

`5350344462612570293` - 🍽

`5384574037701696503` - 🐟

`5310039132297242441` - 🎨

`5350658016700013471` - 🎭

`5357504778685392027` - 🎩

`5350367161514732241` - 🔮

`5350520238444126134` - 🍹

`5310132165583840589` - 🎂

`5350392020785437399` - ☕️

`5350406176997646350` - 🍣

`5350403544182694064` - 🍔

`5350444672789519765` - 🍕

`5312424913615723286` - 🦠

`5417915203100613993` - 💬

`5312054580060625569` - 🎄

`5309744892677727325` - 🎃

`5238156910363950406` - ✍️

`5235579393115438657` - ⭐️

`5237699328843200968` - ✅

`5238027455754680851` - 🎖

`5238234236955148254` - 🤡

`5237889595894414384` - 🧠

`5237999392438371490` - 🦮

`5235912661102773458` - 🐈

</details>


## Contribution

Issues and pull requests are welcome.

## License

[MIT License](LICENSE)
