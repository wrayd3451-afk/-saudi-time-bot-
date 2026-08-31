import os
import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import sqlite3

# إعدادات البوت والصلاحيات
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

# إعداد قاعدة البيانات
conn = sqlite3.connect("server_system.db")
cursor = conn.cursor()

# إنشاء الجداول الأساسية
cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        discord_id INTEGER PRIMARY KEY,
        player_id INTEGER UNIQUE,
        name TEXT,
        status TEXT DEFAULT "غير مفعل",
        job TEXT DEFAULT "مواطن",
        rank TEXT DEFAULT "مبتدئ",
        points INTEGER DEFAULT 0,
        criminal_record TEXT DEFAULT "سجل نظيف",
        penalties INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        player_id INTEGER,
        amount INTEGER,
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# الوظائف المتاحة
JOBS = {
    "العسكرية": ["جندي", "عريف", "وكيل رقيب", "رقيب", "ملازم"],
    "القانون": ["مفوض", "محقق", "نقيب", "قاضي"],
    "الإجرام": ["مبتدئ", "محتراف", "زعيم عصابة"],
    "الإعلام": ["مصور", "مراسل", "مدير إعلامي"],
    "الإسعاف": ["مسعف", "مسعف أول", "طبيب"],
    "الوظائف المدنية": ["موظف", "مشرف", "مدير عام"]
}

# لوحة التحكم الرئيسية للتذاكر
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="التذاكر")
        if not category:
            category = await guild.create_category("التذاكر")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(f"تذكرة-{interaction.user.name}", category=category, overwrites=overwrites)
        
        select_view = View()
        select = Select(placeholder="اختر قسم التذكرة", options=[
            discord.SelectOption(label="الدعم الفني", value="support"),
            discord.SelectOption(label="الشكاوى", value="complaints"),
            discord.SelectOption(label="التوظيف", value="employment")
        ])
        
        async def select_callback(inter: discord.Interaction):
            await inter.response.send_message(f"تم اختيار القسم: {select.values[0]}", ephemeral=True)

        select.callback = select_callback
        select_view.add_item(select)

        await channel.send(f"مرحباً {interaction.user.mention}, الرجاء اختيار القسم المناسب:", view=select_view)
        await interaction.response.send_message(f"تم فتح التذكرة بنجاح: {channel.mention}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")

# 1. نظام التفعيل
@bot.command(name="تفعيل")
async def activate_player(ctx, member: discord.Member, player_id: int):
    cursor.execute("INSERT OR REPLACE INTO players (discord_id, player_id, name, status) VALUES (?, ?, ?, ?)",
                   (member.id, player_id, member.name, "مفعل"))
    conn.commit()
    await ctx.send(f"تم تفعيل اللاعب {member.name} برقم تعريف {player_id}.")

# 2. نظام استدعاء اللاعبين
@bot.command(name="استدعاء")
async def call_player(ctx, member: discord.Member, *, reason: str):
    await ctx.send(f"{member.mention}, تم استدعاؤك من قبل الإدارة. السبب: {reason}")

# 3. نظام رتب الوظائف
@bot.command(name="رتب")
async def set_rank(ctx, member: discord.Member, job: str, rank: str):
    if job in JOBS and rank in JOBS[job]:
        cursor.execute("UPDATE players SET job = ?, rank = ? WHERE discord_id = ?", (job, rank, member.id))
        conn.commit()
        await ctx.send(f"تم تعيين الرتبة {rank} في وظيفة {job} للمستخدم {member.name}.")
    else:
        await ctx.send("الوظيفة أو الرتبة غير صحيحة.")

# 4. عرض اسماء اللاعبين المرتبطين
@bot.command(name="اسماء")
async def list_players(ctx):
    cursor.execute("SELECT player_id, name, job, rank FROM players")
    rows = cursor.fetchall()
    if not rows:
        await ctx.send("لا يوجد لاعبين مسجلين.")
        return
    
    msg = "قائمة اللاعبين المسجلين:\n"
    for row in rows:
        msg += f"الرقم: {row[0]} | الاسم: {row[1]} | الوظيفة: {row[2]} | الرتبة: {row[3]}\n"
    await ctx.send(msg)

# 5. التوظيف
@bot.command(name="توظيف")
async def employ_player(ctx, member: discord.Member, job: str):
    if job in JOBS:
        default_rank = JOBS[job][0]
        cursor.execute("UPDATE players SET job = ?, rank = ? WHERE discord_id = ?", (job, default_rank, member.id))
        conn.commit()
        await ctx.send(f"تم توظيف {member.name} في وظيفة {job} برتبة {default_rank}.")
    else:
        await ctx.send("الوظيفة غير موجودة.")

# 6. التقاعد
@bot.command(name="تقاعد")
async def retire_player(ctx, member: discord.Member):
    cursor.execute("UPDATE players SET job = 'متقاعد', rank = 'مفصول' WHERE discord_id = ?", (member.id,))
    conn.commit()
    await ctx.send(f"تم إحالة اللاعب {member.name} إلى التقاعد.")

# 7. الاستقالة
@bot.command(name="استقالة")
async def resign_player(ctx):
    cursor.execute("UPDATE players SET job = 'مواطن', rank = 'بدون' WHERE discord_id = ?", (ctx.author.id,))
    conn.commit()
    await ctx.send("تم قبول استقالتك وعودتك كمواطن.")

# 8. إخلاء الموقع أو المكان
@bot.command(name="إخلاء")
async def evacuate_area(ctx, *, location: str):
    await ctx.send(f"تنبيه إداري: يرجى إخلاء الموقع التالي فورا: {location}")

# 9. حجز اللاعبين أو الأصول
@bot.command(name="حجز")
async def detain_player(ctx, member: discord.Member, *, reason: str):
    cursor.execute("UPDATE players SET penalties = penalties + 1 WHERE discord_id = ?", (member.id,))
    conn.commit()
    await ctx.send(f"تم حجز اللاعب {member.name}. السبب: {reason}")

# 10. تأكيد العمليات
@bot.command(name="تأكيد")
async def confirm_action(ctx, *, action_name: str):
    await ctx.send(f"تم تأكيد عملية: {action_name} بنجاح بواسطة {ctx.author.name}.")

# نظام النقاط: إضافة أو خصم
@bot.command(name="نقاط")
async def manage_points(ctx, member: discord.Member, amount: int, *, reason: str):
    cursor.execute("UPDATE players SET points = points + ? WHERE discord_id = ?", (amount, member.id))
    cursor.execute("INSERT INTO points_log (admin_id, player_id, amount, reason) VALUES (?, ?, ?, ?)",
                   (ctx.author.id, member.id, amount, reason))
    conn.commit()
    await ctx.send(f"تم تعديل نقاط اللاعب {member.name} بقيمة {amount}. السبب: {reason}")

# ربط VRP (قراءة بيانات من القاعدة وقاعدة بيانات خارجية وهمية)
@bot.command(name="vrp")
async def vrp_data(ctx, player_id: int):
    cursor.execute("SELECT player_id, name, status, job, rank, balance FROM players WHERE player_id = ?", (player_id,))
    row = cursor.fetchone()
    if row:
        response = (
            f"بيانات اللاعب من النظام:\n"
            f"رقم اللاعب: {row[0]}\n"
            f"الاسم: {row[1]}\n"
            f"الحالة: {row[2]}\n"
            f"الوظيفة: {row[3]}\n"
            f"الرتبة: {row[4]}\n"
            f"الرصيد: {row[5]}"
        )
        await ctx.send(response)
    else:
        await ctx.send("لم يتم العثور على بيانات لهذا اللاعب في قاعدة البيانات.")

# أمر لعرض لوحة التذاكر
@bot.command(name="تذاكر")
async def setup_tickets(ctx):
    await ctx.send("اضغط على الزر أدناه لفتح تذكرة جديدة:", view=TicketView())

# تشغيل البوت (ضع التوكن الخاص بك هنا)
# bot.run("YOUR_BOT_TOKEN")
