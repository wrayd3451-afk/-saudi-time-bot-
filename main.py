import discord
from discord import app_commands
from discord.ext import commands

# إعداد الصلاحيات والبوت
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# كلاس الأزرار واللوحة التفاعلية
class GamePanelView(discord.ui.View):

  def __init__(self):
    super().__init__(
        timeout=None
    )  # يخلي الأزرار شغالة دائمًا وما تنتهي صلاحيتها

  # الصف الأول: التذاكر والإدارة
  @discord.ui.button(
      label="التذاكر",
      style=discord.ButtonStyle.secondary,
      emoji="🎫",
      row=0,
  )
  async def tickets_button(
      interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "🎫 تم اختيار قسم **إدارة التذاكر** بنجاح.", ephemeral=True
    )

  @discord.ui.button(
      label="الإدارة", style=discord.ButtonStyle.primary, emoji="👮‍♂️", row=0
  )
  async def management_button(
      interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "👮‍♂️ تم اختيار قسم **إدارة الأعضاء والرتب** بنجاح.", ephemeral=True
    )

  # الصف الثاني: الوظائف والبنك
  @discord.ui.button(
      label="الوظائف", style=discord.ButtonStyle.success, emoji="💼", row=1
  )
  async def jobs_button(
      interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "💼 تم اختيار قسم **إدارة الوظائف** بنجاح.", ephemeral=True
    )

  @discord.ui.button(
      label="البنك", style=discord.ButtonStyle.danger, emoji="💰", row=1
  )
  async def bank_button(
      interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "💰 تم اختيار قسم **إدارة خدمات البنك** بنجاح.", ephemeral=True
    )


@bot.event
async def on_ready():
  print(f"تم تسجيل الدخول بنجاح باسم: {bot.user.name}")
  try:
    synced = await bot.tree.sync()
    print(f"تم مزامنة {len(synced)} أمر (Slash Commands).")
  except Exception as e:
    print(f"خطأ في مزامنة الأوامر: {e}")


# أمر الـ Slash Command لإرسال اللوحة
@bot.tree.command(
    name="gamepanel", description="إرسال لوحة تحكم سيرفر Saudi Time الرئيسية"
)
async def gamepanel(interaction: discord.Interaction):
  # التحقق من صلاحيات المشرف
  if not interaction.user.guild_permissions.administrator:
    await interaction.response.send_message(
        "ما عندك صلاحية تستخدم هالأمر يالغالي ❌", ephemeral=True
    )
    return

  # بناء الـ Embed مطابق لصورة السيرفر
  embed = discord.Embed(
      title="🇸🇦 Saudi Time",
      description=(
          "مرحباً بك في لوحة تحكم السيرفر.\n\nاختر الخدمة التي تريد استخدامها.\n\n"
          "🎫 **التذاكر**\nإدارة التذاكر\n\n"
          "👮‍♂️ **الإدارة**\nإدارة الأعضاء والرتب\n\n"
          "💼 **الوظائف**\nإدارة الوظائف\n\n"
          "💰 **البنك**\nإدارة خدمات البنك"
      ),
      color=discord.Color.green(),  # لون الشريط الجانبي أخضر
  )

  embed.set_footer(text="Saudi Time • Game Panel")

  # إرسال الرسالة مع الأزرار
  await interaction.response.send_message(
      embed=embed, view=GamePanelView(), ephemeral=False
  )


# تشغيل البوت (ضع توكن بوتك هنا بدل النص التجريبي)
bot.run("YOUR_BOT_TOKEN")
