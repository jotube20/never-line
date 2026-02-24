import discord
import os
import sqlite3
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- إعدادات قاعدة البيانات SQLite ---
conn = sqlite3.connect('targets.db', check_same_thread=False)
c = conn.cursor()
# جدول لحفظ التارجت (عشان نمنع التكرار)
c.execute('CREATE TABLE IF NOT EXISTS targets (msg_id INTEGER PRIMARY KEY, user_id INTEGER, target_type TEXT)')
# جدول لربط كل إداري بالروم بتاعته
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
bot = commands.Bot(command_prefix='!', intents=intents)

# --- كلاس الأزرار (Buttons) ---
class TargetView(discord.ui.View):
    def __init__(self, author_id, msg_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.msg_id = msg_id

    async def save_target(self, interaction: discord.Interaction, target_type: str):
        # التأكد إن اللي داس على الزرار هو صاحب الصورة
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ مقدرش أسجل ده، دي مش صورتك!", ephemeral=True)
            return

        # حفظ في قاعدة البيانات
        try:
            c.execute('INSERT INTO targets (msg_id, user_id, target_type) VALUES (?, ?, ?)', (self.msg_id, self.author_id, target_type))
            conn.commit()
            
            # مسح الزراير بعد الاختيار وكتابة رسالة تأكيد
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(content=f"✅ تم تسجيل التارجت بنجاح: **{target_type}** بواسطة {interaction.user.mention}", view=None)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("⚠️ التارجت ده اتسجل قبل كدة!", ephemeral=True)

    @discord.ui.button(label="🛠️ تكت دعم (Su)", style=discord.ButtonStyle.primary)
    async def btn_su(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "دعم")

    @discord.ui.button(label="📝 تقديم (Ap)", style=discord.ButtonStyle.success)
    async def btn_ap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "تقديم")

    @discord.ui.button(label="⚠️ ورن (Wr)", style=discord.ButtonStyle.danger)
    async def btn_wr(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_target(interaction, "ورن")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # لو الرسالة فيها صورة (مرفقات)
    if message.attachments:
        # فحص الروم: هل الروم دي مخصصة للشخص ده؟
        c.execute('SELECT channel_id FROM rooms WHERE user_id = ?', (message.author.id,))
        result = c.fetchone()
        
        if result: # لو الشخص متسجل له روم
            if message.channel.id != result[0]: # لو بعت في روم غير بتاعته
                await message.delete()
                await message.channel.send(f"{message.author.mention} ❌ ممنوع تبعت هنا! روح للروم المخصصة ليك.", delete_after=5)
                return

        # إرسال الزراير تحت الصورة
        view = TargetView(author_id=message.author.id, msg_id=message.id)
        await message.channel.send("👇 حدد نوع التارجت للصورة دي:", view=view, reference=message)

    await bot.process_commands(message)

# --- أمر تحديد روم الإداري (للأونر بس) ---
@bot.command()
@commands.has_permissions(administrator=True)
async def setroom(ctx, member: discord.Member, channel: discord.TextChannel):
    c.execute('REPLACE INTO rooms (user_id, channel_id) VALUES (?, ?)', (member.id, channel.id))
    conn.commit()
    await ctx.send(f"✅ تم تخصيص الروم {channel.mention} للإداري {member.mention} بنجاح.")

# --- أمر معرفة التارجت ---
@bot.command()
async def target(ctx, member: discord.Member = None):
    # لو ماعملش منشن لحد، هيجيب التارجت بتاعه هو
    user = member or ctx.author
    
    c.execute('SELECT target_type, COUNT(*) FROM targets WHERE user_id = ? GROUP BY target_type', (user.id,))
    results = c.fetchall()
    
    # تفريغ البيانات
    stats = {"دعم": 0, "تقديم": 0, "ورن": 0}
    for row in results:
        stats[row[0]] = row[1]
        
    total = sum(stats.values())
    
    embed = discord.Embed(title=f"📊 إحصائيات التارجت لـ {user.display_name}", color=0x2ecc71)
    embed.add_field(name="🛠️ تكتات الدعم (Su)", value=f"**{stats['دعم']}**", inline=False)
    embed.add_field(name="📝 تكتات التقديم (Ap)", value=f"**{stats['تقديم']}**", inline=False)
    embed.add_field(name="⚠️ الإنذارات (Wr)", value=f"**{stats['ورن']}**", inline=False)
    embed.add_field(name="🏆 الإجمالي", value=f"**{total}**", inline=False)
    
    await ctx.send(embed=embed)

# تشغيل البوت
keep_alive()
token = os.getenv('DISCORD_TOKEN')
bot.run(token)
