import os
import sqlite3
import discord
from discord.ext import commands
from discord import app_commands

# =========================================================
# CONFIG
# =========================================================
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "-"

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN غير موجود في Environment Variables.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# =========================================================
# DATABASE
# =========================================================
db = sqlite3.connect("server_system.db")
db.execute("""
CREATE TABLE IF NOT EXISTS points (
    guild_id INTEGER,
    user_id INTEGER,
    points INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(guild_id,user_id)
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS bank (
    guild_id INTEGER,
    user_id INTEGER,
    cash INTEGER NOT NULL DEFAULT 0,
    bank INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(guild_id,user_id)
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER PRIMARY KEY,
    ticket_category INTEGER,
    ticket_log INTEGER,
    flight_channel INTEGER,
    activation_channel INTEGER,
    announcement_channel INTEGER,
    general_log INTEGER,
    bank_log INTEGER,
    staff_role INTEGER,
    bank_role INTEGER,
    activated_role INTEGER
)
""")
db.commit()

def ensure_settings(guild_id):
    db.execute("INSERT OR IGNORE INTO settings(guild_id) VALUES(?)", (guild_id,))
    db.commit()

def get_setting(guild_id, key):
    ensure_settings(guild_id)
    return db.execute(f"SELECT {key} FROM settings WHERE guild_id=?", (guild_id,)).fetchone()[0]

def set_setting(guild_id, key, value):
    ensure_settings(guild_id)
    db.execute(f"UPDATE settings SET {key}=? WHERE guild_id=?", (value, guild_id))
    db.commit()

def get_points(guild_id, user_id):
    row = db.execute("SELECT points FROM points WHERE guild_id=? AND user_id=?",
                     (guild_id, user_id)).fetchone()
    return row[0] if row else 0

def add_points(guild_id, user_id, amount):
    current = get_points(guild_id, user_id)
    new = current + amount
    db.execute("""
        INSERT INTO points(guild_id,user_id,points) VALUES(?,?,?)
        ON CONFLICT(guild_id,user_id) DO UPDATE SET points=excluded.points
    """, (guild_id, user_id, new))
    db.commit()
    return new

def bank_account(guild_id, user_id):
    row = db.execute("SELECT cash,bank FROM bank WHERE guild_id=? AND user_id=?",
                     (guild_id, user_id)).fetchone()
    if row:
        return row
    db.execute("INSERT INTO bank(guild_id,user_id,cash,bank) VALUES(?,?,0,0)",
               (guild_id, user_id))
    db.commit()
    return (0, 0)

def set_bank(guild_id, user_id, cash, balance):
    db.execute("""
        INSERT INTO bank(guild_id,user_id,cash,bank) VALUES(?,?,?,?)
        ON CONFLICT(guild_id,user_id)
        DO UPDATE SET cash=excluded.cash, bank=excluded.bank
    """, (guild_id, user_id, cash, balance))
    db.commit()

def money(n):
    return f"{n:,}$"

async def log(guild, text, kind="general_log"):
    channel_id = get_setting(guild.id, kind)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(text)
            except discord.HTTPException:
                pass

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

# =========================================================
# TICKETS
# =========================================================
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger,
                       custom_id="ticket_close_v2")
    async def close(self, interaction, button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "❌ تحتاج صلاحية إدارة القنوات.", ephemeral=True)
        await interaction.response.send_message("🔒 جاري إغلاق التذكرة...", ephemeral=True)
        await log(interaction.guild, f"🔒 {interaction.user.mention} أغلق {interaction.channel.mention}.",
                  "ticket_log")
        await interaction.channel.delete()

class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_ticket(self, interaction, ticket_type):
        guild = interaction.guild
        member = interaction.user

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{member.id}")
        if existing:
            return await interaction.response.send_message(
                f"⚠️ عندك تذكرة مفتوحة: {existing.mention}", ephemeral=True)

        category_id = get_setting(guild.id, "ticket_category")
        category = guild.get_channel(category_id) if category_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_channels=True)
        }

        staff_role_id = get_setting(guild.id, "staff_role")
        if staff_role_id:
            role = guild.get_role(staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            f"ticket-{member.id}", overwrites=overwrites, category=category)

        embed = discord.Embed(
            title=f"🎫 تذكرة {ticket_type}",
            description=f"مرحبًا {member.mention}\nاكتب طلبك هنا وانتظر الإدارة.",
            color=discord.Color.blurple())
        await channel.send(embed=embed, view=TicketCloseView())
        await interaction.response.send_message(
            f"✅ تم فتح التذكرة: {channel.mention}", ephemeral=True)
        await log(guild, f"🎫 {member.mention} فتح تذكرة **{ticket_type}**: {channel.mention}",
                  "ticket_log")

    @discord.ui.button(label="دعم فني", style=discord.ButtonStyle.primary,
                       custom_id="ticket_support_v2")
    async def support(self, interaction, button):
        await self.create_ticket(interaction, "دعم فني")

    @discord.ui.button(label="تفعيل", style=discord.ButtonStyle.success,
                       custom_id="ticket_activation_v2")
    async def activation(self, interaction, button):
        await self.create_ticket(interaction, "تفعيل")

    @discord.ui.button(label="شكوى", style=discord.ButtonStyle.danger,
                       custom_id="ticket_complaint_v2")
    async def complaint(self, interaction, button):
        await self.create_ticket(interaction, "شكوى")

    @discord.ui.button(label="توظيف", style=discord.ButtonStyle.secondary,
                       custom_id="ticket_recruitment_v2")
    async def recruitment(self, interaction, button):
        await self.create_ticket(interaction, "توظيف")

# =========================================================
# JOBS
# =========================================================
class JobsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def job(self, interaction, name):
        add_points(interaction.guild.id, interaction.user.id, 15)
        await interaction.response.send_message(
            f"✅ تم تقديمك على **{name}** وإضافة 15 نقطة.", ephemeral=True)
        await log(interaction.guild, f"📋 {interaction.user.mention} اختار وظيفة **{name}**.")

    @discord.ui.button(label="إدارة 👑", style=discord.ButtonStyle.primary,
                       custom_id="job_admin_v2")
    async def admin_job(self, interaction, button):
        await self.job(interaction, "الإدارة")

    @discord.ui.button(label="تذاكر 🎫", style=discord.ButtonStyle.success,
                       custom_id="job_ticket_v2")
    async def ticket_job(self, interaction, button):
        await self.job(interaction, "مسؤول تذاكر")

    @discord.ui.button(label="مراقبة 🛡️", style=discord.ButtonStyle.secondary,
                       custom_id="job_monitor_v2")
    async def monitor_job(self, interaction, button):
        await self.job(interaction, "مراقب عام")

# =========================================================
# BANK
# =========================================================
class BankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💳 حسابي", style=discord.ButtonStyle.primary,
                       custom_id="bank_account_v2")
    async def account(self, interaction, button):
        cash, balance = bank_account(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"💳 **حسابك البنكي**\n💵 كاش: **{money(cash)}**\n🏦 البنك: **{money(balance)}**",
            ephemeral=True)

    @discord.ui.button(label="💸 تحويل", style=discord.ButtonStyle.success,
                       custom_id="bank_transfer_v2")
    async def transfer(self, interaction, button):
        await interaction.response.send_message(
            "استخدم الأمر:\n`-تحويل @العضو المبلغ`", ephemeral=True)

    @discord.ui.button(label="📊 كشف حساب", style=discord.ButtonStyle.secondary,
                       custom_id="bank_statement_v2")
    async def statement(self, interaction, button):
        cash, balance = bank_account(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"📊 **كشف الحساب**\nالرصيد البنكي: **{money(balance)}**\nالكاش: **{money(cash)}**",
            ephemeral=True)

# =========================================================
# MAIN PANEL
# =========================================================
class MainPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 التذاكر", style=discord.ButtonStyle.success,
                       row=0, custom_id="main_tickets_v2")
    async def tickets(self, interaction, button):
        await interaction.response.send_message(
            "🎫 اختر نوع التذكرة:", view=TicketTypeView(), ephemeral=True)

    @discord.ui.button(label="📋 الوظائف", style=discord.ButtonStyle.primary,
                       row=0, custom_id="main_jobs_v2")
    async def jobs(self, interaction, button):
        await interaction.response.send_message(
            "📋 اختر الوظيفة:", view=JobsView(), ephemeral=True)

    @discord.ui.button(label="⭐ نقاطي", style=discord.ButtonStyle.secondary,
                       row=0, custom_id="main_points_v2")
    async def points(self, interaction, button):
        pts = get_points(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"⭐ رصيدك: **{pts} نقطة**.", ephemeral=True)

    @discord.ui.button(label="🏦 البنك", style=discord.ButtonStyle.primary,
                       row=1, custom_id="main_bank_v2")
    async def bank(self, interaction, button):
        await interaction.response.send_message(
            "🏦 **البنك**", view=BankView(), ephemeral=True)

    @discord.ui.button(label="✈️ الرحلات", style=discord.ButtonStyle.primary,
                       row=1, custom_id="main_flights_v2")
    async def flights(self, interaction, button):
        await interaction.response.send_message(
            "استخدم الأمر `-رحله` لإنشاء رحلة.", ephemeral=True)

    @discord.ui.button(label="✅ التفعيل", style=discord.ButtonStyle.success,
                       row=1, custom_id="main_activation_v2")
    async def activation(self, interaction, button):
        await interaction.response.send_message(
            "استخدم الأمر `-تفعيل @العضو PSN_ID`.", ephemeral=True)

    @discord.ui.button(label="📢 التعاميم", style=discord.ButtonStyle.secondary,
                       row=2, custom_id="main_announcements_v2")
    async def announcements(self, interaction, button):
        if not is_admin(interaction):
            return await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
        await interaction.response.send_message(
            "استخدم `-تعميم نص الرسالة`.", ephemeral=True)

    @discord.ui.button(label="⚙️ التسطيب", style=discord.ButtonStyle.danger,
                       row=2, custom_id="main_setup_v2")
    async def setup(self, interaction, button):
        if not is_admin(interaction):
            return await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
        await interaction.response.send_message(
            "⚙️ **تسطيب الأنظمة**\n"
            "`-تعيين_تذاكر #كاتقوري`\n"
            "`-تعيين_لوق_تذاكر #روم`\n"
            "`-تعيين_لوق #روم`\n"
            "`-تعيين_رحلات #روم`\n"
            "`-تعيين_تفعيل #روم`\n"
            "`-تعيين_تعاميم #روم`\n"
            "`-تعيين_ادارة @رتبة`\n"
            "`-تعيين_بنك @رتبة`\n"
            "`-تعيين_متفعل @رتبة`\n"
            "كل الإعدادات محفوظة في قاعدة البيانات.",
            ephemeral=True)

# =========================================================
# READY
# =========================================================
@bot.event
async def on_ready():
    bot.add_view(MainPanel())
    bot.add_view(TicketTypeView())
    bot.add_view(TicketCloseView())
    bot.add_view(JobsView())
    bot.add_view(BankView())
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)
    print(f"Logged in as {bot.user}")

# =========================================================
# SLASH COMMANDS
# =========================================================
@bot.tree.command(name="لوحه", description="فتح لوحة تحكم السيرفر")
@app_commands.default_permissions(administrator=True)
async def slash_panel(interaction):
    embed = discord.Embed(
        title="🎛️ لوحة التحكم المركزية",
        description="التذاكر • الوظائف • النقاط • البنك • الرحلات • التفعيل • التسطيب",
        color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, view=MainPanel())

@bot.tree.command(name="بنك", description="فتح نظام البنك")
async def slash_bank(interaction):
    await interaction.response.send_message("🏦 **البنك**", view=BankView(), ephemeral=True)

# =========================================================
# TEXT COMMANDS
# =========================================================
@bot.command(name="لوحه")
@commands.has_permissions(administrator=True)
async def text_panel(ctx):
    await ctx.send("🎛️ **لوحة التحكم المركزية**", view=MainPanel())

@bot.command(name="نقاط")
async def points(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ctx.send(f"⭐ {target.mention} لديه **{get_points(ctx.guild.id, target.id)} نقطة**.")

@bot.command(name="اعطاء")
@commands.has_permissions(administrator=True)
async def give(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("❌ استخدم رقمًا موجبًا.")
    total = add_points(ctx.guild.id, member.id, amount)
    await ctx.send(f"✅ تمت إضافة **{amount}** نقطة إلى {member.mention}. الرصيد: **{total}**.")

@bot.command(name="خصم")
@commands.has_permissions(administrator=True)
async def take(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("❌ استخدم رقمًا موجبًا.")
    current = get_points(ctx.guild.id, member.id)
    total = max(0, current - amount)
    # إعادة ضبط الرصيد باستخدام نفس قاعدة البيانات
    db.execute("""
        INSERT INTO points(guild_id,user_id,points) VALUES(?,?,?)
        ON CONFLICT(guild_id,user_id) DO UPDATE SET points=excluded.points
    """, (ctx.guild.id, member.id, total))
    db.commit()
    await ctx.send(f"✅ تم خصم **{amount}** نقطة. الرصيد: **{total}**.")

@bot.command(name="تحويل")
async def transfer(ctx, member: discord.Member, amount: int):
    if amount <= 0 or member.id == ctx.author.id:
        return await ctx.send("❌ بيانات التحويل غير صحيحة.")
    cash, balance = bank_account(ctx.guild.id, ctx.author.id)
    target_cash, target_balance = bank_account(ctx.guild.id, member.id)
    if balance < amount:
        return await ctx.send("❌ رصيدك البنكي لا يكفي.")
    set_bank(ctx.guild.id, ctx.author.id, cash, balance - amount)
    set_bank(ctx.guild.id, member.id, target_cash, target_balance + amount)
    await ctx.send(f"💸 تم تحويل **{money(amount)}** إلى {member.mention}.")
    await log(ctx.guild, f"💸 {ctx.author.mention} حوّل {money(amount)} إلى {member.mention}.",
              "bank_log")

@bot.command(name="ايداع")
async def deposit(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("❌ استخدم مبلغًا موجبًا.")
    cash, balance = bank_account(ctx.guild.id, ctx.author.id)
    if cash < amount:
        return await ctx.send("❌ ما عندك كاش كافي.")
    set_bank(ctx.guild.id, ctx.author.id, cash - amount, balance + amount)
    await ctx.send(f"🏦 تم إيداع **{money(amount)}**.")

@bot.command(name="سحب")
async def withdraw(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("❌ استخدم مبلغًا موجبًا.")
    cash, balance = bank_account(ctx.guild.id, ctx.author.id)
    if balance < amount:
        return await ctx.send("❌ رصيد البنك لا يكفي.")
    set_bank(ctx.guild.id, ctx.author.id, cash + amount, balance - amount)
    await ctx.send(f"💵 تم سحب **{money(amount)}**.")

@bot.command(name="حسابي")
async def my_account(ctx):
    cash, balance = bank_account(ctx.guild.id, ctx.author.id)
    await ctx.send(
        f"💳 **حساب {ctx.author.mention}**\n"
        f"💵 الكاش: **{money(cash)}**\n"
        f"🏦 البنك: **{money(balance)}**")

@bot.command(name="تعيين_تذاكر")
@commands.has_permissions(administrator=True)
async def set_ticket_category(ctx, category: discord.CategoryChannel):
    set_setting(ctx.guild.id, "ticket_category", category.id)
    await ctx.send(f"✅ تم تعيين قسم التذاكر: **{category.name}**.")

@bot.command(name="تعيين_لوق_تذاكر")
@commands.has_permissions(administrator=True)
async def set_ticket_log(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "ticket_log", channel.id)
    await ctx.send(f"✅ تم تعيين لوق التذاكر: {channel.mention}")

@bot.command(name="تعيين_لوق")
@commands.has_permissions(administrator=True)
async def set_general_log(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "general_log", channel.id)
    await ctx.send(f"✅ تم تعيين اللوق العام: {channel.mention}")

@bot.command(name="تعيين_بنك")
@commands.has_permissions(administrator=True)
async def set_bank_role(ctx, role: discord.Role):
    set_setting(ctx.guild.id, "bank_role", role.id)
    await ctx.send(f"✅ تم تعيين رتبة موظفي البنك: {role.mention}")

@bot.command(name="تعيين_ادارة")
@commands.has_permissions(administrator=True)
async def set_staff_role(ctx, role: discord.Role):
    set_setting(ctx.guild.id, "staff_role", role.id)
    await ctx.send(f"✅ تم تعيين رتبة الإدارة: {role.mention}")

@bot.command(name="تعيين_متفعل")
@commands.has_permissions(administrator=True)
async def set_activated_role(ctx, role: discord.Role):
    set_setting(ctx.guild.id, "activated_role", role.id)
    await ctx.send(f"✅ تم تعيين رتبة المتفعل: {role.mention}")

@bot.command(name="تعيين_رحلات")
@commands.has_permissions(administrator=True)
async def set_flight_channel(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "flight_channel", channel.id)
    await ctx.send(f"✅ تم تعيين روم الرحلات: {channel.mention}")

@bot.command(name="تعيين_تفعيل")
@commands.has_permissions(administrator=True)
async def set_activation_channel(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "activation_channel", channel.id)
    await ctx.send(f"✅ تم تعيين روم التفعيل: {channel.mention}")

@bot.command(name="تعيين_تعاميم")
@commands.has_permissions(administrator=True)
async def set_announcement_channel(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "announcement_channel", channel.id)
    await ctx.send(f"✅ تم تعيين روم التعاميم: {channel.mention}")

@bot.command(name="تعميم")
@commands.has_permissions(administrator=True)
async def announcement(ctx, *, text: str):
    channel_id = get_setting(ctx.guild.id, "announcement_channel")
    channel = ctx.guild.get_channel(channel_id) if channel_id else None
    if not channel:
        return await ctx.send("❌ عيّن روم التعاميم أولًا.")
    embed = discord.Embed(title="📢 تعميم", description=text,
                          color=discord.Color.orange())
    embed.set_footer(text=f"بواسطة {ctx.author}")
    await channel.send(embed=embed)
    await ctx.send("✅ تم إرسال التعميم.")

@bot.command(name="رحله")
@commands.has_permissions(administrator=True)
async def flight(ctx, host="غير محدد", assistant="غير محدد", time="غير محدد", supervisor="غير محدد"):
    channel_id = get_setting(ctx.guild.id, "flight_channel")
    channel = ctx.guild.get_channel(channel_id) if channel_id else None
    if not channel:
        return await ctx.send("❌ عيّن روم الرحلات أولًا.")
    embed = discord.Embed(title="✈️ تفاصيل الرحلة الجديدة",
                          color=discord.Color.blurple())
    embed.add_field(name="🆔 الهوست", value=host, inline=False)
    embed.add_field(name="👥 مساعد الهوست", value=assistant, inline=False)
    embed.add_field(name="⏰ الموعد", value=time, inline=False)
    embed.add_field(name="🛡️ الرقابي", value=supervisor, inline=False)
    await channel.send(embed=embed)
    await ctx.send("✅ تم نشر الرحلة.")

@bot.command(name="تفعيل")
@commands.has_permissions(manage_roles=True)
async def activate(ctx, member: discord.Member, *, psn_id="غير محدد"):
    role_id = get_setting(ctx.guild.id, "activated_role")
    role = ctx.guild.get_role(role_id) if role_id else None
    if role:
        try:
            await member.add_roles(role, reason=f"تفعيل بواسطة {ctx.author}")
        except discord.Forbidden:
            return await ctx.send("❌ البوت لا يستطيع إعطاء رتبة التفعيل. ارفع رتبة البوت.")
    add_points(ctx.guild.id, ctx.author.id, 10)
    embed = discord.Embed(title="✅ تم التفعيل بنجاح",
                          color=discord.Color.green())
    embed.add_field(name="👤 العضو", value=member.mention, inline=False)
    embed.add_field(name="🎮 PSN", value=psn_id, inline=False)
    embed.add_field(name="🛡️ الإداري", value=ctx.author.mention, inline=False)
    embed.add_field(name="⭐ النقاط", value="+10", inline=False)
    await ctx.send(embed=embed)
    await log(ctx.guild, f"✅ {ctx.author.mention} فعّل {member.mention}.", "general_log")

@bot.command(name="توظيف")
async def jobs(ctx):
    await ctx.send("📋 **لوحة الوظائف**", view=JobsView())

@bot.command(name="تذاكر")
async def tickets(ctx):
    await ctx.send("🎫 **اختر نوع التذكرة**", view=TicketTypeView())

@bot.command(name="بنك")
async def bank(ctx):
    await ctx.send("🏦 **نظام البنك**", view=BankView())

# =========================================================
# ERROR HANDLER
# =========================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ ما عندك الصلاحية.")
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send("❌ ناقص بيانات. استخدم `-مساعدة`.")
    if isinstance(error, commands.BadArgument):
        return await ctx.send("❌ تأكد من المنشن/الرقم/القناة.")
    print("Command error:", repr(error))

@bot.command(name="مساعدة")
async def help_cmd(ctx):
    await ctx.send(
        "🎛️ **أهم الأوامر**\n"
        "`/لوحه` — لوحة التحكم\n"
        "`-تذاكر` — نظام التذاكر\n"
        "`-توظيف` — الوظائف\n"
        "`-بنك` — البنك\n"
        "`-حسابي` — حسابك\n"
        "`-ايداع 100` — إيداع\n"
        "`-سحب 100` — سحب\n"
        "`-تحويل @عضو 100` — تحويل\n"
        "`-نقاط` — النقاط\n"
        "`-تفعيل @عضو PSN` — تفعيل\n"
        "`-رحله الهوست المساعد الموعد الرقابي` — رحلة\n"
        "`-تعميم النص` — تعميم\n"
        "⚙️ أو استخدم زر التسطيب من `/لوحه`."
    )

bot.run(TOKEN)
