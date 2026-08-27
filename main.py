import os
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"تم تسجيل الدخول: {bot.user}")
        print(f"تمت مزامنة {len(synced)} أمر Slash")
    except Exception as e:
        print(f"خطأ في مزامنة الأوامر: {e}")


@bot.tree.command(name="لوحه", description="فتح لوحة تحكم السيرفر")
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎛️ لوحة تحكم السيرفر",
        description="اختر النظام الذي تريد استخدامه من الأزرار بالأسفل.",
    )

    view = discord.ui.View(timeout=None)

    buttons = [
        ("🎫 التذاكر", "tickets"),
        ("✅ التفعيل", "verify"),
        ("⭐ النقاط", "points"),
        ("🏦 البنك", "bank"),
        ("👮 الوظائف", "jobs"),
        ("✈️ الرحلات", "trips"),
        ("📢 التعاميم", "announcements"),
        ("⚙️ التسطيب", "setup"),
    ]

    for text, custom_id in buttons:
        view.add_item(
            discord.ui.Button(
                label=text,
                style=discord.ButtonStyle.primary,
                custom_id=custom_id
            )
        )

    await interaction.response.send_message(embed=embed, view=view)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    cid = interaction.data.get("custom_id")

    messages = {
        "tickets": "🎫 نظام التذاكر\nسيتم فتح نظام التذاكر هنا.",
        "verify": "✅ نظام التفعيل\nسيتم إعداد نظام التفعيل هنا.",
        "points": "⭐ نظام النقاط\nسيتم إعداد النقاط هنا.",
        "bank": "🏦 نظام البنك\nسيتم إعداد البنك هنا.",
        "jobs": "👮 نظام الوظائف والقطاعات.",
        "trips": "✈️ نظام الرحلات.",
        "announcements": "📢 نظام التعاميم.",
        "setup": "⚙️ **التسطيب**\nاختر النظام الذي تريد تسطيبه."
    }

    if cid in messages:
        await interaction.response.send_message(
            messages[cid],
            ephemeral=True
        )


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN غير موجود في Environment Variables")

bot.run(TOKEN)
import os
import sqlite3
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB = "server.db"

def db():
    return sqlite3.connect(DB)

def setup_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY,
        tickets_category INTEGER,
        tickets_log INTEGER,
        verify_channel INTEGER,
        verify_role INTEGER,
        logs_channel INTEGER,
        trips_channel INTEGER,
        announcements_channel INTEGER,
        bank_log INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS points (
        guild_id INTEGER,
        user_id INTEGER,
        points INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bank (
        guild_id INTEGER,
        user_id INTEGER,
        balance INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    con.commit()
    con.close()


setup_db()


def get_settings(guild_id):
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM settings WHERE guild_id=?",
        (guild_id,)
    )

    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO settings (guild_id) VALUES (?)",
            (guild_id,)
        )
        con.commit()

        cur.execute(
            "SELECT * FROM settings WHERE guild_id=?",
            (guild_id,)
        )

        row = cur.fetchone()

    con.close()
    return row


class MainPanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 التذاكر",
        style=discord.ButtonStyle.primary,
        custom_id="panel:tickets"
    )
    async def tickets(self, interaction, button):

        embed = discord.Embed(
            title="🎫 تسطيب التذاكر",
            description=
            "من هنا تقدر تضبط نظام التذاكر كامل.\n\n"
            "📁 تحديد الكاتقوري\n"
            "📝 تحديد روم اللوق\n"
            "👮 تحديد رتبة الدعم\n"
            "🎟️ أنواع التذاكر"
        )

        await interaction.response.send_message(
            embed=embed,
            view=TicketSetup(),
            ephemeral=True
        )


    @discord.ui.button(
        label="✅ التفعيل",
        style=discord.ButtonStyle.success,
        custom_id="panel:verify"
    )
    async def verify(self, interaction, button):

        await interaction.response.send_message(
            "✅ **تسطيب التفعيل**\n\n"
            "اضغط الزر لاختيار روم التفعيل والرتبة.",
            view=VerifySetup(),
            ephemeral=True
        )


    @discord.ui.button(
        label="⭐ النقاط",
        style=discord.ButtonStyle.primary,
        custom_id="panel:points"
    )
    async def points(self, interaction, button):

        await interaction.response.send_message(
            "⭐ **نظام النقاط**\n\n"
            "يمكنك إدارة نقاط الأعضاء من هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="🏦 البنك",
        style=discord.ButtonStyle.primary,
        custom_id="panel:bank"
    )
    async def bank(self, interaction, button):

        await interaction.response.send_message(
            "🏦 **نظام البنك**\n\n"
            "💰 الرصيد\n"
            "💸 تحويل\n"
            "📊 كشف حساب\n"
            "🧾 سجل العمليات",
            ephemeral=True
        )


    @discord.ui.button(
        label="👮 الوظائف",
        style=discord.ButtonStyle.primary,
        custom_id="panel:jobs"
    )
    async def jobs(self, interaction, button):

        await interaction.response.send_message(
            "👮 **تسطيب الوظائف والقطاعات**\n\n"
            "من هنا يتم إعداد قطاعات السيرفر ورتبها.",
            ephemeral=True
        )


    @discord.ui.button(
        label="✈️ الرحلات",
        style=discord.ButtonStyle.primary,
        custom_id="panel:trips"
    )
    async def trips(self, interaction, button):

        await interaction.response.send_message(
            "✈️ **تسطيب الرحلات**\n\n"
            "حدد روم الرحلات من هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="📢 التعاميم",
        style=discord.ButtonStyle.primary,
        custom_id="panel:announcements"
    )
    async def announcements(self, interaction, button):

        await interaction.response.send_message(
            "📢 **تسطيب التعاميم**\n\n"
            "حدد روم التعاميم من هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="📝 اللوقات",
        style=discord.ButtonStyle.primary,
        custom_id="panel:logs"
    )
    async def logs(self, interaction, button):

        await interaction.response.send_message(
            "📝 **تسطيب اللوقات**\n\n"
            "حدد روم اللوقات لجميع عمليات البوت.",
            ephemeral=True
        )


    @discord.ui.button(
        label="🔐 الصلاحيات",
        style=discord.ButtonStyle.secondary,
        custom_id="panel:permissions"
    )
    async def permissions(self, interaction, button):

        await interaction.response.send_message(
            "🔐 **الصلاحيات**\n\n"
            "تقدر تحدد رتب الإدارة والدعم وموظفي البنك.",
            ephemeral=True
        )


class TicketSetup(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)


    @discord.ui.button(
        label="📁 تحديد الكاتقوري",
        style=discord.ButtonStyle.primary
    )
    async def category(self, interaction, button):

        await interaction.response.send_message(
            "أرسل **ID الكاتقوري** هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="📝 تحديد اللوق",
        style=discord.ButtonStyle.primary
    )
    async def log(self, interaction, button):

        await interaction.response.send_message(
            "أرسل **ID روم اللوق** هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="👮 رتبة الدعم",
        style=discord.ButtonStyle.primary
    )
    async def support(self, interaction, button):

        await interaction.response.send_message(
            "أرسل **ID رتبة الدعم** هنا.",
            ephemeral=True
        )


class VerifySetup(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)


    @discord.ui.button(
        label="📋 روم التفعيل",
        style=discord.ButtonStyle.primary
    )
    async def channel(self, interaction, button):

        await interaction.response.send_message(
            "أرسل **ID روم التفعيل** هنا.",
            ephemeral=True
        )


    @discord.ui.button(
        label="🏷️ رتبة المتفعل",
        style=discord.ButtonStyle.success
    )
    async def role(self, interaction, button):

        await interaction.response.send_message(
            "أرسل **ID رتبة المتفعل** هنا.",
            ephemeral=True
        )


@bot.tree.command(
    name="لوحه",
    description="فتح لوحة تحكم السيرفر"
)
async def panel(interaction):

    embed = discord.Embed(
        title="🎛️ لوحة تحكم السيرفر",
        description=
        "**مرحبًا بك في لوحة التحكم**\n\n"
        "⚙️ جميع التسطيبات والأنظمة موجودة هنا.\n"
        "اختر النظام الذي تريد إعداده."
    )

    embed.set_footer(
        text="Server Management System"
    )

    await interaction.response.send_message(
        embed=embed,
        view=MainPanel()
    )


@bot.event
async def on_ready():

    try:
        synced = await bot.tree.sync()

        print(
            f"تم تسجيل الدخول باسم: {bot.user}"
        )

        print(
            f"تمت مزامنة {len(synced)} أمر Slash"
        )

    except Exception as e:
        print(
            f"خطأ في مزامنة Slash Commands: {e}"
        )


if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN غير موجود"
    )

bot.run(TOKEN)
import os
import sqlite3
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

DB = "server.db"


# =========================
# DATABASE
# =========================

def database():
    return sqlite3.connect(DB)


def create_database():
    con = database()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            ticket_category INTEGER,
            ticket_log INTEGER,
            ticket_role INTEGER,
            verify_channel INTEGER,
            verify_role INTEGER,
            bank_channel INTEGER,
            bank_log INTEGER,
            bank_role INTEGER,
            points_log INTEGER,
            jobs_channel INTEGER,
            trips_channel INTEGER,
            announcements_channel INTEGER,
            logs_channel INTEGER,
            admin_role INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS points (
            guild_id INTEGER,
            user_id INTEGER,
            points INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    con.commit()
    con.close()


create_database()


def save_setting(guild_id, column, value):

    con = database()
    cur = con.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO settings (guild_id) VALUES (?)",
        (guild_id,)
    )

    cur.execute(
        f"UPDATE settings SET {column}=? WHERE guild_id=?",
        (value, guild_id)
    )

    con.commit()
    con.close()


def get_setting(guild_id, column):

    con = database()
    cur = con.cursor()

    cur.execute(
        f"SELECT {column} FROM settings WHERE guild_id=?",
        (guild_id,)
    )

    result = cur.fetchone()

    con.close()

    return result[0] if result else None


# =========================
# CHANNEL SELECT
# =========================

class ChannelSelect(discord.ui.ChannelSelect):

    def __init__(self, setting, placeholder):

        super().__init__(
            placeholder=placeholder,
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1
        )

        self.setting = setting

    async def callback(self, interaction):

        channel = self.values[0]

        save_setting(
            interaction.guild.id,
            self.setting,
            channel.id
        )

        await interaction.response.send_message(
            f"✅ تم حفظ الروم: {channel.mention}",
            ephemeral=True
        )


# =========================
# CATEGORY SELECT
# =========================

class CategorySelect(discord.ui.ChannelSelect):

    def __init__(self):

        super().__init__(
            placeholder="📁 اختر كاتقوري التذاكر",
            channel_types=[
                discord.ChannelType.category
            ],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):

        category = self.values[0]

        save_setting(
            interaction.guild.id,
            "ticket_category",
            category.id
        )

        await interaction.response.send_message(
            f"✅ تم تحديد كاتقوري التذاكر: **{category.name}**",
            ephemeral=True
        )


# =========================
# ROLE SELECT
# =========================

class RoleSelect(discord.ui.RoleSelect):

    def __init__(self, setting, placeholder):

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1
        )

        self.setting = setting

    async def callback(self, interaction):

        role = self.values[0]

        save_setting(
            interaction.guild.id,
            self.setting,
            role.id
        )

        await interaction.response.send_message(
            f"✅ تم حفظ الرتبة: {role.mention}",
            ephemeral=True
        )


# =========================
# TICKET SETUP
# =========================

class TicketSetup(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            CategorySelect()
        )

        self.add_item(
            ChannelSelect(
                "ticket_log",
                "📝 اختر روم لوق التذاكر"
            )
        )

        self.add_item(
            RoleSelect(
                "ticket_role",
                "👮 اختر رتبة دعم التذاكر"
            )
        )


# =========================
# VERIFY SETUP
# =========================

class VerifySetup(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            ChannelSelect(
                "verify_channel",
                "📋 اختر روم التفعيل"
            )
        )

        self.add_item(
            RoleSelect(
                "verify_role",
                "✅ اختر رتبة المتفعل"
            )
        )


# =========================
# BANK SETUP
# =========================

class BankSetup(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            ChannelSelect(
                "bank_channel",
                "🏦 اختر روم البنك"
            )
        )

        self.add_item(
            ChannelSelect(
                "bank_log",
                "📝 اختر روم لوق البنك"
            )
        )

        self.add_item(
            RoleSelect(
                "bank_role",
                "💳 اختر رتبة موظفي البنك"
            )
        )


# =========================
# GENERAL SETUP
# =========================

class GeneralSetup(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            ChannelSelect(
                "points_log",
                "⭐ اختر روم لوق النقاط"
            )
        )

        self.add_item(
            ChannelSelect(
                "jobs_channel",
                "👮 اختر روم الوظائف"
            )
        )

        self.add_item(
            ChannelSelect(
                "trips_channel",
                "✈️ اختر روم الرحلات"
            )
        )

        self.add_item(
            ChannelSelect(
                "announcements_channel",
                "📢 اختر روم التعاميم"
            )
        )

        self.add_item(
            ChannelSelect(
                "logs_channel",
                "📝 اختر روم اللوقات العامة"
            )
        )

        self.add_item(
            RoleSelect(
                "admin_role",
                "🔐 اختر رتبة الإدارة"
            )
        )


# =========================
# TICKETS
# =========================

class TicketButtons(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 فتح تذكرة",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket"
    )
    async def open_ticket(self, interaction, button):

        guild = interaction.guild

        category_id = get_setting(
            guild.id,
            "ticket_category"
        )

        if not category_id:

            await interaction.response.send_message(
                "❌ لم يتم تسطيب كاتقوري التذاكر.",
                ephemeral=True
            )

            return

        category = guild.get_channel(category_id)

        if not category:

            await interaction.response.send_message(
                "❌ الكاتقوري غير موجود.",
                ephemeral=True
            )

            return

        channel_name = (
            f"ticket-{interaction.user.name}"
        ).lower().replace(" ", "-")

        channel = await guild.create_text_channel(
            channel_name,
            category=category
        )

        await channel.set_permissions(
            guild.default_role,
            view_channel=False
        )

        await channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        role_id = get_setting(
            guild.id,
            "ticket_role"
        )

        if role_id:

            role = guild.get_role(role_id)

            if role:

                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        await channel.send(
            f"🎫 **تذكرتك مفتوحة**\n"
            f"صاحب التذكرة: {interaction.user.mention}",
            view=CloseTicket()
        )

        await interaction.response.send_message(
            f"✅ تم فتح التذكرة: {channel.mention}",
            ephemeral=True
        )


class CloseTicket(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 إغلاق التذكرة",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket"
    )
    async def close(self, interaction, button):

        await interaction.response.send_message(
            "🔒 سيتم إغلاق التذكرة..."
        )

        await interaction.channel.delete()


# =========================
# MAIN PANEL
# =========================

class MainPanel(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 التذاكر",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def tickets(self, interaction, button):

        embed = discord.Embed(
            title="🎫 تسطيب التذاكر",
            description=
            "اختر من القوائم بالأسفل:\n\n"
            "📁 كاتقوري التذاكر\n"
            "📝 لوق التذاكر\n"
            "👮 رتبة الدعم"
        )

        await interaction.response.send_message(
            embed=embed,
            view=TicketSetup(),
            ephemeral=True
        )


    @discord.ui.button(
        label="✅ التفعيل",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def verify(self, interaction, button):

        embed = discord.Embed(
            title="✅ تسطيب التفعيل",
            description=
            "اختر روم التفعيل ورتبة المتفعل."
        )

        await interaction.response.send_message(
            embed=embed,
            view=VerifySetup(),
            ephemeral=True
        )


    @discord.ui.button(
        label="⭐ النقاط",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def points(self, interaction, button):

        await interaction.response.send_message(
            "⭐ نظام النقاط جاهز.\n"
            "إعداد اللوق موجود في التسطيب العام.",
            ephemeral=True
        )


    @discord.ui.button(
        label="🏦 البنك",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def bank(self, interaction, button):

        embed = discord.Embed(
            title="🏦 تسطيب البنك",
            description=
            "حدد روم البنك ولوق البنك ورتبة موظفي البنك."
        )

        await interaction.response.send_message(
            embed=embed,
            view=BankSetup(),
            ephemeral=True
        )


    @discord.ui.button(
        label="👮 الوظائف",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def jobs(self, interaction, button):

        await interaction.response.send_message(
            "👮 **الوظائف والقطاعات**\n\n"
            "تم تخصيص روم الوظائف من التسطيب العام.",
            ephemeral=True
        )


    @discord.ui.button(
        label="✈️ الرحلات",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def trips(self, interaction, button):

        await interaction.response.send_message(
            "✈️ **الرحلات**\n\n"
            "تم تخصيص روم الرحلات من التسطيب العام.",
            ephemeral=True
        )


    @discord.ui.button(
        label="📢 التعاميم",
        style=discord.ButtonStyle.primary,
        row=2
    )
    async def announcements(self, interaction, button):

        await interaction.response.send_message(
            "📢 **التعاميم**\n\n"
            "تم تخصيص روم التعاميم من التسطيب العام.",
            ephemeral=True
        )


    @discord.ui.button(
        label="⚙️ التسطيب",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def setup(self, interaction, button):

        embed = discord.Embed(
            title="⚙️ التسطيب العام",
            description=
            "اختر الرومات والرتب من القوائم بالأسفل.\n"
            "ما تحتاج تكتب أي ID."
        )

        await interaction.response.send_message(
            embed=embed,
            view=GeneralSetup(),
            ephemeral=True
        )


# =========================
# SLASH COMMAND
# =========================

@bot.tree.command(
    name="لوحه",
    description="فتح لوحة تحكم السيرفر"
)
async def panel(interaction):

    embed = discord.Embed(
        title="🎛️ لوحة تحكم السيرفر",
        description=
        "اختر النظام الذي تريد استخدامه من الأزرار بالأسفل."
    )

    await interaction.response.send_message(
        embed=embed,
        view=MainPanel()
    )


# =========================
# READY
# =========================

@bot.event
async def on_ready():

    try:

        bot.add_view(MainPanel())
        bot.add_view(TicketButtons())
        bot.add_view(CloseTicket())

        synced = await bot.tree.sync()

        print(
            f"✅ دخل البوت: {bot.user}"
        )

        print(
            f"✅ تمت مزامنة {len(synced)} أمر Slash"
        )

    except Exception as error:

        print(
            f"❌ خطأ: {error}"
        )


# =========================
# START
# =========================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN غير موجود في Environment Variables"
    )

bot.run(TOKEN)
