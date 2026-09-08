import discord
from discord.ext import commands
import os
import sqlite3

# =====================================================================
# إعدادات البوت والبيانات الأساسية
# =====================================================================
TOKEN = "حط_التوكن_هنا"
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# إعداد قاعدة البيانات المحلية SQLite (لاعبين + النظام البنكي VRP)
db_conn = sqlite3.connect("server_database.db")
db_cursor = db_conn.cursor()

# جدول اللاعبين والوظائف والنقاط
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    player_id INTEGER,
    job TEXT DEFAULT 'مواطن',
    rank TEXT DEFAULT 'مستجد',
    points INTEGER DEFAULT 0,
    status TEXT DEFAULT 'غير مفعل'
)
""")

# جدول النظام البنكي المطور VRP
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS bank_accounts (
    discord_id INTEGER PRIMARY KEY,
    account_number TEXT UNIQUE,
    balance REAL DEFAULT 1000.0,
    is_frozen INTEGER DEFAULT 0
)
""")
db_conn.commit()


@bot.event
async def on_ready():
    print(f"----------------------------------------")
    print(f" تم تشغيل البوت بنجاح: {bot.user.name}")
    print(f" النظام الشامل (السيستم + البنك + VRP) جاهز تماماً 🔥!")
    print(f"----------------------------------------")


# =====================================================================
# 1. نظام الوظائف والأقسام المعتمدة في السيرفر
# =====================================================================
JOBS_LIST = {
    "عسكرية": {"name": "👮 العسكرية", "roles": ["ملازم", "رائد", "قائد العسكرية"]},
    "قانون": {"name": "⚖️ القانون", "roles": ["محامي", "قاضي", "وزير العدل"]},
    "إجرام": {"name": "🔫 الإجرام", "roles": ["عضو عصابة", "زعيم عصابة"]},
    "إعلام": {"name": "📺 الإعلام", "roles": ["مراسل", "مستشار إعلامي"]},
    "إسعاف": {"name": "🚑 الإسعاف", "roles": ["مسعف", "طبيب", "مدير المستشفى"]},
    "مدنية": {"name": "🚕 الوظائف المدنية", "roles": ["موظف مدني", "مدير عام"]}
}


# =====================================================================
# 2. نظام التذاكر والخدمات المطور (Tickets System)
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
        embed.set_footer(text="نظام إدارة السيرفرات المتطور")
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
        await interaction.response.send_message("⚠️ جاري حفظ سجل التذكرة وإغلاق الغرفة...")
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
# 3. الأوامر الإدارية ونظام اللاعبين (ID, تفعيل, توظيف, نقاط)
# =====================================================================

@bot.command(name="تفعيل")
@commands.has_permissions(manage_roles=True)
async def verify_player(ctx, member: discord.Member, player_id: int):
    db_cursor.execute("INSERT OR REPLACE INTO players (discord_id, player_id, status) VALUES (?, ?, ?)", 
                      (member.id, player_id, "مفعل"))
    
    # فتح حساب بنكي تلقائي عند التفعيل برقم حساب عشوائي مرتب
    acc_num = f"SA-VRP-{player_id}"
    db_cursor.execute("INSERT OR IGNORE INTO bank_accounts (discord_id, account_number, balance) VALUES (?, ?, ?)", 
                      (member.id, acc_num, 5000.0))
    db_conn.commit()

    embed = discord.Embed(
        title="✅ تم تفعيل اللاعب وفتح الحساب البنكي",
        description=f"العضو: {member.mention}\nرقم اللاعب (ID): **{player_id}**\nرقم الحساب البنكي: **{acc_num}** (تم إيداع الرصيد الابتدائي)",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="توظيف")
@commands.has_permissions(manage_roles=True)
async def hire_player(ctx, member: discord.Member, job_name: str, *, rank_name: str):
    db_cursor.execute("UPDATE players SET job = ?, rank = ? WHERE discord_id = ?", (job_name, rank_name, member.id))
    db_conn.commit()

    embed = discord.Embed(
        title="📋 قرار توظيف رسمي",
        description=f"تم توظيف العضو {member.mention}\nالقطاع: **{job_name}**\nالرتبة: **{rank_name}**",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)


@bot.command(name="نقاط")
@commands.has_permissions(manage_roles=True)
async def manage_points(ctx, member: discord.Member, action: str, amount: int):
    if action.lower() in ["إضافة", "+"]:
        db_cursor.execute("UPDATE players SET points = points + ? WHERE discord_id = ?", (amount, member.id))
        msg = f"تمت إضافة **{amount}** نقطة إلى العضو {member.mention}"
    elif action.lower() in ["خصم", "-"]:
        db_cursor.execute("UPDATE players SET points = MAX(0, points - ?) WHERE discord_id = ?", (amount, member.id))
        msg = f"تم خصم **{amount}** نقطة من العضو {member.mention}"
    else:
        await ctx.send("❌ الاستخدام الخاطئ! استخدم: `!نقاط @user إضافة 50` أو `!نقاط @user خصم 20`")
        return

    db_conn.commit()
    db_cursor.execute("SELECT points FROM players WHERE discord_id = ?", (member.id,))
    res = db_cursor.fetchone()
    total_pts = res[0] if res else 0

    embed = discord.Embed(
        title="⭐ تحديث نقاط الموظف",
        description=f"{msg}\nمجموع النقاط الحالي: **{total_pts}**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


@bot.command(name="اسماء")
@commands.has_permissions(manage_roles=True)
async def player_info(ctx, member: discord.Member):
    db_cursor.execute("SELECT player_id, job, rank, points, status FROM players WHERE discord_id = ?", (member.id,))
    res = db_cursor.fetchone()

    if not res:
        await ctx.send(f"❌ العضو {member.mention} غير مسجل في قاعدة البيانات بعد!")
        return

    embed = discord.Embed(
        title=f"📊 ملف اللاعب: {member.display_name}",
        color=discord.Color.dark_blue()
    )
    embed.add_field(name="رقم اللاعب (ID)", value=str(res[0]), inline=True)
    embed.add_field(name="حالة التفعيل", value=res[4], inline=True)
    embed.add_field(name="الوظيفة", value=res[1], inline=True)
    embed.add_field(name="الرتبة الحالية", value=res[2], inline=True)
    embed.add_field(name="النقاط", value=str(res[3]), inline=True)
    
    await ctx.send(embed=embed)


# =====================================================================
# 4. نظام البنك المتكامل (VRP Bank System)
# =====================================================================

@bot.command(name="رصيدي", aliases=["بنك"])
async def check_bank(ctx):
    db_cursor.execute("SELECT account_number, balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    res = db_cursor.fetchone()

    if not res:
        await ctx.send(f"❌ {ctx.author.mention}, ليس لديك حساب بنكي مفعل! يطلب من الإدارة تفعيلك عبر أمر `!تفعيل`.")
        return

    acc_num, balance, frozen = res
    status_text = "🔒 مجمد" if frozen == 1 else "🟢 نشط"

    embed = discord.Embed(
        title="🏦 الحساب البنكي الشخصي",
        color=discord.Color.green() if frozen == 0 else discord.Color.red()
    )
    embed.add_field(name="رقم الحساب", value=acc_num, inline=False)
    embed.add_field(name="الرصيد الحالي", value=f"${balance:,.2f}", inline=True)
    embed.add_field(name="حالة الحساب", value=status_text, inline=True)
    
    await ctx.send(embed=embed)


@bot.command(name="إيداع")
async def bank_deposit(ctx, amount: float):
    if amount <= 0:
        await ctx.send("❌ لا يمكنك إيداع مبلغ سالب أو صفر!")
        return

    db_cursor.execute("SELECT is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    res = db_cursor.fetchone()
    if not res:
        await ctx.send("❌ ليس لديك حساب بنكي مسجل.")
        return
    if res[0] == 1:
        await ctx.send("❌ عذراً، حسابك البنكي **مجمد** من قبل الإدارة ولا يمكنك إجراء أي عمليات.")
        return

    db_cursor.execute("UPDATE bank_accounts SET balance = balance + ? WHERE discord_id = ?", (amount, ctx.author.id))
    db_conn.commit()

    db_cursor.execute("SELECT balance FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    new_bal = db_cursor.fetchone()[0]

    await ctx.send(f"💵 تم إيداع **${amount:,.2f}** بنجاح في حسابك. رصيدك الجديد: **${new_bal:,.2f}**")


@bot.command(name="سحب")
async def bank_withdraw(ctx, amount: float):
    if amount <= 0:
        await ctx.send("❌ لا يمكنك سحب مبلغ سالب أو صفر!")
        return

    db_cursor.execute("SELECT balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    res = db_cursor.fetchone()
    if not res:
        await ctx.send("❌ ليس لديك حساب بنكي مسجل.")
        return
    if res[1] == 1:
        await ctx.send("❌ عذراً، حسابك البنكي **مجمد**.")
        return
    
    current_bal = res[0]
    if current_bal < amount:
        await ctx.send(f"❌ رصيدك غير كافي! رصيدك الحالي هو: **${current_bal:,.2f}**")
        return

    db_cursor.execute("UPDATE bank_accounts SET balance = balance - ? WHERE discord_id = ?", (amount, ctx.author.id))
    db_conn.commit()

    await ctx.send(f"💸 تم سحب **${amount:,.2f}** بنجاح. رصيدك المتبقي: **${current_bal - amount:,.2f}**")


@bot.command(name="تحويل")
async def bank_transfer(ctx, target: discord.Member, amount: float):
    if amount <= 0:
        await ctx.send("❌ مبلغ التحويل غير صالح!")
        return
    if target.id == ctx.author.id:
        await ctx.send("❌ لا يمكنك التحويل لنفسك!")
        return

    # فحص حساب المرسل
    db_cursor.execute("SELECT balance, is_frozen FROM bank_accounts WHERE discord_id = ?", (ctx.author.id,))
    sender_res = db_cursor.fetchone()
    if not sender_res or sender_res[1] == 1:
        await ctx.send("❌ حسابك غير متاح أو مجمد للتحويل.")
        return
    if sender_res[0] < amount:
        await ctx.send("❌ رصيدك البنكي لا يكفي لإتمام عملية التحويل.")
        return

    # فحص حساب المستلم
    db_cursor.execute("SELECT is_frozen FROM bank_accounts WHERE discord_id = ?", (target.id,))
    target_res = db_cursor.fetchone()
    if not target_res:
        await ctx.send("❌ الشخص المراد التحويل له ليس لديه حساب بنكي في النظام.")
        return
    if target_res[1] == 1:
        await ctx.send("❌ عذراً، حساب الشخص المستلم **مجمد** ولا تستطيع التحويل له.")
        return

    # تنفيذ عملية التحويل المالية
    db_cursor.execute("UPDATE bank_accounts SET balance = balance - ? WHERE discord_id = ?", (amount, ctx.author.id))
    db_cursor.execute("UPDATE bank_accounts SET balance = balance + ? WHERE discord_id = ?", (amount, target.id))
    db_conn.commit()

    embed = discord.Embed(
        title="🔄 عملية تحويل ناجحة",
        description=f"تم تحويل **${amount:,.2f}** بنجاح من {ctx.author.mention} إلى {target.mention}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@bot.command(name="تجميد")
@commands.has_permissions(administrator=True)
async def freeze_account(ctx, member: discord.Member):
    db_cursor.execute("UPDATE bank_accounts SET is_frozen = 1 WHERE discord_id = ?", (member.id,))
    db_conn.commit()
    await ctx.send(f"🔒 تم تجميد الحساب البنكي للعضو {member.mention} بنجاح.")


@bot.command(name="فك_تجميد")
@commands.has_permissions(administrator=True)
async def unfreeze_account(ctx, member: discord.Member):
    db_cursor.execute("UPDATE bank_accounts SET is_frozen = 0 WHERE discord_id = ?", (member.id,))
    db_conn.commit()
    await ctx.send(f"🟢 تم فك تجميد الحساب البنكي للعضو {member.mention} بنجاح وإعادة نشاطه.")


@bot.command(name="استقالة")
async def resign_player(ctx):
    db_cursor.execute("UPDATE players SET job = 'مواطن', rank = 'مستجد' WHERE discord_id = ?", (ctx.author.id,))
    db_conn.commit()
    
    embed = discord.Embed(
        title="📄 تقديم استقالة",
        description=f"تم تقديم استقالتك بنجاح ياعضونا {ctx.author.mention} وتحويل حالتك إلى مواطن.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)


@bot.command(name="ping")
async def check_ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 سرعة استجابة البوت الحالية: **{latency}ms** (شغال وبأفضل أداء 🔥)")


# تشغيل البوت رسمياً
bot.run(TOKEN)
