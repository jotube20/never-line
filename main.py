import discord
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

LINE_URL = "https://media.discordapp.net/attachments/1474909829058531335/1475499138350059600/1100196984901599343.gif"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.lower()
    if content == "خط" or content == "line":
        embed = discord.Embed(color=0xffa500)
        embed.set_image(url=LINE_URL)
        await message.channel.send(embed=embed)
        try:
            await message.delete()
        except:
            pass

    await bot.process_commands(message)

# هنا بنخلي البوت يقرأ التوكن من البيئة المحيطة (Environment Variable)
token = os.getenv('DISCORD_TOKEN')
bot.run(token)
