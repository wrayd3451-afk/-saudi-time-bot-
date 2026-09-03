import os
import discord
from discord.ext import commands
from discord import app_commands

# ==========================================
# إعدادات البوت
# ==========================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="-",
    intents=intents
)


# ==========================================
# عند تشغيل البوت
# ==========================================

@bot.event
async def on_ready():
    print("========================================")
    print(f"البوت شغال: {bot.user}")
    print("========================================")

    try:
        synced = await bot.tree.sync()
        print(f"تم تسجيل {len(synced)} أمر Slash")
    except Exception as error:
        print(f"خطأ في مزامنة الأوامر: {error}")


# ==========================================
# /test
# ==========================================

@bot.tree.command(
    name="test",
    description="اختبار استجابة البوت"
)
async def test(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🟢 البوت شغال ويستجيب!",
        ephemeral=True
    )


# ==========================================
# /gamepanel
# ==========================================

@bot.tree.command(
    name="gamepanel",
    description="لوحة تحكم Saudi Time"
)
async def gamepanel(interaction: discord.Interaction):
    try:
        # الرد مباشرة حتى لا يظهر:
        # The application did not respond
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="🇸🇦 Saudi Time",
            description=(
                "مرحباً بك في لوحة تحكم السيرفر.\n\n"
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

    except Exception as error:
        print(f"GAMEPANEL ERROR: {error}")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ حدث خطأ: {error}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ حدث خطأ: {error}",
                    ephemeral=True
                )
        except Exception as second_error:
            print(f"ERROR WHILE SENDING ERROR: {second_error}")


# ==========================================
# /role
# ==========================================

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
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ ما عندك صلاحية إدارة الرتب.",
            ephemeral=True
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "❌ هذا الأمر يعمل داخل السيرفر فقط.",
            ephemeral=True
        )
        return

    bot_member = interaction.guild.me

    if bot_member is None:
        await interaction.response.send_message(
            "❌ ما قدرت أتحقق من رتبة البوت.",
            ephemeral=True
        )
        return

    if role >= bot_member.top_role:
        await interaction.response.send_message(
            "❌ ما أقدر أتعامل مع هذه الرتبة لأنها أعلى من رتبة البوت.",
            ephemeral=True
        )
        return

    try:
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

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ البوت ما عنده صلاحية تعديل هذه الرتبة.",
            ephemeral=True
        )
    except Exception as error:
        print(f"ROLE ERROR: {error}")

        await interaction.response.send_message(
            "❌ صار خطأ أثناء تعديل الرتبة.",
            ephemeral=True
        )


# ==========================================
# /roles-slash
# ==========================================

@bot.tree.command(
    name="roles-slash",
    description="إدارة رتب السيرفر"
)
async def roles_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ إدارة الرتب",
        description=(
            "استخدم الأمر التالي لإضافة أو إزالة رتبة:\n\n"
            "`/role`"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ==========================================
# /request-loan-panel
# ==========================================

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


# ==========================================
# تشغيل البوت
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN غير موجود في Secrets"
    )

bot.run(TOKEN)
