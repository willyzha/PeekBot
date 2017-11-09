from discord.ext import commands
import discord
import asyncio
import urllib.request
import json
from .utils.dataIO import dataIO
import os

PIZZA_SETTINGS = "data/pizza/settings.json"

class Pizza:
    def __init__(self, bot):
        self.bot = bot
        self.api_key = dataIO.load_json(PIZZA_SETTINGS)["giphy_api_key"]

    @commands.group(pass_context=True, no_pm=True)
    async def pizza(self, ctx):
        with urllib.request.urlopen("http://api.giphy.com/v1/gifs/random?tag=pizza&api_key="+self.api_key) as url:
            data = json.loads(url.read().decode('utf-8'))
            print(json.dumps(data, sort_keys=True, indent=4))
            msg = data["data"]["image_original_url"]
            await self.bot.say(msg)

def check_folders():
    folders = ("data", "data/pizza/")
    for folder in folders:
         if not os.path.exists(folder):
              print("Creating " + folder + " folder...")
              os.makedirs(folder)

def check_files():
    if not os.path.isfile(PIZZA_SETTINGS):
         print("Creating empty settings.json...")
         dataIO.save_json(PIZZA_SETTINGS, {"giphy_api_key": ""})

def check_api_key():
    settings = dataIO.load_json(PIZZA_SETTINGS)
    return (settings["giphy_api_key"] != "")

def setup(bot):
    check_folders()
    check_files()
    if check_api_key():
        n = Pizza(bot)
        bot.add_cog(n)

        
