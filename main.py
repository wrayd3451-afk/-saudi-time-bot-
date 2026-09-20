# 🇸🇦 سعودي تايم — Complete VRP Discord Bot

## التشغيل على Render / Replit

### 1. الملفات
ارفع الملفات الأربعة:
- main.py
- requirements.txt
- .env.example
- README.txt

### 2. المتطلبات
Python 3.11 أو أحدث.

### 3. تثبيت المكتبات
```bash
pip install -r requirements.txt
```

### 4. Secrets / Environment Variables
ضع:
```text
DISCORD_TOKEN=توكن_البوت
GUILD_ID=آيدي_السيرفر
LOG_CHANNEL_ID=آيدي_روم_اللوق
DB_PATH=saudi_time.sqlite3
```

لا تضع توكن البوت داخل GitHub.

### 5. التشغيل
```bash
python main.py
```

## أهم الأوامر

/لوحه
/تفعيل
/وظائف
/معلومات
/نقاط
/تذكرة
/ادمن
/اعطاء_نقاط
/خصم_نقاط
/توظيف
/ترقية
/تقاعد
/استقالة
/فصل
/عقوبات
/سجل
/استدعاء
/حجز
/تأكيد
/إخلاء
/بنك
/رتب
/اسماء
/تحويل_تذكرة
/إضافة_كاش
/إضافة_بنك
/احصائيات

## مهم جداً
هذه النسخة تعمل بقاعدة SQLite خاصة بالبوت.

هي ليست ربطاً مباشراً مع قاعدة VRP الأصلية.
لعمل الربط الحقيقي مع VRP، يلزم معرفة نوع قاعدة البيانات والجداول والحقول المستخدمة في سيرفرك.

## Render
اجعل الخدمة Background Worker إذا كنت تستخدم Render لتشغيل بوت Discord.
Start Command:
```bash
python main.py
```

## صلاحيات البوت
عند دعوة البوت للسيرفر، أعطه الصلاحيات التي يحتاجها للتذاكر والقنوات:
- View Channels
- Send Messages
- Read Message History
- Manage Channels
- Manage Messages

وإذا كانت التذاكر تحتاج إرسال ملفات:
- Attach Files

# -*- coding: utf-8 -*-
"""
سعودي تايم — Complete VRP Discord Bot
نسخة جاهزة للتشغيل على Render / Replit / VPS.

ملاحظة:
هذه النسخة تحفظ بيانات النظام في SQLite.
الربط المباشر مع قاعدة VRP الحقيقية يحتاج Adapter حسب قاعدة بيانات سيرفرك.
"""

import os
import sqlite3
import datetime as dt
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput


# =========================================================
# الإعدادات
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID_RAW = os.getenv("GUILD_ID", "").strip()
LOG_CHANNEL_ID_RAW = os.getenv("LOG_CHANNEL_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "saudi_time.sqlite3").strip() or "saudi_time.sqlite3"

GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW.isdigit() else None
LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_RAW) if LOG_CHANNEL_ID_RAW.isdigit() else None

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN غير موجود. ضعه في Environment Variables / Secrets."
    )


# =========================================================
# قاعدة البيانات
# =========================================================

db_parent = Path(DB_PATH).parent
if str(db_parent) not in ("", "."):
    db_parent.mkdir(parents=True, exist_ok=True)

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

db.executescript(
    """
    CREATE TABLE IF NOT EXISTS players (
        discord_id INTEGER PRIMARY KEY,
        vrp_id TEXT DEFAULT '',
        name TEXT DEFAULT 'غير مسجل',
        job TEXT DEFAULT 'مواطن',
        rank TEXT DEFAULT 'مواطن',
        points INTEGER DEFAULT 0,
        active INTEGER DEFAULT 0,
        money INTEGER DEFAULT 0,
        bank INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        reason TEXT NOT NULL,
        moderator_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER UNIQUE NOT NULL,
        owner_id INTEGER NOT NULL,
        department TEXT DEFAULT 'عام',
        claimed_by INTEGER DEFAULT 0,
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL,
        target_id INTEGER DEFAULT 0,
        action TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER NOT NULL,
        reason TEXT NOT NULL,
        moderator_id INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );
    """
)
db.commit()


def ensure_player(user_id: int):
    row = db.execute(
        "SELECT * FROM players WHERE discord_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO players (discord_id) VALUES (?)",
            (user_id,),
        )
        db.commit()
    return db.execute(
        "SELECT * FROM players WHERE discord_id = ?", (user_id,)
    ).fetchone()


def get_player(user_id: int):
    return db.execute(
        "SELECT * FROM players WHERE discord_id = ?", (user_id,)
    ).fetchone()


def add_log(actor_id: int, action: str, details: str = "", target_id: int = 0):
    db.execute(
        """
        INSERT INTO logs(actor_id, target_id, action, details)
        VALUES (?, ?, ?, ?)
        """,
        (actor_id, target_id, action, details),
    )
    db.commit()


async def send_log(guild: discord.Guild | None, text: str):
    if guild is None or not LOG_CHANNEL_ID:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(text)
        except discord.HTTPException:
            pass


def is_admin(interaction: discord.Interaction) -> bool:
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


async def require_admin(interaction: discord.Interaction) -> bool:
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ هذا الأمر للإدارة فقط.",
            ephemeral=True,
        )
        return False
    return True


def money(value: int) -> str:
    return f"${int(value):,}"


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# Embed Helpers
# =========================================================

def main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🇸🇦 سعودي تايم",
        description=(
            "**لوحة التحكم الرئيسية**\n\n"
            "اختر الخدمة المطلوبة من الأزرار بالأسفل.\n"
            "جميع البيانات محفوظة تلقائياً في قاعدة بيانات البوت."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="VRP SYSTEM",
        value="التفعيل • الملف الشخصي • الوظائف • النقاط • التذاكر • السجل",
        inline=False,
    )
    embed.set_footer(text="Saudi Time • VRP Control System")
    return embed


# =========================================================
# Modals
# =========================================================

class ActivateModal(Modal, title="تفعيل حساب سعودي تايم"):
    vrp_id = TextInput(
        label="رقم VRP",
        placeholder="مثال: 100",
        max_length=30,
    )
    name = TextInput(
        label="اسم اللاعب",
        placeholder="اسمك في السيرفر",
        max_length=80,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ensure_player(interaction.user.id)
        vrp = self.vrp_id.value.strip()
        name = self.name.value.strip()

        db.execute(
            """
            UPDATE players
            SET vrp_id=?, name=?, active=1
            WHERE discord_id=?
            """,
            (vrp, name, interaction.user.id),
        )
        db.commit()

        add_log(
            interaction.user.id,
            "تفعيل",
            f"VRP={vrp} | الاسم={name}",
            interaction.user.id,
        )
        await send_log(
            interaction.guild,
            f"✅ تفعيل: {interaction.user.mention} | VRP `{vrp}` | {name}",
        )

        await interaction.response.send_message(
            f"✅ **تم تفعيل حسابك بنجاح**\n"
            f"VRP: `{vrp}`\n"
            f"الاسم: **{name}**",
            ephemeral=True,
        )


class HireModal(Modal, title="توظيف لاعب"):
    job = TextInput(
        label="الوظيفة",
        placeholder="مثال: العسكرية",
        max_length=50,
    )
    rank = TextInput(
        label="الرتبة",
        placeholder="مثال: جندي",
        max_length=50,
        required=False,
    )

    def __init__(self, target_id: int):
        super().__init__()
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        if not await require_admin(interaction):
            return

        ensure_player(self.target_id)
        job = self.job.value.strip() or "مواطن"
        rank = self.rank.value.strip() or "مواطن"

        db.execute(
            """
            UPDATE players
            SET job=?, rank=?, active=1
            WHERE discord_id=?
            """,
            (job, rank, self.target_id),
        )
        db.commit()

        add_log(
            interaction.user.id,
            "توظيف",
            f"{job} | {rank}",
            self.target_id,
        )
        await interaction.response.send_message(
            f"✅ تم توظيف <@{self.target_id}> في **{job}** برتبة **{rank}**."
        )


# =========================================================
# الوظائف
# =========================================================

JOB_OPTIONS = [
    ("العسكرية", "👮"),
    ("القانون", "⚖️"),
    ("الإجرام", "🔫"),
    ("الإعلام", "📺"),
    ("الإسعاف", "🚑"),
    ("وظائف مدنية", "🚕"),
]


class JobSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, emoji=emoji, value=name)
            for name, emoji in JOB_OPTIONS
        ]
        super().__init__(
            placeholder="اختر الوظيفة...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        ensure_player(interaction.user.id)
        job = self.values[0]

        db.execute(
            "UPDATE players SET job=? WHERE discord_id=?",
            (job, interaction.user.id),
        )
        db.commit()
        add_log(interaction.user.id, "اختيار وظيفة", job, interaction.user.id)

        await interaction.response.send_message(
            f"✅ تم اختيار وظيفة **{job}**.",
            ephemeral=True,
        )


class JobsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(JobSelect())


# =========================================================
# التذاكر
# =========================================================

DEPARTMENTS = [
    ("الإدارة", "🛡️"),
    ("العسكرية", "👮"),
    ("القانون", "⚖️"),
    ("الإسعاف", "🚑"),
    ("الدعم الفني", "🛠️"),
    ("عام", "📩"),
]


class DepartmentSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, emoji=emoji, value=name)
            for name, emoji in DEPARTMENTS
        ]
        super().__init__(
            placeholder="اختر قسم التذكرة...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.values[0])


class TicketDepartmentView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(DepartmentSelect())


class TicketControls(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="استلام",
        emoji="🙋",
        style=discord.ButtonStyle.success,
        custom_id="st_ticket_claim",
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = db.execute(
            "SELECT * FROM tickets WHERE channel_id=?",
            (interaction.channel.id,),
        ).fetchone()

        if not row:
            await interaction.response.send_message(
                "❌ هذه القناة ليست تذكرة مسجلة.",
                ephemeral=True,
            )
            return

        if not is_admin(interaction):
            await interaction.response.send_message(
                "❌ استلام التذاكر للإدارة فقط.",
                ephemeral=True,
            )
            return

        if row["status"] != "open":
            await interaction.response.send_message(
                "❌ التذكرة مغلقة.",
                ephemeral=True,
            )
            return

        db.execute(
            "UPDATE tickets SET claimed_by=? WHERE channel_id=?",
            (interaction.user.id, interaction.channel.id),
        )
        db.commit()
        add_log(
            interaction.user.id,
            "استلام تذكرة",
            interaction.channel.name,
            row["owner_id"],
        )

        await interaction.response.send_message(
            f"🙋 تم استلام التذكرة بواسطة {interaction.user.mention}."
        )

    @discord.ui.button(
        label="تحويل",
        emoji="🔄",
        style=discord.ButtonStyle.primary,
        custom_id="st_ticket_transfer",
    )
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "❌ تحويل التذاكر للإدارة فقط.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "استخدم `/تحويل_تذكرة` ثم اكتب اسم القسم الجديد.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="إغلاق",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="st_ticket_close",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = db.execute(
            "SELECT * FROM tickets WHERE channel_id=?",
            (interaction.channel.id,),
        ).fetchone()

        if not row:
            await interaction.response.send_message(
                "❌ هذه القناة ليست تذكرة.",
                ephemeral=True,
            )
            return

        if row["owner_id"] != interaction.user.id and not is_admin(interaction):
            await interaction.response.send_message(
                "❌ فقط صاحب التذكرة أو الإدارة يستطيع إغلاقها.",
                ephemeral=True,
            )
            return

        db.execute(
            """
            UPDATE tickets
            SET status='closed', closed_at=?
            WHERE channel_id=?
            """,
            (now_text(), interaction.channel.id),
        )
        db.commit()

        add_log(
            interaction.user.id,
            "إغلاق تذكرة",
            interaction.channel.name,
            row["owner_id"],
        )

        await interaction.response.send_message(
            "🔒 تم إغلاق التذكرة. سيتم حذف القناة بعد 5 ثوانٍ."
        )

        await discord.utils.sleep_until(
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
        )

        try:
            await interaction.channel.delete(reason="إغلاق تذكرة سعودي تايم")
        except discord.HTTPException:
            pass


async def create_ticket(interaction: discord.Interaction, department: str):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "❌ لا يمكن فتح تذكرة هنا.",
            ephemeral=True,
        )
        return

    existing = db.execute(
        """
        SELECT * FROM tickets
        WHERE owner_id=? AND status='open'
        """,
        (interaction.user.id,),
    ).fetchone()

    if existing:
        old_channel = guild.get_channel(existing["channel_id"])
        mention = old_channel.mention if old_channel else "التذكرة القديمة"
        await interaction.response.send_message(
            f"❌ عندك تذكرة مفتوحة بالفعل: {mention}",
            ephemeral=True,
        )
        return

    category = discord.utils.get(guild.categories, name="🎫・التذاكر")
    if category is None:
        category = await guild.create_category("🎫・التذاكر")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
    }

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        )

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.id}",
        category=category,
        overwrites=overwrites,
        reason="فتح تذكرة سعودي تايم",
    )

    db.execute(
        """
        INSERT INTO tickets(channel_id, owner_id, department)
        VALUES (?, ?, ?)
        """,
        (channel.id, interaction.user.id, department),
    )
    db.commit()

    add_log(
        interaction.user.id,
        "فتح تذكرة",
        department,
        interaction.user.id,
    )

    embed = discord.Embed(
        title="🎫 تذكرة سعودي تايم",
        description=(
            f"القسم: **{department}**\n\n"
            "اكتب طلبك بالتفصيل هنا.\n"
            "يمكن للإدارة استلام التذكرة أو تحويلها أو إغلاقها."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Saudi Time Support")

    await channel.send(
        content=interaction.user.mention,
        embed=embed,
        view=TicketControls(),
    )

    await interaction.response.send_message(
        f"✅ تم فتح التذكرة: {channel.mention}",
        ephemeral=True,
    )


# =========================================================
# اللوحة الرئيسية
# =========================================================

class MainPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="التفعيل",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="st_main_activate",
    )
    async def activate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActivateModal())

    @discord.ui.button(
        label="معلوماتي",
        emoji="👤",
        style=discord.ButtonStyle.secondary,
        custom_id="st_main_info",
    )
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message(
                "❌ لا يوجد لك ملف. اضغط التفعيل أولاً.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="👤 ملف اللاعب — سعودي تايم",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="الاسم", value=p["name"], inline=True)
        embed.add_field(name="VRP ID", value=p["vrp_id"] or "غير مربوط", inline=True)
        embed.add_field(name="الوظيفة", value=p["job"], inline=True)
        embed.add_field(name="الرتبة", value=p["rank"], inline=True)
        embed.add_field(name="النقاط", value=f"⭐ {p['points']}", inline=True)
        embed.add_field(
            name="الحالة",
            value="🟢 مفعل" if p["active"] else "🔴 غير مفعل",
            inline=True,
        )
        embed.add_field(name="الكاش", value=money(p["money"]), inline=True)
        embed.add_field(name="البنك", value=money(p["bank"]), inline=True)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="الوظائف",
        emoji="📋",
        style=discord.ButtonStyle.primary,
        custom_id="st_main_jobs",
    )
    async def jobs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📋 اختر الوظيفة:",
            view=JobsView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="النقاط",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        custom_id="st_main_points",
    )
    async def points(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = ensure_player(interaction.user.id)
        await interaction.response.send_message(
            f"⭐ نقاطك: **{p['points']}**",
            ephemeral=True,
        )

    @discord.ui.button(
        label="التذاكر",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="st_main_ticket",
    )
    async def tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🎫 اختر القسم:",
            view=TicketDepartmentView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="السجل",
        emoji="📜",
        style=discord.ButtonStyle.secondary,
        custom_id="st_main_history",
    )
    async def history(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = db.execute(
            """
            SELECT * FROM logs
            WHERE actor_id=? OR target_id=?
            ORDER BY id DESC
            LIMIT 10
            """,
            (interaction.user.id, interaction.user.id),
        ).fetchall()

        if not rows:
            await interaction.response.send_message(
                "📜 لا يوجد سجل حتى الآن.",
                ephemeral=True,
            )
            return

        text = "\n".join(
            f"• **{row['action']}** — {row['details'] or '-'}"
            for row in rows
        )

        await interaction.response.send_message(
            f"📜 **سجلك**\n{text}",
            ephemeral=True,
        )


class AdminPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="توظيف",
        emoji="👔",
        style=discord.ButtonStyle.primary,
        custom_id="st_admin_hire",
    )
    async def hire_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await require_admin(interaction):
            return
        await interaction.response.send_message(
            "استخدم `/توظيف` واختر العضو والوظيفة والرتبة.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="السجلات",
        emoji="📜",
        style=discord.ButtonStyle.secondary,
        custom_id="st_admin_logs",
    )
    async def logs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await require_admin(interaction):
            return

        rows = db.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT 20"
        ).fetchall()

        if not rows:
            text = "لا توجد سجلات."
        else:
            text = "\n".join(
                f"`{r['id']}` • <@{r['actor_id']}> • "
                f"**{r['action']}** • {r['details'] or '-'}"
                for r in rows
            )

        await interaction.response.send_message(
            f"📜 **آخر العمليات**\n{text}",
            ephemeral=True,
        )

    @discord.ui.button(
        label="الإحصائيات",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="st_admin_stats",
    )
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await require_admin(interaction):
            return

        players = db.execute("SELECT COUNT(*) AS c FROM players").fetchone()["c"]
        active = db.execute(
            "SELECT COUNT(*) AS c FROM players WHERE active=1"
        ).fetchone()["c"]
        tickets = db.execute(
            "SELECT COUNT(*) AS c FROM tickets WHERE status='open'"
        ).fetchone()["c"]

        await interaction.response.send_message(
            f"📊 **إحصائيات سعودي تايم**\n"
            f"👥 اللاعبين: **{players}**\n"
            f"🟢 المفعلين: **{active}**\n"
            f"🎫 التذاكر المفتوحة: **{tickets}**",
            ephemeral=True,
        )


# =========================================================
# Bot
# =========================================================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# =========================================================
# Slash Commands
# =========================================================

@bot.tree.command(name="لوحه", description="فتح لوحة سعودي تايم")
async def panel_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=main_embed(),
        view=MainPanel(),
    )


@bot.tree.command(name="تفعيل", description="تفعيل وربط حساب VRP")
async def activate_command(interaction: discord.Interaction):
    await interaction.response.send_modal(ActivateModal())


@bot.tree.command(name="وظائف", description="اختيار وظيفة")
async def jobs_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        "📋 اختر الوظيفة:",
        view=JobsView(),
        ephemeral=True,
    )


@bot.tree.command(name="معلومات", description="عرض ملف اللاعب")
async def info_command(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    if not p:
        await interaction.response.send_message(
            "❌ لا يوجد لك ملف. استخدم `/تفعيل` أولاً.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="👤 ملف اللاعب — سعودي تايم",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="الاسم", value=p["name"], inline=True)
    embed.add_field(name="VRP ID", value=p["vrp_id"] or "غير مربوط", inline=True)
    embed.add_field(name="الوظيفة", value=p["job"], inline=True)
    embed.add_field(name="الرتبة", value=p["rank"], inline=True)
    embed.add_field(name="النقاط", value=f"⭐ {p['points']}", inline=True)
    embed.add_field(
        name="الحالة",
        value="🟢 مفعل" if p["active"] else "🔴 غير مفعل",
        inline=True,
    )
    embed.add_field(name="الكاش", value=money(p["money"]), inline=True)
    embed.add_field(name="البنك", value=money(p["bank"]), inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="نقاط", description="عرض نقاطك")
async def points_command(interaction: discord.Interaction):
    p = ensure_player(interaction.user.id)
    await interaction.response.send_message(
        f"⭐ نقاطك: **{p['points']}**",
        ephemeral=True,
    )


@bot.tree.command(name="تذكرة", description="فتح تذكرة")
async def ticket_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🎫 اختر القسم:",
        view=TicketDepartmentView(),
        ephemeral=True,
    )


@bot.tree.command(name="ادمن", description="فتح لوحة الإدارة")
async def admin_command(interaction: discord.Interaction):
    if not await require_admin(interaction):
        return

    embed = discord.Embed(
        title="🛡️ لوحة إدارة سعودي تايم",
        description="أدوات الإدارة الأساسية.",
        color=discord.Color.red(),
    )
    await interaction.response.send_message(
        embed=embed,
        view=AdminPanel(),
        ephemeral=True,
    )


@bot.tree.command(name="اعطاء_نقاط", description="إضافة نقاط لعضو")
@app_commands.describe(member="العضو", amount="عدد النقاط")
async def give_points(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 10000],
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        "UPDATE players SET points=points+? WHERE discord_id=?",
        (amount, member.id),
    )
    db.commit()

    add_log(interaction.user.id, "إضافة نقاط", str(amount), member.id)
    await interaction.response.send_message(
        f"✅ تمت إضافة **{amount}** نقطة إلى {member.mention}."
    )


@bot.tree.command(name="خصم_نقاط", description="خصم نقاط من عضو")
@app_commands.describe(member="العضو", amount="عدد النقاط")
async def take_points(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 10000],
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        """
        UPDATE players
        SET points=MAX(0, points-?)
        WHERE discord_id=?
        """,
        (amount, member.id),
    )
    db.commit()

    add_log(interaction.user.id, "خصم نقاط", str(amount), member.id)
    await interaction.response.send_message(
        f"✅ تم خصم **{amount}** نقطة من {member.mention}."
    )


@bot.tree.command(name="توظيف", description="توظيف عضو")
@app_commands.describe(member="العضو", job="الوظيفة", rank="الرتبة")
async def hire_command(
    interaction: discord.Interaction,
    member: discord.Member,
    job: str,
    rank: str = "مواطن",
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    job = job.strip() or "مواطن"
    rank = rank.strip() or "مواطن"

    db.execute(
        """
        UPDATE players
        SET job=?, rank=?, active=1
        WHERE discord_id=?
        """,
        (job, rank, member.id),
    )
    db.commit()

    add_log(
        interaction.user.id,
        "توظيف",
        f"{job} | {rank}",
        member.id,
    )

    await interaction.response.send_message(
        f"✅ تم توظيف {member.mention} في **{job}** برتبة **{rank}**."
    )


@bot.tree.command(name="ترقية", description="ترقية عضو")
@app_commands.describe(member="العضو", rank="الرتبة الجديدة")
async def promote_command(
    interaction: discord.Interaction,
    member: discord.Member,
    rank: str,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        "UPDATE players SET rank=? WHERE discord_id=?",
        (rank.strip(), member.id),
    )
    db.commit()

    add_log(interaction.user.id, "ترقية", rank, member.id)
    await interaction.response.send_message(
        f"⬆️ تمت ترقية {member.mention} إلى **{rank}**."
    )


@bot.tree.command(name="تقاعد", description="تسجيل تقاعد عضو")
@app_commands.describe(member="العضو")
async def retire_command(
    interaction: discord.Interaction,
    member: discord.Member,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        """
        UPDATE players
        SET job='متقاعد', active=0
        WHERE discord_id=?
        """,
        (member.id,),
    )
    db.commit()

    add_log(interaction.user.id, "تقاعد", "", member.id)
    await interaction.response.send_message(
        f"🫡 تم تسجيل تقاعد {member.mention}."
    )


@bot.tree.command(name="استقالة", description="تسجيل استقالتك")
async def resign_command(interaction: discord.Interaction):
    ensure_player(interaction.user.id)

    db.execute(
        """
        UPDATE players
        SET job='مستقيل', active=0
        WHERE discord_id=?
        """,
        (interaction.user.id,),
    )
    db.commit()

    add_log(interaction.user.id, "استقالة", "", interaction.user.id)
    await interaction.response.send_message(
        "✅ تم تسجيل استقالتك.",
        ephemeral=True,
    )


@bot.tree.command(name="فصل", description="فصل عضو")
@app_commands.describe(member="العضو")
async def fire_command(
    interaction: discord.Interaction,
    member: discord.Member,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        """
        UPDATE players
        SET job='عاطل', rank='مواطن', active=0
        WHERE discord_id=?
        """,
        (member.id,),
    )
    db.commit()

    add_log(interaction.user.id, "فصل", "", member.id)
    await interaction.response.send_message(
        f"❌ تم فصل {member.mention}."
    )


@bot.tree.command(name="عقوبات", description="تسجيل عقوبة")
@app_commands.describe(
    member="العضو",
    type="نوع العقوبة",
    reason="سبب العقوبة",
)
async def punish_command(
    interaction: discord.Interaction,
    member: discord.Member,
    type: str,
    reason: str,
):
    if not await require_admin(interaction):
        return

    db.execute(
        """
        INSERT INTO punishments(discord_id, type, reason, moderator_id)
        VALUES (?, ?, ?, ?)
        """,
        (member.id, type.strip(), reason.strip(), interaction.user.id),
    )
    db.commit()

    add_log(
        interaction.user.id,
        "عقوبة",
        f"{type}: {reason}",
        member.id,
    )
    await interaction.response.send_message(
        f"⚠️ تم تسجيل عقوبة على {member.mention}."
    )


@bot.tree.command(name="سجل", description="عرض السجل")
@app_commands.describe(member="العضو، اتركه فارغاً لعرض سجلك")
async def history_command(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    if member is not None and not await require_admin(interaction):
        return

    target = member or interaction.user

    rows = db.execute(
        """
        SELECT * FROM logs
        WHERE target_id=? OR actor_id=?
        ORDER BY id DESC
        LIMIT 20
        """,
        (target.id, target.id),
    ).fetchall()

    if not rows:
        text = "لا يوجد سجل."
    else:
        text = "\n".join(
            f"• **{row['action']}** — {row['details'] or '-'}"
            for row in rows
        )

    await interaction.response.send_message(
        f"📜 **سجل {target.display_name}**\n{text}",
        ephemeral=True,
    )


@bot.tree.command(name="استدعاء", description="إرسال استدعاء لعضو")
@app_commands.describe(member="العضو", reason="السبب")
async def summon_command(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
):
    if not await require_admin(interaction):
        return

    try:
        await member.send(
            "📣 **استدعاء من سعودي تايم**\n"
            f"من: {interaction.user.mention}\n"
            f"السبب: **{reason}**"
        )
        result = "تم إرسال الاستدعاء بالخاص."
    except discord.Forbidden:
        result = "⚠️ لم أستطع إرسال الخاص للعضو، لكن تم تسجيل الاستدعاء."

    add_log(interaction.user.id, "استدعاء", reason, member.id)
    await interaction.response.send_message(
        f"📣 {member.mention} — {result}"
    )


@bot.tree.command(name="حجز", description="تسجيل حجز على عضو")
@app_commands.describe(member="العضو", reason="السبب")
async def reserve_command(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        """
        INSERT INTO reservations(discord_id, reason, moderator_id)
        VALUES (?, ?, ?)
        """,
        (member.id, reason.strip(), interaction.user.id),
    )
    db.commit()

    add_log(interaction.user.id, "حجز", reason, member.id)
    await interaction.response.send_message(
        f"🔒 تم تسجيل حجز {member.mention}: **{reason}**."
    )


@bot.tree.command(name="تأكيد", description="تأكيد عضو")
@app_commands.describe(member="العضو")
async def confirm_command(
    interaction: discord.Interaction,
    member: discord.Member,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        "UPDATE players SET active=1 WHERE discord_id=?",
        (member.id,),
    )
    db.commit()

    add_log(interaction.user.id, "تأكيد", "", member.id)
    await interaction.response.send_message(
        f"✅ تم تأكيد {member.mention}."
    )


@bot.tree.command(name="إخلاء", description="تسجيل إخلاء طرف")
@app_commands.describe(member="العضو")
async def clearance_command(
    interaction: discord.Interaction,
    member: discord.Member,
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    add_log(interaction.user.id, "إخلاء طرف", "", member.id)

    await interaction.response.send_message(
        f"📄 تم تسجيل إخلاء طرف {member.mention}."
    )


@bot.tree.command(name="بنك", description="عرض بيانات البنك")
async def bank_command(interaction: discord.Interaction):
    p = ensure_player(interaction.user.id)

    await interaction.response.send_message(
        f"🏦 **حسابك البنكي**\n"
        f"الرصيد: **{money(p['bank'])}**\n"
        f"الكاش: **{money(p['money'])}**",
        ephemeral=True,
    )


@bot.tree.command(name="رتب", description="عرض الوظيفة والرتبة")
async def ranks_command(interaction: discord.Interaction):
    p = ensure_player(interaction.user.id)

    await interaction.response.send_message(
        f"🎖️ الوظيفة: **{p['job']}**\n"
        f"الرتبة: **{p['rank']}**",
        ephemeral=True,
    )


@bot.tree.command(name="اسماء", description="عرض اللاعبين المسجلين")
async def names_command(interaction: discord.Interaction):
    if not await require_admin(interaction):
        return

    rows = db.execute(
        """
        SELECT name, vrp_id, job, rank, active
        FROM players
        ORDER BY name
        LIMIT 50
        """
    ).fetchall()

    if not rows:
        await interaction.response.send_message(
            "لا يوجد لاعبون مسجلون.",
            ephemeral=True,
        )
        return

    text = "\n".join(
        f"• **{row['name']}** | VRP `{row['vrp_id'] or '-'}` | "
        f"{row['job']} | {row['rank']} | "
        f"{'🟢' if row['active'] else '🔴'}"
        for row in rows
    )

    await interaction.response.send_message(
        text,
        ephemeral=True,
    )


@bot.tree.command(name="تحويل_تذكرة", description="تحويل التذكرة لقسم")
@app_commands.describe(department="القسم الجديد")
async def transfer_ticket_command(
    interaction: discord.Interaction,
    department: str,
):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ استخدم الأمر داخل التذكرة.",
            ephemeral=True,
        )
        return

    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ للإدارة فقط.",
            ephemeral=True,
        )
        return

    row = db.execute(
        "SELECT * FROM tickets WHERE channel_id=?",
        (interaction.channel.id,),
    ).fetchone()

    if not row:
        await interaction.response.send_message(
            "❌ هذه ليست تذكرة مسجلة.",
            ephemeral=True,
        )
        return

    department = department.strip() or "عام"

    db.execute(
        "UPDATE tickets SET department=? WHERE channel_id=?",
        (department, interaction.channel.id),
    )
    db.commit()

    add_log(
        interaction.user.id,
        "تحويل تذكرة",
        department,
        row["owner_id"],
    )

    await interaction.response.send_message(
        f"🔄 تم تحويل التذكرة إلى **{department}**."
    )


# =========================================================
# أوامر إضافية مفيدة
# =========================================================

@bot.tree.command(name="إضافة_كاش", description="إضافة كاش للاعب")
@app_commands.describe(member="العضو", amount="المبلغ")
async def add_cash_command(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 100000000],
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        "UPDATE players SET money=money+? WHERE discord_id=?",
        (amount, member.id),
    )
    db.commit()

    add_log(interaction.user.id, "إضافة كاش", str(amount), member.id)
    await interaction.response.send_message(
        f"💵 تمت إضافة **{money(amount)}** إلى {member.mention}."
    )


@bot.tree.command(name="إضافة_بنك", description="إضافة رصيد بنكي للاعب")
@app_commands.describe(member="العضو", amount="المبلغ")
async def add_bank_command(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 100000000],
):
    if not await require_admin(interaction):
        return

    ensure_player(member.id)
    db.execute(
        "UPDATE players SET bank=bank+? WHERE discord_id=?",
        (amount, member.id),
    )
    db.commit()

    add_log(interaction.user.id, "إضافة بنك", str(amount), member.id)
    await interaction.response.send_message(
        f"🏦 تمت إضافة **{money(amount)}** إلى بنك {member.mention}."
    )


@bot.tree.command(name="احصائيات", description="إحصائيات النظام")
async def stats_command(interaction: discord.Interaction):
    if not await require_admin(interaction):
        return

    players = db.execute(
        "SELECT COUNT(*) AS c FROM players"
    ).fetchone()["c"]
    active = db.execute(
        "SELECT COUNT(*) AS c FROM players WHERE active=1"
    ).fetchone()["c"]
    open_tickets = db.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE status='open'"
    ).fetchone()["c"]
    logs_count = db.execute(
        "SELECT COUNT(*) AS c FROM logs"
    ).fetchone()["c"]

    await interaction.response.send_message(
        f"📊 **إحصائيات سعودي تايم**\n"
        f"👥 اللاعبين: **{players}**\n"
        f"🟢 المفعلين: **{active}**\n"
        f"🎫 التذاكر المفتوحة: **{open_tickets}**\n"
        f"📜 السجلات: **{logs_count}**",
        ephemeral=True,
    )


# =========================================================
# أخطاء الأوامر
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    print(f"App command error: {repr(error)}")

    message = "❌ حدث خطأ أثناء تنفيذ الأمر."

    if isinstance(error, app_commands.CommandOnCooldown):
        message = "⏳ حاول مرة أخرى بعد قليل."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


# =========================================================
# Startup
# =========================================================

@bot.event
async def on_ready():
    # تسجيل الـ persistent views مرة واحدة لكل تشغيل
    if not getattr(bot, "_views_loaded", False):
        bot.add_view(MainPanel())
        bot.add_view(AdminPanel())
        bot.add_view(TicketControls())
        bot._views_loaded = True

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} global commands")
    except Exception as exc:
        print(f"⚠️ Command sync failed: {exc}")

    print(f"✅ {bot.user} online — Saudi Time")
    print(f"📁 Database: {DB_PATH}")


bot.run(TOKEN)

discord.py>=2.4,<3
