#256064
import discord
from discord.guild import Guild
from discord.utils import get
from discord import FFmpegPCMAudio
import youtube_dl
import asyncio
from functools import partial
from async_timeout import timeout
from discord.ext import commands
import itertools

import os
from dotenv import load_dotenv  # มีไว้แอบ token ครับ 4 บรรทัดนี้ ไม่งั้นเดี๋ยวมันไม่ให้ผมเอาโค้ดลง github
load_dotenv()
token = os.getenv('TOKEN')

bot = commands.Bot(command_prefix='%',help_command=None)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5" ## song will end if no this line
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')

        # YTDL info dicts (data) have other useful information you might want
        # https://github.com/rg3/youtube-dl/blob/master/README.md

    def __getitem__(self, item: str):
        """Allows us to access attributes similar to a dict.
        This is only useful when you are NOT downloading.
        """
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        await ctx.send(f'```ini\n[Added {data["title"]} to the Queue.]\n```') #delete after can be added

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source, **ffmpeg_options), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data, requester=requester)

class MusicPlayer:
    """A class which is assigned to each guild using the bot for Music.
    This class implements a queue and loop, which allows for different guilds to listen to different playlists
    simultaneously.
    When the bot disconnects from the Voice it's instance will be destroyed.
    """

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None  # Now playing message
        self.volume = .5
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Our main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Wait for the next song. If we timeout cancel the player and disconnect...
                async with timeout(300):  # 5 minutes...
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                del players[self._guild]
                return await self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                # Source was probably a stream (not downloaded)
                # So we should regather to prevent stream expiration
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'There was an error processing your song.\n'
                                             f'```css\n[{e}]\n```')
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            self.np = await self._channel.send(f'**Now Playing:** `{source.title}` requested by '
                                               f'`{source.requester}`')
            await self.next.wait()

            # Make sure the FFmpeg process is cleaned up.
            source.cleanup()
            self.current = None

            try:
                # We are no longer playing this song...
                await self.np.delete()
            except discord.HTTPException:
                pass

    async def destroy(self, guild):
        """Disconnect and cleanup the player."""
        del players[self._guild]
        await self._guild.voice_client.disconnect()
        return self.bot.loop.create_task(self._cog.cleanup(guild))

@bot.event
async def on_ready():
    print(f"discord-bot raedy as {bot.user}")

@bot.command()
async def test(ctx,*,arg):
    await ctx.channel.send("you type {0}".format(arg))

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="bot help",description="ALL command in discord bot Use # and follow the command below.",color=0x66ccff)
    embed.add_field(name="joine",value="get bot connect to channel.",inline=False)
    embed.add_field(name="test",value="resporne message to you're send.",inline=False)
    embed.add_field(name="add",value="add intiger two number.",inline=False)
    embed.add_field(name="play <name>",value="play music at your url.",inline=False)
    embed.add_field(name="exit",value="Bot disconnect.",inline=False)
    embed.add_field(name="skip",value="next music in queues.",inline=False)
    embed.add_field(name="queuelist",value="show list music in queues.",inline=False)
    embed.add_field(name="stop",value="stop your music.",inline=False)
    embed.add_field(name="pause",value="pause Your music.",inline=False)
    embed.add_field(name="resume",value="resume your music.",inline=False)
    embed.set_thumbnail(url='https://th.bing.com/th/id/OIP.VMhmzXWZTBA4RukNoMFutAAAAA?w=169&h=180&c=7&r=0&o=5&dpr=1.25&pid=1.7')
    embed.set_footer(text="your help all commands.",
    icon_url='https://th.bing.com/th/id/OIP.VMhmzXWZTBA4RukNoMFutAAAAA?w=169&h=180&c=7&r=0&o=5&dpr=1.25&pid=1.7')
    await ctx.channel.send(embed=embed)

@bot.command()
async def add(ctx,a: int,b:int):
    await ctx.channel.send(a + b)


@bot.event
async def on_message(message):
    if message.content == '#user':
        await message.channel.send('hello ' + str(message.author.name))
    elif message.content == '#logout':
        await bot.logout()
    await bot.process_commands(message)\

@bot.command()
async def play(ctx,*,search: str):
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("joine")
        await channel.connect()
        voice_client = get(bot.voice_clients,guild=ctx.guild)
    
    await ctx.trigger_typing()

    _player = get_player(ctx)
    source = await YTDLSource.create_source(ctx, search, loop=bot.loop, download=False)

    await _player.queue.put(source)


players = {}
def get_player(ctx):
    try:
        player = players[ctx.guild.id]
    except:
        player = MusicPlayer(ctx)
        players[ctx.guild.id] = player
        
    return player


@bot.command()
async def joine(ctx):
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.trigger_typing()
        await ctx.channel.send("{0} Joine".format(bot.user.name))
        await channel.connect()

@bot.command()
async def exit(ctx):
    del players[ctx.guild.id]
    await ctx.trigger_typing()
    await ctx.channel.send("{0} disconnected.".format(bot.user.name))
    await ctx.voice_client.disconnect()

@bot.command()
async def stop(ctx):
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("bot is not connected to VC",deleat_after=10)
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send("the bot is not currency {0}".format(voice_client.channel))
        return

    voice_client.stop()

@bot.command()
async def pause(ctx):
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("bot is not connected to VC",deleat_after=10)
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send("the bot is not currency {0}".format(voice_client.channel))
        return

    voice_client.pause()

@bot.command()
async def resume(ctx):
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("bot is not connected to VC",deleat_after=10)
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send("the bot is not currency {0}".format(voice_client.channel))
        return

    voice_client.resume()

@bot.command()
async def queuelist(ctx):
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("bot is not connected to VC",deleat_after=10)
        return

    player = get_player(ctx)
    if player.queue.empty():
        await ctx.send("no queue songs")

    upcoming = list(itertools.islice(player.queue._queue,0,player.queue.qsize()))
    fmt = '\n'.join(f'**`{_["title"]}`**' for _ in upcoming)
    embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt)
    await ctx.send(embed=embed)

@bot.command()
async def skip(ctx):
    voice_client = get(bot.voice_clients,guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send("bot is not connected to VC",deleat_after=10)
        return

    if voice_client.is_paused():
        pass
    elif not voice_client.is_playing():
        return 
    voice_client.stop()
    await ctx.send(f'**`{ctx.author}`**: Skipped the song!')


bot.run(token)

