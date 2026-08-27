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

    # الزر الأول (أخضر - يتفاعل معه البوت)
    @discord.ui.button(label="زر تفاعلي", style=discord.ButtonStyle.success, custom_id="btn_1")
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("تم تنفيذ الأمر بنجاح! 🚀", ephemeral=True)

    # الزر الثاني (أحمر - زر خطر أو حذف)
    @discord.ui.button(label="زر ثاني", style=discord.ButtonStyle.danger, custom_id="btn_2")
    async def second_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ضغطت الزر الثاني!", ephemeral=True)

    # الزر الثالث (رابط خارجي)
    @discord.ui.button(label="رابط الموقع", style=discord.ButtonStyle.link, url="https://discord.com")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

# 2. أمر إرسال اللوحة
@bot.command()
async def panel(ctx):
    # تحقق إذا تبي تمنع الأعضاء العاديين من استخدام الأمر (مثلاً للأدممنية فقط)
    # if not ctx.author.guild_permissions.administrator:
    #     return await ctx.send("ما عندك صلاحية!", ephemeral=True)

    view = ControlPanel()
    await ctx.send("🎮 **لوحة التحكم الخاصة بالسيرفر:**\nاختر أحد الخيارات أدناه:", view=view)

