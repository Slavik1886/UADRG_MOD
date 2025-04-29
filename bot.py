import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
from datetime import datetime, timedelta
from dateutil import parser
from tabulate import tabulate
from dotenv import load_dotenv
import asyncio
from typing import Optional, List, Dict
from collections import defaultdict
import json
import random
import pytz

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
WARGAMING_API_KEY = os.getenv('WARGAMING_API_KEY')
CLAN_ID = "500310423"  # UADRG clan ID

# API endpoints
WG_API_BASE = "https://api.worldoftanks.eu/wot"

# Bot setup
class WoTClanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Add this for member-related commands
        intents.guilds = True   # Add this for guild-related commands
        intents.voice_states = True
        intents.invites = True
        super().__init__(command_prefix='/', intents=intents)
        
    async def setup_hook(self):
        print("Syncing commands...")
        try:
            await self.tree.sync()
            print("Commands synced successfully!")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
        
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        print(f'Slash commands synced to {len(self.guilds)} guild(s)')
        print(f'Bot invite link: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands')

class WargamingAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.session = None

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def make_request(self, endpoint, params=None):
        if params is None:
            params = {}
        params['application_id'] = self.api_key
        
        session = await self.get_session()
        async with session.get(f"{WG_API_BASE}/{endpoint}/", params=params) as response:
            return await response.json()

bot = WoTClanBot()
wg_api = WargamingAPI(WARGAMING_API_KEY)

# Системи відстеження
voice_time_tracker = {}
tracked_channels = {}
warning_sent = set()
voice_activity = defaultdict(timedelta)
last_activity_update = datetime.utcnow()

# Система ролей за запрошеннями
invite_roles = {}
invite_cache = {}

# Система привітальних повідомлень
welcome_messages = {}

# Система сповіщень
notification_channels = {}

# Система мутів
muted_users = {}
mute_roles = {}

def load_notification_data():
    try:
        with open('notification_channels.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_notification_data():
    with open('notification_channels.json', 'w') as f:
        json.dump(notification_channels, f)

def load_mute_data():
    try:
        with open('mute_data.json', 'r') as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}  # Конвертуємо ключі в int
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_mute_data():
    # Конвертуємо ключі в str для JSON серіалізації
    data = {str(k): v for k, v in muted_users.items()}
    with open('mute_data.json', 'w') as f:
        json.dump(data, f)

@bot.tree.command(name="clan_info", description="Показати загальну інформацію про клан")
async def clan_info(interaction: discord.Interaction):
    """Display basic clan information"""
    await interaction.response.defer()
    
    try:
        data = await wg_api.make_request('clans/info', {'clan_id': CLAN_ID})
        
        if data['status'] == 'ok' and CLAN_ID in data['data']:
            clan = data['data'][CLAN_ID]
            
            embed = discord.Embed(
                title=f"[{clan['tag']}] {clan['name']}",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Motto", value=clan['motto'] or "Не встановлено", inline=False)
            embed.add_field(name="Members", value=str(clan['members_count']), inline=True)
            embed.add_field(name="Created", value=datetime.fromtimestamp(clan['created_at']).strftime('%Y-%m-%d'), inline=True)
            
            if clan['emblems']:
                embed.set_thumbnail(url=clan['emblems']['x195']['portal'])
                
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Не вдалося отримати інформацію про клан.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="stronghold", description="Показати статистику укріпрайону")
@app_commands.describe(days="Кількість днів для аналізу (за замовчуванням 7)")
async def stronghold_stats(interaction: discord.Interaction, days: int = 7):
    """Display stronghold statistics for the specified number of days"""
    await interaction.response.defer()
    
    try:
        data = await wg_api.make_request('stronghold/statistics', {
            'clan_id': CLAN_ID,
            'period': 'day' if days <= 7 else 'month'
        })
        
        if data['status'] == 'ok' and CLAN_ID in data['data']:
            stats = data['data'][CLAN_ID]
            
            embed = discord.Embed(
                title=f"Статистика укріпрайону за {days} днів",
                color=discord.Color.green()
            )
            
            # Battles statistics
            total_battles = stats.get('total_battles_count', 0)
            wins = stats.get('wins', 0)
            win_rate = (wins / total_battles * 100) if total_battles > 0 else 0
            
            embed.add_field(
                name="Загальна статистика",
                value=f"Всього боїв: {total_battles}\n"
                      f"Перемог: {wins}\n"
                      f"Відсоток перемог: {win_rate:.2f}%",
                inline=False
            )
            
            # Resources statistics
            embed.add_field(
                name="Ресурси",
                value=f"Промресурс: {stats.get('industrial_resource', 0)}\n"
                      f"Заброньовано: {stats.get('reserved_industrial_resource', 0)}",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Не вдалося отримати статистику укріпрайону.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="members_activity", description="Показати активність учасників клану в укріпрайоні")
@app_commands.describe(days="Кількість днів для аналізу (за замовчуванням 7)")
async def members_activity(interaction: discord.Interaction, days: int = 7):
    """Display clan members activity in stronghold"""
    await interaction.response.defer()
    
    try:
        # Get members list
        members_data = await wg_api.make_request('clans/info', {
            'clan_id': CLAN_ID,
            'fields': 'members'
        })
        
        if members_data['status'] == 'ok' and CLAN_ID in members_data['data']:
            members = members_data['data'][CLAN_ID]['members']
            
            # Get stronghold statistics for each member
            member_stats = []
            for member in members:
                account_id = member['account_id']
                
                # Get player's stronghold statistics
                player_stats = await wg_api.make_request('stronghold/accountstats', {
                    'account_id': account_id
                })
                
                if player_stats['status'] == 'ok' and str(account_id) in player_stats['data']:
                    stats = player_stats['data'][str(account_id)]
                    
                    member_stats.append({
                        'nickname': member['account_name'],
                        'battles': stats.get('battles_count', 0),
                        'wins': stats.get('wins', 0),
                        'resources': stats.get('industrial_resource_earned', 0)
                    })
            
            # Sort by battles count
            member_stats.sort(key=lambda x: x['battles'], reverse=True)
            
            # Create table
            table = tabulate(
                [[s['nickname'], s['battles'], s['wins'], s['resources']] for s in member_stats],
                headers=['Гравець', 'Боїв', 'Перемог', 'Промресурс'],
                tablefmt='grid'
            )
            
            # Split message if it's too long
            for chunk in [table[i:i+1900] for i in range(0, len(table), 1900)]:
                await interaction.followup.send(f"```\n{chunk}\n```")
        else:
            await interaction.followup.send("Не вдалося отримати інформацію про учасників клану.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="player_tanks", description="Показати інформацію про танки гравця")
@app_commands.describe(nickname="Нікнейм гравця")
async def player_tanks(interaction: discord.Interaction, nickname: str):
    """Display player's tanks information"""
    await interaction.response.defer()
    
    try:
        # Get account ID
        account_data = await wg_api.make_request('account/list', {'search': nickname, 'limit': 1})
        
        if account_data['status'] == 'ok' and account_data['data']:
            account_id = account_data['data'][0]['account_id']
            
            # Get player's tanks
            tanks_data = await wg_api.make_request('account/tanks', {
                'account_id': account_id,
                'fields': 'tank_id,statistics.battles,statistics.wins'
            })
            
            if tanks_data['status'] == 'ok' and str(account_id) in tanks_data['data']:
                tanks = tanks_data['data'][str(account_id)]
                
                # Get tank names
                tank_ids = [str(tank['tank_id']) for tank in tanks]
                vehicles_data = await wg_api.make_request('encyclopedia/vehicles', {
                    'tank_id': ','.join(tank_ids)
                })
                
                if vehicles_data['status'] == 'ok':
                    tank_stats = []
                    for tank in tanks:
                        tank_id = str(tank['tank_id'])
                        if tank_id in vehicles_data['data']:
                            vehicle = vehicles_data['data'][tank_id]
                            battles = tank['statistics']['battles']
                            wins = tank['statistics']['wins']
                            win_rate = (wins / battles * 100) if battles > 0 else 0
                            
                            tank_stats.append({
                                'name': vehicle['name'],
                                'tier': vehicle['tier'],
                                'type': vehicle['type'],
                                'battles': battles,
                                'win_rate': win_rate
                            })
                    
                    # Sort by battles
                    tank_stats.sort(key=lambda x: x['battles'], reverse=True)
                    
                    # Create embed pages (10 tanks per page)
                    tanks_per_page = 10
                    pages = []
                    
                    for i in range(0, len(tank_stats), tanks_per_page):
                        page_tanks = tank_stats[i:i + tanks_per_page]
                        embed = discord.Embed(
                            title=f"Танки гравця {nickname}",
                            description=f"Сторінка {len(pages) + 1}",
                            color=discord.Color.blue()
                        )
                        
                        for tank in page_tanks:
                            embed.add_field(
                                name=f"{tank['name']} (Рівень {tank['tier']})",
                                value=f"Тип: {tank['type']}\n"
                                      f"Боїв: {tank['battles']}\n"
                                      f"Відсоток перемог: {tank['win_rate']:.2f}%",
                                inline=False
                            )
                        
                        pages.append(embed)
                    
                    # Send first page
                    current_page = 0
                    message = await interaction.followup.send(embed=pages[current_page])
                    
                    # Add navigation reactions
                    if len(pages) > 1:
                        await message.add_reaction("◀️")
                        await message.add_reaction("▶️")
                        
                        def check(reaction, user):
                            return user == interaction.user and str(reaction.emoji) in ["◀️", "▶️"]
                        
                        while True:
                            try:
                                reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
                                
                                if str(reaction.emoji) == "▶️" and current_page < len(pages) - 1:
                                    current_page += 1
                                    await message.edit(embed=pages[current_page])
                                elif str(reaction.emoji) == "◀️" and current_page > 0:
                                    current_page -= 1
                                    await message.edit(embed=pages[current_page])
                                
                                await message.remove_reaction(reaction, user)
                            except asyncio.TimeoutError:
                                await message.clear_reactions()
                                break
                else:
                    await interaction.followup.send("Не вдалося отримати інформацію про танки.")
            else:
                await interaction.followup.send("Не вдалося отримати статистику гравця.")
        else:
            await interaction.followup.send("Гравця не знайдено.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="clan_battles", description="Показати останні бої клану")
@app_commands.describe(count="Кількість боїв для показу (за замовчуванням 10)")
async def clan_battles(interaction: discord.Interaction, count: int = 10):
    """Display recent clan battles"""
    await interaction.response.defer()
    
    try:
        data = await wg_api.make_request('stronghold/battles', {
            'clan_id': CLAN_ID,
            'limit': count
        })
        
        if data['status'] == 'ok' and CLAN_ID in data['data']:
            battles = data['data'][CLAN_ID]
            
            embed = discord.Embed(
                title=f"Останні {count} боїв клану",
                color=discord.Color.green()
            )
            
            for battle in battles:
                result = "Перемога" if battle['result'] == 'victory' else "Поразка"
                battle_time = datetime.fromtimestamp(battle['time']).strftime('%Y-%m-%d %H:%M')
                
                embed.add_field(
                    name=f"Бій {battle_time}",
                    value=f"Результат: {result}\n"
                          f"Тип: {battle['type']}\n"
                          f"Рівень: {battle['level']}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Не вдалося отримати інформацію про бої.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="top_players", description="Показати топ гравців клану за вибраним параметром")
@app_commands.describe(
    parameter="Параметр для сортування (battles/wins/resources)",
    days="Кількість днів для аналізу (за замовчуванням 7)"
)
async def top_players(
    interaction: discord.Interaction,
    parameter: str = "battles",
    days: int = 7
):
    """Display top clan players by selected parameter"""
    await interaction.response.defer()
    
    try:
        # Get members list
        members_data = await wg_api.make_request('clans/info', {
            'clan_id': CLAN_ID,
            'fields': 'members'
        })
        
        if members_data['status'] == 'ok' and CLAN_ID in members_data['data']:
            members = members_data['data'][CLAN_ID]['members']
            
            # Get stronghold statistics for each member
            member_stats = []
            for member in members:
                account_id = member['account_id']
                
                # Get player's stronghold statistics
                player_stats = await wg_api.make_request('stronghold/accountstats', {
                    'account_id': account_id
                })
                
                if player_stats['status'] == 'ok' and str(account_id) in player_stats['data']:
                    stats = player_stats['data'][str(account_id)]
                    
                    member_stats.append({
                        'nickname': member['account_name'],
                        'battles': stats.get('battles_count', 0),
                        'wins': stats.get('wins', 0),
                        'resources': stats.get('industrial_resource_earned', 0)
                    })
            
            # Sort by selected parameter
            if parameter in ['battles', 'wins', 'resources']:
                member_stats.sort(key=lambda x: x[parameter], reverse=True)
                
                # Create embed
                embed = discord.Embed(
                    title=f"Топ 10 гравців за {parameter}",
                    color=discord.Color.gold()
                )
                
                for i, player in enumerate(member_stats[:10], 1):
                    embed.add_field(
                        name=f"{i}. {player['nickname']}",
                        value=f"Значення: {player[parameter]}",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Невірний параметр. Використовуйте: battles, wins або resources")
        else:
            await interaction.followup.send("Не вдалося отримати інформацію про учасників клану.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="clan_rating", description="Показати рейтинг клану")
async def clan_rating(interaction: discord.Interaction):
    """Display clan rating information"""
    await interaction.response.defer()
    
    try:
        data = await wg_api.make_request('clanratings/clans', {
            'clan_id': CLAN_ID
        })
        
        if data['status'] == 'ok' and CLAN_ID in data['data']:
            ratings = data['data'][CLAN_ID]
            
            embed = discord.Embed(
                title="Рейтинг клану",
                color=discord.Color.blue()
            )
            
            for category, rating in ratings.items():
                if isinstance(rating, dict) and 'value' in rating:
                    embed.add_field(
                        name=category,
                        value=f"Значення: {rating['value']}\n"
                              f"Ранг: {rating.get('rank', 'N/A')}",
                        inline=True
                    )
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Не вдалося отримати інформацію про рейтинг клану.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@bot.tree.command(name="player_achievements", description="Показати досягнення гравця")
@app_commands.describe(nickname="Нікнейм гравця")
async def player_achievements(interaction: discord.Interaction, nickname: str):
    """Display player's achievements"""
    await interaction.response.defer()
    
    try:
        # Get account ID
        account_data = await wg_api.make_request('account/list', {'search': nickname, 'limit': 1})
        
        if account_data['status'] == 'ok' and account_data['data']:
            account_id = account_data['data'][0]['account_id']
            
            # Get achievements
            achievements_data = await wg_api.make_request('account/achievements', {
                'account_id': account_id
            })
            
            if achievements_data['status'] == 'ok' and str(account_id) in achievements_data['data']:
                achievements = achievements_data['data'][str(account_id)]
                
                # Get achievement descriptions
                descriptions = await wg_api.make_request('encyclopedia/achievements', {})
                
                if descriptions['status'] == 'ok':
                    embed = discord.Embed(
                        title=f"Досягнення гравця {nickname}",
                        color=discord.Color.purple()
                    )
                    
                    for achievement, count in achievements.items():
                        if achievement in descriptions['data']:
                            desc = descriptions['data'][achievement]
                            embed.add_field(
                                name=f"{desc['name']} (x{count})",
                                value=desc['description'][:1024],
                                inline=False
                            )
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("Не вдалося отримати опис досягнень.")
            else:
                await interaction.followup.send("Не вдалося отримати інформацію про досягнення.")
        else:
            await interaction.followup.send("Гравця не знайдено.")
    except Exception as e:
        await interaction.followup.send(f"Помилка: {str(e)}")

@tasks.loop(minutes=1)
async def check_mutes():
    current_time = datetime.utcnow()
    to_unmute = []
    
    for guild_id, muted_dict in muted_users.items():
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
            
        for user_id, mute_data in muted_dict.items():
            unmute_time = datetime.fromisoformat(mute_data['unmute_time'])
            if current_time >= unmute_time:
                member = guild.get_member(user_id)
                if member:
                    mute_role = guild.get_role(mute_data['role_id'])
                    if mute_role:
                        try:
                            await member.remove_roles(mute_role)
                            log_channel = guild.get_channel(mute_data['log_channel'])
                            if log_channel:
                                embed = discord.Embed(
                                    title="🔊 Користувача розмучено",
                                    description=f"Користувач {member.mention} автоматично розмучений",
                                    color=discord.Color.green()
                                )
                                await log_channel.send(embed=embed)
                        except discord.Forbidden:
                            print(f"Не вдалося зняти мут з користувача {member.id} на сервері {guild.id}")
                to_unmute.append((guild_id, user_id))
    
    # Видаляємо розмучених користувачів
    for guild_id, user_id in to_unmute:
        if guild_id in muted_users:
            muted_users[guild_id].pop(user_id, None)
            if not muted_users[guild_id]:  # Якщо словник пустий
                muted_users.pop(guild_id)
    
    if to_unmute:
        save_mute_data()

async def update_invite_cache(guild):
    """Оновлюємо кеш запрошень для сервера"""
    try:
        invites = await guild.invites()
        invite_cache[guild.id] = {invite.code: invite.uses for invite in invites}
    except discord.Forbidden:
        print(f"Немає дозволу на перегляд запрошень для сервера {guild.name}")
    except Exception as e:
        print(f"Помилка оновлення кешу запрошень: {e}")

@bot.event
async def on_ready():
    print(f'Бот {bot.user} онлайн!')
    
    # Встановлюємо київський час для логування
    kyiv_tz = pytz.timezone('Europe/Kiev')
    now = datetime.now(kyiv_tz)
    print(f"Поточний час (Київ): {now}")
    
    for guild in bot.guilds:
        await update_invite_cache(guild)
    
    try:
        synced = await bot.tree.sync()
        print(f"Синхронізовано {len(synced)} команд")
    except Exception as e:
        print(f"Помилка синхронізації: {e}")
    
    check_voice_activity.start()
    update_voice_activity.start()
    check_mutes.start()  # Додаємо перевірку мутів

@bot.tree.command(name="mute", description="Тимчасово заблокувати користувача")
@app_commands.describe(
    member="Користувач для блокування",
    duration="Тривалість (приклад: 1h, 30m, 1d)",
    reason="Причина блокування",
    log_channel="Канал для логування (необов'язково)"
)
async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    duration: str,
    reason: str,
    log_channel: Optional[discord.TextChannel] = None
):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("❌ У вас немає прав на це", ephemeral=True)
    
    # Перевірка чи є роль для мута
    mute_role = None
    if interaction.guild.id in mute_roles:
        mute_role = interaction.guild.get_role(mute_roles[interaction.guild.id])
    
    if not mute_role:
        # Створюємо нову роль для мута
        try:
            mute_role = await interaction.guild.create_role(
                name="Muted",
                reason="Роль для мута користувачів"
            )
            
            # Налаштовуємо дозволи для всіх текстових каналів
            for channel in interaction.guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    await channel.set_permissions(mute_role,
                                               send_messages=False,
                                               speak=False,
                                               stream=False)
            
            mute_roles[interaction.guild.id] = mute_role.id
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Не вдалося створити роль для мута",
                ephemeral=True
            )
    
    # Парсимо тривалість
    duration_seconds = 0
    try:
        unit = duration[-1].lower()
        value = int(duration[:-1])
        
        if unit == 'm':
            duration_seconds = value * 60
        elif unit == 'h':
            duration_seconds = value * 3600
        elif unit == 'd':
            duration_seconds = value * 86400
        else:
            return await interaction.response.send_message(
                "❌ Невірний формат тривалості. Використовуйте: 30m, 1h, 1d",
                ephemeral=True
            )
    except ValueError:
        return await interaction.response.send_message(
            "❌ Невірний формат тривалості",
            ephemeral=True
        )
    
    unmute_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
    
    # Додаємо роль
    try:
        await member.add_roles(mute_role, reason=reason)
        
        # Зберігаємо інформацію про мут
        if interaction.guild.id not in muted_users:
            muted_users[interaction.guild.id] = {}
        
        muted_users[interaction.guild.id][member.id] = {
            'unmute_time': unmute_time.isoformat(),
            'role_id': mute_role.id,
            'reason': reason,
            'log_channel': log_channel.id if log_channel else None
        }
        save_mute_data()
        
        # Створюємо ембед
        embed = discord.Embed(
            title="🔇 Користувача заблоковано",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Користувач", value=member.mention, inline=True)
        embed.add_field(name="Модератор", value=interaction.user.mention, inline=True)
        embed.add_field(name="Тривалість", value=duration, inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Буде розблоковано", value=f"<t:{int(unmute_time.timestamp())}:F>", inline=False)
        
        # Надсилаємо повідомлення
        await interaction.response.send_message(embed=embed)
        if log_channel:
            await log_channel.send(embed=embed)
        
        # Надсилаємо приватне повідомлення користувачу
        try:
            await member.send(f"Вас заблоковано на сервері {interaction.guild.name}\n"
                            f"Причина: {reason}\n"
                            f"Тривалість: {duration}\n"
                            f"Буде знято: <t:{int(unmute_time.timestamp())}:F>")
        except:
            pass
            
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Не вдалося заблокувати користувача",
            ephemeral=True
        )

@bot.tree.command(name="unmute", description="Розблокувати користувача")
@app_commands.describe(
    member="Користувач для розблокування",
    reason="Причина розблокування"
)
async def unmute(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str
):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("❌ У вас немає прав на це", ephemeral=True)
    
    guild_mutes = muted_users.get(interaction.guild.id, {})
    if member.id not in guild_mutes:
        return await interaction.response.send_message(
            "❌ Цей користувач не заблокований",
            ephemeral=True
        )
    
    mute_data = guild_mutes[member.id]
    mute_role = interaction.guild.get_role(mute_data['role_id'])
    
    if mute_role and mute_role in member.roles:
        try:
            await member.remove_roles(mute_role, reason=reason)
            
            # Видаляємо з бази мутів
            guild_mutes.pop(member.id)
            if not guild_mutes:
                muted_users.pop(interaction.guild.id)
            save_mute_data()
            
            # Створюємо ембед
            embed = discord.Embed(
                title="🔊 Користувача розблоковано",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="Користувач", value=member.mention, inline=True)
            embed.add_field(name="Модератор", value=interaction.user.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            
            # Надсилаємо повідомлення
            await interaction.response.send_message(embed=embed)
            
            # Якщо є канал для логів
            if 'log_channel' in mute_data and mute_data['log_channel']:
                log_channel = interaction.guild.get_channel(mute_data['log_channel'])
                if log_channel:
                    await log_channel.send(embed=embed)
            
            # Надсилаємо приватне повідомлення користувачу
            try:
                await member.send(f"Вас розблоковано на сервері {interaction.guild.name}\n"
                                f"Причина: {reason}")
            except:
                pass
                
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Не вдалося розблокувати користувача",
                ephemeral=True
            )
    else:
        await interaction.response.send_message(
            "❌ Не вдалося знайти роль для мута",
            ephemeral=True
        )

@bot.tree.command(name="notification", description="Налаштувати автоматичні сповіщення для каналу")
@app_commands.describe(
    channel="Канал для відстеження",
    roles="Ролі для згадування (розділіть комами)",
    enabled="Увімкнути чи вимкнути сповіщення"
)
async def notification(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    roles: str,
    enabled: bool = True
):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ У вас немає прав на це", ephemeral=True)
    
    # Перевіряємо та обробляємо ролі
    role_ids = []
    invalid_roles = []
    for role_name in [r.strip() for r in roles.split(',')]:
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            role_ids.append(role.id)
        else:
            invalid_roles.append(role_name)
    
    if invalid_roles:
        return await interaction.response.send_message(
            f"❌ Не знайдено такі ролі: {', '.join(invalid_roles)}",
            ephemeral=True
        )
    
    if enabled:
        notification_channels[str(channel.id)] = {
            'guild_id': interaction.guild.id,
            'roles': role_ids
        }
        save_notification_data()
        
        roles_mention = ', '.join([f'<@&{role_id}>' for role_id in role_ids])
        await interaction.response.send_message(
            f"✅ Налаштовано сповіщення для каналу {channel.mention}\n"
            f"Ролі для згадування: {roles_mention}",
            ephemeral=True
        )
    else:
        if str(channel.id) in notification_channels:
            del notification_channels[str(channel.id)]
            save_notification_data()
            await interaction.response.send_message(
                f"✅ Сповіщення для каналу {channel.mention} вимкнено",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Для каналу {channel.mention} не налаштовано сповіщення",
                ephemeral=True
            )

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Перевіряємо чи канал у списку для сповіщень
    if str(message.channel.id) in notification_channels:
        data = notification_channels[str(message.channel.id)]
        
        # Перевіряємо чи повідомлення з того ж серверу
        if message.guild.id == data['guild_id']:
            roles_mention = ' '.join([f'<@&{role_id}>' for role_id in data['roles']])
            
            # Надсилаємо згадування ролей
            try:
                notification_msg = await message.channel.send(roles_mention)
                # Видаляємо згадування через 1 секунду
                await asyncio.sleep(1)
                await notification_msg.delete()
            except discord.Forbidden:
                print(f"Не вдалося надіслати сповіщення в канал {message.channel.id}")
    
    await bot.process_commands(message)

@bot.tree.command(name="clean", description="Очистити повідомлення в каналі")
@app_commands.describe(
    amount="Кількість повідомлень для видалення (за замовчуванням всі)",
    user="Користувач, чиї повідомлення потрібно видалити (необов'язково)",
    reason="Причина видалення (необов'язково)"
)
async def clean(
    interaction: discord.Interaction,
    amount: Optional[int] = None,
    user: Optional[discord.Member] = None,
    reason: Optional[str] = "Очищення каналу"
):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ У вас немає прав на це", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        def check_message(message):
            if user:
                return message.author == user
            return True
        
        # Якщо amount не вказано, видаляємо всі повідомлення
        if not amount:
            # Створюємо новий канал з тими ж налаштуваннями
            new_channel = await interaction.channel.clone(
                reason=f"Очищення каналу: {reason}"
            )
            await new_channel.edit(position=interaction.channel.position)
            await interaction.channel.delete()
            
            await new_channel.send(
                embed=discord.Embed(
                    title="🧹 Канал очищено",
                    description=f"**Модератор:** {interaction.user.mention}\n"
                              f"**Причина:** {reason}",
                    color=discord.Color.green()
                )
            )
            
            await interaction.followup.send(
                f"✅ Канал повністю очищено",
                ephemeral=True
            )
            return
        
        # Видаляємо вказану кількість повідомлень
        deleted = await interaction.channel.purge(
            limit=amount,
            check=check_message,
            reason=reason
        )
        
        # Створюємо ембед з результатами
        embed = discord.Embed(
            title="🧹 Повідомлення видалено",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Кількість видалених повідомлень",
            value=str(len(deleted)),
            inline=True
        )
        
        embed.add_field(
            name="Модератор",
            value=interaction.user.mention,
            inline=True
        )
        
        if user:
            embed.add_field(
                name="Користувач",
                value=user.mention,
                inline=True
            )
        
        if reason:
            embed.add_field(
                name="Причина",
                value=reason,
                inline=False
            )
        
        # Надсилаємо повідомлення про результат
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Надсилаємо повідомлення в канал, яке видалиться через 5 секунд
        msg = await interaction.channel.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
            
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ У бота немає прав на видалення повідомлень",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Помилка: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="dis_stat", description="Показати статистику активності користувачів")
@app_commands.describe(
    type="Тип статистики",
    limit="Кількість користувачів для показу (за замовчуванням 10)"
)
@app_commands.choices(type=[
    app_commands.Choice(name="🟢 Найактивніші", value="active"),
    app_commands.Choice(name="🔴 Найменш активні", value="inactive")
])
async def dis_stat(
    interaction: discord.Interaction,
    type: app_commands.Choice[str],
    limit: Optional[int] = 10
):
    await interaction.response.defer()
    
    # Збираємо статистику
    member_stats = []
    for member in interaction.guild.members:
        if member.bot:
            continue
            
        # Базова активність (час у голосових каналах)
        voice_time = voice_activity.get(member.id, timedelta())
        
        # Додаткові фактори активності
        joined_days = (datetime.utcnow() - member.joined_at.replace(tzinfo=None)).days if member.joined_at else 0
        roles_count = len(member.roles) - 1  # Віднімаємо @everyone
        
        # Розраховуємо загальний скор активності
        activity_score = (
            voice_time.total_seconds() / 3600  # Години в голосових каналах
            + roles_count * 5  # Бонус за кожну роль
            - joined_days * 0.1  # Невеликий мінус за кожен день з приєднання
        )
        
        member_stats.append({
            'member': member,
            'voice_time': voice_time,
            'joined_days': joined_days,
            'roles_count': roles_count,
            'activity_score': activity_score
        })
    
    # Сортуємо за активністю
    member_stats.sort(
        key=lambda x: x['activity_score'],
        reverse=(type.value == "active")
    )
    
    # Обмежуємо кількість
    member_stats = member_stats[:limit]
    
    # Створюємо ембед
    embed = discord.Embed(
        title="📊 Статистика активності користувачів",
        description=f"{'Найактивніші' if type.value == 'active' else 'Найменш активні'} користувачі серверу",
        color=discord.Color.green() if type.value == "active" else discord.Color.red(),
        timestamp=datetime.utcnow()
    )
    
    # Додаємо поля для кожного користувача
    for i, stat in enumerate(member_stats, 1):
        member = stat['member']
        voice_hours = stat['voice_time'].total_seconds() / 3600
        
        embed.add_field(
            name=f"{i}. {member.display_name}",
            value=f"👥 Ролей: {stat['roles_count']}\n"
                  f"🎤 Годин у голосових: {voice_hours:.1f}\n"
                  f"📅 Днів на сервері: {stat['joined_days']}\n"
                  f"📊 Скор активності: {stat['activity_score']:.1f}",
            inline=False
        )
    
    # Додаємо загальну інформацію
    total_members = len([m for m in interaction.guild.members if not m.bot])
    embed.set_footer(text=f"Всього учасників: {total_members}")
    
    await interaction.followup.send(embed=embed)

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN) 
