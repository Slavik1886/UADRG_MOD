import os
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timedelta
from dateutil import parser
from tabulate import tabulate
from dotenv import load_dotenv

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

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN) 
