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

    @commands.group(pass_context=True)
    @checks.mod_or_permissions(administrator=True)
    async def tts(self, ctx):
        server = ctx.message.server
        msg = box("TextToSpeech Enabled")
        self.ttsEnabled = True
        await self.bot.say(msg)

    @tts.command(pass_context=True)
    async def off():
        """Turn off TextToSpeech"""
        server = ctx.message.server
        msg = box("TextToSpeech Disabled")
        self.ttsEnabled = False
        await self.bot.say(msg)

def setup(bot):
    bot.add_cog(TextToSpeech(bot))
