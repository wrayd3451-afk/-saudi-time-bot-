# بوت نظام VRP لسيرفرات الرول بلاي

بوت دسكورد فيه: هوية، بنك، وظائف ورواتب، مخالفات، سجل جنائي، متجر وشنطة، وأوامر للشرطة والإدارة.

## الملفات
- `bot.py`: كود البوت
- `config.py`: الإعدادات (الرتب، الوظائف والرواتب، أغراض المتجر، فلوس البداية)
- `.env.example`: مكان التوكن وآيدي السيرفر
- `requirements.txt`: المكتبات المطلوبة

## خطوات التشغيل

### 1) سوّ البوت في موقع دسكورد
1. ادخل https://discord.com/developers/applications واضغط **New Application**.
2. من قسم **Bot** اضغط **Reset Token** وانسخ التوكن. لا تعطيه أحد.
3. في نفس الصفحة فعّل **Server Members Intent**.
4. من **OAuth2 → URL Generator** اختر `bot` و `applications.commands`، وفي الصلاحيات اختر **Manage Roles** و **Send Messages** و **Embed Links**. افتح الرابط وضيف البوت لسيرفرك.
5. في إعدادات الرتب بالسيرفر، خل رتبة البوت **فوق** رتب الوظائف والمواطن عشان يقدر يعطيها.

### 2) جهّز جهازك
1. نزّل بايثون من https://python.org (نسخة 3.10 أو أحدث). وقت التثبيت علّم على **Add Python to PATH**.
2. افتح مجلد البوت، واكتب في الـ Terminal أو CMD:
   ```
   pip install -r requirements.txt
   ```

### 3) حط بياناتك
1. غيّر اسم `.env.example` إلى `.env`.
2. حط التوكن وآيدي السيرفر فيه.
3. افتح `config.py` وحط آيدي الرتب (الإدارة، الشرطة، المواطن) وروم اللوق.

**طريقة نسخ الآيدي:** في دسكورد روح الإعدادات ← Advanced ← فعّل **Developer Mode**. بعدها كليك يمين (أو ضغطة مطوّلة في الجوال) على السيرفر أو الرتبة أو الروم واختر **Copy ID**.

### 4) شغّل البوت
```
python bot.py
```
إذا طلع لك `✅ البوت شغال` يعني تمام، والأوامر تظهر بالسيرفر إذا كتبت `/`.

## الأوامر

| القسم | الأوامر |
|---|---|
| الهوية | /هوية_جديدة · /هويتي |
| البنك | /رصيدي · /ايداع · /سحب · /تحويل · /اعطاء_كاش · /الاغنى |
| الوظائف | /الوظائف · /راتب |
| المتجر | /المتجر · /شراء · /شنطتي · /اعطاء_غرض |
| المخالفات | /مخالفاتي · /سداد_مخالفة |
| الشرطة | /مخالفة · /اضافة_سجل · /سجل · /تفتيش · /هوية |
| الإدارة | /تعيين_وظيفة · /اضافة_فلوس · /خصم_فلوس · /مسح_سجل · /حذف_هوية |
| عام | /مساعدة |

اللي عنده صلاحية **Administrator** في السيرفر يقدر يستخدم كل الأوامر حتى لو ما حطيت آيدي الرتب.

## ملاحظات
- البيانات تنحفظ في ملف `vrp.db` جنب البوت. لا تحذفه، وخذ منه نسخة احتياطية كل فترة.
- تقدر تضيف وظيفة أو غرض للمتجر من `config.py` وتعيد تشغيل البوت.
# -*- coding: utf-8 -*-
"""
بوت نظام VRP لسيرفرات الرول بلاي (قراند سوني) على دسكورد
هوية - بنك - وظائف ورواتب - مخالفات - سجل جنائي - متجر وشنطة
"""
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from dotenv import load_dotenv

import config

load_dotenv()
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


# ============================================================
# البوت
# ============================================================
intents = discord.Intents.default()
intents.members = True


class VRPBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
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


def is_admin(inter: discord.Interaction) -> bool:
    return has_role(inter.user, config.ADMIN_ROLE_ID)


def is_police(inter: discord.Interaction) -> bool:
    return has_role(inter.user, config.POLICE_ROLE_ID) or is_admin(inter)


def embed(title: str, desc: str = "", color=0x0B6B55) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color, timestamp=now())
    e.set_footer(text=config.SERVER_NAME)
    return e


def err(msg: str) -> discord.Embed:
    return embed("❌ خطأ", msg, 0xB3261E)


async def log(text: str):
    if not config.LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(config.LOG_CHANNEL_ID)
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
        who = "ما عندك هوية. سوّ هوية بأمر /هوية_جديدة" if target == inter.user else f"{target.mention} ما عنده هوية."
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
@bot.tree.command(name="هوية_جديدة", description="إصدار هوية جديدة لشخصيتك في السيرفر")
@app_commands.describe(الاسم="اسم الشخصية", الميلاد="تاريخ الميلاد مثل 1998/05/20", الجنس="ذكر أو أنثى", الجنسية="جنسية الشخصية")
@app_commands.choices(الجنس=[app_commands.Choice(name="ذكر", value="ذكر"), app_commands.Choice(name="أنثى", value="أنثى")])
async def new_id(inter: discord.Interaction, الاسم: str, الميلاد: str, الجنس: app_commands.Choice[str], الجنسية: str):
    if get_player(inter.user.id):
        return await inter.response.send_message(embed=err("عندك هوية من قبل. استخدم /هويتي"), ephemeral=True)
    if len(الاسم) > 40:
        return await inter.response.send_message(embed=err("الاسم طويل، خله أقل من 40 حرف."), ephemeral=True)
    num = new_id_number()
    db.execute(
        "INSERT INTO players (user_id, id_number, name, birth, gender, nationality, job, cash, bank, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (inter.user.id, num, الاسم, الميلاد, الجنس.value, الجنسية, config.DEFAULT_JOB,
         config.START_CASH, config.START_BANK, now().isoformat()),
    )
    db.commit()
    p = get_player(inter.user.id)
    if config.CITIZEN_ROLE_ID and isinstance(inter.user, discord.Member):
        role = inter.guild.get_role(config.CITIZEN_ROLE_ID)
        if role:
            try:
                await inter.user.add_roles(role)
            except discord.Forbidden:
                pass
    e = id_card(p, inter.user)
    e.description = f"مرحبًا بك في المدينة! استلمت {money(config.START_CASH)} كاش و {money(config.START_BANK)} في البنك."
    await inter.response.send_message(embed=e)
    await log(f"{inter.user.mention} أصدر هوية باسم **{الاسم}** رقم `{num}`")


@bot.tree.command(name="هويتي", description="عرض هويتك")
async def my_id(inter: discord.Interaction):
    p = await require_player(inter)
    if p:
        await inter.response.send_message(embed=id_card(p, inter.user))


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
    await log(f"{inter.user.mention} حوّل {money(المبلغ)} إلى {اللاعب.mention}")


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
    await log(f"{inter.user.mention} عطى {اللاعب.mention} {money(المبلغ)} كاش")


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
    await log(f"{inter.user.mention} غيّر وظيفة {اللاعب.mention} من {p['job']} إلى {الوظيفة}")


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
    await log(f"{inter.user.mention} خالف {اللاعب.mention} بـ {money(المبلغ)}: {السبب}")


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
    await log(f"{inter.user.mention} سدد مخالفات بمبلغ {money(total)}")


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
    await log(f"{inter.user.mention} أضاف للسجل الجنائي لـ {اللاعب.mention}: {التهمة}")


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
    await log(f"{inter.user.mention} مسح السجل الجنائي لـ {اللاعب.mention}")


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
    await log(f"{inter.user.mention} فتّش {اللاعب.mention}")


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
    await log(f"{inter.user.mention} أضاف {money(المبلغ)} ({المكان.name}) لـ {اللاعب.mention}")


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
    await log(f"{inter.user.mention} خصم {money(المبلغ)} ({المكان.name}) من {اللاعب.mention}")


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
    await log(f"{inter.user.mention} حذف هوية {اللاعب.mention}")


@bot.tree.command(name="مساعدة", description="قائمة أوامر البوت")
async def help_cmd(inter: discord.Interaction):
    e = embed("📖 أوامر البوت")
    e.add_field(name="🪪 الهوية", value="/هوية_جديدة · /هويتي", inline=False)
    e.add_field(name="🏦 البنك", value="/رصيدي · /ايداع · /سحب · /تحويل · /اعطاء_كاش · /الاغنى", inline=False)
    e.add_field(name="💼 الوظائف", value="/الوظائف · /راتب", inline=False)
    e.add_field(name="🛒 المتجر", value="/المتجر · /شراء · /شنطتي · /اعطاء_غرض", inline=False)
    e.add_field(name="🚨 المخالفات", value="/مخالفاتي · /سداد_مخالفة", inline=False)
    e.add_field(name="👮 الشرطة", value="/مخالفة · /اضافة_سجل · /سجل · /تفتيش · /هوية", inline=False)
    e.add_field(name="🛠️ الإدارة", value="/تعيين_وظيفة · /اضافة_فلوس · /خصم_فلوس · /مسح_سجل · /حذف_هوية", inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ حط توكن البوت في ملف .env (DISCORD_TOKEN=...)")
    bot.run(TOKEN)
# ==========================================
#   إعدادات بوت نظام VRP - عدّل من هنا
# ==========================================

# اسم السيرفر (يظهر في الهوية والرسائل)
SERVER_NAME = "سيرفر الرول بلاي"

# العملة
CURRENCY = "$"

# الفلوس اللي ياخذها اللاعب أول ما يسوي هوية
START_CASH = 5000
START_BANK = 20000

# ----------------------------------------------------------------
# الرتب في الدسكورد (حط ID الرتبة، طريقة جلبه في ملف الشرح)
# ----------------------------------------------------------------
ADMIN_ROLE_ID = 0      # رتبة الإدارة: تعطي فلوس، تغير الوظائف، تحذف الهويات
POLICE_ROLE_ID = 0     # رتبة الشرطة: تسوي مخالفات وتضيف للسجل الجنائي
CITIZEN_ROLE_ID = 0    # رتبة "مواطن" تنعطى تلقائي بعد إصدار الهوية (0 = بدون)

# روم اللوق: كل العمليات المهمة تنرسل له (0 = بدون لوق)
LOG_CHANNEL_ID = 0

# ----------------------------------------------------------------
# الوظائف والرواتب
# المفتاح: اسم الوظيفة  |  salary: الراتب  |  role_id: رتبة الوظيفة في الدسكورد (اختياري)
# ----------------------------------------------------------------
JOBS = {
    "عاطل":     {"salary": 500,  "role_id": 0},
    "شرطي":     {"salary": 4000, "role_id": 0},
    "مسعف":     {"salary": 3500, "role_id": 0},
    "ميكانيكي": {"salary": 3000, "role_id": 0},
    "سواق تاكسي": {"salary": 2000, "role_id": 0},
    "محامي":    {"salary": 3500, "role_id": 0},
    "تاجر سيارات": {"salary": 2500, "role_id": 0},
}
DEFAULT_JOB = "عاطل"

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
discord.py>=2.3
python-dotenv>=1.0

