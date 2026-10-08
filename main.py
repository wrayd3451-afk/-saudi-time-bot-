# -*- coding: utf-8 -*-
"""
بوت نظام VRP لسيرفرات الرول بلاي على دسكورد
بنك - وظائف ورواتب - مخالفات - سجل جنائي
"""
import asyncio
import base64
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

# مكتبات الصوت لازم تنثبت قبل ما نفتح مكتبة ديسكورد (عشان البوت يقعد في الروم الصوتي)
# ديسكورد صار يشفّر الصوت (DAVE) ويحتاج: discord.py 2.7 وفوق + davey + PyNaCl
def _pkg_version(name: str):
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


_need = []
_v = _pkg_version("discord.py")
if not _v or tuple(int(x) for x in re.findall(r"\d+", _v)[:2]) < (2, 7):
    _need.append("discord.py>=2.7.1")
for _mod, _pkg in (("nacl", "PyNaCl"), ("davey", "davey")):
    try:
        __import__(_mod)
    except ImportError:
        _need.append(_pkg)
if _need:
    print(f"📦 أثبت مكتبات الصوت: {' '.join(_need)}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", *_need])
        import importlib
        importlib.invalidate_caches()
        print("✅ انثبتت مكتبات الصوت")
    except Exception as _e:
        print(f"⚠️ ما قدرت أثبت مكتبات الصوت: {_e}")

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

# اسم السيرفر (يظهر في الرسائل)
SERVER_NAME = "سعودي تايم | Saudi Time"

# العملة
CURRENCY = "$"

# الفلوس اللي ياخذها العضو أول ما ينفتح له حساب
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

# كم جواب صح لازم عشان ينجح في الاختبار (7 = لازم 7 صح أو أكثر)
PASS_MIN = 7

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
    SALARY_COOLDOWN_HOURS=SALARY_COOLDOWN_HOURS, SHOP=SHOP, PASS_MIN=PASS_MIN, INSPECT_FEE=INSPECT_FEE,
)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# ============================================================
# قاعدة البيانات
# ============================================================
# ============================================================
# النسخ الاحتياطي في ديسكورد (عشان البيانات ما تنمسح في Render)
# ============================================================
BACKUP_CH_NAME = "نسخ-احتياطي-البوت"
DB_FILE = "vrp.db"


def _discord_get(path: str, token: str):
    import urllib.request
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (saudi-time, 1.0)"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def restore_backup():
    """إذا ملف البيانات مو موجود (Render مسحه)، نرجّع آخر نسخة من روم النسخ الاحتياطي"""
    token = os.getenv("DISCORD_TOKEN")
    if not token or (os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 0):
        return
    try:
        import urllib.request
        for g in _discord_get("/users/@me/guilds", token):
            chans = _discord_get(f"/guilds/{g['id']}/channels", token)
            ch = next((c for c in chans if c.get("type") == 0 and c.get("name") == BACKUP_CH_NAME), None)
            if not ch:
                continue
            for m in _discord_get(f"/channels/{ch['id']}/messages?limit=20", token):
                att = next((a for a in m.get("attachments", []) if a.get("filename") == DB_FILE), None)
                if att:
                    req = urllib.request.Request(att["url"], headers={"User-Agent": "DiscordBot (saudi-time, 1.0)"})
                    with urllib.request.urlopen(req, timeout=60) as r, open(DB_FILE, "wb") as f:
                        f.write(r.read())
                    print(f"♻️ رجّعت البيانات من النسخة الاحتياطية ({m.get('timestamp', '')[:19]})")
                    return
        print("ℹ️ ما فيه نسخة احتياطية، نبدأ من جديد")
    except Exception as e:
        print(f"⚠️ ما قدرت أرجّع النسخة الاحتياطية: {e}")


restore_backup()
db = sqlite3.connect(DB_FILE)
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
CREATE TABLE IF NOT EXISTS rule_sections (
    guild_id INTEGER,
    idx      INTEGER,
    name     TEXT,
    emoji    TEXT,
    content  TEXT,
    PRIMARY KEY (guild_id, idx)
);
CREATE TABLE IF NOT EXISTS point_labels (
    guild_id INTEGER,
    category TEXT,
    label    TEXT,
    PRIMARY KEY (guild_id, category)
);
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER,
    key      TEXT,
    value    INTEGER,
    PRIMARY KEY (guild_id, key)
);
""")
db.commit()

# أعمدة جديدة لتفاصيل التذاكر (تنضاف حتى لو البيانات قديمة)
try:  # الرد التلقائي لرتبة معينة بس
    db.execute("ALTER TABLE auto_replies ADD COLUMN role_id INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:  # T1 مرة وحدة بس في كل تذكرة
    db.execute("ALTER TABLE tickets ADD COLUMN quiz_used INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
for _col, _def in (("btn_color", "TEXT DEFAULT 'primary'"), ("claim_on", "INTEGER DEFAULT 1"), ("ping_staff", "INTEGER DEFAULT 1")):
    try:
        db.execute(f"ALTER TABLE ticket_types ADD COLUMN {_col} {_def}")
    except sqlite3.OperationalError:
        pass  # موجود
db.commit()


def now():
    return datetime.now(timezone.utc)


def money(n: int) -> str:
    return f"{n:,} {config.CURRENCY}"


def get_player(user_id: int):
    """يرجع حساب العضو، ولو ما عنده يسوي له حساب تلقائي (ما فيه نظام هوية)"""
    row = db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return row
    name = str(user_id)
    try:
        u = bot.get_user(user_id)
        if u:
            name = u.display_name
    except Exception:
        pass
    db.execute(
        "INSERT OR IGNORE INTO players (user_id, id_number, name, job, cash, bank, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, new_id_number(), name, config.DEFAULT_JOB, config.START_CASH, config.START_BANK, now().isoformat()),
    )
    db.commit()
    return db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()


def new_id_number() -> str:
    while True:
        num = "1" + "".join(random.choices("0123456789", k=9))
        if not db.execute("SELECT 1 FROM players WHERE id_number = ?", (num,)).fetchone():
            return num


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
        # نرسل الأوامر لديسكورد بس إذا تغيّرت، عشان نقلل الطلبات
        import hashlib, json
        payload = json.dumps([c.to_dict(self.tree) for c in self.tree.get_commands()], sort_keys=True, ensure_ascii=False)
        digest = int(hashlib.sha1(("global-v2" + payload).encode()).hexdigest()[:12], 16)
        if get_setting(0, "commands_hash") == digest:
            print("ℹ️ الأوامر ما تغيّرت، ما يحتاج أرسلها")
            return
        self._pending_sync = digest  # نرسلها في on_ready لكل السيرفرات اللي فيها البوت

    async def _sync_all(self):
        """الأوامر تنرسل مرة وحدة (عامة لكل السيرفرات)، ونمسح النسخ الخاصة بكل سيرفر عشان ما تتكرر"""
        digest = getattr(self, "_pending_sync", None)
        if digest is None:
            return
        self._pending_sync = None
        try:
            await self.tree.sync()
        except discord.HTTPException as e:
            return print(f"⚠️ ديسكورد رفض تحديث الأوامر: {e}")
        for g in self.guilds:
            try:
                self.tree.clear_commands(guild=g)
                await self.tree.sync(guild=g)  # يمسح الأوامر المكررة الخاصة بالسيرفر
            except discord.HTTPException:
                pass
            await asyncio.sleep(1)
        set_setting(0, "commands_hash", digest)
        print(f"✅ انرسلت {len(self.tree.get_commands())} أمر (بدون تكرار)")

    async def on_ready(self):
        print(f"✅ البوت شغال: {self.user} ")
        await self._sync_all()
        if not getattr(self, "_voice_task", None):
            self._voice_task = asyncio.create_task(voice_keeper())
        if not getattr(self, "_snap_task", None):
            self._snap_task = asyncio.create_task(auto_server_snapshot())
        if not getattr(self, "_backup_task", None):
            self._backup_task = asyncio.create_task(backup_loop())
            try:
                import signal
                asyncio.get_running_loop().add_signal_handler(
                    signal.SIGTERM, lambda: asyncio.create_task(backup_and_exit()))
            except (NotImplementedError, RuntimeError):
                pass


bot = VRPBot()


# ---------- أدوات مساعدة ----------
def has_role(member: discord.Member, role_id: int) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if is_power(member):
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


def embed(title: str, desc: str = "", color=0x006C35) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color, timestamp=now())
    e.set_footer(text=config.SERVER_NAME)
    return e


def err(msg: str) -> discord.Embed:
    return embed("❌ خطأ", msg, 0x006C35)


async def log(text: str, guild=None):
    ch_id = (get_setting(guild.id, "ch_log") if guild else 0) or config.LOG_CHANNEL_ID
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        try:
            await ch.send(embed=embed("📋 لوق", text, 0x006C35))
        except discord.HTTPException:
            pass


async def require_player(inter: discord.Interaction, user: discord.abc.User = None):
    """يرجع حساب العضو (يتسوى تلقائي)"""
    target = user or inter.user
    p = get_player(target.id)
    if not p:
        who = "صار خطأ في حسابك." if target == inter.user else f"{target.mention} ما عنده حساب."
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
        return await inter.response.send_message(embed=err(f"{اللاعب.mention} ما عنده حساب."), ephemeral=True)
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
        return await inter.response.send_message(embed=err(f"{اللاعب.mention} ما عنده حساب."), ephemeral=True)
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
    e = embed("🚨 مخالفة جديدة", color=0x006C35)
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
        embed=embed("🚨 مخالفاتك", "\n".join(lines) + f"\n\n**المجموع:** {money(total)}\nسدد بأمر /سداد_مخالفة", 0x006C35),
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
    await inter.response.send_message(embed=embed("📁 تمت الإضافة للسجل", f"{اللاعب.mention}: {التهمة}", 0x006C35))
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
    e = embed(f"📁 ملف {اللاعب.display_name}", f"**الايدي :** `{اللاعب.id}`", 0x006C35)
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
# المتجر (بدون شنطة: يخصم الكاش ويعلن الشراء)
# ============================================================
@bot.tree.command(name="المتجر", description="عرض أغراض المتجر")
async def shop(inter: discord.Interaction):
    lines = [f"• **{item}**: {money(price)}" for item, price in config.SHOP.items()]
    await inter.response.send_message(embed=embed("🛒 المتجر", "\n".join(lines) + "\n\nاشترِ بأمر /شراء"), ephemeral=True)


async def shop_autocomplete(inter: discord.Interaction, current: str):
    return [app_commands.Choice(name=f"{i} ({money(p)})", value=i) for i, p in config.SHOP.items() if current in i][:25]


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
    db.commit()
    await inter.response.send_message(embed=embed("🛍️ تم الشراء", f"{inter.user.mention} اشترى **{الغرض}** ×{العدد} بـ {money(cost)}"))
    await log(f"{inter.user.mention} اشترى {الغرض} ×{العدد} بـ {money(cost)}", inter.guild)


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


@bot.tree.command(name="مساعدة", description="قائمة أوامر البوت")
async def help_cmd(inter: discord.Interaction):
    e = embed("📖 أوامر البوت")
    e.add_field(name="🏦 البنك", value="/رصيدي · /ايداع · /سحب · /تحويل · /اعطاء_كاش · /الاغنى", inline=False)
    e.add_field(name="🛒 المتجر", value="/المتجر · /شراء", inline=False)
    e.add_field(name="💼 الوظائف", value="/الوظائف · /راتب", inline=False)
    e.add_field(name="🚨 المخالفات", value="/مخالفاتي · /سداد_مخالفة", inline=False)
    e.add_field(name="👮 الشرطة", value="/مخالفة · /اضافة_سجل · /سجل", inline=False)
    e.add_field(name="🛠️ الإدارة", value="/تسطيب_رومات · /تسطيب_رتب · /تعيين_وظيفة · /اضافة_فلوس · /خصم_فلوس · /مسح_سجل", inline=False)
    e.add_field(name="🎫 التذاكر", value="/تسطيب_تذكرة · /حذف_تذكرة · /ارسال_التذاكر", inline=False)
    e.add_field(name="💬 الردود والإيمبد", value="/اضافة_رد · /حذف_رد · /الردود · /ايمبد · /رسالة_للكل", inline=False)
    e.add_field(name="📊 نقاط الإدارة", value="/تسطيب_نقاط_الادارة · /تعديل_نقاط_الادارة · /تصفير_نقاط_الادارة · /تسطيب_الاطار · /تسطيب_رتب_الادارة", inline=False)
    e.add_field(name="🚓 نقاط الشرطة و MDT", value="/تسطيب_نقاط_الشرطة · /تعديل_نقاط_الشرطة · /تصفير_نقاط_الشرطة · /ارسال_لوحة · /حذف_يونت", inline=False)
    e.add_field(name="🏦 البنك والرواتب", value="/ارسال_لوحة (البنك) · /تسطيب_رتب_الشرطة · /تسطيب_الرواتب · /صرف_الرواتب", inline=False)
    e.add_field(name="📜 القوانين", value="/تحميل_القوانين · /اضافة_قوانين · /حذف_قوانين · /ارسال_القوانين", inline=False)
    e.add_field(name="📝 التقديمات", value="/تسطيب_تقديم · /اسئلة_تقديم · /حذف_تقديم · /ارسال_التقديمات", inline=False)
    e.add_field(name="💼 التوظيف والاستقالة", value="/تسطيب_وظيفة · /حذف_وظيفة · /قائمة_الوظائف · `-اسم_الوظيفة @الشخص` · `-استقالة @الشخص`", inline=False)
    e.add_field(name="🛡️ الإسكات والحظر", value="`-اسكات @العضو 30 السبب` · `-فك_اسكات @العضو` · `-حظر ايدي السبب` · `-فك_حظر ايدي` (مشرف السجناء) · `-خط` · /تسطيب_الخط · /تسطيب_الادارة_العليا", inline=False)
    e.add_field(name="📝 الاختبار", value="/تحميل_الاسئلة · /اضافة_سؤال · العضو يكتب `T1` في تذكرته (بس T1) · `-تفعيل @العضو`", inline=False)
    e.add_field(name="✈️ الأقيام", value="`-قيم` في روم إنشاء القيم · `-تفتيش @العضو` في روم التفتيش · /تسطيب_التفتيش", inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)


# ============================================================
# النسخ الاحتياطي: كل دقيقتين إذا تغيّر شي
# ============================================================
_last_backup_changes = -1


async def get_backup_channel():
    guilds = [bot.get_guild(GUILD_ID)] if GUILD_ID and bot.get_guild(GUILD_ID) else list(bot.guilds)
    for g in guilds:
        ch = discord.utils.get(g.text_channels, name=BACKUP_CH_NAME)
        if ch:
            return ch
    for g in guilds:  # ما لقيناه، نسويه (خاص، محد يشوفه غير الأدمن)
        try:
            return await g.create_text_channel(
                BACKUP_CH_NAME,
                overwrites={g.default_role: discord.PermissionOverwrite(view_channel=False),
                            g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                             attach_files=True, read_message_history=True)},
                topic="لا تحذف هذا الروم. البوت يحفظ فيه بياناته عشان ما تنمسح.",
            )
        except discord.HTTPException:
            continue
    return None


async def do_backup(force: bool = False):
    global _last_backup_changes
    if not force and db.total_changes == _last_backup_changes:
        return
    ch = await get_backup_channel()
    if not ch:
        return
    db.commit()
    tmp = "vrp_backup_tmp.db"
    bk = sqlite3.connect(tmp)
    db.backup(bk)
    bk.close()
    try:
        await ch.send(content=f"💾 نسخة احتياطية <t:{int(now().timestamp())}:R>", file=discord.File(tmp, filename=DB_FILE))
        _last_backup_changes = db.total_changes
        # نخلي آخر 3 نسخ بس
        old = [m async for m in ch.history(limit=30) if m.author.id == bot.user.id][3:]
        for m in old:
            try:
                await m.delete()
            except discord.HTTPException:
                pass
    except discord.HTTPException as e:
        print(f"⚠️ فشل النسخ الاحتياطي: {e}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


async def backup_loop():
    await bot.wait_until_ready()
    global _last_backup_changes
    _last_backup_changes = db.total_changes  # لا نرفع نسخة أول ما نشتغل
    while not bot.is_closed():
        await asyncio.sleep(120)
        try:
            await do_backup()
        except Exception as e:
            print(f"⚠️ خطأ في النسخ الاحتياطي: {e}")


async def backup_and_exit():
    print("💾 Render يطفي البوت، نحفظ نسخة أخيرة...")
    try:
        await asyncio.wait_for(do_backup(), timeout=20)
    except Exception:
        pass
    await bot.close()


@bot.tree.command(name="نسخة_احتياطية", description="حفظ نسخة احتياطية من بيانات البوت الحين")
async def manual_backup(inter: discord.Interaction):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    await do_backup(force=True)
    ch = await get_backup_channel()
    await inter.followup.send(embed=embed("💾 تم الحفظ", f"النسخة في {ch.mention}" if ch else "ما قدرت ألقى روم النسخ."), ephemeral=True)


# الصلاحيات العادية للأعضاء (بدون أي صلاحية إدارية)
NORMAL_PERMS = dict(
    view_channel=True, read_message_history=True, send_messages=True, send_messages_in_threads=True,
    create_public_threads=True, embed_links=True, attach_files=True, add_reactions=True,
    use_external_emojis=True, use_external_stickers=True, send_voice_messages=True, use_application_commands=True,
    change_nickname=True, connect=True, speak=True, stream=True, use_voice_activation=True,
    use_soundboard=True, use_embedded_activities=True, request_to_speak=True,
)


CHANNEL_KEEP = {"view_channel", "send_messages", "send_messages_in_threads", "create_public_threads"}


@bot.tree.command(name="اصلاح_الصلاحيات", description="يعطي الكل الصلاحيات العادية (كتابة، صور، فويس، صوتي...) في كل الرومات - لصاحب السيرفر")
async def fix_history_perms(inter: discord.Interaction):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب السيرفر بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    guild = inter.guild
    fixed, failed = 0, []
    # 1) صلاحية @everyone في السيرفر: عرض الرومات + قراءة الرسائل السابقة
    try:
        p = guild.default_role.permissions
        normal = dict(NORMAL_PERMS)
        if any(not getattr(p, k) for k in normal):
            p.update(**normal)
            await guild.default_role.edit(permissions=p, reason="اصلاح الصلاحيات")
            fixed += 1
    except (discord.Forbidden, discord.HTTPException):
        failed.append("@everyone (السيرفر)")
    # 2) كل الرومات والكاتيجوريات: أي ❌ على (Read Message History) تصير ⧸ محايدة
    #    (ما نلمس View Channel عشان الرومات الخاصة تبقى خاصة)
    for ch in guild.channels:
        for target, ow in list(ch.overwrites.items()):
            changed = False
            for perm in NORMAL_PERMS:
                if perm in CHANNEL_KEEP:
                    continue  # ما نلمسها: الرومات الخاصة تبقى خاصة، ورومات القراءة بس تبقى بدون كتابة
                if getattr(ow, perm) is False:
                    setattr(ow, perm, None)
                    changed = True
            if changed:
                try:
                    await ch.set_permissions(target, overwrite=None if ow.is_empty() else ow, reason="اصلاح الصلاحيات")
                    fixed += 1
                except (discord.Forbidden, discord.HTTPException):
                    failed.append(ch.name)
                await asyncio.sleep(0.4)
    msg = f"✅ تم إصلاح **{fixed}** صلاحية.\nالحين الكل عنده الصلاحيات العادية: يكتب، يرسل **صور** و**فويسات**، يتفاعل، ويدخل **الرومات الصوتية** ويتكلم.\nالرومات الخاصة ما تغيّرت وبقت خاصة."
    if failed:
        msg += "\n\n⚠️ ما قدرت أعدّل: " + "، ".join(sorted(set(failed))[:20]) + "\nارفع رتبة البوت فوق الرتب وعطه صلاحية **Manage Roles** و **Manage Channels**."
    await inter.followup.send(embed=embed("🔧 إصلاح الصلاحيات", msg), ephemeral=True)


# ============================================================
# البوت يقعد في روم صوتي 24 ساعة
# ============================================================
LAST_VOICE_ERROR = {}


def _voice_error_ar(e: Exception) -> str:
    t = f"{type(e).__name__}: {e}"
    if "PyNaCl" in t or "nacl" in t.lower():
        return "مكتبة الصوت (PyNaCl) مو مثبتة على الاستضافة"
    if "davey" in t.lower() or "4017" in t or "DAVE" in t:
        return "مكتبة تشفير الصوت (davey) ما انثبتت. ارفع requirements.txt وسوّ Clear build cache & deploy"
    if isinstance(e, discord.Forbidden) or "Missing Permissions" in t:
        return "ما عندي صلاحية Connect أو View Channel في الروم"
    if isinstance(e, asyncio.TimeoutError) or "Timeout" in t:
        return "انتهى الوقت وأنا أحاول أتصل (الاستضافة ممكن تمنع اتصال الصوت)"
    return t[:180]


def _ensure_voice_libs():
    try:
        import nacl  # noqa: F401
        return
    except ImportError:
        pass
    for pkg in (["discord.py[voice]"], ["PyNaCl"]):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", *pkg])
            return
        except Exception:
            continue


async def join_voice(guild: discord.Guild) -> bool:
    ch = guild.get_channel(get_setting(guild.id, "ch_voice"))
    if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
        LAST_VOICE_ERROR[guild.id] = "ما لقيت الروم الصوتي"
        return False
    perms = ch.permissions_for(guild.me)
    if not (perms.view_channel and perms.connect):
        LAST_VOICE_ERROR[guild.id] = "ما عندي صلاحية View Channel أو Connect في الروم"
        return False
    vc = guild.voice_client
    try:
        if vc and vc.is_connected():
            if vc.channel.id != ch.id:
                await vc.move_to(ch)
            return True
        if vc:
            await vc.disconnect(force=True)
        try:
            await ch.connect(self_deaf=True, reconnect=True, timeout=30)
        except RuntimeError as e:
            if "PyNaCl" not in str(e):
                raise
            await asyncio.to_thread(_ensure_voice_libs)
            await ch.connect(self_deaf=True, reconnect=True, timeout=30)
        LAST_VOICE_ERROR.pop(guild.id, None)
        print(f"🔊 دخلت الروم الصوتي: {ch.name}")
        return True
    except Exception as e:
        LAST_VOICE_ERROR[guild.id] = _voice_error_ar(e)
        print(f"⚠️ ما قدرت أدخل الروم الصوتي: {type(e).__name__}: {e}")
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
def has_owner_role(member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    rid = get_setting(member.guild.id, "role_owner")
    return bool(rid and any(r.id == rid for r in member.roles))


def is_power(member) -> bool:
    """أدمن أو الرتبة الأونرية"""
    return isinstance(member, discord.Member) and (member.guild_permissions.administrator or has_owner_role(member))


def admin_only(inter: discord.Interaction) -> bool:
    """الأدمن أو الرتبة الأونرية (أقوى صلاحية)"""
    return isinstance(inter.user, discord.Member) and (inter.user.guild_permissions.administrator or has_owner_role(inter.user))


@bot.tree.command(name="تسطيب_رومات", description="تحديد رومات البوت (لصاحب صلاحية الأدمن)")
@app_commands.describe(
    انشاء_قيم="الروم اللي يكتبون فيه -قيم",
    شراء_تذكرة="الروم اللي ينرسل فيه إعلان الرحلة",
    التفتيش="الروم اللي يكتبون فيه -تفتيش",
    تحديث_الادوار="الروم اللي ينرسل فيه التوظيف والاستقالات",
    القروض="الروم اللي توصل فيه طلبات القروض",
    الصوتي="الروم الصوتي اللي يقعد فيه البوت 24 ساعة",
    ايدي_الصوتي="أو حط ايدي الروم الصوتي هنا (إذا ما لقيته في القائمة)",
    اللوق="روم اللوق",
)
async def setup_channels(
    inter: discord.Interaction,
    انشاء_قيم: discord.TextChannel = None,
    شراء_تذكرة: discord.TextChannel = None,
    التفتيش: discord.TextChannel = None,
    تحديث_الادوار: discord.TextChannel = None,
    القروض: discord.TextChannel = None,
    الصوتي: discord.VoiceChannel = None,
    ايدي_الصوتي: str = None,
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
    if not الصوتي and ايدي_الصوتي:
        raw = ايدي_الصوتي.strip().strip("<#>")
        ch = inter.guild.get_channel(int(raw)) if raw.isdigit() else None
        if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
            الصوتي = ch
        else:
            problems.append("⚠️ ايدي الروم الصوتي غلط، أو الروم مو صوتي.")
    if الصوتي:
        set_setting(gid, "ch_voice", الصوتي.id)
        ok = await join_voice(inter.guild)
        done.append(f"✅ الصوتي: {الصوتي.mention}" + ("" if ok else f"\n⚠️ ما قدرت أدخل: **{LAST_VOICE_ERROR.get(gid, 'سبب غير معروف')}**"))
    if اللوق:
        set_setting(gid, "ch_log", اللوق.id)
        done.append(f"✅ اللوق: {اللوق.mention}")

    if not done and not problems:
        rows = [
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
    ("الاقيام", "role_host", "الأقيام"),
    ("عضو_رسمي", "role_official", "عضو رسمي"),
    ("مقيم", "role_resident", "مقيم"),
    ("عضو_غير_رسمي", "role_unofficial", "عضو غير رسمي (تنشال بأمر -تفعيل)"),
    ("المفعلين", "role_activator", "المفعّلين (يقدرون يستخدمون -تفعيل)"),
    ("السوات", "role_swat", "السوات"),
    ("العدل", "role_justice", "العدل"),
    ("الاونر", "role_owner", "الأونر (أقوى صلاحية في البوت)"),
    ("مشرف_السجناء", "role_prison", "مشرف السجناء (يقدرون يستخدمون -حظر)"),
]


@bot.tree.command(name="تسطيب_رتب", description="تحديد رتب السيرفر (لصاحب صلاحية الأدمن)")
@app_commands.describe(
    الادارة="رتبة الإدارة",
    الشرطة="رتبة الشرطة",
    الاجرام="رتبة الإجرام",
    الاعلام="رتبة الإعلام",
    الاقيام="الرتبة اللي تقدر تسوي -قيم",
    عضو_رسمي="الرتبة الأولى اللي تنعطى بأمر -تفعيل",
    مقيم="الرتبة الثانية اللي تنعطى بأمر -تفعيل",
    عضو_غير_رسمي="الرتبة اللي تنشال من العضو لما يتفعّل",
    المفعلين="الرتبة اللي تقدر تستخدم -تفعيل",
    السوات="رتبة السوات",
    العدل="رتبة العدل",
    الاونر="الرتبة الأونرية: أقوى صلاحية، تقدر تستخدم كل أوامر البوت",
    مشرف_السجناء="الرتبة اللي تقدر تستخدم -حظر و -فك_حظر",
)
async def setup_roles(
    inter: discord.Interaction,
    الادارة: discord.Role = None,
    الشرطة: discord.Role = None,
    الاجرام: discord.Role = None,
    الاعلام: discord.Role = None,
    الاقيام: discord.Role = None,
    عضو_رسمي: discord.Role = None,
    مقيم: discord.Role = None,
    عضو_غير_رسمي: discord.Role = None,
    المفعلين: discord.Role = None,
    السوات: discord.Role = None,
    العدل: discord.Role = None,
    الاونر: discord.Role = None,
    مشرف_السجناء: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    given = {"الادارة": الادارة, "الشرطة": الشرطة, "الاجرام": الاجرام,
             "الاعلام": الاعلام, "الاقيام": الاقيام,
             "عضو_رسمي": عضو_رسمي, "مقيم": مقيم, "عضو_غير_رسمي": عضو_غير_رسمي,
             "المفعلين": المفعلين, "السوات": السوات, "العدل": العدل, "الاونر": الاونر, "مشرف_السجناء": مشرف_السجناء}
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


# ============================================================
# الخط: الأونر يكتب -خط ← تنحذف رسالته ويرسل البوت صورة الخط
# ============================================================
DEFAULT_LINE_PNG = "iVBORw0KGgoAAAANSUhEUgAAAwgAAAAoCAIAAADVI0rrAAClHElEQVR4nHy965MtV5Xtt16Zuavq6IUACSEh0eLRgPvd9NN9+3HDH+yIG3H/OP8hDofDHeEvDjva3XTTXKAlGiQEAgF6Cx1Jp2rvzPVy/MZcuask2i4JcapO7b0zV641H2OOOWa6es735Kp3belhnkqsvXcX3eSdcy642HpvrRXfe3Ou+UOOcwmxRFdqz660WpxvvYdWg3dTdz46f3DtXiqHVJOPxfkect3WnF1w6TL6JdZY+a/PLngXfWi+tRZbCCF037prcY6HOQTngu+l9jXnUqdefHjQ+01NxxZ9dDHlWOtFvXrkYqtb7/1wOHjv66mtx82tJdQUmvelu9x7bb537sinUkoPLgTffffcZiiFz+69+841hO5678H5GELcqved60jNxdCDq64315vWx3nvY+i9lt66dyG4GOM0TS7MpZR13VprgY/lRltrvLi7Zt93faJr0XEVLHv1/Dd4731zPoTQWuMbz/r47tIc4xx7r666VmsptXXnIs9pSlx2za1WF6Pr0beUpmmKtZd1axvXEFvk/6ouPPnWau3Nswh8ruedeore61rsQmKM3kc+PXIx3IBrLvqY+jRNaY5bq3bBznGDWrfovU8h1lrbWkspgbVnsbu+tHC8f3f2c75NPG3XePqsYQ1cROs9dj0SXckUU611K7n3nnMPwbFuzbFY3U0uhhRbK+xV73v0pdeq9ZlmdzHHEPnzvp/16cHrifAeuiTWuWl92HshzIGH73r1jets0W+eE+JaC7X75n3rUVvB+6j34d1YytsvnnbS+7OSznXvuDteySN20SXHPcbedCus5hLDPIWQenN167n0Vkp31aXiQnep+9L71lwpbq6RJey9xdYn3xdXoy+xtujTHPnNLafiYndzdaW6a+7RucZDD64n51NwwfnkdDq0o7Xe3vGLvQUsQO+hereGWvmIlFJ6ZH7kT772R3/8pd//7NWnam4h+Q/KR//0k3/6b+9+651Pv++/kbYnqks8Fbc67n6xNdV6ZG1C71zyLneX9Ofuxh+q/tz0B9kc14JrlT8X5zZ7of6quPDrePjRdPHziz/71Df/8+/9p6uLJc4pt/pgvf7VL17752//w2u//ElMPErbnNr+tVa3LInb5OzZ9u+Vr+bYeN413zFKvpSi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"
db.execute("CREATE TABLE IF NOT EXISTS line_images (guild_id INTEGER PRIMARY KEY, data BLOB, filename TEXT)")
db.commit()


def is_owner_role(member: discord.Member) -> bool:
    owner_role = get_setting(member.guild.id, "role_owner")
    return member.id == member.guild.owner_id or bool(owner_role and any(r.id == owner_role for r in member.roles))


async def line_command(message: discord.Message):
    if not is_owner_role(message.author):
        return
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass
    row = db.execute("SELECT data, filename FROM line_images WHERE guild_id = ?", (message.guild.id,)).fetchone()
    if row:
        data, fname = bytes(row[0]), row[1] or "line.png"
    else:
        data, fname = base64.b64decode(DEFAULT_LINE_PNG), "line.png"
    try:
        await message.channel.send(file=discord.File(io.BytesIO(data), filename=fname))
    except discord.HTTPException:
        pass


@bot.tree.command(name="تسطيب_الخط", description="تغيير صورة الخط اللي تطلع بأمر -خط (للأونر)")
@app_commands.describe(صورة="ارفع صورة الخط الجديدة (اتركها فاضية ترجع الصورة الأصلية)")
async def setup_line(inter: discord.Interaction, صورة: discord.Attachment = None):
    if not is_owner_role(inter.user):
        return await inter.response.send_message(embed=err("هذا الأمر للأونر بس."), ephemeral=True)
    if صورة is None:
        db.execute("DELETE FROM line_images WHERE guild_id = ?", (inter.guild.id,))
        db.commit()
        return await inter.response.send_message(embed=embed("✅ الخط", "رجعت صورة الخط الأصلية."), ephemeral=True)
    if not (صورة.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("لازم تكون صورة."), ephemeral=True)
    if صورة.size > 8 * 1024 * 1024:
        return await inter.response.send_message(embed=err("الصورة كبيرة، خلها أقل من 8 ميقا."), ephemeral=True)
    data = await صورة.read()
    db.execute("INSERT OR REPLACE INTO line_images (guild_id, data, filename) VALUES (?, ?, ?)",
               (inter.guild.id, data, صورة.filename))
    db.commit()
    await inter.response.send_message(embed=embed("✅ الخط", "تم تغيير صورة الخط. جرّب `-خط`."), ephemeral=True)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    # الجوال أحيانًا يحط علامات اتجاه مخفية (RTL) قبل الكلام، نشيلها عشان الأوامر تشتغل
    try:
        message.content = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", message.content or "")
    except AttributeError:
        pass
    if await prot_message(message):
        return
    if await suggestion_check(message):
        return
    if message.content.strip().startswith("-تفعيل"):
        return await activate_command(message)
    if message.content.strip().startswith("-تفتيش"):
        return await inspect_command(message)
    first = message.content.strip().split()[:1]
    if message.content.strip().split()[:1] in (["-ايموجي"], ["-إيموجي"], ["-ايموجيات"]):
        return await emoji_prefix(message)
    if first == ["-اسم"]:
        return await rename_prefix(message)
    if first == ["-ر"]:
        return await role_prefix(message)
    if first == ["-نسخ_من"]:
        try:
            return await clone_from_prefix(message)
        except Exception as ex:
            import traceback; traceback.print_exc()
            return await message.reply(f"⚠️ صار خطأ في النسخ: `{type(ex).__name__}: {str(ex)[:300]}`")
    if first in (["-فحص"], ["-بنق"]):
        me = message.guild.me
        p = message.channel.permissions_for(me)
        return await message.reply(
            f"✅ البوت شغال ويشوف رسايلك\n"
            f"**Administrator:** {'✅' if me.guild_permissions.administrator else '❌'} · "
            f"**يكتب هنا:** {'✅' if p.send_messages else '❌'}\n"
            f"**أنت صاحب السيرفر:** {'✅' if message.author.id == message.guild.owner_id else '❌'}\n"
            "**النسخ المحفوظة:** " + str(db.execute("SELECT COUNT(*) FROM assets WHERE key = 'server_clone'").fetchone()[0]))
    if first == ["-استرجاع"]:
        try:
            return await restore_prefix(message)
        except Exception as ex:  # نعرض الخطأ بدل ما يسكت
            import traceback; traceback.print_exc()
            return await message.reply(f"⚠️ صار خطأ في الاسترجاع: `{type(ex).__name__}: {str(ex)[:300]}`\nصوّره وأرسله.")
    if first == ["-خط"]:
        return await line_command(message)
    if first in (["-فت"], ["-فتح"]):
        return await room_prefix(message, True)
    if first in (["-قف"], ["-قفل"]):
        return await room_prefix(message, False)
    # T1 بس = أسئلة التذكرة (داخل التذكرة ولصاحبها)، وغيرها يروح للردود التلقائية
    if message.content.strip().strip("•·").strip().upper() == "T1":
        if await quiz_shortcut(message, 1):
            return
        return await auto_reply(message)
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
    if not (is_power(message.author) or
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
    text = message.content.strip().strip("•·").strip()
    if not text:
        return
    row = db.execute(
        "SELECT * FROM auto_replies WHERE guild_id = ? AND trim(trigger, '•· ') = ? COLLATE NOCASE",
        (message.guild.id, text),
    ).fetchone()
    if not row:
        return
    rid = row["role_id"] if "role_id" in row.keys() else 0
    if rid and not any(r.id == rid for r in getattr(message.author, "roles", [])):
        return  # الرد لرتبة معينة بس
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

    def __init__(self, trigger: str, as_embed: bool, role_id: int = 0):
        super().__init__()
        self.trigger = trigger
        self.as_embed = as_embed
        self.role_id = role_id

    async def on_submit(self, inter: discord.Interaction):
        db.execute(
            "INSERT INTO auto_replies (guild_id, trigger, response, as_embed, role_id) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, trigger) DO UPDATE SET response = excluded.response, as_embed = excluded.as_embed, "
            "role_id = excluded.role_id",
            (inter.guild.id, self.trigger, self.response.value, int(self.as_embed), self.role_id),
        )
        db.commit()
        await inter.response.send_message(
            embed=embed("✅ انضاف الرد", f"إذا {f'أحد معه <@&{self.role_id}>' if self.role_id else 'أي أحد'} كتب **{self.trigger}** يرد البوت بـ{'ايمبد' if self.as_embed else 'رسالة'}:\n\n{self.response.value}"[:4000]),
            ephemeral=True,
        )


@bot.tree.command(name="اضافة_رد", description="إضافة رد تلقائي على كلمة")
@app_commands.describe(الكلمة="الكلمة اللي إذا أحد كتبها يرد البوت", ايمبد="الرد يطلع ايمبد؟",
                       الرتبة="البوت يرد بس على اللي معه هالرتبة (فاضي = يرد على الكل)")
@app_commands.choices(ايمبد=[app_commands.Choice(name="لا، رسالة عادية", value=0), app_commands.Choice(name="إيه، ايمبد", value=1)])
async def add_auto_reply(inter: discord.Interaction, الكلمة: app_commands.Range[str, 1, 100], ايمبد: app_commands.Choice[int] = None,
                         الرتبة: discord.Role = None):
    if not is_admin(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة فقط."), ephemeral=True)
    await inter.response.send_modal(AutoReplyModal(الكلمة.strip(), bool(ايمبد and ايمبد.value), الرتبة.id if الرتبة else 0))


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


@bot.tree.command(name="قائمة_التذاكر", description="تشوف كل التذاكر: رقمها واسمها وتفاصيلها")
async def list_tickets(inter: discord.Interaction):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    types_ = get_ticket_types(inter.guild.id)
    if not types_:
        return await inter.response.send_message(embed=err("ما سطّبت ولا تذكرة. استخدم /تسطيب_تذكرة"), ephemeral=True)
    e = embed("🎫 - قائمة التذاكر", f"عدد التذاكر: **{len(types_)}** من 20")
    for t in types_:
        sups = db.execute("SELECT role_id FROM ticket_supervisors WHERE guild_id = ? AND slot = ?",
                          (inter.guild.id, t["slot"])).fetchall()
        opened = db.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND slot = ?",
                            (inter.guild.id, t["slot"])).fetchone()[0]
        qn = db.execute("SELECT COUNT(*) FROM quiz_questions WHERE guild_id = ? AND slot = ?",
                        (inter.guild.id, t["slot"])).fetchone()[0]
        info = [
            f"**الشكل:** {'أزرار' if t['slot'] > 10 else 'منيو'}",
            ("**المسؤول:** " + (f"<@&{t['staff_role']}>" if t['staff_role'] else "ما تحدد")),
            f"**الاستلام:** {'✅' if (t['claim_on'] if t['claim_on'] is not None else 1) else '❌'}",
            f"**المشرفين:** {' '.join(f'<@&{r[0]}>' for r in sups) if sups else 'لا أحد'}",
            f"**مفتوحة الحين:** {opened} · **الأسئلة:** {qn}",
        ]
        e.add_field(name=f"#{t['slot']} - {t['emoji'] or '🎫'} {t['name']}", value="\n".join(info)[:1024], inline=False)
        if len(e.fields) >= 25:
            break
    await inter.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="تسطيب_تذكرة", description="إضافة أو تعديل نوع تذكرة (1-10 منيو، 11-20 أزرار)")
@app_commands.describe(
    الرقم="1 إلى 10 تطلع في المنيو، و 11 إلى 20 تطلع أزرار",
    الاسم="اسم التذكرة، مثل: جمارك، دعم فني، شكوى",
    الكاتقوري="الكاتقوري اللي تنفتح فيه التذاكر",
    رتبة_المسؤول="الرتبة اللي تستلم التذكرة وتشوفها",
    الايموجي="ايموجي يطلع جنب الاسم (اختياري)",
    رسالة_الترحيب="الكلام اللي يطلع أول ما تنفتح التذكرة (اختياري)",
    لون_الزر="لون الزر في لوحة الأزرار (التذاكر 11-20)",
    الاستلام="فيها زر استلام وترك التذكرة ولا لا",
    منشن_المسؤول="يمنشن رتبة المسؤول أول ما تنفتح التذكرة",
)
@app_commands.choices(
    لون_الزر=[app_commands.Choice(name=n, value=v) for n, v in
             (("أزرق", "primary"), ("أخضر", "success"), ("رمادي", "secondary"), ("أحمر", "danger"))],
    الاستلام=[app_commands.Choice(name="إيه، فيها استلام", value=1), app_commands.Choice(name="لا، بدون استلام", value=0)],
    منشن_المسؤول=[app_commands.Choice(name="إيه، منشن", value=1), app_commands.Choice(name="لا، بدون منشن", value=0)],
)
async def setup_ticket(
    inter: discord.Interaction,
    الرقم: app_commands.Range[int, 1, 20],
    الاسم: app_commands.Range[str, 1, 40],
    الكاتقوري: discord.CategoryChannel,
    رتبة_المسؤول: discord.Role,
    الايموجي: str = None,
    رسالة_الترحيب: str = None,
    لون_الزر: app_commands.Choice[str] = None,
    الاستلام: app_commands.Choice[int] = None,
    منشن_المسؤول: app_commands.Choice[int] = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    old = db.execute("SELECT * FROM ticket_types WHERE guild_id = ? AND slot = ?", (inter.guild.id, الرقم)).fetchone()
    color = لون_الزر.value if لون_الزر else (old["btn_color"] if old and old["btn_color"] else "primary")
    claim = الاستلام.value if الاستلام else (old["claim_on"] if old and old["claim_on"] is not None else 1)
    ping = منشن_المسؤول.value if منشن_المسؤول else (old["ping_staff"] if old and old["ping_staff"] is not None else 1)
    emoji = (الايموجي or "").strip()[:30] if الايموجي is not None else (old["emoji"] if old else "")
    welcome = رسالة_الترحيب or (old["welcome"] if old else DEFAULT_TICKET_WELCOME)
    db.execute(
        "INSERT INTO ticket_types (guild_id, slot, name, emoji, category_id, staff_role, welcome, btn_color, claim_on, ping_staff) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id, slot) DO UPDATE SET name = excluded.name, "
        "emoji = excluded.emoji, category_id = excluded.category_id, staff_role = excluded.staff_role, "
        "welcome = excluded.welcome, btn_color = excluded.btn_color, claim_on = excluded.claim_on, ping_staff = excluded.ping_staff",
        (inter.guild.id, الرقم, الاسم, emoji, الكاتقوري.id, رتبة_المسؤول.id, welcome, color, claim, ping),
    )
    db.commit()
    colors = {"primary": "🔵 أزرق", "success": "🟢 أخضر", "secondary": "⚪ رمادي", "danger": "🔴 أحمر"}
    await inter.response.send_message(
        embed=embed(
            "🎫 تم تسطيب التذكرة",
            f"**رقم {الرقم}:** {الاسم}\nالكاتقوري: {الكاتقوري.mention}\nالمسؤول: {رتبة_المسؤول.mention}\n"
            f"**الشكل:** {'أزرار' if الرقم > 10 else 'منيو'}" + (f" | **لون الزر:** {colors[color]}" if الرقم > 10 else "") + "\n"
            f"**الاستلام:** {'✅ فيها' if claim else '❌ بدون (قفل بس)'}\n**منشن المسؤول:** {'✅' if ping else '❌'}\n\n"
            "لما تخلص، أرسل اللوحة بـ **/ارسال_التذاكر** .",
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


def ticket_select(guild_id: int, slots=None) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    options = [
        discord.SelectOption(label=t["name"], value=str(t["slot"]), emoji=t["emoji"] or None)
        for t in get_ticket_types(guild_id) if (t["slot"] in slots if slots else t["slot"] <= 10)
    ]
    view.add_item(discord.ui.Select(custom_id="ticket:open", placeholder="- اختر نوع التذكرة .", options=options))
    return view


def ticket_buttons_panel(guild_id: int, slots=None) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    styles = {"primary": discord.ButtonStyle.primary, "success": discord.ButtonStyle.success,
              "secondary": discord.ButtonStyle.secondary, "danger": discord.ButtonStyle.danger}
    for i, t in enumerate([t for t in get_ticket_types(guild_id) if (t["slot"] in slots if slots else t["slot"] > 10)]):
        view.add_item(discord.ui.Button(label=t["name"], emoji=t["emoji"] or None,
                                        style=styles.get(t["btn_color"] or "primary", discord.ButtonStyle.primary),
                                        custom_id=f"ticket:btn:{t['slot']}", row=i // 5))
    return view


@bot.tree.command(name="ارسال_التذاكر", description="إرسال لوحة التذاكر في روم")
@app_commands.describe(
    الروم="الروم اللي تنرسل فيه لوحة التذاكر",
    الشكل="منيو (التذاكر 1-10) أو أزرار (التذاكر 11-20)",
    الأرقام="أرقام التذاكر اللي تطلع في هاللوحة بس، مثل: 12 أو 11,13 (فاضي = كلها)",
    الوصف="الكلام اللي فوق (اختياري)",
    الصورة="صورة تطلع في اللوحة (فاضي = صورة سعودي تايم الخضراء)",
)
@app_commands.choices(الشكل=[
    app_commands.Choice(name="منيو (التذاكر 1 - 10)", value="menu"),
    app_commands.Choice(name="أزرار (التذاكر 11 - 20)", value="buttons"),
])
async def send_ticket_panel(inter: discord.Interaction, الروم: discord.TextChannel,
                            الشكل: app_commands.Choice[str] = None, الأرقام: str = None, الوصف: str = None,
                            الصورة: discord.Attachment = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    buttons = bool(الشكل and الشكل.value == "buttons")
    slots = None
    if الأرقام:
        slots = [int(x) for x in re.findall(r"\d+", الأرقام.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))]
        types = [t for t in get_ticket_types(inter.guild.id) if t["slot"] in slots]
        if not الشكل:  # لو ما اختار الشكل، ناخذه من رقم أول تذكرة
            buttons = bool(types) and types[0]["slot"] > 10
    else:
        types = [t for t in get_ticket_types(inter.guild.id) if (t["slot"] > 10) == buttons]
    if not types:
        return await inter.response.send_message(embed=err(
            ("ما لقيت تذاكر بهالأرقام." if الأرقام else
             "ما سطّبت ولا تذكرة " + ("من 11 إلى 20 (الأزرار)." if buttons else "من 1 إلى 10 (المنيو)."))
            + " شف /تسطيب_تذكرة"), ephemeral=True)
    slots = [t["slot"] for t in types]
    lines = "\n".join(f"{t['emoji'] or '🎫'} - {t['name']}" for t in types)
    e = embed(
        "🎫 - التذاكر",
        (الوصف or f"- مرحبا بك عزيزي العضو في قسم التذاكر الخاص بـ **{config.SERVER_NAME}** .\n\n"
                  + ("اضغط على الزر حق التذكرة اللي تبيها ." if buttons else "اختر نوع التذكرة من القائمة اللي تحت .")) + f"\n\n{lines}",
    )
    if الصورة is not None and (الصورة.content_type or "").startswith("image/"):
        ext = os.path.splitext(الصورة.filename)[1].lower() or ".png"
        pfile = discord.File(io.BytesIO(await الصورة.read()), filename=f"panel{ext}")
    else:
        pfile, _ = ticket_image_file(inter.guild.id, 0)
        pfile.filename = "panel" + os.path.splitext(pfile.filename)[1]
    e.set_image(url=f"attachment://{pfile.filename}")
    try:
        await الروم.send(embed=e, file=pfile,
                         view=ticket_buttons_panel(inter.guild.id, slots) if buttons else ticket_select(inter.guild.id, slots))
    except discord.Forbidden:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    except discord.HTTPException:
        return await inter.response.send_message(
            embed=err("فيه ايموجي غلط في وحدة من التذاكر. عدّلها بـ /تسطيب_تذكرة وحط ايموجي عادي مثل 🛃"), ephemeral=True
        )
    register_panel(inter.guild.id, "tickets_btn" if buttons else "tickets", الروم.id, {"buttons": buttons, "slots": slots, "desc": الوصف})
    await inter.response.send_message(embed=embed("✅ انرسلت لوحة التذاكر", الروم.mention), ephemeral=True)


# ---------- مشرفين التذاكر ----------
db.execute("CREATE TABLE IF NOT EXISTS ticket_supervisors (guild_id INTEGER, slot INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, slot, role_id))")
db.commit()


def supervisor_roles(guild: discord.Guild, slot: int):
    rows = db.execute("SELECT role_id FROM ticket_supervisors WHERE guild_id = ? AND slot = ?", (guild.id, slot)).fetchall()
    return [r for r in (guild.get_role(x[0]) for x in rows) if r]


def is_supervisor(member: discord.Member, slot: int) -> bool:
    ids = {x[0] for x in db.execute("SELECT role_id FROM ticket_supervisors WHERE guild_id = ? AND slot = ?",
                                    (member.guild.id, slot)).fetchall()}
    return any(r.id in ids for r in member.roles)


STAFF_PERMS = dict(view_channel=True, send_messages=True, read_message_history=True,
                   attach_files=True, embed_links=True, send_voice_messages=True)


@bot.tree.command(name="تسطيب_مشرف_التذاكر", description="رتبة مشرف لتذاكر معينة (مشرف مساعدة، مشرف شكاوى، مشرف الجمارك...)")
@app_commands.describe(
    الرتبة="رتبة المشرف",
    الأرقام="أرقام التذاكر اللي يشرف عليها، مثل: 1 أو 2,3",
    حذف="اختر نعم عشان تشيل الرتبة من هالتذاكر",
)
@app_commands.choices(حذف=[app_commands.Choice(name="نعم", value=1)])
async def setup_ticket_supervisor(inter: discord.Interaction, الرتبة: discord.Role, الأرقام: str,
                                  حذف: app_commands.Choice[int] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    slots = sorted({int(x) for x in re.findall(r"\d+", الأرقام.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
                    if 1 <= int(x) <= 20})
    if not slots:
        return await inter.response.send_message(embed=err("اكتب أرقام التذاكر من 1 إلى 20، مثل: 1 أو 2,3"), ephemeral=True)
    for sl in slots:
        if حذف:
            db.execute("DELETE FROM ticket_supervisors WHERE guild_id = ? AND slot = ? AND role_id = ?", (inter.guild.id, sl, الرتبة.id))
        else:
            db.execute("INSERT OR IGNORE INTO ticket_supervisors VALUES (?, ?, ?)", (inter.guild.id, sl, الرتبة.id))
    db.commit()
    rows = db.execute("SELECT slot, role_id FROM ticket_supervisors WHERE guild_id = ? ORDER BY slot", (inter.guild.id,)).fetchall()
    allv = "\n".join(f"• تذكرة {r[0]}: <@&{r[1]}>" for r in rows) or "ما فيه مشرفين."
    await inter.response.send_message(embed=embed("👮 مشرفين التذاكر", (
        f"{'🗑️ انشال' if حذف else '✅ تم تعيين'} {الرتبة.mention} {'من' if حذف else 'على'} التذاكر: {', '.join(map(str, slots))}\n\n"
        f"**كل المشرفين:**\n{allv}\n\nالمشرف يشوف التذكرة دايم حتى بعد ما تنستلم، ويقدر يقفلها.")), ephemeral=True)


# ---------- صور التذاكر ----------
db.execute("CREATE TABLE IF NOT EXISTS ticket_images (guild_id INTEGER, slot INTEGER, data BLOB, filename TEXT, PRIMARY KEY (guild_id, slot))")
db.commit()


def ticket_image_file(guild_id: int, slot: int):
    """صورة التذكرة: صورتها الخاصة ← وإلا صورة كل التذاكر (0) ← وإلا صورة الخط الخضراء"""
    row = (db.execute("SELECT data, filename FROM ticket_images WHERE guild_id = ? AND slot = ?", (guild_id, slot)).fetchone()
           or db.execute("SELECT data, filename FROM ticket_images WHERE guild_id = ? AND slot = 0", (guild_id,)).fetchone()
           or db.execute("SELECT data, filename FROM line_images WHERE guild_id = ?", (guild_id,)).fetchone())
    if row:
        data, fname = bytes(row[0]), (row[1] or "image.png")
    else:
        data, fname = base64.b64decode(DEFAULT_LINE_PNG), "image.png"
    ext = os.path.splitext(fname)[1].lower() if os.path.splitext(fname)[1].lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp") else ".png"
    name = f"ticket{ext}"
    return discord.File(io.BytesIO(data), filename=name), f"attachment://{name}"


@bot.tree.command(name="صورة_التذاكر", description="تحط صورة تطلع داخل التذاكر (لكل التذاكر أو لتذكرة معينة)")
@app_commands.describe(
    صورة="ارفع الصورة (اتركها فاضية عشان تحذف الصورة)",
    رقم_التذكرة="رقم التذكرة من 1 إلى 20 (فاضي = كل التذاكر)",
)
async def set_ticket_image(inter: discord.Interaction, صورة: discord.Attachment = None,
                           رقم_التذكرة: app_commands.Range[int, 1, 20] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    slot = رقم_التذكرة or 0
    where = f"التذكرة رقم {slot}" if slot else "كل التذاكر"
    if صورة is None:
        db.execute("DELETE FROM ticket_images WHERE guild_id = ? AND slot = ?", (inter.guild.id, slot))
        db.commit()
        return await inter.response.send_message(embed=embed("🖼️ صور التذاكر", f"انحذفت صورة {where}."), ephemeral=True)
    if not (صورة.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("لازم تكون صورة."), ephemeral=True)
    if صورة.size > 8 * 1024 * 1024:
        return await inter.response.send_message(embed=err("الصورة كبيرة، خلها أقل من 8 ميقا."), ephemeral=True)
    data = await صورة.read()
    db.execute("INSERT OR REPLACE INTO ticket_images (guild_id, slot, data, filename) VALUES (?, ?, ?, ?)",
               (inter.guild.id, slot, data, صورة.filename))
    db.commit()
    await inter.response.send_message(embed=embed("🖼️ صور التذاكر", f"✅ تم حط الصورة لـ **{where}**.\nتطلع في أي تذكرة تنفتح من الحين."), ephemeral=True)


def ticket_buttons(claim_on: bool = True) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if claim_on:
        view.add_item(discord.ui.Button(label="إستلام التذكرة", style=discord.ButtonStyle.success, custom_id="ticket:claim"))
        view.add_item(discord.ui.Button(label="ترك التذكرة", style=discord.ButtonStyle.secondary, custom_id="ticket:unclaim"))
    view.add_item(discord.ui.Button(label="قفل التذكرة", style=discord.ButtonStyle.danger, custom_id="ticket:close"))
    return view


def is_ticket_staff(member: discord.Member, ttype) -> bool:
    if is_power(member):
        return True
    return ttype is not None and any(r.id == ttype["staff_role"] for r in member.roles)


async def open_ticket(inter: discord.Interaction, slot: int):
    guild = inter.guild
    ttype = db.execute("SELECT * FROM ticket_types WHERE guild_id = ? AND slot = ?", (guild.id, slot)).fetchone()
    if not ttype:
        return await inter.response.send_message(embed=err("التذكرة هذي انحذفت."), ephemeral=True)
    # تذكرة وحدة بس لكل عضو (أي نوع)، عشان ما يسوي سبام
    for row in db.execute("SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ?",
                          (guild.id, inter.user.id)).fetchall():
        if guild.get_channel(row["channel_id"]):
            return await inter.response.send_message(
                embed=err(f"عندك تذكرة مفتوحة: <#{row['channel_id']}>\nاقفلها أول قبل ما تفتح وحدة ثانية ."), ephemeral=True
            )
        db.execute("DELETE FROM tickets WHERE channel_id = ?", (row["channel_id"],))  # روم انحذف بيد
    db.commit()
    key = (guild.id, inter.user.id)
    if key in opening_tickets:  # ضغط الزر أكثر من مرة بسرعة
        return await inter.response.send_message(embed=err("تذكرتك قاعدة تنفتح، انتظر ثانية ."), ephemeral=True)
    opening_tickets.add(key)
    try:
        await _create_ticket(inter, slot, ttype)
    finally:
        opening_tickets.discard(key)


opening_tickets = set()


async def _create_ticket(inter: discord.Interaction, slot: int, ttype):
    guild = inter.guild
    await inter.response.defer(ephemeral=True)
    db.execute("UPDATE ticket_types SET counter = counter + 1 WHERE guild_id = ? AND slot = ?", (guild.id, slot))
    db.commit()
    num = db.execute("SELECT counter FROM ticket_types WHERE guild_id = ? AND slot = ?", (guild.id, slot)).fetchone()["counter"]
    category = guild.get_channel(ttype["category_id"])
    staff = guild.get_role(ttype["staff_role"])
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True,
                                                 embed_links=True, send_voice_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True,
                                              manage_roles=True),
    }
    for sup in supervisor_roles(guild, slot):
        overwrites[sup] = discord.PermissionOverwrite(**STAFF_PERMS)
    if staff:
        overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True,
                                                        attach_files=True, embed_links=True, send_voice_messages=True)
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
    ping = staff.mention if staff and (ttype["ping_staff"] if ttype["ping_staff"] is not None else 1) else ""
    claim_on = bool(ttype["claim_on"] if ttype["claim_on"] is not None else 1)
    f, url = ticket_image_file(guild.id, slot)
    e.set_image(url=url)
    await ch.send(content=f"{inter.user.mention} {ping}", embed=e, view=ticket_buttons(claim_on), file=f)
    await inter.followup.send(embed=embed("✅ انفتحت تذكرتك", ch.mention), ephemeral=True)
    await log(f"{inter.user.mention} فتح تذكرة **{ttype['name']}** {ch.mention}", guild)


async def handle_ticket_button(inter: discord.Interaction, action: str):
    t = db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
    if not t:
        return await inter.response.send_message(embed=err("هذي مو تذكرة مسجلة."), ephemeral=True)
    ttype = db.execute("SELECT * FROM ticket_types WHERE guild_id = ? AND slot = ?", (t["guild_id"], t["slot"])).fetchone()
    staff = is_ticket_staff(inter.user, ttype)

    if action in ("claim", "unclaim") and ttype is not None and ttype["claim_on"] == 0:
        return await inter.response.send_message(embed=err("هذي التذكرة ما فيها استلام."), ephemeral=True)
    if action == "claim":
        if not staff and not is_supervisor(inter.user, t["slot"]):
            return await inter.response.send_message(embed=err("الاستلام للإدارة المسؤولة بس."), ephemeral=True)
        if t["claimed_by"]:
            return await inter.response.send_message(embed=err(f"التذكرة مستلمة من <@{t['claimed_by']}>"), ephemeral=True)
        db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (inter.user.id, inter.channel.id))
        add_points(inter.guild.id, inter.user.id, "admin", "ticket", pts_value(inter.guild.id, "pts_ticket"))
        db.commit()
        await inter.response.send_message(embed=embed("✅ تم استلام التذكرة", f"المسؤول عن التذكرة: {inter.user.mention}"))
        # الإداريين الثانيين ما يشوفون التذكرة بعد الاستلام (المشرفين يشوفونها)
        try:
            await inter.channel.set_permissions(inter.user, overwrite=discord.PermissionOverwrite(**STAFF_PERMS))
            srole = inter.guild.get_role(ttype["staff_role"]) if ttype else None
            if srole:
                await inter.channel.set_permissions(srole, overwrite=discord.PermissionOverwrite(view_channel=False))
        except discord.HTTPException:
            await log(f"⚠️ ما قدرت أخفي التذكرة {inter.channel.mention} عن الإداريين. عطني صلاحية Manage Roles.", inter.guild)

    elif action == "unclaim":
        if t["claimed_by"] != inter.user.id and not is_power(inter.user) and not is_supervisor(inter.user, t["slot"]):
            return await inter.response.send_message(embed=err("بس اللي مستلم التذكرة يقدر يتركها."), ephemeral=True)
        db.execute("UPDATE tickets SET claimed_by = 0 WHERE channel_id = ?", (inter.channel.id,))
        db.commit()
        await inter.response.send_message(embed=embed("↩️ تم ترك التذكرة", "التذكرة الحين متاحة لأي إداري يستلمها."))
        try:
            srole = inter.guild.get_role(ttype["staff_role"]) if ttype else None
            if srole:
                await inter.channel.set_permissions(srole, overwrite=discord.PermissionOverwrite(**STAFF_PERMS))
            old = inter.guild.get_member(t["claimed_by"]) if t["claimed_by"] else None
            if old and old.id != t["owner_id"]:
                await inter.channel.set_permissions(old, overwrite=None)
        except discord.HTTPException:
            pass

    elif action in ("close", "closeyes", "closeno"):
        # مين يقدر يقفل: اللي مستلم التذكرة بس (وإذا التذكرة بدون استلام: الإدارة المسؤولة). صاحب التذكرة ما يقفل.
        claim_on = ttype is None or ttype["claim_on"] != 0
        is_admin = is_power(inter.user) or is_supervisor(inter.user, t["slot"])
        if claim_on:
            if not t["claimed_by"] and not is_admin:
                return await inter.response.send_message(embed=err("لازم أحد من الإدارة يستلم التذكرة أول، واللي يستلمها هو اللي يقفلها."), ephemeral=True)
            if t["claimed_by"] and t["claimed_by"] != inter.user.id and not is_admin:
                return await inter.response.send_message(embed=err(f"بس اللي مستلم التذكرة <@{t['claimed_by']}> يقدر يقفلها."), ephemeral=True)
        elif not staff and not is_admin:
            return await inter.response.send_message(embed=err("القفل للإدارة المسؤولة بس."), ephemeral=True)

        if action == "close":
            v = discord.ui.View(timeout=None)
            v.add_item(discord.ui.Button(label="نعم، اقفل التذكرة", style=discord.ButtonStyle.success, custom_id="ticket:closeyes"))
            v.add_item(discord.ui.Button(label="لا", style=discord.ButtonStyle.secondary, custom_id="ticket:closeno"))
            return await inter.response.send_message(embed=embed("❓ تأكيد القفل", "**هل تم خدمة العضو بأكمل وجه؟**"), view=v)

        if action == "closeno":
            try:
                return await inter.response.edit_message(embed=embed("↩️ تم إلغاء القفل", "التذكرة باقية مفتوحة."), view=None)
            except discord.HTTPException:
                return

        # closeyes
        await inter.response.edit_message(embed=embed("🔒 تم خدمة العضو", "التذكرة بتنقفل بعد 5 ثواني."), view=None)
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
        return False  # برا التذكرة: يكمل للردود التلقائية
    if t["quiz_used"]:
        await message.reply(embed=err("استخدمت `T1` في هذي التذكرة قبل. الاختبار مرة وحدة بس لكل تذكرة."))
        return True
    # T1 داخل أي تذكرة = أسئلة نفس التذكرة (مثلاً تذكرة 11 تجيب أسئلة 11)
    qs = get_questions(message.guild.id, t["slot"]) or get_questions(message.guild.id, n)
    if not qs:
        row = db.execute("SELECT slot FROM quiz_questions WHERE guild_id = ? ORDER BY slot LIMIT 1", (message.guild.id,)).fetchone()
        qs = get_questions(message.guild.id, row["slot"]) if row else []
    if not qs:
        await message.reply(embed=err("ما فيه أسئلة. خل الإدارة تحطها بـ /تحميل_الاسئلة"))
        return True
    db.execute("UPDATE tickets SET quiz_used = 1 WHERE channel_id = ?", (message.channel.id,))
    db.commit()
    state = {"qs": qs, "i": 0, "right": 0, "wrong": []}
    quiz_state[(message.channel.id, message.author.id)] = state
    e, v = quiz_question_view(state)
    await message.channel.send(content=message.author.mention, embed=e, view=v)
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    return True


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
    need = min(config.PASS_MIN, total)
    passed = state["right"] >= need
    if passed:
        await inter.response.edit_message(
            embed=embed("✅ نجحت في الاختبار", f"جاوبت {state['right']} من {total} صح. انتظر الإدارة تفعّلك."), view=None
        )
    else:
        await inter.response.edit_message(
            embed=embed("❌ لم تنجح في الاختبار", f"جاوبت {state['right']} من {total} صح، والمطلوب {need}.", 0x006C35),
            view=None,
        )
        try:
            await inter.user.send(embed=embed(
                "❌ - لم تنجح في الاختبار",
                f"**- عزيزي العضو {inter.user.mention} .**\n\n"
                f"❗ - نُفيدك بأنك لم تتمكن من تجاوز الأختبار الخاص بـ **{config.SERVER_NAME}** , "
                "يجب عليك مُراجعة القوانين لتتمكن من إجتياز الأختبار للمرة القادمة .\n\n"
                f"الدرجة : **{state['right']} / {total}** ( المطلوب {need} )\n\n**( نتمنى لك التوفيق )**",
                0x006C35,
            ))
        except discord.HTTPException:
            pass
    result = embed(
        "📝 نتيجة الاختبار",
        f"العضو: {inter.user.mention}\nالدرجة: **{state['right']} / {total}** (المطلوب {need})\n"
        + ("**✅ ناجح**، الإدارة تقدر تفعّله بـ `-تفعيل`" if passed else "**❌ مرفوض**، انرسل له في الخاص إنه لم ينجح")
        + ("\n\n**الأسئلة اللي غلط فيها:**\n" + "\n".join(f"• {w}" for w in state["wrong"]) if state["wrong"] else ""),
        0x006C35 if passed else 0x006C35,
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
    if not (is_power(message.author) or
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
        0x006C35 if clean else 0x006C35,
    )
    dm = embed(
        "🛃 - تم تفتيشك",
        f"**- عزيزي {member.mention} .**\n\n"
        f"✈️ - تم تفتيشك من قبل ( {message.author.mention} ) في مطار **{config.SERVER_NAME}** .\n\n"
        f"**النتيجة :** {status}\n"
        + (f"💵 - تم سحب **{get_setting(gid, 'inspect_fee') or config.INSPECT_FEE}** {config.CURRENCY} رسوم التفتيش .\n\n**( نتمنى لك رحلة سعيدة )**"
           if clean else "\n🚫 - لا يمكنك دخول الرحلة , يجب عليك التوظف أولاً .\n\n**( نتمنى لك التوفيق )**"),
        0x006C35 if clean else 0x006C35,
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
              0x006C35)
    await message.reply(embed=e)
    try:
        await member.send(embed=embed("🔇 - تم إسكاتك", f"تم إسكاتك في **{config.SERVER_NAME}** لمدة **{fmt_minutes(mins)}**\n**السبب :** {reason}", 0x006C35))
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
    prison_role = get_setting(message.guild.id, "role_prison")
    allowed = message.author.id == message.guild.owner_id or (prison_role and any(r.id == prison_role for r in message.author.roles))
    if not allowed:
        return await message.reply(embed=err("الحظر لمشرف السجناء بس." if prison_role else
                                             "رتبة مشرف السجناء ما تحددت. حددها بـ /تسطيب_رتب"))
    parts = message.content.split()
    raw = parts[1].strip("<@!>") if len(parts) > 1 else ""
    if not raw.isdigit():
        return await message.reply(embed=err("الاستخدام: `-حظر ايدي_العضو السبب`" if ban else "الاستخدام: `-فك_حظر ايدي_العضو`"))
    uid = int(raw)
    reason = " ".join(parts[2:]) or "بدون سبب"
    if uid in (message.author.id, message.guild.owner_id, bot.user.id if bot.user else 0):
        return await message.reply(embed=err("ما تقدر تحظر هذا الشخص."))
    member = message.guild.get_member(uid)
    if ban and member and staff_level(member) > 0 and staff_level(member) >= staff_level(message.author):
        return await message.reply(embed=err("رتبته مثلك أو أعلى منك."))
    try:
        if ban:
            if member:
                try:
                    await member.send(embed=embed("⛔ - تم حظرك", f"تم حظرك من **{config.SERVER_NAME}**\n**السبب :** {reason}", 0x006C35))
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
                                    + f"**بواسطة :** {message.author.mention}", 0x006C35 if ban else 0x006C35))
    await log(f"{message.author.mention} {'حظر' if ban else 'فك حظر'} `{uid}` {reason if ban else ''}", message.guild)


# ============================================================
# التفعيل: -تفعيل @العضو ايدي_سوني
# ============================================================
def can_activate(member: discord.Member) -> bool:
    if is_power(member):
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

    # شيل رتبة (عضو غير رسمي): من التسطيب، وإذا ما تحددت يدور عليها بالاسم
    removed_note = ""
    un_id = get_setting(message.guild.id, "role_unofficial")
    un_role = message.guild.get_role(un_id) if un_id else None
    if un_role is None:
        un_role = discord.utils.find(lambda r: r.name.replace(" ", "") in ("عضوغيررسمي", "غيررسمي"), message.guild.roles)
    if un_role and un_role in member.roles:
        try:
            await member.remove_roles(un_role, reason=f"تفعيل بواسطة {message.author}")
            removed_note = f"\n**انشالت :** {un_role.mention}"
        except discord.Forbidden:
            removed_note = f"\n⚠️ ما قدرت أشيل {un_role.mention}، خل رتبة البوت فوقها."

    db.execute(
        "INSERT INTO activations (guild_id, user_id, sony_id, by_id, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET sony_id = excluded.sony_id, by_id = excluded.by_id, created_at = excluded.created_at",
        (message.guild.id, member.id, sony_id, message.author.id, now().isoformat()),
    )
    db.commit()
    e = embed(
        "✅ - تم التفعيل",
        f"**العضو :** {member.mention}\n**ايدي العضو :** `{member.id}`\n**ايدي سوني :** `{sony_id}`\n"
        f"**الرتب :** {' '.join(r.mention for r in roles)}{removed_note}\n**بواسطة :** {message.author.mention}",
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
ADMIN_CAT_ORDER = ["publish", "activate", "hire", "ticket", "resign"]
ADMIN_CAT_EMOJI = {"publish": "📢", "activate": "✅", "hire": "💼", "ticket": "🎫", "resign": "📤", "manual": "✏️"}
ADMIN_CAT_DEFAULT = {"publish": "نقاط النشر", "activate": "نقاط التفعيل", "hire": "نقاط التوظيف",
                     "ticket": "نقاط استلام التكتات", "resign": "نقاط الاستقالات", "manual": "نقاط يدوية"}
ADMIN_PTS_KEY = {"publish": "pts_publish", "activate": "pts_activate", "hire": "pts_hire", "ticket": "pts_ticket", "resign": "pts_resign"}


def admin_label(gid: int, cat: str, with_emoji: bool = True) -> str:
    row = db.execute("SELECT label FROM point_labels WHERE guild_id = ? AND category = ?", (gid, cat)).fetchone()
    name = row["label"] if row else ADMIN_CAT_DEFAULT.get(cat, cat)
    return f"{ADMIN_CAT_EMOJI.get(cat, '')} {name}".strip() if with_emoji else name


def cat_label(gid: int, kind: str, cat: str) -> str:
    return admin_label(gid, cat) if kind == "admin" else POLICE_CATS.get(cat, cat)
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
    if is_power(member):
        return True
    ids = {r.id for r in member.roles}
    keys = ["role_admin"] + [k for k, _ in RANK_KEYS]
    return any(get_setting(member.guild.id, k) in ids for k in keys if get_setting(member.guild.id, k))


def frame_file(gid: int, kind: str):
    if kind != "admin":  # الإطار للإدارة بس
        return None
    row = db.execute("SELECT filename, data FROM assets WHERE guild_id = ? AND key = 'frame_admin'", (gid,)).fetchone()
    if not row:
        return None
    return discord.File(io.BytesIO(row["data"]), filename=row["filename"])


def points_card(guild: discord.Guild, member: discord.Member, kind: str):
    cats = ({c: admin_label(guild.id, c) for c in ADMIN_CAT_ORDER + ["manual"]} if kind == "admin" else POLICE_CATS)
    b = points_breakdown(guild.id, member.id, kind)
    total = sum(b.values())
    rank = points_rank(guild.id, member.id, kind)
    title = "📊 نقاط الإدارة" if kind == "admin" else "🚓 نقاط الشرطة"
    e = discord.Embed(title=title, color=0x006C35 if kind == "admin" else 0x006C35, timestamp=now())
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
        title = f"🏆 أفضل 10 | {cat_label(guild.id, kind, category)}"
    e = discord.Embed(title=title, description="\n".join(lines) or "ما فيه نقاط للحين.", color=0x006C35, timestamp=now())
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


def admin_menu_view(gid: int = 0) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    options = [
        discord.SelectOption(label="نقاطي", value="me", emoji="📊"),
        discord.SelectOption(label="نقاط شخص معين", value="user", emoji="🔎"),
        discord.SelectOption(label="توب أفضل عشرة", value="top", emoji="🏆"),
    ]
    v.add_item(discord.ui.Select(custom_id="pts:admin", placeholder="- اختر من القائمة .", options=options))
    return v


MDT_MENU = [
    ("تسجيل دخول", "in", "🟢"),
    ("تسجيل خروج", "out", "🔴"),
    ("المتواجدين بالدوام", "onduty", "👮"),
    ("بحث عن مواطن", "search", "🔎"),
    ("قبض على مجرم", "arrest", "🚔"),
    ("مخالفة", "fine", "🧾"),
    ("نقاطي", "me", "📊"),
    ("نقاط شخص معين", "user", "👤"),
    ("توب أفضل عشرة", "top", "🏆"),
    ("إعادة الاختيار", "reset", "🔄"),
]


def mdt_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Select(custom_id="mdt:menu", placeholder="إفتح لاختيار امر", options=[
        discord.SelectOption(label=label, value=val, emoji=emoji) for label, val, emoji in MDT_MENU]))
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
        recs = db.execute("SELECT * FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 10", (member.id,)).fetchall()
        fines_ = db.execute("SELECT * FROM fines WHERE user_id = ? AND paid = 0", (member.id,)).fetchall()
        e = embed("💻 MDT - ملف المواطن", f"**العضو :** {member.mention}\n**الايدي :** `{member.id}`\n**الوظيفة :** {p['job']}")
        e.set_thumbnail(url=member.display_avatar.url)
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
        e = embed("🚔 - تم القبض", color=0x006C35)
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
                0x006C35,
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
        e = embed("🚨 مخالفة جديدة", color=0x006C35)
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
            await inter.message.edit(view=admin_menu_view(guild.id))
        except discord.HTTPException:
            pass
        return

    if cid.startswith("pts:again:"):
        kind = cid.split(":")[2]
        if kind == "admin":
            return await inter.response.send_message(embed=embed("📊 نقاط الإدارة", "اختر من القائمة ."), view=admin_menu_view(inter.guild.id), ephemeral=True)
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
        view = admin_menu_view(inter.guild.id)
    elif النوع.value == "bank":
        e = embed("🏦 - بنك سعودي تايم", f"**- مرحبا بك في بنك {config.SERVER_NAME} .**\n\n"
                  "اختر من القائمة اللي تحت .", 0x006C35)
        view = bank_view()
    elif النوع.value == "units":
        e = embed("🚓 - اليونتات", f"**- مرحبا بك عزيزي العسكري في {config.SERVER_NAME} .**\n\n"
                  "اضغط على القطاع حقك وبيطلع لك رقم اليونت ويتغيّر اسمك تلقائي .\n\n"
                  "🔵 **LSPD** ← يونت يبدأ بـ **D-**\n⚫ **SWAT** ← يونت يبدأ بـ **S-**", 0x006C35)
        view = units_view()
    else:
        e = embed("💻 - MDT الشرطة", f"**- مرحبا بك عزيزي العسكري في نظام {config.SERVER_NAME} .**\n\n"
                  "🟢 سجّل دخول أول ما تبدأ دوامك، و 🔴 سجّل خروج إذا خلصت .", 0x006C35)
        view = mdt_view()
    try:
        await الروم.send(embed=e, view=view)
    except discord.Forbidden:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    await inter.response.send_message(embed=embed("✅ انرسلت اللوحة", الروم.mention), ephemeral=True)


@bot.tree.command(name="تسطيب_الاطار", description="رفع صورة الإطار اللي تطلع تحت نقاط الإدارة")
async def setup_frame(inter: discord.Interaction, الصورة: discord.Attachment):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if not (الصورة.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("لازم تكون صورة."), ephemeral=True)
    if الصورة.size > 7_000_000:
        return await inter.response.send_message(embed=err("الصورة كبيرة، خلها أقل من 7 ميقا."), ephemeral=True)
    kind = "admin"
    data = await الصورة.read()
    ext = (الصورة.filename.rsplit(".", 1)[-1] or "png").lower()
    db.execute(
        "INSERT INTO assets (guild_id, key, filename, data) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, key) DO UPDATE SET filename = excluded.filename, data = excluded.data",
        (inter.guild.id, f"frame_{kind}", f"frame_{kind}.{ext}", data),
    )
    db.commit()
    await inter.response.send_message(
        embed=embed("✅ انحفظ الإطار", "إطار نقاط الإدارة ."),
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


def admin_points_text(gid: int) -> str:
    return "\n".join(f"• {admin_label(gid, c)} : **{pts_value(gid, ADMIN_PTS_KEY[c])}** نقطة" for c in ADMIN_CAT_ORDER)


@bot.tree.command(name="تسطيب_نقاط_الادارة", description="تغيير اسم نوع من نقاط الإدارة وكم نقطة ياخذ")
@app_commands.describe(النوع="نوع النقاط", الاسم_الجديد="الاسم اللي يطلع في البطاقة والتوب (اختياري)",
                       العدد="كم نقطة ياخذ عليها (اختياري)")
@app_commands.choices(النوع=[
    app_commands.Choice(name="النشر", value="publish"), app_commands.Choice(name="التفعيل", value="activate"),
    app_commands.Choice(name="التوظيف", value="hire"), app_commands.Choice(name="استلام التكتات", value="ticket"),
    app_commands.Choice(name="الاستقالات", value="resign"),
])
async def setup_admin_points(inter: discord.Interaction, النوع: app_commands.Choice[str] = None,
                             الاسم_الجديد: app_commands.Range[str, 1, 40] = None,
                             العدد: app_commands.Range[int, 0, 1000] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    if النوع and الاسم_الجديد:
        db.execute("INSERT INTO point_labels (guild_id, category, label) VALUES (?, ?, ?) "
                   "ON CONFLICT(guild_id, category) DO UPDATE SET label = excluded.label", (gid, النوع.value, الاسم_الجديد.strip()))
        db.commit()
    if النوع and العدد is not None:
        set_setting(gid, ADMIN_PTS_KEY[النوع.value], العدد)
    await inter.response.send_message(embed=embed(
        "📊 نقاط الإدارة", admin_points_text(gid) + "\n\nبعد ما تغيّر الأسماء، أرسل لوحة النقاط من جديد بـ /ارسال_لوحة ."), ephemeral=True)


@bot.tree.command(name="تسطيب_نقاط_الشرطة", description="كم نقطة ياخذ العسكري على كل شي")
@app_commands.describe(القبض="نقاط القبض على مجرم (الافتراضي 3)", المخالفة="نقاط المخالفة (الافتراضي 1)",
                       دقائق_الدوام="كل كم دقيقة دوام = نقطة (الافتراضي 30)")
async def setup_police_points(inter: discord.Interaction, القبض: app_commands.Range[int, 0, 1000] = None,
                              المخالفة: app_commands.Range[int, 0, 1000] = None,
                              دقائق_الدوام: app_commands.Range[int, 1, 1440] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    for key, val in (("pts_arrest", القبض), ("pts_fine", المخالفة), ("pts_duty_min", دقائق_الدوام)):
        if val is not None:
            set_setting(gid, key, val)
    await inter.response.send_message(embed=embed("🚓 نقاط الشرطة", (
        f"🚔 القبض : **{pts_value(gid, 'pts_arrest')}** نقطة\n🧾 المخالفة : **{pts_value(gid, 'pts_fine')}** نقطة\n"
        f"🕒 نقطة كل **{pts_value(gid, 'pts_duty_min')}** دقيقة دوام"), 0x006C35), ephemeral=True)


async def _edit_points(inter: discord.Interaction, kind: str, member: discord.Member, amount: int):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    add_points(inter.guild.id, member.id, kind, "manual", amount)
    total = sum(points_breakdown(inter.guild.id, member.id, kind).values())
    name = "نقاط الإدارة" if kind == "admin" else "نقاط الشرطة"
    await inter.response.send_message(
        embed=embed(f"✏️ تم تعديل {name}", f"{member.mention}: {'+' if amount > 0 else ''}{amount}\nالمجموع الحين: **{total}**"),
        ephemeral=True)
    await log(f"{inter.user.mention} عدّل {name} لـ {member.mention}: {amount}", inter.guild)


@bot.tree.command(name="تعديل_نقاط_الادارة", description="إضافة أو خصم نقاط إدارة")
@app_commands.describe(العدد="موجب للإضافة، سالب للخصم (مثال: -5)")
async def edit_admin_points(inter: discord.Interaction, العضو: discord.Member, العدد: app_commands.Range[int, -100000, 100000]):
    await _edit_points(inter, "admin", العضو, العدد)


@bot.tree.command(name="تعديل_نقاط_الشرطة", description="إضافة أو خصم نقاط شرطة")
@app_commands.describe(العدد="موجب للإضافة، سالب للخصم (مثال: -5)")
async def edit_police_points(inter: discord.Interaction, العضو: discord.Member, العدد: app_commands.Range[int, -100000, 100000]):
    await _edit_points(inter, "police", العضو, العدد)


async def _reset_points(inter: discord.Interaction, kind: str, member):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if member:
        db.execute("DELETE FROM points_log WHERE guild_id = ? AND kind = ? AND user_id = ?", (inter.guild.id, kind, member.id))
    else:
        db.execute("DELETE FROM points_log WHERE guild_id = ? AND kind = ?", (inter.guild.id, kind))
    db.commit()
    name = "نقاط الإدارة" if kind == "admin" else "نقاط الشرطة"
    await inter.response.send_message(embed=embed("🗑️ تم التصفير", f"{name} لـ {member.mention if member else 'الكل'}"), ephemeral=True)
    await log(f"{inter.user.mention} صفّر {name} لـ {member.mention if member else 'الكل'}", inter.guild)


@bot.tree.command(name="تصفير_نقاط_الادارة", description="تصفير نقاط الإدارة للكل أو لعضو")
async def reset_admin_points(inter: discord.Interaction, العضو: discord.Member = None):
    await _reset_points(inter, "admin", العضو)


@bot.tree.command(name="تصفير_نقاط_الشرطة", description="تصفير نقاط الشرطة للكل أو لعضو")
async def reset_police_points(inter: discord.Interaction, العضو: discord.Member = None):
    await _reset_points(inter, "police", العضو)


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
    register_panel(inter.guild.id, "apps", الروم.id, {"desc": الوصف})
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
        e = discord.Embed(title=f"📝 تقديم جديد - {t['name']}", color=0x006C35, timestamp=now())
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
                    0x006C35,
                ))
        except discord.HTTPException:
            pass
    result = (f"✅ **مقبول** بواسطة {inter.user.mention}" if accepted else
              f"❌ **مرفوض** بواسطة {inter.user.mention}" + (f"\nالسبب: {reason}" if reason else ""))
    try:
        e = message.embeds[0] if message.embeds else embed("📝 تقديم")
        e.color = 0x006C35 if accepted else 0x006C35
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
    if name in ("قيم", "تفعيل", "تفتيش", "استقالة", "استقاله", "خط", "فت", "فتح", "قف", "قفل", "استرجاع", "ايموجي", "إيموجي", "ايموجيات", "اسم", "ر", "نسخ_من", "فحص", "بنق"):
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
            0x006C35,
        )
        await inter.response.edit_message(embed=e, view=None)
        await role_update_post(guild, e)
        try:
            await self.member.send(embed=embed("📤 - تمت استقالتك", f"تمت استقالتك من القطاع **{SECTORS[sector]}** في **{config.SERVER_NAME}** .", 0x006C35))
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
UNIT_TAG = re.compile(r"(^[\u200e\u200f\s]*[DS]-\d+\s*\|\s*)|(\s*\|\s*[DS]-\d+\s*$)|[\u200e\u200f]")


def units_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="LSPD", emoji="🔵", style=discord.ButtonStyle.primary, custom_id="unit:lspd"))
    v.add_item(discord.ui.Button(label="SWAT", emoji="⚫", style=discord.ButtonStyle.secondary, custom_id="unit:swat"))
    return v


def unit_nick(member: discord.Member, code: str) -> str:
    base = UNIT_TAG.sub("", member.display_name).strip() or member.name
    # اليونت آخر الاسم وعلى اليمين دايم (حتى لو الاسم عربي)
    base = base[:32 - len(code) - 4]
    return f"\u200e{base} | {code}"


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
    if not (is_power(inter.user) or any(r.id == role_id for r in inter.user.roles)):
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
    await inter.response.send_message(embed=embed(f"🚓 يونت {u['label']}", text, 0x006C35), ephemeral=True)
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
    """صاحب السيرفر أو الرتبة الأونرية"""
    return inter.guild is not None and (inter.user.id == inter.guild.owner_id or has_owner_role(inter.user))


def get_account(uid: int):
    return db.execute("SELECT * FROM bank_accounts WHERE user_id = ?", (uid,)).fetchone()


def new_iban() -> str:
    """آيبان قصير: 4 أرقام (ولو امتلت كلها نصير 5)"""
    for digits in (4, 5, 6):
        for _ in range(200):
            iban = str(random.randint(10 ** (digits - 1), 10 ** digits - 1))
            if not db.execute("SELECT 1 FROM bank_accounts WHERE iban = ?", (iban,)).fetchone():
                return iban
    raise RuntimeError("ما لقيت آيبان فاضي")


def fmt_iban(iban: str) -> str:
    return iban


def ensure_account(uid: int):
    """يفتح حساب بنكي تلقائي لو ما عنده"""
    acc = get_account(uid)
    if acc:
        return acc
    db.execute("INSERT OR IGNORE INTO bank_accounts (user_id, iban, created_at) VALUES (?, ?, ?)", (uid, new_iban(), now().isoformat()))
    db.commit()
    return get_account(uid)


# الحسابات القديمة اللي آيبانها طويل نحولها لـ 4 أرقام
for _row in db.execute("SELECT user_id, iban FROM bank_accounts").fetchall():
    if len(_row["iban"]) > 6:
        db.execute("UPDATE bank_accounts SET iban = ? WHERE user_id = ?", (new_iban(), _row["user_id"]))
db.commit()


def active_loan(uid: int):
    return db.execute("SELECT * FROM loans WHERE user_id = ? AND status IN ('pending', 'active') ORDER BY id DESC",
                      (uid,)).fetchone()


BANK_MENU = [
    ("الكاش", "cash", "💵"),
    ("حسابي البنكي", "me", "💳"),
    ("تحويل مبلغ", "transfer", "🔁"),
    ("سحب الأموال", "withdraw", "📤"),
    ("إيداع الأموال", "deposit", "📥"),
    ("طلب قرض", "loan", "📝"),
    ("دفع القروض", "payloan", "💸"),
    ("إعادة الاختيار", "reset", "🔄"),
]


def bank_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Select(custom_id="bank:menu", placeholder="إفتح لاختيار امر", options=[
        discord.SelectOption(label=label, value=val, emoji=emoji) for label, val, emoji in BANK_MENU]))
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
    target = discord.ui.TextInput(label="رقم الآيبان أو ايدي العضو", placeholder="مثال: 4821 أو ايدي العضو", max_length=40)
    amount = discord.ui.TextInput(label="المبلغ", placeholder="مثال: 5000", max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        amt = parse_amount(self.amount.value)
        if not amt:
            return await inter.response.send_message(embed=err("اكتب المبلغ رقم صحيح."), ephemeral=True)
        raw = self.target.value.strip().replace(" ", "").upper().strip("<@!>")
        raw = raw[2:] if raw.startswith("SA") else raw
        raw = raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        acc = None
        if raw.isdigit() and len(raw) <= 6:
            acc = db.execute("SELECT * FROM bank_accounts WHERE iban = ?", (raw,)).fetchone()
        elif raw.isdigit():
            acc = get_account(int(raw)) or (ensure_account(int(raw)) if inter.guild.get_member(int(raw)) else None)
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
        e = embed("📝 طلب قرض جديد", color=0x006C35)
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
        return await inter.response.send_message(embed=err("صار خطأ، جرّب مرة ثانية."), ephemeral=True)
    acc = ensure_account(uid)
    if action == "create":  # الحساب ينفتح تلقائي، فزر إنشاء حساب القديم يعرض الحساب
        action = "me"
    if action == "me":
        loan = active_loan(uid)
        e = embed("💳 حسابي البنكي")
        e.set_thumbnail(url=inter.user.display_avatar.url)
        e.add_field(name="الاسم", value=inter.user.display_name)
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
        e.color = 0x006C35 if accepted else 0x006C35
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
                0x006C35 if accepted else 0x006C35,
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
        if i == OFFICER_FROM:
            lines.append("\n**🎖️ الضباط :**")
        lines.append(f"• {name}: {('<@&%d>' % rid) if rid else 'ما تحددت'}")
    lines.insert(0, "**🪖 الأفراد :**")
    await inter.response.send_message(embed=embed("👮 رتب الشرطة", "\n".join(lines) + "\n\n" + salaries_text(gid)), ephemeral=True)


OFFICER_FROM = POLICE_RANKS.index("ملازم")  # من ملازم وفوق = ضباط، وتحته = أفراد


def rank_group(i: int) -> str:
    return "officers" if i >= OFFICER_FROM else "enlisted"


GROUP_NAME = {"officers": "الضباط", "enlisted": "الأفراد"}


def salaries_text(gid: int) -> str:
    return (f"🎖️ **الضباط** (ملازم ← فريق أول) : {money(get_setting(gid, 'sal_officers'))}\n"
            f"🪖 **الأفراد** (مستجد ← رئيس رقباء) : {money(get_setting(gid, 'sal_enlisted'))}")


@bot.tree.command(name="تسطيب_الرواتب", description="راتب الضباط وراتب الأفراد (لصاحب السيرفر بس)")
@app_commands.describe(الضباط="راتب الضباط (من ملازم إلى فريق أول)", الأفراد="راتب الأفراد (من مستجد إلى رئيس رقباء)")
async def setup_salaries(inter: discord.Interaction, الضباط: app_commands.Range[int, 0, 100_000_000] = None,
                         الأفراد: app_commands.Range[int, 0, 100_000_000] = None):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("الرواتب لصاحب السيرفر بس."), ephemeral=True)
    gid = inter.guild.id
    if الضباط is not None:
        set_setting(gid, "sal_officers", الضباط)
    if الأفراد is not None:
        set_setting(gid, "sal_enlisted", الأفراد)
    await inter.response.send_message(embed=embed("💰 الرواتب", salaries_text(gid)), ephemeral=True)


def member_salary(member: discord.Member):
    """يرجع (الرتبة والفئة، الراتب) حسب أعلى رتبة شرطة معه"""
    gid = member.guild.id
    ids = {r.id for r in member.roles}
    for i in range(len(POLICE_RANKS) - 1, -1, -1):
        rid = get_setting(gid, f"prank_{i}")
        if rid and rid in ids:
            group = rank_group(i)
            sal = get_setting(gid, f"sal_{group}")
            return (f"{POLICE_RANKS[i]} - {GROUP_NAME[group]}", sal) if sal else (None, 0)
    return None, 0


@bot.tree.command(name="صرف_الرواتب", description="صرف رواتب الضباط والأفراد (لصاحب السيرفر بس)")
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


# ============================================================
# القوانين: لوحة فيها بنر + منيو أقسام
# ============================================================
DEFAULT_RULES = [
    ("📜", "القوانين العامة", [
        "القانون الذهبي : عدم رد الخطأ بالخطأ , إذا أحد غلط عليك افتح تذكرة ولا ترد عليه .",
        "الرول بلاي : هو تقمص الشخصية بالأقوال والأفعال , ويمنع الخروج من الشخصية أثناء الرول .",
        "يُمنع القتل العشوائي ( RDM ) بدون سبب رول واضح .",
        "يُمنع الصدم العشوائي ( VDM ) بالسيارات بدون سبب رول .",
        "تقدير الحياة ( LAR ) : يجب الخوف على حياتك وحياة غيرك , وعدم المخاطرة الغير واقعية .",
        "الحاجز السمعي : الشخص لا يسمع إذا كان بينه وبين الآخر جدار أو حاجز أو مسافة .",
        "يُمنع الميتا قيمنق : استخدام معلومات من خارج الرول ( ديسكورد , بث ) داخل الرول .",
        "يُمنع الباور قيمنق : إجبار شخص على رول بدون ما تعطيه فرصة يرد .",
        "يُمنع الإزعاج أو تشغيل الأغاني داخل الرول .",
        "احترام الجميع واجب , ويُمنع السب والشتم والعنصرية بشكل نهائي .",
    ]),
    ("🔫", "قوانين الإجرام", [
        "يُمنع الخطف أو القتل في المناطق الآمنة ( المستشفى , مركز الشرطة , الملكية ) .",
        "يُمنع مداهمة مركز الشرطة , إلا في حال تحرير خويك من داخل المركز .",
        "يُسمح بأخذ أسلحة من مركز الشرطة فقط في حال المداهمة ومعك عدد .",
        "يُسمح بسرقة سيارات الشرطة فقط إذا معك عدد وحاوطت العسكري وهو في سيارته .",
        "يُسمح بالسرقة حتى لو ما كنت عصابة , بشرط يكون فيه رول واضح .",
        "يُمنع الخطف أثناء مداهمة التحرير .",
        "الرهينة ما تقدر تهرب في نص التفاوض .",
        "يُمنع مقاومة شخصين أو أكثر إذا كانوا مصوبين عليك .",
        "يُمنع التوجه لأي مقر أول 10 دقائق من بداية الرستارت .",
        "يُمنع قتل المواطن أو المخرب نفسه في وقت الإعصار .",
    ]),
    ("🚓", "قوانين القيادة والمطاردات", [
        "إجبارية التوقف بعد انفجار 3 كفرات .",
        "يُمنع التفحيط في الأماكن التالية : الملكية , المستشفى , مركز الشرطة .",
        "يُمنع طلوع الجبال بالسيارات الصغيرة .",
        "أول ما يبدأ القيم توقف أول 10 ثواني وبعدها تتحرك .",
        "إذا سقطت تنسى آخر 5 دقايق من الرول .",
        "إذا سقطت وتحللت تنسى آخر 15 دقيقة .",
        "يُمنع الهروب من المطاردة عن طريق الخروج من اللعبة .",
        "يُمنع استخدام الثغرات أو القلتشات في المطاردة .",
        "يجب التوقف عند إشارة الشرطة إذا ما كان عندك رول هروب واضح .",
        "يُمنع صدم سيارات الشرطة عمداً بدون سبب رول .",
    ]),
]


def get_rule_sections(gid: int):
    return db.execute("SELECT * FROM rule_sections WHERE guild_id = ? ORDER BY idx", (gid,)).fetchall()


def rules_menu(gid: int) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    opts = [discord.SelectOption(label=r["name"][:100], value=str(r["idx"]), emoji=r["emoji"] or None)
            for r in get_rule_sections(gid)][:25]
    v.add_item(discord.ui.Select(custom_id="rules:open", placeholder="اختر من القائمة", options=opts))
    return v


class RuleSectionModal(discord.ui.Modal, title="📜 قسم قوانين"):
    content = discord.ui.TextInput(
        label="القوانين", style=discord.TextStyle.paragraph, max_length=4000,
        placeholder="اكتب كل قانون في سطر، والبوت يرقّمها لحاله",
    )

    def __init__(self, name: str, emoji: str, idx: int = None, current: str = None):
        super().__init__()
        self.name, self.emoji, self.idx = name, emoji, idx
        if current:
            self.content.default = current

    async def on_submit(self, inter: discord.Interaction):
        gid = inter.guild.id
        if self.idx is None:
            row = db.execute("SELECT COALESCE(MAX(idx), 0) AS m FROM rule_sections WHERE guild_id = ?", (gid,)).fetchone()
            self.idx = row["m"] + 1
        db.execute(
            "INSERT INTO rule_sections (guild_id, idx, name, emoji, content) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, idx) DO UPDATE SET name = excluded.name, emoji = excluded.emoji, content = excluded.content",
            (gid, self.idx, self.name, self.emoji, self.content.value),
        )
        db.commit()
        n = len([l for l in self.content.value.splitlines() if l.strip()])
        await inter.response.send_message(embed=embed(
            "✅ انحفظ القسم", f"**{self.name}** ({n} قانون)\n\nأرسل اللوحة من جديد بـ /ارسال_القوانين عشان يطلع في المنيو ."), ephemeral=True)


@bot.tree.command(name="اضافة_قوانين", description="إضافة أو تعديل قسم قوانين (يطلع في منيو القوانين)")
@app_commands.describe(اسم_القسم="مثل: القوانين العامة، قوانين الإجرام", الايموجي="ايموجي جنب اسم القسم (اختياري)")
async def add_rules(inter: discord.Interaction, اسم_القسم: app_commands.Range[str, 1, 80], الايموجي: str = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    old = db.execute("SELECT * FROM rule_sections WHERE guild_id = ? AND name = ?", (inter.guild.id, اسم_القسم.strip())).fetchone()
    if not old and len(get_rule_sections(inter.guild.id)) >= 25:
        return await inter.response.send_message(embed=err("وصلت الحد: 25 قسم."), ephemeral=True)
    await inter.response.send_modal(RuleSectionModal(
        اسم_القسم.strip(), (الايموجي or (old["emoji"] if old else "") or "").strip()[:30],
        old["idx"] if old else None, old["content"] if old else None,
    ))


@bot.tree.command(name="حذف_قوانين", description="حذف قسم قوانين")
async def delete_rules(inter: discord.Interaction, اسم_القسم: str):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    cur = db.execute("DELETE FROM rule_sections WHERE guild_id = ? AND name = ?", (inter.guild.id, اسم_القسم))
    db.commit()
    if not cur.rowcount:
        return await inter.response.send_message(embed=err("ما لقيت هالقسم."), ephemeral=True)
    await inter.response.send_message(embed=embed("🗑️ انحذف القسم", اسم_القسم), ephemeral=True)


@delete_rules.autocomplete("اسم_القسم")
@add_rules.autocomplete("اسم_القسم")
async def rules_autocomplete(inter: discord.Interaction, current: str):
    return [app_commands.Choice(name=r["name"][:100], value=r["name"]) for r in get_rule_sections(inter.guild.id)
            if current in r["name"]][:25]


@bot.tree.command(name="تحميل_القوانين", description="يحط 30 قانون أرض جاهزة في 3 أقسام (تقدر تعدّلها بعدين)")
async def load_default_rules(inter: discord.Interaction):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    for emoji, name, rules in DEFAULT_RULES:
        old = db.execute("SELECT idx FROM rule_sections WHERE guild_id = ? AND name = ?", (gid, name)).fetchone()
        idx = old["idx"] if old else (db.execute("SELECT COALESCE(MAX(idx), 0) AS m FROM rule_sections WHERE guild_id = ?",
                                                 (gid,)).fetchone()["m"] + 1)
        db.execute(
            "INSERT INTO rule_sections (guild_id, idx, name, emoji, content) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, idx) DO UPDATE SET name = excluded.name, emoji = excluded.emoji, content = excluded.content",
            (gid, idx, name, emoji, "\n".join(rules)),
        )
    db.commit()
    total = sum(len(r) for _, _, r in DEFAULT_RULES)
    await inter.response.send_message(embed=embed(
        "✅ انحطت القوانين", f"انحط **{total} قانون** في {len(DEFAULT_RULES)} أقسام .\n\n"
        "تقدر تعدّل أي قسم بـ **/اضافة_قوانين** (اختر اسمه)، وبعدها أرسل اللوحة بـ **/ارسال_القوانين** ."), ephemeral=True)


class RulesPanelModal(discord.ui.Modal, title="📜 لوحة القوانين"):
    title_in = discord.ui.TextInput(label="العنوان", default="قوانين سعودي تايم", max_length=256)
    body_in = discord.ui.TextInput(
        label="الكلام اللي فوق المنيو", style=discord.TextStyle.paragraph, max_length=4000,
        default=("- تعرف علينا .\n\n📜 - نُرحب بكم في سيرفر سعودي تايم , هذه اللوحة فيها كل قوانين الأرض "
                 "اللي لازم يعرفها كل مواطن قبل ما يدخل الرول .\n\n"
                 "⚖️ - الالتزام بالقوانين واجب على الجميع , ومخالفتها تعرّضك للعقوبة .\n\n"
                 "👇 - اختر القسم من القائمة اللي تحت ويطلع لك قوانينه ."),
    )

    def __init__(self, channel: discord.TextChannel, banner: discord.Attachment):
        super().__init__()
        self.channel, self.banner = channel, banner

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        e = discord.Embed(title=self.title_in.value, description=self.body_in.value, color=0x006C35)
        e.set_footer(text=config.SERVER_NAME)
        kwargs = {"embed": e, "view": rules_menu(inter.guild.id)}
        if self.banner:
            try:
                f = await self.banner.to_file()
                e.set_image(url=f"attachment://{f.filename}")
                kwargs["file"] = f
            except discord.HTTPException:
                pass
        try:
            await self.channel.send(**kwargs)
        except discord.HTTPException:
            return await inter.followup.send(embed=err(f"ما قدرت أرسل في {self.channel.mention}. (أو فيه ايموجي غلط في قسم)"), ephemeral=True)
        await inter.followup.send(embed=embed("✅ انرسلت لوحة القوانين", self.channel.mention), ephemeral=True)


@bot.tree.command(name="ارسال_القوانين", description="إرسال لوحة القوانين في روم")
@app_commands.describe(الروم="الروم اللي تنرسل فيه اللوحة", البنر="صورة البنر اللي فوق (اختياري)")
async def send_rules_panel(inter: discord.Interaction, الروم: discord.TextChannel, البنر: discord.Attachment = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    if not get_rule_sections(inter.guild.id):
        return await inter.response.send_message(embed=err("ما فيه قوانين. استخدم /تحميل_القوانين أو /اضافة_قوانين أول."), ephemeral=True)
    if البنر and not (البنر.content_type or "").startswith("image/"):
        return await inter.response.send_message(embed=err("البنر لازم يكون صورة."), ephemeral=True)
    await inter.response.send_modal(RulesPanelModal(الروم, البنر))


async def handle_rules(inter: discord.Interaction):
    idx = int((inter.data.get("values") or ["0"])[0])
    r = db.execute("SELECT * FROM rule_sections WHERE guild_id = ? AND idx = ?", (inter.guild.id, idx)).fetchone()
    if not r:
        await inter.response.send_message(embed=err("هالقسم انحذف."), ephemeral=True)
    else:
        lines = [l.strip() for l in r["content"].splitlines() if l.strip()]
        body = "\n\n".join(f"**{i} -** {l}" for i, l in enumerate(lines, 1))
        e = discord.Embed(title=f"{r['emoji'] or '📜'} - {r['name']}", description=body[:4096], color=0x006C35)
        e.set_footer(text=config.SERVER_NAME)
        await inter.response.send_message(embed=e, ephemeral=True)
    try:  # نرجّع المنيو فاضي
        await inter.message.edit(view=rules_menu(inter.guild.id))
    except discord.HTTPException:
        pass


# ============================================================
# النشرة الإخبارية + الاقتراحات
# ============================================================
db.execute("CREATE TABLE IF NOT EXISTS text_settings (guild_id INTEGER, key TEXT, value TEXT, PRIMARY KEY (guild_id, key))")
db.commit()


def get_text(guild_id: int, key: str, default: str = "") -> str:
    row = db.execute("SELECT value FROM text_settings WHERE guild_id = ? AND key = ?", (guild_id, key)).fetchone()
    return row[0] if row and row[0] is not None else default


def set_text(guild_id: int, key: str, value: str):
    db.execute("INSERT OR REPLACE INTO text_settings (guild_id, key, value) VALUES (?, ?, ?)", (guild_id, key, value))
    db.commit()


NEWS_SOURCES_DEFAULT = "مجهول، عسكري، مدني"


def news_sources(gid: int):
    raw = get_text(gid, "news_sources", NEWS_SOURCES_DEFAULT)
    items = [x.strip() for x in re.split(r"[،,\n]", raw) if x.strip()]
    return items[:25] or ["مجهول", "عسكري", "مدني"]


@bot.tree.command(name="تسطيب_النشرة", description="تسطيب النشرة الإخبارية (للأدمن)")
@app_commands.describe(
    روم_النشر="الروم اللي تنزل فيه النشرات",
    الرتبة="الرتبة اللي تقدر تنشر (فاضي = أي أحد)",
)
async def setup_news(inter: discord.Interaction, روم_النشر: discord.TextChannel = None, الرتبة: discord.Role = None,
):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    if روم_النشر: set_setting(gid, "ch_news", روم_النشر.id)
    if الرتبة: set_setting(gid, "role_news", الرتبة.id)
    ch, role = get_setting(gid, "ch_news"), get_setting(gid, "role_news")
    await inter.response.send_message(embed=embed("📰 تسطيب النشرة", (
        f"**روم النشر:** {f'<#{ch}>' if ch else 'ما تحدد'}\n"
        f"**مين ينشر:** {f'<@&{role}>' if role else 'أي أحد'}\n"
        "**يصدر الخبر من:** مجهول (دايم)\n"
        "\n"
        "بعدها أرسل الزر بـ /ارسال_النشرة")), ephemeral=True)


@bot.tree.command(name="ارسال_النشرة", description="إرسال زر النشرة الإخبارية في روم")
async def send_news_panel(inter: discord.Interaction, الروم: discord.TextChannel):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="نشر نشرة إخبارية", emoji="📰", style=discord.ButtonStyle.success, custom_id="news:open"))
    e = embed("📰 - الــنــشــرة الــيــومــيــة الــاعــلــامــيــة",
              f"- اضغط الزر اللي تحت عشان تنشر نشرة إخبارية في **{config.SERVER_NAME}** .")
    try:
        await الروم.send(embed=e, view=v)
    except discord.HTTPException:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    await inter.response.send_message(embed=embed("✅ انرسل زر النشرة", الروم.mention), ephemeral=True)


def _news_input(label, cid, ph):
    return discord.ui.TextInput(label=label, custom_id=cid, placeholder=ph, max_length=1000,
                                style=discord.TextStyle.paragraph)


class NewsModal(discord.ui.Modal, title="📰 النشرة الإخبارية"):
    """ما لها وقت ينتهي، والإرسال ينعالج في on_interaction عشان يشتغل حتى لو البوت رستر وانت تكتب"""

    def __init__(self, source: str = "مجهول"):
        super().__init__(timeout=None, custom_id="news:modal")
        self.add_item(_news_input("الموقع المعني", "loc", "مثال: البنك المركزي"))
        self.add_item(_news_input("تصنيف الحالة", "status", "مثال: سطو مسلح"))
        self.add_item(_news_input("يتم التوجه", "dir", "مثال: العساكر"))
        self.add_item(_news_input("في نطاق مسؤولية", "scope", "مثال: مجرم"))


def _modal_values(data) -> dict:
    out = {}

    def walk(x):
        if isinstance(x, dict):
            if "custom_id" in x and "value" in x:
                out[x["custom_id"]] = x["value"]
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data.get("components", []))
    return out


async def news_submit(inter: discord.Interaction):
    v = _modal_values(inter.data or {})
    gid = inter.guild.id
    ch = inter.guild.get_channel(get_setting(gid, "ch_news")) or inter.channel
    text = (
        f"**1-يــصــدر الــخــبــر مــن:** مجهول\n\n"
        f"**2-الــمــوقــع الــمــعــنــى:** {v.get('loc', '-')}\n\n"
        f"**3-تــصــنــيــف الــحــالــه:** {v.get('status', '-')}\n\n"
        f"**4-يــتــم الــتــوجــه :** {v.get('dir', '-')}\n\n"
        f"**5-فــي نــطــاق مــســؤولــيــه:** {v.get('scope', '-')}"
    )
    e = embed("📰 - الــنــشــرة الــيــومــيــة الــاعــلــامــيــة", text[:4096])
    try:
        await ch.send(embed=e)
    except discord.HTTPException:
        return await inter.response.send_message(embed=err("ما قدرت أنشر. تأكد من صلاحياتي في روم النشر."), ephemeral=True)
    await inter.response.send_message(embed=embed("✅ تم نشر النشرة", ch.mention), ephemeral=True)
    await log(f"📰 {inter.user.mention} نشر نشرة إخبارية في {ch.mention}", inter.guild)


async def news_open(inter: discord.Interaction):
    role = get_setting(inter.guild.id, "role_news")
    if role and not is_power(inter.user) and not any(r.id == role for r in inter.user.roles):
        return await inter.response.send_message(embed=err(f"النشر لرتبة <@&{role}> بس."), ephemeral=True)
    await inter.response.send_modal(NewsModal("مجهول"))  # الخبر يصدر دايم من مجهول


# ---------- الاقتراحات ----------
@bot.tree.command(name="تسطيب_الاقتراحات", description="تحديد روم الاقتراحات والإيموجيات (للأدمن)")
@app_commands.describe(الروم="روم الاقتراحات", ايموجي_الصح="إيموجي الموافقة (مثل ✅ أو إيموجي السيرفر)",
                       ايموجي_الخطأ="إيموجي الرفض (مثل ❌ أو إيموجي السيرفر)")
async def setup_suggestions(inter: discord.Interaction, الروم: discord.TextChannel,
                            ايموجي_الصح: str = None, ايموجي_الخطأ: str = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب صلاحية الأدمن بس."), ephemeral=True)
    gid = inter.guild.id
    set_setting(gid, "ch_suggest", الروم.id)
    if ايموجي_الصح: set_text(gid, "sug_yes", ايموجي_الصح.strip())
    if ايموجي_الخطأ: set_text(gid, "sug_no", ايموجي_الخطأ.strip())
    await inter.response.send_message(embed=embed("💡 الاقتراحات", (
        f"**الروم:** {الروم.mention}\n**الصح:** {get_text(gid, 'sug_yes', '✅')}\n**الخطأ:** {get_text(gid, 'sug_no', '❌')}\n\n"
        "الحين أي عضو يكتب في الروم، البوت يحوّل كلامه لإيمبد ويحط الإيموجيات.")), ephemeral=True)


async def suggestion_check(message: discord.Message) -> bool:
    if not message.guild or message.channel.id != get_setting(message.guild.id, "ch_suggest"):
        return False
    text = message.content.strip()
    if not text:
        return False
    gid = message.guild.id
    e = discord.Embed(title="💡 - اقتراح جديد", description=text[:4000], color=0x006C35, timestamp=now())
    e.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    e.add_field(name="المقترح", value=message.author.mention)
    e.set_footer(text=config.SERVER_NAME)
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    try:
        msg = await message.channel.send(embed=e)
    except discord.HTTPException:
        return True
    for em in (get_text(gid, "sug_yes", "✅"), get_text(gid, "sug_no", "❌")):
        try:
            await msg.add_reaction(em)
        except discord.HTTPException:
            await log(f"⚠️ ما قدرت أحط الإيموجي {em} في الاقتراحات. حط إيموجي من نفس السيرفر أو إيموجي عادي.", message.guild)
    return True


# ============================================================
# فتح وقفل الرومات: كل الرتب اللي في صلاحيات الروم
# ============================================================
async def _room_apply(guild: discord.Guild, ch, user, open_: bool):
    me = guild.me
    roles = [t for t in ch.overwrites if isinstance(t, discord.Role)
             and t not in me.roles and not t.managed and not t.permissions.administrator]
    changed, failed = [], []
    for role in roles:
        if role.is_default() and open_:
            continue  # @everyone ما نفتحه، الروم يبقى للرتب اللي حاطها بس
        ow = ch.overwrites_for(role)
        if open_:
            ow.update(view_channel=True, send_messages=True, read_message_history=True)
        else:
            ow.update(view_channel=False, send_messages=False)
        try:
            await ch.set_permissions(role, overwrite=ow, reason=f"{'فتح' if open_ else 'قفل'} الروم بواسطة {user}")
            changed.append(role.mention)
        except discord.HTTPException:
            failed.append(role.name)
        await asyncio.sleep(0.3)
    if not open_ and guild.default_role not in roles:
        try:  # نتأكد إن @everyone ما يشوف الروم وهو مقفول
            ow = ch.overwrites_for(guild.default_role)
            ow.update(view_channel=False, send_messages=False)
            await ch.set_permissions(guild.default_role, overwrite=ow)
        except discord.HTTPException:
            pass
    await log(f"{user.mention} {'فتح' if open_ else 'قفل'} الروم {ch.mention}"
              + (f" ⚠️ ما قدرت أعدّل: {'، '.join(failed)} (خل رتبة البوت فوقها)" if failed else ""), guild)
    return changed, failed


def _room_text(ch, open_, changed, failed):
    text = (f"{'🔓 تم فتح' if open_ else '🔒 تم قفل'} {ch.mention}\n\n"
            f"**الرتب ({len(changed)}):** {' '.join(changed) if changed else 'ما فيه رتب في صلاحيات الروم'}")
    if failed:
        text += f"\n\n⚠️ ما قدرت أعدّل: {'، '.join(failed)}\nخل رتبة البوت فوقها وعطه **Manage Roles**."
    return text


async def _toggle_room(inter: discord.Interaction, room, open_: bool):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    ch = room or inter.channel
    await inter.response.defer(ephemeral=True)
    await _room_apply(inter.guild, ch, inter.user, open_)
    try:
        await ch.send("🔓 تم فتح الروم" if open_ else "🔒 تم قفل الروم")
    except discord.HTTPException:
        pass
    await inter.followup.send("🔓 تم فتح الروم" if open_ else "🔒 تم قفل الروم", ephemeral=True)


async def room_prefix(message: discord.Message, open_: bool):
    """-فت يفتح الروم، -قف يقفله (الروم اللي انكتب فيه الأمر)"""
    if not is_power(message.author):
        return await message.reply(embed=err("هذا الأمر للأدمن والأونر بس."))
    await _room_apply(message.guild, message.channel, message.author, open_)
    try:
        await message.channel.send("🔓 تم فتح الروم" if open_ else "🔒 تم قفل الروم")
    except discord.HTTPException:
        pass


@bot.tree.command(name="فتح_روم", description="يفتح الروم: يعطي كل الرتب اللي في صلاحياته عرض + كتابة")
@app_commands.describe(الروم="الروم (فاضي = الروم اللي أنت فيه)")
async def open_room(inter: discord.Interaction, الروم: discord.TextChannel = None):
    await _toggle_room(inter, الروم, True)


@bot.tree.command(name="قفل_روم", description="يقفل الروم: يشيل العرض والكتابة من كل الرتب اللي في صلاحياته")
@app_commands.describe(الروم="الروم (فاضي = الروم اللي أنت فيه)")
async def close_room(inter: discord.Interaction, الروم: discord.TextChannel = None):
    await _toggle_room(inter, الروم, False)


# ============================================================
# حماية السيرفر: نسخة كاملة (الرتب + الرومات + الصلاحيات + إعدادات البوت)
# وتسترجعها في سيرفر ثاني لو صار شي
# ============================================================
CLONE_SKIP_TABLES = {"tickets", "duty_active", "sqlite_sequence"}


def _ow_dump(overwrites: dict) -> list:
    out = []
    for target, ow in overwrites.items():
        allow, deny = ow.pair()
        out.append({"type": "role" if isinstance(target, discord.Role) else "member",
                    "id": target.id, "allow": allow.value, "deny": deny.value})
    return out


def _bot_data_dump(gid: int) -> dict:
    data = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        if name in CLONE_SKIP_TABLES:
            continue
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({name})")]
        if "guild_id" not in cols:
            continue
        rows = []
        for row in db.execute(f"SELECT * FROM {name} WHERE guild_id = ?", (gid,)).fetchall():
            if name == "assets" and row["key"] == "server_clone":
                continue  # النسخة نفسها ما تنحط داخل النسخة
            d = {}
            for c in cols:
                v = row[c]
                d[c] = {"b64": base64.b64encode(bytes(v)).decode()} if isinstance(v, (bytes, bytearray, memoryview)) else v
            rows.append(d)
        if rows:
            data[name] = rows
    return data


def make_server_snapshot(guild: discord.Guild) -> dict:
    roles = [{"id": r.id, "name": r.name, "color": r.color.value, "hoist": r.hoist, "mentionable": r.mentionable,
              "permissions": r.permissions.value, "position": r.position}
             for r in sorted(guild.roles, key=lambda r: r.position) if not r.is_default() and not r.managed]
    cats = [{"id": c.id, "name": c.name, "position": c.position, "overwrites": _ow_dump(c.overwrites)}
            for c in sorted(guild.categories, key=lambda c: c.position)]
    chans = []
    for ch in sorted(guild.channels, key=lambda c: c.position):
        if isinstance(ch, discord.CategoryChannel):
            continue
        d = {"id": ch.id, "name": ch.name, "position": ch.position, "category_id": ch.category_id,
             "overwrites": _ow_dump(ch.overwrites), "synced": bool(ch.category and ch.permissions_synced)}
        if isinstance(ch, discord.StageChannel):
            d.update(type="stage")
        elif isinstance(ch, discord.VoiceChannel):
            d.update(type="voice", bitrate=ch.bitrate, user_limit=ch.user_limit)
        elif isinstance(ch, discord.ForumChannel):
            d.update(type="forum", topic=ch.topic or "", nsfw=ch.nsfw)
        elif isinstance(ch, discord.TextChannel):
            d.update(type="news" if ch.is_news() else "text", topic=ch.topic or "", nsfw=ch.nsfw,
                     slowmode=ch.slowmode_delay)
        else:
            continue
        chans.append(d)
    return {"version": 1, "source_guild": guild.id, "name": guild.name, "created": now().isoformat(),
            "everyone_perms": guild.default_role.permissions.value,
            "roles": roles, "categories": cats, "channels": chans, "bot_data": _bot_data_dump(guild.id),
            "members": [{"id": m.id, "nick": m.nick,
                         "roles": [r.id for r in m.roles if not r.is_default() and not r.managed]}
                        for m in guild.members if not m.bot]}


def save_snapshot(gid: int, snap: dict):
    db.execute("INSERT OR REPLACE INTO assets (guild_id, key, filename, data) VALUES (?, 'server_clone', 'server_backup.json', ?)",
               (gid, json.dumps(snap, ensure_ascii=False).encode()))
    db.commit()


def snapshot_file(snap: dict) -> discord.File:
    return discord.File(io.BytesIO(json.dumps(snap, ensure_ascii=False).encode()),
                        filename=f"server_backup_{now().strftime('%Y-%m-%d')}.json")


# ---------- نسخ الكلام والإيموجيات والملصقات ----------
import gzip

MEDIA_FILE_BUDGET = 6 * 1024 * 1024   # أقصى حجم للمرفقات المنسوخة
PART_SIZE = 8 * 1024 * 1024           # حجم كل جزء في الخاص


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


async def collect_media(guild: discord.Guild, per_channel: int) -> dict:
    media = {"emojis": [], "stickers": [], "messages": {}}
    for attr in ("icon", "banner", "splash"):
        asset = getattr(guild, attr, None)
        if asset:
            try:
                media[attr] = _b64(await asset.read())
            except discord.HTTPException:
                pass
    for e in guild.emojis:
        try:
            media["emojis"].append({"id": e.id, "name": e.name, "animated": e.animated, "data": _b64(await e.read())})
        except discord.HTTPException:
            pass
    for s in guild.stickers:
        try:
            media["stickers"].append({"name": s.name, "description": s.description or s.name, "emoji": s.emoji or "⭐",
                                      "format": s.format.name, "data": _b64(await s.read())})
        except (discord.HTTPException, AttributeError):
            pass
    if per_channel <= 0:
        return media
    budget = MEDIA_FILE_BUDGET
    ticket_chs = {r[0] for r in db.execute("SELECT channel_id FROM tickets WHERE guild_id = ?", (guild.id,)).fetchall()}
    for ch in guild.text_channels:
        if ch.id in ticket_chs or ch.name == BACKUP_CH_NAME:
            continue
        msgs = []
        try:
            async for m in ch.history(limit=per_channel, oldest_first=False):
                if m.type not in (discord.MessageType.default, discord.MessageType.reply):
                    continue
                files = []
                for a in m.attachments:
                    if a.size <= 1024 * 1024 and budget - a.size > 0:
                        try:
                            files.append({"name": a.filename, "data": _b64(await a.read())})
                            budget -= a.size
                        except discord.HTTPException:
                            pass
                if not (m.content or m.embeds or files):
                    continue
                msgs.append({
                    "bot": bool(bot.user and m.author.id == bot.user.id),
                    "author": m.author.display_name, "avatar": m.author.display_avatar.url,
                    "content": m.content, "embeds": [e.to_dict() for e in m.embeds if e.type == "rich"][:10],
                    "files": files, "components": [c.to_dict() for c in m.components],
                })
        except discord.HTTPException:
            continue
        if msgs:
            media["messages"][str(ch.id)] = list(reversed(msgs))  # من الأقدم للأحدث
    return media


def snapshot_parts(snap: dict):
    raw = gzip.compress(json.dumps(snap, ensure_ascii=False).encode())
    parts = [raw[i:i + PART_SIZE] for i in range(0, len(raw), PART_SIZE)] or [raw]
    day = now().strftime('%Y-%m-%d')
    if len(parts) == 1:
        return [discord.File(io.BytesIO(parts[0]), filename=f"server_backup_{day}.gz")]
    return [discord.File(io.BytesIO(p), filename=f"server_backup_{day}.part{i + 1}of{len(parts)}.gz")
            for i, p in enumerate(parts)]


def media_path(gid: int) -> str:
    return f"server_full_{gid}.gz"


def save_full(gid: int, snap: dict):
    try:
        with open(media_path(gid), "wb") as f:
            f.write(gzip.compress(json.dumps(snap, ensure_ascii=False).encode()))
    except OSError:
        pass


def load_full(gid: int):
    try:
        with open(media_path(gid), "rb") as f:
            return json.loads(gzip.decompress(f.read()).decode())
    except (OSError, ValueError):
        return None


async def read_snapshot_attachments(atts) -> dict | None:
    """يقبل ملف .json أو .gz أو أجزاء .partNofM.gz (يرتبها ويجمعها)"""
    atts = [a for a in atts if a.filename.lower().endswith((".json", ".gz"))]
    if not atts:
        return None

    def order(a):
        m_ = re.search(r"part(\d+)of", a.filename)
        return int(m_.group(1)) if m_ else 0
    try:
        blob = b"".join([await a.read() for a in sorted(atts, key=order)])
        if blob[:2] == b"\x1f\x8b":
            blob = gzip.decompress(blob)
        return json.loads(blob.decode())
    except (ValueError, OSError, discord.HTTPException):
        return None


_ID_RE = re.compile(r"\d{17,20}")


def _remap(obj, ids: dict):
    s = json.dumps(obj, ensure_ascii=False)
    s = _ID_RE.sub(lambda m_: str(ids.get(int(m_.group(0)), m_.group(0))), s)
    return json.loads(s)


def _view_from(rows: list):
    if not rows:
        return None
    v = discord.ui.View(timeout=None)
    for ri, row in enumerate(rows[:5]):
        for c in row.get("components", []):
            emo = discord.PartialEmoji.from_dict(c["emoji"]) if c.get("emoji") else None
            try:
                if c.get("type") == 2:
                    style = discord.ButtonStyle(c.get("style", 1))
                    if style == discord.ButtonStyle.link:
                        v.add_item(discord.ui.Button(label=c.get("label"), url=c.get("url"), emoji=emo, row=ri))
                    elif style != discord.ButtonStyle.premium:
                        v.add_item(discord.ui.Button(label=c.get("label"), style=style, emoji=emo, row=ri,
                                                     custom_id=c.get("custom_id"), disabled=c.get("disabled", False)))
                elif c.get("type") == 3:
                    opts = [discord.SelectOption(label=o["label"], value=o["value"], description=o.get("description"),
                                                 emoji=discord.PartialEmoji.from_dict(o["emoji"]) if o.get("emoji") else None)
                            for o in c.get("options", [])]
                    v.add_item(discord.ui.Select(custom_id=c.get("custom_id"), placeholder=c.get("placeholder"),
                                                 min_values=c.get("min_values", 1), max_values=c.get("max_values", 1),
                                                 options=opts, row=ri))
            except (ValueError, TypeError, KeyError):
                pass
    return v if v.children else None


async def restore_media(target: discord.Guild, media: dict, ids: dict, say):
    # الإيموجيات أول (عشان الرسايل اللي فيها إيموجي تطلع صح)
    ok = 0
    for e in media.get("emojis", []):
        try:
            ne = await target.create_custom_emoji(name=e["name"], image=base64.b64decode(e["data"]), reason="استرجاع السيرفر")
            ids[e["id"]] = ne.id
            ok += 1
        except discord.HTTPException:
            pass
        await asyncio.sleep(1)
    if media.get("emojis"):
        await say(f"😀 رجّعت **{ok}** إيموجي من {len(media['emojis'])}")
    ok = 0
    for s in media.get("stickers", []):
        try:
            ext = {"apng": "png", "png": "png", "gif": "gif"}.get(s.get("format", "png"), "png")
            await target.create_sticker(name=s["name"], description=s["description"][:100], emoji=s["emoji"],
                                        file=discord.File(io.BytesIO(base64.b64decode(s["data"])), filename=f"s.{ext}"))
            ok += 1
        except (discord.HTTPException, ValueError):
            pass
        await asyncio.sleep(1)
    if media.get("stickers"):
        await say(f"🏷️ رجّعت **{ok}** ملصق من {len(media['stickers'])}")

    total = sum(len(v) for v in media.get("messages", {}).values())
    if not total:
        return
    await say(f"💬 أرجّع الكلام ({total} رسالة)... هذا ياخذ وقت شوي.")
    sent, failed, first_err = 0, 0, ""
    for old_id, msgs in media["messages"].items():
        ch = target.get_channel(ids.get(int(old_id), 0))
        if not isinstance(ch, discord.TextChannel):
            continue
        hook = None
        for m in msgs:
            m = _remap({k: v for k, v in m.items() if k not in ("files", "avatar")}, ids) | {"files": m["files"], "avatar": m["avatar"]}
            embeds = [discord.Embed.from_dict(e) for e in m["embeds"]]
            files = [discord.File(io.BytesIO(base64.b64decode(f["data"])), filename=f["name"]) for f in m["files"]]
            try:
                if m["bot"]:
                    view = _view_from(m.get("components") or [])
                    kw = {"content": m["content"] or None, "embeds": embeds, "files": files}
                    if view:
                        kw["view"] = view
                    await ch.send(**kw)
                else:
                    if hook is None:
                        hook = await ch.create_webhook(name="استرجاع", reason="استرجاع السيرفر")
                    await hook.send(content=m["content"] or None, embeds=embeds, files=files,
                                    username=(m["author"] or "عضو")[:80], avatar_url=m["avatar"],
                                    allowed_mentions=discord.AllowedMentions.none())
                sent += 1
            except Exception as ex:  # نكمل الباقي ونعرض أول خطأ
                failed += 1
                first_err = first_err or f"{type(ex).__name__}: {str(ex)[:200]}"
            await asyncio.sleep(0.7)
        if hook:
            try:
                await hook.delete()
            except discord.HTTPException:
                pass
    await say(f"💬 رجّعت **{sent}** رسالة" + (f"\n⚠️ {failed} ما رجعت، أول خطأ: `{first_err}`" if failed else ""))


@bot.tree.command(name="نسخ_السيرفر", description="ياخذ نسخة كاملة من السيرفر (رتب، رومات، صلاحيات، إعدادات البوت)")
@app_commands.describe(الرسايل="كم رسالة ينسخ من كل روم (الافتراضي 50، 0 = بدون كلام)")
async def clone_backup(inter: discord.Interaction, الرسايل: app_commands.Range[int, 0, 100] = 50):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب السيرفر والأونر بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    if not inter.guild.chunked:
        await inter.guild.chunk()
    snap = make_server_snapshot(inter.guild)
    save_snapshot(inter.guild.id, snap)          # النسخة الخفيفة (رتب + رومات + إعدادات)
    await inter.followup.send("⏳ أنسخ الكلام والإيموجيات... انتظر شوي.", ephemeral=True)
    media = await collect_media(inter.guild, الرسايل)
    full = dict(snap, media=media)
    save_full(inter.guild.id, full)              # النسخة الكاملة
    await do_backup(force=True)
    nmsg = sum(len(v) for v in media["messages"].values())
    sent_dm = False
    try:  # نسخة في الخاص: لو السيرفر تهكر، الملف يبقى عندك
        parts = snapshot_parts(full)
        await inter.user.send(embed=embed("🛡️ نسخة السيرفر", (
            f"نسخة **{inter.guild.name}**\n**رتب:** {len(snap['roles'])} · **رومات:** {len(snap['channels'])} · "
            f"**رسايل:** {nmsg} · **إيموجي:** {len(media['emojis'])} · **ملصقات:** {len(media['stickers'])}\n\n"
            "احتفظ بالملف" + (f"ات ({len(parts)} أجزاء، لازم كلها)" if len(parts) > 1 else "") +
            ". لو صار شي: دخّل البوت السيرفر الجديد واكتب `-استرجاع`.")))
        for f in parts:
            await inter.user.send(file=f)
        sent_dm = True
    except discord.HTTPException:
        pass
    await inter.followup.send(embed=embed("🛡️ تم نسخ السيرفر", (
        f"**رتب:** {len(snap['roles'])} · **كاتيجوري:** {len(snap['categories'])} · **رومات:** {len(snap['channels'])}\n"
        f"**رسايل:** {nmsg} · **إيموجي:** {len(media['emojis'])} · **ملصقات:** {len(media['stickers'])}\n"
        f"**إعدادات البوت:** {sum(len(v) for v in snap['bot_data'].values())} سطر\n\n"
        + ("📩 أرسلت لك الملف في الخاص، احتفظ فيه." if sent_dm else "⚠️ ما قدرت أرسل لك في الخاص. افتح الخاص وأعد الأمر.")
    )), ephemeral=True)


db.execute("CREATE TABLE IF NOT EXISTS restore_members (guild_id INTEGER, user_id INTEGER, roles TEXT, nick TEXT, PRIMARY KEY (guild_id, user_id))")
db.commit()


async def apply_restored_member(member: discord.Member) -> int:
    """يرجّع للعضو رتبه واسمه من السيرفر القديم (لو موجود في النسخة)"""
    row = db.execute("SELECT roles, nick FROM restore_members WHERE guild_id = ? AND user_id = ?",
                     (member.guild.id, member.id)).fetchone()
    if not row:
        return 0
    roles = [r for r in (member.guild.get_role(i) for i in json.loads(row[0] or "[]"))
             if r and r < member.guild.me.top_role and not r.managed and r not in member.roles]
    try:
        if roles:
            await member.add_roles(*roles, reason="استرجاع رتب السيرفر القديم")
        if row[1] and member.id != member.guild.owner_id:
            await member.edit(nick=row[1][:32])
    except discord.HTTPException:
        pass
    db.execute("DELETE FROM restore_members WHERE guild_id = ? AND user_id = ?", (member.guild.id, member.id))
    db.commit()
    return 1


# ---------- مكان اللوحات (عشان ترجع في مكانها بعد الاسترجاع) ----------
db.execute("CREATE TABLE IF NOT EXISTS panels (guild_id INTEGER, kind TEXT, channel_id INTEGER, args TEXT, PRIMARY KEY (guild_id, kind, channel_id))")
db.commit()


def register_panel(gid: int, kind: str, channel_id: int, args: dict):
    db.execute("INSERT OR REPLACE INTO panels VALUES (?, ?, ?, ?)", (gid, kind, channel_id, json.dumps(args, ensure_ascii=False)))
    db.commit()


async def post_ticket_panel(guild: discord.Guild, ch, buttons: bool, slots=None, desc=None):
    types_ = [t for t in get_ticket_types(guild.id) if (t["slot"] in slots if slots else (t["slot"] > 10) == buttons)]
    if not types_:
        return False
    slots = [t["slot"] for t in types_]
    lines = "\n".join(f"{t['emoji'] or '🎫'} - {t['name']}" for t in types_)
    e = embed("🎫 - التذاكر", (desc or f"- مرحبا بك عزيزي العضو في قسم التذاكر الخاص بـ **{config.SERVER_NAME}** .\n\n"
                               + ("اضغط على الزر حق التذكرة اللي تبيها ." if buttons else "اختر نوع التذكرة من القائمة اللي تحت ."))
              + f"\n\n{lines}")
    pfile, _ = ticket_image_file(guild.id, 0)
    pfile.filename = "panel" + os.path.splitext(pfile.filename)[1]
    e.set_image(url=f"attachment://{pfile.filename}")
    await ch.send(embed=e, file=pfile, view=ticket_buttons_panel(guild.id, slots) if buttons else ticket_select(guild.id, slots))
    return True


async def post_app_panel(guild: discord.Guild, ch, desc=None):
    types_ = get_app_types(guild.id)
    if not types_:
        return False
    lines = "\n".join(f"{t['emoji'] or '📝'} - {t['name']}" for t in types_)
    e = embed("📝 - التقديمات", (desc or f"- مرحبا بك في قسم التقديمات الخاص بـ **{config.SERVER_NAME}** .\n\n"
                                       "اختر التقديم من القائمة وجاوب على الأسئلة .") + f"\n\n{lines}")
    await ch.send(embed=e, view=app_select_view(guild.id))
    return True


def _norm(name: str) -> str:
    n = re.sub(r"[ـ\-_\s|┊︙・•.]", "", (name or "").lower())
    return n.translate(str.maketrans({"ة": "ه", "ى": "ي", "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي"}))


def _guess_channel(guild: discord.Guild, words):
    for ch in guild.text_channels:
        n = _norm(ch.name)
        if any(w in n for w in words):
            return ch
    return None


async def resend_panels(guild: discord.Guild) -> list:
    """يرسل لوحات التذاكر والتقديمات في أماكنها (المحفوظة، أو يخمّنها من اسم الروم)"""
    done = []
    rows = db.execute("SELECT kind, channel_id, args FROM panels WHERE guild_id = ?", (guild.id,)).fetchall()
    kinds = {r[0] for r in rows if guild.get_channel(r[1])}
    for kind, cid, args in rows:
        ch = guild.get_channel(cid)
        if not isinstance(ch, discord.TextChannel):
            continue
        a = json.loads(args or "{}")
        try:
            ok = (await post_ticket_panel(guild, ch, a.get("buttons", False), a.get("slots"), a.get("desc"))
                  if kind.startswith("tickets") else await post_app_panel(guild, ch, a.get("desc")))
            if ok:
                done.append(f"{'🎫 التذاكر' if kind.startswith('tickets') else '📝 التقديمات'} ← {ch.mention}")
        except discord.HTTPException:
            pass
        await asyncio.sleep(1)
    if not any(k.startswith("tickets") for k in kinds):  # ما نعرف مكانها: نخمّن من اسم الروم
        # 1) كل تذكرة في الروم اللي اسمه فيه اسمها (جمارك، مساعدة، شكوى، طلب قيادة...)
        placed = {}
        for t in get_ticket_types(guild.id):
            tn = _norm(t["name"])
            if len(tn) < 3:
                continue
            ch_ = next((c for c in guild.text_channels if tn in _norm(c.name) or _norm(c.name).endswith(tn)), None)
            if ch_ is None:  # جرّب كل كلمة من اسم التذكرة (مثل: شكوى من "تذكرة شكوى")
                for w in [_norm(x) for x in re.split(r"[\s\-ـ]+", t["name"]) if len(_norm(x)) >= 4 and _norm(x) not in ("تذكره", "تذاكر")]:
                    ch_ = next((c for c in guild.text_channels if w in _norm(c.name)), None)
                    if ch_:
                        break
            if ch_:
                placed.setdefault(ch_.id, []).append(t["slot"])
        for cid_, slots_ in placed.items():
            ch_ = guild.get_channel(cid_)
            for buttons in (False, True):
                part = [x for x in slots_ if (x > 10) == buttons]
                if not part:
                    continue
                try:
                    if await post_ticket_panel(guild, ch_, buttons, part):
                        register_panel(guild.id, "tickets_btn" if buttons else "tickets", ch_.id, {"buttons": buttons, "slots": part})
                        done.append(f"🎫 {'، '.join(t['name'] for t in get_ticket_types(guild.id) if t['slot'] in part)} ← {ch_.mention}")
                except discord.HTTPException:
                    pass
                await asyncio.sleep(1)
        # 2) لو ما لقى روم لأي تذكرة: روم عام اسمه تذاكر
        ch = None if placed else _guess_channel(guild, ("تذاكر", "تذكره", "تكت", "ticket"))
        if ch:
            for buttons in (False, True):
                try:
                    if await post_ticket_panel(guild, ch, buttons):
                        register_panel(guild.id, "tickets_btn" if buttons else "tickets", ch.id, {"buttons": buttons})
                        done.append(f"🎫 التذاكر ({'أزرار' if buttons else 'منيو'}) ← {ch.mention}")
                except discord.HTTPException:
                    pass
    if "apps" not in kinds:
        ch = _guess_channel(guild, ("تقديم", "تقديمات", "apply"))
        if ch:
            try:
                if await post_app_panel(guild, ch):
                    register_panel(guild.id, "apps", ch.id, {})
                    done.append(f"📝 التقديمات ← {ch.mention}")
            except discord.HTTPException:
                pass
    return done


@bot.tree.command(name="اعادة_اللوحات", description="يرجّع لوحات التذاكر والتقديمات في أماكنها القديمة")
async def resend_panels_cmd(inter: discord.Interaction):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    done = await resend_panels(inter.guild)
    await inter.followup.send(embed=embed("🔁 إعادة اللوحات", (
        "\n".join(done) if done else
        "ما قدرت أرسل شي. تأكد إن التذاكر والتقديمات مسطّبة (/قائمة_التذاكر)، "
        "أو أرسلها بيدك مرة وحدة بـ /ارسال_التذاكر و /ارسال_التقديمات وبعدها يحفظ البوت مكانها.")), ephemeral=True)


async def order_roles_like(guild: discord.Guild, snap: dict) -> int:
    """يرتّب رتب السيرفر بنفس ترتيب النسخة (بالاسم). يرجع كم رتبة ترتبت"""
    by_name = collections.defaultdict(list)
    for r in sorted(guild.roles, key=lambda r: r.position):
        if not r.is_default():
            by_name[r.name].append(r)
    wanted = []  # من تحت لفوق حسب النسخة
    for r in snap.get("roles", []):
        if by_name.get(r["name"]):
            wanted.append(by_name[r["name"]].pop(0))
    top = guild.me.top_role
    wanted = [r for r in wanted if r < top]
    others = [r for r in sorted(guild.roles, key=lambda r: r.position)
              if not r.is_default() and r < top and r not in wanted]
    final = wanted + others  # رتب النسخة تحت، والرتب الجديدة فوقها تحت البوت
    if not final:
        return 0
    try:
        await guild.edit_role_positions(positions={r: i + 1 for i, r in enumerate(final)}, reason="ترتيب الرتب مثل النسخة")
        return len(wanted)
    except discord.HTTPException as e:
        print("order roles error:", e)
        return -1


@bot.tree.command(name="ترتيب_الرتب", description="يرتّب رتب السيرفر بنفس ترتيب السيرفر القديم (من النسخة)")
async def reorder_roles_cmd(inter: discord.Interaction):
    if inter.user.id != inter.guild.owner_id and not await bot.is_owner(inter.user):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب السيرفر بس."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    names = {r.name for r in inter.guild.roles}
    snap, best = None, 0
    for row in db.execute("SELECT guild_id, data FROM assets WHERE key = 'server_clone'").fetchall():
        if row[0] == inter.guild.id:
            continue
        cand = json.loads(bytes(row[1]).decode())
        score = sum(1 for r in cand.get("roles", []) if r["name"] in names)  # النسخة اللي رتبها تشبه هالسيرفر
        if score > best:
            snap, best = cand, score
    if not snap:
        return await inter.followup.send(embed=err("ما لقيت نسخة السيرفر القديم."), ephemeral=True)
    n = await order_roles_like(inter.guild, snap)
    if n < 0:
        return await inter.followup.send(embed=err(
            "ديسكورد رفض الترتيب. تأكد إن **رتبة البوت أعلى رتبة** في القائمة (اسحبها فوق الكل) وعندها Administrator، وأعد الأمر."),
            ephemeral=True)
    await inter.followup.send(embed=embed("✅ ترتيب الرتب", (
        f"رتّبت **{n}** رتبة بنفس ترتيب سيرفرك القديم **{snap.get('name')}** 👑\n"
        "الرتب الجديدة (اللي ما كانت في القديم) صارت فوقها تحت البوت.")), ephemeral=True)


async def _restore_server(target: discord.Guild, snap: dict, status_ch, wipe: bool):
    async def say(t):
        try:
            await status_ch.send(t)
        except discord.HTTPException:
            pass

    rmap, cmap = {}, {}  # الايدي القديم ← الجديد
    rmap[snap["source_guild"]] = target.default_role.id  # @everyone
    if wipe:
        await say("🧹 أحذف الرومات والرتب القديمة...")
        for ch in list(target.channels):
            if ch.id == status_ch.id:
                continue
            try:
                await ch.delete(reason="استرجاع السيرفر")
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.4)
        for r in list(target.roles):
            if r.is_default() or r.managed or r >= target.me.top_role:
                continue
            try:
                await r.delete(reason="استرجاع السيرفر")
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.4)

    try:
        await target.default_role.edit(permissions=discord.Permissions(snap["everyone_perms"]))
    except discord.HTTPException:
        pass
    await say(f"👑 أسوي الرتب ({len(snap['roles'])})...")
    created = []
    for r in reversed(snap["roles"]):  # من فوق لتحت: كل رتبة جديدة تنحط تحت اللي قبلها، فيطلع نفس الترتيب
        try:
            nr = await target.create_role(name=r["name"], colour=discord.Colour(r["color"]), hoist=r["hoist"],
                                          mentionable=r["mentionable"], permissions=discord.Permissions(r["permissions"]),
                                          reason="استرجاع السيرفر")
            rmap[r["id"]] = nr.id
            created.append(nr)
        except discord.HTTPException:
            try:  # البوت ما يقدر يعطي صلاحية ما عنده، نسويها بدون صلاحيات
                nr = await target.create_role(name=r["name"], colour=discord.Colour(r["color"]), hoist=r["hoist"],
                                              mentionable=r["mentionable"], reason="استرجاع السيرفر")
                rmap[r["id"]] = nr.id
                created.append(nr)
            except discord.HTTPException:
                pass
        await asyncio.sleep(0.4)
    await order_roles_like(target, snap)

    def build_ow(items):
        out = {}
        for o in items:
            if o["type"] == "role":
                tgt = target.get_role(rmap.get(o["id"], 0))
            else:
                tgt = target.get_member(o["id"])
            if tgt:
                out[tgt] = discord.PermissionOverwrite.from_pair(discord.Permissions(o["allow"]), discord.Permissions(o["deny"]))
        return out

    await say(f"📁 أسوي الكاتيجوري ({len(snap['categories'])})...")
    for c in snap["categories"]:
        try:
            nc = await target.create_category(c["name"], overwrites=build_ow(c["overwrites"]), reason="استرجاع السيرفر")
            cmap[c["id"]] = nc.id
        except discord.HTTPException:
            pass
        await asyncio.sleep(0.4)

    await say(f"💬 أسوي الرومات ({len(snap['channels'])})...")
    for d in snap["channels"]:
        cat = target.get_channel(cmap.get(d.get("category_id") or 0, 0))
        ow = build_ow(d["overwrites"])
        try:
            if d["type"] == "voice":
                nc = await target.create_voice_channel(d["name"], category=cat, overwrites=ow,
                                                       bitrate=min(d.get("bitrate", 64000), int(target.bitrate_limit)),
                                                       user_limit=d.get("user_limit", 0))
            elif d["type"] == "stage":
                nc = await target.create_stage_channel(d["name"], category=cat, overwrites=ow)
            elif d["type"] == "forum":
                nc = await target.create_forum(d["name"], category=cat, overwrites=ow, topic=d.get("topic") or None,
                                               nsfw=d.get("nsfw", False))
            else:
                nc = await target.create_text_channel(d["name"], category=cat, overwrites=ow, topic=d.get("topic") or None,
                                                      nsfw=d.get("nsfw", False), slowmode_delay=d.get("slowmode", 0),
                                                      news=d["type"] == "news" and "COMMUNITY" in target.features)
            cmap[d["id"]] = nc.id
        except discord.HTTPException:
            pass
        await asyncio.sleep(0.4)

    # إعدادات البوت: ننسخها ونبدّل ايديات الرتب والرومات القديمة بالجديدة
    ids = {**rmap, **cmap}

    def conv(v):
        if isinstance(v, dict) and "b64" in v:
            return base64.b64decode(v["b64"])
        if isinstance(v, int) and v in ids:
            return ids[v]
        return v

    n = 0
    for table, rows in (snap.get("bot_data") or {}).items():
        if table in CLONE_SKIP_TABLES:
            continue
        try:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
        except sqlite3.Error:
            continue
        for row in rows:
            row = {k: conv(v) for k, v in row.items() if k in cols and k != "id"}
            row["guild_id"] = target.id
            keys = list(row)
            try:
                db.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
                           [row[k] for k in keys])
                n += 1
            except sqlite3.Error:
                pass
    db.commit()
    if snap.get("media"):
        await restore_media(target, snap["media"], ids, say)
    if not (snap.get("media") or {}).get("messages"):  # ما فيه كلام منسوخ ← نرسل اللوحات في أماكنها
        placed = await resend_panels(target)
        if placed:
            await say("🎫 رجّعت اللوحات في أماكنها:\n" + "\n".join(placed))
    # شكل السيرفر: الاسم والصورة والبانر
    try:
        kw = {"name": snap.get("name") or target.name}
        media = snap.get("media") or {}
        if media.get("icon"):
            kw["icon"] = base64.b64decode(media["icon"])
        if media.get("banner") and "BANNER" in target.features:
            kw["banner"] = base64.b64decode(media["banner"])
        await target.edit(**kw, reason="استرجاع السيرفر")
    except (discord.HTTPException, ValueError):
        pass
    # رتب الأعضاء: اللي موجود ياخذها الحين، واللي يدخل بعدين ياخذها أول ما يدخل
    db.execute("DELETE FROM restore_members WHERE guild_id = ?", (target.id,))
    given = 0
    for m in snap.get("members", []):
        new_roles = [ids[r] for r in m.get("roles", []) if r in ids]
        if not new_roles and not m.get("nick"):
            continue
        db.execute("INSERT OR REPLACE INTO restore_members VALUES (?, ?, ?, ?)",
                   (target.id, m["id"], json.dumps(new_roles), m.get("nick")))
        if target.get_member(m["id"]):
            given += await apply_restored_member(target.get_member(m["id"]))
    db.commit()
    if snap.get("members"):
        await say(f"👥 رجّعت رتب **{given}** عضو موجود، والباقي ياخذون رتبهم وأسماءهم أول ما يدخلون ✅")
    await say(f"✅ **خلص الاسترجاع!**\nرتب: {len(created)} · رومات وكاتيجوري: {len(cmap)} · إعدادات البوت: {n}\n\n"
              "📌 ارفع رتبة البوت فوق. ولو لوحة ما اشتغلت، أعد إرسالها. واحذف هالروم لو تبي.")


@bot.tree.command(name="استرجاع_السيرفر", description="يرجّع نسخة السيرفر في هذا السيرفر (رتب، رومات، إعدادات البوت)")
@app_commands.describe(
    الملف="ملف النسخة اللي وصلك في الخاص (فاضي = آخر نسخة محفوظة عند البوت)",
    حذف_الموجود="يحذف الرومات والرتب اللي في هذا السيرفر قبل (للسيرفر الجديد الفاضي)",
)
@app_commands.choices(حذف_الموجود=[app_commands.Choice(name="نعم، احذف الموجود", value=1)])
async def clone_restore(inter: discord.Interaction, الملف: discord.Attachment = None,
                        حذف_الموجود: app_commands.Choice[int] = None):
    if inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message(embed=err("الاسترجاع لصاحب السيرفر بس."), ephemeral=True)
    if not inter.guild.me.guild_permissions.administrator:
        return await inter.response.send_message(embed=err("عطني صلاحية **Administrator** في هذا السيرفر أول."), ephemeral=True)
    await inter.response.defer(ephemeral=True)
    snap = None
    if الملف:
        snap = await read_snapshot_attachments([الملف])
    if snap is None:  # بدون ملف (أو رفع صورة بالغلط): آخر نسخة من سيرفر ثاني صاحبه نفس الشخص
        snap = best_snapshot(latest_snapshot_for(inter.user.id, inter.guild.id, await bot.is_owner(inter.user)))
    if not snap or "roles" not in snap:
        return await inter.followup.send(embed=err("ما لقيت نسخة. اكتب `/نسخ_السيرفر` في سيرفرك الأساسي أول."), ephemeral=True)
    if snap["source_guild"] == inter.guild.id and حذف_الموجود:
        return await inter.followup.send(embed=err("ما تقدر تحذف وتسترجع في نفس السيرفر الأصلي."), ephemeral=True)
    await inter.followup.send(embed=embed("🛡️ بدأ الاسترجاع", (
        f"نسخة **{snap.get('name')}** ({snap.get('created', '')[:10]})\n"
        f"رتب: {len(snap['roles'])} · رومات: {len(snap['channels'])}\n\nبياخذ كم دقيقة، تابع هنا في الروم.")), ephemeral=True)
    await log(f"🛡️ {inter.user.mention} بدأ استرجاع نسخة **{snap.get('name')}**", inter.guild)
    asyncio.create_task(_restore_server(inter.guild, snap, inter.channel, bool(حذف_الموجود)))


def best_snapshot(snap):
    """نضيف للنسخة الخفيفة الكلام والإيموجيات من آخر نسخة كاملة لنفس السيرفر (لو موجودة)"""
    if snap and not snap.get("media"):
        full = load_full(snap.get("source_guild", 0))
        if full and full.get("media"):
            return dict(snap, media=full["media"])
    return snap


def latest_snapshot_for(user_id: int, exclude_gid: int, is_bot_owner: bool = False):
    snap = None
    for row in db.execute("SELECT guild_id, data FROM assets WHERE key = 'server_clone'").fetchall():
        if row[0] == exclude_gid:
            continue
        g = bot.get_guild(row[0])
        # صاحب البوت ياخذ أي نسخة (حتى لو انسرقت ملكية السيرفر الأصلي)
        if not is_bot_owner and g is not None and g.owner_id != user_id:
            continue
        s_ = json.loads(bytes(row[1]).decode())
        if snap is None or s_.get("created", "") > snap.get("created", ""):
            snap = s_
    return snap


async def restore_prefix(message: discord.Message):
    """-استرجاع : يكتبه صاحب السيرفر الجديد، والبوت يسوي كل شي لحاله"""
    g = message.guild
    if message.author.id != g.owner_id:
        return await message.reply("❌ الاسترجاع لصاحب السيرفر بس.")
    if not g.me.guild_permissions.administrator:
        return await message.reply("❌ عطني **Administrator** أول.")
    snap = None
    if message.attachments:
        snap = await read_snapshot_attachments(message.attachments)
    snap = snap or best_snapshot(latest_snapshot_for(message.author.id, g.id, await bot.is_owner(message.author)))
    if not snap or "roles" not in snap:
        return await message.reply("❌ ما لقيت نسخة. اكتب `/نسخ_السيرفر` في سيرفرك الأساسي أول.")
    wipe = len(g.channels) <= 10  # سيرفر جديد فاضي: نحذف رومات ديسكورد الافتراضية
    await message.reply(f"🛡️ بدأ الاسترجاع من نسخة **{snap.get('name')}**... انتظر كم دقيقة.")
    asyncio.create_task(_restore_server(g, snap, message.channel, wipe))


async def clone_from_prefix(message: discord.Message):
    """-نسخ_من ايدي_السيرفر : ينسخ سيرفر ثاني (البوت فيه) لهذا السيرفر مباشرة، بكل شي"""
    g = message.guild
    parts = message.content.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.reply("❌ الاستخدام: `-نسخ_من ايدي_السيرفر_اللي_تبي_تنسخه`")
    src = bot.get_guild(int(parts[1]))
    if src is None:
        return await message.reply("❌ البوت مو موجود في ذاك السيرفر. دخّله فيه أول.")
    if src.id == g.id:
        return await message.reply("❌ هذا نفس السيرفر.")
    is_bot_owner = await bot.is_owner(message.author)
    if message.author.id != g.owner_id or (src.owner_id != message.author.id and not is_bot_owner):
        return await message.reply("❌ لازم تكون صاحب السيرفرين.")
    if not g.me.guild_permissions.administrator:
        return await message.reply("❌ عطني **Administrator** هنا أول.")
    status = await message.reply(f"⏳ أنسخ **{src.name}** (رتب، رومات، كلام، إيموجيات، رتب الأعضاء)... انتظر.")
    if not src.chunked:
        await src.chunk()
    snap = make_server_snapshot(src)
    save_snapshot(src.id, snap)
    snap["media"] = await collect_media(src, 50)
    save_full(src.id, snap)
    try:
        await status.edit(content=f"🛡️ خلصت النسخ، أبدأ أحطه هنا... تابع الرسايل تحت.")
    except discord.HTTPException:
        pass
    asyncio.create_task(_restore_server(g, snap, message.channel, len(g.channels) <= 10))


@bot.tree.command(name="نسخ_من_سيرفر", description="ينسخ سيرفر ثاني (البوت فيه) لهذا السيرفر بكل شي: رتب، رومات، كلام، إيموجيات")
@app_commands.describe(ايدي_السيرفر="ايدي السيرفر اللي تبي تنسخه (الأساسي)",
                       حذف_الموجود="يحذف رومات ورتب هذا السيرفر قبل النسخ")
@app_commands.choices(حذف_الموجود=[app_commands.Choice(name="نعم، احذف الموجود", value=1)])
async def clone_from_cmd(inter: discord.Interaction, ايدي_السيرفر: str, حذف_الموجود: app_commands.Choice[int] = None):
    g = inter.guild
    if not ايدي_السيرفر.strip().isdigit():
        return await inter.response.send_message(embed=err("حط ايدي السيرفر أرقام بس."), ephemeral=True)
    src = bot.get_guild(int(ايدي_السيرفر.strip()))
    if src is None:
        return await inter.response.send_message(embed=err("البوت مو موجود في ذاك السيرفر."), ephemeral=True)
    if src.id == g.id:
        return await inter.response.send_message(embed=err("هذا نفس السيرفر."), ephemeral=True)
    if inter.user.id != g.owner_id or (src.owner_id != inter.user.id and not await bot.is_owner(inter.user)):
        return await inter.response.send_message(embed=err("لازم تكون صاحب السيرفرين."), ephemeral=True)
    if not g.me.guild_permissions.administrator:
        return await inter.response.send_message(embed=err("عطني **Administrator** هنا أول، وارفع رتبتي فوق الكل."), ephemeral=True)
    await inter.response.send_message(f"⏳ أنسخ **{src.name}** بكل شي... تابع هنا.")
    ch = inter.channel
    try:
        if not src.chunked:
            await src.chunk()
        snap = make_server_snapshot(src)
        save_snapshot(src.id, snap)
        snap["media"] = await collect_media(src, 50)
        save_full(src.id, snap)
    except Exception as ex:
        import traceback; traceback.print_exc()
        return await ch.send(f"⚠️ صار خطأ وأنا أنسخ: `{type(ex).__name__}: {str(ex)[:300]}`")
    await ch.send("🛡️ خلصت النسخ، أبدأ أحطه هنا...")
    asyncio.create_task(_restore_server(g, snap, ch, bool(حذف_الموجود)))


@bot.tree.command(name="نسخ_الكلام", description="ينسخ الكلام بس من سيرفر ثاني لهذا السيرفر (الرومات بنفس الأسماء)")
@app_commands.describe(ايدي_السيرفر="ايدي السيرفر اللي فيه الكلام", الرسايل="كم رسالة من كل روم (الافتراضي 50)")
async def copy_messages_cmd(inter: discord.Interaction, ايدي_السيرفر: str, الرسايل: app_commands.Range[int, 1, 100] = 50):
    g = inter.guild
    src = bot.get_guild(int(ايدي_السيرفر)) if ايدي_السيرفر.strip().isdigit() else None
    if src is None:
        return await inter.response.send_message(embed=err("البوت مو موجود في ذاك السيرفر، أو الايدي غلط."), ephemeral=True)
    if inter.user.id != g.owner_id and not await bot.is_owner(inter.user):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب السيرفر بس."), ephemeral=True)
    await inter.response.send_message(f"⏳ أجمع الكلام من **{src.name}**...")
    ch_out = inter.channel
    try:
        media = await collect_media(src, الرسايل)
    except Exception as ex:
        return await ch_out.send(f"⚠️ خطأ وأنا أجمع: `{type(ex).__name__}: {str(ex)[:300]}`")
    media["emojis"], media["stickers"] = [], []
    total = sum(len(v) for v in media["messages"].values())
    if not total:
        return await ch_out.send(
            "⚠️ ما لقيت ولا رسالة في السيرفر الأساسي.\nتأكد إن البوت عنده **Administrator** هناك، "
            "وإن **Message Content Intent** مفعّل في discord.com/developers ← Bot.")
    # نربط الرومات والرتب والإيموجيات بالاسم
    ids = {}
    tgt_by_name = {}
    for c in g.text_channels:
        tgt_by_name.setdefault(_norm(c.name), c)
    missing = []
    for c in src.text_channels:
        t = tgt_by_name.get(_norm(c.name))
        if t:
            ids[c.id] = t.id
        elif str(c.id) in media["messages"]:
            missing.append(c.name)
    for r in src.roles:
        t = discord.utils.get(g.roles, name=r.name)
        if t:
            ids[r.id] = t.id
    for e in src.emojis:
        t = discord.utils.get(g.emojis, name=e.name)
        if t:
            ids[e.id] = t.id
    await ch_out.send(f"📦 لقيت **{total}** رسالة في **{len(media['messages'])}** روم. أبدأ أحطها...")

    async def say(t):
        try:
            await ch_out.send(t)
        except discord.HTTPException:
            pass
    try:
        await restore_media(g, media, ids, say)
    except Exception as ex:
        import traceback; traceback.print_exc()
        return await say(f"⚠️ خطأ وأنا أحط الكلام: `{type(ex).__name__}: {str(ex)[:300]}`")
    if missing:
        await say("ℹ️ رومات ما لقيت لها روم بنفس الاسم هنا: " + "، ".join(missing[:20]))
    await say("✅ خلص نسخ الكلام")


OLD_TS_PREFIX = re.compile(r"^\s*(ts|ᴛꜱ|TS)\s*[┊|︙:・•\-]*\s*", re.I)


def decorated_name(name: str, suffix: str, sep: str, strip_old: bool) -> str:
    base = OLD_TS_PREFIX.sub("", name) if strip_old else name
    base = base.strip("-_ ") or name
    return f"{base}{sep}{suffix}"[:100]


@bot.tree.command(name="تزيين_الرومات", description="يضيف ┊ᴛꜱ لآخر اسم كل روم ما فيه (مثل: تذكرة-شكاوى-┊ᴛꜱ)")
@app_commands.describe(
    الزخرفة="اللي ينضاف آخر الاسم (الافتراضي: ┊ ᴛꜱ)",
    الصوتية="تشمل الرومات الصوتية؟",
    الكاتيجوري="تشمل الكاتيجوري؟",
    تجربة="يعرض لك وش بيتغير بدون ما يغيّر شي",
)
@app_commands.choices(
    الصوتية=[app_commands.Choice(name="نعم", value=1), app_commands.Choice(name="لا", value=0)],
    الكاتيجوري=[app_commands.Choice(name="نعم", value=1), app_commands.Choice(name="لا", value=0)],
    تجربة=[app_commands.Choice(name="نعم، وريني بس", value=1)],
)
async def decorate_channels(inter: discord.Interaction, الزخرفة: str = "┊ ᴛꜱ",
                            الصوتية: app_commands.Choice[int] = None, الكاتيجوري: app_commands.Choice[int] = None,
                            تجربة: app_commands.Choice[int] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    suffix = الزخرفة.strip() or "┊ ᴛꜱ"
    voice = الصوتية is None or الصوتية.value == 1
    cats = bool(الكاتيجوري and الكاتيجوري.value == 1)
    targets = []
    for ch in inter.guild.channels:
        if isinstance(ch, discord.CategoryChannel) and not cats:
            continue
        if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) and not voice:
            continue
        # أي روم مزخرف من قبل (فيه ┊ أو ᴛꜱ) نخليه بشكله ولا نلمسه
        if ch.name == BACKUP_CH_NAME or suffix in ch.name or "┊" in ch.name or "ᴛꜱ" in ch.name:
            continue
        text_like = isinstance(ch, (discord.TextChannel, discord.ForumChannel))
        # الرومات الكتابية ما تقبل مسافة عادية، فنحط مسافة خاصة تبين مثل المسافة
        suf = suffix.replace(" ", "\u2005") if text_like else suffix
        new = decorated_name(ch.name, suf, "-" if text_like else " ", False)
        if new != ch.name:
            targets.append((ch, new))
    if not targets:
        return await inter.response.send_message(embed=embed("✨ تزيين الرومات", "كل الرومات فيها الزخرفة من قبل ✅"), ephemeral=True)
    preview = "\n".join(f"• {c.name} ← **{n}**" for c, n in targets[:25]) + (f"\n… و {len(targets) - 25} غيرها" if len(targets) > 25 else "")
    if تجربة:
        return await inter.response.send_message(embed=embed(f"👀 تجربة ({len(targets)} روم)", preview[:4000]), ephemeral=True)
    await inter.response.send_message(f"✨ أزيّن **{len(targets)}** روم... (تقريبًا {max(1, len(targets) * 2 // 60)} دقيقة)")
    status = await inter.original_response()

    async def run():
        done, failed = 0, 0
        for c, n in targets:
            try:
                await c.edit(name=n, reason=f"تزيين الرومات بواسطة {inter.user}")
                done += 1
            except discord.HTTPException:
                failed += 1
            await asyncio.sleep(1.5)
        try:
            await status.edit(content=f"✅ تم تزيين **{done}** روم" + (f" · ❌ {failed} ما قدرت" if failed else ""))
        except discord.HTTPException:
            pass
    asyncio.create_task(run())


async def auto_server_snapshot():
    """كل 24 ساعة يحدّث نسخة كل سيرفر (تنحفظ مع النسخة الاحتياطية)"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        for g in bot.guilds:
            try:
                if not g.chunked:
                    await g.chunk()
                save_snapshot(g.id, make_server_snapshot(g))
            except Exception as ex:  # noqa
                print("snapshot error:", ex)
        await asyncio.sleep(24 * 3600)


@bot.event
async def on_guild_join(guild: discord.Guild):
    """لما البوت يدخل سيرفر جديد (مثل السيرفر البديل) ترسل الأوامر له على طول"""
    print(f"✅ دخلت سيرفر جديد: {guild.name} (الأوامر العامة تطلع فيه لحالها)")


# ============================================================
# 🛡️ نظام الحماية (ضد التهكير والتخريب والسبام)
# ============================================================
import collections

db.execute("CREATE TABLE IF NOT EXISTS prot_whitelist (guild_id INTEGER, target_id INTEGER, kind TEXT, PRIMARY KEY (guild_id, target_id))")
db.commit()

PROT_WINDOW = 60          # ثانية
_prot_hits = collections.defaultdict(collections.deque)      # (gid, uid, kind) -> أوقات
_deleted_channels = collections.defaultdict(lambda: collections.deque(maxlen=60))  # gid -> (وقت, نسخة الروم)
_deleted_roles = collections.defaultdict(lambda: collections.deque(maxlen=60))
_spam = collections.defaultdict(collections.deque)
_banned_by = collections.defaultdict(list)   # (gid, uid) -> اللي حظرهم
_punished = {}            # (gid, uid) -> وقت (عشان ما نعاقب نفس الشخص مرتين ورا بعض)
DANGER_PERMS = ("administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members",
                "kick_members", "manage_webhooks", "mention_everyone")


def prot(gid: int, key: str, default: int = 0) -> int:
    v = get_setting(gid, key)
    return v if v else default


def prot_on(gid: int) -> bool:
    return get_setting(gid, "prot_on") == 1


def is_trusted(guild: discord.Guild, uid: int) -> bool:
    if uid in (guild.owner_id, bot.user.id if bot.user else 0):
        return True
    rows = {r[0] for r in db.execute("SELECT target_id FROM prot_whitelist WHERE guild_id = ?", (guild.id,)).fetchall()}
    if uid in rows:
        return True
    m = guild.get_member(uid)
    return bool(m and any(r.id in rows for r in m.roles))


def _hit(gid: int, uid: int, kind: str, window: int = PROT_WINDOW) -> int:
    q = _prot_hits[(gid, uid, kind)]
    t = now().timestamp()
    q.append(t)
    while q and t - q[0] > window:
        q.popleft()
    return len(q)


async def prot_alert(guild: discord.Guild, text: str):
    await log("🛡️ **الحماية:** " + text, guild)
    try:
        owner = guild.owner or (await guild.fetch_member(guild.owner_id) if guild.owner_id else None)
        if owner:
            await owner.send(embed=embed("🛡️ تنبيه حماية", f"**{guild.name}**\n{text}"))
    except discord.HTTPException:
        pass


async def prot_punish(guild: discord.Guild, uid: int, reason: str):
    key = (guild.id, uid)
    if now().timestamp() - _punished.get(key, 0) < 30:
        return
    _punished[key] = now().timestamp()
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except discord.HTTPException:
            member = None
    mode = get_text(guild.id, "prot_punish", "strip")
    done = "ما قدرت أعاقبه (رتبته فوق رتبة البوت)"
    try:
        if member and member.bot:
            await guild.ban(member, reason=f"الحماية: {reason}", delete_message_seconds=0)
            done = "انحظر (بوت)"
        elif mode == "ban":
            await guild.ban(discord.Object(id=uid), reason=f"الحماية: {reason}", delete_message_seconds=0)
            done = "انحظر"
        elif mode == "kick" and member:
            await member.kick(reason=f"الحماية: {reason}")
            done = "انطرد"
        elif member:
            removable = [r for r in member.roles if not r.is_default() and not r.managed and r < guild.me.top_role]
            await member.remove_roles(*removable, reason=f"الحماية: {reason}")
            done = f"انسحبت منه كل رتبه ({len(removable)}) فراحت صلاحياته (الرتب نفسها ما تغيّرت)"
    except discord.HTTPException:
        pass
    await prot_alert(guild, f"<@{uid}> {reason}\n**العقوبة:** {done}")


async def prot_restore(guild: discord.Guild, uid: int):
    """نرجّع اللي خرّبه آخر دقيقتين: الرومات والرتب المحذوفة، ونحذف اللي سوّاه"""
    t = now().timestamp()
    roles_back = 0
    for when, data in list(_deleted_roles[guild.id]):
        if data["by"] != uid or t - when > 120:
            continue
        try:
            await guild.create_role(name=data["name"], permissions=discord.Permissions(data["perms"]),
                                    colour=discord.Colour(data["color"]), hoist=data["hoist"],
                                    mentionable=data["mentionable"], reason="الحماية: استرجاع")
            roles_back += 1
        except discord.HTTPException:
            pass
        _deleted_roles[guild.id].remove((when, data))
    chans_back = 0
    for when, data in sorted(list(_deleted_channels[guild.id]), key=lambda x: x[1]["position"]):
        if data["by"] != uid or t - when > 120:
            continue
        cat = guild.get_channel(data["category_id"]) if data["category_id"] else None
        ow = {}
        for tid, (allow, deny) in data["overwrites"].items():
            tgt = guild.get_role(tid) or guild.get_member(tid)
            if tgt:
                ow[tgt] = discord.PermissionOverwrite.from_pair(discord.Permissions(allow), discord.Permissions(deny))
        try:
            if data["type"] == "category":
                await guild.create_category(data["name"], overwrites=ow, position=data["position"])
            elif data["type"] == "voice":
                await guild.create_voice_channel(data["name"], category=cat, overwrites=ow, position=data["position"])
            else:
                await guild.create_text_channel(data["name"], category=cat, overwrites=ow, position=data["position"],
                                                topic=data.get("topic") or None)
            chans_back += 1
        except discord.HTTPException:
            pass
        _deleted_channels[guild.id].remove((when, data))
        await asyncio.sleep(0.4)
    if roles_back or chans_back:
        await prot_alert(guild, f"♻️ رجّعت **{chans_back}** روم و **{roles_back}** رتبة انحذفت من <@{uid}>")


@bot.event
async def on_guild_channel_delete(channel):
    _deleted_channels[channel.guild.id].append((now().timestamp(), {
        "id": channel.id, "name": channel.name, "position": channel.position, "by": 0,
        "type": "category" if isinstance(channel, discord.CategoryChannel) else
                "voice" if isinstance(channel, discord.VoiceChannel) else "text",
        "category_id": getattr(channel, "category_id", None), "topic": getattr(channel, "topic", None),
        "overwrites": {t.id: tuple(p.value for p in ow.pair()) for t, ow in channel.overwrites.items()},
    }))


@bot.event
async def on_guild_role_delete(role):
    _deleted_roles[role.guild.id].append((now().timestamp(), {
        "id": role.id, "name": role.name, "perms": role.permissions.value, "color": role.color.value,
        "hoist": role.hoist, "mentionable": role.mentionable, "by": 0}))


def _mark_by(store, gid: int, target_id: int, uid: int):
    for _, d in store[gid]:
        if d["id"] == target_id:
            d["by"] = uid


@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
    guild = entry.guild
    if not prot_on(guild.id) or entry.user_id is None:
        return
    uid = entry.user_id
    A = discord.AuditLogAction
    act = entry.action
    if act == A.channel_delete:
        await asyncio.sleep(0.5)
        _mark_by(_deleted_channels, guild.id, entry.target.id, uid)
    elif act == A.role_delete:
        await asyncio.sleep(0.5)
        _mark_by(_deleted_roles, guild.id, entry.target.id, uid)
    if is_trusted(guild, uid):
        return
    limit = prot(guild.id, "prot_limit", 3)
    names = {A.channel_delete: "حذف رومات", A.channel_create: "إنشاء رومات", A.role_delete: "حذف رتب",
             A.role_create: "إنشاء رتب", A.ban: "حظر أعضاء", A.kick: "طرد أعضاء"}

    if act in names:
        if act == A.ban and entry.target:
            _banned_by[(guild.id, uid)].append(entry.target.id)
        if act in (A.ban, A.kick):  # الطرد والحظر: أكثر من 3 في اليوم
            day_limit = prot(guild.id, "prot_kick_limit", 3)
            hit = _hit(guild.id, uid, "kickban", 24 * 3600) > day_limit
            why = f"{names[act]} أكثر من {day_limit} في اليوم"
        else:
            hit = _hit(guild.id, uid, act.name) >= limit
            why = f"حاول **{names[act]}** ({limit} مرات بدقيقة)"
        if hit:
            _prot_hits.pop((guild.id, uid, "kickban"), None)
            await prot_punish(guild, uid, why)
            await prot_restore(guild, uid)
            unb = 0
            for vid in _banned_by.pop((guild.id, uid), []):  # نفك الحظر عن اللي حظرهم
                try:
                    await guild.unban(discord.Object(id=vid), reason="الحماية: حظر بدون حق")
                    unb += 1
                except discord.HTTPException:
                    pass
            if unb:
                await prot_alert(guild, f"♻️ فكيت الحظر عن **{unb}** عضو حظرهم <@{uid}>")
    elif act == A.member_prune:
        await prot_punish(guild, uid, "سوّى **Prune** (طرد جماعي)")
    elif act == A.bot_add:
        try:
            await guild.kick(entry.target, reason="الحماية: بوت انضاف بدون إذن")
        except discord.HTTPException:
            pass
        await prot_punish(guild, uid, f"ضاف بوت بدون إذن ({entry.target}) وانطرد البوت")
    elif act == A.webhook_create:
        try:
            for wh in await guild.webhooks():
                if wh.id == entry.target.id:
                    await wh.delete(reason="الحماية")
        except discord.HTTPException:
            pass
        if _hit(guild.id, uid, "webhook") >= 2:
            await prot_punish(guild, uid, "سوّى ويب هوك أكثر من مرة")
        else:
            await prot_alert(guild, f"<@{uid}> سوّى ويب هوك، وحذفته")
    elif act == A.role_update:
        before, after = entry.before, entry.after
        bp, ap = getattr(before, "permissions", None), getattr(after, "permissions", None)
        if bp is not None and ap is not None:
            added = [p for p in DANGER_PERMS if getattr(ap, p) and not getattr(bp, p)]
            if added:
                role = guild.get_role(entry.target.id)
                try:
                    if role:
                        await role.edit(permissions=bp, reason="الحماية: صلاحية خطيرة")
                except discord.HTTPException:
                    pass
                await prot_punish(guild, uid, f"عطى رتبة صلاحيات خطيرة ({', '.join(added)}) ورجّعتها")
    elif act == A.member_role_update:
        added = getattr(entry.after, "roles", []) or []
        danger = [r for r in added if isinstance(r, discord.Role) and r.permissions.administrator]
        if danger:
            target = guild.get_member(entry.target.id)
            try:
                if target and target.id != guild.owner_id:
                    await target.remove_roles(*danger, reason="الحماية: رتبة أدمن بدون إذن")
            except discord.HTTPException:
                pass
            await prot_punish(guild, uid, f"عطى {entry.target} رتبة أدمن ({', '.join(r.name for r in danger)}) وشلتها")


@bot.event
async def on_member_join(member: discord.Member):
    gid = member.guild.id
    if prot_on(gid) and not member.bot:
        days = get_setting(gid, "prot_newacc")
        if days and (now() - member.created_at).days < days:
            try:
                await member.send(embed=embed("🛡️ الحماية", f"حسابك جديد مرة. لازم يكون عمر حسابك {days} أيام على الأقل عشان تدخل **{member.guild.name}**."))
            except discord.HTTPException:
                pass
            try:
                await member.kick(reason=f"الحماية: حساب جديد (أقل من {days} أيام)")
                await log(f"🛡️ طردت {member} لأن حسابه جديد", member.guild)
                return
            except discord.HTTPException:
                pass
    if await apply_restored_member(member):
        return  # رجعت له رتبه القديمة
    await give_auto_roles(member)


AUTO_ROLE_KEYS = {"human": ("auto_human1", "auto_human2", "auto_human3"), "bot": ("auto_bot1", "auto_bot2")}


def auto_roles_for(guild: discord.Guild, is_bot: bool):
    keys = AUTO_ROLE_KEYS["bot" if is_bot else "human"]
    return [r for r in (guild.get_role(get_setting(guild.id, k)) for k in keys) if r]


async def give_auto_roles(member: discord.Member):
    roles = [r for r in auto_roles_for(member.guild, member.bot)
             if r not in member.roles and r < member.guild.me.top_role and not r.managed]
    if not roles:
        return
    try:
        await member.add_roles(*roles, reason="رتب تلقائية")
    except discord.HTTPException:
        await log(f"⚠️ ما قدرت أعطي {member.mention} الرتب التلقائية. خل رتبة البوت فوقها.", member.guild)


@bot.tree.command(name="تسطيب_الرتب_التلقائية", description="رتب تنعطى تلقائي لأي شخص أو بوت يدخل السيرفر")
@app_commands.describe(
    الأعضاء="رتبة تنعطى لكل شخص يدخل", الأعضاء_2="رتبة ثانية للأشخاص (اختياري)", الأعضاء_3="رتبة ثالثة للأشخاص (اختياري)",
    البوتات="رتبة تنعطى لكل بوت يدخل", البوتات_2="رتبة ثانية للبوتات (اختياري)",
    للموجودين="تعطيها الحين للي داخل السيرفر من قبل وما عندهم إياها؟", حذف="تشيل كل الرتب التلقائية",
)
@app_commands.choices(للموجودين=[app_commands.Choice(name="نعم", value=1)], حذف=[app_commands.Choice(name="نعم", value=1)])
async def setup_auto_roles(inter: discord.Interaction, الأعضاء: discord.Role = None, الأعضاء_2: discord.Role = None,
                           الأعضاء_3: discord.Role = None, البوتات: discord.Role = None, البوتات_2: discord.Role = None,
                           للموجودين: app_commands.Choice[int] = None, حذف: app_commands.Choice[int] = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    gid = inter.guild.id
    if حذف:
        for k in AUTO_ROLE_KEYS["human"] + AUTO_ROLE_KEYS["bot"]:
            set_setting(gid, k, 0)
    for key, role in zip(AUTO_ROLE_KEYS["human"] + AUTO_ROLE_KEYS["bot"], (الأعضاء, الأعضاء_2, الأعضاء_3, البوتات, البوتات_2)):
        if role:
            set_setting(gid, key, role.id)
    humans, bots_ = auto_roles_for(inter.guild, False), auto_roles_for(inter.guild, True)
    warn = [r.mention for r in humans + bots_ if r >= inter.guild.me.top_role]
    text = (f"**👤 الأشخاص:** {' '.join(r.mention for r in humans) or 'ما فيه'}\n"
            f"**🤖 البوتات:** {' '.join(r.mention for r in bots_) or 'ما فيه'}\n\n"
            "أي أحد يدخل السيرفر ياخذ رتبه لحاله ✅")
    if warn:
        text += f"\n\n⚠️ هذي الرتب فوق رتبة البوت وما يقدر يعطيها: {' '.join(warn)}\nارفع رتبة البوت فوقها."
    if not للموجودين:
        return await inter.response.send_message(embed=embed("🎭 الرتب التلقائية", text), ephemeral=True)
    await inter.response.send_message(embed=embed("🎭 الرتب التلقائية", text + "\n\n⏳ أعطيها للموجودين الحين..."), ephemeral=True)
    if not inter.guild.chunked:
        await inter.guild.chunk()
    n = 0
    for m in inter.guild.members:
        need = [r for r in auto_roles_for(inter.guild, m.bot) if r not in m.roles and r < inter.guild.me.top_role]
        if need:
            try:
                await m.add_roles(*need, reason="رتب تلقائية")
                n += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.7)
    try:
        await inter.followup.send(f"✅ عطيت الرتب لـ **{n}** من الموجودين.", ephemeral=True)
    except discord.HTTPException:
        pass


INVITE_RE = re.compile(r"(discord\.gg/|discord(app)?\.com/invite/)", re.I)


async def prot_message(message: discord.Message) -> bool:
    """سبام + روابط سيرفرات + منشن كثير. يرجع True لو انحذفت الرسالة"""
    gid = message.guild.id
    if not prot_on(gid) or is_trusted(message.guild, message.author.id) or is_power(message.author):
        return False
    if get_setting(gid, "prot_links") != 2 and INVITE_RE.search(message.content):
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention} ممنوع روابط السيرفرات 🚫", delete_after=5)
        except discord.HTTPException:
            pass
        return True
    if len(message.raw_mentions) + len(message.raw_role_mentions) >= 6 or message.mention_everyone:
        try:
            await message.delete()
            await message.author.timeout(timedelta(minutes=10), reason="الحماية: منشن كثير")
            await message.channel.send(f"{message.author.mention} انسكت 10 دقايق بسبب المنشن الكثير 🔇", delete_after=8)
        except discord.HTTPException:
            pass
        return True
    q = _spam[(gid, message.author.id)]
    t = now().timestamp()
    q.append(t)
    while q and t - q[0] > 5:
        q.popleft()
    if len(q) >= 6:
        q.clear()
        try:
            await message.author.timeout(timedelta(minutes=10), reason="الحماية: سبام")
            await message.channel.send(f"{message.author.mention} انسكت 10 دقايق بسبب السبام 🔇", delete_after=8)
            await message.channel.purge(limit=15, check=lambda m: m.author.id == message.author.id)
        except discord.HTTPException:
            pass
        return True
    return False


@bot.tree.command(name="الحماية", description="تشغيل وتسطيب نظام الحماية (لصاحب السيرفر)")
@app_commands.describe(
    التشغيل="تشغيل أو إطفاء الحماية",
    العقوبة="وش يصير للي يخرّب",
    الحد="كم مرة بالدقيقة (حذف رومات/رتب...) قبل العقوبة - الافتراضي 3",
    حد_الطرد="كم طرد/حظر مسموح في اليوم لكل شخص - الافتراضي 3",
    الروابط="منع روابط السيرفرات الثانية",
    عمر_الحساب="أقل عمر للحساب بالأيام عشان يدخل (0 = بدون)",
)
@app_commands.choices(
    التشغيل=[app_commands.Choice(name="تشغيل ✅", value=1), app_commands.Choice(name="إطفاء ❌", value=2)],
    العقوبة=[app_commands.Choice(name="سحب كل رتبه (تروح صلاحياته هو بس)", value="strip"), app_commands.Choice(name="طرد", value="kick"),
             app_commands.Choice(name="حظر", value="ban")],
    الروابط=[app_commands.Choice(name="ممنوعة ✅", value=1), app_commands.Choice(name="مسموحة ❌", value=2)],
)
async def protection_setup(inter: discord.Interaction, التشغيل: app_commands.Choice[int] = None,
                           العقوبة: app_commands.Choice[str] = None, الحد: app_commands.Range[int, 1, 20] = None,
                           حد_الطرد: app_commands.Range[int, 1, 50] = None,
                           الروابط: app_commands.Choice[int] = None, عمر_الحساب: app_commands.Range[int, 0, 60] = None):
    if inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message(embed=err("الحماية لصاحب السيرفر بس."), ephemeral=True)
    gid = inter.guild.id
    if التشغيل: set_setting(gid, "prot_on", التشغيل.value)
    if العقوبة: set_text(gid, "prot_punish", العقوبة.value)
    if الحد: set_setting(gid, "prot_limit", الحد)
    if حد_الطرد: set_setting(gid, "prot_kick_limit", حد_الطرد)
    if الروابط: set_setting(gid, "prot_links", الروابط.value)
    if عمر_الحساب is not None: set_setting(gid, "prot_newacc", عمر_الحساب)
    pun = {"strip": "سحب كل رتبه", "kick": "طرد", "ban": "حظر"}[get_text(gid, "prot_punish", "strip")]
    wl = db.execute("SELECT target_id, kind FROM prot_whitelist WHERE guild_id = ?", (gid,)).fetchall()
    me = inter.guild.me
    warn = []
    if not me.guild_permissions.administrator:
        warn.append("⚠️ عطني **Administrator** عشان أقدر أحمي السيرفر.")
    if me.top_role.position < len(inter.guild.roles) - 2:
        warn.append("⚠️ ارفع رتبة البوت **فوق كل الرتب**، اللي فوق البوت ما أقدر أعاقبه.")
    await inter.response.send_message(embed=embed("🛡️ نظام الحماية", (
        f"**الحالة:** {'✅ شغالة' if prot_on(gid) else '❌ طافية'}\n"
        f"**العقوبة:** {pun}\n**الحد:** {prot(gid, 'prot_limit', 3)} مرات بالدقيقة\n"
        f"**الطرد والحظر:** أكثر من {prot(gid, 'prot_kick_limit', 3)} في اليوم ← عقوبة\n"
        f"**روابط السيرفرات:** {'مسموحة' if get_setting(gid, 'prot_links') == 2 else 'ممنوعة'}\n"
        f"**عمر الحساب:** {get_setting(gid, 'prot_newacc') or 'بدون'}{' أيام' if get_setting(gid, 'prot_newacc') else ''}\n\n"
        "**وش تحمي:**\n• حذف/إنشاء رومات ورتب بكثرة ← عقوبة + ترجيع اللي انحذف\n"
        "• طرد أو حظر أكثر من الحد في اليوم، Prune ← عقوبة\n• إضافة بوتات ← ينطرد البوت\n• ويب هوك ← ينحذف\n"
        "• إعطاء صلاحيات خطيرة أو رتبة أدمن ← ترجع + عقوبة\n• سبام، منشن كثير، روابط ← حذف + إسكات\n\n"
        f"**المستثنين ({len(wl)}):** " + (" ".join(f"<@&{t}>" if k == "role" else f"<@{t}>" for t, k in wl) or "لا أحد")
        + "\nأضف الناس اللي تثق فيهم بـ /استثناء_الحماية"
        + ("\n\n" + "\n".join(warn) if warn else ""))), ephemeral=True)


@bot.tree.command(name="استثناء_الحماية", description="تضيف أو تشيل شخص/رتبة من الاستثناء (يقدرون يعدّلون بدون عقوبة)")
@app_commands.describe(العضو="شخص تثق فيه", الرتبة="رتبة تثق فيها", شيل="اختر نعم عشان تشيله من الاستثناء")
@app_commands.choices(شيل=[app_commands.Choice(name="نعم", value=1)])
async def protection_whitelist(inter: discord.Interaction, العضو: discord.Member = None, الرتبة: discord.Role = None,
                               شيل: app_commands.Choice[int] = None):
    if inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message(embed=err("الاستثناء لصاحب السيرفر بس."), ephemeral=True)
    if not العضو and not الرتبة:
        return await inter.response.send_message(embed=err("اختر عضو أو رتبة."), ephemeral=True)
    for t, kind in ((العضو, "user"), (الرتبة, "role")):
        if t is None:
            continue
        if شيل:
            db.execute("DELETE FROM prot_whitelist WHERE guild_id = ? AND target_id = ?", (inter.guild.id, t.id))
        else:
            db.execute("INSERT OR REPLACE INTO prot_whitelist VALUES (?, ?, ?)", (inter.guild.id, t.id, kind))
    db.commit()
    who = " ".join(x.mention for x in (العضو, الرتبة) if x)
    await inter.response.send_message(embed=embed("🛡️ الاستثناء", f"{'🗑️ انشال' if شيل else '✅ انضاف'} {who}"), ephemeral=True)


# ============================================================
# إضافة إيموجيات كثيرة مرة وحدة (من سيرفرات ثانية، متحركة وعادية)
# ============================================================
EMOJI_TAG_RE = re.compile(r"<(a?):([A-Za-z0-9_~]{1,32}):(\d{15,21})>")
EMOJI_URL_RE = re.compile(r"cdn\.discordapp\.com/emojis/(\d{15,21})\.(gif|png|webp|jpg)(?:\?[^\s]*)?", re.I)


def parse_emojis(text: str):
    found, seen = [], set()
    for anim, name, eid in EMOJI_TAG_RE.findall(text):
        if eid not in seen:
            seen.add(eid)
            found.append((eid, name, anim == "a"))
    for m_ in EMOJI_URL_RE.finditer(text):
        eid = m_.group(1)
        if eid not in seen:
            seen.add(eid)
            anim = m_.group(2).lower() == "gif" or "animated=true" in m_.group(0).lower()
            found.append((eid, f"emoji_{len(found) + 1}", anim))
    return found


async def add_emojis(guild: discord.Guild, items, status):
    import aiohttp
    added, failed, full = [], 0, 0
    static_left = guild.emoji_limit - sum(1 for e in guild.emojis if not e.animated)
    anim_left = guild.emoji_limit - sum(1 for e in guild.emojis if e.animated)
    async with aiohttp.ClientSession() as http:
        for n, (eid, name, anim) in enumerate(items, 1):
            if (anim and anim_left <= 0) or (not anim and static_left <= 0):
                full += 1
                continue
            url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if anim else 'png'}?quality=lossless"
            try:
                async with http.get(url) as r:
                    data = await r.read() if r.status == 200 else None
                if not data:
                    failed += 1
                    continue
                name = re.sub(r"[^A-Za-z0-9_]", "_", name)[:32]
                name = name if len(name) >= 2 else f"e_{name or eid[-4:]}"
                e = await guild.create_custom_emoji(name=name, image=data, reason="إضافة إيموجيات")
                added.append(str(e))
                if anim:
                    anim_left -= 1
                else:
                    static_left -= 1
            except (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError):
                failed += 1
            if n % 10 == 0:
                try:
                    await status.edit(content=f"⏳ أضيف الإيموجيات... {n}/{len(items)} (انضاف {len(added)})")
                except discord.HTTPException:
                    pass
            await asyncio.sleep(1.2)
    text = f"✅ انضاف **{len(added)}** إيموجي من {len(items)}"
    if full:
        text += (f"\n⚠️ **{full}** ما انضافت لأن خانات السيرفر امتلت "
                 f"(سيرفرك يقبل {guild.emoji_limit} عادي + {guild.emoji_limit} متحرك، والبوستات تزيدها)")
    if failed:
        text += f"\n❌ **{failed}** ما قدرت أضيفها"
    preview = " ".join(added)
    if preview:
        text += "\n\n" + (preview if len(preview) < 1500 else preview[:1500] + " ...")
    try:
        await status.edit(content=text)
    except discord.HTTPException:
        pass


async def emoji_prefix(message: discord.Message):
    """-ايموجي ثم الإيموجيات (أو روابطها) - تقدر تكتب كثير في رسالة وحدة"""
    if not is_power(message.author) and not message.author.guild_permissions.manage_expressions:
        return await message.reply("❌ هذا الأمر للإدارة بس.")
    items = parse_emojis(message.content)
    if not items:
        return await message.reply(
            "❌ ما لقيت إيموجيات.\nاكتب `-ايموجي` وبعدها الإيموجيات (متحركة أو عادية)، أو روابطها.\n"
            "💡 بدون نيترو: اضغط مطوّل على الإيموجي ← **Copy Link** ← والصق الروابط.")
    status = await message.reply(f"⏳ بضيف **{len(items)}** إيموجي... انتظر.")
    asyncio.create_task(add_emojis(message.guild, items, status))


@bot.tree.command(name="اضافة_ايموجيات", description="تضيف إيموجيات كثيرة مرة وحدة من سيرفرات ثانية (متحركة وعادية)")
@app_commands.describe(الإيموجيات="حط الإيموجيات أو روابطها هنا، كثير مرة وحدة")
async def add_emojis_cmd(inter: discord.Interaction, الإيموجيات: str):
    if not admin_only(inter) and not inter.user.guild_permissions.manage_expressions:
        return await inter.response.send_message(embed=err("هذا الأمر للإدارة بس."), ephemeral=True)
    items = parse_emojis(الإيموجيات)
    if not items:
        return await inter.response.send_message(embed=err("ما لقيت إيموجيات. حط الإيموجيات نفسها أو روابطها."), ephemeral=True)
    await inter.response.send_message(f"⏳ بضيف **{len(items)}** إيموجي... انتظر.")
    status = await inter.original_response()
    asyncio.create_task(add_emojis(inter.guild, items, status))


# ============================================================
# دعوة الأعضاء القدام للسيرفر الجديد
# ============================================================
def old_member_ids() -> set:
    ids = set()
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({name})")]
        for c in ("user_id", "owner_id"):
            if c in cols:
                ids.update(r[0] for r in db.execute(f"SELECT DISTINCT {c} FROM {name}").fetchall()
                           if isinstance(r[0], int) and r[0] > 10 ** 15)
    return ids


async def run_old_invites(guild: discord.Guild, owner: discord.abc.User, link: str, text: str, status):
    targets = [i for i in old_member_ids() if guild.get_member(i) is None and i != owner.id
               and not (bot.user and i == bot.user.id)]
    e = embed("🇸🇦 سـعـودي تـايـم رجـع !", (text or
              "حياك الله 💚\nسعودي تايم رجع بسيرفر جديد، ونبيك معنا من جديد 👑\n\n"
              f"**🔗 رابط السيرفر الجديد:**\n{link}\n\nلا تتأخر… المدينة ناقصتك 🔥") + (f"\n\n{link}" if text and link not in text else ""))
    sent, failed = 0, []
    for n, uid in enumerate(targets, 1):
        user = bot.get_user(uid)
        try:
            if user is None:
                user = await bot.fetch_user(uid)
            if user.bot:
                continue
            await user.send(embed=e)
            sent += 1
        except discord.HTTPException:
            failed.append(user or uid)
        if n % 10 == 0:
            try:
                await status.edit(content=f"📨 أرسل للأعضاء القدام... {n}/{len(targets)} (وصل {sent})")
            except discord.HTTPException:
                pass
        await asyncio.sleep(1.5)
    lines = [f"{u.name} ({u.id})" if isinstance(u, (discord.User, discord.Member)) else str(u) for u in failed]
    try:
        await status.edit(content=(
            f"✅ خلصت! وصلت الدعوة لـ **{sent}** عضو من {len(targets)}.\n"
            + (f"📋 **{len(failed)}** ما قدرت أراسلهم (ديسكورد ما يخلي البوت يراسل أحد ما يشاركه سيرفر). "
               "أرسلت لك أسماءهم في الخاص عشان تراسلهم بنفسك." if failed else "")))
    except discord.HTTPException:
        pass
    if failed:
        try:
            await owner.send("📋 الأعضاء القدام اللي ما وصلتهم الدعوة، راسلهم بنفسك أو أضفهم:",
                             file=discord.File(io.BytesIO("\n".join(lines).encode()), filename="old_members.txt"))
        except discord.HTTPException:
            pass


@bot.tree.command(name="دعوة_القدامى", description="يرسل رابط السيرفر الجديد لكل الأعضاء القدام في الخاص")
@app_commands.describe(الرابط="رابط دعوة السيرفر الجديد (خله ما ينتهي)", الرسالة="رسالة خاصة (اختياري)")
async def invite_old_members(inter: discord.Interaction, الرابط: str, الرسالة: str = None):
    if not is_owner(inter):
        return await inter.response.send_message(embed=err("هذا الأمر لصاحب السيرفر بس."), ephemeral=True)
    if "discord" not in الرابط:
        return await inter.response.send_message(embed=err("حط رابط دعوة ديسكورد، مثل: https://discord.gg/xxxx"), ephemeral=True)
    n = len([i for i in old_member_ids() if inter.guild.get_member(i) is None])
    if not n:
        return await inter.response.send_message(embed=err("ما لقيت أعضاء قدام عند البوت (أو كلهم موجودين هنا)."), ephemeral=True)
    await inter.response.send_message(f"📨 بدأت أرسل الدعوة لـ **{n}** عضو قديم... (تاخذ تقريبًا {max(1, n * 2 // 60)} دقيقة)")
    status = await inter.original_response()
    asyncio.create_task(run_old_invites(inter.guild, inter.user, الرابط.strip(), الرسالة, status))


# ============================================================
# -اسم ايدي الاسم_الجديد   |   -ر ايدي ايدي_رتبة ايدي_رتبة ...
# الإدارة في الروم المخصص بس، والأونر في أي مكان
# ============================================================
async def _resolve_member(guild: discord.Guild, raw: str):
    raw = raw.strip("<@!>")
    if not raw.isdigit():
        return None
    m = guild.get_member(int(raw))
    if m is None:
        try:
            m = await guild.fetch_member(int(raw))
        except discord.HTTPException:
            m = None
    return m


def _staff_room_check(message: discord.Message, key: str):
    """يرجع رسالة خطأ لو ما يحق له، أو None"""
    a = message.author
    if has_owner_role(a) or a.id == message.guild.owner_id:
        return None  # الأونر في كل مكان
    if not has_role(a, get_setting(message.guild.id, "role_admin")):
        return "هذا الأمر للإدارة بس."
    ch = get_setting(message.guild.id, key)
    if ch and message.channel.id != ch:
        return f"هذا الأمر في <#{ch}> بس."
    return None


async def rename_prefix(message: discord.Message):
    bad = _staff_room_check(message, "ch_names")
    if bad:
        return await message.reply(f"❌ {bad}")
    parts = message.content.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("❌ الاستخدام: `-اسم ايدي_الشخص الاسم الجديد`")
    member = await _resolve_member(message.guild, parts[1])
    if not member:
        return await message.reply("❌ ما لقيت الشخص. تأكد من الايدي.")
    if member.id != message.author.id and not has_owner_role(message.author) and message.author.id != message.guild.owner_id \
            and staff_level(member) >= staff_level(message.author) and staff_level(member) > 0:
        return await message.reply("❌ رتبته مثلك أو أعلى منك.")
    new = parts[2].strip()[:32]
    old = member.display_name
    try:
        await member.edit(nick=new, reason=f"تغيير اسم بواسطة {message.author}")
    except discord.HTTPException:
        return await message.reply("❌ ما قدرت أغيّر اسمه. خل رتبة البوت فوق رتبته (وصاحب السيرفر ما يتغيّر اسمه).")
    await message.reply(f"✅ تم تغيير اسم {member.mention}\n**من:** {old}\n**إلى:** {new}")
    await log(f"✏️ {message.author.mention} غيّر اسم {member.mention} من **{old}** إلى **{new}**", message.guild)


async def role_prefix(message: discord.Message):
    bad = _staff_room_check(message, "ch_roles_cmd")
    if bad:
        return await message.reply(f"❌ {bad}")
    parts = message.content.split()
    if len(parts) < 3:
        return await message.reply("❌ الاستخدام: `-ر ايدي_الشخص ايدي_الرتبة` (وتقدر تحط أكثر من رتبة)")
    member = await _resolve_member(message.guild, parts[1])
    if not member:
        return await message.reply("❌ ما لقيت الشخص. تأكد من الايدي.")
    is_top = has_owner_role(message.author) or message.author.id == message.guild.owner_id
    added, removed, failed = [], [], []
    for raw in parts[2:]:
        raw = raw.strip("<@&>")
        role = message.guild.get_role(int(raw)) if raw.isdigit() else None
        if role is None or role.is_default() or role.managed:
            failed.append(f"`{raw}` (ما لقيتها)")
            continue
        if role >= message.guild.me.top_role:
            failed.append(f"{role.mention} (فوق رتبة البوت)")
            continue
        if not is_top and (role >= message.author.top_role or role.permissions.administrator):
            failed.append(f"{role.mention} (أعلى من رتبتك)")
            continue
        try:
            if role in member.roles:  # عنده الرتبة ← تنشال
                await member.remove_roles(role, reason=f"بواسطة {message.author}")
                removed.append(role.mention)
            else:
                await member.add_roles(role, reason=f"بواسطة {message.author}")
                added.append(role.mention)
        except discord.HTTPException:
            failed.append(f"{role.mention} (ما قدرت)")
    lines = [f"**العضو:** {member.mention}"]
    if added:
        lines.append(f"✅ **انعطى:** {' '.join(added)}")
    if removed:
        lines.append(f"➖ **انشال:** {' '.join(removed)}")
    if failed:
        lines.append(f"❌ **ما تم:** {'، '.join(failed)}")
    await message.reply("\n".join(lines))
    if added or removed:
        await log(f"🎭 {message.author.mention} عدّل رتب {member.mention}: "
                  f"{'+ ' + ' '.join(added) if added else ''} {'- ' + ' '.join(removed) if removed else ''}", message.guild)


@bot.tree.command(name="تسطيب_روم_الادوار", description="تحدد الروم اللي الإدارة تستخدم فيه -ر و -اسم (الأونر في كل مكان)")
@app_commands.describe(روم_الرتب="الروم اللي يشتغل فيه -ر", روم_الاسماء="الروم اللي يشتغل فيه -اسم")
async def setup_role_rooms(inter: discord.Interaction, روم_الرتب: discord.TextChannel = None,
                           روم_الاسماء: discord.TextChannel = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    if روم_الرتب:
        set_setting(inter.guild.id, "ch_roles_cmd", روم_الرتب.id)
    if روم_الاسماء:
        set_setting(inter.guild.id, "ch_names", روم_الاسماء.id)
    r, n = get_setting(inter.guild.id, "ch_roles_cmd"), get_setting(inter.guild.id, "ch_names")
    await inter.response.send_message(embed=embed("🎭 روم الأدوار", (
        f"**`-ر` :** {f'<#{r}>' if r else 'أي روم'}\n**`-اسم` :** {f'<#{n}>' if n else 'أي روم'}\n\n"
        "الإدارة تستخدمها في الروم المحدد بس، والأونر في أي مكان 👑")), ephemeral=True)


# ============================================================
# 🎖️ التسجيل العسكري: زر يحسب المسجلين ويعطيهم رتبة، وكل دورة لها عدد
# لما تكتمل الدورة: يمنشن المسجلين ويقفلها ويفتح دورة جديدة
# ============================================================
db.execute("CREATE TABLE IF NOT EXISTS enlist (message_id INTEGER, user_id INTEGER, created_at TEXT, PRIMARY KEY (message_id, user_id))")
try:
    db.execute("ALTER TABLE enlist ADD COLUMN batch INTEGER DEFAULT 1")
except sqlite3.OperationalError:
    pass
db.execute("CREATE TABLE IF NOT EXISTS enlist_panels (message_id INTEGER PRIMARY KEY, guild_id INTEGER, role_id INTEGER, cap INTEGER, batch INTEGER)")
db.commit()


def enlist_panel_row(mid: int):
    r = db.execute("SELECT * FROM enlist_panels WHERE message_id = ?", (mid,)).fetchone()
    return (r["cap"], r["batch"]) if r else (30, 1)


def enlist_batch_ids(mid: int, batch: int):
    return [r[0] for r in db.execute("SELECT user_id FROM enlist WHERE message_id = ? AND batch = ? ORDER BY created_at",
                                     (mid, batch)).fetchall()]


def enlist_view(role_id: int, count: int, cap: int = 30) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label=f"تسجيل ({count}/{cap})", emoji="🎖️", style=discord.ButtonStyle.success,
                                 custom_id=f"enlist:join:{role_id}"))
    v.add_item(discord.ui.Button(label="المسجلين", emoji="📋", style=discord.ButtonStyle.secondary,
                                 custom_id=f"enlist:list:{role_id}"))
    v.add_item(discord.ui.Button(label="منشن الدورة", emoji="📣", style=discord.ButtonStyle.primary,
                                 custom_id=f"enlist:ping:{role_id}"))
    return v


def _enlist_embed(e: discord.Embed, count: int, cap: int = 30, batch: int = 1) -> discord.Embed:
    e = e.copy()
    e.clear_fields()
    e.add_field(name="🪖 الدورة", value=f"**رقم {batch}**")
    e.add_field(name="👥 المسجلين", value=f"**{count} / {cap}**")
    return e


@bot.tree.command(name="تسجيل_عسكري", description="لوحة تسجيل عسكري: اللي يضغط ياخذ رتبة، وكل ما تكتمل الدورة يمنشنهم ويفتح دورة جديدة")
@app_commands.describe(الروم="الروم اللي تنرسل فيه اللوحة", الرتبة="الرتبة اللي تنعطى للي يسجل (مثل: طالب تحت تدريب)",
                       العدد="كم شخص في كل دورة (الافتراضي 30)",
                       الوصف="الكلام اللي في اللوحة", العنوان="عنوان اللوحة (الافتراضي: تسجيل عسكري)",
                       الصورة="صورة للوحة (اختياري)")
async def enlist_panel(inter: discord.Interaction, الروم: discord.TextChannel, الرتبة: discord.Role,
                       العدد: app_commands.Range[int, 1, 200] = 30, الوصف: str = None, العنوان: str = None,
                       الصورة: discord.Attachment = None):
    if not admin_only(inter):
        return await inter.response.send_message(embed=err("هذا الأمر للأدمن والأونر بس."), ephemeral=True)
    if الرتبة >= inter.guild.me.top_role:
        return await inter.response.send_message(embed=err(f"{الرتبة.mention} فوق رتبة البوت. ارفع رتبة البوت فوقها."), ephemeral=True)
    e = embed(f"🎖️ - {العنوان or 'تـسـجـيـل عـسـكـري'}", (الوصف or
              "- باب التسجيل العسكري مفتوح الحين 🪖\n\nاضغط زر **تسجيل** عشان تنضم للدورة، وتاخذ رتبة "
              f"{الرتبة.mention} وتبدأ تدريبك ."))
    e = _enlist_embed(e, 0, العدد, 1)
    kw = {}
    if الصورة and (الصورة.content_type or "").startswith("image/"):
        kw["file"] = await الصورة.to_file()
        e.set_image(url=f"attachment://{kw['file'].filename}")
    try:
        msg = await الروم.send(embed=e, view=enlist_view(الرتبة.id, 0, العدد), **kw)
    except discord.HTTPException:
        return await inter.response.send_message(embed=err(f"ما أقدر أرسل في {الروم.mention}."), ephemeral=True)
    db.execute("INSERT OR REPLACE INTO enlist_panels VALUES (?, ?, ?, ?, 1)", (msg.id, inter.guild.id, الرتبة.id, العدد))
    db.commit()
    await inter.response.send_message(embed=embed("✅ انرسلت لوحة التسجيل", f"{الروم.mention}\nكل دورة **{العدد}** شخص."), ephemeral=True)


async def handle_enlist(inter: discord.Interaction, cid: str):
    _, action, rid = cid.split(":")
    role = inter.guild.get_role(int(rid))
    mid = inter.message.id
    cap, batch = enlist_panel_row(mid)
    if action in ("list", "ping"):
        if not has_role(inter.user, get_setting(inter.guild.id, "role_admin")):
            return await inter.response.send_message(embed=err("هذا الزر للإدارة بس."), ephemeral=True)
        ids = enlist_batch_ids(mid, batch)
        if action == "list":
            text = "\n".join(f"{i}. <@{u}>" for i, u in enumerate(ids, 1)) or "ما أحد سجّل في هالدورة للحين."
            return await inter.response.send_message(embed=embed(f"📋 مسجلين الدورة {batch} ({len(ids)}/{cap})", text[:4000]),
                                                     ephemeral=True)
        if not ids:
            return await inter.response.send_message(embed=err("ما أحد سجّل في هالدورة للحين."), ephemeral=True)
        await inter.response.send_message(f"📣 **مسجلين الدورة رقم {batch}** ({len(ids)}):\n" + " ".join(f"<@{u}>" for u in ids))
        return
    if role is None:
        return await inter.response.send_message(embed=err("رتبة التسجيل انحذفت. خل الإدارة ترسل اللوحة من جديد."), ephemeral=True)
    if db.execute("SELECT 1 FROM enlist WHERE message_id = ? AND user_id = ?", (mid, inter.user.id)).fetchone() \
            or role in inter.user.roles:
        return await inter.response.send_message(embed=err("أنت مسجّل من قبل ✅"), ephemeral=True)
    try:
        await inter.user.add_roles(role, reason="تسجيل عسكري")
    except discord.HTTPException:
        return await inter.response.send_message(embed=err("ما قدرت أعطيك الرتبة. خل الإدارة ترفع رتبة البوت."), ephemeral=True)
    db.execute("INSERT OR IGNORE INTO enlist (message_id, user_id, created_at, batch) VALUES (?, ?, ?, ?)",
               (mid, inter.user.id, now().isoformat(), batch))
    db.commit()
    ids = enlist_batch_ids(mid, batch)
    count = len(ids)
    e = inter.message.embeds[0] if inter.message.embeds else embed("🎖️ تسجيل عسكري")
    full = count >= cap
    if full:  # اكتملت الدورة ← دورة جديدة
        db.execute("INSERT OR REPLACE INTO enlist_panels VALUES (?, ?, ?, ?, ?)", (mid, inter.guild.id, role.id, cap, batch + 1))
        db.commit()
        await inter.response.edit_message(embed=_enlist_embed(e, 0, cap, batch + 1), view=enlist_view(role.id, 0, cap))
    else:
        await inter.response.edit_message(embed=_enlist_embed(e, count, cap, batch), view=enlist_view(role.id, count, cap))
    await inter.followup.send(embed=embed("🎖️ تم تسجيلك", f"أخذت رتبة {role.mention}\nأنت رقم **{count}** في الدورة **{batch}** 🪖"),
                              ephemeral=True)
    await log(f"🎖️ {inter.user.mention} سجّل في الدورة {batch} وأخذ {role.mention} ({count}/{cap})", inter.guild)
    if full:
        try:
            await inter.channel.send(
                f"🔒 **اكتملت الدورة رقم {batch}** ({cap} متدرب) وانقفل التسجيل فيها 🎖️\n"
                + " ".join(f"<@{u}>" for u in ids)
                + f"\n\n✅ انفتح التسجيل للدورة رقم **{batch + 1}**")
        except discord.HTTPException:
            pass


@bot.event
async def on_interaction(inter: discord.Interaction):
    if inter.type == discord.InteractionType.modal_submit and inter.guild \
            and (inter.data or {}).get("custom_id") == "news:modal":
        return await news_submit(inter)
    if inter.type != discord.InteractionType.component or not inter.guild:
        return
    cid = (inter.data or {}).get("custom_id", "")
    if cid == "ticket:open":
        values = inter.data.get("values") or []
        if values:
            await open_ticket(inter, int(values[0]))
        try:  # نرجّع المنيو فاضي بنفس التذاكر اللي كانت فيه
            keep = [int(o.value) for row in inter.message.components for c in getattr(row, "children", [])
                    for o in getattr(c, "options", [])]
            await inter.message.edit(view=ticket_select(inter.guild.id, keep or None))
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
    elif cid == "mdt:menu":
        choice = (inter.data.get("values") or ["reset"])[0]
        if choice == "reset":
            return await inter.response.edit_message(view=mdt_view())
        await handle_points_interaction(inter, f"mdt:{choice}")
        try:
            await inter.message.edit(view=mdt_view())
        except discord.HTTPException:
            pass
    elif cid.startswith("pts:") or cid.startswith("mdt:"):
        await handle_points_interaction(inter, cid)
    elif cid.startswith("enlist:"):
        await handle_enlist(inter, cid)
    elif cid == "news:open":
        await news_open(inter)
    elif cid == "rules:open":
        await handle_rules(inter)
    elif cid == "bank:menu":
        choice = (inter.data.get("values") or ["reset"])[0]
        if choice == "reset":
            return await inter.response.edit_message(view=bank_view())
        await handle_bank(inter, choice)
        try:
            await inter.message.edit(view=bank_view())
        except discord.HTTPException:
            pass
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
