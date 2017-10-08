from discord.ext import commands
from random import choice
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
from collections import Counter, defaultdict, namedtuple
import discord
import time
import os
import asyncio
import chardet

class TextToSpeech:
    """General commands."""
    def __init__(self, bot):
        self.bot = bot
        self.ttsEnabled = False

    @commands.group(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(administrator=True)
    async def tts(self, ctx):
        """Gives the current status of TextToSpeech"""
        if ctx.invoked_subcommand is None:
            server = ctx.message.server
            if self.ttsEnabled:
                msg = box("TextToSpeech is currently enabled")
            else:
                msg = box("TextToSpeech is currently disabled")
            await self.bot.say(msg)

    @tts.command(pass_context=True)
    async def off(self, ctx):
        """Turn off TextToSpeech"""
        server = ctx.message.server
        msg = box("TextToSpeech Disabled")
        self.ttsEnabled = False
        await self.bot.say(msg)
        
    @tts.command(pass_context=True)
    async def on(self, ctx):
        """Turn on TextToSpeech"""
        server = ctx.message.server
        msg = box("TextToSpeech Enabled")
        self.ttsEnabled = True
        await self.bot.say(msg)

def setup(bot):
    bot.add_cog(TextToSpeech(bot))
