# -*- coding: utf-8 -*-
"""
بوت نظام VRP لسيرفرات الرول بلاي على دسكورد
هوية - بنك - وظائف ورواتب - مخالفات - سجل جنائي - متجر وشنطة
"""
import asyncio
import io
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import subprocess
import sys
import types

# نخلي كل الرسائل تطلع في اللوق على طول
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
print("🚀 بدأ تشغيل البوت...")

# لو المكتبة مو مثبتة، يثبتها البوت لحاله
try:
    import discord
    from discord import app_commands
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py>=2.3"])
    import discord
    from discord import app_commands

# مكتبات الصوت (عشان البوت يقعد في الروم الصوتي)
try:
    import nacl  # noqa: F401
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py[voice]"])
    except Exception as _e:
        print(f"⚠️ ما قدرت أثبت مكتبات الصوت: {_e}")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
#   إعدادات بوت نظام VRP - عدّل من هنا
# ==========================================

# اسم السيرفر (يظهر في الهوية والرسائل)
SERVER_NAME = "سعودي تايم | Saudi Time"

# العملة
CURRENCY = "$"

# الفلوس اللي ياخذها اللاعب أول ما يسوي هوية
START_CASH = 5000
START_BANK = 20000

# ----------------------------------------------------------------
# الرتب في الدسكورد (حط ID الرتبة)
# ----------------------------------------------------------------
ADMIN_ROLE_ID = 0      # رتبة الإدارة
POLICE_ROLE_ID = 0     # رتبة الشرطة
CITIZEN_ROLE_ID = 0    # رتبة "مواطن" تنعطى تلقائي بعد إصدار الهوية (0 = بدون)

# روم اللوق (0 = بدون لوق)
LOG_CHANNEL_ID = 0

# ----------------------------------------------------------------
# الوظائف والرواتب
# ----------------------------------------------------------------
JOBS = {
    "عاطل":        {"salary": 500,  "role_id": 0},
    "شرطي":        {"salary": 4000, "role_id": 0},
    "مسعف":        {"salary": 3500, "role_id": 0},
    "ميكانيكي":    {"salary": 3000, "role_id": 0},
    "سواق تاكسي":  {"salary": 2000, "role_id": 0},
    "محامي":       {"salary": 3500, "role_id": 0},
    "تاجر سيارات": {"salary": 2500, "role_id": 0},
}
DEFAULT_JOB = "عاطل"

# مبلغ التفتيش اللي يطلع في رسالة الخاص (رسالة بس، ما ينسحب فعلياً)
INSPECT_FEE = 400

# كم غلطة مسموحة في الاختبار (لو غلط أكثر منها ينرفض)
# 1 = لازم 9 من 10 صح، ولو غلط في سؤالين ينرفض
MAX_WRONG = 1

# كل كم ساعة يقدر اللاعب يستلم راتبه
SALARY_COOLDOWN_HOURS = 24

# ----------------------------------------------------------------
# المتجر: اسم الغرض: السعر
# ----------------------------------------------------------------
SHOP = {
    "جوال": 1500,
    "راديو": 800,
    "رخصة قيادة": 2000,
    "رخصة سلاح": 10000,
    "عدة تصليح": 1200,
    "ماء": 20,
    "برقر": 45,
    "لاب توب": 4000,
}

# نجمع الإعدادات تحت اسم config عشان باقي الكود يستخدمها
config = types.SimpleNamespace(
    SERVER_NAME=SERVER_NAME, CURRENCY=CURRENCY,
    START_CASH=START_CASH, START_BANK=START_BANK,
    ADMIN_ROLE_ID=ADMIN_ROLE_ID, POLICE_ROLE_ID=POLICE_ROLE_ID,
    CITIZEN_ROLE_ID=CITIZEN_ROLE_ID, LOG_CHANNEL_ID=LOG_CHANNEL_ID,
    JOBS=JOBS, DEFAULT_JOB=DEFAULT_JOB,
    SALARY_COOLDOWN_HOURS=SALARY_COOLDOWN_HOURS, SHOP=SHOP, MAX_WRONG=MAX_WRONG, INSPECT_FEE=INSPECT_FEE,
)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# ============================================================
# قاعدة البيانات
# ============================================================
db = sqlite3.connect("vrp.db")
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS players (
    user_id     INTEGER PRIMARY KEY,
    id_number   TEXT UNIQUE,
    name        TEXT,
    birth       TEXT,
    gender      TEXT,
    nationality TEXT,
    job         TEXT,
    cash        INTEGER DEFAULT 0,
    bank        INTEGER DEFAULT 0,
    last_salary TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS fines (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    amount    INTEGER,
    reason    TEXT,
    officer   INTEGER,
    paid      INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    charge    TEXT,
    officer   INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item    TEXT,
    qty     INTEGER,
    PRIMARY KEY (user_id, item)
);
CREATE TABLE IF NOT EXISTS ticket_types (
    guild_id    INTEGER,
    slot        INTEGER,
    name        TEXT,
    emoji       TEXT,
    category_id INTEGER,
    staff_role  INTEGER,
    welcome     TEXT,
    counter     INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, slot)
);
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id   INTEGER,
    owner_id   INTEGER,
    slot       INTEGER,
    claimed_by INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS quiz_questions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    slot     INTEGER,
    question TEXT,
    right_a  TEXT,
    wrong_a  TEXT
);
CREATE TABLE IF NOT EXISTS activations (
    guild_id   INTEGER,
    user_id    INTEGER,
    sony_id    TEXT,
    by_id      INTEGER,
    created_at TEXT,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS auto_replies (
    guild_id INTEGER,
    trigger  TEXT,
    response TEXT,
    as_embed INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, trigger)
);
CREATE TABLE IF NOT EXISTS inspect_roles (
    guild_id INTEGER,
    role_id  INTEGER,
    PRIMARY KEY (guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS points_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER,
    user_id    INTEGER,
    kind       TEXT,
    category   TEXT,
    amount     INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS duty_active (
    guild_id   INTEGER,
    user_id    INTEGER,
    started_at TEXT,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS duty_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER,
    user_id    INTEGER,
    started_at TEXT,
    minutes    INTEGER
);
CREATE TABLE IF NOT EXISTS assets (
    guild_id INTEGER,
    key      TEXT,
    filename TEXT,
    data     BLOB,
    PRIMARY KEY (guild_id, key)
);
CREATE TABLE IF NOT EXISTS app_types (
    guild_id      INTEGER,
    slot          INTEGER,
    name          TEXT,
    emoji         TEXT,
    review_ch     INTEGER,
    role1         INTEGER,
    role2         INTEGER,
    reviewer_role INTEGER,
    questions     TEXT,
    PRIMARY KEY (guild_id, slot)
);
CREATE TABLE IF NOT EXISTS app_submissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER,
    slot       INTEGER,
    user_id    INTEGER,
    answers    TEXT,
    status     TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS job_roles (
    guild_id INTEGER,
    name     TEXT,
    role_id  INTEGER,
    sector   TEXT,
    PRIMARY KEY (guild_id, name)
);
CREATE TABLE IF NOT EXISTS units (
    guild_id INTEGER,
    user_id  INTEGER,
    kind     TEXT,
    number   INTEGER,
    PRIMARY KEY (guild_id, user_id, kind)
);
CREATE TABLE IF NOT EXISTS bank_accounts (
    user_id    INTEGER PRIMARY KEY,
    iban       TEXT UNIQUE,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS loans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER,
    user_id    INTEGER,
    amount     INTEGER,
    remaining  INTEGER,
    reason     TEXT,
    status     TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER,
    key      TEXT,
    value    INTEGER,
    PRIMARY KEY (guild_id, key)
);
""")
db.commit()


def now():
    return datetime.now(timezone.utc)


def money(n: int) -> str:
    return f"{n:,} {config.CURRENCY}"


def get_player(user_id: int):
    return db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()


def new_id_number() -> str:
    while True:
        num = "1" + "".join(random.choices("0123456789", k=9))
        if not db.execute("SELECT 1 FROM players WHERE id_number = ?", (num,)).fetchone():
            return num


def add_item(user_id: int, item: str, qty: int):
    db.execute(
        "INSERT INTO inventory (user_id, item, qty) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item) DO UPDATE SET qty = qty + excluded.qty",
        (user_id, item, qty),
    )
    db.execute("DELETE FROM inventory WHERE qty <= 0")
    db.commit()


def item_qty(user_id: int, item: str) -> int:
    row = db.execute("SELECT qty FROM inventory WHERE user_id = ? AND item = ?", (user_id, item)).fetchone()
    return row["qty"] if row else 0


def get_setting(guild_id: int, key: str) -> int:
    row = db.execute("SELECT value FROM settings WHERE guild_id = ? AND key = ?", (guild_id, key)).fetchone()
    return row["value"] if row else 0


def set_setting(guild_id: int, key: str, value: int):
    db.execute(
        "INSERT INTO settings (guild_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
        (guild_id, key, value),
    )
    db.commit()


# ============================================================
# البوت
# ============================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # عشان البوت يقرأ أمر -قيم


class VRPBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(CreateIDPanel())
        self.add_view(ViewIDPanel())
        # نرسل الأوامر لديسكورد بس إذا تغيّرت، عشان نقلل الطلبات
        import hashlib, json
        payload = json.dumps([c.to_dict(self.tree) for c in self.tree.get_commands()], sort_keys=True, ensure_ascii=False)
        digest = int(hashlib.sha1(payload.encode()).hexdigest()[:12], 16)
        if get_setting(0, "commands_hash") == digest:
            print("ℹ️ الأوامر ما تغيّرت، ما يحتاج أرسلها")
            return
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
            set_setting(0, "commands_hash", digest)
            print(f"✅ انرسلت {len(self.tree.get_commands())} أمر لديسكورد")
        except discord.HTTPException as e:
            # ما نطيّح البوت، يكمل شغال بالأوامر اللي عند ديسكورد
            print(f"⚠️ ديسكورد رفض تحديث الأوامر: {e}")

    async def on_ready(self):
        print(f"✅ البوت شغال: {self.user} ")
        if not getattr(self, "_voice_task", None):
            self._voice_task = asyncio.create_task(voice_keeper())


bot = VRPBot()


# ---------- أدوات مساعدة ----------
def has_role(member: discord.Member, role_id: int) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return role_id != 0 and any(r.id == role_id for r in member.roles)


def role_setting(guild, key: str, fallback: int = 0) -> int:
    if guild is None:
        return fallback
    return get_setting(guild.id, key) or fallback


def is_admin(inter: discord.Interaction) -> bool:
    return has_role(inter.user, role_setting(inter.guild, "role_admin", config.ADMIN_ROLE_ID))


def is_police(inter: discord.Interaction) -> bool:
    return (has_role(inter.user, role_setting(inter.guild, "role_police", config.POLICE_ROLE_ID))
            or (role_setting(inter.guild, "role_swat") and has_role(inter.user, role_setting(inter.guild, "role_swat")))
            or is_admin(inter))


def embed(title: str, desc: str = "", color=0x0B6B55) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color, timestamp=now())
    e.set_footer(text=config.SERVER_NAME)
    return e


def err(msg: str) -> discord.Embed:
    return embed("❌ خطأ", msg, 0xB3261E)


async def log(text: str, guild=None):
    ch_id = (get_setting(guild.id, "ch_log") if guild else 0) or config.LOG_CHANNEL_ID
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        try:
            await ch.send(embed=embed("📋 لوق", text, 0x4A5A54))
        except discord.HTTPException:
            pass


async def require_player(inter: discord.Interaction, user: discord.abc.User = None):
    """يرجع بيانات اللاعب، ولو ما عنده هوية يرد برسالة خطأ ويرجع None"""
    target = user or inter.user
    p = get_player(target.id)
    if not p:
        who = "ما عندك هوية. روح روم إنشاء الهوية واضغط زر إنشاء هوية." if target == inter.user else f"{target.mention} ما عنده هوية."
        await inter.response.send_message(embed=err(who), ephemeral=True)
    return p


async def set_job_role(member: discord.Member, old_job: str, new_job: str):
    try:
        old_role = member.guild.get_role(config.JOBS.get(old_job, {}).get("role_id", 0))
        new_role = member.guild.get_role(config.JOBS.get(new_job, {}).get("role_id", 0))
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role)
        if new_role:
            await member.add_roles(new_role)
    except discord.Forbidden:
        pass


def id_card(p, member: discord.abc.User) -> discord.Embed:
    e = embed("🪪 بطاقة الهوية الوطنية")
    e.add_field(name="الاسم", value=p["name"], inline=True)
    e.add_field(name="رقم الهوية", value=f"`{p['id_number']}`", inline=True)
    e.add_field(name="تاريخ الميلاد", value=p["birth"], inline=True)
    e.add_field(name="الجنس", value=p["gender"], inline=True)
    e.add_field(name="الجنسية", value=p["nationality"], inline=True)
    e.add_field(name="الوظيفة", value=p["job"], inline=True)
    e.set_thumbnail(url=member.display_avatar.url)
    return e


# ============================================================
# الهوية
# ============================================================
class CreateIDModal(discord.ui.Modal, title="🪪 إصدار هوية جديدة"):
    name_in = discord.ui.TextInput(label="الاسم", placeholder="اسم شخصيتك", max_length=40)
    birth_in = discord.ui.TextInput(label="تاريخ الميلاد", placeholder="مثال: 1998/05/20", max_length=20)
    gender_in = discord.ui.TextInput(label="الجنس", placeholder="ذكر أو أنثى", max_length=10)
    nat_in = discord.ui.TextInput(label="الجنسية", placeholder="مثال: سعودي", max_length=30)

    async def on_submit(self, inter: discord.Interaction):
        if get_player(inter.user.id):
            return await inter.response.send_message(embed=err("عندك هوية من قبل."), ephemeral=True)
        gender = self.gender_in.value.strip()
        if gender not in ("ذكر", "أنثى", "انثى"):
            return await inter.response.send_message(embed=err("الجنس لازم يكون: ذكر أو أنثى"), ephemeral=True)
        gender = "أنثى" if gender == "انثى" else gender
        name = self.name_in.value.strip()
        num = new_id_number()
        db.execute(
            "INSERT INTO players (user_id, id_number, name, birth, gender, nationality, job, cash, bank, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (inter.user.id, num, name, self.birth_in.value.strip(), gender, self.nat_in.value.strip(),
             config.DEFAULT_JOB, config.START_CASH, config.START_BANK, now().isoformat()),
        )
        db.commit()
        p = get_player(inter.user.id)
        citizen = role_setting(inter.guild, "role_citizen", config.CITIZEN_ROLE_ID)
        if citizen and isinstance(inter.user, discord.Member):
            role = inter.guild.get_role(citizen)
            if role:
                try:
                    await inter.user.add_roles(role)
                except discord.Forbidden:
                    pass
        e = id_card(p, inter.user)
        e.description = f"مرحبًا بك في المدينة! استلمت {money(config.START_CASH)} كاش و {money(config.START_BANK)} في البنك."
        await inter.response.send_message(embed=e, ephemeral=True)
        await log(f"{inter.user.mention} أصدر هوية باسم **{name}** رقم `{num}`", inter.guild)


class CreateIDPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إنشاء هوية", emoji="🪪", style=discord.ButtonStyle.success, custom_id="panel:create_id")
    async def create(self, inter: discord.Interaction, button: discord.ui.Button):
        if get_player(inter.user.id):
            return await inter.response.send_message(embed=err("عندك هوية من قبل. روح روم عرض الهوية."), ephemeral=True)
        await inter.response.send_modal(CreateIDModal())


class ViewIDPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="عرض هويتي", emoji="🪪", style=discord.ButtonStyle.primary, custom_id="panel:view_id")
    async def view(self, inter: discord.Interaction, button: discord.ui.Button):
        p = await require_player(inter)
        if p:
            await inter.response.send_message(embed=id_card(p, inter.user), ephemeral=True)


def create_id_panel_embed() -> discord.Embed:
    return embed(
        "🪪 إنشاء هوية",
        f"أهلاً بك في **{config.SERVER_NAME}**\n\nاضغط الزر اللي تحت وعبّي بياناتك عشان تطلع لك هويتك الوطنية.",
    )


def view_id_panel_embed() -> discord.Embed:
    return embed("🪪 عرض الهوية", "اضغط الزر اللي تحت عشان تشوف هويتك.\n\nالهوية تطلع لك أنت بس.")


@bot.tree.command(name="هوية", description="عرض هوية لاعب (للشرطة والإدارة)")
async def view_id(inter: discord.Interaction, اللاعب: discord.Member):
    if not is_police(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للشرطة والإدارة فقط."), ephemeral=True)
    p = await require_player(inter, اللاعب)
    if p:
        await inter.response.send_message(embed=id_card(p, اللاعب), ephemeral=True)


# ============================================================
# البنك
# ============================================================
@bot.tree.command(name="رصيدي", description="عرض فلوسك الكاش والبنك")
async def balance(inter: discord.Interaction):
    p = await require_player(inter)
    if not p:
        return
    e = embed("🏦 حسابك")
    e.add_field(name="💵 كاش", value=money(p["cash"]))
    e.add_field(name="🏦 البنك", value=money(p["bank"]))
    e.add_field(name="المجموع", value=money(p["cash"] + p["bank"]))
    await inter.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="ايداع", description="إيداع كاش في البنك")
async def deposit(inter: discord.Interaction, المبلغ: app_commands.Range[int, 1]):
    p = await require_player(inter)
    if not p:
        return
    if p["cash"] < المبلغ:
        return await inter.response.send_message(embed=err(f"كاشك ما يكفي. عندك {money(p['cash'])}"), ephemeral=True)
    db.execute("UPDATE players SET cash = cash - ?, bank = bank + ? WHERE user_id = ?", (المبلغ, المبلغ, inter.user.id))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم الإيداع", f"أودعت {money(المبلغ)} في البنك."), ephemeral=True)


@bot.tree.command(name="سحب", description="سحب فلوس من البنك كاش")
async def withdraw(inter: discord.Interaction, المبلغ: app_commands.Range[int, 1]):
    p = await require_player(inter)
    if not p:
        return
    if p["bank"] < المبلغ:
        return await inter.response.send_message(embed=err(f"رصيدك في البنك ما يكفي. عندك {money(p['bank'])}"), ephemeral=True)
    db.execute("UPDATE players SET bank = bank - ?, cash = cash + ? WHERE user_id = ?", (المبلغ, المبلغ, inter.user.id))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم السحب", f"سحبت {money(المبلغ)} كاش."), ephemeral=True)


@bot.tree.command(name="تحويل", description="تحويل بنكي للاعب ثاني")
async def transfer(inter: discord.Interaction, اللاعب: discord.Member, المبلغ: app_commands.Range[int, 1]):
    if اللاعب.id == inter.user.id:
        return await inter.response.send_message(embed=err("ما تقدر تحول لنفسك."), ephemeral=True)
    p = await require_player(inter)
    if not p:
        return
    if not get_player(اللاعب.id):
        return await inter.response.send_message(embed=err(f"{اللاعب.mention} ما عنده هوية."), ephemeral=True)
    if p["bank"] < المبلغ:
        return await inter.response.send_message(embed=err(f"رصيدك ما يكفي. عندك {money(p['bank'])}"), ephemeral=True)
    db.execute("UPDATE players SET bank = bank - ? WHERE user_id = ?", (المبلغ, inter.user.id))
    db.execute("UPDATE players SET bank = bank + ? WHERE user_id = ?", (المبلغ, اللاعب.id))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم التحويل", f"حولت {money(المبلغ)} إلى {اللاعب.mention}"))
    await log(f"{inter.user.mention} حوّل {money(المبلغ)} إلى {اللاعب.mention}", inter.guild)


@bot.tree.command(name="اعطاء_كاش", description="تعطي لاعب قريب منك كاش من يدك")
async def give_cash(inter: discord.Interaction, اللاعب: discord.Member, المبلغ: app_commands.Range[int, 1]):
    if اللاعب.id == inter.user.id:
        return await inter.response.send_message(embed=err("ما تقدر تعطي نفسك."), ephemeral=True)
    p = await require_player(inter)
    if not p:
        return
    if not get_player(اللاعب.id):
        return await inter.response.send_message(embed=err(f"{اللاعب.mention} ما عنده هوية."), ephemeral=True)
    if p["cash"] < المبلغ:
        return await inter.response.send_message(embed=err(f"كاشك ما يكفي. عندك {money(p['cash'])}"), ephemeral=True)
    db.execute("UPDATE players SET cash = cash - ? WHERE user_id = ?", (المبلغ, inter.user.id))
    db.execute("UPDATE players SET cash = cash + ? WHERE user_id = ?", (المبلغ, اللاعب.id))
    db.commit()
    await inter.response.send_message(embed=embed("💵 تسليم كاش", f"{inter.user.mention} عطى {اللاعب.mention} {money(المبلغ)} كاش"))
    await log(f"{inter.user.mention} عطى {اللاعب.mention} {money(المبلغ)} كاش", inter.guild)


@bot.tree.command(name="الاغنى", description="قائمة أغنى 10 لاعبين")
async def top(inter: discord.Interaction):
    rows = db.execute("SELECT name, user_id, cash + bank AS total FROM players ORDER BY total DESC LIMIT 10").fetchall()
    if not rows:
        return await inter.response.send_message(embed=err("ما فيه لاعبين مسجلين."), ephemeral=True)
    lines = [f"**{i}.** {r['name']} (<@{r['user_id']}>) : {money(r['total'])}" for i, r in enumerate(rows, 1)]
    await inter.response.send_message(embed=embed("💰 أغنى اللاعبين", "\n".join(lines)))


# ============================================================
# الوظائف والرواتب
# ============================================================
@bot.tree.command(name="راتب", description="استلام راتب وظيفتك")
async def salary(inter: discord.Interaction):
    p = await require_player(inter)
    if not p:
        return
    if p["last_salary"]:
        next_time = datetime.fromisoformat(p["last_salary"]) + timedelta(hours=config.SALARY_COOLDOWN_HOURS)
        if now() < next_time:
            left = next_time - now()
            h, m = left.seconds // 3600 + left.days * 24, (left.seconds % 3600) // 60
            return await inter.response.send_message(embed=err(f"استلمت راتبك. الراتب الجاي بعد {h} ساعة و {m} دقيقة."), ephemeral=True)
    amount = config.JOBS.get(p["job"], {}).get("salary", 0)
    db.execute("UPDATE players SET bank = bank + ?, last_salary = ? WHERE user_id = ?", (amount, now().isoformat(), inter.user.id))
    db.commit()
    await inter.response.send_message(embed=embed("💼 نزل الراتب", f"نزل راتبك كـ **{p['job']}**: {money(amount)} في حسابك البنكي."))


@bot.tree.command(name="الوظائف", description="عرض الوظائف ورواتبها")
async def jobs(inter: discord.Interaction):
    lines = [f"• **{name}**: {money(j['salary'])}" for name, j in config.JOBS.items()]
    await inter.response.send_message(embed=embed("💼 الوظائف", "\n".join(lines)), ephemeral=True)


async def job_autocomplete(inter: discord.Interaction, current: str):
    return [app_commands.Choice(name=j, value=j) for j in config.JOBS if current in j][:25]


@bot.tree.command(name="تعيين_وظيفة", description="تغيير وظيفة لاعب (للإدارة)")
@app_commands.autocomplete(الوظيفة=job_autocomplete)
async def set_job(inter: discord.Interaction, اللاعب: discord.Member, الوظيفة: str):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    if الوظيفة not in config.JOBS:
        return await inter.response.send_message(embed=err("الوظيفة غير موجودة. شف /الوظائف"), ephemeral=True)
    p = await require_player(inter, اللاعب)
    if not p:
        return
    db.execute("UPDATE players SET job = ? WHERE user_id = ?", (الوظيفة, اللاعب.id))
    db.commit()
    await set_job_role(اللاعب, p["job"], الوظيفة)
    await inter.response.send_message(embed=embed("✅ تم التعيين", f"{اللاعب.mention} صار **{الوظيفة}**"))
    await log(f"{inter.user.mention} غيّر وظيفة {اللاعب.mention} من {p['job']} إلى {الوظيفة}", inter.guild)


# ============================================================
# الشرطة: المخالفات والسجل
# ============================================================
@bot.tree.command(name="مخالفة", description="تسجيل مخالفة على لاعب (للشرطة)")
async def fine(inter: discord.Interaction, اللاعب: discord.Member, المبلغ: app_commands.Range[int, 1], السبب: str):
    if not is_police(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للشرطة فقط."), ephemeral=True)
    if not await require_player(inter, اللاعب):
        return
    cur = db.execute(
        "INSERT INTO fines (user_id, amount, reason, officer, created_at) VALUES (?, ?, ?, ?, ?)",
        (اللاعب.id, المبلغ, السبب, inter.user.id, now().isoformat()),
    )
    db.commit()
    e = embed("🚨 مخالفة جديدة", color=0xB98118)
    e.add_field(name="المخالف", value=اللاعب.mention)
    e.add_field(name="المبلغ", value=money(المبلغ))
    e.add_field(name="رقم المخالفة", value=f"#{cur.lastrowid}")
    e.add_field(name="السبب", value=السبب, inline=False)
    e.add_field(name="الشرطي", value=inter.user.mention, inline=False)
    await inter.response.send_message(content=اللاعب.mention, embed=e)
    add_points(inter.guild.id, inter.user.id, "police", "fine", pts_value(inter.guild.id, "pts_fine"))
    await log(f"{inter.user.mention} خالف {اللاعب.mention} بـ {money(المبلغ)}: {السبب}", inter.guild)


@bot.tree.command(name="مخالفاتي", description="عرض مخالفاتك غير المسددة")
async def my_fines(inter: discord.Interaction):
    if not await require_player(inter):
        return
    rows = db.execute("SELECT * FROM fines WHERE user_id = ? AND paid = 0", (inter.user.id,)).fetchall()
    if not rows:
        return await inter.response.send_message(embed=embed("✅ ما عليك مخالفات"), ephemeral=True)
    total = sum(r["amount"] for r in rows)
    lines = [f"**#{r['id']}** : {money(r['amount'])} ({r['reason']})" for r in rows]
    await inter.response.send_message(
        embed=embed("🚨 مخالفاتك", "\n".join(lines) + f"\n\n**المجموع:** {money(total)}\nسدد بأمر /سداد_مخالفة", 0xB98118),
        ephemeral=True,
    )


@bot.tree.command(name="سداد_مخالفة", description="سداد مخالفة من حسابك البنكي")
@app_commands.describe(رقم_المخالفة="رقم المخالفة، أو اتركه فاضي لسداد الكل")
async def pay_fine(inter: discord.Interaction, رقم_المخالفة: int = None):
    p = await require_player(inter)
    if not p:
        return
    if رقم_المخالفة:
        rows = db.execute("SELECT * FROM fines WHERE id = ? AND user_id = ? AND paid = 0", (رقم_المخالفة, inter.user.id)).fetchall()
    else:
        rows = db.execute("SELECT * FROM fines WHERE user_id = ? AND paid = 0", (inter.user.id,)).fetchall()
    if not rows:
        return await inter.response.send_message(embed=err("ما لقيت مخالفات غير مسددة."), ephemeral=True)
    total = sum(r["amount"] for r in rows)
    if p["bank"] < total:
        return await inter.response.send_message(embed=err(f"رصيدك ما يكفي. المطلوب {money(total)} وعندك {money(p['bank'])}"), ephemeral=True)
    db.execute("UPDATE players SET bank = bank - ? WHERE user_id = ?", (total, inter.user.id))
    db.executemany("UPDATE fines SET paid = 1 WHERE id = ?", [(r["id"],) for r in rows])
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم السداد", f"سددت {len(rows)} مخالفة بمبلغ {money(total)}"), ephemeral=True)
    await log(f"{inter.user.mention} سدد مخالفات بمبلغ {money(total)}", inter.guild)


@bot.tree.command(name="اضافة_سجل", description="إضافة تهمة للسجل الجنائي (للشرطة)")
async def add_record(inter: discord.Interaction, اللاعب: discord.Member, التهمة: str):
    if not is_police(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للشرطة فقط."), ephemeral=True)
    if not await require_player(inter, اللاعب):
        return
    db.execute("INSERT INTO records (user_id, charge, officer, created_at) VALUES (?, ?, ?, ?)",
               (اللاعب.id, التهمة, inter.user.id, now().isoformat()))
    db.commit()
    await inter.response.send_message(embed=embed("📁 تمت الإضافة للسجل", f"{اللاعب.mention}: {التهمة}", 0xB3261E))
    await log(f"{inter.user.mention} أضاف للسجل الجنائي لـ {اللاعب.mention}: {التهمة}", inter.guild)


@bot.tree.command(name="سجل", description="عرض السجل الجنائي والمخالفات للاعب (للشرطة)")
async def view_record(inter: discord.Interaction, اللاعب: discord.Member):
    if not is_police(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للشرطة فقط."), ephemeral=True)
    p = await require_player(inter, اللاعب)
    if not p:
        return
    recs = db.execute("SELECT * FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 15", (اللاعب.id,)).fetchall()
    fines_ = db.execute("SELECT * FROM fines WHERE user_id = ? AND paid = 0", (اللاعب.id,)).fetchall()
    e = embed(f"📁 ملف {p['name']}", f"رقم الهوية: `{p['id_number']}`", 0x4A5A54)
    e.add_field(
        name=f"السجل الجنائي ({len(recs)})",
        value="\n".join(f"• {r['charge']} ({r['created_at'][:10]})" for r in recs) or "نظيف ✅",
        inline=False,
    )
    e.add_field(
        name="مخالفات غير مسددة",
        value=f"{len(fines_)} مخالفة بمجموع {money(sum(f['amount'] for f in fines_))}" if fines_ else "لا يوجد",
        inline=False,
    )
    await inter.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="مسح_سجل", description="مسح السجل الجنائي للاعب (للإدارة)")
async def clear_record(inter: discord.Interaction, اللاعب: discord.Member):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    db.execute("DELETE FROM records WHERE user_id = ?", (اللاعب.id,))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم مسح السجل", اللاعب.mention), ephemeral=True)
    await log(f"{inter.user.mention} مسح السجل الجنائي لـ {اللاعب.mention}", inter.guild)


# ============================================================
# المتجر والشنطة
# ============================================================
@bot.tree.command(name="المتجر", description="عرض أغراض المتجر")
async def shop(inter: discord.Interaction):
    lines = [f"• **{item}**: {money(price)}" for item, price in config.SHOP.items()]
    await inter.response.send_message(embed=embed("🛒 المتجر", "\n".join(lines) + "\n\nاشترِ بأمر /شراء"), ephemeral=True)


async def shop_autocomplete(inter: discord.Interaction, current: str):
    return [app_commands.Choice(name=f"{i} ({money(p)})", value=i) for i, p in config.SHOP.items() if current in i][:25]


async def inv_autocomplete(inter: discord.Interaction, current: str):
    rows = db.execute("SELECT item, qty FROM inventory WHERE user_id = ?", (inter.user.id,)).fetchall()
    return [app_commands.Choice(name=f"{r['item']} (×{r['qty']})", value=r["item"]) for r in rows if current in r["item"]][:25]


@bot.tree.command(name="شراء", description="شراء غرض من المتجر بالكاش")
@app_commands.autocomplete(الغرض=shop_autocomplete)
async def buy(inter: discord.Interaction, الغرض: str, العدد: app_commands.Range[int, 1, 100] = 1):
    if الغرض not in config.SHOP:
        return await inter.response.send_message(embed=err("الغرض غير موجود في المتجر."), ephemeral=True)
    p = await require_player(inter)
    if not p:
        return
    cost = config.SHOP[الغرض] * العدد
    if p["cash"] < cost:
        return await inter.response.send_message(embed=err(f"كاشك ما يكفي. السعر {money(cost)} وعندك {money(p['cash'])}"), ephemeral=True)
    db.execute("UPDATE players SET cash = cash - ? WHERE user_id = ?", (cost, inter.user.id))
    add_item(inter.user.id, الغرض, العدد)
    await inter.response.send_message(embed=embed("🛍️ تم الشراء", f"اشتريت **{الغرض}** ×{العدد} بـ {money(cost)}"), ephemeral=True)


@bot.tree.command(name="شنطتي", description="عرض الأغراض اللي معك")
async def inventory(inter: discord.Interaction):
    if not await require_player(inter):
        return
    rows = db.execute("SELECT item, qty FROM inventory WHERE user_id = ?", (inter.user.id,)).fetchall()
    text = "\n".join(f"• {r['item']} ×{r['qty']}" for r in rows) or "شنطتك فاضية."
    await inter.response.send_message(embed=embed("🎒 شنطتك", text), ephemeral=True)


@bot.tree.command(name="اعطاء_غرض", description="تعطي لاعب غرض من شنطتك")
@app_commands.autocomplete(الغرض=inv_autocomplete)
async def give_item(inter: discord.Interaction, اللاعب: discord.Member, الغرض: str, العدد: app_commands.Range[int, 1] = 1):
    if اللاعب.id == inter.user.id:
        return await inter.response.send_message(embed=err("ما تقدر تعطي نفسك."), ephemeral=True)
    if not await require_player(inter):
        return
    if not get_player(اللاعب.id):
        return await inter.response.send_message(embed=err(f"{اللاعب.mention} ما عنده هوية."), ephemeral=True)
    if item_qty(inter.user.id, الغرض) < العدد:
        return await inter.response.send_message(embed=err("ما عندك هالكمية من الغرض."), ephemeral=True)
    add_item(inter.user.id, الغرض, -العدد)
    add_item(اللاعب.id, الغرض, العدد)
    await inter.response.send_message(embed=embed("🤝 تسليم غرض", f"{inter.user.mention} عطى {اللاعب.mention} **{الغرض}** ×{العدد}"))


@bot.tree.command(name="تفتيش", description="تفتيش شنطة لاعب (للشرطة)")
async def search(inter: discord.Interaction, اللاعب: discord.Member):
    if not is_police(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للشرطة فقط."), ephemeral=True)
    p = await require_player(inter, اللاعب)
    if not p:
        return
    rows = db.execute("SELECT item, qty FROM inventory WHERE user_id = ?", (اللاعب.id,)).fetchall()
    text = "\n".join(f"• {r['item']} ×{r['qty']}" for r in rows) or "الشنطة فاضية."
    await inter.response.send_message(embed=embed(f"🔍 تفتيش {p['name']}", text + f"\n\n💵 كاش: {money(p['cash'])}"), ephemeral=True)
    await log(f"{inter.user.mention} فتّش {اللاعب.mention}", inter.guild)


# ============================================================
# أوامر الإدارة
# ============================================================
@bot.tree.command(name="اضافة_فلوس", description="إضافة فلوس للاعب (للإدارة)")
@app_commands.choices(المكان=[app_commands.Choice(name="البنك", value="bank"), app_commands.Choice(name="كاش", value="cash")])
async def admin_add(inter: discord.Interaction, اللاعب: discord.Member, المبلغ: app_commands.Range[int, 1], المكان: app_commands.Choice[str]):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    if not await require_player(inter, اللاعب):
        return
    db.execute(f"UPDATE players SET {المكان.value} = {المكان.value} + ? WHERE user_id = ?", (المبلغ, اللاعب.id))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تمت الإضافة", f"أضفت {money(المبلغ)} ({المكان.name}) لـ {اللاعب.mention}"), ephemeral=True)
    await log(f"{inter.user.mention} أضاف {money(المبلغ)} ({المكان.name}) لـ {اللاعب.mention}", inter.guild)


@bot.tree.command(name="خصم_فلوس", description="خصم فلوس من لاعب (للإدارة)")
@app_commands.choices(المكان=[app_commands.Choice(name="البنك", value="bank"), app_commands.Choice(name="كاش", value="cash")])
async def admin_remove(inter: discord.Interaction, اللاعب: discord.Member, المبلغ: app_commands.Range[int, 1], المكان: app_commands.Choice[str]):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    if not await require_player(inter, اللاعب):
        return
    db.execute(f"UPDATE players SET {المكان.value} = MAX(0, {المكان.value} - ?) WHERE user_id = ?", (المبلغ, اللاعب.id))
    db.commit()
    await inter.response.send_message(embed=embed("✅ تم الخصم", f"خصمت {money(المبلغ)} ({المكان.name}) من {اللاعب.mention}"), ephemeral=True)
    await log(f"{inter.user.mention} خصم {money(المبلغ)} ({المكان.name}) من {اللاعب.mention}", inter.guild)


@bot.tree.command(name="حذف_هوية", description="حذف هوية لاعب وكل بياناته (للإدارة)")
async def delete_id(inter: discord.Interaction, اللاعب: discord.Member):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    if not await require_player(inter, اللاعب):
        return
    for table in ("players", "fines", "records", "inventory"):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (اللاعب.id,))
    db.commit()
    await inter.response.send_message(embed=embed("🗑️ تم حذف الهوية", f"انحذفت هوية {اللاعب.mention} وكل بياناته."), ephemeral=True)
    await log(f"{inter.user.mention} حذف هوية {اللاعب.mention}", inter.guild)


@bot.tree.command(name="مساعدة", description="قائمة أوامر البوت")
async def help_cmd(inter: discord.Interaction):
    e = embed("📖 أوامر البوت")
    e.add_field(name="🪪 الهوية", value="من روم إنشاء الهوية وروم عرض الهوية (أزرار)", inline=False)
    e.add_field(name="🏦 البنك", value="/رصيدي · /ايداع · /سحب · /تحويل · /اعطاء_كاش · /الاغنى", inline=False)
    e.add_field(name="💼 الوظائف", value="/الوظائف · /راتب", inline=False)
    e.add_field(name="🛒 المتجر", value="/المتجر · /شراء · /شنطتي · /اعطاء_غرض", inline=False)
    e.add_field(name="🚨 المخالفات", value="/مخالفاتي · /سداد_مخالفة", inline=False)
    e.add_field(name="👮 الشرطة", value="/مخالفة · /اضافة_سجل · /سجل · /تفتيش · /هوية", inline=False)
    e.add_field(name="🛠️ الإدارة", value="/تسطيب_رومات · /تسطيب_رتب · /تعيين_وظيفة · /اضافة_فلوس · /خصم_فلوس · /مسح_سجل · /حذف_هوية", inline=False)
    e.add_field(name="🎫 التذاكر", value="/تسطيب_تذكرة · /حذف_تذكرة · /ارسال_التذاكر", inline=False)
    e.add_field(name="💬 الردود والإيمبد", value="/اضافة_رد · /حذف_رد · /الردود · /ايمبد · /رسالة_للكل", inline=False)
    e.add_field(name="📊 النقاط و MDT", value="/ارسال_لوحة · /حذف_يونت · /تسطيب_الاطار · /تسطيب_رتب_الادارة · /تسطيب_النقاط · /تعديل_نقاط · /تصفير_النقاط", inline=False)
    e.add_field(name="🏦 البنك والرواتب", value="/ارسال_لوحة (البنك) · /تسطيب_رتب_الشرطة · /تسطيب_الرواتب · /صرف_الرواتب", inline=False)
    e.add_field(name="📝 التقديمات", value="/تسطيب_تقديم · /اسئلة_تقديم · /حذف_تقديم · /ارسال_التقديمات", inline=False)
    e.add_field(name="💼 التوظيف والاستقالة", value="/تسطيب_وظيفة · /حذف_وظيفة · /قائمة_الوظائف · `-اسم_الوظيفة @الشخص` · `-استقالة @الشخص`", inline=False)
    e.add_field(name="🛡️ الإسكات والحظر", value="`-اسكات @العضو 30 السبب` · `-فك_اسكات @العضو` · `-حظر ايدي السبب` · `-فك_حظر ايدي` · /تسطيب_الادارة_العليا", inline=False)
    e.add_field(name="📝 الاختبار", value="/تحميل_الاسئلة · /اضافة_سؤال · العضو يكتب `T1` في تذكرته · `-تفعيل @العضو`", inline=False)
    e.add_field(name="✈️ الأقيام", value="`-قيم` في روم إنشاء القيم · `-تفتيش @العضو` في روم التفتيش · /تسطيب_التفتيش", inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)


# ============================================================
# البوت يقعد في روم صوتي 24 ساعة
# ============================================================
async def join_voice(guild: discord.Guild) -> bool:
    ch = guild.get_channel(get_setting(guild.id, "ch_voice"))
    if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
        return False
    vc = guild.voice_client
    try:
        if vc and vc.is_connected():
            if vc.channel.id != ch.id:
                await vc.move_to(ch)
            return True
        if vc:
            await vc.disconnect(force=True)
        await ch.connect(self_deaf=True, reconnect=True, timeout=30)
        print(f"🔊 دخلت الروم الصوتي: {ch.name}")
        return True
    except Exception as e:
        print(f"⚠️ ما قدرت أدخل الروم الصوتي: {e}")
        return False


async def voice_keeper():
    """يتأكد كل دقيقة إن البوت قاعد في الروم الصوتي، ولو طلع يرجعه"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            if get_setting(guild.id, "ch_voice"):
                await join_voice(guild)
        await asyncio.sleep(60)


# ============================================================
# التسطيب: الرومات والرتب
# ============================================================
def admin_only(inter: discord.Interaction) -> bool:
    return isinstance(inter.user, discord.Member) and inter.user.guild_permissions.administrator


@bot.tree.command(name="تسطيب_رومات", description="تحديد رومات البوت (لصاحب صلاحية الأدمن)")
@app_commands.describe(
    انشاء_هوية="الروم اللي فيه زر إنشاء الهوية",
    عرض_هوية="الروم اللي فيه زر عرض الهوية",
    انشاء_قيم="الروم اللي يكتبون فيه -قيم",
    شراء_تذكرة="الروم اللي ينرسل فيه إعلان الرحلة",
    التفتيش="الروم اللي يكتبون فيه -تفتيش",
    تحديث_الادوار="الروم اللي ينرسل فيه التوظيف والاستقالات",
    القروض="الروم اللي توصل فيه طلبات القروض",
    الصوتي="الروم الصوتي اللي يقعد فيه البوت 24 ساعة",
    اللوق="روم اللوق",
)
async def setup_channels(
    inter: discord.Interaction,
    انشاء_هوية: discord.TextChannel = None,
    عرض_هوية: discord.TextChannel = None,
    انشاء_قيم: discord.TextChannel = None,
    شراء_تذكرة: discord.TextChannel = None,
    التفتيش: discord.TextChannel = None,
    تحديث_الادوار: discord.TextChannel = None,
    القروض: discord.TextChannel = None,
    الصوتي: discord.VoiceChannel = None,
    اللوق: discord.TextChannel = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    gid = inter.guild.id
    done = []
    problems = []

    async def post_panel(ch, emb, view, label):
        try:
            await ch.send(embed=emb, view=view)
            done.append(f"✅ {label}: {ch.mention} (أرسلت اللوحة)")
        except discord.Forbidden:
            problems.append(f"⚠️ ما أقدر أرسل في {ch.mention}. عطني صلاحية الإرسال فيه.")

    if انشاء_هوية:
        set_setting(gid, "ch_create_id", انشاء_هوية.id)
        await post_panel(انشاء_هوية, create_id_panel_embed(), CreateIDPanel(), "إنشاء الهوية")
    if عرض_هوية:
        set_setting(gid, "ch_view_id", عرض_هوية.id)
        await post_panel(عرض_هوية, view_id_panel_embed(), ViewIDPanel(), "عرض الهوية")
    if انشاء_قيم:
        set_setting(gid, "ch_game", انشاء_قيم.id)
        done.append(f"✅ إنشاء القيم: {انشاء_قيم.mention}")
    if شراء_تذكرة:
        set_setting(gid, "ch_ticket", شراء_تذكرة.id)
        done.append(f"✅ شراء التذكرة: {شراء_تذكرة.mention}")
    if التفتيش:
        set_setting(gid, "ch_inspect", التفتيش.id)
        done.append(f"✅ التفتيش: {التفتيش.mention}")
    if تحديث_الادوار:
        set_setting(gid, "ch_roles_update", تحديث_الادوار.id)
        done.append(f"✅ تحديث الأدوار: {تحديث_الادوار.mention}")
    if القروض:
        set_setting(gid, "ch_loans", القروض.id)
        done.append(f"✅ القروض: {القروض.mention}")
    if الصوتي:
        set_setting(gid, "ch_voice", الصوتي.id)
        ok = await join_voice(inter.guild)
        done.append(f"✅ الصوتي: {الصوتي.mention}" + ("" if ok else " (⚠️ ما قدرت أدخل، شف صلاحية Connect)"))
    if اللوق:
        set_setting(gid, "ch_log", اللوق.id)
        done.append(f"✅ اللوق: {اللوق.mention}")

    if not done and not problems:
        rows = [
            ("إنشاء الهوية", "ch_create_id"), ("عرض الهوية", "ch_view_id"),
            ("إنشاء القيم", "ch_game"), ("شراء التذكرة", "ch_ticket"),
            ("التفتيش", "ch_inspect"), ("تحديث الأدوار", "ch_roles_update"),
            ("القروض", "ch_loans"), ("الصوتي", "ch_voice"), ("اللوق", "ch_log"),
        ]
        text = "\n".join(f"• {n}: {('<#%d>' % get_setting(gid, k)) if get_setting(gid, k) else 'ما تحدد'}" for n, k in rows)
        return await inter.followup.send(embed=embed("🛠️ الرومات الحالية", text + "\n\nاختر روم من خيارات الأمر عشان تغيّره."), ephemeral=True)
    await inter.followup.send(embed=embed("🛠️ تسطيب الرومات", "\n".join(done + problems)), ephemeral=True)


ROLE_KEYS = [
    ("الادارة", "role_admin", "الإدارة"),
    ("الشرطة", "role_police", "الشرطة"),
    ("الاجرام", "role_crime", "الإجرام"),
    ("الاعلام", "role_media", "الإعلام"),
    ("المواطن", "role_citizen", "المواطن"),
    ("الاقيام", "role_host", "الأقيام"),
    ("عضو_رسمي", "role_official", "عضو رسمي"),
    ("مقيم", "role_resident", "مقيم"),
    ("المفعلين", "role_activator", "المفعّلين (يقدرون يستخدمون -تفعيل)"),
    ("السوات", "role_swat", "السوات"),
    ("العدل", "role_justice", "العدل"),
    ("الاونر", "role_owner", "الأونر (يقدرون يستخدمون -حظر)"),
]


@bot.tree.command(name="تسطيب_رتب", description="تحديد رتب السيرفر (لصاحب صلاحية الأدمن)")
@app_commands.describe(
    الادارة="رتبة الإدارة",
    الشرطة="رتبة الشرطة",
    الاجرام="رتبة الإجرام",
    الاعلام="رتبة الإعلام",
    المواطن="الرتبة اللي تنعطى بعد إنشاء الهوية",
    الاقيام="الرتبة اللي تقدر تسوي -قيم",
    عضو_رسمي="الرتبة الأولى اللي تنعطى بأمر -تفعيل",
    مقيم="الرتبة الثانية اللي تنعطى بأمر -تفعيل",
    المفعلين="الرتبة اللي تقدر تستخدم -تفعيل",
    السوات="رتبة السوات",
    العدل="رتبة العدل",
    الاونر="الرتبة الأونرية اللي تقدر تستخدم -حظر",
)
async def setup_roles(
    inter: discord.Interaction,
    الادارة: discord.Role = None,
    الشرطة: discord.Role = None,
    الاجرام: discord.Role = None,
    الاعلام: discord.Role = None,
    المواطن: discord.Role = None,
    الاقيام: discord.Role = None,
    عضو_رسمي: discord.Role = None,
    مقيم: discord.Role = None,
    المفعلين: discord.Role = None,
    السوات: discord.Role = None,
    العدل: discord.Role = None,
    الاونر: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    given = {"الادارة": الادارة, "الشرطة": الشرطة, "الاجرام": الاجرام,
             "الاعلام": الاعلام, "المواطن": المواطن, "الاقيام": الاقيام,
             "عضو_رسمي": عضو_رسمي, "مقيم": مقيم,
             "المفعلين": المفعلين, "السوات": السوات, "العدل": العدل, "الاونر": الاونر}
    changed = []
    for arg, key, label in ROLE_KEYS:
        role = given[arg]
        if role:
            set_setting(gid, key, role.id)
            changed.append(f"✅ {label}: {role.mention}")
    if changed:
        return await inter.response.send_message(embed=embed("🛠️ تسطيب الرتب", "\n".join(changed)), ephemeral=True)
    text = "\n".join(
        f"• {label}: {('<@&%d>' % get_setting(gid, key)) if get_setting(gid, key) else 'ما تحددت'}"
        for _, key, label in ROLE_KEYS
    )
    await inter.response.send_message(embed=embed("🛠️ الرتب الحالية", text + "\n\nاختر رتبة من خيارات الأمر عشان تغيّرها."), ephemeral=True)


# ============================================================
# الأقيام: -قيم
# ============================================================
GAME_QUESTIONS = [
    ("host_id", "✈️ - اكتب **ايدي الهوست** (كابتن الطائرة)"),
    ("helper_id", "✈️ - اكتب **ايدي مساعد الهوست**"),
    ("board_time", "⏰ - اكتب **وقت التجوين** (موعد ركوب الرحلة)"),
    ("takeoff_time", "🛫 - اكتب **وقت الإقلاع**"),
]
active_games = set()


def flight_embed(guild: discord.Guild, host: discord.Member, a: dict) -> discord.Embed:
    desc = (
        "مرحباً بكم أعزائنا مواطنون مدينة سعودي تايم , تم الأعلان عن رحلة جوية إلى مطار سعودي تايم الرسمي , "
        "نرجوا الأستعداد والتجهز لموعد ركوب وإقلاع الطائرة .\n\n"
        f"**( 1 ) - كابتن الطائرة :** {a.get('host_name', host.mention)}\n"
        f"**( 2 ) - مساعد الطائرة :** {a['helper_name']}\n"
        f"**( 3 ) - أيدي كابتن الطائرة :** {a['host_id']}\n"
        f"**( 4 ) - أيدي مساعد الطائرة :** {a['helper_id']}\n"
        f"**( 5 ) - موعد ركوب الرحلة :** {a['board_time']}\n"
        f"**( 6 ) - موعد إقلاع الرحلة :** {a['takeoff_time']}\n\n"
        "**ملاحظات مهمة :**\n"
        "🔴 - إضافة كابتن الطائرة والمُساعد .\n"
        "🔴 - عدم إزعاج كابتن الطائرة والمُساعد .\n"
        "🔴 - عدم إزعاج داخل الطائرة عند ركوبك للرحلة .\n"
        "🔴 - وضع الحالة مُتصل لإمكانهم أرسال دعوة اليك ."
    )
    e = discord.Embed(title="✈️ - إعلان رحلة لدولة تايم .", description=desc, color=0x006C35, timestamp=now())
    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text=config.SERVER_NAME)
    return e


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if message.content.strip().startswith("-تفعيل"):
        return await activate_command(message)
    if message.content.strip().startswith("-تفتيش"):
        return await inspect_command(message)
    first = message.content.strip().split()[:1]
    m_t = re.fullmatch(r"[Tt](\d{1,2})", message.content.strip())
    if m_t and 1 <= int(m_t.group(1)) <= 20:
        return await quiz_shortcut(message, int(m_t.group(1)))
    if first in (["-اسكات"], ["-إسكات"]):
        return await mute_command(message)
    if first in (["-فك_اسكات"], ["-فك"]):
        return await unmute_command(message)
    if first == ["-حظر"]:
        return await ban_command(message, True)
    if first == ["-فك_حظر"]:
        return await ban_command(message, False)
    if message.content.strip().split()[:1] in (["-استقالة"], ["-استقاله"]):
        return await resign_command(message)
    if message.content.strip() != "-قيم":
        if message.content.strip().startswith("-") and await hire_command(message):
            return
        return await auto_reply(message)
    gid = message.guild.id
    game_ch = get_setting(gid, "ch_game")
    ticket_ch_id = get_setting(gid, "ch_ticket")
    if game_ch and message.channel.id != game_ch:
        return
    host_role = get_setting(gid, "role_host")
    if not (message.author.guild_permissions.administrator or
            (host_role and any(r.id == host_role for r in message.author.roles))):
        return await message.reply(embed=err("هذا الأمر لرتبة الأقيام بس."))
    if not ticket_ch_id:
        return await message.reply(embed=err("روم شراء التذكرة ما تحدد. خل الإدارة تستخدم /تسطيب_رومات"))
    key = (gid, message.author.id)
    if key in active_games:
        return await message.reply(embed=err("عندك قيم تنشئه الحين. كمّله أو اكتب **الغاء**"))
    active_games.add(key)

    def check(m: discord.Message):
        return m.author.id == message.author.id and m.channel.id == message.channel.id

    answers = {}
    try:
        await message.channel.send(embed=embed("✈️ إنشاء قيم", "جاوب على الأسئلة. تقدر تكتب **الغاء** بأي وقت."))
        for field, question in GAME_QUESTIONS:
            await message.channel.send(question)
            try:
                reply = await bot.wait_for("message", check=check, timeout=180)
            except asyncio.TimeoutError:
                return await message.channel.send(embed=err(f"{message.author.mention} خلص الوقت، انلغى القيم."))
            text = reply.content.strip()
            if text in ("الغاء", "إلغاء"):
                return await message.channel.send(embed=embed("❌ انلغى القيم"))
            if field == "helper_id":
                answers["helper_name"] = reply.mentions[0].mention if reply.mentions else text
                if reply.mentions:
                    text = str(reply.mentions[0].id)
            elif field == "host_id":
                answers["host_name"] = reply.mentions[0].mention if reply.mentions else message.author.mention
                if reply.mentions:
                    text = str(reply.mentions[0].id)
            answers[field] = text[:100] or "-"

        ticket_ch = message.guild.get_channel(ticket_ch_id)
        if not ticket_ch:
            return await message.channel.send(embed=err("ما لقيت روم شراء التذكرة. سطّبه من جديد."))
        try:
            await ticket_ch.send(embed=flight_embed(message.guild, message.author, answers))
        except discord.Forbidden:
            return await message.channel.send(embed=err(f"ما أقدر أرسل في {ticket_ch.mention}. عطني صلاحية."))
        add_points(gid, message.author.id, "admin", "publish", pts_value(gid, "pts_publish"))
        await message.channel.send(embed=embed("✅ تم نشر الرحلة", f"انرسل الإعلان في {ticket_ch.mention}"))
        await log(f"{message.author.mention} نشر رحلة في {ticket_ch.mention}", message.guild)
    finally:
        active_games.discard(key)


# ============================================================
# الرد التلقائي
# ============================================================
async def auto_reply(message: discord.Message):
    text = message.content.strip()
    if not text:
        return
    row = db.execute(
        "SELECT * FROM auto_replies WHERE guild_id = ? AND trigger = ?", (message.guild.id, text)
    ).fetchone()
    if not row:
        return
    try:
        if row["as_embed"]:
            e = discord.Embed(description=row["response"], color=0x006C35)
            e.set_footer(text=config.SERVER_NAME)
            await message.reply(embed=e, mention_author=False)
        else:
            await message.reply(row["response"], mention_author=False)
    except discord.HTTPException:
        pass


class AutoReplyModal(discord.ui.Modal, title="💬 الرد التلقائي"):
    response = discord.ui.TextInput(
        label="الرد", style=discord.TextStyle.paragraph, max_length=2000,
        placeholder="اكتب الرد اللي يرسله البوت، وتقدر تنزل سطر",
    )

    def __init__(self, trigger: str, as_embed: bool):
        super().__init__()
        self.trigger = trigger
        self.as_embed = as_embed

    async def on_submit(self, inter: discord.Interaction):
        db.execute(
            "INSERT INTO auto_replies (guild_id, trigger, response, as_embed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, trigger) DO UPDATE SET response = excluded.response, as_embed = excluded.as_embed",
            (inter.guild.id, self.trigger, self.response.value, int(self.as_embed)),
        )
        db.commit()
        await inter.response.send_message(
            embed=embed("✅ انضاف الرد", f"إذا أحد كتب **{self.trigger}** يرد البوت بـ{'ايمبد' if self.as_embed else 'رسالة'}:\n\n{self.response.value}"[:4000]),
            ephemeral=True,
        )


@bot.tree.command(name="اضافة_رد", description="إضافة رد تلقائي على كلمة")
@app_commands.describe(الكلمة="الكلمة اللي إذا أحد كتبها يرد البوت", ايمبد="الرد يطلع ايمبد؟")
@app_commands.choices(ايمبد=[app_commands.Choice(name="لا، رسالة عادية", value=0), app_commands.Choice(name="إيه، ايمبد", value=1)])
async def add_auto_reply(inter: discord.Interaction, الكلمة: app_commands.Range[str, 1, 100], ايمبد: app_commands.Choice[int] = None):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    await inter.response.send_modal(AutoReplyModal(الكلمة.strip(), bool(ايمبد and ايمبد.value)))


@bot.tree.command(name="حذف_رد", description="حذف رد تلقائي")
async def delete_auto_reply(inter: discord.Interaction, الكلمة: str):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    cur = db.execute("DELETE FROM auto_replies WHERE guild_id = ? AND trigger = ?", (inter.guild.id, الكلمة.strip()))
    db.commit()
    if not cur.rowcount:
        return await inter.response.send_message(embed=err("ما لقيت رد على هالكلمة. شف /الردود"), ephemeral=True)
    await inter.response.send_message(embed=embed("🗑️ انحذف الرد", الكلمة), ephemeral=True)


@delete_auto_reply.autocomplete("الكلمة")
async def auto_reply_autocomplete(inter: discord.Interaction, current: str):
    rows = db.execute("SELECT trigger FROM auto_replies WHERE guild_id = ?", (inter.guild.id,)).fetchall()
    return [app_commands.Choice(name=r["trigger"][:100], value=r["trigger"]) for r in rows if current in r["trigger"]][:25]


@bot.tree.command(name="الردود", description="عرض الردود التلقائية")
async def list_auto_replies(inter: discord.Interaction):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    rows = db.execute("SELECT * FROM auto_replies WHERE guild_id = ? ORDER BY trigger", (inter.guild.id,)).fetchall()
    if not rows:
        return await inter.response.send_message(embed=err("ما فيه ردود. أضف بـ /اضافة_رد"), ephemeral=True)
    text = "\n".join(
        f"• **{r['trigger']}** {'(ايمبد)' if r['as_embed'] else ''} ← {r['response'][:60]}{'…' if len(r['response']) > 60 else ''}"
        for r in rows
    )
    await inter.response.send_message(embed=embed("💬 الردود التلقائية", text[:4000]), ephemeral=True)


# ============================================================
# رسالة ايمبد
# ============================================================
EMBED_COLORS = {"green": 0x006C35, "red": 0xB3261E, "blue": 0x2B6CB0, "gold": 0xC9A227, "black": 0x1F1F1F, "white": 0xF2F2F2}


class EmbedModal(discord.ui.Modal, title="📝 رسالة ايمبد"):
    title_in = discord.ui.TextInput(label="العنوان (اختياري)", required=False, max_length=256)
    body_in = discord.ui.TextInput(
        label="الكلام", style=discord.TextStyle.paragraph, max_length=4000,
        placeholder="اكتب الكلام، وتقدر تنزل سطر وتستخدم **خط عريض**",
    )

    def __init__(self, channel: discord.TextChannel, color: int, image: discord.Attachment, mention: str):
        super().__init__()
        self.channel = channel
        self.color = color
        self.image = image
        self.mention = mention

    async def on_submit(self, inter: discord.Interaction):
        e = discord.Embed(title=self.title_in.value or None, description=self.body_in.value, color=self.color)
        e.set_footer(text=config.SERVER_NAME, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        kwargs = {"embed": e}
        if self.mention:
            kwargs["content"] = self.mention
            kwargs["allowed_mentions"] = discord.AllowedMentions(everyone=True, roles=True)
        await inter.response.defer(ephemeral=True)
        if self.image:
            try:
                f = await self.image.to_file()
                e.set_image(url=f"attachment://{f.filename}")
                kwargs["file"] = f
            except discord.HTTPException:
                pass
        try:
            await self.channel.send(**kwargs)
        except discord.Forbidden:
            return await inter.followup.send(embed=err(f"ما أقدر أرسل في {self.channel.mention}."), ephemeral=True)
        add_points(inter.guild.id, inter.user.id, "admin", "publish", pts_value(inter.guild.id, "pts_publish"))
        await inter.followup.send(embed=embed("✅ انرسل الايمبد", self.channel.mention), ephemeral=True)
        await log(f"{inter.user.mention} أرسل ايمبد في {self.channel.mention}", inter.guild)


@bot.tree.command(name="ايمبد", description="إرسال رسالة ايمبد في روم")
@app_commands.describe(الروم="الروم اللي ينرسل فيه", اللون="لون الايمبد", صورة="صورة تطلع تحت الكلام (اختياري)", منشن="منشن فوق الايمبد")
@app_commands.choices(
    اللون=[
        app_commands.Choice(name="أخضر", value="green"), app_commands.Choice(name="أحمر", value="red"),
        app_commands.Choice(name="أزرق", value="blue"), app_commands.Choice(name="ذهبي", value="gold"),
        app_commands.Choice(name="أسود", value="black"), app_commands.Choice(name="أبيض", value="white"),
    ],
    منشن=[
        app_commands.Choice(name="بدون", value="none"),
        app_commands.Choice(name="@everyone", value="@everyone"),
        app_commands.Choice(name="@here", value="@here"),
    ],
)
async def send_embed(
    inter: discord.Interaction,
    الروم: discord.TextChannel,
    اللون: app_commands.Choice[str] = None,
    صورة: discord.Attachment = None,
    منشن: app_commands.Choice[str] = None,
):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    if صورة and not (صورة.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("المرفق لازم يكون صورة."), ephemeral=True)
    color = EMBED_COLORS[اللون.value] if اللون else EMBED_COLORS["green"]
    mention = منشن.value if منشن and منشن.value != "none" else ""
    await inter.response.send_modal(EmbedModal(الروم, color, صورة, mention))


# ============================================================
# رسالة في الخاص لكل الأعضاء
# ============================================================
broadcast_running = set()  # guild ids


async def run_broadcast(guild: discord.Guild, members: list, e: discord.Embed, status_msg, author):
    sent = failed = 0
    try:
        for i, m in enumerate(members, 1):
            try:
                await m.send(embed=e)
                sent += 1
            except discord.HTTPException:
                failed += 1  # خاصه مقفل
            await asyncio.sleep(1.5)  # بطيء عشان ديسكورد ما يحظر البوت
            if i % 25 == 0:
                try:
                    await status_msg.edit(embed=embed("📨 جاري الإرسال...", f"{i} / {len(members)}"))
                except discord.HTTPException:
                    pass
    finally:
        broadcast_running.discard(guild.id)
    try:
        await status_msg.edit(embed=embed(
            "✅ خلص الإرسال",
            f"وصلت لـ **{sent}** عضو\nما وصلت لـ **{failed}** عضو (خاصهم مقفل)",
        ))
    except discord.HTTPException:
        pass
    await log(f"{author.mention} أرسل رسالة في الخاص لـ {sent} عضو", guild)


class BroadcastConfirm(discord.ui.View):
    def __init__(self, members: list, e: discord.Embed, author_id: int):
        super().__init__(timeout=120)
        self.members = members
        self.e = e
        self.author_id = author_id

    @discord.ui.button(label="أرسل", emoji="📨", style=discord.ButtonStyle.success)
    async def confirm(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.author_id:
            return await inter.response.send_message(embed=err("مو لك."), ephemeral=True)
        if inter.guild.id in broadcast_running:
            return await inter.response.edit_message(embed=err("فيه إرسال شغال الحين، انتظره يخلص."), view=None)
        broadcast_running.add(inter.guild.id)
        mins = max(1, round(len(self.members) * 1.5 / 60))
        await inter.response.edit_message(
            embed=embed("📨 بدأ الإرسال", f"بيوصل لـ {len(self.members)} عضو، وياخذ تقريباً {mins} دقيقة."), view=None
        )
        status = await inter.original_response()
        asyncio.create_task(run_broadcast(inter.guild, self.members, self.e, status, inter.user))
        self.stop()

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary)
    async def cancel(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.edit_message(embed=embed("❌ انلغى"), view=None)
        self.stop()


class BroadcastModal(discord.ui.Modal, title="📨 رسالة لكل الأعضاء"):
    title_in = discord.ui.TextInput(label="العنوان (اختياري)", required=False, max_length=256)
    body_in = discord.ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, role: discord.Role):
        super().__init__()
        self.role = role

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        if not guild.chunked:
            await guild.chunk()
        members = [m for m in (self.role.members if self.role else guild.members) if not m.bot]
        if not members:
            return await inter.followup.send(embed=err("ما لقيت أعضاء."), ephemeral=True)
        e = discord.Embed(title=self.title_in.value or None, description=self.body_in.value, color=0x006C35, timestamp=now())
        e.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        e.set_footer(text=config.SERVER_NAME)
        who = f"كل اللي معهم رتبة {self.role.mention}" if self.role else "كل أعضاء السيرفر"
        await inter.followup.send(
            content=f"**هذي معاينة الرسالة، بتنرسل لـ {who} ({len(members)} عضو). متأكد؟**",
            embed=e, view=BroadcastConfirm(members, e, inter.user.id), ephemeral=True,
        )


@bot.tree.command(name="رسالة_للكل", description="يرسل رسالتك في الخاص لكل الأعضاء (لصاحب صلاحية الأدمن)")
@app_commands.describe(رتبة="ترسل بس للي معهم هالرتبة (اختياري، بدونها ترسل للكل)")
async def broadcast(inter: discord.Interaction, رتبة: discord.Role = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if inter.guild.id in broadcast_running:
        return await inter.response.send_message(embed=err("فيه إرسال شغال الحين، انتظره يخلص."), ephemeral=True)
    await inter.response.send_modal(BroadcastModal(رتبة))


# ============================================================
# التذاكر (لين 10 أنواع)
# ============================================================
DEFAULT_TICKET_WELCOME = (
    "نؤد أن نخبرك انه يجب عليك الأنتظار حتى يتواصل معك الأداري المسؤول عن التذكرة , "
    "يجب أن تُقدم شرحا واضحا ومُبسط لنتمكن من خدمتك بشكل سريع وبشكل أفضل ."
)


def get_ticket_types(guild_id: int):
    return db.execute("SELECT * FROM ticket_types WHERE guild_id = ? ORDER BY slot", (guild_id,)).fetchall()


@bot.tree.command(name="تسطيب_تذكرة", description="إضافة أو تعديل نوع تذكرة (1-10 منيو، 11-20 أزرار)")
@app_commands.describe(
    الرقم="1 إلى 10 تطلع في المنيو، و 11 إلى 20 تطلع أزرار",
    الاسم="اسم التذكرة، مثل: جمارك، دعم فني، شكوى",
    الكاتقوري="الكاتقوري اللي تنفتح فيه التذاكر",
    رتبة_المسؤول="الرتبة اللي تستلم التذكرة وتشوفها",
    الايموجي="ايموجي يطلع جنب الاسم (اختياري)",
    رسالة_الترحيب="الكلام اللي يطلع أول ما تنفتح التذكرة (اختياري)",
)
async def setup_ticket(
    inter: discord.Interaction,
    الرقم: app_commands.Range[int, 1, 20],
    الاسم: app_commands.Range[str, 1, 40],
    الكاتقوري: discord.CategoryChannel,
    رتبة_المسؤول: discord.Role,
    الايموجي: str = None,
    رسالة_الترحيب: str = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    db.execute(
        "INSERT INTO ticket_types (guild_id, slot, name, emoji, category_id, staff_role, welcome) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id, slot) DO UPDATE SET name = excluded.name, emoji = excluded.emoji, "
        "category_id = excluded.category_id, staff_role = excluded.staff_role, welcome = excluded.welcome",
        (inter.guild.id, الرقم, الاسم, (الايموجي or "").strip()[:30], الكاتقوري.id, رتبة_المسؤول.id,
         رسالة_الترحيب or DEFAULT_TICKET_WELCOME),
    )
    db.commit()
    await inter.response.send_message(
        embed=embed(
            "🎫 تم تسطيب التذكرة",
            f"**رقم {الرقم}:** {الاسم}\nالكاتقوري: {الكاتقوري.mention}\nالمسؤول: {رتبة_المسؤول.mention}\n\n"
            "لما تخلص تسطيب التذاكر، استخدم **/ارسال_التذاكر** عشان ترسل اللوحة.",
        ),
        ephemeral=True,
    )


@bot.tree.command(name="حذف_تذكرة", description="حذف نوع تذكرة")
async def delete_ticket_type(inter: discord.Interaction, الرقم: app_commands.Range[int, 1, 20]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    db.execute("DELETE FROM ticket_types WHERE guild_id = ? AND slot = ?", (inter.guild.id, الرقم))
    db.commit()
    await inter.response.send_message(
        embed=embed("🗑️ تم الحذف", f"انحذفت التذكرة رقم {الرقم}. أرسل اللوحة من جديد بـ /ارسال_التذاكر"),
        ephemeral=True,
    )


def ticket_select(guild_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    options = [
        discord.SelectOption(label=t["name"], value=str(t["slot"]), emoji=t["emoji"] or None)
        for t in get_ticket_types(guild_id) if t["slot"] <= 10
    ]
    view.add_item(discord.ui.Select(custom_id="ticket:open", placeholder="- اختر نوع التذكرة .", options=options))
    return view


def ticket_buttons_panel(guild_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    styles = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.secondary, discord.ButtonStyle.danger]
    for i, t in enumerate([t for t in get_ticket_types(guild_id) if t["slot"] > 10]):
        view.add_item(discord.ui.Button(label=t["name"], emoji=t["emoji"] or None, style=styles[i % 4],
                                        custom_id=f"ticket:btn:{t['slot']}", row=i // 5))
    return view


@bot.tree.command(name="ارسال_التذاكر", description="إرسال لوحة التذاكر في روم")
@app_commands.describe(
    الروم="الروم اللي تنرسل فيه لوحة التذاكر",
    الشكل="منيو (التذاكر 1-10) أو أزرار (التذاكر 11-20)",
    الوصف="الكلام اللي فوق (اختياري)",
)
@app_commands.choices(الشكل=[
    app_commands.Choice(name="منيو (التذاكر 1 - 10)", value="menu"),
    app_commands.Choice(name="أزرار (التذاكر 11 - 20)", value="buttons"),
])
async def send_ticket_panel(inter: discord.Interaction, الروم: discord.TextChannel,
                            الشكل: app_commands.Choice[str] = None, الوصف: str = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    buttons = bool(الشكل and الشكل.value == "buttons")
    types = [t for t in get_ticket_types(inter.guild.id) if (t["slot"] > 10) == buttons]
    if not types:
        return await inter.response.send_message(embed=err(
            "ما سطّبت ولا تذكرة " + ("من 11 إلى 20 (الأزرار)." if buttons else "من 1 إلى 10 (المنيو).") + " استخدم /تسطيب_تذكرة"
        ), ephemeral=True)
    lines = "\n".join(f"{t['emoji'] or '🎫'} - {t['name']}" for t in types)
    e = embed(
        "🎫 - التذاكر",
        (الوصف or f"- مرحبا بك عزيزي العضو في قسم التذاكر الخاص بـ **{config.SERVER_NAME}** .\n\n"
                  + ("اضغط على الزر حق التذكرة اللي تبيها ." if buttons else "اختر نوع التذكرة من القائمة اللي تحت .")) + f"\n\n{lines}",
    )
    try:
        await الروم.send(embed=e, view=ticket_buttons_panel(inter.guild.id) if buttons else ticket_select(inter.guild.id))
    except discord.Forbidden:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    except discord.HTTPException:
        return await inter.response.send_message(
            embed=err("فيه ايموجي غلط في وحدة من التذاكر. عدّلها بـ /تسطيب_تذكرة وحط ايموجي عادي مثل 🛃"), ephemeral=True
        )
    await inter.response.send_message(embed=embed("✅ انرسلت لوحة التذاكر", الروم.mention), ephemeral=True)


def ticket_buttons() -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="إستلام التذكرة", style=discord.ButtonStyle.success, custom_id="ticket:claim"))
    view.add_item(discord.ui.Button(label="ترك التذكرة", style=discord.ButtonStyle.secondary, custom_id="ticket:unclaim"))
    view.add_item(discord.ui.Button(label="قفل التذكرة", style=discord.ButtonStyle.danger, custom_id="ticket:close"))
    return view


def is_ticket_staff(member: discord.Member, ttype) -> bool:
    if member.guild_permissions.administrator:
        return True
    return ttype is not None and any(r.id == ttype["staff_role"] for r in member.roles)


async def open_ticket(inter: discord.Interaction, slot: int):
    guild = inter.guild
    ttype = db.execute("SELECT * FROM ticket_types WHERE guild_id = ? AND slot = ?", (guild.id, slot)).fetchone()
    if not ttype:
        return await inter.response.send_message(embed=err("التذكرة هذي انحذفت."), ephemeral=True)
    existing = db.execute(
        "SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ? AND slot = ?",
        (guild.id, inter.user.id, slot),
    ).fetchone()
    if existing and guild.get_channel(existing["channel_id"]):
        return await inter.response.send_message(
            embed=err(f"عندك تذكرة مفتوحة من نفس النوع: <#{existing['channel_id']}>"), ephemeral=True
        )
    await inter.response.defer(ephemeral=True)
    db.execute("UPDATE ticket_types SET counter = counter + 1 WHERE guild_id = ? AND slot = ?", (guild.id, slot))
    db.commit()
    num = db.execute("SELECT counter FROM ticket_types WHERE guild_id = ? AND slot = ?", (guild.id, slot)).fetchone()["counter"]
    category = guild.get_channel(ttype["category_id"])
    staff = guild.get_role(ttype["staff_role"])
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
    }
    if staff:
        overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    try:
        ch = await guild.create_text_channel(
            name=f"{ttype['name']}-{num}",
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
        )
    except discord.Forbidden:
        return await inter.followup.send(embed=err("ما عندي صلاحية أسوي رومات. عطني صلاحية Manage Channels."), ephemeral=True)
    db.execute(
        "INSERT OR REPLACE INTO tickets (channel_id, guild_id, owner_id, slot, created_at) VALUES (?, ?, ?, ?, ?)",
        (ch.id, guild.id, inter.user.id, slot, now().isoformat()),
    )
    db.commit()
    e = embed(
        f"{ttype['emoji'] or '🎫'} - {ttype['name']}",
        f"**- مرحبا بك عزيزي العضو في قسم ( {ttype['name']} ) .**\n\n📄 - {ttype['welcome']}\n\n"
        f"مُقدم الطلب : ( {inter.user.mention} )",
    )
    await ch.send(content=f"{inter.user.mention} {staff.mention if staff else ''}", embed=e, view=ticket_buttons())
    await inter.followup.send(embed=embed("✅ انفتحت تذكرتك", ch.mention), ephemeral=True)
    await log(f"{inter.user.mention} فتح تذكرة **{ttype['name']}** {ch.mention}", guild)


async def handle_ticket_button(inter: discord.Interaction, action: str):
    t = db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
    if not t:
        return await inter.response.send_message(embed=err("هذي مو تذكرة مسجلة."), ephemeral=True)
    ttype = db.execute("SELECT * FROM ticket_types WHERE guild_id = ? AND slot = ?", (t["guild_id"], t["slot"])).fetchone()
    staff = is_ticket_staff(inter.user, ttype)

    if action == "claim":
        if not staff:
            return await inter.response.send_message(embed=err("الاستلام للإدارة المسؤولة بس."), ephemeral=True)
        if t["claimed_by"]:
            return await inter.response.send_message(embed=err(f"التذكرة مستلمة من <@{t['claimed_by']}>"), ephemeral=True)
        db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (inter.user.id, inter.channel.id))
        add_points(inter.guild.id, inter.user.id, "admin", "ticket", pts_value(inter.guild.id, "pts_ticket"))
        db.commit()
        await inter.response.send_message(embed=embed("✅ تم استلام التذكرة", f"المسؤول عن التذكرة: {inter.user.mention}"))

    elif action == "unclaim":
        if t["claimed_by"] != inter.user.id and not inter.user.guild_permissions.administrator:
            return await inter.response.send_message(embed=err("بس اللي مستلم التذكرة يقدر يتركها."), ephemeral=True)
        db.execute("UPDATE tickets SET claimed_by = 0 WHERE channel_id = ?", (inter.channel.id,))
        db.commit()
        await inter.response.send_message(embed=embed("↩️ تم ترك التذكرة", "التذكرة الحين متاحة لأي إداري يستلمها."))

    elif action == "close":
        if not staff and inter.user.id != t["owner_id"]:
            return await inter.response.send_message(embed=err("ما تقدر تقفل هذي التذكرة."), ephemeral=True)
        await inter.response.send_message(embed=embed("🔒 التذكرة بتنقفل بعد 5 ثواني", f"قفلها: {inter.user.mention}", 0xB3261E))
        db.execute("DELETE FROM tickets WHERE channel_id = ?", (inter.channel.id,))
        db.commit()
        await log(f"{inter.user.mention} قفل التذكرة **{inter.channel.name}** (صاحبها <@{t['owner_id']}>)", inter.guild)
        await asyncio.sleep(5)
        try:
            await inter.channel.delete()
        except discord.HTTPException:
            pass


# ============================================================
# أسئلة الاختبار
# ============================================================
def get_questions(guild_id: int, slot: int):
    return db.execute(
        "SELECT * FROM quiz_questions WHERE guild_id = ? AND slot = ? ORDER BY id", (guild_id, slot)
    ).fetchall()


@bot.tree.command(name="اضافة_سؤال", description="إضافة سؤال لاختبار تذكرة")
@app_commands.describe(
    رقم_التذكرة="رقم التذكرة من 1 إلى 10",
    السؤال="نص السؤال",
    الجواب_الصح="الجواب الصحيح",
    الجواب_الغلط="الجواب الغلط",
    غلط_2="جواب غلط ثاني (اختياري)",
    غلط_3="جواب غلط ثالث (اختياري)",
)
async def add_question(
    inter: discord.Interaction,
    رقم_التذكرة: app_commands.Range[int, 1, 20],
    السؤال: app_commands.Range[str, 1, 300],
    الجواب_الصح: app_commands.Range[str, 1, 80],
    الجواب_الغلط: app_commands.Range[str, 1, 80],
    غلط_2: app_commands.Range[str, 1, 80] = None,
    غلط_3: app_commands.Range[str, 1, 80] = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if len(get_questions(inter.guild.id, رقم_التذكرة)) >= 25:
        return await inter.response.send_message(embed=err("وصلت الحد: 25 سؤال لكل تذكرة."), ephemeral=True)
    db.execute(
        "INSERT INTO quiz_questions (guild_id, slot, question, right_a, wrong_a) VALUES (?, ?, ?, ?, ?)",
        (inter.guild.id, رقم_التذكرة, السؤال, الجواب_الصح, "\n".join(w for w in (الجواب_الغلط, غلط_2, غلط_3) if w)),
    )
    db.commit()
    n = len(get_questions(inter.guild.id, رقم_التذكرة))
    await inter.response.send_message(
        embed=embed("✅ انضاف السؤال", f"**{السؤال}**\n✅ {الجواب_الصح}\n❌ {' / '.join(w for w in (الجواب_الغلط, غلط_2, غلط_3) if w)}\n\nعدد أسئلة التذكرة {رقم_التذكرة}: **{n}**"),
        ephemeral=True,
    )


@bot.tree.command(name="الاسئلة", description="عرض أسئلة اختبار تذكرة")
async def list_questions(inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 20]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    qs = get_questions(inter.guild.id, رقم_التذكرة)
    if not qs:
        return await inter.response.send_message(embed=err("ما فيه أسئلة لهذي التذكرة."), ephemeral=True)
    text = "\n\n".join(
        f"**{i}. {q['question']}**\n✅ {q['right_a']}\n❌ {' / '.join(q['wrong_a'].splitlines())}" for i, q in enumerate(qs, 1)
    )
    await inter.response.send_message(embed=embed(f"📝 أسئلة التذكرة {رقم_التذكرة}", text[:4000]), ephemeral=True)


@bot.tree.command(name="حذف_سؤال", description="حذف سؤال من اختبار تذكرة")
@app_commands.describe(رقم_السؤال="رقم السؤال من أمر /الاسئلة")
async def delete_question(
    inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 20], رقم_السؤال: app_commands.Range[int, 1, 25]
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    qs = get_questions(inter.guild.id, رقم_التذكرة)
    if رقم_السؤال > len(qs):
        return await inter.response.send_message(embed=err("رقم السؤال غلط. شف /الاسئلة"), ephemeral=True)
    q = qs[رقم_السؤال - 1]
    db.execute("DELETE FROM quiz_questions WHERE id = ?", (q["id"],))
    db.commit()
    await inter.response.send_message(embed=embed("🗑️ انحذف السؤال", q["question"]), ephemeral=True)


DEFAULT_QUESTIONS = [
    ("القانون الذهبي هو عدم رد الخطأ بالخطأ ؟", "نعم", ["خطأ"]),
    ("قانون الرول بلاي هو تبادل الإحترام داخل الرحلات ؟", "خطأ", ["نعم"]),
    ("قانون تقدير الحياة هو الخوف على حياتك وحياة غيرك ؟", "نعم", ["خطأ"]),
    ("ماهو قانون القتل العشوائي ؟", "RDM", ["VDM"]),
    ("قانون الحاجز السمعي هو سماع الشخص من مسافة بعيدة ؟", "خطأ", ["نعم"]),
    ("هل يُسمح الخطف أو القتل بالمناطق الآمنة ؟", "خطأ", ["نعم"]),
    ("هل يُسمح سرقة الممتلكات الحكومية ؟", "نعم", ["خطأ"]),
    ("هل يُسمح الإزعاج بشكل عام ؟", "خطأ", ["نعم"]),
    ("هل يُسمح التوجه لأي مقر أول عشر دقائق ؟", "خطأ", ["نعم"]),
    ("إجبارية التوقف بعد إنفجار كم كفر ؟", "3", ["1", "2", "4"]),
]


@bot.tree.command(name="تحميل_الاسئلة", description="يحط أسئلة قوانين الرول بلاي الجاهزة (10 أسئلة) في تذكرة")
async def load_default_questions(inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 20]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    db.execute("DELETE FROM quiz_questions WHERE guild_id = ? AND slot = ?", (inter.guild.id, رقم_التذكرة))
    db.executemany(
        "INSERT INTO quiz_questions (guild_id, slot, question, right_a, wrong_a) VALUES (?, ?, ?, ?, ?)",
        [(inter.guild.id, رقم_التذكرة, q, r, "\n".join(w)) for q, r, w in DEFAULT_QUESTIONS],
    )
    db.commit()
    await inter.response.send_message(
        embed=embed("✅ انحطت الأسئلة", f"انحط {len(DEFAULT_QUESTIONS)} سؤال في التذكرة {رقم_التذكرة}. شوفها بـ /الاسئلة"),
        ephemeral=True,
    )


async def quiz_shortcut(message: discord.Message, n: int):
    """العضو يكتب T1 داخل تذكرته وتطلع له الأسئلة على طول"""
    t = db.execute("SELECT * FROM tickets WHERE channel_id = ?", (message.channel.id,)).fetchone()
    if not t or message.author.id != t["owner_id"]:
        return
    # T1 داخل أي تذكرة = أسئلة نفس التذكرة (مثلاً تذكرة 11 تجيب أسئلة 11)
    qs = get_questions(message.guild.id, t["slot"]) or get_questions(message.guild.id, n)
    if not qs:
        row = db.execute("SELECT slot FROM quiz_questions WHERE guild_id = ? ORDER BY slot LIMIT 1", (message.guild.id,)).fetchone()
        qs = get_questions(message.guild.id, row["slot"]) if row else []
    if not qs:
        return await message.reply(embed=err("ما فيه أسئلة. خل الإدارة تحطها بـ /تحميل_الاسئلة"))
    state = {"qs": qs, "i": 0, "right": 0, "wrong": []}
    quiz_state[(message.channel.id, message.author.id)] = state
    e, v = quiz_question_view(state)
    await message.channel.send(content=message.author.mention, embed=e, view=v)
    try:
        await message.delete()
    except discord.HTTPException:
        pass


quiz_state = {}  # (channel_id, user_id) -> {"qs": [...], "i": int, "right": int, "wrong": [..]}


def quiz_question_view(state: dict):
    q = state["qs"][state["i"]]
    total = len(state["qs"])
    e = embed(f"📝 السؤال {state['i'] + 1} من {total}", f"**{q['question']}**")
    choices = [("r", q["right_a"])] + [(f"w{n}", w) for n, w in enumerate(q["wrong_a"].splitlines())]
    labels = [c[1].strip() for c in choices]
    if all(l.isdigit() for l in labels):
        choices.sort(key=lambda c: int(c[1]))  # الأرقام بالترتيب 1 2 3 4
    elif set(labels) in ({"نعم", "خطأ"}, {"نعم", "لا"}):
        choices.sort(key=lambda c: 0 if c[1].strip() == "نعم" else 1)
    else:
        random.shuffle(choices)
    v = discord.ui.View(timeout=None)
    for key, text in choices:
        v.add_item(discord.ui.Button(label=text[:80], style=discord.ButtonStyle.secondary,
                                     custom_id=f"quiz:ans:{state['i']}:{key}"))
    return e, v


async def quiz_start(inter: discord.Interaction, cid: str = "quiz:start"):
    t = db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
    if not t:
        return await inter.response.send_message(embed=err("هذي مو تذكرة مسجلة."), ephemeral=True)
    if inter.user.id != t["owner_id"]:
        return await inter.response.send_message(embed=err("الاختبار لصاحب التذكرة بس."), ephemeral=True)
    parts = cid.split(":")
    slot = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else t["slot"]
    qs = get_questions(inter.guild.id, slot)
    if not qs:
        return await inter.response.send_message(embed=err("ما فيه أسئلة لهذي التذكرة."), ephemeral=True)
    state = {"qs": qs, "i": 0, "right": 0, "wrong": []}
    quiz_state[(inter.channel.id, inter.user.id)] = state
    e, v = quiz_question_view(state)
    await inter.response.send_message(embed=e, view=v, ephemeral=True)


async def quiz_answer(inter: discord.Interaction, cid: str):
    key = (inter.channel.id, inter.user.id)
    state = quiz_state.get(key)
    _, _, idx, choice = cid.split(":")
    if not state and db.execute("SELECT 1 FROM tickets WHERE channel_id = ? AND owner_id != ?",
                                (inter.channel.id, inter.user.id)).fetchone():
        return await inter.response.send_message(embed=err("الاختبار لصاحب التذكرة بس."), ephemeral=True)
    if not state or int(idx) != state["i"]:
        return await inter.response.send_message(embed=err("الاختبار انتهى أو انعاد. اضغط بدء الإختبار من جديد."), ephemeral=True)
    q = state["qs"][state["i"]]
    if choice == "r":
        state["right"] += 1  # أي شي غير r يعتبر غلط
    else:
        state["wrong"].append(q["question"])
    state["i"] += 1
    if state["i"] < len(state["qs"]):
        e, v = quiz_question_view(state)
        return await inter.response.edit_message(embed=e, view=v)

    quiz_state.pop(key, None)
    total = len(state["qs"])
    wrong = len(state["wrong"])
    passed = wrong <= config.MAX_WRONG
    need = max(total - config.MAX_WRONG, 0)
    if passed:
        await inter.response.edit_message(
            embed=embed("✅ نجحت في الاختبار", f"جاوبت {state['right']} من {total} صح. انتظر الإدارة تفعّلك."), view=None
        )
    else:
        await inter.response.edit_message(
            embed=embed("❌ لم تنجح في الاختبار", f"جاوبت {state['right']} من {total} صح، والمطلوب {need}.", 0xB3261E),
            view=None,
        )
        try:
            await inter.user.send(embed=embed(
                "❌ - لم تنجح في الاختبار",
                f"**- عزيزي العضو {inter.user.mention} .**\n\n"
                f"❗ - نُفيدك بأنك لم تتمكن من تجاوز الأختبار الخاص بـ **{config.SERVER_NAME}** , "
                "يجب عليك مُراجعة القوانين لتتمكن من إجتياز الأختبار للمرة القادمة .\n\n"
                f"الدرجة : **{state['right']} / {total}** ( المطلوب {need} )\n\n**( نتمنى لك التوفيق )**",
                0xB3261E,
            ))
        except discord.HTTPException:
            pass
    result = embed(
        "📝 نتيجة الاختبار",
        f"العضو: {inter.user.mention}\nالدرجة: **{state['right']} / {total}** (المطلوب {need})\n"
        + ("**✅ ناجح**، الإدارة تقدر تفعّله بـ `-تفعيل`" if passed else "**❌ مرفوض**، انرسل له في الخاص إنه لم ينجح")
        + ("\n\n**الأسئلة اللي غلط فيها:**\n" + "\n".join(f"• {w}" for w in state["wrong"]) if state["wrong"] else ""),
        0x0B6B55 if passed else 0xB3261E,
    )
    await inter.channel.send(embed=result)


# ============================================================
# التفتيش: -تفتيش @العضو
# ============================================================
@bot.tree.command(name="تسطيب_التفتيش", description="تحديد رتب الوظائف اللي تعتبر سليمة في التفتيش + الرسوم")
@app_commands.describe(
    وظيفة_1="رتبة وظيفة (تطلع سليم)", وظيفة_2="رتبة وظيفة", وظيفة_3="رتبة وظيفة",
    وظيفة_4="رتبة وظيفة", وظيفة_5="رتبة وظيفة",
    حذف="رتبة تشيلها من قائمة الوظائف",
    الرسوم="المبلغ اللي يطلع في رسالة التفتيش (الافتراضي 400)",
)
async def setup_inspect(
    inter: discord.Interaction,
    وظيفة_1: discord.Role = None, وظيفة_2: discord.Role = None, وظيفة_3: discord.Role = None,
    وظيفة_4: discord.Role = None, وظيفة_5: discord.Role = None,
    حذف: discord.Role = None,
    الرسوم: app_commands.Range[int, 0, 10_000_000] = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    changes = []
    for role in (وظيفة_1, وظيفة_2, وظيفة_3, وظيفة_4, وظيفة_5):
        if role:
            db.execute("INSERT OR IGNORE INTO inspect_roles (guild_id, role_id) VALUES (?, ?)", (gid, role.id))
            changes.append(f"➕ {role.mention}")
    if حذف:
        db.execute("DELETE FROM inspect_roles WHERE guild_id = ? AND role_id = ?", (gid, حذف.id))
        changes.append(f"➖ {حذف.mention}")
    if الرسوم is not None:
        set_setting(gid, "inspect_fee", الرسوم)
        changes.append(f"💵 الرسوم: {الرسوم}")
    db.commit()

    roles = db.execute("SELECT role_id FROM inspect_roles WHERE guild_id = ?", (gid,)).fetchall()
    extra = [("role_crime", "الإجرام"), ("role_police", "الشرطة"), ("role_media", "الإعلام"),
             ("role_host", "الأقيام"), ("role_admin", "الإدارة")]
    auto = [f"<@&{get_setting(gid, k)}>" for k, _ in extra if get_setting(gid, k)]
    text = (
        ("\n".join(changes) + "\n\n" if changes else "")
        + "**رتب الوظائف (سليم ✅):**\n"
        + ("\n".join(f"• <@&{r['role_id']}>" for r in roles) or "• ما فيه")
        + "\n\n**تنحسب تلقائي من /تسطيب_رتب:**\n" + (" ".join(auto) or "ما فيه")
        + f"\n\n**الرسوم:** {get_setting(gid, 'inspect_fee') or config.INSPECT_FEE}"
        + "\n\nاللي ما معه ولا وحدة من هالرتب يطلع **غير سليم ( لازم يتوظف )**."
    )
    await inter.response.send_message(embed=embed("🛃 تسطيب التفتيش", text[:4000]), ephemeral=True)


async def inspect_command(message: discord.Message):
    gid = message.guild.id
    inspect_ch = get_setting(gid, "ch_inspect")
    if not inspect_ch:
        return await message.reply(embed=err("روم التفتيش ما تحدد. خل الإدارة تستخدم /تسطيب_رومات"))
    if message.channel.id != inspect_ch:
        return
    host_role = get_setting(gid, "role_host")
    if not (message.author.guild_permissions.administrator or
            (host_role and any(r.id == host_role for r in message.author.roles))):
        return await message.reply(embed=err("التفتيش لرتبة الأقيام بس."))

    parts = message.content.split()
    usage = "الاستخدام: `-تفتيش @العضو` أو `-تفتيش ايدي_العضو`"
    member = message.mentions[0] if message.mentions else None
    if member is None and len(parts) >= 2 and parts[1].strip("<@!>").isdigit():
        uid = int(parts[1].strip("<@!>"))
        member = message.guild.get_member(uid)
        if member is None:
            try:
                member = await message.guild.fetch_member(uid)
            except discord.HTTPException:
                member = None
    if member is None or member.bot:
        return await message.reply(embed=err("ما لقيت العضو. " + usage))

    role_ids = {r.id for r in member.roles}
    # رتب الوظائف: الإجرام والشرطة والإعلام والأقيام والإدارة + رتب الوظائف اللي في JOBS
    job_roles = {
        "role_crime": "إجرام 🦹", "role_police": "شرطة 👮", "role_media": "إعلام 📰",
        "role_host": "أقيام ✈️", "role_admin": "إدارة 🛠️", "role_swat": "سوات 🪖", "role_justice": "عدل ⚖️",
    }
    kind = None
    for r in member.roles:
        if db.execute("SELECT 1 FROM inspect_roles WHERE guild_id = ? AND role_id = ?", (gid, r.id)).fetchone():
            kind = r.name
            break
        j = db.execute("SELECT name FROM job_roles WHERE guild_id = ? AND role_id = ?", (gid, r.id)).fetchone()
        if j:
            kind = j["name"]
            break
    for key, label in job_roles.items():
        if kind:
            break
        rid = get_setting(gid, key)
        if rid and rid in role_ids:
            kind = label
    if kind is None:
        for job, j in config.JOBS.items():
            if j.get("role_id") and j["role_id"] in role_ids:
                kind = job
                break
    if kind is None:
        p = get_player(member.id)
        if p and p["job"] and p["job"] != config.DEFAULT_JOB:
            kind = p["job"]
    clean = kind is not None
    status = "سليم ✅" if clean else "غير سليم ❌ ( لازم يتوظف )"
    kind = kind or "بدون وظيفة"

    e = embed(
        "🛃 - نتيجة التفتيش",
        f"**العضو :** {member.mention}\n**ايدي العضو :** `{member.id}`\n**الصفة :** {kind}\n"
        f"**النتيجة :** {status}\n**المفتش :** {message.author.mention}",
        0x006C35 if clean else 0xB3261E,
    )
    dm = embed(
        "🛃 - تم تفتيشك",
        f"**- عزيزي {member.mention} .**\n\n"
        f"✈️ - تم تفتيشك من قبل ( {message.author.mention} ) في مطار **{config.SERVER_NAME}** .\n\n"
        f"**النتيجة :** {status}\n"
        + (f"💵 - تم سحب **{get_setting(gid, 'inspect_fee') or config.INSPECT_FEE}** {config.CURRENCY} رسوم التفتيش .\n\n**( نتمنى لك رحلة سعيدة )**"
           if clean else "\n🚫 - لا يمكنك دخول الرحلة , يجب عليك التوظف أولاً .\n\n**( نتمنى لك التوفيق )**"),
        0x006C35 if clean else 0xB3261E,
    )
    try:
        await member.send(embed=dm)
        e.set_footer(text=f"{config.SERVER_NAME} | انرسلت له رسالة في الخاص")
    except discord.HTTPException:
        e.set_footer(text=f"{config.SERVER_NAME} | ما وصلته رسالة الخاص (خاصه مقفل)")
    await message.reply(embed=e)
    await log(f"{message.author.mention} فتّش {member.mention}: {status}", message.guild)


# ============================================================
# الإسكات بالتسلسل + الحظر للأونر
# ============================================================
def parse_duration(text: str):
    """10 = 10 دقايق، 10m / 10د ، 2h / 2س ، 1d / 1ي"""
    m = re.fullmatch(r"(\d{1,4})\s*(m|min|د|دقيقة|دقايق|h|س|ساعة|ساعات|d|ي|يوم|ايام)?", text.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), (m.group(2) or "m")
    if unit in ("h", "س", "ساعة", "ساعات"):
        mins = n * 60
    elif unit in ("d", "ي", "يوم", "ايام"):
        mins = n * 1440
    else:
        mins = n
    return max(1, min(mins, 28 * 1440))


def fmt_minutes(mins: int) -> str:
    if mins % 1440 == 0:
        return f"{mins // 1440} يوم"
    if mins % 60 == 0:
        return f"{mins // 60} ساعة"
    return f"{mins} دقيقة"


async def mute_command(message: discord.Message):
    lvl = staff_level(message.author)
    if lvl <= 0:
        return await message.reply(embed=err("الإسكات للإدارة بس."))
    parts = message.content.split()
    member = await find_member_in_message(message, " ".join(parts[1:]))
    if member is None or member.bot:
        return await message.reply(embed=err("الاستخدام: `-اسكات @العضو المدة السبب`\nمثال: `-اسكات @فهد 30 سب` (30 دقيقة) أو `2h` أو `1d`"))
    if member.id == message.author.id:
        return await message.reply(embed=err("ما تقدر تسكت نفسك."))
    if staff_level(member) >= lvl:
        return await message.reply(embed=err(f"ما تقدر تسكت {member.mention}، رتبته مثلك أو أعلى منك."))
    rest = [x for x in parts[2:] if not x.startswith("<@")]
    mins = parse_duration(rest[0]) if rest else None
    reason = " ".join(rest[1:] if mins else rest) or "بدون سبب"
    mins = mins or 10
    try:
        await member.timeout(timedelta(minutes=mins), reason=f"{message.author}: {reason}")
    except discord.Forbidden:
        return await message.reply(embed=err("ما أقدر أسكته. عطني صلاحية Timeout Members وخل رتبتي فوق رتبته."))
    e = embed("🔇 - تم الإسكات",
              f"**العضو :** {member.mention}\n**المدة :** {fmt_minutes(mins)}\n**السبب :** {reason}\n**بواسطة :** {message.author.mention}",
              0xB98118)
    await message.reply(embed=e)
    try:
        await member.send(embed=embed("🔇 - تم إسكاتك", f"تم إسكاتك في **{config.SERVER_NAME}** لمدة **{fmt_minutes(mins)}**\n**السبب :** {reason}", 0xB98118))
    except discord.HTTPException:
        pass
    await log(f"{message.author.mention} سكّت {member.mention} {fmt_minutes(mins)}: {reason}", message.guild)


async def unmute_command(message: discord.Message):
    lvl = staff_level(message.author)
    if lvl <= 0:
        return await message.reply(embed=err("فك الإسكات للإدارة بس."))
    parts = message.content.split()
    member = await find_member_in_message(message, " ".join(parts[1:]))
    if member is None:
        return await message.reply(embed=err("الاستخدام: `-فك_اسكات @العضو`"))
    if staff_level(member) >= lvl:
        return await message.reply(embed=err("رتبته مثلك أو أعلى منك."))
    try:
        await member.timeout(None, reason=f"فك إسكات بواسطة {message.author}")
    except discord.Forbidden:
        return await message.reply(embed=err("ما أقدر أفك إسكاته."))
    await message.reply(embed=embed("🔊 - تم فك الإسكات", f"{member.mention} بواسطة {message.author.mention}"))
    await log(f"{message.author.mention} فك إسكات {member.mention}", message.guild)


async def ban_command(message: discord.Message, ban: bool):
    owner_role = get_setting(message.guild.id, "role_owner")
    allowed = message.author.id == message.guild.owner_id or (owner_role and any(r.id == owner_role for r in message.author.roles))
    if not allowed:
        return await message.reply(embed=err("الحظر للرتبة الأونرية بس."))
    parts = message.content.split()
    raw = parts[1].strip("<@!>") if len(parts) > 1 else ""
    if not raw.isdigit():
        return await message.reply(embed=err("الاستخدام: `-حظر ايدي_العضو السبب`" if ban else "الاستخدام: `-فك_حظر ايدي_العضو`"))
    uid = int(raw)
    reason = " ".join(parts[2:]) or "بدون سبب"
    if uid in (message.author.id, message.guild.owner_id, bot.user.id if bot.user else 0):
        return await message.reply(embed=err("ما تقدر تحظر هذا الشخص."))
    member = message.guild.get_member(uid)
    if ban and member and staff_level(member) >= staff_level(message.author):
        return await message.reply(embed=err("رتبته مثلك أو أعلى منك."))
    try:
        if ban:
            if member:
                try:
                    await member.send(embed=embed("⛔ - تم حظرك", f"تم حظرك من **{config.SERVER_NAME}**\n**السبب :** {reason}", 0xB3261E))
                except discord.HTTPException:
                    pass
            await message.guild.ban(discord.Object(id=uid), reason=f"{message.author}: {reason}", delete_message_seconds=0)
        else:
            await message.guild.unban(discord.Object(id=uid), reason=f"فك حظر بواسطة {message.author}")
    except discord.NotFound:
        return await message.reply(embed=err("ما لقيت العضو." if ban else "هالشخص مو محظور."))
    except discord.Forbidden:
        return await message.reply(embed=err("ما عندي صلاحية Ban Members، أو رتبتي تحت رتبته."))
    title = "⛔ - تم الحظر" if ban else "✅ - تم فك الحظر"
    await message.reply(embed=embed(title, f"**الايدي :** `{uid}`\n" + (f"**السبب :** {reason}\n" if ban else "")
                                    + f"**بواسطة :** {message.author.mention}", 0xB3261E if ban else 0x006C35))
    await log(f"{message.author.mention} {'حظر' if ban else 'فك حظر'} `{uid}` {reason if ban else ''}", message.guild)


# ============================================================
# التفعيل: -تفعيل @العضو ايدي_سوني
# ============================================================
def can_activate(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {r.id for r in member.roles}
    activator = get_setting(member.guild.id, "role_activator")
    if activator and activator in ids:
        return True
    admin_role = get_setting(member.guild.id, "role_admin")
    if admin_role and admin_role in ids:
        return True
    return any(t["staff_role"] in ids for t in get_ticket_types(member.guild.id))


async def activate_command(message: discord.Message):
    if not can_activate(message.author):
        return await message.reply(embed=err("التفعيل لرتبة المفعّلين بس."))
    parts = message.content.split()
    usage = "الاستخدام: `-تفعيل @العضو` (وتقدر تضيف ايدي سوني بعده)"
    if len(parts) < 2:
        return await message.reply(embed=err(usage))
    member = message.mentions[0] if message.mentions else None
    if member is None:
        raw = parts[1].strip("<@!>")
        if raw.isdigit():
            member = message.guild.get_member(int(raw))
            if member is None:
                try:
                    member = await message.guild.fetch_member(int(raw))
                except discord.HTTPException:
                    member = None
    if member is None:
        return await message.reply(embed=err("ما لقيت العضو. " + usage))
    sony_id = " ".join(parts[2:])[:60] or "-"

    role_ids = [get_setting(message.guild.id, "role_official"), get_setting(message.guild.id, "role_resident")]
    roles = [message.guild.get_role(r) for r in role_ids if r]
    roles = [r for r in roles if r]
    if not roles:
        return await message.reply(embed=err("رتبة عضو رسمي ومقيم ما تحددت. استخدم /تسطيب_رتب"))
    try:
        await member.add_roles(*roles, reason=f"تفعيل بواسطة {message.author}")
    except discord.Forbidden:
        return await message.reply(embed=err("ما أقدر أعطي الرتب. خل رتبة البوت فوق رتبة عضو رسمي ومقيم."))

    db.execute(
        "INSERT INTO activations (guild_id, user_id, sony_id, by_id, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET sony_id = excluded.sony_id, by_id = excluded.by_id, created_at = excluded.created_at",
        (message.guild.id, member.id, sony_id, message.author.id, now().isoformat()),
    )
    db.commit()
    e = embed(
        "✅ - تم التفعيل",
        f"**العضو :** {member.mention}\n**ايدي العضو :** `{member.id}`\n**ايدي سوني :** `{sony_id}`\n"
        f"**الرتب :** {' '.join(r.mention for r in roles)}\n**بواسطة :** {message.author.mention}",
    )
    await message.reply(embed=e)
    try:
        await member.send(embed=embed(
            "✅ - تم تفعيلك",
            f"**- عزيزي {member.mention} .**\n\n🎉 - تم تفعيلك في **{config.SERVER_NAME}** بنجاح , "
            f"وصرت الحين عضو رسمي ومقيم في المدينة .\n\n📄 - نرجوا منك الالتزام بالقوانين , ونتمنى لك وقت ممتع معنا 🇸🇦\n\n"
            f"**المفعّل :** {message.author.mention}",
        ))
    except discord.HTTPException:
        pass
    add_points(message.guild.id, message.author.id, "admin", "activate", pts_value(message.guild.id, "pts_activate"))
    await log(f"{message.author.mention} فعّل {member.mention} (سوني: `{sony_id}`)", message.guild)


# ============================================================
# نظام النقاط: الإدارة + الشرطة (MDT)
# ============================================================
POINT_DEFAULTS = {
    "pts_publish": 2,     # نشر رحلة (-قيم) أو ايمبد
    "pts_activate": 3,    # -تفعيل
    "pts_ticket": 1,      # استلام تذكرة
    "pts_hire": 2,        # توظيف
    "pts_resign": 1,      # استقالة
    "pts_arrest": 3,      # قبض على مجرم
    "pts_fine": 1,        # مخالفة
    "pts_duty_min": 30,   # كل كم دقيقة دوام = نقطة
}
ADMIN_CATS = {"publish": "📢 نقاط النشر", "activate": "✅ نقاط التفعيل", "hire": "💼 نقاط التوظيف",
              "ticket": "🎫 نقاط استلام التكتات", "resign": "📤 نقاط الاستقالات", "manual": "✏️ نقاط يدوية"}
POLICE_CATS = {"duty": "🕒 نقاط تسجيل الدخول", "arrest": "🚔 نقاط القبض", "fine": "🧾 نقاط المخالفات", "manual": "✏️ نقاط يدوية"}
UPPER_RANKS = ["SIR", "LeadeR", "Damon", "BoSS", "AssistanT", "CommaNDeR", "Co Founder", "Founder"]  # من الأقل للأعلى
UPPER_ARGS = ["sir", "leader", "damon", "boss", "assistant", "commander", "co_founder", "founder"]
# من الأعلى للأقل
RANK_KEYS = ([(f"rank_u{i}", UPPER_RANKS[i - 1]) for i in range(8, 0, -1)]
             + [(f"rank_m{i}", f"Middle {i}") for i in range(7, 0, -1)]
             + [(f"rank_j{i}", f"Junior {i}") for i in range(7, 0, -1)])
# المستوى: Junior 1 = 1 ... Junior 7 = 7، Middle 1 = 8 ... Middle 7 = 14، SIR = 15 ... Founder = 22
RANK_LEVEL = {**{f"rank_j{i}": i for i in range(1, 8)}, **{f"rank_m{i}": 7 + i for i in range(1, 8)},
              **{f"rank_u{i}": 14 + i for i in range(1, 9)}}


def staff_level(member: discord.Member) -> int:
    if member.id == member.guild.owner_id:
        return 1000
    ids = {r.id for r in member.roles}
    owner_role = get_setting(member.guild.id, "role_owner")
    if owner_role and owner_role in ids:
        return 500  # الرتبة الأونرية فوق كل الإدارة
    level = 0
    for key, lvl in RANK_LEVEL.items():
        rid = get_setting(member.guild.id, key)
        if rid and rid in ids:
            level = max(level, lvl)
    if level == 0 and member.guild_permissions.administrator:
        level = 100
    return level


def pts_value(gid: int, key: str) -> int:
    v = get_setting(gid, key)
    return v if v else POINT_DEFAULTS[key]


def add_points(gid: int, uid: int, kind: str, cat: str, amount: int):
    if not amount:
        return
    db.execute(
        "INSERT INTO points_log (guild_id, user_id, kind, category, amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (gid, uid, kind, cat, amount, now().isoformat()),
    )
    db.commit()


def points_breakdown(gid: int, uid: int, kind: str) -> dict:
    rows = db.execute(
        "SELECT category, SUM(amount) AS s FROM points_log WHERE guild_id = ? AND user_id = ? AND kind = ? GROUP BY category",
        (gid, uid, kind),
    ).fetchall()
    return {r["category"]: r["s"] or 0 for r in rows}


def points_top(gid: int, kind: str, limit: int = 10, category: str = None):
    if category:
        return db.execute(
            "SELECT user_id, SUM(amount) AS s FROM points_log WHERE guild_id = ? AND kind = ? AND category = ? "
            "GROUP BY user_id HAVING s > 0 ORDER BY s DESC LIMIT ?",
            (gid, kind, category, limit),
        ).fetchall()
    return db.execute(
        "SELECT user_id, SUM(amount) AS s FROM points_log WHERE guild_id = ? AND kind = ? "
        "GROUP BY user_id HAVING s > 0 ORDER BY s DESC LIMIT ?",
        (gid, kind, limit),
    ).fetchall()


def points_rank(gid: int, uid: int, kind: str):
    rows = db.execute(
        "SELECT user_id, SUM(amount) AS s FROM points_log WHERE guild_id = ? AND kind = ? GROUP BY user_id ORDER BY s DESC",
        (gid, kind),
    ).fetchall()
    for i, r in enumerate(rows, 1):
        if r["user_id"] == uid:
            return i
    return None


def admin_rank_name(member: discord.Member) -> str:
    ids = {r.id for r in member.roles}
    top = get_setting(member.guild.id, "role_admin")
    if top and top in ids:
        return "الإدارة العليا 👑"
    for key, name in RANK_KEYS:
        rid = get_setting(member.guild.id, key)
        if rid and rid in ids:
            return name
    return "—"


def is_staff_member(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    ids = {r.id for r in member.roles}
    keys = ["role_admin"] + [k for k, _ in RANK_KEYS]
    return any(get_setting(member.guild.id, k) in ids for k in keys if get_setting(member.guild.id, k))


def frame_file(gid: int, kind: str):
    row = db.execute("SELECT filename, data FROM assets WHERE guild_id = ? AND key = ?", (gid, f"frame_{kind}"),).fetchone()
    if not row:
        row = db.execute("SELECT filename, data FROM assets WHERE guild_id = ? AND key = 'frame_admin'", (gid,)).fetchone()
    if not row:
        return None
    return discord.File(io.BytesIO(row["data"]), filename=row["filename"])


def points_card(guild: discord.Guild, member: discord.Member, kind: str):
    cats = ADMIN_CATS if kind == "admin" else POLICE_CATS
    b = points_breakdown(guild.id, member.id, kind)
    total = sum(b.values())
    rank = points_rank(guild.id, member.id, kind)
    title = "📊 نقاط الإدارة" if kind == "admin" else "🚓 نقاط الشرطة"
    e = discord.Embed(title=title, color=0x006C35 if kind == "admin" else 0x2B6CB0, timestamp=now())
    if guild.me:
        e.set_author(name=guild.me.display_name, icon_url=guild.me.display_avatar.url)
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 العضو", value=member.mention, inline=True)
    if kind == "admin":
        e.add_field(name="🎖️ الرتبة الإدارية", value=admin_rank_name(member), inline=True)
    else:
        mins = db.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS m FROM duty_sessions WHERE guild_id = ? AND user_id = ?",
            (guild.id, member.id),
        ).fetchone()["m"]
        e.add_field(name="⏱️ ساعات الدوام", value=f"{mins // 60} ساعة و {mins % 60} دقيقة", inline=True)
    for key, label in cats.items():
        if key == "manual" and not b.get("manual"):
            continue
        e.add_field(name=label, value=f"**{b.get(key, 0)}**", inline=True)
    e.add_field(name="⭐ المجموع", value=f"**{total}**", inline=True)
    e.add_field(name="🏆 الترتيب", value=f"#{rank}" if rank else "—", inline=True)
    e.set_footer(text=config.SERVER_NAME)
    f = frame_file(guild.id, kind)
    if f:
        e.set_image(url=f"attachment://{f.filename}")
    return e, f


def top_embed(guild: discord.Guild, kind: str, category: str = None):
    rows = points_top(guild.id, kind, category=category)
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else f'**{i + 1}.**'} <@{r['user_id']}> : **{r['s']}** نقطة" for i, r in enumerate(rows)]
    title = "🏆 أفضل 10 في الإدارة" if kind == "admin" else "🏆 أفضل 10 في الشرطة"
    if category:
        title = f"🏆 أفضل 10 | {(ADMIN_CATS if kind == 'admin' else POLICE_CATS).get(category, category)}"
    e = discord.Embed(title=title, description="\n".join(lines) or "ما فيه نقاط للحين.", color=0xC9A227, timestamp=now())
    if guild.me:
        e.set_author(name=guild.me.display_name, icon_url=guild.me.display_avatar.url)
    e.set_footer(text=config.SERVER_NAME)
    f = frame_file(guild.id, kind)
    if f:
        e.set_image(url=f"attachment://{f.filename}")
    return e, f


def again_view(kind: str) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="إعادة الاختيار", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id=f"pts:again:{kind}"))
    return v


def admin_menu_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Select(
        custom_id="pts:admin", placeholder="- اختر من القائمة .",
        options=[
            discord.SelectOption(label="نقاطي", value="me", emoji="📊"),
            discord.SelectOption(label="نقاط شخص معين", value="user", emoji="🔎"),
            discord.SelectOption(label="توب أفضل عشرة", value="top", emoji="🏆"),
            discord.SelectOption(label="توب النشر", value="top:publish", emoji="📢"),
            discord.SelectOption(label="توب التفعيل", value="top:activate", emoji="✅"),
            discord.SelectOption(label="توب التوظيف", value="top:hire", emoji="💼"),
            discord.SelectOption(label="توب استلام التكتات", value="top:ticket", emoji="🎫"),
            discord.SelectOption(label="توب الاستقالات", value="top:resign", emoji="📤"),
        ],
    ))
    return v


def mdt_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="تسجيل دخول", emoji="🟢", style=discord.ButtonStyle.success, custom_id="mdt:in", row=0))
    v.add_item(discord.ui.Button(label="تسجيل خروج", emoji="🔴", style=discord.ButtonStyle.danger, custom_id="mdt:out", row=0))
    v.add_item(discord.ui.Button(label="بحث عن مواطن", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="mdt:search", row=1))
    v.add_item(discord.ui.Button(label="قبض على مجرم", emoji="🚔", style=discord.ButtonStyle.primary, custom_id="mdt:arrest", row=1))
    v.add_item(discord.ui.Button(label="مخالفة", emoji="🧾", style=discord.ButtonStyle.primary, custom_id="mdt:fine", row=1))
    v.add_item(discord.ui.Button(label="نقاطي", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="mdt:me", row=2))
    v.add_item(discord.ui.Button(label="نقاط شخص معين", emoji="👤", style=discord.ButtonStyle.secondary, custom_id="mdt:user", row=2))
    v.add_item(discord.ui.Button(label="توب أفضل عشرة", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="mdt:top", row=2))
    v.add_item(discord.ui.Button(label="المتواجدين بالدوام", emoji="👮", style=discord.ButtonStyle.secondary, custom_id="mdt:onduty", row=2))
    return v


async def send_card(inter: discord.Interaction, e: discord.Embed, f, kind: str, edit: bool = False):
    kwargs = {"embed": e, "view": again_view(kind)}
    if f:
        kwargs["file"] = f
    if inter.response.is_done():
        await inter.followup.send(ephemeral=True, **kwargs)
    else:
        await inter.response.send_message(ephemeral=True, **kwargs)


class PickUserView(discord.ui.View):
    def __init__(self, kind: str):
        super().__init__(timeout=120)
        self.kind = kind
        sel = discord.ui.UserSelect(placeholder="اختر الشخص")
        sel.callback = self.picked
        self.sel = sel
        self.add_item(sel)

    async def picked(self, inter: discord.Interaction):
        member = self.sel.values[0]
        if not isinstance(member, discord.Member):
            member = inter.guild.get_member(member.id)
        if member is None:
            return await inter.response.send_message(embed=err("ما لقيت العضو."), ephemeral=True)
        e, f = points_card(inter.guild, member, self.kind)
        await send_card(inter, e, f, self.kind)


def resolve_member_text(guild: discord.Guild, text: str):
    raw = text.strip().strip("<@!>")
    if raw.isdigit():
        return guild.get_member(int(raw))
    return None


class MDTSearchModal(discord.ui.Modal, title="🔎 بحث عن مواطن"):
    who = discord.ui.TextInput(label="ايدي العضو في ديسكورد", placeholder="مثال: 123456789012345678", max_length=25)

    async def on_submit(self, inter: discord.Interaction):
        member = resolve_member_text(inter.guild, self.who.value)
        if member is None:
            return await inter.response.send_message(embed=err("ما لقيت العضو. تأكد من الايدي."), ephemeral=True)
        p = get_player(member.id)
        if not p:
            return await inter.response.send_message(embed=err(f"{member.mention} ما عنده هوية."), ephemeral=True)
        recs = db.execute("SELECT * FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 10", (member.id,)).fetchall()
        fines_ = db.execute("SELECT * FROM fines WHERE user_id = ? AND paid = 0", (member.id,)).fetchall()
        e = id_card(p, member)
        e.title = "💻 MDT - ملف المواطن"
        e.add_field(
            name=f"📁 السجل الجنائي ({len(recs)})",
            value="\n".join(f"• {r['charge']} ({r['created_at'][:10]})" for r in recs) or "نظيف ✅",
            inline=False,
        )
        e.add_field(
            name="🧾 مخالفات غير مسددة",
            value=f"{len(fines_)} مخالفة بمجموع {money(sum(f['amount'] for f in fines_))}" if fines_ else "لا يوجد",
            inline=False,
        )
        await inter.response.send_message(embed=e, ephemeral=True)


class MDTArrestModal(discord.ui.Modal, title="🚔 قبض على مجرم"):
    who = discord.ui.TextInput(label="ايدي المجرم في ديسكورد", max_length=25)
    charge = discord.ui.TextInput(label="التهمة", max_length=200)
    jail = discord.ui.TextInput(label="مدة السجن", placeholder="مثال: 15 دقيقة", max_length=40)
    fine_in = discord.ui.TextInput(label="الغرامة (اختياري)", placeholder="مثال: 5000", required=False, max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        member = resolve_member_text(inter.guild, self.who.value)
        if member is None:
            return await inter.response.send_message(embed=err("ما لقيت المجرم. تأكد من الايدي."), ephemeral=True)
        if member.id == inter.user.id:
            return await inter.response.send_message(embed=err("ما تقدر تقبض على نفسك."), ephemeral=True)
        charge = f"{self.charge.value} ( سجن {self.jail.value} )"
        db.execute("INSERT INTO records (user_id, charge, officer, created_at) VALUES (?, ?, ?, ?)",
                   (member.id, charge, inter.user.id, now().isoformat()))
        amount = int(self.fine_in.value) if self.fine_in.value.strip().isdigit() else 0
        if amount:
            db.execute("INSERT INTO fines (user_id, amount, reason, officer, created_at) VALUES (?, ?, ?, ?, ?)",
                       (member.id, amount, self.charge.value, inter.user.id, now().isoformat()))
        db.commit()
        pts = pts_value(inter.guild.id, "pts_arrest")
        add_points(inter.guild.id, inter.user.id, "police", "arrest", pts)
        e = embed("🚔 - تم القبض", color=0xB3261E)
        e.add_field(name="المجرم", value=member.mention)
        e.add_field(name="التهمة", value=self.charge.value)
        e.add_field(name="مدة السجن", value=self.jail.value)
        if amount:
            e.add_field(name="الغرامة", value=money(amount))
        e.add_field(name="الشرطي", value=inter.user.mention)
        await inter.response.send_message(embed=e)
        await inter.followup.send(embed=embed("✅ انضافت لك نقاط", f"+{pts} نقطة قبض"), ephemeral=True)
        try:
            await member.send(embed=embed(
                "🚔 - تم القبض عليك",
                f"**التهمة :** {self.charge.value}\n**مدة السجن :** {self.jail.value}"
                + (f"\n**الغرامة :** {money(amount)}" if amount else "") + f"\n**الشرطي :** {inter.user.mention}",
                0xB3261E,
            ))
        except discord.HTTPException:
            pass
        await log(f"{inter.user.mention} قبض على {member.mention}: {charge}", inter.guild)


class MDTFineModal(discord.ui.Modal, title="🧾 مخالفة"):
    who = discord.ui.TextInput(label="ايدي المخالف في ديسكورد", max_length=25)
    amount = discord.ui.TextInput(label="المبلغ", placeholder="مثال: 1500", max_length=12)
    reason = discord.ui.TextInput(label="السبب", max_length=200)

    async def on_submit(self, inter: discord.Interaction):
        member = resolve_member_text(inter.guild, self.who.value)
        if member is None:
            return await inter.response.send_message(embed=err("ما لقيت العضو. تأكد من الايدي."), ephemeral=True)
        if not self.amount.value.strip().isdigit() or int(self.amount.value) <= 0:
            return await inter.response.send_message(embed=err("المبلغ لازم يكون رقم."), ephemeral=True)
        amount = int(self.amount.value)
        cur = db.execute("INSERT INTO fines (user_id, amount, reason, officer, created_at) VALUES (?, ?, ?, ?, ?)",
                         (member.id, amount, self.reason.value, inter.user.id, now().isoformat()))
        db.commit()
        pts = pts_value(inter.guild.id, "pts_fine")
        add_points(inter.guild.id, inter.user.id, "police", "fine", pts)
        e = embed("🚨 مخالفة جديدة", color=0xB98118)
        e.add_field(name="المخالف", value=member.mention)
        e.add_field(name="المبلغ", value=money(amount))
        e.add_field(name="رقم المخالفة", value=f"#{cur.lastrowid}")
        e.add_field(name="السبب", value=self.reason.value, inline=False)
        e.add_field(name="الشرطي", value=inter.user.mention, inline=False)
        await inter.response.send_message(content=member.mention, embed=e)
        await inter.followup.send(embed=embed("✅ انضافت لك نقاط", f"+{pts} نقطة مخالفة"), ephemeral=True)
        await log(f"{inter.user.mention} خالف {member.mention} بـ {money(amount)}: {self.reason.value}", inter.guild)


async def handle_points_interaction(inter: discord.Interaction, cid: str):
    guild = inter.guild
    if cid == "pts:admin":
        if not is_staff_member(inter.user):
            return await inter.response.send_message(embed=err("هذي القائمة للإدارة بس."), ephemeral=True)
        choice = (inter.data.get("values") or ["me"])[0]
        if choice == "me":
            e, f = points_card(guild, inter.user, "admin")
            await send_card(inter, e, f, "admin")
        elif choice == "user":
            await inter.response.send_message(embed=embed("🔎 اختر الشخص"), view=PickUserView("admin"), ephemeral=True)
        else:
            cat = choice.split(":")[1] if ":" in choice else None
            e, f = top_embed(guild, "admin", cat)
            await send_card(inter, e, f, "admin")
        try:  # نرجّع القائمة فاضية عشان يقدر يختار نفس الخيار مرة ثانية
            await inter.message.edit(view=admin_menu_view())
        except discord.HTTPException:
            pass
        return

    if cid.startswith("pts:again:"):
        kind = cid.split(":")[2]
        if kind == "admin":
            return await inter.response.send_message(embed=embed("📊 نقاط الإدارة", "اختر من القائمة ."), view=admin_menu_view(), ephemeral=True)
        return await inter.response.send_message(embed=embed("💻 MDT الشرطة", "اختر من الأزرار ."), view=mdt_view(), ephemeral=True)

    # ---- MDT ----
    if not (is_police(inter) or is_staff_member(inter.user)):
        return await inter.response.send_message(embed=err("الـ MDT للشرطة بس."), ephemeral=True)
    action = cid.split(":")[1]
    gid, uid = guild.id, inter.user.id
    if action == "in":
        row = db.execute("SELECT started_at FROM duty_active WHERE guild_id = ? AND user_id = ?", (gid, uid)).fetchone()
        if row:
            return await inter.response.send_message(embed=err("أنت مسجل دخول من قبل."), ephemeral=True)
        db.execute("INSERT INTO duty_active (guild_id, user_id, started_at) VALUES (?, ?, ?)", (gid, uid, now().isoformat()))
        db.commit()
        await inter.response.send_message(embed=embed("🟢 - تسجيل دخول", f"{inter.user.mention} سجّل دخول للدوام ."), ephemeral=False)
        await log(f"{inter.user.mention} سجّل دخول دوام الشرطة", guild)
    elif action == "out":
        row = db.execute("SELECT started_at FROM duty_active WHERE guild_id = ? AND user_id = ?", (gid, uid)).fetchone()
        if not row:
            return await inter.response.send_message(embed=err("أنت مو مسجل دخول."), ephemeral=True)
        mins = int((now() - datetime.fromisoformat(row["started_at"])).total_seconds() // 60)
        per = pts_value(gid, "pts_duty_min")
        pts = mins // per if per else 0
        db.execute("DELETE FROM duty_active WHERE guild_id = ? AND user_id = ?", (gid, uid))
        db.execute("INSERT INTO duty_sessions (guild_id, user_id, started_at, minutes) VALUES (?, ?, ?, ?)",
                   (gid, uid, row["started_at"], mins))
        db.commit()
        add_points(gid, uid, "police", "duty", pts)
        await inter.response.send_message(embed=embed(
            "🔴 - تسجيل خروج",
            f"{inter.user.mention} سجّل خروج .\n**مدة الدوام :** {mins // 60} ساعة و {mins % 60} دقيقة\n**النقاط :** +{pts}",
        ))
        await log(f"{inter.user.mention} سجّل خروج بعد {mins} دقيقة (+{pts})", guild)
    elif action == "search":
        await inter.response.send_modal(MDTSearchModal())
    elif action == "arrest":
        await inter.response.send_modal(MDTArrestModal())
    elif action == "fine":
        await inter.response.send_modal(MDTFineModal())
    elif action == "me":
        e, f = points_card(guild, inter.user, "police")
        await send_card(inter, e, f, "police")
    elif action == "user":
        await inter.response.send_message(embed=embed("👤 اختر الشخص"), view=PickUserView("police"), ephemeral=True)
    elif action == "top":
        e, f = top_embed(guild, "police")
        await send_card(inter, e, f, "police")
    elif action == "onduty":
        rows = db.execute("SELECT user_id, started_at FROM duty_active WHERE guild_id = ?", (gid,)).fetchall()
        lines = []
        for r in rows:
            m = int((now() - datetime.fromisoformat(r["started_at"])).total_seconds() // 60)
            lines.append(f"• <@{r['user_id']}> ( من {m} دقيقة )")
        await inter.response.send_message(embed=embed("👮 المتواجدين بالدوام", "\n".join(lines) or "ما فيه أحد."), ephemeral=True)


# ---------- أوامر التسطيب ----------
@bot.tree.command(name="ارسال_لوحة", description="إرسال لوحة نقاط الإدارة أو MDT الشرطة في روم")
@app_commands.choices(النوع=[
    app_commands.Choice(name="نقاط الإدارة", value="admin"),
    app_commands.Choice(name="MDT الشرطة", value="mdt"),
    app_commands.Choice(name="اليونتات LSPD / SWAT", value="units"),
    app_commands.Choice(name="البنك", value="bank"),
])
async def send_points_panel(inter: discord.Interaction, النوع: app_commands.Choice[str], الروم: discord.TextChannel):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if النوع.value == "admin":
        e = embed("📊 - نقاط الإدارة", f"**- مرحبا بك عزيزي الإداري في نظام نقاط {config.SERVER_NAME} .**\n\nاختر من القائمة اللي تحت .")
        view = admin_menu_view()
    elif النوع.value == "bank":
        e = embed("🏦 - بنك سعودي تايم", f"**- مرحبا بك في بنك {config.SERVER_NAME} .**\n\n"
                  "🏦 افتح حسابك وخذ رقم الآيبان حقك\n💳 شوف رصيدك\n📥 📤 إيداع وسحب\n"
                  "🔁 حوّل لأي أحد بالآيبان أو الايدي\n📝 💸 اطلب قرض وسدده", 0x006C35)
        view = bank_view()
    elif النوع.value == "units":
        e = embed("🚓 - اليونتات", f"**- مرحبا بك عزيزي العسكري في {config.SERVER_NAME} .**\n\n"
                  "اضغط على القطاع حقك وبيطلع لك رقم اليونت ويتغيّر اسمك تلقائي .\n\n"
                  "🔵 **LSPD** ← يونت يبدأ بـ **D-**\n⚫ **SWAT** ← يونت يبدأ بـ **S-**", 0x2B6CB0)
        view = units_view()
    else:
        e = embed("💻 - MDT الشرطة", f"**- مرحبا بك عزيزي العسكري في نظام {config.SERVER_NAME} .**\n\n"
                  "🟢 سجّل دخول أول ما تبدأ دوامك، و 🔴 سجّل خروج إذا خلصت .", 0x2B6CB0)
        view = mdt_view()
    try:
        await الروم.send(embed=e, view=view)
    except discord.Forbidden:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    await inter.response.send_message(embed=embed("✅ انرسلت اللوحة", الروم.mention), ephemeral=True)


@bot.tree.command(name="تسطيب_الاطار", description="رفع صورة الإطار اللي تطلع تحت النقاط")
@app_commands.choices(النوع=[
    app_commands.Choice(name="الإدارة", value="admin"),
    app_commands.Choice(name="الشرطة", value="police"),
])
async def setup_frame(inter: discord.Interaction, الصورة: discord.Attachment, النوع: app_commands.Choice[str] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if not (الصورة.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("لازم تكون صورة."), ephemeral=True)
    if الصورة.size > 7_000_000:
        return await inter.response.send_message(embed=err("الصورة كبيرة، خلها أقل من 7 ميقا."), ephemeral=True)
    kind = النوع.value if النوع else "admin"
    data = await الصورة.read()
    ext = (الصورة.filename.rsplit(".", 1)[-1] or "png").lower()
    db.execute(
        "INSERT INTO assets (guild_id, key, filename, data) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, key) DO UPDATE SET filename = excluded.filename, data = excluded.data",
        (inter.guild.id, f"frame_{kind}", f"frame_{kind}.{ext}", data),
    )
    db.commit()
    await inter.response.send_message(
        embed=embed("✅ انحفظ الإطار", f"إطار {'الإدارة' if kind == 'admin' else 'الشرطة'}. (إذا ما حطيت إطار للشرطة، يطلع إطار الإدارة)"),
        ephemeral=True,
    )


@bot.tree.command(name="تسطيب_رتب_الادارة", description="تحديد رتب الإدارة من Junior 1 إلى Middle 7")
@app_commands.describe(**{f"جونير_{i}": f"رتبة Junior {i}" for i in range(1, 8)}, **{f"ميدل_{i}": f"رتبة Middle {i}" for i in range(1, 8)})
async def setup_admin_ranks(
    inter: discord.Interaction,
    جونير_1: discord.Role = None, جونير_2: discord.Role = None, جونير_3: discord.Role = None, جونير_4: discord.Role = None,
    جونير_5: discord.Role = None, جونير_6: discord.Role = None, جونير_7: discord.Role = None,
    ميدل_1: discord.Role = None, ميدل_2: discord.Role = None, ميدل_3: discord.Role = None, ميدل_4: discord.Role = None,
    ميدل_5: discord.Role = None, ميدل_6: discord.Role = None, ميدل_7: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    given = {
        **{f"rank_j{i}": r for i, r in enumerate((جونير_1, جونير_2, جونير_3, جونير_4, جونير_5, جونير_6, جونير_7), 1)},
        **{f"rank_m{i}": r for i, r in enumerate((ميدل_1, ميدل_2, ميدل_3, ميدل_4, ميدل_5, ميدل_6, ميدل_7), 1)},
    }
    for key, role in given.items():
        if role:
            set_setting(gid, key, role.id)
    order = [(f"rank_j{i}", f"Junior {i}") for i in range(1, 8)] + [(f"rank_m{i}", f"Middle {i}") for i in range(1, 8)]
    top = get_setting(gid, "role_admin")
    text = "\n".join(f"• {name}: {('<@&%d>' % get_setting(gid, k)) if get_setting(gid, k) else 'ما تحددت'}" for k, name in order)
    text += f"\n\n👑 **الإدارة العليا:** {('<@&%d>' % top) if top else 'حددها من /تسطيب_رتب (الادارة)'}"
    await inter.response.send_message(embed=embed("🎖️ رتب الإدارة", text), ephemeral=True)


@bot.tree.command(name="تسطيب_الادارة_العليا", description="تحديد رتب الإدارة العليا من SIR إلى Founder")
@app_commands.describe(
    sir="رتبة SIR",
    leader="رتبة LeadeR",
    damon="رتبة Damon",
    boss="رتبة BoSS",
    assistant="رتبة AssistanT",
    commander="رتبة CommaNDeR",
    co_founder="رتبة Co Founder",
    founder="رتبة Founder",
)
async def setup_upper_ranks(
    inter: discord.Interaction,
    sir: discord.Role = None,
    leader: discord.Role = None,
    damon: discord.Role = None,
    boss: discord.Role = None,
    assistant: discord.Role = None,
    commander: discord.Role = None,
    co_founder: discord.Role = None,
    founder: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    for i, role in enumerate((sir, leader, damon, boss, assistant, commander, co_founder, founder), 1):
        if role:
            set_setting(gid, f"rank_u{i}", role.id)
    text = "\n".join(
        f"• {UPPER_RANKS[i - 1]}: {('<@&%d>' % get_setting(gid, f'rank_u{i}')) if get_setting(gid, f'rank_u{i}') else 'ما تحددت'}"
        for i in range(8, 0, -1)
    )
    await inter.response.send_message(embed=embed("👑 الإدارة العليا", text + "\n\nالترتيب من الأعلى للأقل، وتحتهم Middle 7 لين Junior 1 ."), ephemeral=True)


@bot.tree.command(name="تسطيب_النقاط", description="كم نقطة لكل شي")
@app_commands.describe(
    النشر="نقاط نشر رحلة أو ايمبد (الافتراضي 2)", التفعيل="نقاط أمر -تفعيل (الافتراضي 3)",
    التذكرة="نقاط استلام تذكرة (الافتراضي 1)", القبض="نقاط القبض على مجرم (الافتراضي 3)",
    التوظيف="نقاط التوظيف (الافتراضي 2)", الاستقالة="نقاط الاستقالة (الافتراضي 1)",
    المخالفة="نقاط المخالفة (الافتراضي 1)", دقائق_الدوام="كل كم دقيقة دوام = نقطة (الافتراضي 30)",
)
async def setup_points(
    inter: discord.Interaction,
    النشر: app_commands.Range[int, 0, 1000] = None, التفعيل: app_commands.Range[int, 0, 1000] = None,
    التذكرة: app_commands.Range[int, 0, 1000] = None, القبض: app_commands.Range[int, 0, 1000] = None,
    المخالفة: app_commands.Range[int, 0, 1000] = None, دقائق_الدوام: app_commands.Range[int, 1, 1440] = None,
    التوظيف: app_commands.Range[int, 0, 1000] = None, الاستقالة: app_commands.Range[int, 0, 1000] = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    for key, val in (("pts_publish", النشر), ("pts_activate", التفعيل), ("pts_ticket", التذكرة),
                     ("pts_arrest", القبض), ("pts_fine", المخالفة), ("pts_duty_min", دقائق_الدوام),
                     ("pts_hire", التوظيف), ("pts_resign", الاستقالة)):
        if val is not None:
            set_setting(gid, key, val)
    text = (
        f"📢 النشر: **{pts_value(gid, 'pts_publish')}**\n✅ التفعيل: **{pts_value(gid, 'pts_activate')}**\n"
        f"🎫 استلام تذكرة: **{pts_value(gid, 'pts_ticket')}**\n💼 التوظيف: **{pts_value(gid, 'pts_hire')}**\n"
        f"📤 الاستقالة: **{pts_value(gid, 'pts_resign')}**\n🚔 القبض: **{pts_value(gid, 'pts_arrest')}**\n"
        f"🧾 المخالفة: **{pts_value(gid, 'pts_fine')}**\n🕒 نقطة كل **{pts_value(gid, 'pts_duty_min')}** دقيقة دوام"
    )
    await inter.response.send_message(embed=embed("⚙️ إعدادات النقاط", text), ephemeral=True)


@bot.tree.command(name="تعديل_نقاط", description="إضافة أو خصم نقاط (لصاحب صلاحية الأدمن)")
@app_commands.describe(العدد="موجب للإضافة، سالب للخصم (مثال: -5)")
@app_commands.choices(النوع=[
    app_commands.Choice(name="نقاط الإدارة", value="admin"),
    app_commands.Choice(name="نقاط الشرطة", value="police"),
])
async def edit_points(inter: discord.Interaction, النوع: app_commands.Choice[str], العضو: discord.Member,
                      العدد: app_commands.Range[int, -100000, 100000]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    add_points(inter.guild.id, العضو.id, النوع.value, "manual", العدد)
    total = sum(points_breakdown(inter.guild.id, العضو.id, النوع.value).values())
    await inter.response.send_message(
        embed=embed("✏️ تم تعديل النقاط", f"{العضو.mention}: {'+' if العدد > 0 else ''}{العدد}\nالمجموع الحين: **{total}**"),
        ephemeral=True,
    )
    await log(f"{inter.user.mention} عدّل {النوع.name} لـ {العضو.mention}: {العدد}", inter.guild)


@bot.tree.command(name="تصفير_النقاط", description="تصفير نقاط الكل أو عضو معين (لصاحب صلاحية الأدمن)")
@app_commands.choices(النوع=[
    app_commands.Choice(name="نقاط الإدارة", value="admin"),
    app_commands.Choice(name="نقاط الشرطة", value="police"),
])
async def reset_points(inter: discord.Interaction, النوع: app_commands.Choice[str], العضو: discord.Member = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if العضو:
        db.execute("DELETE FROM points_log WHERE guild_id = ? AND kind = ? AND user_id = ?", (inter.guild.id, النوع.value, العضو.id))
    else:
        db.execute("DELETE FROM points_log WHERE guild_id = ? AND kind = ?", (inter.guild.id, النوع.value))
    db.commit()
    await inter.response.send_message(
        embed=embed("🗑️ تم التصفير", f"{النوع.name} لـ {العضو.mention if العضو else 'الكل'}"), ephemeral=True
    )
    await log(f"{inter.user.mention} صفّر {النوع.name} لـ {العضو.mention if العضو else 'الكل'}", inter.guild)


# ============================================================
# التقديمات (لين 10 أنواع)
# ============================================================
def get_app_types(gid: int):
    return db.execute("SELECT * FROM app_types WHERE guild_id = ? ORDER BY slot", (gid,)).fetchall()


def get_app_type(gid: int, slot: int):
    return db.execute("SELECT * FROM app_types WHERE guild_id = ? AND slot = ?", (gid, slot)).fetchone()


@bot.tree.command(name="تسطيب_تقديم", description="إضافة أو تعديل تقديم (لين 10)")
@app_commands.describe(
    الرقم="رقم التقديم من 1 إلى 10",
    الاسم="اسم التقديم، مثل: تقديم شرطة",
    روم_المراجعة="الروم اللي تنرسل فيه التقديمات للإدارة",
    رتبة_1="الرتبة الأولى اللي تنعطى إذا انقبل",
    رتبة_2="الرتبة الثانية اللي تنعطى إذا انقبل (اختياري)",
    المراجعين="الرتبة اللي تقدر تقبل وترفض (اختياري، الافتراضي الإدارة)",
    الايموجي="ايموجي جنب الاسم (اختياري)",
)
async def setup_application(
    inter: discord.Interaction,
    الرقم: app_commands.Range[int, 1, 10],
    الاسم: app_commands.Range[str, 1, 60],
    روم_المراجعة: discord.TextChannel,
    رتبة_1: discord.Role,
    رتبة_2: discord.Role = None,
    المراجعين: discord.Role = None,
    الايموجي: str = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    old = get_app_type(inter.guild.id, الرقم)
    db.execute(
        "INSERT INTO app_types (guild_id, slot, name, emoji, review_ch, role1, role2, reviewer_role, questions) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id, slot) DO UPDATE SET name = excluded.name, "
        "emoji = excluded.emoji, review_ch = excluded.review_ch, role1 = excluded.role1, role2 = excluded.role2, "
        "reviewer_role = excluded.reviewer_role",
        (inter.guild.id, الرقم, الاسم, (الايموجي or "").strip()[:30], روم_المراجعة.id, رتبة_1.id,
         رتبة_2.id if رتبة_2 else 0, المراجعين.id if المراجعين else 0, old["questions"] if old else ""),
    )
    db.commit()
    await inter.response.send_message(embed=embed(
        "📝 تم تسطيب التقديم",
        f"**رقم {الرقم}:** {الاسم}\nروم المراجعة: {روم_المراجعة.mention}\n"
        f"الرتب إذا انقبل: {رتبة_1.mention} {رتبة_2.mention if رتبة_2 else ''}\n\n"
        f"الحين حط أسئلته بـ **/اسئلة_تقديم** وبعدها أرسل اللوحة بـ **/ارسال_التقديمات**",
    ), ephemeral=True)


class AppQuestionsModal(discord.ui.Modal, title="📝 أسئلة التقديم (لين 5)"):
    def __init__(self, slot: int, current: list):
        super().__init__()
        self.slot = slot
        self.inputs = []
        for i in range(5):
            ti = discord.ui.TextInput(
                label=f"السؤال {i + 1}" + ("" if i == 0 else " (اختياري)"),
                required=(i == 0), max_length=100,
                default=current[i] if i < len(current) else None,
            )
            self.inputs.append(ti)
            self.add_item(ti)

    async def on_submit(self, inter: discord.Interaction):
        qs = [t.value.strip() for t in self.inputs if t.value and t.value.strip()]
        db.execute("UPDATE app_types SET questions = ? WHERE guild_id = ? AND slot = ?",
                   ("\n".join(qs), inter.guild.id, self.slot))
        db.commit()
        await inter.response.send_message(
            embed=embed("✅ انحفظت الأسئلة", "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1))), ephemeral=True
        )


@bot.tree.command(name="اسئلة_تقديم", description="كتابة أسئلة التقديم (لين 5 أسئلة)")
async def application_questions(inter: discord.Interaction, الرقم: app_commands.Range[int, 1, 10]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    t = get_app_type(inter.guild.id, الرقم)
    if not t:
        return await inter.response.send_message(embed=err("سطّب التقديم أول بـ /تسطيب_تقديم"), ephemeral=True)
    await inter.response.send_modal(AppQuestionsModal(الرقم, [q for q in (t["questions"] or "").splitlines() if q]))


@bot.tree.command(name="حذف_تقديم", description="حذف تقديم")
async def delete_application(inter: discord.Interaction, الرقم: app_commands.Range[int, 1, 10]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    db.execute("DELETE FROM app_types WHERE guild_id = ? AND slot = ?", (inter.guild.id, الرقم))
    db.commit()
    await inter.response.send_message(embed=embed("🗑️ انحذف التقديم", f"رقم {الرقم}. أرسل اللوحة من جديد."), ephemeral=True)


def app_select_view(gid: int) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    opts = [discord.SelectOption(label=t["name"], value=str(t["slot"]), emoji=t["emoji"] or None) for t in get_app_types(gid)]
    v.add_item(discord.ui.Select(custom_id="app:open", placeholder="- اختر التقديم .", options=opts))
    return v


@bot.tree.command(name="ارسال_التقديمات", description="إرسال لوحة التقديمات في روم")
async def send_app_panel(inter: discord.Interaction, الروم: discord.TextChannel, الوصف: str = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    types_ = get_app_types(inter.guild.id)
    if not types_:
        return await inter.response.send_message(embed=err("ما فيه تقديمات. سطّب بـ /تسطيب_تقديم"), ephemeral=True)
    lines = "\n".join(f"{t['emoji'] or '📝'} - {t['name']}" for t in types_)
    e = embed("📝 - التقديمات", (الوصف or f"- مرحبا بك في قسم التقديمات الخاص بـ **{config.SERVER_NAME}** .\n\n"
                                          "اختر التقديم من القائمة وجاوب على الأسئلة .") + f"\n\n{lines}")
    try:
        await الروم.send(embed=e, view=app_select_view(inter.guild.id))
    except discord.Forbidden:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    except discord.HTTPException:
        return await inter.response.send_message(embed=err("فيه ايموجي غلط في أحد التقديمات."), ephemeral=True)
    await inter.response.send_message(embed=embed("✅ انرسلت لوحة التقديمات", الروم.mention), ephemeral=True)


class ApplyModal(discord.ui.Modal):
    def __init__(self, t):
        super().__init__(title=f"📝 {t['name']}"[:45])
        self.t = t
        self.inputs = []
        for q in [q for q in (t["questions"] or "").splitlines() if q][:5]:
            ti = discord.ui.TextInput(
                label=q[:45], placeholder=q[:100] if len(q) > 45 else None,
                style=discord.TextStyle.paragraph, max_length=1000,
            )
            self.inputs.append((q, ti))
            self.add_item(ti)

    async def on_submit(self, inter: discord.Interaction):
        t = self.t
        answers = [(q, ti.value) for q, ti in self.inputs]
        cur = db.execute(
            "INSERT INTO app_submissions (guild_id, slot, user_id, answers, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (inter.guild.id, t["slot"], inter.user.id, json.dumps(answers, ensure_ascii=False), now().isoformat()),
        )
        db.commit()
        sid = cur.lastrowid
        ch = inter.guild.get_channel(t["review_ch"])
        e = discord.Embed(title=f"📝 تقديم جديد - {t['name']}", color=0xC9A227, timestamp=now())
        e.set_author(name=str(inter.user), icon_url=inter.user.display_avatar.url)
        e.set_thumbnail(url=inter.user.display_avatar.url)
        e.add_field(name="المقدّم", value=f"{inter.user.mention} (`{inter.user.id}`)", inline=False)
        for q, a in answers:
            e.add_field(name=q[:256], value=(a or "-")[:1024], inline=False)
        e.set_footer(text=f"{config.SERVER_NAME} | رقم التقديم #{sid}")
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(label="قبول", emoji="✅", style=discord.ButtonStyle.success, custom_id=f"app:acc:{sid}"))
        v.add_item(discord.ui.Button(label="رفض", emoji="❌", style=discord.ButtonStyle.danger, custom_id=f"app:rej:{sid}"))
        if not ch:
            return await inter.response.send_message(embed=err("روم المراجعة انحذف. كلّم الإدارة."), ephemeral=True)
        try:
            await ch.send(embed=e, view=v)
        except discord.HTTPException:
            return await inter.response.send_message(embed=err("ما قدرت أرسل تقديمك. كلّم الإدارة."), ephemeral=True)
        await inter.response.send_message(embed=embed("✅ انرسل تقديمك", "انتظر رد الإدارة، وبيوصلك الرد في الخاص ."), ephemeral=True)


class RejectReasonModal(discord.ui.Modal, title="❌ سبب الرفض"):
    reason = discord.ui.TextInput(label="السبب (اختياري)", required=False, max_length=300, style=discord.TextStyle.paragraph)

    def __init__(self, sid: int, message: discord.Message):
        super().__init__()
        self.sid = sid
        self.message = message

    async def on_submit(self, inter: discord.Interaction):
        await finish_application(inter, self.sid, False, self.reason.value, self.message)


def can_review(member: discord.Member, t) -> bool:
    if is_staff_member(member):
        return True
    return bool(t and t["reviewer_role"] and any(r.id == t["reviewer_role"] for r in member.roles))


async def finish_application(inter: discord.Interaction, sid: int, accepted: bool, reason: str, message):
    s = db.execute("SELECT * FROM app_submissions WHERE id = ?", (sid,)).fetchone()
    if not s or s["status"] != "pending":
        return await inter.response.send_message(embed=err("هذا التقديم انرد عليه من قبل."), ephemeral=True)
    t = get_app_type(s["guild_id"], s["slot"])
    member = inter.guild.get_member(s["user_id"])
    given = []
    if accepted and member and t:
        roles = [inter.guild.get_role(r) for r in (t["role1"], t["role2"]) if r]
        roles = [r for r in roles if r]
        try:
            if roles:
                await member.add_roles(*roles, reason=f"قبول تقديم بواسطة {inter.user}")
            given = roles
        except discord.Forbidden:
            return await inter.response.send_message(embed=err("ما أقدر أعطي الرتب. خل رتبة البوت فوقها."), ephemeral=True)
    db.execute("UPDATE app_submissions SET status = ? WHERE id = ?", ("accepted" if accepted else "rejected", sid))
    db.commit()
    name = t["name"] if t else "التقديم"
    if member:
        try:
            if accepted:
                await member.send(embed=embed(
                    "✅ - تم قبولك",
                    f"**- عزيزي {member.mention} .**\n\n🎉 - تم قبولك في **{name}** في **{config.SERVER_NAME}** .\n"
                    + (f"الرتب : {' '.join(r.name for r in given)}\n" if given else "") + "\n**( نتمنى لك التوفيق )**",
                ))
            else:
                await member.send(embed=embed(
                    "❌ - تم رفض تقديمك",
                    f"**- عزيزي {member.mention} .**\n\nنعتذر , تم رفض تقديمك في **{name}** ."
                    + (f"\n\n**السبب :** {reason}" if reason else "") + "\n\n**( نتمنى لك التوفيق المرة الجاية )**",
                    0xB3261E,
                ))
        except discord.HTTPException:
            pass
    result = (f"✅ **مقبول** بواسطة {inter.user.mention}" if accepted else
              f"❌ **مرفوض** بواسطة {inter.user.mention}" + (f"\nالسبب: {reason}" if reason else ""))
    try:
        e = message.embeds[0] if message.embeds else embed("📝 تقديم")
        e.color = 0x006C35 if accepted else 0xB3261E
        e.add_field(name="النتيجة", value=result, inline=False)
        await message.edit(embed=e, view=None)
    except discord.HTTPException:
        pass
    if inter.response.is_done():
        await inter.followup.send(embed=embed("تم", result), ephemeral=True)
    else:
        await inter.response.send_message(embed=embed("تم", result), ephemeral=True)
    await log(f"{inter.user.mention} {'قبل' if accepted else 'رفض'} تقديم <@{s['user_id']}> ({name})", inter.guild)


async def handle_app_interaction(inter: discord.Interaction, cid: str):
    if cid == "app:open":
        slot = int((inter.data.get("values") or ["0"])[0])
        t = get_app_type(inter.guild.id, slot)
        try:
            await inter.message.edit(view=app_select_view(inter.guild.id))
        except discord.HTTPException:
            pass
        if not t:
            return await inter.response.send_message(embed=err("التقديم هذا انحذف."), ephemeral=True)
        if not (t["questions"] or "").strip():
            return await inter.response.send_message(embed=err("التقديم هذا ما له أسئلة للحين."), ephemeral=True)
        pending = db.execute(
            "SELECT 1 FROM app_submissions WHERE guild_id = ? AND slot = ? AND user_id = ? AND status = 'pending'",
            (inter.guild.id, slot, inter.user.id),
        ).fetchone()
        if pending:
            return await inter.response.send_message(embed=err("عندك تقديم للحين ينتظر الرد."), ephemeral=True)
        ids = {r.id for r in inter.user.roles}
        if t["role1"] in ids and (not t["role2"] or t["role2"] in ids):
            return await inter.response.send_message(embed=err("أنت مقبول في هذا من قبل."), ephemeral=True)
        return await inter.response.send_modal(ApplyModal(t))

    _, action, sid = cid.split(":")
    s = db.execute("SELECT * FROM app_submissions WHERE id = ?", (int(sid),)).fetchone()
    t = get_app_type(s["guild_id"], s["slot"]) if s else None
    if not can_review(inter.user, t):
        return await inter.response.send_message(embed=err("المراجعة للإدارة بس."), ephemeral=True)
    if action == "acc":
        await finish_application(inter, int(sid), True, "", inter.message)
    else:
        await inter.response.send_modal(RejectReasonModal(int(sid), inter.message))


# ============================================================
# التوظيف والاستقالة
# ============================================================
SECTORS = {"military": "عسكري 👮", "crime": "مجرم 🦹", "justice": "عدل ⚖️", "civil": "مدني 👷"}
SECTOR_ROLE_KEY = {"military": "role_police", "crime": "role_crime", "justice": "role_justice"}


def get_jobs(gid: int):
    return db.execute("SELECT * FROM job_roles WHERE guild_id = ? ORDER BY name", (gid,)).fetchall()


@bot.tree.command(name="تسطيب_وظيفة", description="إضافة وظيفة للتوظيف بأمر -اسم_الوظيفة")
@app_commands.describe(
    الاسم="اسم الوظيفة، مثل: عصابة الذيب (يكتبها الإداري بعد -)",
    الرتبة="رتبة الوظيفة",
    القطاع="القطاع (عشان الاستقالة تشيلها)",
)
@app_commands.choices(القطاع=[app_commands.Choice(name=v, value=k) for k, v in SECTORS.items()])
async def setup_job(inter: discord.Interaction, الاسم: app_commands.Range[str, 1, 50], الرتبة: discord.Role,
                    القطاع: app_commands.Choice[str]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    name = الاسم.strip().lstrip("-").strip()
    if name in ("قيم", "تفعيل", "تفتيش", "استقالة", "استقاله"):
        return await inter.response.send_message(embed=err("هالاسم محجوز لأمر ثاني."), ephemeral=True)
    if len(get_jobs(inter.guild.id)) >= 50 and not db.execute(
            "SELECT 1 FROM job_roles WHERE guild_id = ? AND name = ?", (inter.guild.id, name)).fetchone():
        return await inter.response.send_message(embed=err("وصلت الحد: 50 وظيفة."), ephemeral=True)
    db.execute(
        "INSERT INTO job_roles (guild_id, name, role_id, sector) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, name) DO UPDATE SET role_id = excluded.role_id, sector = excluded.sector",
        (inter.guild.id, name, الرتبة.id, القطاع.value),
    )
    db.commit()
    await inter.response.send_message(embed=embed(
        "💼 تم تسطيب الوظيفة",
        f"**{name}** ← {الرتبة.mention} ({القطاع.name})\n\nالتوظيف: `-{name} @الشخص`",
    ), ephemeral=True)


@bot.tree.command(name="حذف_وظيفة", description="حذف وظيفة من التوظيف")
async def delete_job(inter: discord.Interaction, الاسم: str):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    cur = db.execute("DELETE FROM job_roles WHERE guild_id = ? AND name = ?", (inter.guild.id, الاسم.strip()))
    db.commit()
    if not cur.rowcount:
        return await inter.response.send_message(embed=err("ما لقيت هالوظيفة."), ephemeral=True)
    await inter.response.send_message(embed=embed("🗑️ انحذفت الوظيفة", الاسم), ephemeral=True)


@delete_job.autocomplete("الاسم")
async def job_name_autocomplete(inter: discord.Interaction, current: str):
    return [app_commands.Choice(name=j["name"], value=j["name"]) for j in get_jobs(inter.guild.id) if current in j["name"]][:25]


@bot.tree.command(name="قائمة_الوظائف", description="عرض الوظائف المسطّبة للتوظيف")
async def list_jobs(inter: discord.Interaction):
    jobs = get_jobs(inter.guild.id)
    if not jobs:
        return await inter.response.send_message(embed=err("ما فيه وظائف. سطّب بـ /تسطيب_وظيفة"), ephemeral=True)
    by_sector = {}
    for j in jobs:
        by_sector.setdefault(j["sector"], []).append(f"• `-{j['name']}` ← <@&{j['role_id']}>")
    e = embed("💼 الوظائف")
    for k, lines in by_sector.items():
        e.add_field(name=SECTORS.get(k, k), value="\n".join(lines)[:1024], inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)


async def role_update_post(guild: discord.Guild, e: discord.Embed):
    ch = guild.get_channel(get_setting(guild.id, "ch_roles_update"))
    if ch:
        try:
            await ch.send(embed=e)
        except discord.HTTPException:
            pass


async def find_member_in_message(message: discord.Message, after: str):
    if message.mentions:
        return message.mentions[0]
    raw = after.strip().split()[0].strip("<@!>") if after.strip() else ""
    if raw.isdigit():
        m = message.guild.get_member(int(raw))
        if m is None:
            try:
                m = await message.guild.fetch_member(int(raw))
            except discord.HTTPException:
                m = None
        return m
    return None


async def hire_command(message: discord.Message) -> bool:
    """يرجع True إذا الرسالة كانت أمر توظيف"""
    text = message.content.strip()[1:].strip()
    jobs = sorted(get_jobs(message.guild.id), key=lambda j: len(j["name"]), reverse=True)
    job = next((j for j in jobs if text == j["name"] or text.startswith(j["name"] + " ")), None)
    if not job:
        return False
    if not is_staff_member(message.author):
        await message.reply(embed=err("التوظيف للإدارة بس."))
        return True
    member = await find_member_in_message(message, text[len(job["name"]):])
    if member is None or member.bot:
        await message.reply(embed=err(f"الاستخدام: `-{job['name']} @الشخص`"))
        return True
    roles = [message.guild.get_role(job["role_id"])]
    sector_key = SECTOR_ROLE_KEY.get(job["sector"])
    if sector_key and get_setting(message.guild.id, sector_key):
        roles.append(message.guild.get_role(get_setting(message.guild.id, sector_key)))
    roles = [r for r in roles if r and r not in member.roles]
    try:
        if roles:
            await member.add_roles(*roles, reason=f"توظيف بواسطة {message.author}")
    except discord.Forbidden:
        await message.reply(embed=err("ما أقدر أعطي الرتبة. خل رتبة البوت فوقها."))
        return True
    add_points(message.guild.id, message.author.id, "admin", "hire", pts_value(message.guild.id, "pts_hire"))
    e = embed(
        "💼 - تحديث أدوار | توظيف",
        f"**العضو :** {member.mention}\n**الوظيفة :** {job['name']} <@&{job['role_id']}>\n"
        f"**القطاع :** {SECTORS.get(job['sector'], '-')}\n**بواسطة :** {message.author.mention}",
    )
    await message.reply(embed=e)
    await role_update_post(message.guild, e)
    try:
        await member.send(embed=embed("💼 - تم توظيفك", f"مبروك ! تم توظيفك في **{job['name']}** في **{config.SERVER_NAME}** 🎉"))
    except discord.HTTPException:
        pass
    await log(f"{message.author.mention} وظّف {member.mention} في {job['name']}", message.guild)
    return True


class ResignView(discord.ui.View):
    def __init__(self, admin_id: int, member: discord.Member):
        super().__init__(timeout=120)
        self.admin_id = admin_id
        self.member = member
        sel = discord.ui.Select(placeholder="- اختر القطاع .", options=[
            discord.SelectOption(label="عسكري", value="military", emoji="👮"),
            discord.SelectOption(label="مجرم", value="crime", emoji="🦹"),
            discord.SelectOption(label="عدل", value="justice", emoji="⚖️"),
            discord.SelectOption(label="مدني", value="civil", emoji="👷"),
        ])
        sel.callback = self.picked
        self.sel = sel
        self.add_item(sel)

    async def picked(self, inter: discord.Interaction):
        if inter.user.id != self.admin_id:
            return await inter.response.send_message(embed=err("مو لك."), ephemeral=True)
        sector = self.sel.values[0]
        guild = inter.guild
        role_ids = {j["role_id"] for j in get_jobs(guild.id) if j["sector"] == sector}
        key = SECTOR_ROLE_KEY.get(sector)
        if key and get_setting(guild.id, key):
            role_ids.add(get_setting(guild.id, key))
        if sector == "military" and get_setting(guild.id, "role_swat"):
            role_ids.add(get_setting(guild.id, "role_swat"))
        remove = [r for r in self.member.roles if r.id in role_ids]
        if not remove:
            return await inter.response.edit_message(embed=err(f"{self.member.mention} ما عنده رتب في هالقطاع."), view=None)
        try:
            await self.member.remove_roles(*remove, reason=f"استقالة بواسطة {inter.user}")
        except discord.Forbidden:
            return await inter.response.edit_message(embed=err("ما أقدر أشيل الرتب. خل رتبة البوت فوقها."), view=None)
        # لو كانت وظيفته في البوت من هالقطاع، نرجعه عاطل
        db.execute("UPDATE players SET job = ? WHERE user_id = ?", (config.DEFAULT_JOB, self.member.id))
        db.commit()
        add_points(guild.id, inter.user.id, "admin", "resign", pts_value(guild.id, "pts_resign"))
        e = embed(
            "📤 - تحديث أدوار | استقالة",
            f"**العضو :** {self.member.mention}\n**القطاع :** {SECTORS[sector]}\n"
            f"**الرتب اللي انشالت :** {' '.join(r.mention for r in remove)}\n**بواسطة :** {inter.user.mention}",
            0xB3261E,
        )
        await inter.response.edit_message(embed=e, view=None)
        await role_update_post(guild, e)
        try:
            await self.member.send(embed=embed("📤 - تمت استقالتك", f"تمت استقالتك من القطاع **{SECTORS[sector]}** في **{config.SERVER_NAME}** .", 0xB3261E))
        except discord.HTTPException:
            pass
        await log(f"{inter.user.mention} سوّى استقالة لـ {self.member.mention} ({SECTORS[sector]})", guild)
        self.stop()


async def resign_command(message: discord.Message):
    if not is_staff_member(message.author):
        return await message.reply(embed=err("الاستقالة للإدارة بس."))
    after = message.content.strip().split(maxsplit=1)
    member = await find_member_in_message(message, after[1] if len(after) > 1 else "")
    if member is None or member.bot:
        return await message.reply(embed=err("الاستخدام: `-استقالة @الشخص`"))
    await message.reply(embed=embed("📤 استقالة", f"العضو: {member.mention}\nاختر القطاع اللي بيستقيل منه :"),
                        view=ResignView(message.author.id, member))


# ============================================================
# اليونتات: LSPD (D-30 وفوق) و SWAT (S-20 وفوق)
# ============================================================
UNITS = {
    "lspd": {"prefix": "D", "start": 30, "role": "role_police", "label": "LSPD"},
    "swat": {"prefix": "S", "start": 20, "role": "role_swat", "label": "SWAT"},
}
UNIT_TAG = re.compile(r"^\s*[DS]-\d+\s*\|\s*")


def units_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="LSPD", emoji="🔵", style=discord.ButtonStyle.primary, custom_id="unit:lspd"))
    v.add_item(discord.ui.Button(label="SWAT", emoji="⚫", style=discord.ButtonStyle.secondary, custom_id="unit:swat"))
    return v


def unit_nick(member: discord.Member, code: str) -> str:
    base = UNIT_TAG.sub("", member.display_name).strip() or member.name
    return f"{code} | {base}"[:32]


async def handle_unit(inter: discord.Interaction, kind: str):
    u = UNITS.get(kind)
    if not u:
        return
    gid = inter.guild.id
    role_id = get_setting(gid, u["role"])
    if not role_id:
        return await inter.response.send_message(
            embed=err(f"رتبة {'الشرطة' if kind == 'lspd' else 'السوات'} ما تحددت. خل الإدارة تستخدم /تسطيب_رتب"), ephemeral=True
        )
    if not (inter.user.guild_permissions.administrator or any(r.id == role_id for r in inter.user.roles)):
        return await inter.response.send_message(embed=err(f"هذا الزر لرتبة <@&{role_id}> بس."), ephemeral=True)

    row = db.execute("SELECT kind, number FROM units WHERE guild_id = ? AND user_id = ?",
                      (gid, inter.user.id)).fetchone()
    if row:
        have = UNITS[row["kind"]]
        return await inter.response.send_message(embed=err(
            f"عندك يونت من قبل : **`{have['prefix']}-{row['number']}`** ( {have['label']} )\n\n"
            "ما تقدر تاخذ يونت ثاني. إذا تبي تغيّره، كلّم الإدارة ."
        ), ephemeral=True)
    new = True
    if new:
        last = db.execute("SELECT MAX(number) AS m FROM units WHERE guild_id = ? AND kind = ?", (gid, kind)).fetchone()["m"]
        number = max(u["start"], (last or 0) + 1)
        db.execute("INSERT INTO units (guild_id, user_id, kind, number) VALUES (?, ?, ?, ?)", (gid, inter.user.id, kind, number))
        db.commit()
    else:
        number = row["number"]
    code = f"{u['prefix']}-{number}"
    nick = unit_nick(inter.user, code)
    changed = True
    try:
        if inter.user.display_name != nick:
            await inter.user.edit(nick=nick, reason=f"يونت {u['label']}")
    except discord.HTTPException:
        changed = False
    text = (f"{'✅ تم إعطاؤك يونت' if new else 'ℹ️ يونتك من قبل'} **{u['label']}** : **`{code}`**\n\n"
            + (f"اسمك صار: **{nick}**" if changed else
               "⚠️ ما قدرت أغيّر اسمك. خل رتبة البوت فوق رتبتك، وعطه صلاحية Manage Nicknames .\n"
               "(ولو أنت صاحب السيرفر، ديسكورد ما يسمح للبوت يغيّر اسمك)"))
    await inter.response.send_message(embed=embed(f"🚓 يونت {u['label']}", text, 0x2B6CB0), ephemeral=True)
    if new:
        await log(f"{inter.user.mention} أخذ يونت {u['label']} `{code}`", inter.guild)


@bot.tree.command(name="حذف_يونت", description="حذف يونت عسكري (لصاحب صلاحية الأدمن)")
@app_commands.choices(النوع=[
    app_commands.Choice(name="LSPD", value="lspd"),
    app_commands.Choice(name="SWAT", value="swat"),
    app_commands.Choice(name="الاثنين", value="all"),
])
async def delete_unit(inter: discord.Interaction, العضو: discord.Member, النوع: app_commands.Choice[str]):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if النوع.value == "all":
        db.execute("DELETE FROM units WHERE guild_id = ? AND user_id = ?", (inter.guild.id, العضو.id))
    else:
        db.execute("DELETE FROM units WHERE guild_id = ? AND user_id = ? AND kind = ?", (inter.guild.id, العضو.id, النوع.value))
    db.commit()
    try:
        base = UNIT_TAG.sub("", العضو.display_name).strip()
        if base != العضو.display_name:
            await العضو.edit(nick=base or None)
    except discord.HTTPException:
        pass
    await inter.response.send_message(embed=embed("🗑️ انحذف اليونت", f"{العضو.mention} ({النوع.name})"), ephemeral=True)


# ============================================================
# البنك: حساب + آيبان + تحويل + قروض
# ============================================================
POLICE_RANKS = [
    "مستجد", "جندي", "جندي أول", "عريف", "وكيل رقيب", "رقيب", "رقيب أول", "رئيس رقباء",
    "ملازم", "ملازم أول", "نقيب", "رائد", "مقدم", "عقيد", "عميد", "لواء", "فريق", "فريق أول",
]


def is_owner(inter: discord.Interaction) -> bool:
    return inter.guild is not None and inter.user.id == inter.guild.owner_id


def get_account(uid: int):
    return db.execute("SELECT * FROM bank_accounts WHERE user_id = ?", (uid,)).fetchone()


def new_iban() -> str:
    while True:
        iban = "SA" + "".join(random.choices("0123456789", k=22))
        if not db.execute("SELECT 1 FROM bank_accounts WHERE iban = ?", (iban,)).fetchone():
            return iban


def fmt_iban(iban: str) -> str:
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def active_loan(uid: int):
    return db.execute("SELECT * FROM loans WHERE user_id = ? AND status IN ('pending', 'active') ORDER BY id DESC",
                      (uid,)).fetchone()


def bank_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    items = [
        ("إنشاء حساب", "🏦", discord.ButtonStyle.success, "bank:create", 0),
        ("حسابي البنكي", "💳", discord.ButtonStyle.primary, "bank:me", 0),
        ("الكاش", "💵", discord.ButtonStyle.primary, "bank:cash", 0),
        ("إيداع", "📥", discord.ButtonStyle.secondary, "bank:deposit", 1),
        ("سحب", "📤", discord.ButtonStyle.secondary, "bank:withdraw", 1),
        ("تحويل", "🔁", discord.ButtonStyle.secondary, "bank:transfer", 1),
        ("طلب قرض", "📝", discord.ButtonStyle.secondary, "bank:loan", 2),
        ("دفع قرض", "💸", discord.ButtonStyle.secondary, "bank:payloan", 2),
    ]
    for label, emoji, style, cid, row in items:
        v.add_item(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=cid, row=row))
    return v


def parse_amount(text: str):
    t = text.strip().replace(",", "").replace("٬", "")
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return int(t) if t.isdigit() and int(t) > 0 else None


class DepositModal(discord.ui.Modal, title="📥 إيداع"):
    amount = discord.ui.TextInput(label="المبلغ", placeholder="مثال: 5000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        p = get_player(inter.user.id)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        if p["cash"] < amt:
            return await inter.response.send_message(embed=err(f"كاشك ما يكفي. عندك {money(p['cash'])}"), ephemeral=True)
        db.execute("UPDATE players SET cash = cash - ?, bank = bank + ? WHERE user_id = ?", (amt, amt, inter.user.id))
        db.commit()
        p = get_player(inter.user.id)
        await inter.response.send_message(embed=embed("📥 تم الإيداع", f"أودعت **{money(amt)}**\nرصيدك الحين: **{money(p['bank'])}**"), ephemeral=True)


class WithdrawModal(discord.ui.Modal, title="📤 سحب"):
    amount = discord.ui.TextInput(label="المبلغ", placeholder="مثال: 5000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        p = get_player(inter.user.id)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        if p["bank"] < amt:
            return await inter.response.send_message(embed=err(f"رصيدك ما يكفي. عندك {money(p['bank'])}"), ephemeral=True)
        db.execute("UPDATE players SET bank = bank - ?, cash = cash + ? WHERE user_id = ?", (amt, amt, inter.user.id))
        db.commit()
        p = get_player(inter.user.id)
        await inter.response.send_message(embed=embed("📤 تم السحب", f"سحبت **{money(amt)}** كاش\nكاشك الحين: **{money(p['cash'])}**"), ephemeral=True)


class TransferModal(discord.ui.Modal, title="🔁 تحويل"):
    target = discord.ui.TextInput(label="رقم الآيبان أو ايدي العضو", placeholder="SA... أو 123456789012345678", max_length=40)
    amount = discord.ui.TextInput(label="المبلغ", placeholder="مثال: 5000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        raw = self.target.value.strip().replace(" ", "").upper().strip("<@!>")
        acc = None
        if raw.startswith("SA"):
            acc = db.execute("SELECT * FROM bank_accounts WHERE iban = ?", (raw,)).fetchone()
        elif raw.isdigit():
            acc = get_account(int(raw))
        if not acc:
            return await inter.response.send_message(embed=err("ما لقيت حساب بهالآيبان أو الايدي."), ephemeral=True)
        if acc["user_id"] == inter.user.id:
            return await inter.response.send_message(embed=err("ما تقدر تحول لنفسك."), ephemeral=True)
        p = get_player(inter.user.id)
        if p["bank"] < amt:
            return await inter.response.send_message(embed=err(f"رصيدك ما يكفي. عندك {money(p['bank'])}"), ephemeral=True)
        db.execute("UPDATE players SET bank = bank - ? WHERE user_id = ?", (amt, inter.user.id))
        db.execute("UPDATE players SET bank = bank + ? WHERE user_id = ?", (amt, acc["user_id"]))
        db.commit()
        await inter.response.send_message(embed=embed(
            "🔁 تم التحويل", f"حولت **{money(amt)}** إلى <@{acc['user_id']}>\nالآيبان: `{fmt_iban(acc['iban'])}`"), ephemeral=True)
        target = inter.guild.get_member(acc["user_id"])
        if target:
            try:
                await target.send(embed=embed("🏦 حوالة واردة", f"وصلتك حوالة **{money(amt)}** من {inter.user.mention}"))
            except discord.HTTPException:
                pass
        await log(f"{inter.user.mention} حوّل {money(amt)} إلى <@{acc['user_id']}>", inter.guild)


class LoanModal(discord.ui.Modal, title="📝 طلب قرض"):
    reason = discord.ui.TextInput(label="سبب القرض", style=discord.TextStyle.paragraph, max_length=300)
    amount = discord.ui.TextInput(label="كمية المبلغ", placeholder="مثال: 50000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        if active_loan(inter.user.id):
            return await inter.response.send_message(embed=err("عندك قرض أو طلب قرض من قبل."), ephemeral=True)
        ch = inter.guild.get_channel(get_setting(inter.guild.id, "ch_loans"))
        if not ch:
            return await inter.response.send_message(embed=err("روم القروض ما تحدد. كلّم الإدارة."), ephemeral=True)
        cur = db.execute(
            "INSERT INTO loans (guild_id, user_id, amount, remaining, reason, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (inter.guild.id, inter.user.id, amt, amt, self.reason.value, now().isoformat()),
        )
        db.commit()
        lid = cur.lastrowid
        acc = get_account(inter.user.id)
        e = embed("📝 طلب قرض جديد", color=0xC9A227)
        e.set_thumbnail(url=inter.user.display_avatar.url)
        e.add_field(name="العضو", value=f"{inter.user.mention} (`{inter.user.id}`)", inline=False)
        e.add_field(name="الآيبان", value=f"`{fmt_iban(acc['iban'])}`", inline=False)
        e.add_field(name="المبلغ", value=f"**{money(amt)}**")
        e.add_field(name="رصيده الحين", value=money(get_player(inter.user.id)["bank"]))
        e.add_field(name="السبب", value=self.reason.value, inline=False)
        e.set_footer(text=f"{config.SERVER_NAME} | قرض #{lid}")
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(label="قبول", emoji="✅", style=discord.ButtonStyle.success, custom_id=f"loan:acc:{lid}"))
        v.add_item(discord.ui.Button(label="رفض", emoji="❌", style=discord.ButtonStyle.danger, custom_id=f"loan:rej:{lid}"))
        try:
            owner = inter.guild.owner
            await ch.send(content=owner.mention if owner else None, embed=e, view=v)
        except discord.HTTPException:
            return await inter.response.send_message(embed=err("ما قدرت أرسل الطلب. كلّم الإدارة."), ephemeral=True)
        await inter.response.send_message(embed=embed("✅ انرسل طلب القرض", "بيوصلك الرد في الخاص ."), ephemeral=True)


class PayLoanModal(discord.ui.Modal, title="💸 دفع قرض"):
    amount = discord.ui.TextInput(label="المبلغ اللي تبي تدفعه", placeholder="مثال: 10000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        loan = db.execute("SELECT * FROM loans WHERE user_id = ? AND status = 'active'", (inter.user.id,)).fetchone()
        if not loan:
            return await inter.response.send_message(embed=err("ما عليك قرض."), ephemeral=True)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        amt = min(amt, loan["remaining"])
        p = get_player(inter.user.id)
        if p["bank"] < amt:
            return await inter.response.send_message(embed=err(f"رصيدك ما يكفي. عندك {money(p['bank'])}"), ephemeral=True)
        left = loan["remaining"] - amt
        db.execute("UPDATE players SET bank = bank - ? WHERE user_id = ?", (amt, inter.user.id))
        db.execute("UPDATE loans SET remaining = ?, status = ? WHERE id = ?", (left, "paid" if left == 0 else "active", loan["id"]))
        db.commit()
        text = f"دفعت **{money(amt)}**\n" + ("🎉 **سددت القرض كامل !**" if left == 0 else f"الباقي عليك: **{money(left)}**")
        await inter.response.send_message(embed=embed("💸 تم الدفع", text), ephemeral=True)
        await log(f"{inter.user.mention} دفع {money(amt)} من قرضه (الباقي {money(left)})", inter.guild)


async def handle_bank(inter: discord.Interaction, action: str):
    uid = inter.user.id
    p = get_player(uid)
    if not p:
        return await inter.response.send_message(embed=err("ما عندك هوية. سوّ هوية أول من روم إنشاء الهوية."), ephemeral=True)
    acc = get_account(uid)
    if action == "create":
        if acc:
            return await inter.response.send_message(embed=err(f"عندك حساب من قبل.\nالآيبان: `{fmt_iban(acc['iban'])}`"), ephemeral=True)
        iban = new_iban()
        db.execute("INSERT INTO bank_accounts (user_id, iban, created_at) VALUES (?, ?, ?)", (uid, iban, now().isoformat()))
        db.commit()
        await log(f"{inter.user.mention} فتح حساب بنكي `{iban}`", inter.guild)
        return await inter.response.send_message(embed=embed(
            "🏦 تم فتح حسابك البنكي",
            f"**الاسم :** {p['name']}\n**رقم الآيبان :** `{fmt_iban(iban)}`\n**الرصيد :** {money(p['bank'])}\n\n"
            "احفظ الآيبان، الناس يحولون لك فيه .",
        ), ephemeral=True)
    if not acc:
        return await inter.response.send_message(embed=err("ما عندك حساب بنكي. اضغط **إنشاء حساب** أول."), ephemeral=True)
    if action == "me":
        loan = active_loan(uid)
        e = embed("💳 حسابي البنكي")
        e.set_thumbnail(url=inter.user.display_avatar.url)
        e.add_field(name="الاسم", value=p["name"])
        e.add_field(name="رقم الآيبان", value=f"`{fmt_iban(acc['iban'])}`", inline=False)
        e.add_field(name="🏦 الرصيد", value=f"**{money(p['bank'])}**")
        e.add_field(name="💵 الكاش", value=money(p["cash"]))
        if loan:
            e.add_field(name="📝 القرض", value=(f"عليك **{money(loan['remaining'])}** من {money(loan['amount'])}"
                                                if loan["status"] == "active" else f"طلب {money(loan['amount'])} ينتظر الرد"), inline=False)
        return await inter.response.send_message(embed=e, ephemeral=True)
    if action == "cash":
        return await inter.response.send_message(embed=embed("💵 الكاش", f"الكاش اللي معك: **{money(p['cash'])}**"), ephemeral=True)
    if action == "deposit":
        return await inter.response.send_modal(DepositModal())
    if action == "withdraw":
        return await inter.response.send_modal(WithdrawModal())
    if action == "transfer":
        return await inter.response.send_modal(TransferModal())
    if action == "loan":
        if active_loan(uid):
            return await inter.response.send_message(embed=err("عندك قرض أو طلب قرض من قبل. سدده أول."), ephemeral=True)
        return await inter.response.send_modal(LoanModal())
    if action == "payloan":
        if not db.execute("SELECT 1 FROM loans WHERE user_id = ? AND status = 'active'", (uid,)).fetchone():
            return await inter.response.send_message(embed=err("ما عليك قرض."), ephemeral=True)
        return await inter.response.send_modal(PayLoanModal())


async def handle_loan_decision(inter: discord.Interaction, cid: str):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("قبول القروض لصاحب السيرفر بس."), ephemeral=True)
    _, action, lid = cid.split(":")
    loan = db.execute("SELECT * FROM loans WHERE id = ?", (int(lid),)).fetchone()
    if not loan or loan["status"] != "pending":
        return await inter.response.send_message(embed=err("هذا الطلب انرد عليه من قبل."), ephemeral=True)
    accepted = action == "acc"
    if accepted:
        db.execute("UPDATE loans SET status = 'active' WHERE id = ?", (loan["id"],))
        db.execute("UPDATE players SET bank = bank + ? WHERE user_id = ?", (loan["amount"], loan["user_id"]))
    else:
        db.execute("UPDATE loans SET status = 'rejected' WHERE id = ?", (loan["id"],))
    db.commit()
    try:
        e = inter.message.embeds[0]
        e.color = 0x006C35 if accepted else 0xB3261E
        e.add_field(name="النتيجة", value=("✅ **مقبول**" if accepted else "❌ **مرفوض**") + f" بواسطة {inter.user.mention}", inline=False)
        await inter.response.edit_message(embed=e, view=None)
    except (discord.HTTPException, IndexError):
        await inter.response.send_message(embed=embed("تم"), ephemeral=True)
    member = inter.guild.get_member(loan["user_id"])
    if member:
        try:
            await member.send(embed=embed(
                "✅ تم قبول قرضك" if accepted else "❌ تم رفض قرضك",
                (f"انضاف لحسابك **{money(loan['amount'])}**\nسدده من البنك بزر **دفع قرض** ." if accepted
                 else f"تم رفض طلب القرض ({money(loan['amount'])})."),
                0x006C35 if accepted else 0xB3261E,
            ))
        except discord.HTTPException:
            pass
    await log(f"{inter.user.mention} {'قبل' if accepted else 'رفض'} قرض <@{loan['user_id']}> ({money(loan['amount'])})", inter.guild)


# ============================================================
# رتب الشرطة والرواتب (الصرف لصاحب السيرفر بس)
# ============================================================
@bot.tree.command(name="تسطيب_رتب_الشرطة", description="تحديد رتب الشرطة من مستجد إلى فريق أول")
@app_commands.describe(
    مستجد="رتبة مستجد",
    جندي="رتبة جندي",
    جندي_أول="رتبة جندي أول",
    عريف="رتبة عريف",
    وكيل_رقيب="رتبة وكيل رقيب",
    رقيب="رتبة رقيب",
    رقيب_أول="رتبة رقيب أول",
    رئيس_رقباء="رتبة رئيس رقباء",
    ملازم="رتبة ملازم",
    ملازم_أول="رتبة ملازم أول",
    نقيب="رتبة نقيب",
    رائد="رتبة رائد",
    مقدم="رتبة مقدم",
    عقيد="رتبة عقيد",
    عميد="رتبة عميد",
    لواء="رتبة لواء",
    فريق="رتبة فريق",
    فريق_أول="رتبة فريق أول",
)
async def setup_police_ranks(
    inter: discord.Interaction,
    مستجد: discord.Role = None,
    جندي: discord.Role = None,
    جندي_أول: discord.Role = None,
    عريف: discord.Role = None,
    وكيل_رقيب: discord.Role = None,
    رقيب: discord.Role = None,
    رقيب_أول: discord.Role = None,
    رئيس_رقباء: discord.Role = None,
    ملازم: discord.Role = None,
    ملازم_أول: discord.Role = None,
    نقيب: discord.Role = None,
    رائد: discord.Role = None,
    مقدم: discord.Role = None,
    عقيد: discord.Role = None,
    عميد: discord.Role = None,
    لواء: discord.Role = None,
    فريق: discord.Role = None,
    فريق_أول: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    given = [مستجد, جندي, جندي_أول, عريف, وكيل_رقيب, رقيب, رقيب_أول, رئيس_رقباء, ملازم, ملازم_أول, نقيب, رائد, مقدم, عقيد, عميد, لواء, فريق, فريق_أول]
    for i, role in enumerate(given):
        if role:
            set_setting(gid, f"prank_{i}", role.id)
    lines = []
    for i, name in enumerate(POLICE_RANKS):
        rid = get_setting(gid, f"prank_{i}")
        sal = get_setting(gid, f"psal_{i}")
        lines.append(f"• {name}: {('<@&%d>' % rid) if rid else 'ما تحددت'}" + (f" ← {money(sal)}" if sal else ""))
    await inter.response.send_message(embed=embed("👮 رتب الشرطة", "\n".join(lines)), ephemeral=True)


@bot.tree.command(name="تسطيب_الرواتب", description="تحديد راتب كل رتبة شرطة وراتب العدل")
@app_commands.describe(الرتبة="الرتبة", الراتب="الراتب")
@app_commands.choices(الرتبة=[app_commands.Choice(name=n, value=str(i)) for i, n in enumerate(POLICE_RANKS)]
                      + [app_commands.Choice(name="العدل", value="justice")])
async def setup_salaries(inter: discord.Interaction, الرتبة: app_commands.Choice[str], الراتب: app_commands.Range[int, 0, 100_000_000]):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("الرواتب لصاحب السيرفر بس."), ephemeral=True)
    key = "sal_justice" if الرتبة.value == "justice" else f"psal_{الرتبة.value}"
    set_setting(inter.guild.id, key, الراتب)
    gid = inter.guild.id
    lines = [f"• {n}: {money(get_setting(gid, f'psal_{i}'))}" for i, n in enumerate(POLICE_RANKS) if get_setting(gid, f"psal_{i}")]
    if get_setting(gid, "sal_justice"):
        lines.append(f"• العدل: {money(get_setting(gid, 'sal_justice'))}")
    await inter.response.send_message(embed=embed("💰 الرواتب", "\n".join(lines) or "ما فيه رواتب"), ephemeral=True)


def member_salary(member: discord.Member):
    """يرجع (اسم الرتبة، الراتب) لأعلى رتبة معه"""
    gid = member.guild.id
    ids = {r.id for r in member.roles}
    for i in range(len(POLICE_RANKS) - 1, -1, -1):
        rid = get_setting(gid, f"prank_{i}")
        if rid and rid in ids and get_setting(gid, f"psal_{i}"):
            return POLICE_RANKS[i], get_setting(gid, f"psal_{i}")
    j = get_setting(gid, "role_justice")
    if j and j in ids and get_setting(gid, "sal_justice"):
        return "العدل", get_setting(gid, "sal_justice")
    return None, 0


@bot.tree.command(name="صرف_الرواتب", description="صرف رواتب العسكر والعدل (لصاحب السيرفر بس)")
async def pay_salaries(inter: discord.Interaction):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("صرف الرواتب لصاحب السيرفر بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    guild = inter.guild
    if not guild.chunked:
        await guild.chunk()
    paid, skipped, total = [], [], 0
    for m in guild.members:
        if m.bot:
            continue
        rank, sal = member_salary(m)
        if not sal:
            continue
        if not get_player(m.id):
            skipped.append(m.mention)
            continue
        db.execute("UPDATE players SET bank = bank + ? WHERE user_id = ?", (sal, m.id))
        paid.append((m, rank, sal))
        total += sal
    db.commit()
    for m, rank, sal in paid:
        try:
            await m.send(embed=embed("💰 نزل الراتب", f"نزل راتبك كـ **{rank}** : **{money(sal)}** في حسابك البنكي 🏦"))
        except discord.HTTPException:
            pass
        await asyncio.sleep(0.5)
    lines = [f"• {m.mention} ({rank}) : {money(sal)}" for m, rank, sal in paid]
    text = (f"**انصرف لـ {len(paid)} عضو بمجموع {money(total)}**\n\n" + "\n".join(lines))[:3800]
    if skipped:
        text += f"\n\n⚠️ ما انصرف لهم لأن ما عندهم هوية: {' '.join(skipped)}"[:190]
    await inter.followup.send(embed=embed("💰 تم صرف الرواتب", text or "ما فيه أحد له راتب."), ephemeral=True)
    await log(f"{inter.user.mention} صرف الرواتب لـ {len(paid)} عضو ({money(total)})", guild)


@bot.event
async def on_interaction(inter: discord.Interaction):
    if inter.type != discord.InteractionType.component or not inter.guild:
        return
    cid = (inter.data or {}).get("custom_id", "")
    if cid == "ticket:open":
        values = inter.data.get("values") or []
        if values:
            await open_ticket(inter, int(values[0]))
        try:  # نرجّع المنيو فاضي عشان يقدر يختار مرة ثانية
            await inter.message.edit(view=ticket_select(inter.guild.id))
        except discord.HTTPException:
            pass
    elif cid.startswith("ticket:btn:"):
        await open_ticket(inter, int(cid.split(":")[2]))
    elif cid.startswith("ticket:"):
        await handle_ticket_button(inter, cid.split(":", 1)[1])
    elif cid.startswith("quiz:start"):
        await quiz_start(inter, cid)
    elif cid.startswith("quiz:ans:"):
        await quiz_answer(inter, cid)
    elif cid.startswith("pts:") or cid.startswith("mdt:"):
        await handle_points_interaction(inter, cid)
    elif cid.startswith("bank:"):
        await handle_bank(inter, cid.split(":", 1)[1])
    elif cid.startswith("loan:"):
        await handle_loan_decision(inter, cid)
    elif cid.startswith("unit:"):
        await handle_unit(inter, cid.split(":", 1)[1])
    elif cid.startswith("app:"):
        await handle_app_interaction(inter, cid)


# ============================================================
# سيرفر صغير عشان Render (Web Service) يلقى port مفتوح
# ============================================================
def keep_alive():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Bot is running".encode())

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    port = int(os.getenv("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), Handler)
    except OSError:
        # في الاستضافات اللي ما تحتاج port (مثل PebbleHost) نكمّل عادي
        print("ℹ️ ما فتحت port، ما يحتاج في هالاستضافة")
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"🌐 السيرفر فاتح على port {port}")


if __name__ == "__main__":
    import time
    keep_alive()
    if not TOKEN:
        raise SystemExit("❌ حط توكن البوت في Environment في Render باسم DISCORD_TOKEN")
    print(f"🔑 التوكن موجود ({len(TOKEN)} حرف). جاري تسجيل الدخول لديسكورد...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ التوكن غلط! خذ توكن جديد من موقع المطورين وحطه في DISCORD_TOKEN")
        time.sleep(60)
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        print("❌ لازم تفعّل Message Content Intent و Server Members Intent في موقع مطورين ديسكورد (قسم Bot)")
        time.sleep(60)
        sys.exit(1)
    except discord.HTTPException as e:
        if e.status == 429:
            # ديسكورد حاظر الـ IP مؤقتاً. ننتظر بدل ما نطيح ونعيد على طول ونطوّل الحظر
            print("⏳ ديسكورد حاظر الـ IP مؤقتاً (429). بنستنى 15 دقيقة وبعدها نعيد المحاولة...")
            time.sleep(15 * 60)
            sys.exit(1)  # Render يعيد تشغيل البوت
        raise
