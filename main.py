import discord
import os
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- سيرفر وهمي عشان Render يفضل شغال ---
app = Flask('')
@app.route('/')
def home():
    return "I am alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ---------------------------------------

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
    if message.content.lower() in ["خط", "line"]:
        embed = discord.Embed(color=0xffa500)
        embed.set_image(url=LINE_URL)
        await message.channel.send(embed=embed)
        try: await message.delete()
        except: pass

# تشغيل السيرفر الوهمي ثم البوت
keep_alive()
token = os.getenv('DISCORD_TOKEN')
bot.run(token)
