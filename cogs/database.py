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
        self.client = bot

    async def on_message(self, message):
        self.save_message_to_database(message)

    @commands.command(hidden=True, pass_context=True)
    @checks.mod_or_permissions(manage_server=True)
    async def rebuild_database(self, ctx):
        server = ctx.message.server
        client = self.client
        for channel in server.channels:
            if channel.type == discord.ChannelType.text:
                print("Saving channel " + channel.name)
                async for message in client.logs_from(channel, limit=99999):
                    self.save_message_to_database(message)
        
    def save_message_to_database(self, message):
        server = message.server
        author = message.author
        channel = message.channel
       
        if server is None:
            return
       
        c = self.database.cursor()

        sql_cmd = "SELECT EXISTS(SELECT 1 FROM USER WHERE id=? collate nocase) LIMIT 1"
        c.execute(sql_cmd, (author.id,))
        if c.fetchone()[0]==0:
            # name, id, bot, avatar, created_at
            sql_cmd = "INSERT INTO USER VALUES (?,?,?,?,?)"
            c.execute(sql_cmd, (string(author.name), author.id, string(author.bot), string(author.avatar), string(author.created_at),))

        sql_cmd = "SELECT EXISTS(SELECT 1 FROM SERVERS WHERE id=? collate nocase) LIMIT 1"
        c.execute(sql_cmd, (server.id,))
        if c.fetchone()[0]==0:
            # name, id, owner_id
            sql_cmd = "INSERT INTO USER VALUES (?,?,?)"
            c.execute(sql_cmd, (string(server.name),server.id,server.owner.id,))

        sql_cmd = "SELECT EXISTS(SELECT 1 FROM MESSAGE WHERE message_id=? collate nocase) LIMIT 1"
        c.execute(sql_cmd, (message.id,))
        if c.fetchone()[0]==0:
            sql_cmd = "INSERT INTO MESSAGE VALUES (?,?,?,?,?,?,?,?,?)"  

            c.execute(sql_cmd, (message.id,string(message.edited_timestamp),string(message.timestamp),string(message.tts),string(message.author.name),message.author.id,message.content,message.server.id,message.channel.id,))
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

def string(input):
    if input is None:
        return "None"
    else:
        return str(input)
        
def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Database(bot))
