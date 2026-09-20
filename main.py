سعودي تايم — Strong VRP Discord Bot

التشغيل:
1) Python 3.11+
2) pip install -r requirements.txt
3) ضع DISCORD_TOKEN في Secrets
4) ضع GUILD_ID إذا أردت مزامنة أوامر أسرع مع سيرفر محدد
5) python main.py

اللوحة:
 /لوحه

أنظمة مضافة:
التفعيل، الملف الشخصي، الوظائف، النقاط، التذاكر، استلام التذاكر،
إغلاق وتحويل التذاكر، التوظيف، الترقية، التقاعد، الاستقالة،
الفصل، العقوبات، الاستدعاء، الحجز، التأكيد، إخلاء الطرف،
البنك، الرتب، الأسماء، السجل، ولوحة الإدارة.

تنبيه:
هذه النسخة لا تدّعي أنها مرتبطة بقاعدة VRP الفعلية.
الربط الحقيقي يحتاج أسماء جداول وحقول قاعدة بيانات VRP الخاصة بسيرفرك.
import os
import sqlite3
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput, Button

# =========================================================
# سعودي تايم — VRP Discord Control System
# نسخة قوية قابلة للتوسعة والربط مع VRP الحقيقي
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DB_PATH = os.getenv("DB_PATH", "saudi_time.sqlite3")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0") or 0)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN غير موجود في Secrets / Environment Variables")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row

db.executescript("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    vrp_id TEXT,
    name TEXT DEFAULT 'غير مسجل',
    job TEXT DEFAULT 'عاطل',
    rank TEXT DEFAULT 'مواطن',
    points INTEGER DEFAULT 0,
    active INTEGER DEFAULT 0,
    money INTEGER DEFAULT 0,
    bank INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS punishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER,
    type TEXT,
    reason TEXT,
    moderator_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER UNIQUE,
    owner_id INTEGER,
    department TEXT DEFAULT 'عام',
    claimed_by INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    target_id INTEGER,
    action TEXT,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
""")
db.commit()

def player(uid):
    return db.execute("SELECT * FROM players WHERE discord_id=?", (uid,)).fetchone()

def ensure_player(uid):
    p = player(uid)
    if not p:
        db.execute("INSERT INTO players(discord_id) VALUES(?)", (uid,))
        db.commit()
    return player(uid)

def log(actor, action, details="", target=None):
    db.execute(
        "INSERT INTO logs(actor_id,target_id,action,details) VALUES(?,?,?,?,?)",
        (actor, target, action, details)
    )
    db.commit()

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

async def admin_check(interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ هذا القسم للإدارة فقط.", ephemeral=True)
        return False
    return True

async def send_log_channel(guild, text):
    if not LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(text)
        except discord.HTTPException:
            pass

# ---------------------- Modals ----------------------

class ActivateModal(Modal, title="تفعيل حساب سعودي تايم"):
    vrp_id = TextInput(label="رقم VRP", placeholder="مثال: 100", max_length=30)
    name = TextInput(label="اسم اللاعب", placeholder="اسمك في السيرفر", max_length=80)

    async def on_submit(self, interaction):
        ensure_player(interaction.user.id)
        db.execute(
            "UPDATE players SET vrp_id=?, name=?, active=1 WHERE discord_id=?",
            (self.vrp_id.value.strip(), self.name.value.strip(), interaction.user.id)
        )
        db.commit()
        log(interaction.user.id, "تفعيل", f"VRP={self.vrp_id.value}")
        await interaction.response.send_message(
            f"✅ تم تفعيل حسابك.\n**VRP:** `{self.vrp_id.value}`\n**الاسم:** `{self.name.value}`",
            ephemeral=True
        )

class JobModal(Modal, title="توظيف لاعب"):
    job = TextInput(label="الوظيفة", placeholder="مثال: العسكرية / الإسعاف / القانون")
    rank = TextInput(label="الرتبة", placeholder="مثال: جندي / متدرب", required=False)

    async def on_submit(self, interaction):
        if not await admin_check(interaction):
            return
        target_id = getattr(self, "target_id", None)
        if not target_id:
            await interaction.response.send_message("❌ تعذر تحديد اللاعب.", ephemeral=True)
            return
        ensure_player(target_id)
        rank = self.rank.value.strip() or "مواطن"
        db.execute(
            "UPDATE players SET job=?, rank=?, active=1 WHERE discord_id=?",
            (self.job.value.strip(), rank, target_id)
        )
        db.commit()
        log(interaction.user.id, "توظيف", f"{self.job.value} | {rank}", target_id)
        await interaction.response.send_message("✅ تم التوظيف وتحديث الرتبة.", ephemeral=True)

# ---------------------- Selects ----------------------

class JobSelect(Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="العسكرية", emoji="👮", value="العسكرية"),
            discord.SelectOption(label="القانون", emoji="⚖️", value="القانون"),
            discord.SelectOption(label="الإجرام", emoji="🔫", value="الإجرام"),
            discord.SelectOption(label="الإعلام", emoji="📺", value="الإعلام"),
            discord.SelectOption(label="الإسعاف", emoji="🚑", value="الإسعاف"),
            discord.SelectOption(label="وظائف مدنية", emoji="🚕", value="وظائف مدنية"),
        ]
        super().__init__(placeholder="اختر وظيفتك...", options=opts)

    async def callback(self, interaction):
        p = ensure_player(interaction.user.id)
        db.execute("UPDATE players SET job=? WHERE discord_id=?", (self.values[0], interaction.user.id))
        db.commit()
        log(interaction.user.id, "اختيار وظيفة", self.values[0])
        await interaction.response.send_message(f"✅ تم اختيار **{self.values[0]}**.", ephemeral=True)

class DepartmentSelect(Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="الإدارة", emoji="🛡️", value="الإدارة"),
            discord.SelectOption(label="العسكرية", emoji="👮", value="العسكرية"),
            discord.SelectOption(label="القانون", emoji="⚖️", value="القانون"),
            discord.SelectOption(label="الإسعاف", emoji="🚑", value="الإسعاف"),
            discord.SelectOption(label="الدعم الفني", emoji="🛠️", value="الدعم الفني"),
            discord.SelectOption(label="عام", emoji="📩", value="عام"),
        ]
        super().__init__(placeholder="اختر القسم...", options=opts)

    async def callback(self, interaction):
        await create_ticket(interaction, self.values[0])

# ---------------------- Views ----------------------

class JobsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(JobSelect())

class TicketDepartmentView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(DepartmentSelect())

class MainPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="التفعيل", emoji="✅", style=discord.ButtonStyle.success, custom_id="st_main_activate")
    async def activate(self, interaction, button):
        await interaction.response.send_modal(ActivateModal())

    @discord.ui.button(label="معلوماتي", emoji="👤", style=discord.ButtonStyle.secondary, custom_id="st_main_info")
    async def info(self, interaction, button):
        p = player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ ما عندك سجل. اضغط التفعيل أولاً.", ephemeral=True)
            return
        e = discord.Embed(title="👤 ملف اللاعب — سعودي تايم", color=0x5865F2)
        e.add_field(name="الاسم", value=p["name"], inline=True)
        e.add_field(name="VRP ID", value=p["vrp_id"] or "غير مربوط", inline=True)
        e.add_field(name="الوظيفة", value=p["job"], inline=True)
        e.add_field(name="الرتبة", value=p["rank"], inline=True)
        e.add_field(name="النقاط", value=f"⭐ {p['points']}", inline=True)
        e.add_field(name="الحالة", value="🟢 مفعل" if p["active"] else "🔴 غير مفعل", inline=True)
        e.add_field(name="الكاش", value=f"${p['money']:,}", inline=True)
        e.add_field(name="البنك", value=f"${p['bank']:,}", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="الوظائف", emoji="📋", style=discord.ButtonStyle.primary, custom_id="st_main_jobs")
    async def jobs(self, interaction, button):
        await interaction.response.send_message("📋 اختر الوظيفة:", view=JobsView(), ephemeral=True)

    @discord.ui.button(label="النقاط", emoji="⭐", style=discord.ButtonStyle.secondary, custom_id="st_main_points")
    async def points(self, interaction, button):
        p = ensure_player(interaction.user.id)
        await interaction.response.send_message(f"⭐ نقاطك: **{p['points']}**", ephemeral=True)

    @discord.ui.button(label="التذاكر", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="st_main_ticket")
    async def tickets(self, interaction, button):
        await interaction.response.send_message("🎫 اختر القسم:", view=TicketDepartmentView(), ephemeral=True)

    @discord.ui.button(label="السجل", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="st_main_history")
    async def history(self, interaction, button):
        rows = db.execute(
            "SELECT * FROM logs WHERE target_id=? OR actor_id=? ORDER BY id DESC LIMIT 8",
            (interaction.user.id, interaction.user.id)
        ).fetchall()
        if not rows:
            await interaction.response.send_message("📜 لا يوجد سجل حتى الآن.", ephemeral=True)
            return
        text = "\n".join(
            f"• **{r['action']}** — {r['details']} — <t:{int(datetime.datetime.fromisoformat(r['created_at']).timestamp())}:R>"
            for r in rows
        )
        await interaction.response.send_message(f"📜 **سجلك**\n{text}", ephemeral=True)

class AdminPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إدارة لاعب", emoji="👤", style=discord.ButtonStyle.primary, custom_id="st_admin_player")
    async def player_admin(self, interaction, button):
        if not await admin_check(interaction): return
        await interaction.response.send_message(
            "استخدم أوامر الإدارة `/توظيف` أو `/ترقية` أو `/فصل` أو `/اعطاء_نقاط` أو `/خصم_نقاط`.",
            ephemeral=True
        )

    @discord.ui.button(label="استدعاء", emoji="📣", style=discord.ButtonStyle.primary, custom_id="st_admin_call")
    async def call(self, interaction, button):
        if not await admin_check(interaction): return
        await interaction.response.send_message("📣 استخدم `/استدعاء` لإرسال استدعاء.", ephemeral=True)

    @discord.ui.button(label="السجلات", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="st_admin_logs")
    async def logs(self, interaction, button):
        if not await admin_check(interaction): return
        rows = db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 15").fetchall()
        if not rows:
            text = "لا توجد سجلات."
        else:
            text = "\n".join(f"`{r['id']}` • <@{r['actor_id']}> • **{r['action']}** • {r['details']}" for r in rows)
        await interaction.response.send_message(f"📜 **آخر العمليات**\n{text}", ephemeral=True)

class TicketControls(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام", emoji="🙋", style=discord.ButtonStyle.success, custom_id="st_ticket_claim")
    async def claim(self, interaction, button):
        row = db.execute("SELECT * FROM tickets WHERE channel_id=?", (interaction.channel.id,)).fetchone()
        if not row:
            await interaction.response.send_message("❌ هذه ليست تذكرة مسجلة.", ephemeral=True)
            return
        db.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (interaction.user.id, interaction.channel.id))
        db.commit()
        log(interaction.user.id, "استلام تذكرة", interaction.channel.name)
        await interaction.response.send_message(f"🙋 تم استلام التذكرة بواسطة {interaction.user.mention}.")

    @discord.ui.button(label="إغلاق", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="st_ticket_close")
    async def close(self, interaction, button):
        row = db.execute("SELECT * FROM tickets WHERE channel_id=?", (interaction.channel.id,)).fetchone()
        if not row:
            await interaction.response.send_message("❌ هذه ليست تذكرة مسجلة.", ephemeral=True)
            return
        if row["owner_id"] != interaction.user.id and not is_admin(interaction):
            await interaction.response.send_message("❌ فقط صاحب التذكرة أو الإدارة يمكنه إغلاقها.", ephemeral=True)
            return
        db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (interaction.channel.id,))
        db.commit()
        await interaction.response.send_message("🔒 سيتم إغلاق التذكرة.")
        await interaction.channel.edit(name=f"closed-{interaction.channel.name}")

# ---------------------- Ticket ----------------------

async def create_ticket(interaction, department):
    guild = interaction.guild
    if not guild:
        return
    category = discord.utils.get(guild.categories, name="🎫・التذاكر")
    if not category:
        category = await guild.create_category("🎫・التذاكر")

    old = db.execute(
        "SELECT * FROM tickets WHERE owner_id=? AND status='open'",
        (interaction.user.id,)
    ).fetchone()
    if old:
        ch = guild.get_channel(old["channel_id"])
        await interaction.response.send_message(
            f"❌ عندك تذكرة مفتوحة بالفعل: {ch.mention if ch else 'غير موجودة'}",
            ephemeral=True
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
        )
    }
    channel = await guild.create_text_channel(
        f"ticket-{interaction.user.id}",
        category=category,
        overwrites=overwrites
    )
    db.execute(
        "INSERT INTO tickets(channel_id,owner_id,department) VALUES(?,?,?)",
        (channel.id, interaction.user.id, department)
    )
    db.commit()
    log(interaction.user.id, "فتح تذكرة", department)
    e = discord.Embed(
        title="🎫 تذكرة سعودي تايم",
        description=f"القسم: **{department}**\nاكتب طلبك بالتفصيل وانتظر الإدارة.",
        color=0x5865F2
    )
    await channel.send(content=interaction.user.mention, embed=e, view=TicketControls())
    await interaction.response.send_message(f"✅ تم فتح التذكرة: {channel.mention}", ephemeral=True)

# ---------------------- Slash commands ----------------------

@bot.tree.command(name="لوحه", description="فتح لوحة سعودي تايم")
async def panel(interaction):
    e = discord.Embed(
        title="🇸🇦 سعودي تايم",
        description="**لوحة التحكم الرئيسية**\n\nاختر الخدمة من الأزرار بالأسفل.",
        color=0x5865F2
    )
    e.add_field(name="VRP SYSTEM", value="التفعيل • الوظائف • النقاط • التذاكر • السجل", inline=False)
    e.set_footer(text="Saudi Time • VRP Control System")
    await interaction.response.send_message(embed=e, view=MainPanel())

@bot.tree.command(name="تفعيل", description="تفعيل وربط حساب VRP")
async def activate(interaction):
    await interaction.response.send_modal(ActivateModal())

@bot.tree.command(name="وظائف", description="اختيار وظيفة")
async def jobs(interaction):
    await interaction.response.send_message("📋 اختر الوظيفة:", view=JobsView(), ephemeral=True)

@bot.tree.command(name="معلومات", description="عرض معلومات اللاعب")
async def info(interaction):
    await MainPanel.info(MainPanel(), interaction, None)

@bot.tree.command(name="نقاط", description="عرض نقاط اللاعب")
async def points(interaction):
    p = ensure_player(interaction.user.id)
    await interaction.response.send_message(f"⭐ نقاطك: **{p['points']}**", ephemeral=True)

@bot.tree.command(name="تذكرة", description="فتح تذكرة")
async def ticket(interaction):
    await interaction.response.send_message("🎫 اختر القسم:", view=TicketDepartmentView(), ephemeral=True)

@bot.tree.command(name="ادمن", description="فتح لوحة الإدارة")
async def admin(interaction):
    if not await admin_check(interaction): return
    e = discord.Embed(title="🛡️ لوحة إدارة سعودي تايم", description="كل أدوات الإدارة الأساسية.", color=0xED4245)
    await interaction.response.send_message(embed=e, view=AdminPanel(), ephemeral=True)

@bot.tree.command(name="اعطاء_نقاط", description="إضافة نقاط")
@app_commands.describe(member="العضو", amount="عدد النقاط")
async def give_points(interaction, member: discord.Member, amount: app_commands.Range[int,1,10000]):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET points=points+? WHERE discord_id=?", (amount, member.id))
    db.commit()
    log(interaction.user.id, "إضافة نقاط", str(amount), member.id)
    await interaction.response.send_message(f"✅ تمت إضافة **{amount}** نقطة إلى {member.mention}.")

@bot.tree.command(name="خصم_نقاط", description="خصم نقاط")
@app_commands.describe(member="العضو", amount="عدد النقاط")
async def take_points(interaction, member: discord.Member, amount: app_commands.Range[int,1,10000]):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET points=MAX(0,points-?) WHERE discord_id=?", (amount, member.id))
    db.commit()
    log(interaction.user.id, "خصم نقاط", str(amount), member.id)
    await interaction.response.send_message(f"✅ تم خصم **{amount}** نقطة من {member.mention}.")

@bot.tree.command(name="توظيف", description="توظيف عضو")
@app_commands.describe(member="العضو", job="الوظيفة", rank="الرتبة")
async def hire(interaction, member: discord.Member, job: str, rank: str="مواطن"):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET job=?,rank=?,active=1 WHERE discord_id=?", (job,rank,member.id))
    db.commit()
    log(interaction.user.id, "توظيف", f"{job} | {rank}", member.id)
    await interaction.response.send_message(f"✅ تم توظيف {member.mention} في **{job}** برتبة **{rank}**.")

@bot.tree.command(name="ترقية", description="ترقية عضو")
@app_commands.describe(member="العضو", rank="الرتبة الجديدة")
async def promote(interaction, member: discord.Member, rank: str):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET rank=? WHERE discord_id=?", (rank, member.id))
    db.commit()
    log(interaction.user.id, "ترقية", rank, member.id)
    await interaction.response.send_message(f"⬆️ تمت ترقية {member.mention} إلى **{rank}**.")

@bot.tree.command(name="تقاعد", description="تقاعد عضو")
@app_commands.describe(member="العضو")
async def retire(interaction, member: discord.Member):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET job='متقاعد', active=0 WHERE discord_id=?", (member.id,))
    db.commit()
    log(interaction.user.id, "تقاعد", "", member.id)
    await interaction.response.send_message(f"🫡 تم تسجيل تقاعد {member.mention}.")

@bot.tree.command(name="استقالة", description="تسجيل استقالة عضو")
async def resign(interaction):
    ensure_player(interaction.user.id)
    db.execute("UPDATE players SET job='مستقيل', active=0 WHERE discord_id=?", (interaction.user.id,))
    db.commit()
    log(interaction.user.id, "استقالة")
    await interaction.response.send_message("✅ تم تسجيل استقالتك.", ephemeral=True)

@bot.tree.command(name="فصل", description="فصل عضو")
@app_commands.describe(member="العضو")
async def fire(interaction, member: discord.Member):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET job='عاطل',rank='مواطن',active=0 WHERE discord_id=?", (member.id,))
    db.commit()
    log(interaction.user.id, "فصل", "", member.id)
    await interaction.response.send_message(f"❌ تم فصل {member.mention}.")

@bot.tree.command(name="عقوبات", description="إضافة عقوبة لعضو")
@app_commands.describe(member="العضو", type="نوع العقوبة", reason="السبب")
async def punish(interaction, member: discord.Member, type: str, reason: str):
    if not await admin_check(interaction): return
    db.execute(
        "INSERT INTO punishments(discord_id,type,reason,moderator_id) VALUES(?,?,?,?)",
        (member.id,type,reason,interaction.user.id)
    )
    db.commit()
    log(interaction.user.id, "عقوبة", f"{type}: {reason}", member.id)
    await interaction.response.send_message(f"⚠️ تم تسجيل عقوبة على {member.mention}.")

@bot.tree.command(name="سجل", description="عرض سجل لاعب")
@app_commands.describe(member="العضو")
async def history(interaction, member: discord.Member=None):
    if member and not await admin_check(interaction):
        return
    target = member or interaction.user
    rows = db.execute(
        "SELECT * FROM logs WHERE target_id=? OR actor_id=? ORDER BY id DESC LIMIT 15",
        (target.id,target.id)
    ).fetchall()
    text = "\n".join(f"• **{r['action']}** — {r['details']}" for r in rows) or "لا يوجد سجل."
    await interaction.response.send_message(f"📜 **سجل {target.display_name}**\n{text}", ephemeral=True)

@bot.tree.command(name="استدعاء", description="إرسال استدعاء لعضو")
@app_commands.describe(member="العضو", reason="سبب الاستدعاء")
async def summon(interaction, member: discord.Member, reason: str):
    if not await admin_check(interaction): return
    await member.send(f"📣 **استدعاء من سعودي تايم**\nمن: {interaction.user.mention}\nالسبب: **{reason}**")
    log(interaction.user.id, "استدعاء", reason, member.id)
    await interaction.response.send_message(f"📣 تم إرسال الاستدعاء إلى {member.mention}.")

@bot.tree.command(name="حجز", description="حجز عضو في النظام")
@app_commands.describe(member="العضو", reason="السبب")
async def reserve(interaction, member: discord.Member, reason: str):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    log(interaction.user.id, "حجز", reason, member.id)
    await interaction.response.send_message(f"🔒 تم تسجيل حجز {member.mention}: **{reason}**.")

@bot.tree.command(name="تأكيد", description="تأكيد عضو")
@app_commands.describe(member="العضو")
async def confirm(interaction, member: discord.Member):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    db.execute("UPDATE players SET active=1 WHERE discord_id=?", (member.id,))
    db.commit()
    log(interaction.user.id, "تأكيد", "", member.id)
    await interaction.response.send_message(f"✅ تم تأكيد {member.mention}.")

@bot.tree.command(name="إخلاء", description="تسجيل إخلاء طرف")
@app_commands.describe(member="العضو")
async def clear(interaction, member: discord.Member):
    if not await admin_check(interaction): return
    ensure_player(member.id)
    log(interaction.user.id, "إخلاء", "", member.id)
    await interaction.response.send_message(f"📄 تم تسجيل إخلاء طرف {member.mention}.")

@bot.tree.command(name="بنك", description="عرض بيانات البنك المسجلة")
async def bank(interaction):
    p = ensure_player(interaction.user.id)
    await interaction.response.send_message(
        f"🏦 **حسابك البنكي**\nالرصيد: **${p['bank']:,}**\nالكاش: **${p['money']:,}**",
        ephemeral=True
    )

@bot.tree.command(name="رتب", description="عرض رتبتك")
async def ranks(interaction):
    p = ensure_player(interaction.user.id)
    await interaction.response.send_message(f"🎖️ وظيفتك: **{p['job']}**\nرتبتك: **{p['rank']}**", ephemeral=True)

@bot.tree.command(name="اسماء", description="عرض أسماء اللاعبين المسجلين")
async def names(interaction):
    if not await admin_check(interaction): return
    rows = db.execute("SELECT name,vrp_id,job,rank FROM players ORDER BY name LIMIT 50").fetchall()
    text = "\n".join(f"• **{r['name']}** | VRP `{r['vrp_id']}` | {r['job']} | {r['rank']}" for r in rows)
    await interaction.response.send_message(text or "لا يوجد لاعبون.", ephemeral=True)

@bot.tree.command(name="تحويل_تذكرة", description="تحويل التذكرة لقسم")
@app_commands.describe(department="القسم الجديد")
async def transfer_ticket(interaction, department: str):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("❌ استخدم الأمر داخل التذكرة.", ephemeral=True)
        return
    row = db.execute("SELECT * FROM tickets WHERE channel_id=?", (interaction.channel.id,)).fetchone()
    if not row:
        await interaction.response.send_message("❌ هذه ليست تذكرة.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
        return
    db.execute("UPDATE tickets SET department=? WHERE channel_id=?", (department, interaction.channel.id))
    db.commit()
    log(interaction.user.id, "تحويل تذكرة", department, row["owner_id"])
    await interaction.response.send_message(f"🔄 تم تحويل التذكرة إلى **{department}**.")

# ---------------------- startup ----------------------

@bot.event
async def on_ready():
    bot.add_view(MainPanel())
    bot.add_view(AdminPanel())
    bot.add_view(TicketControls())
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()
    print(f"✅ {bot.user} online — Saudi Time")
