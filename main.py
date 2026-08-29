import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="-",
    intents=intents
)


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as: {bot.user}")
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync Error: {e}")


# =========================
# /panel
# =========================

@bot.tree.command(
    name="panel",
    description="Open the server control panel"
)
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎛️ Server Control Panel",
        description=(
            "Welcome to the control panel.\n\n"
            "Choose what you want to do from the buttons below."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(text="Server System")

    view = PanelView()

    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


# =========================
# BUTTONS
# =========================

class PanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tickets",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="panel:tickets"
    )
    async def tickets(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "🎫 Ticket System",
            ephemeral=True
        )

    @discord.ui.button(
        label="Jobs",
        emoji="📋",
        style=discord.ButtonStyle.success,
        custom_id="panel:jobs"
    )
    async def jobs(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "📋 Jobs System",
            ephemeral=True
        )

    @discord.ui.button(
        label="Points",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        custom_id="panel:points"
    )
    async def points(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "⭐ Your points: 0",
            ephemeral=True
        )


# =========================
# /come
# =========================

@bot.tree.command(
    name="come",
    description="Request a member to come"
)
@app_commands.describe(member="Member you want to call")
async def come(
    interaction: discord.Interaction,
    member: discord.Member
):

    await interaction.response.send_message(
        f"📢 {member.mention} تم استدعاؤك من قبل {interaction.user.mention}"
    )


# =========================
# /developers
# =========================

@bot.tree.command(
    name="developers",
    description="Show bot developers"
)
async def developers(interaction: discord.Interaction):

    embed = discord.Embed(
        title="👨‍💻 Developers",
        description="Bot Development Team",
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /gamepanel
# =========================

@bot.tree.command(
    name="gamepanel",
    description="Open the game panel"
)
async def gamepanel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎮 Game Panel",
        description=(
            "🎫 Tickets\n"
            "📋 Jobs\n"
            "⭐ Points\n"
            "👤 Activation"
        ),
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed,
        view=PanelView()
    )


# =========================
# RUN
# =========================

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

bot.run(TOKEN)
import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="-", intents=intents)


@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"تم تشغيل البوت: {bot.user}")
    print(f"تم تسجيل {len(synced)} أمر")


# =========================
# الأوامر العربية
# =========================

@bot.tree.command(
    name="لوحه",
    description="فتح لوحة التحكم"
)
async def لوحه(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🎛️ **لوحة التحكم**\nاختر الأمر الذي تريده."
    )


@bot.tree.command(
    name="تفعيل",
    description="تفعيل عضو"
)
async def تفعيل(interaction: discord.Interaction):
    await interaction.response.send_message(
        "✅ تم فتح نظام التفعيل."
    )


@bot.tree.command(
    name="تذاكر",
    description="فتح نظام التذاكر"
)
async def تذاكر(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🎫 تم فتح نظام التذاكر."
    )


@bot.tree.command(
    name="وظائف",
    description="عرض الوظائف"
)
async def وظائف(interaction: discord.Interaction):
    await interaction.response.send_message(
        "📋 **الوظائف**\nاختر الوظيفة المناسبة لك."
    )


@bot.tree.command(
    name="نقاط",
    description="عرض النقاط"
)
async def نقاط(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"⭐ نقاطك: **0**"
    )


@bot.tree.command(
    name="بنك",
    description="فتح نظام البنك"
)
async def بنك(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🏦 تم فتح نظام البنك."
    )


@bot.tree.command(
    name="رحله",
    description="بدء رحلة"
)
async def رحله(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🚗 تم بدء الرحلة."
    )


@bot.tree.command(
    name="مطوّرين",
    description="عرض المطورين"
)
async def مطورين(interaction: discord.Interaction):
    await interaction.response.send_message(
        "👨‍💻 **المطورين**"
    )


@bot.tree.command(
    name="استدعاء",
    description="استدعاء عضو"
)
@app_commands.describe(العضو="العضو المطلوب استدعاؤه")
async def استدعاء(
    interaction: discord.Interaction,
    العضو: discord.Member
):
    await interaction.response.send_message(
        f"📢 {العضو.mention} تم استدعاؤك."
    )


# =========================
# تشغيل البوت
# =========================

if not TOKEN:
    raise RuntimeError("لم يتم العثور على DISCORD_TOKEN")

bot.run(TOKEN)
