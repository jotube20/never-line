import discord
import os
import pytz
import motor.motor_asyncio
from datetime import datetime, timedelta
from discord.ext import commands
from flask import Flask
from threading import Thread

# ==========================================
#              إعدادات قاعدة البيانات (MongoDB)
# ==========================================
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print("⚠️ تحذير: لم يتم العثور على رابط MongoDB في الإعدادات!")

cluster = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = cluster["NeverManagement"] # اسم الداتا بيز

# المجموعات (Collections) بديلة الجداول
targets_col = db["targets"]
rooms_col = db["rooms"]
pending_col = db["pending"]
owners_col = db["bot_owners"]

# ==========================================
#              إعدادات السيرفر والآيديهات
# ==========================================
MAIN_OWNER_ID = 892133353757736960 # الأونر الأساسي الدائم
STAFF_CATEGORY_ID = 1474909829540872405
OWNER_CATEGORY_ID = 1474909829259726871

# رومات استقبال المراجعات
STAFF_LOG_ID = 1475818693832212591
OWNER_LOG_ID = 1475818413640126476

LINE_URL = "https://media.discordapp.net/attachments/1474909829058531335/1475499138350059600/1100196984901599343.gif"
EMBED_COLOR = 0x2b2d31

# ==========================================
#              سيرفر Render الوهمي
# ==========================================
app = Flask('')
@app.route('/')
def home(): return "System is Online!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# ==========================================
#              تهيئة البوت
# ==========================================
class MyBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(ReviewView())

intents = discord.Intents.default()
intents.message_content = True
bot = MyBot(command_prefix='!', intents=intents, help_command=None)

# ==========================================
#              دوال مساعدة وحماية
# ==========================================
def get_reset_timestamp():
    egypt_tz = pytz.timezone('Africa/Cairo')
    now = datetime.now(egypt_tz)
    days_ahead = 4 - now.weekday()
    if days_ahead < 0 or (days_ahead == 0 and now.hour >= 18):
        days_ahead += 7
    next_friday = now + timedelta(days=days_ahead)
    next_friday = next_friday.replace(hour=18, minute=0, second=0, microsecond=0)
    return int(next_friday.timestamp())

async def get_target_number(user_id, t_type):
    count = await targets_col.count_documents({"user_id": user_id, "target_type": t_type})
    return count + 1

# دالة حماية الأوامر
def is_bot_owner():
    async def predicate(ctx):
        if ctx.author.id == MAIN_OWNER_ID: return True
        owner = await owners_col.find_one({"user_id": ctx.author.id})
        if owner: return True
        await ctx.send("❌ معندكش صلاحية تتحكم في البوت (مخصصة لأونرات البوت فقط).")
        return False
    return commands.check(predicate)

# دالة حماية الأزرار
async def check_button_owner(interaction: discord.Interaction):
    if interaction.user.id == MAIN_OWNER_ID: return True
    owner = await owners_col.find_one({"user_id": interaction.user.id})
    if owner: return True
    await interaction.response.send_message("❌ معندكش صلاحية لاستخدام الزرار ده!", ephemeral=True)
    return False

# ==========================================
#              واجهات المستخدم (UI)
# ==========================================

# --- 1. نافذة الرفض (Modal) ---
class RejectModal(discord.ui.Modal, title='سبب الرفض'):
    reason = discord.ui.TextInput(label='اكتب سبب الرفض هنا:', style=discord.TextStyle.long, required=True)

    def __init__(self, msg_id, author_id, t_type, img_url, embed):
        super().__init__()
        self.msg_id = msg_id
        self.author_id = author_id
        self.t_type = t_type
        self.img_url = img_url
        self.review_embed = embed

    async def on_submit(self, interaction: discord.Interaction):
        await pending_col.delete_one({"msg_id": self.msg_id})
        
        self.review_embed.color = 0xe74c3c
        self.review_embed.title = "❌ تم رفض التارجت"
        self.review_embed.add_field(name="المراجع", value=interaction.user.mention, inline=False)
        self.review_embed.add_field(name="السبب", value=self.reason.value, inline=False)
        await interaction.message.edit(embed=self.review_embed, view=None)
        
        try:
            user = bot.get_user(self.author_id) or await bot.fetch_user(self.author_id)
            dm_embed = discord.Embed(title="❌ تم رفض التارجت الخاص بك", color=0xe74c3c)
            dm_embed.add_field(name="النوع", value=self.t_type, inline=True)
            dm_embed.add_field(name="السبب", value=self.reason.value, inline=False)
            dm_embed.set_image(url=self.img_url)
            await user.send(embed=dm_embed)
        except: pass
        
        await interaction.response.send_message("تم الرفض وإرسال السبب في الخاص بنجاح.", ephemeral=True)

# --- 2. أزرار المراجعة للإدارة العليا ---
class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="قبول ✅", style=discord.ButtonStyle.success, custom_id="review_accept")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_button_owner(interaction): return

        row = await pending_col.find_one({"msg_id": interaction.message.id})
        if not row:
            await interaction.response.send_message("❌ التارجت ده مش موجود في قائمة الانتظار!", ephemeral=True)
            return
        
        # التأكد إنه متراجعش قبل كده
        existing = await targets_col.find_one({"msg_id": interaction.message.id})
        if existing:
            await interaction.response.send_message("⚠️ تم مراجعة هذا التارجت مسبقاً!", ephemeral=True)
            return

        author_id = row["author_id"]
        t_type = row["target_type"]
        
        # حفظ التارجت ومسحه من الانتظار
        await targets_col.insert_one({"msg_id": interaction.message.id, "user_id": author_id, "target_type": t_type})
        await pending_col.delete_one({"msg_id": interaction.message.id})

        embed = interaction.message.embeds[0]
        embed.color = 0x2ecc71
        embed.title = "✅ تم قبول التارجت"
        embed.add_field(name="المراجع", value=interaction.user.mention, inline=False)
        await interaction.message.edit(embed=embed, view=None)

        try:
            user = bot.get_user(author_id) or await bot.fetch_user(author_id)
            dm_embed = discord.Embed(description=f"✅ تم قبول تارجت **{t_type}** الخاص بك!", color=0x2ecc71)
            await user.send(embed=dm_embed)
        except: pass
        
        await interaction.response.send_message("تم قبول التارجت وإبلاغ العضو.", ephemeral=True)

    @discord.ui.button(label="رفض ❌", style=discord.ButtonStyle.danger, custom_id="review_reject")
    async def btn_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_button_owner(interaction): return

        row = await pending_col.find_one({"msg_id": interaction.message.id})
        if not row:
            await interaction.response.send_message("❌ التارجت ده مش موجود في قائمة الانتظار!", ephemeral=True)
            return
        
        embed = interaction.message.embeds[0]
        await interaction.response.send_modal(RejectModal(interaction.message.id, row["author_id"], row["target_type"], row["image_url"], embed))

# --- 3. أزرار إرسال التارجت للإداري ---
class TargetSubmitView(discord.ui.View):
    def __init__(self, author_id, img_url):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.img_url = img_url

    async def send_to_review(self, interaction: discord.Interaction, target_type: str):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ دي مش صورتك!", ephemeral=True)
            return

        cat_id = interaction.channel.category_id
        if cat_id == OWNER_CATEGORY_ID: log_ch_id = OWNER_LOG_ID
        elif cat_id == STAFF_CATEGORY_ID: log_ch_id = STAFF_LOG_ID
        else:
            await interaction.response.send_message("❌ الروم دي مش تابعة لكاتجوري الإدارة ولا الأونرات!", ephemeral=True)
            return
        
        log_channel = bot.get_channel(log_ch_id)
        if not log_channel:
            await interaction.response.send_message("❌ روم المراجعة غير موجودة!", ephemeral=True)
            return

        t_num = await get_target_number(self.author_id, target_type)
        prefix = "Su" if target_type == "دعم" else "Ap" if target_type == "تقديم" else "Wr"

        embed = discord.Embed(title="مراجعة تارجت جديد 🔎", color=0xf1c40f)
        embed.add_field(name="الاسم:", value=interaction.user.mention, inline=False)
        embed.add_field(name="نوع التارجت:", value=target_type, inline=False)
        embed.add_field(name="رقم التارجت:", value=f"{prefix} {t_num}", inline=False)
        embed.set_image(url=self.img_url)

        msg = await log_channel.send(embed=embed, view=ReviewView())

        await pending_col.insert_one({
            "msg_id": msg.id, 
            "author_id": self.author_id, 
            "target_type": target_type, 
            "target_num": t_num, 
            "image_url": self.img_url
        })

        line_embed = discord.Embed(color=EMBED_COLOR)
        line_embed.set_image(url=LINE_URL)
        await log_channel.send(embed=line_embed)

        for item in self.children: item.disabled = True
        await interaction.response.edit_message(content="⏳ **تم إرسال التارجت للمراجعة. سيتم إبلاغك في الخاص بالنتيجة.**", view=None)

    @discord.ui.button(label="دعم (Su)", style=discord.ButtonStyle.primary)
    async def btn_su(self, i: discord.Interaction, b: discord.ui.Button): await self.send_to_review(i, "دعم")

    @discord.ui.button(label="تقديم (Ap)", style=discord.ButtonStyle.success)
    async def btn_ap(self, i: discord.Interaction, b: discord.ui.Button): await self.send_to_review(i, "تقديم")

    @discord.ui.button(label="ورن (Wr)", style=discord.ButtonStyle.danger)
    async def btn_wr(self, i: discord.Interaction, b: discord.ui.Button): await self.send_to_review(i, "ورن")

    @discord.ui.button(label="إلغاء ❌", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ دي مش صورتك!", ephemeral=True)
            return
        await interaction.message.delete()

# --- 4. أزرار تأكيد تصفير التارجت ---
class ResetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تصفير تارجت الجميع 🗑️", style=discord.ButtonStyle.danger)
    async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_button_owner(interaction): return
        
        await targets_col.delete_many({})
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(content="✅ **تم تصفير التارجت لجميع الإداريين بنجاح، وبدأ أسبوع جديد!**", view=None)

# --- 5. قائمة المساعدة ---
class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Owners", description="Owners management commands", value="owners"),
            discord.SelectOption(label="Staff", description="Staff commands", value="staff"),
            discord.SelectOption(label="Public", description="Public commands", value="public")
        ]
        super().__init__(placeholder="Select command category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=EMBED_COLOR)
        if self.values[0] == "owners":
            embed.title = "Owners Commands"
            embed.description = "أوامر الإدارة العليا (الأونرات)."
            embed.add_field(name="!addowner", value="إضافة أونر للبوت.", inline=True)
            embed.add_field(name="!removeowner", value="إزالة أونر من البوت.", inline=True)
            embed.add_field(name="!setroom", value="تحديد روم التارجت لإداري.", inline=True)
            embed.add_field(name="!unsetroom", value="مسح روم التارجت لإداري.", inline=True)
            embed.add_field(name="!minus", value="خصم تارجت من إداري.", inline=True)
            embed.add_field(name="!reset", value="تصفير التارجت للجميع.", inline=True)
        elif self.values[0] == "staff":
            embed.title = "Staff Commands"
            embed.description = "أوامر الإستاف لمتابعة العمل."
            embed.add_field(name="!target", value="عرض إحصائيات التارجت.", inline=False)
        elif self.values[0] == "public":
            embed.title = "Public Commands"
            embed.description = "الأوامر العامة."
            embed.add_field(name="!ping", value="معرفة سرعة استجابة البوت.", inline=False)
            embed.add_field(name="خط", value="إرسال الفاصل الزمني.", inline=False)

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
    print("MongoDB Connected Successfully!")

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    content = message.content.lower()
    if content in ["خط", "line"]:
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_image(url=LINE_URL)
        await message.channel.send(embed=embed)
        try: await message.delete()
        except: pass

    if message.attachments:
        room = await rooms_col.find_one({"channel_id": message.channel.id})
        if room:
            if room["user_id"] != message.author.id:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ❌ دي مش روم التارجت بتاعتك!", delete_after=5)
                return
            else:
                img_url = message.attachments[0].url
                view = TargetSubmitView(author_id=message.author.id, img_url=img_url)
                await message.channel.send("👇 حدد نوع التارجت، أو اضغط إلغاء للتراجع:", view=view, reference=message)

    await bot.process_commands(message)

# ==========================================
#               الأوامر (Commands)
# ==========================================

@bot.command()
async def help(ctx):
    embed = discord.Embed(color=EMBED_COLOR)
    embed.description = f"Hey: {ctx.author.mention} 👋\n\nI'm: {bot.user.mention}, a custom System bot built specially for the server.\n\nTo get started using this bot, select a category from `Select command category...` 🔽"
    if bot.user.avatar: embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_image(url=LINE_URL)
    await ctx.send(embed=embed, view=HelpView())

# --- أوامر نظام الأونرات ---
@bot.command()
@is_bot_owner()
async def addowner(ctx, user: discord.User):
    existing = await owners_col.find_one({"user_id": user.id})
    if existing:
        await ctx.send("⚠️ الشخص ده أونر بالفعل!")
    else:
        await owners_col.insert_one({"user_id": user.id})
        await ctx.send(embed=discord.Embed(description=f"✅ تم إضافة الأونر بنجاح: {user.mention}", color=0x2ecc71))

@bot.command()
@is_bot_owner()
async def removeowner(ctx, user: discord.User):
    if user.id == MAIN_OWNER_ID:
        await ctx.send("❌ مقدرش أشيل الأونر الأساسي!")
        return
    result = await owners_col.delete_one({"user_id": user.id})
    if result.deleted_count > 0:
        await ctx.send(embed=discord.Embed(description=f"✅ تم إزالة الأونر بنجاح: {user.mention}", color=0xe74c3c))
    else:
        await ctx.send("⚠️ الشخص ده مش متسجل كأونر أصلاً!")

# --- أوامر التحكم في الرومات والتارجت ---
@bot.command()
@is_bot_owner()
async def setroom(ctx, member: discord.Member, channel: discord.TextChannel):
    await rooms_col.update_one({"user_id": member.id}, {"$set": {"channel_id": channel.id}}, upsert=True)
    await ctx.send(embed=discord.Embed(description=f"✅ تم تخصيص الروم {channel.mention} للإداري {member.mention}.", color=0x2ecc71))

@bot.command()
@is_bot_owner()
async def unsetroom(ctx, member: discord.Member):
    await rooms_col.delete_one({"user_id": member.id})
    await ctx.send(embed=discord.Embed(description=f"✅ تم مسح روم التارجت المخصصة للإداري {member.mention}.", color=0xe74c3c))

@bot.command()
@is_bot_owner()
async def reset(ctx):
    await ctx.send("⚠️ **تنبيه إداري:** هل أنت متأكد من رغبتك في تصفير التارجت لجميع الإداريين؟", view=ResetView())

@bot.command()
@is_bot_owner()
async def minus(ctx, member: discord.Member, target_type: str, amount: int = 1):
    valid_types = ["دعم", "تقديم", "ورن"]
    if target_type not in valid_types:
        await ctx.send("❌ نوع التارجت غير صحيح! (اختر: دعم، تقديم، ورن)")
        return
        
    cursor = targets_col.find({"user_id": member.id, "target_type": target_type}).sort("_id", -1).limit(amount)
    docs = await cursor.to_list(length=amount)
    
    if not docs: 
        await ctx.send(f"⚠️ الإداري {member.display_name} معندوش تارجت من نوع **{target_type}** عشان يتخصم!")
    else: 
        msg_ids = [doc["msg_id"] for doc in docs]
        await targets_col.delete_many({"msg_id": {"$in": msg_ids}})
        await ctx.send(embed=discord.Embed(description=f"✅ تم خصم **{len(docs)}** من تارجت **{target_type}** للإداري {member.mention}.", color=0xe74c3c))

@bot.command()
async def target(ctx, member: discord.Member = None):
    user = member or ctx.author
    room = await rooms_col.find_one({"user_id": user.id})
    if not room:
        await ctx.send("عفواً، هذا الشخص لا يوجد في قاعدة بيانات الإداريين المسجلين.")
        return

    # حساب الإحصائيات من MongoDB
    pipeline = [
        {"$match": {"user_id": user.id}},
        {"$group": {"_id": "$target_type", "count": {"$sum": 1}}}
    ]
    cursor = targets_col.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    
    stats = {"دعم": 0, "تقديم": 0, "ورن": 0}
    for row in results:
        stats[row["_id"]] = row["count"]
        
    total = sum(stats.values())
    
    embed = discord.Embed(title="📊 إحصائيات التارجت الأسبوعي", color=EMBED_COLOR)
    embed.description = f"**الإداري:** {user.mention}\n⏳ **الوقت المتبقي للتصفير:** <t:{get_reset_timestamp()}:R>"
    if user.avatar: embed.set_thumbnail(url=user.avatar.url)
        
    embed.add_field(name="🛠️ دعم (Su)", value=f"`{stats['دعم']}`", inline=True)
    embed.add_field(name="📝 تقديم (Ap)", value=f"`{stats['تقديم']}`", inline=True)
    embed.add_field(name="⚠️ ورن (Wr)", value=f"`{stats['ورن']}`", inline=True)
    embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed.add_field(name="🏆 الإجمالي", value=f"**{total}**", inline=False)
    embed.set_image(url=LINE_URL)
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send(embed=discord.Embed(description=f"🏓 Pong! **{round(bot.latency * 1000)}ms**", color=EMBED_COLOR))

keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))

