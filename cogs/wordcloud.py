from os import path
from wordcloud import WordCloud
import sqlite3 as lite
from discord.ext import commands
import matplotlib.pyplot as plt
import os

DATABASE_PATH = "data/database/data.db"
WORDCLOUD_PATH = "data/wordcloud/"

class Wordcloud:
    """General commands."""
    def __init__(self, bot):
        self.bot = bot
        self.database = lite.connect(DATABASE_PATH)
    
    @commands.command(pass_context=True)
    async def wordcloud(self, ctx):
        server = ctx.message.server
        author = ctx.message.author
        self.database = lite.connect(DATABASE_PATH)
        
        c = self.database.cursor()
        wordcloud_text = ""
        sql_cmd = "SELECT content FROM MESSAGE WHERE author_id=?"
        for row in c.execute(sql_cmd, (author.id,)):
            wordcloud_text = wordcloud_text + row[0] + " "
        
        wordcloud = WordCloud().generate(wordcloud_text)
        
        temp_wordcloud_file = WORDCLOUD_PATH+str(author.id)+".png"    
        wordcloud.to_file(temp_wordcloud_file)
                
        await self.bot.upload(temp_wordcloud_file)
                
        
def check_folders():
    folders = ("data", WORDCLOUD_PATH)
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)
        
def setup(bot):
    check_folders()
    bot.add_cog(Wordcloud(bot))