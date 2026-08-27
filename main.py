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

