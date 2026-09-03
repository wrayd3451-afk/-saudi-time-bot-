import os
import discord
from discord.ext import commands
from discord import app_commands

# ==============================
# إعدادات البوت
# ==============================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="-",
    intents=intents
)


# ==============================
# عند تشغيل البوت
# ==============================

@bot.event
async def on_ready():
    print("================================")
    print(f"✅ البوت شغال: {bot.user}")
    print("================================")

    try:
        synced = await bot.tree.sync()
        print(f"✅ تم تسجيل {len(synced)} أمر Slash")
    except Exception as error:
        print(f"❌ خطأ في تسجيل الأوامر: {error}")


# ==============================
# /gamepanel
# ==============================

@bot.tree.command(
    name="gamepanel",
    description="لوحة تحكم Saudi Time"
)
async def gamepanel(interaction: discord.Interaction):

    # نرد مباشرة على ديسكورد
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="🇸🇦 Saudi Time",
        description=(
            "مرحباً بك في لوحة تحكم السيرفر\n\n"
            "اختر الخدمة التي تريد استخدامها."
        ),
        color=discord.Color.green()
    )

    embed.add_field(
        name="🎫 التذاكر",
        value="إدارة التذاكر",
        inline=False
    )

    embed.add_field(
        name="👮 الإدارة",
        value="إدارة الأعضاء والرتب",
        inline=False
    )

    embed.add_field(
        name="💼 الوظائف",
        value="إدارة الوظائف",
        inline=False
    )

    embed.add_field(
        name="💰 البنك",
        value="إدارة خدمات البنك",
        inline=False
    )

    embed.set_footer(
        text="Saudi Time • Game Panel"
    )

    await interaction.followup.send(
        embed=embed,
        ephemeral=True
    )


# ==============================
# /role
# ==============================

@bot.tree.command(
    name="role",
    description="إضافة أو إزالة رتبة من عضو"
)
@app_commands.describe(
    member="العضو",
    role="الرتبة"
)
async def role(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role
):

    # التأكد من صلاحية المستخدم
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ ما عندك صلاحية إدارة الرتب.",
            ephemeral=True
        )
        return

    # التأكد أن البوت يستطيع إعطاء الرتبة
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "❌ ما أقدر أتعامل مع هذه الرتبة لأنها أعلى من رتبتي.",
            ephemeral=True
        )
        return

    if role in member.roles:

        await member.remove_roles(role)

        await interaction.response.send_message(
            f"✅ تمت إزالة رتبة {role.mention} من {member.mention}.",
            ephemeral=True
        )

    else:

        await member.add_roles(role)

        await interaction.response.send_message(
            f"✅ تمت إضافة رتبة {role.mention} إلى {member.mention}.",
            ephemeral=True
        )


# ==============================
# /roles-slash
# ==============================

@bot.tree.command(
    name="roles-slash",
    description="إدارة رتب السيرفر"
)
async def roles_slash(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🛡️ إدارة الرتب",
        description=(
            "استخدم أمر `/role` لإضافة أو إزالة رتبة من عضو.\n\n"
            "مثال:\n"
            "`/role member role`"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ==============================
# /request-loan-panel
# ==============================

@bot.tree.command(
    name="request-loan-panel",
    description="لوحة طلب القروض"
)
async def request_loan_panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="💰 طلب قرض",
        description=(
            "هذه لوحة طلب القرض.\n\n"
            "يمكنك من خلالها تقديم طلب قرض."
        ),
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ==============================
# أمر اختبار
# ==============================

@bot.tree.command(
    name="test",
    description="اختبار استجابة البوت"
)
async def test(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🟢 البوت شغال ويستجيب!",
        ephemeral=True
    )


# ==============================
# تشغيل البوت
# ==============================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "❌ DISCORD_TOKEN غير موجود في Secrets"
    )

bot.run(TOKEN)
