import discord
from discord.ext import commands
import asyncio
import sqlite3

# إعدادات البوت الأساسية
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== قاعدة البيانات (SQLite) ====================
db = sqlite3.connect("server_system.db")
cursor = db.cursor()

# إنشاء الجداول المطلوبة لأنظمة اللعبة والهوية والتذاكر والنقاط
cursor.execute('''CREATE TABLE IF NOT EXISTS players (
                    discord_id INTEGER PRIMARY KEY,
                    player_id INTEGER,
                    job TEXT DEFAULT 'مدني',
                    rank TEXT DEFAULT 'مواطن',
                    points INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'غير مفعل'
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS points_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    target_id INTEGER,
                    amount INTEGER,
                    reason TEXT
                )''')
db.commit()

@bot.event
async def on_ready():
    print(f"تم تشغيل نظام السيرفر بنجاح باسم: {bot.user}")

# ==================== 1. نظام الهوية والـ VRP ====================
class VRPSystem:
    @staticmethod
    def get_player(discord_id):
        cursor.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
        return cursor.fetchone()

    @staticmethod
    def link_player(discord_id, player_id):
        cursor.execute("INSERT OR REPLACE INTO players (discord_id, player_id, status) VALUES (?, ?, 'مفعل')", (discord_id, player_id))
        db.commit()

@bot.command(name="تفعيل")
@commands.has_permissions(administrator=True)
async def verify_player(ctx, member: discord.Member, player_id: int):
    VRPSystem.link_player(member.id, player_id)
    embed = discord.Embed(title="✅ تم التفعيل بنجاح", color=discord.Color.green())
    embed.add_field(name="العضو", value=member.mention, inline=True)
    embed.add_field(name="رقم اللاعب (ID)", value=str(player_id), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="اسماء")
async def player_identity(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = VRPSystem.get_player(member.id)
    
    embed = discord.Embed(title=f"🪪 هوية اللاعب: {member.name}", color=discord.Color.blue())
    if data:
        embed.add_field(name="رقم اللاعب", value=str(data[1]), inline=True)
        embed.add_field(name="الحالة", value=data[5], inline=True)
        embed.add_field(name="الوظيفة", value=data[2], inline=True)
        embed.add_field(name="الرتبة", value=data[3], inline=True)
        embed.add_field(name="النقاط", value=str(data[4]), inline=True)
    else:
        embed.description = "❌ العضو غير مسجل أو غير مفعل في قاعدة بيانات الـ VRP."
    await ctx.send(embed=embed)

# ==================== 2. نظام الوظائف والترقيات ====================
VALID_JOBS = ["العسكرية", "القانون", "الإجرام", "الإعلام", "الإسعاف", "الوظائف المدنية"]

@bot.command(name="توظيف")
@commands.has_permissions(administrator=True)
async def hire(ctx, member: discord.Member, job_name: str, *, rank_name: str):
    if job_name not in VALID_JOBS:
        await ctx.send(f"❌ الوظيفة غير صالحة. الوظائف المتاحة: {', '.join(VALID_JOBS)}")
        return
    
    cursor.execute("UPDATE players SET job = ?, rank = ? WHERE discord_id = ?", (job_name, rank_name, member.id))
    db.commit()
    await ctx.send(بنجاح `تم توظيف {member.mention} في قطاع **{job_name}** برتبة **{rank_name}** 🎖️`)

@bot.command(name="استقالة")
async def resign(ctx):
    cursor.execute("UPDATE players SET job = 'مدني', rank = 'مواطن' WHERE discord_id = ?", (ctx.author.id,))
    db.commit()
    await ctx.send(f"📄 {ctx.author.mention}, تم قبول استقالتك وأصبحت الآن (مدني).")

# ==================== 3. نظام التذاكر (Ticket System) ====================
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني العام", emoji="🛠️", description="للاستفسارات والمشاكل العامة"),
            discord.SelectOption(label="شكاوى الإدارة", emoji="⚖️", description="للشكاوى والاعتراضات"),
            discord.SelectOption(label="قسم الشرطة والعسكرية", emoji="👮", description="كل ما يخص القطاع العسكري")
        ]
        super().__init__(placeholder="اختر قسم التذكرة المناسب...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        category = discord.utils.get(guild.categories, name="التذاكر")
        if not category:
            category = await guild.create_category("التذاكر")

        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
        
        embed = discord.Embed(title=f"🎟️ تذكرة جديدة: {self.values[0]}", description=f"أهلاً بك {interaction.user.mention}\nاشرح مشكلتك أو طلبك بالتفصيل وسيتم خدمتك قريباً.", color=discord.Color.green())
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح: {channel.mention}", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

@bot.command(name="ticket-setup")
@commands.has_permissions(administrator=True)
async def ticket_setup(ctx):
    embed = discord.Embed(title="🎫 نظام التذاكر المركزي", description="اختر من القائمة أدناه لفتح تذكرة جديدة وسيقوم البوت بإنشاء روم خاص بك.", color=discord.Color.blue())
    await ctx.send(embed=embed, view=TicketView())

@bot.command(name="إغلاق")
async def close_ticket(ctx):
    if "ticket-" in ctx.channel.name:
        await ctx.send("🔒 جاري إغلاق وحذف التذكرة...")
        await asyncio.sleep(3)
        await ctx.channel.delete()
    else:
        await ctx.send("❌ هذا الأمر يختص برومات التذاكر فقط.")

# ==================== 4. نظام النقاط والترقيات ====================
@bot.command(name="نقاط")
async def manage_points(ctx, action: str, member: discord.Member, amount: int, *, reason: str = "بدون سبب"):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ ليس لديك صلاحية لإدارة النقاط.")
        return

    data = VRPSystem.get_player(member.id)
    if not data:
        await ctx.send("❌ هذا اللاعب غير مسجل بنظام الهوية.")
        return

    current_points = data[4]
    if action == "إضافة":
        new_points = current_points + amount
        cursor.execute("UPDATE players SET points = ? WHERE discord_id = ?", (new_points, member.id))
        cursor.execute("INSERT INTO points_log (admin_id, target_id, amount, reason) VALUES (?, ?, ?, ?)", (ctx.author.id, member.id, amount, reason))
        db.commit()
        await ctx.send(f"➕ تم إضافة **{amount}** نقطة لـ {member.mention}. (الرصيد الجديد: {new_points})")
    elif action == "خصم":
        new_points = max(0, current_points - amount)
        cursor.execute("UPDATE players SET points = ? WHERE discord_id = ?", (new_points, member.id))
        cursor.execute("INSERT INTO points_log (admin_id, target_id, amount, reason) VALUES (?, ?, ?, ?)", (ctx.author.id, member.id, -amount, reason))
        db.commit()
        await ctx.send(f"➖ تم خصم **{amount}** نقطة من {member.mention}. (الرصيد الجديد: {new_points})")

# ==================== 5. أوامر إدارية وإضافية ====================
@bot.command(name="استدعاء")
@commands.has_permissions(manage_messages=True)
async def summon(ctx, member: discord.Member, *, reason="بدون سبب"):
    embed = discord.Embed(title="🚨 تنبيه استدعاء إداري", description=f"تم استدعاؤك يا {member.mention} بواسطة الإدارة.\n**السبب:** {reason}", color=discord.Color.red())
    await ctx.send(embed=embed)
    try:
        await member.send(embed=embed)
    except:
        pass

@bot.command(name="حجز")
@commands.has_permissions(manage_roles=True)
async def jail(ctx, member: discord.Member, minutes: int = 10, *, reason="مخالفة القوانين"):
    await ctx.send(f"🔒 تم حجز اللاعب {member.mention} لمدة {minutes} دقائق. السبب: {reason}")

# ضع التوكن الخاص بك هنا
bot.run("YOUR_BOT_TOKEN")
