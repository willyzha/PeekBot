from discord.ext import commands
from random import choice
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
from collections import Counter, defaultdict, namedtuple
import discord
import asyncio
import sqlite3 as lite
import sys
import os

DATABASE_PATH = "data/database/data.db"

class Database:
    """General commands."""
    def __init__(self, bot):
        self.database = lite.connect(DATABASE_PATH)

    async def on_message(self, message):
        server = message.server
        author = message.author
        channel = message.channel
        
        c = self.database.cursor()

        c.execute("SELECT EXISTS(SELECT 1 FROM USER WHERE id="+str(author.id)+" collate nocase) LIMIT 1")
        if c.fetchone()[0]==0:
            c.execute("INSERT INTO USER VALUES ('"+author.name+"',"+author.id+",'"+str(author.bot)+"','"+author.avatar+"','"+str(author.created_at)+"')")

        c.execute("SELECT EXISTS(SELECT 1 FROM SERVERS WHERE id="+str(server.id)+" collate nocase) LIMIT 1")
        if c.fetchone()[0]==0:
            c.execute("INSERT INTO SERVERS VALUES ('"+server.name+"',"+server.id+","+server.owner.id+")")

        print(message.edited_timestamp)
        sql_command = message.id+",'"+str(message.edited_timestamp)+"','"+str(message.timestamp)+"','"+str(message.tts)+"','"+str(message.author.name)+"',"+str(message.author.id)+",'"+message.content+"',"+message.server.id+","+message.channel.id
        
        print(sql_command)
        
        c.execute("INSERT INTO MESSAGE VALUES ("+sql_command+")")
        self.database.commit()        

def check_folders():
    folders = ("data", "data/database/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)

def check_files():
    if not os.path.isfile(DATABASE_PATH):
        conn = lite.connect(DATABASE_PATH)
        c = conn.cursor()
        #c.execute("CREATE TABLE IF NOT EXISTS servers (Id INT, Name TEXT)")
        #c.execute("CREATE TABLE IF NOT EXISTS users (Id INT, ServerId INT, Name TEXT, Avatar_Url TEXT)")
        #c.execute("CREATE TABLE IF NOT EXISTS messages (UserId INT, Message TEXT)")

def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Database(bot))