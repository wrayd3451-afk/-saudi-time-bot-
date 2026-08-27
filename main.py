import os
import sqlite3
import discord
from discord.ext import commands
from discord import app_commands

# =========================================================
# إعدادات البوت
# =========================================================
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "-"

if not TOKEN:
    raise RuntimeError("ضع DISCORD_TOKEN في متغيرات البيئة قبل تشغيل البوت.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# =========================================================
# قاعدة البيانات - النقاط + إعدادات السيرفر
# =========================================================
db = sqlite3.connect("wolf_style_bot.db")
db.execute("""
CREATE TABLE IF NOT EXISTS points (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER PRIMARY KEY,
    flight_channel INTEGER,
    ticket_category INTEGER,
    log_channel INTEGER
)
""")
db.commit()

def get_points(guild_id, user_id):
    row = db.execute(
        "SELECT points FROM points WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    ).fetchone()
    return row[0] if row else 0

def add_points(guild_id, user_id, amount):
    current = get_points(guild_id, user_id)
    db.execute("""
        INSERT INTO points(guild_id,user_id,points)
        VALUES(?,?,?)
        ON CONFLICT(guild_id,user_id)
        DO UPDATE SET points=excluded.points
    """, (guild_id, user_id, current + amount))
    db.commit()
    return current + amount

def set_points(guild_id, user_id, amount):
    db.execute("""
        INSERT INTO points(guild_id,user_id,points)
        VALUES(?,?,?)
        ON CONFLICT(guild_id,user_id)
        DO UPDATE SET points=excluded.points
    """, (guild_id, user_id, amount))
    db.commit()

def get_setting(guild_id, name):
    row = db.execute(
        f"SELECT {name} FROM settings WHERE guild_id=?",
        (guild_id,)
    ).fetchone()
    return row[0] if row else None

def set_setting(guild_id, name, value):
    db.execute(
        "INSERT OR IGNORE INTO settings(guild_id) VALUES(?)",
        (guild_id,)
    )
    db.execute(f"UPDATE settings SET {name}=? WHERE guild_id=?", (value, guild_id))
    db.commit()

# =========================================================
# أدوات مساعدة
# =========================================================
async def log_action(guild, text):
    channel_id = get_setting(guild.id, "log_channel")
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(text)
            except discord.HTTPException:
                pass

def admin_only():
    return commands.has_permissions(administrator=True)

# =========================================================
# مودال الرحلة
# =========================================================
class FlightModal(discord.ui.Modal, title="✈️ إنشاء رحلة"):
    host_id = discord.ui.TextInput(label="آيدي الهوست", placeholder="مثال: 12345")
    assistant = discord.ui.TextInput(label="مساعد الهوست", placeholder="اسم أو منشن")
    time = discord.ui.TextInput(label="موعد الرحلة", placeholder="مثال: 9:30 PM")
    supervisor = discord.ui.TextInput(label="رقابي الرحلة", placeholder="اسم أو منشن")

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = get_setting(interaction.guild.id, "flight_channel")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None

        if channel is None:
            await interaction.response.send_message(
                "❌ لم يتم تحديد روم الرحلات. استخدم `-تعيين_رحلات #الروم`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✈️ تفاصيل الرحلة الجديدة",
            color=discord.Color.blurple()
        )
        embed.add_field(name="🆔 آيدي الهوست", value=self.host_id.value, inline=False)
        embed.add_field(name="👥 مساعد الهوست", value=self.assistant.value, inline=False)
        embed.add_field(name="⏰ الموعد", value=self.time.value, inline=False)
        embed.add_field(name="🛡️ الرقابي", value=self.supervisor.value, inline=False)
        embed.set_footer(text=f"بواسطة {interaction.user}")

        await channel.send(embed=embed)
        await log_action(interaction.guild, f"✈️ {interaction.user.mention} نشر رحلة.")
        await interaction.response.send_message("✅ تم نشر الرحلة بنجاح.", ephemeral=True)

# =========================================================
# نظام التفعيل
# =========================================================
class ActivationModal(discord.ui.Modal, title="✅ تفعيل عضو"):
    member = discord.ui.TextInput(label="منشن العضو", placeholder="@الشخص")
    psn = discord.ui.TextInput(label="آيدي سوني", placeholder="PSN ID")

    async def on_submit(self, interaction: discord.Interaction):
        member = None
        if interaction.message:
            member = interaction.guild.get_member(interaction.user.id)

        add_points(interaction.guild.id, interaction.user.id, 10)

        embed = discord.Embed(
            title="✅ تم التفعيل بنجاح",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 العضو", value=self.member.value, inline=False)
        embed.add_field(name="🎮 آيدي سوني", value=self.psn.value, inline=False)
        embed.add_field(name="🛡️ الإداري المفعل", value=interaction.user.mention, inline=False)
        embed.add_field(name="⭐ النقاط", value="+10", inline=False)

        await interaction.channel.send(embed=embed)
        await log_action(interaction.guild, f"✅ {interaction.user.mention} فعّل عضوًا وأضاف له النظام 10 نقاط للإداري.")
        await interaction.response.send_message("تم التفعيل وإضافة 10 نقاط لك.", ephemeral=True)

# =========================================================
# التذاكر
# =========================================================
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="إغلاق التذكرة 🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_permanent"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ تحتاج صلاحية إدارة القنوات.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 سيتم إغلاق التذكرة.", ephemeral=True)
        await log_action(interaction.guild, f"🔒 {interaction.user.mention} أغلق {interaction.channel.mention}.")
        await interaction.channel.delete()

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="فتح تذكرة 🎫",
        style=discord.ButtonStyle.success,
        custom_id="ticket_open_permanent"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        # منع فتح تذاكر متعددة بالاسم نفسه
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{member.id}")
        if existing:
            await interaction.response.send_message(
                f"⚠️ عندك تذكرة مفتوحة بالفعل: {existing.mention}",
                ephemeral=True
            )
            return

        category_id = get_setting(guild.id, "ticket_category")
        category = guild.get_channel(category_id) if category_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            overwrites=overwrites,
            category=category
        )

        embed = discord.Embed(
            title="🎫 تذكرة جديدة",
            description=(
                f"مرحبًا {member.mention}\n"
                "اكتب طلبك هنا، وانتظر الإدارة.\n\n"
                "يمكن للإدارة إغلاق التذكرة من الزر."
            ),
            color=discord.Color.blurple()
        )

        await channel.send(embed=embed, view=TicketCloseView())
        await interaction.response.send_message(
            f"✅ تم فتح تذكرتك: {channel.mention}",
            ephemeral=True
        )
        await log_action(guild, f"🎫 {member.mention} فتح تذكرة {channel.mention}.")

# =========================================================
# الوظائف
# =========================================================
class JobsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def choose(self, interaction, job):
        add_points(interaction.guild.id, interaction.user.id, 15)
        await interaction.response.send_message(
            f"✅ تم تسجيلك في وظيفة **{job}** وإضافة 15 نقطة.",
            ephemeral=True
        )
        await log_action(
            interaction.guild,
            f"📋 {interaction.user.mention} اختار وظيفة **{job}**."
        )

    @discord.ui.button(
        label="مدير إداري",
        style=discord.ButtonStyle.primary,
        custom_id="job_manager_permanent"
    )
    async def manager(self, interaction, button):
        await self.choose(interaction, "مدير إداري")

    @discord.ui.button(
        label="مسؤول تذاكر",
        style=discord.ButtonStyle.success,
        custom_id="job_ticket_permanent"
    )
    async def tickets(self, interaction, button):
        await self.choose(interaction, "مسؤول تذاكر")

    @discord.ui.button(
        label="مراقب عام",
        style=discord.ButtonStyle.secondary,
        custom_id="job_monitor_permanent"
    )
    async def monitor(self, interaction, button):
        await self.choose(interaction, "مراقب عام")

# =========================================================
# لوحة التحكم الرئيسية
# =========================================================
class MainPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="التذاكر 🎫",
        style=discord.ButtonStyle.success,
        row=0,
        custom_id="main_ticket_permanent"
    )
    async def tickets(self, interaction, button):
        embed = discord.Embed(
            title="🎫 نظام التذاكر",
            description="اضغط على الزر لفتح تذكرة جديدة.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(
            embed=embed,
            view=TicketView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="الوظائف 📋",
        style=discord.ButtonStyle.primary,
        row=0,
        custom_id="main_jobs_permanent"
    )
    async def jobs(self, interaction, button):
        embed = discord.Embed(
            title="📋 الوظائف والتوظيف",
            description="اختر الوظيفة المناسبة.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(
            embed=embed,
            view=JobsView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="نقاطي ⭐",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="main_points_permanent"
    )
    async def points(self, interaction, button):
        pts = get_points(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"⭐ رصيدك الحالي: **{pts}** نقطة.",
            ephemeral=True
        )

    @discord.ui.button(
        label="رحلة ✈️",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="main_flight_permanent"
    )
    async def flight(self, interaction, button):
        await interaction.response.send_modal(FlightModal())

    @discord.ui.button(
        label="تفعيل ✅",
        style=discord.ButtonStyle.success,
        row=1,
        custom_id="main_activate_permanent"
    )
    async def activate(self, interaction, button):
        await interaction.response.send_modal(ActivationModal())

    @discord.ui.button(
        label="مساعدة ℹ️",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="main_help_permanent"
    )
    async def help(self, interaction, button):
        await interaction.response.send_message(
            "🎛️ **لوحة النظام**\n"
            "🎫 التذاكر — فتح تذكرة\n"
            "📋 الوظائف — اختيار وظيفة\n"
            "⭐ نقاطي — عرض الرصيد\n"
            "✈️ رحلة — إنشاء رحلة\n"
            "✅ تفعيل — تفعيل عضو",
            ephemeral=True
        )

# =========================================================
# أحداث البوت
# =========================================================
@bot.event
async def on_ready():
    # تسجيل الأزرار الدائمة مرة واحدة عند تشغيل البوت
    bot.add_view(MainPanel())
    bot.add_view(TicketView())
    bot.add_view(TicketCloseView())
    bot.add_view(JobsView())

    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)

    print(f"Logged in as {bot.user} | النظام جاهز.")

# =========================================================
# أمر إرسال اللوحة
# =========================================================
@bot.command(name="لوحه")
@admin_only()
async def panel(ctx):
    embed = discord.Embed(
        title="🎛️ لوحة التحكم المركزية",
        description=(
            "اختر الخدمة المطلوبة من الأزرار بالأسفل.\n\n"
            "🎫 التذاكر\n"
            "📋 الوظائف والتوظيف\n"
            "⭐ النقاط\n"
            "✈️ الرحلات\n"
            "✅ التفعيل"
        ),
        color=discord.Color.dark_embed()
    )
    embed.set_footer(text="Wolf Style System")
    await ctx.send(embed=embed, view=MainPanel())

# =========================================================
# أوامر إضافية
# =========================================================
@bot.command(name="نقاط")
async def points(ctx, member: discord.Member = None):
    target = member or ctx.author
    pts = get_points(ctx.guild.id, target.id)
    await ctx.send(f"⭐ {target.mention} لديه **{pts}** نقطة.")

@bot.command(name="اعطاء")
@commands.has_permissions(administrator=True)
async def give_points(ctx, member: discord.Member, amount: int):
    if amount < 0:
        await ctx.send("❌ لا يمكن إضافة رقم سالب.")
        return
    total = add_points(ctx.guild.id, member.id, amount)
    await ctx.send(f"✅ تمت إضافة **{amount}** نقطة إلى {member.mention}. الرصيد: **{total}**.")

@bot.command(name="خصم")
@commands.has_permissions(administrator=True)
async def remove_points(ctx, member: discord.Member, amount: int):
    if amount < 0:
        await ctx.send("❌ استخدم رقمًا موجبًا.")
        return
    total = max(0, get_points(ctx.guild.id, member.id) - amount)
    set_points(ctx.guild.id, member.id, total)
    await ctx.send(f"✅ تم خصم **{amount}** نقطة من {member.mention}. الرصيد: **{total}**.")

@bot.command(name="تعيين_رحلات")
@admin_only()
async def set_flights(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "flight_channel", channel.id)
    await ctx.send(f"✅ تم تعيين {channel.mention} كروم للرحلات.")

@bot.command(name="تعيين_لوق")
@admin_only()
async def set_logs(ctx, channel: discord.TextChannel):
    set_setting(ctx.guild.id, "log_channel", channel.id)
    await ctx.send(f"✅ تم تعيين {channel.mention} كروم للسجلات.")

@bot.command(name="تعيين_تذاكر")
@admin_only()
async def set_ticket_category(ctx, category: discord.CategoryChannel):
    set_setting(ctx.guild.id, "ticket_category", category.id)
    await ctx.send(f"✅ تم تعيين الكاتقوري {category.name} للتذاكر.")

@bot.command(name="مساعدة")
async def help_command(ctx):
    await ctx.send(
        "🎛️ **الأوامر:**\n"
        "`-لوحه` — إرسال لوحة التحكم\n"
        "`-نقاط` — عرض نقاطك\n"
        "`-نقاط @عضو` — عرض نقاط عضو\n"
        "`-اعطاء @عضو 10` — إضافة نقاط (إدارة)\n"
        "`-خصم @عضو 10` — خصم نقاط (إدارة)\n"
        "`-تعيين_رحلات #روم` — تحديد روم الرحلات\n"
        "`-تعيين_لوق #روم` — تحديد روم السجلات\n"
        "`-تعيين_تذاكر اسم-الكاتقوري` — تحديد قسم التذاكر"
    )

# =========================================================
# تشغيل
# =========================================================
bot.run(TOKEN)
