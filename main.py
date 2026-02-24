import discord
import os
import sqlite3
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- إعدادات قاعدة البيانات SQLite ---
conn = sqlite3.connect('targets.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS targets (msg_id INTEGER PRIMARY KEY, user_id INTEGER, target_type TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS rooms (user_id INTEGER PRIMARY KEY, channel_id INTEGER)')
conn.commit()

# --- سيرفر وهمي عشان Render ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"
def run():
    app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- إعدادات البوت ---
intents = discord.Intents.default()
intents.message_content = True
# تم إيقاف أمر help الافتراضي هنا
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

LINE_URL = "https://media.discordapp.net/attachments/1474909829058531335/1475499138350059600/1100196984901599343.gif"
EMBED_COLOR = 0x2b2d31 # لون ديسكورد الداكن الاحترافي

# ==========================================
#              واجهات المستخدم (UI)
# ==========================================

# 1. أزرار التارجت
class TargetView(discord.ui.View):
    def __init__(self, author_id, msg_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.msg_id = msg_id

    async def save_target(self, interaction: discord.Interaction, target_type: str):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("مقدرش أسجل ده، دي مش صورتك!", ephemeral=True)
            return

        try:
            c.execute('INSERT INTO targets (msg_id, user_id, target_type) VALUES (?, ?, ?)', (self.msg_id, self.author_id, target_type))
            conn.commit()
            
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(content=f"تم تسجيل التارجت: **{target_type}** بواسطة {interaction.user.mention}", view=None)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("التارجت ده اتسجل قبل كدة!", ephemeral=True)

    @discord.ui.button(label="دعم (Su)", style=discord.ButtonStyle.primary)
    async def btn_su(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "دعم")

    @discord.ui.button(label="تقديم (Ap)", style=discord.ButtonStyle.success)
    async def btn_ap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "تقديم")

    @discord.ui.button(label="ورن (Wr)", style=discord.ButtonStyle.danger)
    async def btn_wr(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "ورن")

# 2. قائمة المساعدة المنسدلة
class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Owners", description="Owners management commands", value="owners"),
            discord.SelectOption(label="Staff", description="Staff commands", value="staff"),
            discord.SelectOption(label="Public", description="Public commands", value="public"),
            discord.SelectOption(label="Team", description="Team commands", value="team"),
            discord.SelectOption(label="Giveaway", description="Giveaway commands", value="giveaway")
        ]
        super().__init__(placeholder="Select command category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=EMBED_COLOR)
        
        if self.values[0] == "owners":
            embed.title = "Owners Commands"
            embed.description = "أوامر الإدارة العليا."
            embed.add_field(name="!setroom", value="**الاستخدام:** `!setroom @user #channel`\n**الوظيفة:** تحديد الروم المخصصة لإداري لرفع التارجت.", inline=False)
            
        elif self.values[0] == "staff":
            embed.title = "Staff Commands"
            embed.description = "أوامر الإستاف لمتابعة العمل."
            embed.add_field(name="!target", value="**الاستخدام:** `!target` أو `!target @user`\n**الوظيفة:** عرض إحصائيات التارجت.", inline=False)
            
        elif self.values[0] == "public":
            embed.title = "Public Commands"
            embed.description = "الأوامر العامة."
            embed.add_field(name="!ping", value="**الاستخدام:** `!ping`\n**الوظيفة:** معرفة سرعة استجابة البوت.", inline=False)
            embed.add_field(name="خط", value="**الاستخدام:** إرسال كلمة `خط` أو `line`\n**الوظيفة:** إرسال الفاصل الزمني.", inline=False)
            
        elif self.values[0] in ["team", "giveaway"]:
            embed.title = self.values[0].capitalize() + " Commands"
            embed.description = "لا توجد أوامر متاحة حالياً في هذا القسم."

        embed.set_image(url=LINE_URL)
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpSelect())

# ==========================================
#                الأحداث (Events)
# ==========================================

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # كود الخط
    content = message.content.lower()
    if content in ["خط", "line"]:
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_image(url=LINE_URL)
        await message.channel.send(embed=embed)
        try: await message.delete()
        except: pass

    # التحقق من رومات التارجت والصور (النظام الذكي الجديد)
    if message.attachments:
        c.execute('SELECT user_id FROM rooms WHERE channel_id = ?', (message.channel.id,))
        channel_owner = c.fetchone()
        
        if channel_owner: # لو الروم دي متسجلة كروم تارجت لحد معين
            if channel_owner[0] != message.author.id:
                # لو اللي بيبعت مش صاحب الروم
                await message.delete()
                await message.channel.send(f"{message.author.mention} ❌ دي مش روم التارجت بتاعتك!", delete_after=5)
                return
            else:
                # لو صاحب الروم هو اللي بعت، نطلعله الأزرار
                view = TargetView(author_id=message.author.id, msg_id=message.id)
                await message.channel.send("حدد نوع التارجت:", view=view, reference=message)

    await bot.process_commands(message)

# ==========================================
#               الأوامر (Commands)
# ==========================================

@bot.command()
async def help(ctx):
    embed = discord.Embed(color=EMBED_COLOR)
    embed.description = f"Hey: {ctx.author.mention} 👋\n\nI'm: {bot.user.mention}, a custom System bot built specially for the server.\n\nTo get started using this bot, select a category from `Select command category...` 🔽"
    
    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    
    embed.set_image(url=LINE_URL)
    view = HelpView()
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def setroom(ctx, member: discord.Member, channel: discord.TextChannel):
    c.execute('REPLACE INTO rooms (user_id, channel_id) VALUES (?, ?)', (member.id, channel.id))
    conn.commit()
    embed = discord.Embed(description=f"✅ تم تخصيص الروم {channel.mention} للإداري {member.mention}.", color=0x2ecc71)
    await ctx.send(embed=embed)

@bot.command()
async def target(ctx, member: discord.Member = None):
    user = member or ctx.author
    c.execute('SELECT target_type, COUNT(*) FROM targets WHERE user_id = ? GROUP BY target_type', (user.id,))
    results = c.fetchall()
    
    stats = {"دعم": 0, "تقديم": 0, "ورن": 0}
    for row in results:
        stats[row[0]] = row[1]
        
    total = sum(stats.values())
    
    embed = discord.Embed(title=f"إحصائيات {user.display_name}", color=EMBED_COLOR)
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
        
    embed.add_field(name="دعم (Su)", value=f"`{stats['دعم']}`", inline=True)
    embed.add_field(name="تقديم (Ap)", value=f"`{stats['تقديم']}`", inline=True)
    embed.add_field(name="ورن (Wr)", value=f"`{stats['ورن']}`", inline=True)
    embed.add_field(name="الإجمالي", value=f"**{total}**", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(description=f"🏓 Pong! **{latency}ms**", color=EMBED_COLOR)
    await ctx.send(embed=embed)

# تشغيل البوت
keep_alive()
token = os.getenv('DISCORD_TOKEN')
bot.run(token)

