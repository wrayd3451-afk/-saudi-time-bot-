# -*- coding: utf-8 -*-
"""
بوت نظام VRP لسيرفرات الرول بلاي على دسكورد
هوية - بنك - وظائف ورواتب - مخالفات - سجل جنائي - متجر وشنطة
"""
import asyncio
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import subprocess
import sys
import types

# لو المكتبة مو مثبتة، يثبتها البوت لحاله
try:
    import discord
    from discord import app_commands
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py>=2.3"])
    import discord
    from discord import app_commands

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
    SALARY_COOLDOWN_HOURS=SALARY_COOLDOWN_HOURS, SHOP=SHOP, MAX_WRONG=MAX_WRONG,
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
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"✅ البوت شغال: {self.user} ")


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
    return has_role(inter.user, role_setting(inter.guild, "role_police", config.POLICE_ROLE_ID)) or is_admin(inter)


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
    e.add_field(name="📝 الاختبار", value="/تحميل_الاسئلة · /اضافة_سؤال · /الاسئلة · /حذف_سؤال · `-تفعيل @العضو ايدي_سوني`", inline=False)
    e.add_field(name="✈️ الأقيام", value="اكتب `-قيم` في روم إنشاء القيم (لرتبة الأقيام)", inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)


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
    اللوق="روم اللوق",
)
async def setup_channels(
    inter: discord.Interaction,
    انشاء_هوية: discord.TextChannel = None,
    عرض_هوية: discord.TextChannel = None,
    انشاء_قيم: discord.TextChannel = None,
    شراء_تذكرة: discord.TextChannel = None,
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
    if اللوق:
        set_setting(gid, "ch_log", اللوق.id)
        done.append(f"✅ اللوق: {اللوق.mention}")

    if not done and not problems:
        rows = [
            ("إنشاء الهوية", "ch_create_id"), ("عرض الهوية", "ch_view_id"),
            ("إنشاء القيم", "ch_game"), ("شراء التذكرة", "ch_ticket"), ("اللوق", "ch_log"),
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
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    given = {"الادارة": الادارة, "الشرطة": الشرطة, "الاجرام": الاجرام,
             "الاعلام": الاعلام, "المواطن": المواطن, "الاقيام": الاقيام,
             "عضو_رسمي": عضو_رسمي, "مقيم": مقيم}
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
    if message.content.strip() != "-قيم":
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


@bot.tree.command(name="تسطيب_تذكرة", description="إضافة أو تعديل نوع تذكرة (لين 10 أنواع)")
@app_commands.describe(
    الرقم="رقم التذكرة من 1 إلى 10",
    الاسم="اسم التذكرة، مثل: جمارك، دعم فني، شكوى",
    الكاتقوري="الكاتقوري اللي تنفتح فيه التذاكر",
    رتبة_المسؤول="الرتبة اللي تستلم التذكرة وتشوفها",
    الايموجي="ايموجي يطلع جنب الاسم (اختياري)",
    رسالة_الترحيب="الكلام اللي يطلع أول ما تنفتح التذكرة (اختياري)",
)
async def setup_ticket(
    inter: discord.Interaction,
    الرقم: app_commands.Range[int, 1, 10],
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
async def delete_ticket_type(inter: discord.Interaction, الرقم: app_commands.Range[int, 1, 10]):
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
        for t in get_ticket_types(guild_id)
    ]
    view.add_item(discord.ui.Select(custom_id="ticket:open", placeholder="- اختر نوع التذكرة .", options=options))
    return view


@bot.tree.command(name="ارسال_التذاكر", description="إرسال لوحة التذاكر في روم")
@app_commands.describe(الروم="الروم اللي تنرسل فيه لوحة التذاكر", الوصف="الكلام اللي فوق القائمة (اختياري)")
async def send_ticket_panel(inter: discord.Interaction, الروم: discord.TextChannel, الوصف: str = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    types = get_ticket_types(inter.guild.id)
    if not types:
        return await inter.response.send_message(embed=err("ما سطّبت ولا تذكرة. استخدم /تسطيب_تذكرة أول."), ephemeral=True)
    lines = "\n".join(f"{t['emoji'] or '🎫'} - {t['name']}" for t in types)
    e = embed(
        "🎫 - التذاكر",
        (الوصف or f"- مرحبا بك عزيزي العضو في قسم التذاكر الخاص بـ **{config.SERVER_NAME}** .\n\n"
                  "اختر نوع التذكرة من القائمة اللي تحت .") + f"\n\n{lines}",
    )
    try:
        await الروم.send(embed=e, view=ticket_select(inter.guild.id))
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
    if get_questions(guild.id, slot):
        qe = embed(
            "📝 - الاختبار",
            "**- مرحبا بك عزيزي العضو .**\n\n📄 - عزيزي العضو باستطاعتك الان إستكمال الإجراءات "
            "عبر الزر المُتواجد بالأسفل وإستكمال الأسئلة التي تظهر لك .",
        )
        qv = discord.ui.View(timeout=None)
        qv.add_item(discord.ui.Button(label="- بدء الإختبار .", emoji="📝", style=discord.ButtonStyle.primary, custom_id="quiz:start"))
        await ch.send(embed=qe, view=qv)
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
    رقم_التذكرة: app_commands.Range[int, 1, 10],
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
async def list_questions(inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 10]):
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
    inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 10], رقم_السؤال: app_commands.Range[int, 1, 25]
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
async def load_default_questions(inter: discord.Interaction, رقم_التذكرة: app_commands.Range[int, 1, 10]):
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


async def quiz_start(inter: discord.Interaction):
    t = db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
    if not t:
        return await inter.response.send_message(embed=err("هذي مو تذكرة مسجلة."), ephemeral=True)
    if inter.user.id != t["owner_id"]:
        return await inter.response.send_message(embed=err("الاختبار لصاحب التذكرة بس."), ephemeral=True)
    qs = get_questions(inter.guild.id, t["slot"])
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
# التفعيل: -تفعيل @العضو ايدي_سوني
# ============================================================
def can_activate(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {r.id for r in member.roles}
    admin_role = get_setting(member.guild.id, "role_admin")
    if admin_role and admin_role in ids:
        return True
    return any(t["staff_role"] in ids for t in get_ticket_types(member.guild.id))


async def activate_command(message: discord.Message):
    if not can_activate(message.author):
        return await message.reply(embed=err("التفعيل للإدارة بس."))
    parts = message.content.split()
    usage = "الاستخدام: `-تفعيل @العضو ايدي_سوني` أو `-تفعيل ايدي_العضو ايدي_سوني`"
    if len(parts) < 3:
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
    sony_id = " ".join(parts[2:])[:60]

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
    await log(f"{message.author.mention} فعّل {member.mention} (سوني: `{sony_id}`)", message.guild)


@bot.event
async def on_interaction(inter: discord.Interaction):
    if inter.type != discord.InteractionType.component or not inter.guild:
        return
    cid = (inter.data or {}).get("custom_id", "")
    if cid == "ticket:open":
        values = inter.data.get("values") or []
        if values:
            await open_ticket(inter, int(values[0]))
    elif cid.startswith("ticket:"):
        await handle_ticket_button(inter, cid.split(":", 1)[1])
    elif cid == "quiz:start":
        await quiz_start(inter)
    elif cid.startswith("quiz:ans:"):
        await quiz_answer(inter, cid)


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
    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"🌐 السيرفر فاتح على port {port}")


if __name__ == "__main__":
    keep_alive()
    if not TOKEN:
        raise SystemExit("❌ حط توكن البوت في Environment في Render باسم DISCORD_TOKEN")
    bot.run(TOKEN)
