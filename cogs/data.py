from discord.ext import commands
from random import choice
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
from collections import Counter, defaultdict, namedtuple
import discord

import sqlite3 as lite
import sys

DATABASE_PATH = "data/trivia/data.db"

class Data:
    """General commands."""
    def __init__(self, bot):
        self.database = lite.connect(DATABASE_PATH)

    async def on_message(self, message):
        serverId = message.server.id
        authorId = message.author.id
        
        c = self.database.cursor()
        

        
def check_folders():
    folders = ("data", "data/data/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)

def check_files():
    if not os.path.isfile(DATABASE_PATH):
        conn = lite.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS servers (Id INT, Name TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS users (Id INT, ServerId INT, Name TEXT, Avatar_Url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS messages (UserId INT, Message TEXT)"
        
def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Data(bot))