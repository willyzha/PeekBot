from os import path
from wordcloud import WordCloud
import sqlite3 as lite
from discord.ext import commands
import matplotlib.pyplot as plt
import numpy as np
import os
from urllib import request
from PIL import Image
from io import BytesIO 

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
        channel = ctx.message.channel
        self.database = lite.connect(DATABASE_PATH)
        
        c = self.database.cursor()
        wordcloud_text = ""
        sql_cmd = "SELECT content FROM MESSAGE WHERE author_id=? AND channel_id=?"
        for row in c.execute(sql_cmd, (author.id, channel.id,)):
            wordcloud_text = wordcloud_text.re + row[0].replace("wordcloud","") + " "
        
        wordcloud = WordCloud(width=800, height=400).generate(wordcloud_text)
        
        temp_wordcloud_file = WORDCLOUD_PATH+str(author.id)+".png"    
        wordcloud.to_file(temp_wordcloud_file,)
        
        await self.bot.say(author.mention)
        await self.bot.upload(temp_wordcloud_file)
                
    @commands.command(pass_context=True)
    async def mycloud(self, ctx):
        server = ctx.message.server
        author = ctx.message.author
        self.database = lite.connect(DATABASE_PATH)
        
        c = self.database.cursor()
        wordcloud_text = ""
        sql_cmd = "SELECT content FROM MESSAGE WHERE author_id=?"
        for row in c.execute(sql_cmd, (author.id,)):
            wordcloud_text = wordcloud_text + row[0] + " "
            
        avatar_url = author.avatar_url
        if avatar_url == "":
            avatar_url = author.default_avatar_url
        print(avatar_url)
        avatar_path = WORDCLOUD_PATH + str(author.id)+"_avatar.webp"
        req = request.Request(avatar_url, headers={'User-Agent': 'Mozilla/5.0'})

        with request.urlopen(req) as url:
            with open(avatar_path, 'wb') as f:
                f.write(url.read())
                f.close()
        
        file = BytesIO(request.urlopen(req).read())
        img = Image.open(file)
        
        mask = np.array(img)#Image.open(avatar_path))
        
        temp_wordcloud_file = WORDCLOUD_PATH+str(author.id)+".png"    
        wc = WordCloud(background_color="white", mask=mask)
        wc.generate(wordcloud_text)
        
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