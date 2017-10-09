from discord.ext import commands
from random import choice
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
import logging
import collections
import discord
import time
import os
import asyncio
import chardet
import gTTS
from enum import Enum

log = logging.getLogger("red.tts")

class QueueKey(Enum):
	REPEAT = 1
	PLAYLIST = 2
	VOICE_CHANNEL_ID = 3
	QUEUE = 4
	TEMP_QUEUE = 5
	NOW_PLAYING = 6
	NOW_PLAYING_CHANNEL = 7

class TextToSpeech:
    """General commands."""
    def __init__(self, bot):
        self.bot = bot
        self.ttsEnabled = False
        self.local_playlist_path = "data/tts"
        self.connect_timers = {}
        self.queue = {}

    @client.event
    async def on_message(message):
        if self.ttsEnabled:
            print(message)
            tts = gTTS(text=message, lang='en', slow=True)
            ttsFileName = os.path.join(self.local_playlist_path, "tts.mp3")
            tts.save(ttsFileName)
        
    @commands.group(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(administrator=True)
    async def tts(self, ctx):
        """Gives the current status of TextToSpeech"""
        if ctx.invoked_subcommand is None:
            server = ctx.message.server
            if self.ttsEnabled:
                msg = box("TextToSpeech is currently enabled")
                voice_client = await self._create_ffmpeg_player(server, "test.mp4", local=True, start_time=None, end_time=None)

                voice_client.audio_player.start()
            else:
                msg = box("TextToSpeech is currently disabled")
            await self.bot.say(msg)

    @tts.command(pass_context=True)
    async def off(self, ctx):
        """Turn off TextToSpeech"""
        server = ctx.message.server
        
        if server.id not in self.queue:
            self._setup_queue(server)
        await self._stop_and_disconnect(server)
        msg = box("TextToSpeech Disabled")
        self.ttsEnabled = False
        await self.bot.say(msg)
        
    @tts.command(pass_context=True)
    async def on(self, ctx):
        """Turn on TextToSpeech"""
        server = ctx.message.server
        author = ctx.message.author
        voice_channel = author.voice_channel
        
        if server.id not in self.queue:
            self._setup_queue(server)
        
        if self.is_playing(server):
            await ctx.invoke(self._queue, url=url)
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
        self.ttsEnabled = True
        await self.bot.say(msg)

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
                                 QueueKey.NOW_PLAYING: None, QueueKey.NOW_PLAYING_CHANNEL: None}
        
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
            song_filename = os.path.join(self.local_playlist_path, filename)
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

        voice_client.audio_player = voice_client.create_ffmpeg_player(
            song_filename, use_avconv=use_avconv, options=options, before_options=before_options)

        # Set initial volume
        vol = 50/100#self.get_server_settings(server)['VOLUME'] / 100
        voice_client.audio_player.volume = vol

        return voice_client  # Just for ease of use, it's modified in-place

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
    
def setup(bot):
    bot.add_cog(TextToSpeech(bot))
    
    
