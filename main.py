import discord
from discord.ext import commands, tasks
import os
import sqlite3

# =====================================================================
# إعدادات البوت والبيانات الأساسية
# =====================================================================
TOKEN = os.getenv("TOKEN")
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# إعداد قاعدة البيانات الشاملة SQLite
db_conn = sqlite3.connect("server_database.db")
db_cursor = db_conn.cursor()

# 1. جدول الهويات واللاعبين والوظائف
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS player_ids (
    discord_id INTEGER PRIMARY KEY,
    game_id INTEGER UNIQUE,
    job TEXT DEFAULT 'مواطن',
    rank TEXT DEFAULT 'مستجد',
    status TEXT DEFAULT 'مفعل',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 2. جدول النظام البنكي والمالي
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS bank_accounts (
    discord_id INTEGER PRIMARY KEY,
    account_number TEXT UNIQUE,
    balance REAL DEFAULT 1000.0,
    is_frozen INTEGER DEFAULT 0
)
""")

# 3. جدول السجل الأمني والمخالفات (MDC System)
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS criminal_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER,
    officer_id INTEGER,
    reason TEXT,
    date_recorded TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
db_conn.commit()


@bot.event
async def on_ready():
    print(f"----------------------------------------")
    print(f" تم تشغيل السيرفر الأسطوري بنجاح: {bot.user.name} 🔥")
    print(f" جميع الأنظمة (الهويات، التذاكر، البنك، السجل، الرواتب) شغالين!")
    print(f"----------------------------------------")
    # تشغيل نظام توزيع الرواتب التلقائي في الخلفية
    auto_salary.start()


# =====================================================================
# قائمة الوظائف والرواتب المعتمدة
# =====================================================================
JOBS_LIST = {
    "عسكرية": {"name": "👮 العسكرية", "salary": 1500},
    "قانون": {"name": "⚖️ القانون", "salary": 1400},
    "إجرام": {"name": "🔫 الإجرام", "salary": 800},
    "إعلام": {"name": "📺 الإعلام", "salary": 1000},
    "إسعاف": {"name": "🚑 الإسعاف", "salary": 1300},
    "مدنية": {"name": "🚕 الوظائف المدنية", "salary": 900}
}


# =====================================================================
# 1. نظام الهويات وصورة البطاقة (ID Card System)
# =====================================================================
@bot.command(name="صنع_هوية", aliases=["إنشاء_هوية", "تفعيل"])
@commands.has_permissions(manage_roles=True)
async def create_id(ctx, member: discord.Member, game_id: int, job_name: str = "مواطن", *, rank_name: str = "مستجد"):
    try:
        # تسجيل أو تحديث الهوية
        db_cursor.execute(
            "INSERT OR REPLACE INTO player_ids (discord_id, game_id, job, rank, status) VALUES (?, ?, ?, ?, ?)",
            (member.id, game_id, job_name, rank_name, "مفعل")
        )
        
        # إنشاء حساب بنكي تلقائي مع الهوية
        acc_num = f"SA-VRP-{game_id}"
        db_cursor.execute(
            "INSERT OR IGNORE INTO bank_accounts (discord_id, account_number, balance) VALUES (?, ?, ?)",
            (member.id, acc_num, 5000.0)
        )
        db_conn.commit()

        embed = discord.Embed(
            title="🪪 نظام الهويات الرسمي | إصدار بطاقة",
            description=f"تم إصدار الهوية الحكومية وفتح الحساب البنكي للعضو {member.mention} بنجاح!",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 رقم الـ ID", value=f"**{game_id}**", inline=True)
        embed.add_field(name="💼 الوظيفة", value=f"**{job_name}**", inline=True)
        embed.add_field(name="⭐ الرتبة", value=f"**{rank_name}**", inline=True)
        embed.add_field(name="🏦 رقم الحساب", value=f"`{acc_num}`", inline=False)
        embed.set_footer(text=f"بواسطة الإداري: {ctx.author.display_name}")

        await ctx.send(embed=embed)

    except sqlite3.IntegrityError:
        await ctx.send(f"❌ عذراً، رقم الـ ID (**{game_id}**) أو اللاعب مسجل مسبقاً في النظام!")


@bot.command(name="id", aliases=["هويتي", "ملفي"])
async def show_id(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    # جلب بيانات الهوية
    db_cursor.execute("SELECT game_id, job, rank, status, created_date FROM player_ids WHERE discord_id = ?", (member.id,))
    p_data = db_cursor.fetchone()

    # جلب بيانات البنك
    db_cursor.execute("SELECT account_number, balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (member.id,))
    b_data = db_cursor.fetchone()

    # جلب عدد المخالفات الأمنية
    db_cursor.execute("SELECT COUNT(*) FROM criminal_records WHERE target_id = ?", (member.id,))
    violations_count = db_cursor.fetchone()[0]

    embed = discord.Embed(title=f"🪪 بطاقة الهوية الشخصية", color=discord.Color.gold())
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    if not p_data:
        embed.description = f"العضو {member.mention} لا يمتلك بطاقة هوية مسجلة في النظام."
        embed.color = discord.Color.red()
        embed.add_field(name="📌 الحالة", value="غير مسجل (يحتاج إصدار هوية من الإدارة)", inline=False)
    else:
        game_id, job, rank, status, created_date = p_data
        acc_num = b_data[0] if b_data else "لا يوجد"
        balance = b_data[1] if b_data else 0.0
        is_frozen = b_data[2] if b_data else 0

        bank_status = "🔒 مجمد" if is_frozen == 1 else f"${balance:,.2f}"
        security_status = f"🚨 عليه {violations_count} مخالفة" if violations_count > 0 else "🟢 السجل نظيف"

        embed.description = f"بطاقة هوية رسمية معتمدة للمواطن: **{member.display_name}**"
        embed.add_field(name="🆔 رقم اللاعب (ID)", value=f"`{game_id}`", inline=True)
        embed.add_field(name="📌 الحالة", value=f"🟢 {status}", inline=True)
        embed.add_field(name="💼 الوظيفة", value=f"**{job}**", inline=True)
        embed.add_field(name="⭐ الرتبة", value=f"**{rank}**", inline=True)
        embed.add_field(name="🏦 الرصيد المالي", value=f"**{bank_status}**", inline=True)
        embed.add_field(name="📋 رقم الحساب", value=f"`{acc_num}`", inline=True)
        embed.add_field(name="🛡️ السجل الأمني", value=security_status, inline=False)

    embed.set_footer(text=f"طلب بواسطة: {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)


# =====================================================================
# 2. نظام التذاكر والخدمات (Tickets System)
# =====================================================================
class DepartmentSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني العام", emoji="🛠️", description="استفسارات ومشاكل الديسكورد"),
            discord.SelectOption(label="قسم التوظيف", emoji="📋", description="التقديم على العسكرية والوظائف"),
            discord.SelectOption(label="شكاوى الإدارة", emoji="⚖️", description="لتقديم شكوى أو استفسار إداري"),
            discord.SelectOption(label="شؤون البنك والمالية", emoji="🏦", description="مواضيع الحسابات والتحويلات المالية")
        ]
        super().__init__(placeholder="اختر القسم المناسب لفتح تذكرتك...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="TICKETS SYSTEM")
        if not category:
            category = await guild.create_category("TICKETS SYSTEM")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)
        
        embed = discord.Embed(
            title=f"🎫 تذكرة جديدة - القسم: {self.values[0]}",
            description=f"أهلاً بك {interaction.user.mention}!\nتم فتح التذكرة بنجاح. يرجى توضيح طلبك بالكامل وسنتواجد لخدمتك قريباً.",
            color=discord.Color.blue()
        )
        await channel.send(embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"تم إنشاء تذكرتك بنجاح في الغرفة: {channel.mention}", ephemeral=True)


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DepartmentSelect())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 إغلاق التذكرة", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ جاري إغلاق الغرفة...")
        await interaction.channel.delete()


@bot.command(name="تذاكر")
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    embed = discord.Embed(
        title="📌 مركز المساعدة والتذاكر الرسمي",
        description="إذا احتجت أي استفسار، تفعيل، توظيف، أو خدمات بنكية، اختر القسم المناسب من القائمة بالأسفل لفتح تذكرة.",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    await ctx.send(embed=embed, view=TicketView())
    await ctx.message.delete()


# =====================================================================
# 3. الوظائف الإدارية والتوظيف والسجل الأمني
# =====================================================================
@bot.command(name="توظيف")
@commands.has_permissions(manage_roles=True)
async def hire_player(ctx, member: discord.Member, job_name: str, *, rank_name: str):
    db_cursor.execute("UPDATE player_ids SET job = ?, rank = ? WHERE discord_id = ?", (job_name, rank_name, member.id))
    db_conn.commit()

    embed = discord.Embed(
        title="📋 قرار توظيف رسمي",
        description=f"تم ترقية وتوظيف العضو {member.mention}\nالقطاع: **{job_name}**\nالرتبة: **{rank_name}**",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)


@bot.command(name="سجل")
@commands.has_permissions(manage_roles=True)
async def criminal_record(ctx, member: discord.Member, *, reason: str):
    db_cursor.execute("INSERT INTO criminal_records (target_id, officer_id, reason) VALUES (?, ?, ?)", 
                      (member.id, ctx.author.id, reason))
    db_conn.commit()

    embed = discord.Embed(
        title="🚨 تسجيل مخالفة أمنية جديدة",
        description=f"تم تسجيل مخالفة بحق العضو: {member.mention}\nالتفاصيل: **{reason}**\nبواسطة العسكري: {ctx.author.mention}",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)


@bot.command(name="كشف")
@commands.has_permissions(manage_roles=True)
async def check_criminal_record(ctx, member: discord.Member):
    db_cursor.execute("SELECT reason, date_recorded FROM criminal_records WHERE target_id = ?", (member.id,))
    records = db_cursor.fetchall()

    embed = discord.Embed(title=f"📋 السجل الأمني للاعب: {member.display_name}", color=discord.Color.dark_red())

    if not records:
        embed.description = "سجل هذا اللاعب نظيف تماماً 🟢 ولا توجد أي مخالفات مسجلة."
    else:
        text = ""
        for idx, rec in enumerate(records, 1):
            text += f"**{idx}.** {rec[0]} *(التاريخ: {rec[1]})*\n"
        embed.description = text

    await ctx.send(embed=embed)


# =====================================================================
# 4. النظام البنكي والتحويل والرواتب التلقائية
# =====================================================================
@bot.command(name="رصيدي", aliases=["بنك"])
async def check_bank(ctx):
    db_cursor.execute("SELECT account_number, balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    res = db_cursor.fetchone()

    if not res:
        await ctx.send(f"❌ {ctx.author.mention}, ليس لديك حساب بنكي مفعل!")
        return

    acc_num, balance, frozen = res
    status_text = "🔒 مجمد" if frozen == 1 else "🟢 نشط"

    embed = discord.Embed(title="🏦 الحساب البنكي الشخصي", color=discord.Color.green() if frozen == 0 else discord.Color.red())
    embed.add_field(name="رقم الحساب", value=acc_num, inline=False)
    embed.add_field(name="الرصيد الحالي", value=f"${balance:,.2f}", inline=True)
    embed.add_field(name="حالة الحساب", value=status_text, inline=True)
    
    await ctx.send(embed=embed)


@bot.command(name="تحويل")
async def bank_transfer(ctx, target: discord.Member, amount: float):
    if amount <= 0 or target.id == ctx.author.id:
        await ctx.send("❌ عملية تحويل غير صالحة!")
        return

    db_cursor.execute("SELECT balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    sender_res = db_cursor.fetchone()
    if not sender_res or sender_res[1] == 1 or sender_res[0] < amount:
        await ctx.send("❌ رصيدك لا يكفي أو حسابك غير متاح للتحويل.")
        return

    db_cursor.execute("SELECT is_frozen FROM bank_accounts WHERE discord_id = ?", (target.id,))
    target_res = db_cursor.fetchone()
    if not target_res or target_res[0] == 1:
        await ctx.send("❌ حساب المستلم غير موجود أو مجمد.")
        return

    db_cursor.execute("UPDATE bank_accounts SET balance = balance - ? WHERE discord_id = ?", (amount, ctx.author.id))
    db_cursor.execute("UPDATE bank_accounts SET balance = balance + ? WHERE discord_id = ?", (amount, target.id))
    db_conn.commit()

    await ctx.send(f"🔄 تم تحويل **${amount:,.2f}** بنجاح من {ctx.author.mention} إلى {target.mention}")


@tasks.loop(hours=1.0)
async def auto_salary():
    db_cursor.execute("SELECT discord_id, job FROM player_ids WHERE status = 'مفعل'")
    players = db_cursor.fetchall()
    
    for p in players:
        discord_id, job = p
        salary = JOBS_LIST.get(job, {}).get("salary", 500)
        db_cursor.execute("UPDATE bank_accounts SET balance = balance + ? WHERE discord_id = ?", (salary, discord_id))
    db_conn.commit()


@bot.command(name="ping")
async def check_ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 سرعة استجابة البوت: **{latency}ms** (السيرفر الأسطوري يعمل بكفاءة 🔥)")


# تشغيل البوت عبر التوكن في Secrets
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ خطأ: لم يتم العثور على التوكن في متغيرات البيئة (Secrets)!")
