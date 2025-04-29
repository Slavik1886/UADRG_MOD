import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict
import json
import random
import aiohttp
from typing import Optional, List, Union, Dict
import pytz
import logging
from pathlib import Path
import yaml
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('EnhancedBot')

class EnhancedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.message_content = True
        intents.voice_states = True
        intents.invites = True
        intents.presences = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.guild_typing = True
        intents.dm_messages = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        # Data storage
        self.config = {}
        self.voice_time_tracker = {}
        self.tracked_channels = {}
        self.warning_sent = set()
        self.voice_activity = defaultdict(timedelta)
        self.last_activity_update = datetime.utcnow()
        self.invite_roles = {}
        self.invite_cache = {}
        self.welcome_messages = {}
        self.temp_channels = {}
        self.auto_roles = {}
        self.muted_users = {}
        self.server_stats = defaultdict(dict)
        
        # Load configurations
        self.load_config()
        
        # Start background tasks
        self.start_tasks()
    
    def load_config(self):
        """Load bot configuration from YAML file"""
        try:
            with open('config.yml', 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("Config file not found, using defaults")
            self.config = {
                'default_prefix': '!',
                'log_channel': None,
                'mod_role': None,
                'admin_role': None,
                'mute_role': None,
                'welcome_channel': None,
                'auto_roles': [],
                'blocked_words': [],
                'max_mentions': 5,
                'max_lines': 10,
                'temp_channels_category': None
            }
            self.save_config()
    
    def save_config(self):
        """Save bot configuration to YAML file"""
        with open('config.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)
    
    def start_tasks(self):
        """Start all background tasks"""
        self.check_voice_activity.start()
        self.update_voice_activity.start()
        self.update_server_stats.start()
        self.check_temp_mutes.start()
        self.backup_data.start()
    
    @tasks.loop(minutes=1)
    async def check_voice_activity(self):
        """Monitor voice channel activity"""
        current_time = datetime.utcnow()
        for guild_id, data in self.tracked_channels.items():
            guild = self.get_guild(guild_id)
            if not guild:
                continue
            
            voice_channel = guild.get_channel(data["voice_channel"])
            log_channel = guild.get_channel(data["log_channel"])
            if not voice_channel or not log_channel:
                continue
            
            for member in voice_channel.members:
                if member.bot:
                    continue
                
                member_key = f"{guild_id}_{member.id}"
                if member_key not in self.voice_time_tracker:
                    self.voice_time_tracker[member_key] = current_time
                    self.warning_sent.discard(member_key)
                    continue
                
                time_in_channel = current_time - self.voice_time_tracker[member_key]
                await self.handle_inactive_member(member, member_key, time_in_channel, log_channel, data)
    
    async def handle_inactive_member(self, member, member_key, time_in_channel, log_channel, data):
        """Handle inactive members in voice channels"""
        if time_in_channel > timedelta(minutes=10) and member_key not in self.warning_sent:
            try:
                await member.send("⚠️ Ви в каналі для неактивних користувачів вже 10+ хвилин. ✅ Будьте активні, або Ви будете відєднані!")
                self.warning_sent.add(member_key)
            except:
                pass
        
        if time_in_channel > timedelta(minutes=15):
            try:
                await member.move_to(None)
                embed = discord.Embed(
                    title="🔴 Відключення за неактивність",
                    description=f"{member.mention} було відключено через неактивність",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                msg = await log_channel.send(embed=embed)
                self.loop.create_task(self.delete_after(msg, data["delete_after"]))
                del self.voice_time_tracker[member_key]
                self.warning_sent.discard(member_key)
            except:
                pass
    
    @tasks.loop(minutes=1)
    async def update_voice_activity(self):
        """Update voice activity tracking"""
        now = datetime.utcnow()
        time_elapsed = now - self.last_activity_update
        self.last_activity_update = now
        
        for guild in self.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot:
                        self.voice_activity[member.id] += time_elapsed
    
    @tasks.loop(minutes=5)
    async def update_server_stats(self):
        """Update server statistics"""
        for guild in self.guilds:
            stats = {
                'total_members': len(guild.members),
                'online_members': len([m for m in guild.members if m.status != discord.Status.offline]),
                'total_channels': len(guild.channels),
                'total_roles': len(guild.roles),
                'voice_channels': len(guild.voice_channels),
                'text_channels': len(guild.text_channels),
                'boost_level': guild.premium_tier,
                'boost_count': guild.premium_subscription_count
            }
            self.server_stats[guild.id].update(stats)
    
    @tasks.loop(minutes=30)
    async def backup_data(self):
        """Backup bot data periodically"""
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_data = {
            'config': self.config,
            'invite_roles': self.invite_roles,
            'welcome_messages': self.welcome_messages,
            'auto_roles': self.auto_roles,
            'server_stats': dict(self.server_stats)
        }
        
        backup_file = backup_dir / f'backup_{timestamp}.json'
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=4)
        
        # Keep only last 5 backups
        backups = sorted(backup_dir.glob('backup_*.json'))
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                old_backup.unlink()
    
    @tasks.loop(minutes=1)
    async def check_temp_mutes(self):
        """Check and remove temporary mutes"""
        current_time = datetime.utcnow()
        to_unmute = []
        
        for user_id, mute_data in self.muted_users.items():
            if current_time >= mute_data['end_time']:
                to_unmute.append((user_id, mute_data['guild_id']))
        
        for user_id, guild_id in to_unmute:
            await self.unmute_member(user_id, guild_id)
    
    async def unmute_member(self, user_id: int, guild_id: int):
        """Remove mute from a member"""
        guild = self.get_guild(guild_id)
        if not guild:
            return
        
        member = guild.get_member(user_id)
        if not member:
            return
        
        mute_role = guild.get_role(self.config.get('mute_role'))
        if not mute_role:
            return
        
        try:
            await member.remove_roles(mute_role, reason="Тимчасове обмеження закінчилось")
            del self.muted_users[user_id]
            
            # Log unmute
            log_channel = guild.get_channel(self.config.get('log_channel'))
            if log_channel:
                embed = discord.Embed(
                    title="🔊 Обмеження знято",
                    description=f"З користувача {member.mention} знято обмеження чату",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                await log_channel.send(embed=embed)
        except:
            logger.error(f"Failed to unmute {member.id} in {guild.id}", exc_info=True)
    
    async def delete_after(self, message, minutes):
        """Delete a message after specified minutes"""
        if minutes <= 0:
            return
        await asyncio.sleep(minutes * 60)
        try:
            await message.delete()
        except:
            pass
    
    async def setup_hook(self):
        """Setup bot hooks and load extensions"""
        # Load extensions
        for ext in ['cogs.admin', 'cogs.moderation', 'cogs.utilities', 'cogs.fun', 'cogs.voice']:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")
    
    async def on_ready(self):
        """Bot ready event handler"""
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        
        # Set up presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="за сервером | !help"
        )
        await self.change_presence(activity=activity)
        
        # Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        # Initialize invite cache
        for guild in self.guilds:
            try:
                invites = await guild.invites()
                self.invite_cache[guild.id] = {
                    invite.code: invite.uses for invite in invites
                }
            except:
                pass

def main():
    """Main entry point for the bot"""
    bot = EnhancedBot()
    
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("No Discord token found in environment variables")
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        logger.error("Failed to login. Please check your token.")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == '__main__':
    main() 
