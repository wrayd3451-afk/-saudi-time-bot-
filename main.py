import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")
⁠await await bot.tree.sync()
@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

bot.run(os.environ['DISCORD_TOKEN'])
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="إرسال تعميم", style=discord.ButtonStyle.primary)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("تم الضغط على الزر!", ephemeral=True)

@bot.command()
async def panel(ctx):
    await ctx.send("لوحة التحكم:", view=MyView())
    import discord
from discord.ext import commands

# 1. كلاس الأزرار (لوحة المفاتيح)
class ControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # الأزرار تبق شغالة دائمًا

import os
import discord
from discord.ext import commands

# 1. إعدادات البوت والـ Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 2. كلاس الأزرار (لوحة المفاتيح)
class ControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # الأزرار تبق شغالة دائمًا

    # الزر الأول (أخضر)
    @discord.ui.button(label="زر تفاعلي", style=discord.ButtonStyle.success, custom_id="btn_1")
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("تم تنفيذ الأمر بنجاح! 🚀", ephemeral=True)

    # الزر الثاني (أحمر)
    @discord.ui.button(label="زر ثاني", style=discord.ButtonStyle.danger, custom_id="btn_2")
    async def second_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ضغطت الزر الثاني!", ephemeral=True)

    # الزر الثالث (رابط)
    @discord.ui.button(label="رابط الموقع", style=discord.ButtonStyle.link, url="https://discord.com")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

# 3. أحداث البوت والأوامر
@bot.event
async def on_ready():
    bot.add_view(ControlPanel()) # لتفعيل الأزرار الدائمة
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

@bot.command()
async def panel(ctx):
    # تحقق من صلاحية الأدمن (اختياري)
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("ما عندك صلاحية!", ephemeral=True)
    
    view = ControlPanel()
    await ctx.send("🎮 **لوحة التحكم الخاصة بالسيرفر:**\nاختر أحد الخيارات أدناه:", view=view)

# 4. تشغيل البوت
bot.run(os.environ['DISCORD_TOKEN'])
import os
import discord
from discord.ext import commands

# 1. إعدادات البوت والـ Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

# 2. كلاس الأزرار (لوحة المفاتيح)
class ControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="زر تفاعلي", style=discord.ButtonStyle.success, custom_id="btn_1")
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("تم تنفيذ الأمر بنجاح! 🚀", ephemeral=True)

    @discord.ui.button(label="زر ثاني", style=discord.ButtonStyle.danger, custom_id="btn_2")
    async def second_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ضغطت الزر الثاني!", ephemeral=True)

    @discord.ui.button(label="رابط الموقع", style=discord.ButtonStyle.link, url="https://discord.com")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

# 3. أحداث البوت
@bot.event
async def on_ready():
    bot.add_view(ControlPanel())
    print(f"Logged in as {bot.user}")

# 4. أمر الـ panel الرئيسي
@bot.command()
async def panel(ctx):
    view = ControlPanel()
    await ctx.send("🎮 **لوحة التحكم الخاصة بالسيرفر:**\nاختر أحد الخيارات أدناه:", view=view)

# 5. أمر الرحلة (ينقل البيانات وينشرها في روم ثاني)
@bot.command()
async def رحله(ctx, id_الهوست: str = "غير محدد", مساعد_الهوست: str = "غير محدد", موعد_الرحله: str = "غير محدد", رقابي_الرحله: str = "غير محدد"):
    
    # 🔴 حط آيدي الروم الثاني اللي تبي الإمبد ينزل فيه هنا بين القوسين
    target_channel_id = 123456789012345678  
    
    target_channel = bot.get_channel(target_channel_id)
    
    if not target_channel:
        return await ctx.send("عذراً، لم أجد الروم المخصص لإرسال الرحلات! تأكد من آيدي الروم.", ephemeral=True)

    # تصميم الإمبد
    embed = discord.Embed(
        title="✈️ **تفاصيل الرحلة الجديدة**",
        color=discord.Color.blue()
    )
    embed.add_field(name="🆔 آيدي الهوست", value=id_الهوست, inline=False)
    embed.add_field(name="👥 مساعد الهوست", value=مساعد_الهوست, inline=False)
    embed.add_field(name="⏰ موعد الرحلة", value=موعد_الرحله, inline=False)
    embed.add_field(name="🛡️ رقابي الرحلة", value=رقابي_الرحله, inline=False)
    
    view = ControlPanel()
    
    # يرسل الإمبد للروم الثاني
    await target_channel.send(embed=embed, view=view)
    
    # يعطي رد خفيف للي كتب الأمر عشان يعرف إنه تم بنجاح
    await ctx.send("✅ تم نشر تفاصيل الرحلة في روم الرحلات بنجاح!", ephemeral=True)

# تشغيل البوت
bot.run(os.environ['DISCORD_TOKEN'])

import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

# 1. كلاس الأزرار الخاصة بالتذكرة (خيارين)
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # الأزرار تبقا شغالة دائمًا

    # الزر الأول (مثلاً: قبول / أو فتح تذكرة)
    @discord.ui.button(label="فتح تذكرة", style=discord.ButtonStyle.success, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ تم فتح تذكرتك بنجاح! انتظر الإدارة.", ephemeral=True)

    # الزر الثاني (مثلاً: إلغاء / أو مساعدة)
    @discord.ui.button(label="مساعدة", style=discord.ButtonStyle.secondary, custom_id="help_ticket_btn")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ℹ️ تم طلب المساعدة، سيتم الرد عليك قريباً.", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(TicketView())
    print(f"Logged in as {bot.user}")

# 2. أمر T1 (يعرض الأسئلة والخيارين مثل الصورة)
@bot.command()
name = "t1" # يقدر العضو يكتب -t1
@bot.command(name="t1")
async def t1(ctx):
    # مسح رسالة الأمر الأصلية عشان يكون الشات نظيف (اختياري)
    try:
        await ctx.message.delete()
    except:
        pass

    # تصميم الإمبد اللي فيه الأسئلة
    embed = discord.Embed(
        title="📋 **نظام التذاكر والتفعيل**",
        description="يرجى قراءة الأسئلة أدناه والضغط على الزر المناسب للبدء:",
        color=discord.Color.blurple()
    )
    embed.add_field(name="❓ س1:", value="هل قرأت قوانين السيرفر جيداً؟", inline=False)
    embed.add_field(name="❓ س2:", value="هل أنت مستعد لبدء التفعيل الآن؟", inline=False)
    
    # ربط الإمبد بالأزرار (الخيارين)
    view = TicketView()
    
    # إرسال الرسالة في الروم
    await ctx.send(embed=embed, view=view)

# تشغيل البوت
bot.run(os.environ['DISCORD_TOKEN'])
import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

# قاموس لحفظ نقاط الأعضاء مؤقتاً (يفضل لاحقاً ربطه بقاعدة بيانات مثل SQLite)
user_points = {}

# ==========================================
# 1. نظام أزرار الوظائف (التوظيف)
# ==========================================
class JobSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="مدير إداري", style=discord.ButtonStyle.primary, custom_id="job_manager")
    async def job_manager(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مدير إداري")

    @discord.ui.button(label="مسؤول تذاكر", style=discord.ButtonStyle.success, custom_id="job_ticket")
    async def job_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مسؤول تذاكر")

    @discord.ui.button(label="مراقب عام", style=discord.ButtonStyle.secondary, custom_id="job_monitor")
    async def job_monitor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مراقب عام")

    async def assign_job(self, interaction: discord.Interaction, job_name: str):
        # هنا تقدر تحط شرط الرتبة المعينة المطلوبة للتوظيف
        user = interaction.user
        await interaction.response.send_message(f"✅ تم توظيفك بنجاح في وظيفة: **{job_name}** وتمت إضافة النقاط لرصيدك!", ephemeral=True)
        
        # إضافة نقاط للتوظيف تلقائياً
        user_points[user.id] = user_points.get(user.id, 0) + 15

# ==========================================
# 2. الأحداث والأوامر
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(JobSelectView())
    print(f"Logged in as {bot.user} (نظام النقاط والتفاعل جاهز!)")

# أمر التفعيل (-تفعيل [ايدي الشخص] [ايدي سوني])
@bot.command(name="تفعيل")
async def tfaeel(ctx, member: discord.Member = None, *, psn_id: str = "غير محدد"):
    if not member:
        return await ctx.send("❌ عذراً، يرجى تحديد الشخص المراد تفعيله. مثال: `-تفعيل @الشخص PSN_ID`", ephemeral=True)

    # إضافة نقاط للي سوي التفعيل (مثلاً 10 نقاط)
    user_points[ctx.author.id] = user_points.get(ctx.author.id, 0) + 10

    embed = discord.Embed(
        title="✅ **تم التفعيل بنجاح**",
        color=discord.Color.green()
    )
    embed.add_field(name="👤 العضو:", value=member.mention, inline=False)
    embed.add_field(name="🎮 آيدي سوني:", value=psn_id, inline=False)
    embed.add_field(name="🛡️ الإداري المفعل:", value=ctx.author.mention, inline=False)
    embed.add_field(name="⭐ النقاط المضافة:", value="+10 نقاط للإداري", inline=False)

    await ctx.send(embed=embed)

# نظام إعطاء النقاط يدويًا (-اعطاء نقاط)
@bot.command(name="اعطاء")
async def give_points(ctx, action: str = None):
    if action == "نقاط":
        await ctx.send("✍️ أرسل الآن **من هو الشخص** و **كم عدد النقاط** التي تريد إضافتها؟ (مثلاً: `@الشخص 50`)")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for('message', timeout=30.0, check=check)
            parts = msg.content.split()
            target_mention = msg.mentions[0]
            points_to_add = int(parts[1])

            user_points[target_mention.id] = user_points.get(target_mention.id, 0) + points_to_add
            await ctx.send(f"✅ تم بنجاح إضافة `{points_to_add}` نقطة إلى العضو {target_mention.mention}!")
        except Exception as e:
            await ctx.send("⏰ انتهى الوقت أو الصيغة غير صحيحة، حاول مرة أخرى.")

# أمر التوظيف وعرض خيارات الوظائف (-وظيفه)
@bot.command(name="وظيفه")
async def job_command(ctx):
    # تحقق من صلاحية أو رتبه معينة للإداري اللي يكتب الأمر
    embed = discord.Embed(
        title="📋 **لوحة اختيار الوظائف**",
        description="اختر الوظيفة المناسبة من الأزرار أدناه:",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=JobSelectView())

# عرض رصيد النقاط (-نقاطي أو -نقاط)
@bot.command(name="نقاط")
async def my_points(ctx, member: discord.Member = None):
    target = member or ctx.author
    points = user_points.get(target.id, 0)
    await ctx.send(dict(f"⭐ العضو {target.mention} لديه رصيد: `{points}` نقطة."))

# تشغيل البوت
bot.run(os.environ['DISCORD_TOKEN'])

import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

# قاموس لحفظ نقاط الأعضاء
user_points = {}

# ==========================================
# 1. كلاس أزرار الوظائف (التوظيف)
# ==========================================
class JobSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="مدير إداري", style=discord.ButtonStyle.primary, custom_id="job_manager")
    async def job_manager(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مدير إداري")

    @discord.ui.button(label="مسؤول تذاكر", style=discord.ButtonStyle.success, custom_id="job_ticket")
    async def job_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مسؤول تذاكر")

    @discord.ui.button(label="مراقب عام", style=discord.ButtonStyle.secondary, custom_id="job_monitor")
    async def job_monitor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_job(interaction, "مراقب عام")

    async def assign_job(self, interaction: discord.Interaction, job_name: str):
        user = interaction.user
        await interaction.response.send_message(f"✅ تم توظيفك بنجاح في وظيفة: **{job_name}** وإضافة النقاط!", ephemeral=True)
        
        # إضافة نقاط للتوظيف تلقائياً
        user_points[user.id] = user_points.get(user.id, 0) + 15

# ==========================================
# 2. أحداث البوت
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(JobSelectView())
    print(f"Logged in as {bot.user} (البوت شغال وجاهز!)")

# ==========================================
# 3. الأوامر الأساسية
# ==========================================

# أمر التفعيل (-تفعيل [@الشخص] [ايدي سوني])
@bot.command(name="تفعيل")
async def tfaeel(ctx, member: discord.Member = None, *, psn_id: str = "غير محدد"):
    if not member:
        return await ctx.send("❌ عذراً، يرجى إرفاق منشن الشخص. مثال: `-تفعيل @الشخص PSN_ID`", ephemeral=True)

    # إضافة 10 نقاط للإداري اللي فعّل
    user_points[ctx.author.id] = user_points.get(ctx.author.id, 0) + 10

    embed = discord.Embed(
        title="✅ **تم التفعيل بنجاح**",
        color=discord.Color.green()
    )
    embed.add_field(name="👤 العضو:", value=member.mention, inline=False)
    embed.add_field(name="🎮 آيدي سوني:", value=psn_id, inline=False)
    embed.add_field(name="🛡️ الإداري المفعل:", value=ctx.author.mention, inline=False)
    embed.add_field(name="⭐ النقاط:", value="+10 نقاط للإداري", inline=False)

    await ctx.send(embed=embed)

# نظام إعطاء النقاط (-اعطاء نقاط)
@bot.command(name="اعطاء")
async def give_points(ctx, action: str = None):
    if action == "نقاط":
        await ctx.send("✍️ أرسل الآن بالمنشن الشخص والعدد المطلوبة (مثلاً: `@الشخص 50`)")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for('message', timeout=30.0, check=check)
            target_mention = msg.mentions[0]
            parts = msg.content.split()
            points_to_add = int(parts[1])

            user_points[target_mention.id] = user_points.get(target_mention.id, 0) + points_to_add
            await ctx.send(f"✅ تم بنجاح إضافة `{points_to_add}` نقطة إلى العضو {target_mention.mention}!")
        except Exception:
            await ctx.send("⏰ انتهى الوقت أو الصيغة غير صحيحة.")

# أمر التوظيف (-وظيفه)
@bot.command(name="وظيفه")
async def job_command(ctx):
    embed = discord.Embed(
        title="📋 **لوحة اختيار الوظائف**",
        description="اختر الوظيفة المناسبة من الأزرار أدناه:",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=JobSelectView())

# عرض النقاط (-نقاط)
@bot.command(name="نقاط")
async def my_points(ctx, member: discord.Member = None):
    target = member or ctx.author
    points = user_points.get(target.id, 0)
    await ctx.send(f"⭐ رصيد النقاط للعضو {target.mention} هو: `{points}` نقطة.")

# تشغيل البوت
bot.run(os.environ['DISCORD_TOKEN'])

