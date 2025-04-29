# World of Tanks Clan Discord Bot

Discord бот для відстеження статистики клану World of Tanks [UADRG], з фокусом на укріпрайон.

## Функціональність

- Перегляд загальної інформації про клан
- Статистика укріпрайону
- Активність учасників клану в укріпрайоні
- Статистика промресурсу
- Інформація про танки гравців
- Рейтинг клану
- Досягнення гравців
- Історія боїв клану

## Команди

Бот використовує slash-команди Discord:

### Загальні команди
- `/clan_info` - Показати загальну інформацію про клан
- `/clan_rating` - Показати рейтинг клану в грі

### Укріпрайон
- `/stronghold [days=7]` - Показати статистику укріпрайону за вказану кількість днів
- `/members_activity [days=7]` - Показати активність учасників клану в укріпрайоні
- `/clan_battles [count=10]` - Показати останні бої клану
- `/top_players [parameter=battles] [days=7]` - Показати топ гравців клану за вибраним параметром
  - Параметри: battles (бої), wins (перемоги), resources (промресурс)

### Інформація про гравців
- `/player_tanks <nickname>` - Показати інформацію про танки гравця
- `/player_achievements <nickname>` - Показати досягнення гравця

## Налаштування

1. Створіть Discord бота на [Discord Developer Portal](https://discord.com/developers/applications)
   - В налаштуваннях бота увімкніть опцію "MESSAGE CONTENT INTENT"
   - В розділі "OAuth2 > URL Generator" виберіть наступні дозволи:
     - `applications.commands`
     - `bot`
2. Отримайте API ключ Wargaming на [Wargaming Developer Portal](https://developers.wargaming.net/)
3. Скопіюйте `.env.example` в `.env` та заповніть необхідні значення:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   WARGAMING_API_KEY=your_wargaming_api_key_here
   ```

## Встановлення

1. Клонуйте репозиторій
2. Встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```
3. Запустіть бота:
   ```bash
   python bot.py
   ```

## Розгортання на Railway

1. Створіть новий проект на [Railway](https://railway.app/)
2. Підключіть ваш GitHub репозиторій
3. Додайте змінні середовища (`DISCORD_TOKEN` та `WARGAMING_API_KEY`) в налаштуваннях проекту
4. Railway автоматично розгорне ваш бот

## Ліцензія

MIT 
