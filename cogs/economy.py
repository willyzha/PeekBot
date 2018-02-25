import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from collections import namedtuple, defaultdict, deque, OrderedDict
from datetime import datetime
from copy import deepcopy
from .utils import checks
from cogs.utils.chat_formatting import pagify, box
from enum import Enum
from __main__ import send_cmd_help
import os
import time
import logging
import random
import asyncio
from asyncio import Lock
import sys
import threading
from PIL import Image
from random import randint

default_settings = {"PAYDAY_TIME": 300, "PAYDAY_CREDITS": 120,
                    "SLOT_MIN": 5, "SLOT_MAX": 100, "SLOT_TIME": 0,
                    "REGISTER_CREDITS": 0}
multiplier_settings = {"Potato Farmer": 2, "Sweet Potato Farmer": 2.5, "Tomato Farmer": 3, "Heirloom Tomato Farmer": 3.5, "Potato Factory Owner": 5, "Tomato Factory Owner": 7, "Asparagus Factory Owner": 9, "Leek Factory Owner": 15}

class EconomyError(Exception):
    pass


class OnCooldown(EconomyError):
    pass


class InvalidBid(EconomyError):
    pass


class BankError(Exception):
    pass


class AccountAlreadyExists(BankError):
    pass


class NoAccount(BankError):
    pass


class InsufficientBalance(BankError):
    pass


class NegativeValue(BankError):
    pass


class SameSenderAndReceiver(BankError):
    pass


NUM_ENC = "\N{COMBINING ENCLOSING KEYCAP}"


class SMReel(Enum):
    cherries  = "\N{CHERRIES}"
    cookie    = "\N{COOKIE}"
    two       = "\N{DIGIT TWO}" + NUM_ENC
    flc       = "\N{FOUR LEAF CLOVER}"
    cyclone   = "\N{CYCLONE}"
    sunflower = "\N{SUNFLOWER}"
    six       = "\N{DIGIT SIX}" + NUM_ENC
    mushroom  = "\N{MUSHROOM}"
    heart     = "\N{HEAVY BLACK HEART}"
    snowflake = "\N{SNOWFLAKE}"

PAYOUTS = {
    (SMReel.two, SMReel.two, SMReel.six) : {
        "payout" : lambda x: x * 2500 + x,
        "phrase" : "JACKPOT! 226! Your bid has been multiplied * 2500!"
    },
    (SMReel.flc, SMReel.flc, SMReel.flc) : {
        "payout" : lambda x: x + 1000,
        "phrase" : "4LC! +1000!"
    },
    (SMReel.cherries, SMReel.cherries, SMReel.cherries) : {
        "payout" : lambda x: x + 800,
        "phrase" : "Three cherries! +800!"
    },
    (SMReel.two, SMReel.six) : {
        "payout" : lambda x: x * 4 + x,
        "phrase" : "2 6! Your bid has been multiplied * 4!"
    },
    (SMReel.cherries, SMReel.cherries) : {
        "payout" : lambda x: x * 3 + x,
        "phrase" : "Two cherries! Your bid has been multiplied * 3!"
    },
    "3 symbols" : {
        "payout" : lambda x: x + 500,
        "phrase" : "Three symbols! +500!"
    },
    "2 symbols" : {
        "payout" : lambda x: x * 2 + x,
        "phrase" : "Two consecutive symbols! Your bid has been multiplied * 2!"
    },
}

SLOT_PAYOUTS_MSG = ("Slot machine payouts:\n"
                    "{two.value} {two.value} {six.value} Bet * 2500\n"
                    "{flc.value} {flc.value} {flc.value} +1000\n"
                    "{cherries.value} {cherries.value} {cherries.value} +800\n"
                    "{two.value} {six.value} Bet * 4\n"
                    "{cherries.value} {cherries.value} Bet * 3\n\n"
                    "Three symbols: +500\n"
                    "Two symbols: Bet * 2".format(**SMReel.__dict__))


class Bank:

    def __init__(self, bot, file_path):
        self.accounts = dataIO.load_json(file_path)
        self.bot = bot

    def create_account(self, user, *, initial_balance=0):
        server = user.server
        if not self.account_exists(user):
            if server.id not in self.accounts:
                self.accounts[server.id] = {}
            if user.id in self.accounts:  # Legacy account
                balance = self.accounts[user.id]["balance"]
            else:
                balance = initial_balance
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            account = {"name": user.name,
                       "balance": balance,
                       "created_at": timestamp
                       }
            self.accounts[server.id][user.id] = account
            self._save_bank()
            return self.get_account(user)
        else:
            raise AccountAlreadyExists()

    def account_exists(self, user):
        try:
            self._get_account(user)
        except NoAccount:
            return False
        return True

    def withdraw_credits(self, user, amount):
        server = user.server

        if amount < 0:
            raise NegativeValue()

        account = self._get_account(user)
        if account["balance"] >= amount:
            account["balance"] -= amount
            self.accounts[server.id][user.id] = account
            self._save_bank()
        else:
            raise InsufficientBalance()

    def add_money(self, user, amount):
        server = user.server
        account = self._get_account(user)
        account["balance"] +=  amount
        self.accounts[server.id][user.id] = account
        self._save_bank()

    def deposit_credits(self, user, amount):
        server = user.server
        if amount < 0:
            raise NegativeValue()
        account = self._get_account(user)
        account["balance"] += amount
        self.accounts[server.id][user.id] = account
        self._save_bank()

    def set_credits(self, user, amount):
        server = user.server
        if amount < 0:
            raise NegativeValue()
        account = self._get_account(user)
        account["balance"] = amount
        self.accounts[server.id][user.id] = account
        self._save_bank()

    def transfer_credits(self, sender, receiver, amount):
        if amount < 0:
            raise NegativeValue()
        if sender is receiver:
            raise SameSenderAndReceiver()
        if self.account_exists(sender) and self.account_exists(receiver):
            sender_acc = self._get_account(sender)
            if sender_acc["balance"] < amount:
                raise InsufficientBalance()
            self.withdraw_credits(sender, amount)
            self.deposit_credits(receiver, amount)
        else:
            raise NoAccount()

    def can_spend(self, user, amount):
        account = self._get_account(user)
        if account["balance"] >= amount:
            return True
        else:
            return False

    def wipe_bank(self, server):
        self.accounts[server.id] = {}
        self._save_bank()

    def get_server_accounts(self, server):
        if server.id in self.accounts:
            raw_server_accounts = deepcopy(self.accounts[server.id])
            accounts = []
            for k, v in raw_server_accounts.items():
                v["id"] = k
                v["server"] = server
                acc = self._create_account_obj(v)
                accounts.append(acc)
            return accounts
        else:
            return []

    def get_all_accounts(self):
        accounts = []
        for server_id, v in self.accounts.items():
            server = self.bot.get_server(server_id)
            if server is None:
                # Servers that have since been left will be ignored
                # Same for users_id from the old bank format
                continue
            raw_server_accounts = deepcopy(self.accounts[server.id])
            for k, v in raw_server_accounts.items():
                v["id"] = k
                v["server"] = server
                acc = self._create_account_obj(v)
                accounts.append(acc)
        return accounts

    def get_balance(self, user):
        account = self._get_account(user)
        return account["balance"]

    def get_account(self, user):
        acc = self._get_account(user)
        acc["id"] = user.id
        acc["server"] = user.server
        return self._create_account_obj(acc)

    def _create_account_obj(self, account):
        account["member"] = account["server"].get_member(account["id"])
        account["created_at"] = datetime.strptime(account["created_at"],
                                                  "%Y-%m-%d %H:%M:%S")
        Account = namedtuple("Account", "id name balance "
                             "created_at server member")
        return Account(**account)

    def _save_bank(self):
        dataIO.save_json("data/economy/bank.json", self.accounts)

    def _save_settings(self):
        dataIO.save_json("data/economy/settings.json", self.settings)
    
    def _get_account(self, user):
        server = user.server
        try:
            return deepcopy(self.accounts[server.id][user.id])
        except KeyError:
            raise NoAccount()


class SetParser:
    def __init__(self, argument):
        allowed = ("+", "-")
        if argument and argument[0] in allowed:
            try:
                self.sum = int(argument)
            except:
                raise
            if self.sum < 0:
                self.operation = "withdraw"
            elif self.sum > 0:
                self.operation = "deposit"
            else:
                raise
            self.sum = abs(self.sum)
        elif argument.isdigit():
            self.sum = int(argument)
            self.operation = "set"
        else:
            raise


class Economy:
    """Economy

    Get rich and have fun with imaginary currency!"""

    def __init__(self, bot):
        global default_settings
        self.bot = bot
        self.bank = Bank(bot, "data/economy/bank.json")
        self.file_path = "data/economy/settings.json"
        self.settings = dataIO.load_json(self.file_path)
        if "PAYDAY_TIME" in self.settings:  # old format
            default_settings = self.settings
            self.settings = {}
        self.settings = defaultdict(lambda: default_settings, self.settings)
        self.payday_register = defaultdict(dict)
        self.slot_register = defaultdict(dict)
        self.game_state = "null"
        self.timer = 0
        self.players = {}
        
        """
        self.players
            player_name
                "hand"
                    0 (hand number)
                        "card"
                            0 (card number)
                                "rank"
                                "suit"
                                "value"
                        "ranks"
                        "bet"
                        "standing"
                        "blackjack"
                "curr_hand"
            *dealer*
        """

        self.deck = {}
        
        self.dealer_hidden_card = None
        self.deck_queue = []
        self.drawn_queue = []
        self.num_decks = 2
        self.draw_lock = Lock()
       
        for suit in ["hearts", "diamonds", "clubs", "spades"]:
            self.deck[suit] = {}
            for i in range(2, 11):
                self.deck[suit][i] = {}
                self.deck[suit][i]["rank"] = str(i)
                self.deck[suit][i]["value"] = i
            
            self.deck[suit][1] = {}
            self.deck[suit][1]["rank"] = "ace"
            self.deck[suit][1]["value"] = 11

            self.deck[suit][11] = {}
            self.deck[suit][11]["rank"] = "jack"
            self.deck[suit][11]["value"] = 10

            self.deck[suit][12] = {}
            self.deck[suit][12]["rank"] = "queen"
            self.deck[suit][12]["value"] = 10

            self.deck[suit][13] = {}
            self.deck[suit][13]["rank"] = "king"
            self.deck[suit][13]["value"] = 10

            #with (yield from self.draw_lock):
            for j in range(0, self.num_decks):
                for card in list(self.deck[suit].values()):
                    temp_card = card
                    temp_card["suit"] = suit                
                    self.drawn_queue.append(temp_card)

        self.shuffle_deck()
        
        #print(self.deck_queue)
        #print(self.drawn_queue)
        
        #print(len(self.deck_queue))
        #print(len(self.drawn_queue))
        
    @commands.group(name="bank", pass_context=True)
    async def _bank(self, ctx):
        """Bank operations"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @_bank.command(pass_context=True, no_pm=True)
    async def register(self, ctx):
        """Registers an account at the Twentysix bank"""
        settings = self.settings[ctx.message.server.id]
        author = ctx.message.author
        credits = 0
        if ctx.message.server.id in self.settings:
            credits = settings.get("REGISTER_CREDITS", 0)
        try:
            account = self.bank.create_account(author, initial_balance=credits)
            await self.bot.say("{} Account opened. Current balance: {}"
                               "".format(author.mention, account.balance))
        except AccountAlreadyExists:
            await self.bot.say("{} You already have an account at the"
                               " Twentysix bank.".format(author.mention))

    @_bank.command(pass_context=True)
    async def balance(self, ctx, user: discord.Member=None):
        """Shows balance of user.

        Defaults to yours."""
        if not user:
            user = ctx.message.author
            try:
                await self.bot.say("{} Your balance is: {}".format(
                    user.mention, self.bank.get_balance(user)))
            except NoAccount:
                await self.bot.say("{} You don't have an account at the"
                                   " Twentysix bank. Type `{}bank register`"
                                   " to open one.".format(user.mention,
                                                          ctx.prefix))
        else:
            try:
                await self.bot.say("{}'s balance is {}".format(
                    user.name, self.bank.get_balance(user)))
            except NoAccount:
                await self.bot.say("That user has no bank account.")

    @_bank.command(pass_context=True)
    async def transfer(self, ctx, user: discord.Member, sum: int):
        """Transfer credits to other users"""
        author = ctx.message.author
        try:
            self.bank.transfer_credits(author, user, sum)
            logger.info("{}({}) transferred {} credits to {}({})".format(
                author.name, author.id, sum, user.name, user.id))
            await self.bot.say("{} credits have been transferred to {}'s"
                               " account.".format(sum, user.name))
        except NegativeValue:
            await self.bot.say("You need to transfer at least 1 credit.")
        except SameSenderAndReceiver:
            await self.bot.say("You can't transfer credits to yourself.")
        except InsufficientBalance:
            await self.bot.say("You don't have that sum in your bank account.")
        except NoAccount:
            await self.bot.say("That user has no bank account.")

    @_bank.command(name="set", pass_context=True)
    @checks.admin_or_permissions(manage_server=True)
    async def _set(self, ctx, user: discord.Member, credits: SetParser):
        """Sets credits of user's bank account. See help for more operations

        Passing positive and negative values will add/remove credits instead

        Examples:
            bank set @Twentysix 26 - Sets 26 credits
            bank set @Twentysix +2 - Adds 2 credits
            bank set @Twentysix -6 - Removes 6 credits"""
        author = ctx.message.author
        try:
            if credits.operation == "deposit":
                self.bank.deposit_credits(user, credits.sum)
                logger.info("{}({}) added {} credits to {} ({})".format(
                    author.name, author.id, credits.sum, user.name, user.id))
                await self.bot.say("{} credits have been added to {}"
                                   "".format(credits.sum, user.name))
            elif credits.operation == "withdraw":
                self.bank.withdraw_credits(user, credits.sum)
                logger.info("{}({}) removed {} credits to {} ({})".format(
                    author.name, author.id, credits.sum, user.name, user.id))
                await self.bot.say("{} credits have been withdrawn from {}"
                                   "".format(credits.sum, user.name))
            elif credits.operation == "set":
                self.bank.set_credits(user, credits.sum)
                logger.info("{}({}) set {} credits to {} ({})"
                            "".format(author.name, author.id, credits.sum,
                                      user.name, user.id))
                await self.bot.say("{}'s credits have been set to {}".format(
                    user.name, credits.sum))
        except InsufficientBalance:
            await self.bot.say("User doesn't have enough credits.")
        except NoAccount:
            await self.bot.say("User has no bank account.")

    @_bank.command(pass_context=True, no_pm=True)
    @checks.serverowner_or_permissions(administrator=True)
    async def reset(self, ctx, confirmation: bool=False):
        """Deletes all server's bank accounts"""
        if confirmation is False:
            await self.bot.say("This will delete all bank accounts on "
                               "this server.\nIf you're sure, type "
                               "{}bank reset yes".format(ctx.prefix))
        else:
            self.bank.wipe_bank(ctx.message.server)
            await self.bot.say("All bank accounts of this server have been "
                               "deleted.")

    @commands.command(pass_context=True, no_pm=True)
    async def payday(self, ctx):  # TODO
        """Get some free credits"""
        author = ctx.message.author
        server = author.server
        id = author.id
        if self.bank.account_exists(author):
            if id in self.payday_register[server.id]:
                seconds = abs(self.payday_register[server.id][
                              id] - int(time.perf_counter()))
                if seconds >= self.settings[server.id]["PAYDAY_TIME"]:
                    multiplier = 1;
                    for role in author.roles:
                        if role.name in multiplier_settings:
                            if multiplier_settings[role.name] > multiplier:
                                multiplier = multiplier_settings[role.name]
                
                    payday_credit = self.settings[server.id]["PAYDAY_CREDITS"] * multiplier
                    self.bank.deposit_credits(author, payday_credit)
                    self.payday_register[server.id][
                        id] = int(time.perf_counter())
                    await self.bot.say(
                        "{} Here, take some credits. Enjoy! (+{}"
                        " credits!)".format(
                            author.mention,
                            str(payday_credit)))
                else:
                    dtime = self.display_time(
                        self.settings[server.id]["PAYDAY_TIME"] - seconds)
                    await self.bot.say(
                        "{} Too soon. For your next payday you have to"
                        " wait {}.".format(author.mention, dtime))
            else:
                multiplier = 1;
                for role in author.roles:
                    if role.name in multiplier_settings:
                        if multiplier_settings[role.name] > multiplier:
                            multiplier = multiplier_settings[role.name]
                            
                payday_credit = self.settings[server.id]["PAYDAY_CREDITS"] * multiplier
                self.payday_register[server.id][id] = int(time.perf_counter())
                self.bank.deposit_credits(author, payday_credit)
                await self.bot.say(
                    "{} Here, take some credits. Enjoy! (+{} credits!)".format(
                        author.mention,
                        str(payday_credit)))
        else:
            await self.bot.say("{} You need an account to receive credits."
                               " Type `{}bank register` to open one.".format(
                                   author.mention, ctx.prefix))

    @commands.group(pass_context=True)
    async def leaderboard(self, ctx):
        """Server / global leaderboard

        Defaults to server"""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self._server_leaderboard)

    @leaderboard.command(name="server", pass_context=True)
    async def _server_leaderboard(self, ctx, top: int=10):
        """Prints out the server's leaderboard

        Defaults to top 10"""
        # Originally coded by Airenkun - edited by irdumb
        server = ctx.message.server
        if top < 1:
            top = 10
        bank_sorted = sorted(self.bank.get_server_accounts(server),
                             key=lambda x: x.balance, reverse=True)
        bank_sorted = [a for a in bank_sorted if a.member] #  exclude users who left
        if len(bank_sorted) < top:
            top = len(bank_sorted)
        topten = bank_sorted[:top]
        highscore = ""
        place = 1
        for acc in topten:
            highscore += str(place).ljust(len(str(top)) + 1)
            highscore += (str(acc.member.display_name) + " ").ljust(23 - len(str(acc.balance)))
            highscore += str(acc.balance) + "\n"
            place += 1
        if highscore != "":
            for page in pagify(highscore, shorten_by=12):
                await self.bot.say(box(page, lang="py"))
        else:
            await self.bot.say("There are no accounts in the bank.")

    @leaderboard.command(name="global")
    async def _global_leaderboard(self, top: int=10):
        """Prints out the global leaderboard

        Defaults to top 10"""
        if top < 1:
            top = 10
        bank_sorted = sorted(self.bank.get_all_accounts(),
                             key=lambda x: x.balance, reverse=True)
        bank_sorted = [a for a in bank_sorted if a.member] #  exclude users who left
        unique_accounts = []
        for acc in bank_sorted:
            if not self.already_in_list(unique_accounts, acc):
                unique_accounts.append(acc)
        if len(unique_accounts) < top:
            top = len(unique_accounts)
        topten = unique_accounts[:top]
        highscore = ""
        place = 1
        for acc in topten:
            highscore += str(place).ljust(len(str(top)) + 1)
            highscore += ("{} |{}| ".format(acc.member, acc.server)
                          ).ljust(23 - len(str(acc.balance)))
            highscore += str(acc.balance) + "\n"
            place += 1
        if highscore != "":
            for page in pagify(highscore, shorten_by=12):
                await self.bot.say(box(page, lang="py"))
        else:
            await self.bot.say("There are no accounts in the bank.")

    def already_in_list(self, accounts, user):
        for acc in accounts:
            if user.id == acc.id:
                return True
        return False

    @commands.command(pass_context=True, no_pm=True)
    async def dice(self, ctx, bid: int, guess: int):
        """Play the dice game"""
        author = ctx.message.author
        server = author.server
                                
        try:
            if not self.bank.can_spend(author, bid):
                raise InsufficientBalance
                
            await self.dice_game(author, bid, guess)
        except NoAccount:
            await self.bot.say("{} You need an account to use the slot "
                   "machine. Type `{}bank register` to open one."
                   "".format(author.mention, ctx.prefix))
        except InsufficientBalance:
            await self.bot.say("{} You need an account with enough funds to "
                               "play the slot machine.".format(author.mention))
    
    async def dice_game(self, author, bid, guess):
        payout = 0
        roll = random.randint(1,6)
        if roll == guess:
            payout = bid * 6
                    
        if payout:
            then = self.bank.get_balance(author)
            pay = payout
            now = then - bid + pay
            pay1 = pay - bid
            self.bank.add_money(author, pay1)
            await self.bot.say("{}\n{} {}\n\nYour bid: {}\n{} → {}!"
                               "".format("I rolled a " + str(roll) + ".", author.mention,
                                         "You guessed correctly!", bid, then, now))
        else:
            then = self.bank.get_balance(author)
            self.bank.withdraw_credits(author, bid)
            now = then - bid
            await self.bot.say("{}\n{} you guessed wrong loser!\nYour bid: {}\n{} → {}!"
                               "".format("I rolled a " + str(roll) + ".", author.mention, bid, then, now))    

    @commands.group(pass_context=True, no_pm=True)
    async def blackjack(self, ctx):
        """Play some blackjack"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @blackjack.command(pass_context=True, no_pm=True)
    async def start(self, ctx):
        """Start a game of blackjack"""

        if self.game_state == "null":
            self.game_state = "pregame"
            await self.blackjack_game(ctx)
        else:
            await self.bot.say("A blackjack game is already in progress!")

    @blackjack.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def stop(self, ctx):
        """Stop the current game of blackjack (no refunds)"""

        if self.game_state == "null":
            await self.bot.say("There is no game currently running")
        else:
            self.game_state = "null"
            await self.bot.say("**Blackjack has been stopped**")

    @blackjack.command(pass_context=True, no_pm=True)
    async def bet(self, ctx, bet: int):
        """Join the game of blackjack with your opening bet"""
        player = ctx.message.author
        if self.bank.can_spend(player, bet) and self.game_state == "pregame":
            if bet < 0 or bet > 100000:
                await self.bot.say("{0}, bet must be between {1} and {2}.".format(player.mention, 0, 100000))
            else:
                if not (player in self.players.keys()):
                    await self.bot.say("{0} has placed a bet of {1}".format(player.mention, bet))
                    self.bank.withdraw_credits(player, bet)

                else:
                    await self.bot.say("{0} has placed a new bet of {1}".format(player.mention, bet))
                    self.bank.add_money(player, bet)
                    self.bank.withdraw_credits(player, bet)

                self.players[player] = {}
                self.players[player]["curr_hand"] = 0
                self.players[player]["hand"] = {}
                self.players[player]["hand"][0] = {}
                self.players[player]["hand"][0]["card"] = {}
                self.players[player]["hand"][0]["ranks"] = []
                self.players[player]["hand"][0]["bet"] = bet
                self.players[player]["hand"][0]["standing"] = False
                self.players[player]["hand"][0]["blackjack"] = False
                
        
        elif self.game_state == "null":
            await self.bot.say("There is currently no game running, type `!blackjack start` to begin one")
        
        elif self.game_state != "pregame" and self.game_state != "null":
            await self.bot.say("There is currently a game in progress, wait for the next game")

        elif not self.bank.can_spend(player, bet):
            await self.bot.say("{0}, you need an account with enough funds to play blackjack".format(player.mention))

    @blackjack.command(pass_context=True, no_pm=True)
    async def hit(self, ctx):
        """Hit and draw another card"""
        player = ctx.message.author

        card = await self.draw_card(player)
        curr_hand = self.players[player]["curr_hand"]
        ranks = self.players[player]["hand"][curr_hand]["ranks"]
        count = await self.count_hand(player, curr_hand)

        if self.game_state == "game" and self.players[player]["hand"][curr_hand]["standing"] == False:
            
            if count > 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has **busted**!".format(player.mention))
                self.players[player]["hand"][curr_hand]["standing"] = True
            
            elif count > 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has **busted** on their current hand! Moving on to next split hand!".format(player.mention))
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif "ace" in ranks:
                await self.bot.say("{0} has hit and drawn a {1}, totaling their hand to {2} ({3})".format(player.mention, card, str(count), str(count - 10)))

            else:
                await self.bot.say("{0} has hit and drawn a {1}, totaling their hand to {2}".format(player.mention, card, count))

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot hit right now".format(player.mention))
        
        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot hit".format(player.mention))

    @blackjack.command(pass_context=True, no_pm=True)
    async def stand(self, ctx):
        """Finishing drawing and stand with your current cards"""
        player = ctx.message.author
        curr_hand = self.players[player]["curr_hand"]
        if self.game_state == "game" and not self.players[player]["hand"][curr_hand]["standing"]:
            count = await self.count_hand(player, self.players[player]["curr_hand"])
            
            if len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has stood with a hand totaling to {1}".format(player.mention, str(count)))
            
            else:
                await self.bot.say("{0} has stood with a hand totaling to {1}. Moving on to next split hand!".format(player.mention, str(count)))
                self.players[player]["curr_hand"] += 1

            self.players[player]["hand"][curr_hand]["standing"] = True

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot stand right now".format(player.mention))
        
        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are already standing".format(player.mention))


    @blackjack.command(pass_context=True, no_pm=True)
    async def double(self, ctx):
        """Double your original bet and draw one last card"""
        player = ctx.message.author
        curr_hand = self.players[player]["curr_hand"]
        bet = self.players[player]["hand"][curr_hand]["bet"]

        if self.bank.can_spend(player, bet) and not self.players[player]["hand"][curr_hand]["standing"] and self.game_state == "game":
            await self.bot.say("{0} has doubled down, totaling their bet to {1}".format(player.mention, self.players[player]["hand"][curr_hand]["bet"]))

            self.players[player]["hand"][curr_hand]["bet"] += bet
            self.bank.withdraw_credits(player, bet)
            
            card = await self.draw_card(player)
            count = await self.count_hand(player, self.players[player]["curr_hand"])

            if count > 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has **busted**!".format(player.mention))
                self.players[player]["hand"][curr_hand]["standing"] = True
            
            elif count > 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has **busted**! Moving on to next split hand!".format(player.mention))
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count < 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has doubled and drawn a {1}, totaling their hand to {2}".format(player.mention, card, count))
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count < 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has doubled and drawn a {1}, totaling their hand to {2}. Moving on to next split hand!".format(player.mention, card, count))
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot double down right now!".format(player.mention))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot double!".format(player.mention))
        
        elif not self.bank.can_spend(player, bet):
            await self.bot.say("{0}, you do not have enough money to double down!".format(player.mention))
        

    @blackjack.command(pass_context=True, no_pm=True)
    async def split(self, ctx):
        """Split your hand into two seperate hands if you have two cards of the same rank"""
        player = ctx.message.author
        
        curr_hand = self.players[player]["curr_hand"]
        cards = self.players[player]["hand"][curr_hand]["card"]

        if (cards[0]["value"] == 11 and cards[1]["value"] == 1) or (cards[0]["value"] == 1 and cards[1]["value"] == 11): #reset aces to orginal value
            cards[0]["value"] = 11
            cards[0]["rank"] = "ace"

            cards[1]["value"] = 11
            cards[1]["rank"] = "ace"
        
        if cards[0]["value"] == cards[1]["value"] and len(cards) == 2 and self.game_state == "game" and not self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0} has split their {1}'s! Play through your first hand and stand to begin your next!".format(player.mention, cards[0]["value"]))
            hand_index = len(self.players[player]["hand"])
            
            self.players[player]["hand"][hand_index] = {}
            self.players[player]["hand"][hand_index]["card"] = {}
            self.players[player]["hand"][hand_index]["ranks"] = []
            self.players[player]["hand"][hand_index]["bet"] = self.players[player]["hand"][curr_hand]["bet"]
            self.players[player]["hand"][hand_index]["standing"] = False
            self.players[player]["hand"][hand_index]["blackjack"] = False

            self.players[player]["hand"][hand_index]["card"][0] = cards[1]
            del cards[1]

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot split right now!".format(player.mention))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot split!".format(player.mention))

        elif len(cards) != 2:
            await self.bot.say("{0}, you may only split with two cards!".format(player.mention))
  
        elif cards[0]["value"] != cards[1]["value"]:
            await self.bot.say("{0}, you may only split with two cards of the same value!".format(player.mention))


    async def blackjack_game(self, ctx):
        while self.game_state != "null":
            if self.game_state == "pregame":
                self.players = {}
                self.timer = 0
                await self.bot.say(":moneybag::hearts:`Blackjack started!`:diamonds::moneybag:")
                await asyncio.sleep(20)

            if self.game_state == "pregame":
                if len(self.players) == 0:
                    await self.bot.say("No bets made, aborting game!")
                    self.game_state = "null"
                else:
                    self.game_state = "drawing"

            if self.game_state == "drawing":
                for player in self.players:
                    
                    card1 = await self.draw_card(player)
                    card2 = await self.draw_card(player)    

                    # Merge images for the two cards
                    #output_img =  self.merge_image_list(["data/economy/playing_cards/" + card1.replace(" ", "_") + ".png", "data/economy/playing_cards/" + card2.replace(" ", "_") + ".png"])
                    
                    #await self.bot.upload(output_img)

                    curr_hand = self.players[player]["curr_hand"]
                    ranks = self.players[player]["hand"][curr_hand]["ranks"]
                    count = await self.count_hand(player, curr_hand)

                    if "ace" in ranks and ("jack" in ranks or "queen" in ranks or "king" in ranks):
                        await self.bot.say("{0} has a **blackjack**!".format(player.mention))
                        self.players[player]["hand"][curr_hand]["blackjack"] = True
                        self.players[player]["hand"][curr_hand]["standing"] = True

                    elif "ace" in ranks:
                        await self.bot.say("{0} has drawn a {1} and a {2}, totaling to {3} ({4})!".format(player.mention, card1, card2, str(count), str(count-10)))

                    else:
                        await self.bot.say("{0} has drawn a {1} and a {2}, totaling to {3}!".format(player.mention, card1, card2, str(count)))
                    
                    await asyncio.sleep(1)

                self.players["dealer"] = {}
                self.players["dealer"]["curr_hand"] = 0
                self.players["dealer"]["hand"] = {}
                self.players["dealer"]["hand"][0] = {}
                self.players["dealer"]["hand"][0]["card"] = {}
                self.players["dealer"]["hand"][0]["ranks"] = []

                card = await self.draw_card("dealer")
                hidden_card = await self.draw_card("dealer")
                #print(hidden_card)
                
                #output_img = self.merge_image_list(["data/economy/playing_cards/" + card.replace(" ", "_") + ".png", "data/economy/playing_cards/hidden_card.png"])

                #await self.bot.upload(output_img)

                #if True:
                    #await self.bot.upload("data/economy/playing_cards/hidden_card.png")
                
                await self.bot.say("**The dealer has drawn a {0}!**".format(card))
                self.game_state = "game"

            if self.game_state == "game":
                all_stood = True
                for player in self.players:
                    for hand in self.players[player]["hand"]:
                        if player != "dealer" and not self.players[player]["hand"][hand]["standing"]:
                            all_stood = False

                if self.timer < 60 and not all_stood:
                    self.timer += 1
                    await asyncio.sleep(1)
                elif all_stood or self.timer >= 60:
                    self.game_state = "endgame"

            if self.game_state == "endgame":

                card = await self.draw_card("dealer")
                dealer_count = await self.count_hand("dealer", 0)
                ranks = self.players["dealer"]["hand"][0]["ranks"]
                blackjack = False

                if "ace" in ranks and ("jack" in ranks or "queen" in ranks or "king" in ranks) and len(self.players["dealer"]["hand"][curr_hand]["ranks"]) == 2:
                    blackjack = True

                if dealer_count <= 21 and not blackjack: #if dealer has a normal hand, no bust
                    if "ace" in ranks and dealer_count < 17:
                        await self.bot.say("**The dealer has drawn a {0}, totaling his hand to {1} ({2})!**".format(card, str(dealer_count), str(dealer_count - 10)))
                    else:
                        await self.bot.say("**The dealer has drawn a {0}, totaling his hand to {1}!**".format(card, str(dealer_count)))

                
                if blackjack: #if dealer has blackjack
                    await self.bot.say("**The dealer has a blackjack!**")
                    
                    for player in self.players:
                        if player != "dealer":
                            for hand in self.players[player]["hand"]:
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"])
                                    await self.bot.say("{0} ties dealer and pushes!".format(player.mention))
                                else:
                                    await self.bot.say("{0} loses with a score of {1}".format(player.mention, str(count)))

                    self.game_state = "pregame"
                    await asyncio.sleep(3)

                elif dealer_count > 21: #if dealer busts
                    await self.bot.say("**The dealer has busted!**")
                    for player in self.players:
                        if player != "dealer":
                            for hand in self.players[player]["hand"]:
                                count = await self.count_hand(player, hand)
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"] * 2.5)
                                    await self.bot.say("{0} beats dealer with a blackjack and wins **{2}**!".format(player.mention, str(count), self.players[player]["hand"][hand]["bet"] * 1.5))
                                elif count <= 21:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"] * 2)
                                    await self.bot.say("{0} doesn't bust with a score of {1} and wins **{2}**!".format(player.mention, str(count), self.players[player]["hand"][hand]["bet"]))
                                else:
                                    await self.bot.say("{0} busted and wins nothing".format(player.mention))
                    
                    self.game_state = "pregame"
                    await asyncio.sleep(3)

                elif dealer_count >= 17: #if dealer stands
                    await self.bot.say("**The dealer stands at {0}!**".format(dealer_count))
                    for player in self.players:
                        if player != "dealer":
                            for hand in self.players[player]["hand"]:
                                count = await self.count_hand(player, hand)
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"] * 2.5)
                                    await self.bot.say("{0} beats dealer with a blackjack and wins **{2}**!".format(player.mention, str(count), self.players[player]["hand"][hand]["bet"] * 1.5))
                                elif count > 21:
                                    await self.bot.say("{0} busted and wins nothing".format(player.mention))
                                elif count > dealer_count:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"] * 2)
                                    await self.bot.say("{0} beats dealer with a score of {1} and wins **{2}**!".format(player.mention, str(count), self.players[player]["hand"][hand]["bet"]))
                                elif count == dealer_count:
                                    self.bank.add_money(player, self.players[player]["hand"][hand]["bet"])
                                    await self.bot.say("{0} ties dealer and pushes!".format(player.mention))
                                else:
                                    await self.bot.say("{0} loses with a score of {1}".format(player.mention, str(count)))

                    self.game_state = "pregame"
                    await asyncio.sleep(3)
                    
                if len(self.drawn_queue) > len(self.deck_queue):
                    await self.bot.say("The is being shuffled!")
                    self.shuffle_deck()
                    

    async def draw_card(self, player):

        #with (yield from self.draw_lock):
        drawn_card = self.deck_queue.pop(0)           

        #rank = self.deck[suit][num]["rank"]

        curr_hand = self.players[player]["curr_hand"]
        card_index = len(self.players[player]["hand"][curr_hand]["card"])

        if player is "dealer" and card_index == 1:
            if self.dealer_hidden_card is None:
                self.dealer_hidden_card = drawn_card
                return str(drawn_card)
            else:
                self.deck_queue = [drawn_card] + self.deck_queue
                drawn_card = self.dealer_hidden_card
                self.dealer_hidden_card = None            
            
        suit = drawn_card["suit"]
        value = drawn_card["value"]
        rank = drawn_card["rank"]
            
        self.players[player]["hand"][curr_hand]["card"][card_index] = {}
        self.players[player]["hand"][curr_hand]["card"][card_index]["suit"] = suit
        self.players[player]["hand"][curr_hand]["card"][card_index]["rank"] = rank
        self.players[player]["hand"][curr_hand]["card"][card_index]["value"] = value
        self.players[player]["hand"][curr_hand]["ranks"].append(rank)

        await self.count_hand(player, curr_hand) #to change ace names and values in the "ranks" table, don't actually need the count

        if True:
            hand = []
            for card in list(self.players[player]["hand"][curr_hand]["card"].values()):
                print_rank = card["rank"]
                if print_rank == "small_ace":
                    print_rank = "ace"
                hand.append("data/economy/playing_cards//" + print_rank + "_of_" + card["suit"] + ".png")
            if player is "dealer" and len(hand) == 1:
                hand.append("data/economy/playing_cards/hidden_card.png")

            if len(hand) > 1:
                hand_img = self.merge_image_list(hand)
                await self.bot.upload(hand_img)

        if rank == "small_ace":
            rank = "ace"
        
        self.drawn_queue.append(drawn_card)  
        
        #print(len(self.deck_queue))
        #print(len(self.drawn_queue))
        
        return rank + " of " + suit

    async def count_hand(self, player, curr_hand):
        count = 0
        cards = self.players[player]["hand"][curr_hand]["card"]

        for card in cards:
            count += cards[card]["value"]

        for card in cards:
            if count > 21:
                if cards[card]["value"] == 11:
                    cards[card]["value"] = 1
                    cards[card]["rank"] = "small_ace"
                    count -= 10

                    self.players[player]["hand"][curr_hand]["ranks"] = []
                    for card in self.players[player]["hand"][curr_hand]["card"]:
                        self.players[player]["hand"][curr_hand]["ranks"].append(self.players[player]["hand"][curr_hand]["card"][card]["rank"])
                    break

        return count


    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def blackjackset(self, ctx):
        """Changes blackjack settings"""
        if ctx.invoked_subcommand is None:
            msg = "```"
            for k, v in self.settings.items():
                msg += str(k) + ": " + str(v) + "\n"
            msg += "\nType {}help blackjackset to see the list of commands.```".format(ctx.prefix)
            await self.bot.say(msg)


    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def blackjackdecklist(self, ctx):
        #with (yield from self.draw_lock):
        temp_list = OrderedDict([("ace",0),("2",0),("3",0),("4",0),("5",0),("6",0),("7",0),("8",0),("9",0),("10",0),("jack",0),("queen",0),("king",0)])
        for card in self.deck_queue:
            suit = card["suit"]
            value = card["value"]
            rank = card["rank"]

            temp_list[rank] = temp_list[rank] + 1
        
        output_msg = "Remaining Cards\n"
        for card in temp_list.keys():
            print(card)
            output_msg = output_msg + str(card) + ": " + str(temp_list[card]) + "\n"
        
        await self.bot.say("```"+ output_msg + "```")
        
        temp_list = OrderedDict([("ace",0),("2",0),("3",0),("4",0),("5",0),("6",0),("7",0),("8",0),("9",0),("10",0),("jack",0),("queen",0),("king",0)])
        for card in self.drawn_queue:
            suit = card["suit"]
            value = card["value"]
            rank = card["rank"]

            temp_list[rank] = temp_list[rank] + 1
                
        output_msg = "Drawn Cards\n"
        for card in temp_list.keys():
            if temp_list[card] > 0:
                output_msg = output_msg + str(card) + ": " + str(temp_list[card]) + "\n"
        
        await self.bot.say("```"+ output_msg + "```")
            
    @blackjackset.command()
    async def blackjackmin(self, bet : int):
        """Minimum blackjack bet"""
        self.settings["BLACKJACK_MIN"] = bet
        await self.bot.say("Minimum bet is now " + str(bet) + " credits.")
        self._save_settings()

    @blackjackset.command()
    async def blackjackmax(self, bet : int):
        """Maximum blackjack bet"""
        self.settings["BLACKJACK_MAX"] = bet
        await self.bot.say("Maximum bet is now " + str(bet) + " credits.")
        self._save_settings()

    @blackjackset.command()
    async def blackjackmaxtoggle(self):
        """Toggle the use of a maximum blackjack bet"""
        self.settings["BLACKJACK_MAX_ENABLED"] = not self.settings["BLACKJACK_MAX_ENABLED"]
        if self.settings["BLACKJACK_MAX_ENABLED"]:
            await self.bot.say("Maximum bet is now enabled.")
        else:
            await self.bot.say("Maximum bet is now disabled.")

        self._save_settings()

    @blackjackset.command()
    async def blackjackpretime(self, time : int):
        """Set the pregame time for players to bet"""
        self.settings["BLACKJACK_PRE_GAME_TIME"] = time
        await self.bot.say("Blackjack pre-game time is now " + str(time))
        self._save_settings()

    @blackjackset.command()
    async def blackjacktime(self, time : int):
        """Set the maximum game time given to hit"""
        self.settings["BLACKJACK_GAME_TIME"] = time
        await self.bot.say("Blackjack maximum game time is now " + str(time))
        self._save_settings()

    @blackjackset.command()
    async def blackjackimagestoggle(self):
        """Toggle the use of card images"""
        self.settings["BLACKJACK_IMAGES_ENABLED"] = not self.settings["BLACKJACK_IMAGES_ENABLED"]
        if self.settings["BLACKJACK_IMAGES_ENABLED"]:
            await self.bot.say("Card images are now enabled.")
        else:
            await self.bot.say("Card images are now disabled.")

        self._save_settings()
    
    @blackjackset.command()
    async def paydaytime(self, seconds : int):
        """Seconds between each payday"""
        self.settings["PAYDAY_TIME"] = seconds
        await self.bot.say("Value modified. At least " + str(seconds) + " seconds must pass between each payday.")
        self._save_settings()

    @blackjackset.command()
    async def paydaycredits(self, credits : int):
        """Credits earned each payday"""
        self.settings["PAYDAY_CREDITS"] = credits
        await self.bot.say("Every payday will now give " + str(credits) + " credits.")
        self._save_settings()   
    

    @commands.command()
    async def payouts(self):
        """Shows slot machine payouts"""
        await self.bot.whisper(SLOT_PAYOUTS_MSG)


    @commands.command(pass_context=True, no_pm=True)
    async def slot(self, ctx, bid: int):
        """Play the slot machine"""
        author = ctx.message.author
        server = author.server
        settings = self.settings[server.id]
        valid_bid = settings["SLOT_MIN"] <= bid and bid <= settings["SLOT_MAX"]
        slot_time = settings["SLOT_TIME"]
        last_slot = self.slot_register.get(author.id)
        now = datetime.utcnow()
        try:
            if last_slot:
                if (now - last_slot).seconds < slot_time:
                    raise OnCooldown()
            if not valid_bid:
                raise InvalidBid()
            if not self.bank.can_spend(author, bid):
                raise InsufficientBalance
            await self.slot_machine(author, bid)
        except NoAccount:
            await self.bot.say("{} You need an account to use the slot "
                               "machine. Type `{}bank register` to open one."
                               "".format(author.mention, ctx.prefix))
        except InsufficientBalance:
            await self.bot.say("{} You need an account with enough funds to "
                               "play the slot machine.".format(author.mention))
        except OnCooldown:
            await self.bot.say("Slot machine is still cooling off! Wait {} "
                               "seconds between each pull".format(slot_time))
        except InvalidBid:
            await self.bot.say("Bid must be between {} and {}."
                               "".format(settings["SLOT_MIN"],
                                         settings["SLOT_MAX"]))

    async def slot_machine(self, author, bid):
        default_reel = deque(SMReel)
        reels = []
        self.slot_register[author.id] = datetime.utcnow()
        for i in range(3):
            default_reel.rotate(random.randint(-999, 999)) # weeeeee
            new_reel = deque(default_reel, maxlen=3) # we need only 3 symbols
            reels.append(new_reel)                   # for each reel
        rows = ((reels[0][0], reels[1][0], reels[2][0]),
                (reels[0][1], reels[1][1], reels[2][1]),
                (reels[0][2], reels[1][2], reels[2][2]))

        slot = "~~\n~~" # Mobile friendly
        for i, row in enumerate(rows): # Let's build the slot to show
            sign = "  "
            if i == 1:
                sign = ">"
            slot += "{}{} {} {}\n".format(sign, *[c.value for c in row])

        payout = PAYOUTS.get(rows[1])
        if not payout:
            # Checks for two-consecutive-symbols special rewards
            payout = PAYOUTS.get((rows[1][0], rows[1][1]),
                     PAYOUTS.get((rows[1][1], rows[1][2]))
                                )
        if not payout:
            # Still nothing. Let's check for 3 generic same symbols
            # or 2 consecutive symbols
            has_three = rows[1][0] == rows[1][1] == rows[1][2]
            has_two = (rows[1][0] == rows[1][1]) or (rows[1][1] == rows[1][2])
            if has_three:
                payout = PAYOUTS["3 symbols"]
            elif has_two:
                payout = PAYOUTS["2 symbols"]

        if payout:
            then = self.bank.get_balance(author)
            pay = payout["payout"](bid)
            now = then - bid + pay
            self.bank.set_credits(author, now)
            await self.bot.say("{}\n{} {}\n\nYour bid: {}\n{} → {}!"
                               "".format(slot, author.mention,
                                         payout["phrase"], bid, then, now))
        else:
            then = self.bank.get_balance(author)
            self.bank.withdraw_credits(author, bid)
            now = then - bid
            await self.bot.say("{}\n{} Nothing!\nYour bid: {}\n{} → {}!"
                               "".format(slot, author.mention, bid, then, now))

    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def economyset(self, ctx):
        """Changes economy module settings"""
        server = ctx.message.server
        settings = self.settings[server.id]
        if ctx.invoked_subcommand is None:
            msg = "```"
            for k, v in settings.items():
                msg += "{}: {}\n".format(k, v)
            msg += "```"
            await send_cmd_help(ctx)
            await self.bot.say(msg)

    @economyset.command(pass_context=True)
    async def slotmin(self, ctx, bid: int):
        """Minimum slot machine bid"""
        server = ctx.message.server
        self.settings[server.id]["SLOT_MIN"] = bid
        await self.bot.say("Minimum bid is now {} credits.".format(bid))
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def slotmax(self, ctx, bid: int):
        """Maximum slot machine bid"""
        server = ctx.message.server
        self.settings[server.id]["SLOT_MAX"] = bid
        await self.bot.say("Maximum bid is now {} credits.".format(bid))
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def slottime(self, ctx, seconds: int):
        """Seconds between each slots use"""
        server = ctx.message.server
        self.settings[server.id]["SLOT_TIME"] = seconds
        await self.bot.say("Cooldown is now {} seconds.".format(seconds))
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def paydaytime(self, ctx, seconds: int):
        """Seconds between each payday"""
        server = ctx.message.server
        self.settings[server.id]["PAYDAY_TIME"] = seconds
        await self.bot.say("Value modified. At least {} seconds must pass "
                           "between each payday.".format(seconds))
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def paydaycredits(self, ctx, credits: int):
        """Credits earned each payday"""
        server = ctx.message.server
        self.settings[server.id]["PAYDAY_CREDITS"] = credits
        await self.bot.say("Every payday will now give {} credits."
                           "".format(credits))
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def registercredits(self, ctx, credits: int):
        """Credits given on registering an account"""
        server = ctx.message.server
        if credits < 0:
            credits = 0
        self.settings[server.id]["REGISTER_CREDITS"] = credits
        await self.bot.say("Registering an account will now give {} credits."
                           "".format(credits))
        dataIO.save_json(self.file_path, self.settings)

    # What would I ever do without stackoverflow?
    def display_time(self, seconds, granularity=2):
        intervals = (  # Source: http://stackoverflow.com/a/24542445
            ('weeks', 604800),  # 60 * 60 * 24 * 7
            ('days', 86400),    # 60 * 60 * 24
            ('hours', 3600),    # 60 * 60
            ('minutes', 60),
            ('seconds', 1),
        )

        result = []

        for name, count in intervals:
            value = seconds // count
            if value:
                seconds -= value * count
                if value == 1:
                    name = name.rstrip('s')
                result.append("{} {}".format(value, name))
        return ', '.join(result[:granularity])

    def merge_image_list(self, img_list):
        images = list(map(Image.open, img_list))
        widths, heights = zip(*(i.size for i in images))

        total_width = sum(widths)
        max_height = max(heights)

        new_im = Image.new('RGB', (total_width, max_height))

        x_offset = 0
        for im in images:
            new_im.paste(im, (x_offset,0))
            x_offset += im.size[0]

        new_im.save('data/economy/playing_cards/output.png')
        return 'data/economy/playing_cards/output.png'
        
    def shuffle_deck(self):
        
        #with yield from self.draw_lock:
        for i in range(0, len(self.deck_queue)):
            self.drawn_queue.append(self.deck_queue[i])
            
            del self.deck_queue[i]
        
        for i in range(0, len(self.drawn_queue)):
            randIndex = randint(0, len(self.drawn_queue)-1)
            
            self.deck_queue.append(self.drawn_queue[randIndex])
            
            del self.drawn_queue[randIndex]
        

def check_folders():
    if not os.path.exists("data/economy"):
        print("Creating data/economy folder...")
        os.makedirs("data/economy")


def check_files():
    settings = {
        "BLACKJACK_MIN" : 10,
        "BLACKJACK_MAX" : 5000,
        "BLACKJACK_MAX_ENABLED" : False,
        "BLACKJACK_GAME_TIME" : 60,
        "BLACKJACK_PRE_GAME_TIME" : 15,
        "BLACKJACK_IMAGES_ENABLED" : False
    }
    f = "data/economy/settings.json"
    if not dataIO.is_valid_json(f):
        print("Creating default economy's settings.json...")
        dataIO.save_json(f, {})

    f = "data/economy/bank.json"
    if not dataIO.is_valid_json(f):
        print("Creating empty bank.json...")
        dataIO.save_json(f, {})


def setup(bot):
    global logger
    check_folders()
    check_files()
    logger = logging.getLogger("red.economy")
    if logger.level == 0:
        # Prevents the logger from being loaded again in case of module reload
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(
            filename='data/economy/economy.log', encoding='utf-8', mode='a')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(message)s', datefmt="[%d/%m/%Y %H:%M]"))
        logger.addHandler(handler)
    bot.add_cog(Economy(bot))
