from discord.ext import commands
from random import choice
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
import logging
import collections
import discord
import time
import copy
import os
import asyncio
import uuid
import chardet
import re
from gtts import gTTS
from enum import Enum

log = logging.getLogger("red.tts")

available_languages = { 'af' : 'Afrikaans', 
                        'sq' : 'Albanian', 
                        'ar' : 'Arabic',
                        'hy' : 'Armenian', 
                        'bn' : 'Bengali', 
                        'ca' : 'Catalan', 
                        'zh' : 'Chinese', 
                        'zh-cn' : 'Chinese (Mandarin/China)', 
                        'zh-tw' : 'Chinese (Mandarin/Taiwan)', 
                        'zh-yue' : 'Chinese (Cantonese)', 
                        'hr' : 'Croatian', 
                        'cs' : 'Czech', 
                        'da' : 'Danish', 
                        'nl' : 'Dutch', 
                        'en' : 'English', 
                        'en-au' : 'English (Australia)', 
                        'en-uk' : 'English (United Kingdom)',
                        'en-us' : 'English (United States)', 
                        'eo' : 'Esperanto', 
                        'fi' : 'Finnish', 
                        'fr' : 'French', 
                        'de' : 'German', 
                        'el' : 'Greek', 
                        'hi' : 'Hindi', 
                        'hu' : 'Hungarian', 
                        'is' : 'Icelandic', 
                        'id' : 'Indonesian', 
                        'it' : 'Italian', 
                        'ja' : 'Japanese',
                        'km' : 'Khmer (Cambodian)', 
                        'ko' : 'Korean', 
                        'la' : 'Latin', 
                        'lv' : 'Latvian', 
                        'mk' : 'Macedonian', 
                        'no' : 'Norwegian', 
                        'pl' : 'Polish', 
                        'pt' : 'Portuguese', 
                        'ro' : 'Romanian', 
                        'ru' : 'Russian', 
                        'sr' : 'Serbian', 
                        'si' : 'Sinhala', 
                        'sk' : 'Slovak', 
                        'es' : 'Spanish', 
                        'es-es' : 'Spanish (Spain)', 
                        'es-us' : 'Spanish (United States)', 
                        'sw' : 'Swahili', 
                        'sv' : 'Swedish', 
                        'ta' : 'Tamil', 
                        'th' : 'Thai', 
                        'tr' : 'Turkish', 
                        'uk' : 'Ukrainian', 
                        'vi' : 'Vietnamese', 
                        'cy' : 'Welsh' }

class QueueKey(Enum):
    REPEAT = 1
    PLAYLIST = 2
    VOICE_CHANNEL_ID = 3
    QUEUE = 4
    TEMP_QUEUE = 5
    NOW_PLAYING = 6
    NOW_PLAYING_CHANNEL = 7
    LAST_MESSAGE_USER = 8
    TSS_ENABLED = 9
    TTS_LANGUAGE = 10
    SB_ENABLED = 11

class TextToSpeech:
    """General commands."""
    def __init__(self, bot):
        self.bot = bot
        self.local_playlist_path = "data/tts"
        self.local_soundboard_settings = "data/soundboard/sb_settings.json"
        self.connect_timers = {}
        self.queue = {}
        self.remove_queue = deque()
        self.user_list = deque()
        self.mp3_remove_all()

    async def on_message(self, message):

        if message.channel.is_private:
            return
            
        server = message.server
        sid = server.id
        message_content = message.content

        if server.id not in self.queue:
            self._setup_queue(server)
     
        if not self.queue[sid][QueueKey.TSS_ENABLED]:
            return

        #print(self.queue[sid][QueueKey.TSS_ENABLED])
     

        print(message.clean_content)
            
        for member in message.mentions:
            message_content = message_content.replace(str(member.id), member.name).replace("<@", "").replace(">", "")
        for role in message.role_mentions:
            message_content = message_content.replace(str(role.id), role.name).replace("<@", "").replace(">", "")
            message_content = message_content.replace(str(channel.id), channel.name).replace("<@", "").replace(">", "")
            
        if self.queue[sid][QueueKey.TSS_ENABLED] and not message.tts and not message.author.bot:
            for text in self._tokenize(message_content, 10):
                print(text)
               
                if text.strip() != "":
                    if self.queue[server.id][QueueKey.LAST_MESSAGE_USER] == message.author.id:
                        self.queue[sid][QueueKey.QUEUE].append(text.strip())
                    else:
                        username = message.author.name
                        self.queue[sid][QueueKey.QUEUE].append(username + " says: " + text.strip())
                        self.queue[server.id][QueueKey.LAST_MESSAGE_USER] = message.author.id
                    
    def _tokenize(self, text, max_size):
        """ Tokenizer on basic punctuation """
        
        punc = "¡!()[]¿?.,،;:—。、：？！\n"
        punc_list = [re.escape(c) for c in punc]
        pattern = '|'.join(punc_list)
        parts = re.split(pattern, text)

        return parts
                    
    @commands.group(pass_context=True, no_pm=True)
    async def happybirthday(self, ctx):
        sid = ctx.message.server.id
        self.queue[sid][QueueKey.QUEUE].append("Happy brithday to you! Happy birthday to you! Happybirthday dear Ricky Leek. Happy Birthday to you!")
    
    @commands.group(pass_context=True, no_pm=True)
    async def sb(self, ctx, sound):
        print(ctx.invoked_subcommand)
        if sound is not None:
            server = ctx.message.server
            if sound == "on":
                await self.sb_on(ctx)
            elif sound == "off":
                await self.sb_off(ctx)
            else:
                if self.queue[server.id][QueueKey.SB_ENABLED]:
                    print(sound)
                    msg = sound
                    self.local_soundboard_settings
                    current = dataIO.load_json(self.local_soundboard_settings)
                    if sound in current.keys():
                        msg = msg + " exists"
                        self.queue[server.id][QueueKey.TEMP_QUEUE].append("data/soundboard/"+current[sound])
                    await self.bot.say(msg)
        else:
            msg = box("Useage: sb <sound>")
            await self.bot.say(msg)
            
    async def sb_on(self, ctx):
        """Turn on TextToSpeech"""
        server = ctx.message.server
        author = ctx.message.author
        voice_channel = author.voice_channel
        
        if server.id not in self.queue:
            self._setup_queue(server)
        
        if self.is_playing(server) and self.queue[server.id][QueueKey.TSS_ENABLED]:
            #await ctx.invoke(self._queue, url=url)
            self._stop(server)
            if self.queue[server.id][QueueKey.TSS_ENABLED]:
                self.queue[server.id][QueueKey.TSS_ENABLED] = False
            self.queue[server.id][QueueKey.SB_ENABLED] = True
            msg = box("SoundBoard Enabled")
            await self.bot.say(msg)
            return  # Default to queue
        
                # Checking already connected, will join if not

        try:
            self.has_connect_perm(author, server)
        except AuthorNotConnected:
            await self.bot.say("You must join a voice channel before I can"
                               " play anything.")
            return
        except UnauthorizedConnect:
            await self.bot.say("I don't have permissions to join your"
                               " voice channel.")
            return
        except UnauthorizedSpeak:
            await self.bot.say("I don't have permissions to speak in your"
                               " voice channel.")
            return
        except ChannelUserLimit:
            await self.bot.say("Your voice channel is full.")
            return

        if not self.voice_connected(server):
            await self._join_voice_channel(voice_channel)
        else:  # We are connected but not to the right channel
            if self.voice_client(server).channel != voice_channel:
                await self._stop_and_disconnect(server)
                await self._join_voice_channel(voice_channel)
        
        msg = box("SoundBoard Enabled")
        await self.bot.say(msg)
        if self.queue[server.id][QueueKey.TSS_ENABLED]:
            self.queue[server.id][QueueKey.TSS_ENABLED] = False
        self.queue[server.id][QueueKey.SB_ENABLED] = True    
        
    async def sb_off(self, ctx):
        """Turn off TextToSpeech"""
        server = ctx.message.server
        
        if server.id not in self.queue:
            self._setup_queue(server)
        await self._stop_and_disconnect(server)
        msg = box("SoundBoard Disabled")
        self.queue[server.id][QueueKey.SB_ENABLED] = False
        await self.bot.say(msg)
        
    @commands.group(pass_context=True, no_pm=True)
    async def tts(self, ctx):
        """Gives the current status of TextToSpeech"""
        if ctx.invoked_subcommand is None:
            server = ctx.message.server
            if self.queue[server.id][QueueKey.TSS_ENABLED]:
                msg = box("TextToSpeech is currently enabled")
            else:
                msg = box("TextToSpeech is currently disabled")
            await self.bot.say(msg)

    @tts.command(pass_context=True)
    async def language(self, ctx):
        server = ctx.message.server
        language = re.search(r'\!tts language (.+)',ctx.message.content).group(1)
        msg = ""
        if language is None:
            return
        elif language == 'list':
            msg = "Available Languages: \n"
            for key, value in available_languages.items():
                msg = msg + key + " : " + value + "\n"

        if server.id not in self.queue:
            self._setup_queue(server)

        if language in available_languages:
            self.queue[server.id][QueueKey.TTS_LANGUAGE] = language
            msg = "Language switched to " + available_languages[language] + "."

        await self.bot.say(msg)
            
    @tts.command(pass_context=True)
    async def off(self, ctx):
        """Turn off TextToSpeech"""
        server = ctx.message.server
        
        if server.id not in self.queue:
            self._setup_queue(server)
        await self._stop_and_disconnect(server)
        msg = box("TextToSpeech Disabled")
        self.queue[server.id][QueueKey.TSS_ENABLED] = False
        await self.bot.say(msg)
        
    @tts.command(pass_context=True)
    async def on(self, ctx):
        """Turn on TextToSpeech"""
        server = ctx.message.server
        author = ctx.message.author
        voice_channel = author.voice_channel
        
        if server.id not in self.queue:
            self._setup_queue(server)
        
        if self.is_playing(server) and self.queue[server.id][QueueKey.SB_ENABLED]:
            #await ctx.invoke(self._queue, url=url)
            self._stop(server)
            if self.queue[server.id][QueueKey.SB_ENABLED]:
                self.queue[server.id][QueueKey.SB_ENABLED] = False
            self.queue[server.id][QueueKey.TSS_ENABLED] = True
            msg = box("TextToSpeech Enabled")
            await self.bot.say(msg)
            return  # Default to queue
        
                # Checking already connected, will join if not

        try:
            self.has_connect_perm(author, server)
        except AuthorNotConnected:
            await self.bot.say("You must join a voice channel before I can"
                               " play anything.")
            return
        except UnauthorizedConnect:
            await self.bot.say("I don't have permissions to join your"
                               " voice channel.")
            return
        except UnauthorizedSpeak:
            await self.bot.say("I don't have permissions to speak in your"
                               " voice channel.")
            return
        except ChannelUserLimit:
            await self.bot.say("Your voice channel is full.")
            return

        if not self.voice_connected(server):
            await self._join_voice_channel(voice_channel)
        else:  # We are connected but not to the right channel
            if self.voice_client(server).channel != voice_channel:
                await self._stop_and_disconnect(server)
                await self._join_voice_channel(voice_channel)
        
        msg = box("TextToSpeech Enabled")
        await self.bot.say(msg)
        self.queue[server.id][QueueKey.TSS_ENABLED] = True

#    @commands.command(pass_context=True, no_pm=True)
#    async def connect(self, ctx, *, url_or_search_terms):
    
    def is_playing(self, server):
        if not self.voice_connected(server):
            return False
        if self.voice_client(server) is None:
            return False
        if not hasattr(self.voice_client(server), 'audio_player'):
            return False
        if self.voice_client(server).audio_player.is_done():
            return False
        return True
        
    def has_connect_perm(self, author, server):
        channel = author.voice_channel

        if channel:
            is_admin = channel.permissions_for(server.me).administrator
            if channel.user_limit == 0:
                is_full = False
            else:
                is_full = len(channel.voice_members) >= channel.user_limit

        if channel is None:
            raise AuthorNotConnected
        elif channel.permissions_for(server.me).connect is False:
            raise UnauthorizedConnect
        elif channel.permissions_for(server.me).speak is False:
            raise UnauthorizedSpeak
        elif is_full and not is_admin:
            raise ChannelUserLimit
        else:
            return True
        return False
        
    def voice_connected(self, server):
        if self.bot.is_voice_connected(server):
            return True
        return False
        
    def _setup_queue(self, server):
        self.queue[server.id] = {QueueKey.REPEAT: False, QueueKey.PLAYLIST: False,
                                 QueueKey.VOICE_CHANNEL_ID: None,
                                 QueueKey.QUEUE: deque(), QueueKey.TEMP_QUEUE: deque(),
                                 QueueKey.NOW_PLAYING: None, QueueKey.NOW_PLAYING_CHANNEL: None,
                                 QueueKey.LAST_MESSAGE_USER: "",
                                 QueueKey.TSS_ENABLED: False,
                                 QueueKey.LAST_MESSAGE_USER: 0,
                                 QueueKey.TTS_LANGUAGE: "en",
                                 QueueKey.SB_ENABLED: False}


        
    async def _join_voice_channel(self, channel):
        server = channel.server
        connect_time = self.connect_timers.get(server.id, 0)
        if time.time() < connect_time:
            diff = int(connect_time - time.time())
            raise ConnectTimeout("You are on connect cooldown for another {}"
                                 " seconds.".format(diff))
        if server.id in self.queue:
            self.queue[server.id][QueueKey.VOICE_CHANNEL_ID] = channel.id
        try:
            await asyncio.wait_for(self.bot.join_voice_channel(channel),
                                   timeout=5, loop=self.bot.loop)
        except asyncio.futures.TimeoutError as e:
            log.exception(e)
            self.connect_timers[server.id] = time.time() + 300
            raise ConnectTimeout("We timed out connecting to a voice channel,"
                                 " please try again in 10 minutes.")
    
    async def _disconnect_voice_client(self, server):
        if not self.voice_connected(server):
            return

        voice_client = self.voice_client(server)

        await voice_client.disconnect()
        
    def _stop_player(self, server):
        if not self.voice_connected(server):
            return

        voice_client = self.voice_client(server)

        if hasattr(voice_client, 'audio_player'):
            voice_client.audio_player.stop()
            
#    def _stop_downloader(self, server):
#        if server.id not in self.downloaders:
#            return
#
#        del self.downloaders[server.id]
        
    def _stop(self, server):
        self._setup_queue(server)
        self._stop_player(server)
        #self._stop_downloader(server)
        #self.bot.loop.create_task(self._update_bot_status())
    
    async def _stop_and_disconnect(self, server):
        self._stop(server)
        await self._disconnect_voice_client(server)
        
    def voice_client(self, server):
        return self.bot.voice_client_in(server)
        
    async def _create_ffmpeg_player(self, server, filename, local=False, start_time=None, end_time=None):
        """This function will guarantee we have a valid voice client,
            even if one doesn't exist previously."""
        voice_channel_id = self.queue[server.id][QueueKey.VOICE_CHANNEL_ID]
        voice_client = self.voice_client(server)

        if voice_client is None:
            log.debug("not connected when we should be in sid {}".format(
                server.id))
            to_connect = self.bot.get_channel(voice_channel_id)
            if to_connect is None:
                raise VoiceNotConnected("Okay somehow we're not connected and"
                                        " we have no valid channel to"
                                        " reconnect to. In other words...LOL"
                                        " REKT.")
            log.debug("valid reconnect channel for sid"
                      " {}, reconnecting...".format(server.id))
            await self._join_voice_channel(to_connect)  # SHIT
        elif voice_client.channel.id != voice_channel_id:
            # This was decided at 3:45 EST in #advanced-testing by 26
            self.queue[server.id][QueueKey.VOICE_CHANNEL_ID] = voice_client.channel.id
            log.debug("reconnect chan id for sid {} is wrong, fixing".format(
                server.id))

        # Okay if we reach here we definitively have a working voice_client

        if local:
            song_filename = filename
        else:
            song_filename = os.path.join(self.cache_path, filename)

        use_avconv = True#self.settings["AVCONV"]
        options = '-b:a 64k -bufsize 64k'
        before_options = ''

        if start_time:
            before_options += '-ss {}'.format(start_time)
        if end_time:
            options += ' -to {} -copyts'.format(end_time)

        try:
            voice_client.audio_player.process.kill()
            log.debug("killed old player")
        except AttributeError:
            pass
        except ProcessLookupError:
            pass

        log.debug("making player on sid {}".format(server.id))
        #print(voice_client)
        voice_client.audio_player = voice_client.create_ffmpeg_player(
            song_filename, use_avconv=use_avconv, options=options, before_options=before_options)

        # Set initial volume
        vol = 50/100#self.get_server_settings(server)['VOLUME'] / 100
        voice_client.audio_player.volume = vol

        return voice_client  # Just for ease of use, it's modified in-place

    async def gTTS_queue_manager(self, sid):
        server = self.bot.get_server(sid)
        queue = self.queue[server.id][QueueKey.QUEUE]
        assert queue is self.queue[server.id][QueueKey.QUEUE]
        
        
        ttsMessage = queue.popleft()
        tts = gTTS(text=ttsMessage, lang=self.queue[server.id][QueueKey.TTS_LANGUAGE], slow=False)
        unique_filename = str(uuid.uuid4()) + ".mp3"
        ttsFileName = os.path.join(self.local_playlist_path, unique_filename)
        tts.save(ttsFileName)
            
        self.queue[server.id][QueueKey.TEMP_QUEUE].append(ttsFileName)

    async def gTTS_queue_scheduler(self):
        while self == self.bot.get_cog('TextToSpeech'):
            tasks = []
            queue = copy.deepcopy(self.queue)
            for sid in queue:
                #print("gTTS:  " + str(queue[sid][QueueKey.QUEUE]))
                if len(queue[sid][QueueKey.QUEUE]) == 0:
                    continue
                # log.debug("scheduler found a non-empty queue"
                #           " for sid: {}".format(sid))
                tasks.append(
                    self.bot.loop.create_task(self.gTTS_queue_manager(sid)))
            completed = [t.done() for t in tasks]
            while not all(completed):
                completed = [t.done() for t in tasks]
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.1)
            
    async def voice_queue_manager(self, sid):
        server = self.bot.get_server(sid)
        queue = self.queue[server.id][QueueKey.TEMP_QUEUE]
        assert queue is self.queue[server.id][QueueKey.TEMP_QUEUE]
        
        if not self.is_playing(server) and (self.queue[server.id][QueueKey.TSS_ENABLED] or self.queue[server.id][QueueKey.SB_ENABLED]):
            if self.voice_client(server) is None:
                return

            filename = queue.popleft()
            #print("pop " + filename) 

            voice_client = await self._create_ffmpeg_player(server, filename, local=True, start_time=None, end_time=None)
            #print("create voice client")
            voice_client.audio_player.start()
            #print("start voice client")
            self.remove_queue.append(filename)
            #os.remove(os.path.join(self.local_playlist_path, filename))

    async def voice_queue_scheduler(self):
        while self == self.bot.get_cog('TextToSpeech'):
            tasks = []
            queue = copy.deepcopy(self.queue)
            for sid in queue:
                #print("voice: " + str(queue[sid][QueueKey.TEMP_QUEUE]))
                if len(queue[sid][QueueKey.TEMP_QUEUE]) == 0:
                    self.mp3_cleanup()
                    continue
                # log.debug("scheduler found a non-empty queue"
                #           " for sid: {}".format(sid))
                tasks.append(
                    self.bot.loop.create_task(self.voice_queue_manager(sid)))
            completed = [t.done() for t in tasks]
            while not all(completed):
                completed = [t.done() for t in tasks]
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.1)
            
    def mp3_cleanup(self):
        if len(self.remove_queue) > 0:
            file_to_remove = self.remove_queue.popleft()
            if self.local_playlist_path in file_to_remove:
                os.remove(file_to_remove)

    def mp3_remove_all(self):
        for file in os.listdir(self.local_playlist_path):
            if file.endswith(".mp3"):
                os.remove(os.path.join(self.local_playlist_path, file))
                
    async def disconnect_timer(self):
        stop_times = {}
        while self == self.bot.get_cog('TextToSpeech'):
            for vc in list(self.bot.voice_clients):
                server = vc.server
                #print(vc.channel.voice_members)
                if len(vc.channel.voice_members) == 1:
                    await self._stop_and_disconnect(server)
            await asyncio.sleep(5)

        
class deque(collections.deque):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def peek(self):
        ret = self.pop()
        self.append(ret)
        return copy.deepcopy(ret)

    def peekleft(self):
        ret = self.popleft()
        self.appendleft(ret)
        return copy.deepcopy(ret)
                                 
class NotConnected(Exception):
    pass
        
class AuthorNotConnected(NotConnected):
    pass

class UnauthorizedConnect(Exception):
    pass    
    
class UnauthorizedSpeak(Exception):
    pass
    
class ChannelUserLimit(Exception):
    pass   
    
class ConnectTimeout(NotConnected):
    pass
  
def check_folders():
    folders = ("data", "data/tts", "data/soundboard")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)
            
def check_files():
    default = {"sample": "sample.mp3"}
    data_path = "data/soundboard/"
    settings_path = "data/soundboard/sb_settings.json"
    if not os.path.isfile(settings_path):
        print("Creating default audio settings.json...")
        dataIO.save_json(settings_path, default)
    else:  # consistency check
        try:
            current = dataIO.load_json(settings_path)
        except JSONDecodeError:
            # settings.json keeps getting corrupted for unknown reasons. Let's
            # try to keep it from making the cog load fail.
            dataIO.save_json(settings_path, default)
            current = dataIO.load_json(settings_path)
            
        if current.keys() != default.keys():
            for key in list(current.keys()):
                mp3_file = data_path + current[key]
                
                if not os.path.isfile(mp3_file):
                    print(mp3_file + " does not exist! Removing from list.")
                    current.pop(key)
                    
            dataIO.save_json(settings_path, current)
        
def setup(bot):
    n = TextToSpeech(bot)
    check_folders()
    check_files()
    bot.add_cog(n)
    bot.loop.create_task(n.gTTS_queue_scheduler())
    bot.loop.create_task(n.disconnect_timer())
    bot.loop.create_task(n.voice_queue_scheduler())    
