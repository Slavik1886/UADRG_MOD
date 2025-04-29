import os
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timedelta
from dateutil import parser
from tabulate import tabulate
from dotenv import load_dotenv
import asyncio
from typing import Optional, List

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
        super().__init__(command_prefix='/', intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()
        
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        print(f'Slash commands synced to {len(self.guilds)} guild(s)')

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

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN) 
