import os
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"تم تسجيل الدخول: {bot.user}")
        print(f"تمت مزامنة {len(synced)} أمر Slash")
    except Exception as e:
        print(f"خطأ في مزامنة الأوامر: {e}")


@bot.tree.command(name="لوحه", description="فتح لوحة تحكم السيرفر")
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎛️ لوحة تحكم السيرفر",
        description="اختر النظام الذي تريد استخدامه من الأزرار بالأسفل.",
    )

    view = discord.ui.View(timeout=None)

    buttons = [
        ("🎫 التذاكر", "tickets"),
        ("✅ التفعيل", "verify"),
        ("⭐ النقاط", "points"),
        ("🏦 البنك", "bank"),
        ("👮 الوظائف", "jobs"),
        ("✈️ الرحلات", "trips"),
        ("📢 التعاميم", "announcements"),
        ("⚙️ التسطيب", "setup"),
    ]

    for text, custom_id in buttons:
        view.add_item(
            discord.ui.Button(
                label=text,
                style=discord.ButtonStyle.primary,
                custom_id=custom_id
            )
        )

    await interaction.response.send_message(embed=embed, view=view)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    cid = interaction.data.get("custom_id")

    messages = {
        "tickets": "🎫 نظام التذاكر\nسيتم فتح نظام التذاكر هنا.",
        "verify": "✅ نظام التفعيل\nسيتم إعداد نظام التفعيل هنا.",
        "points": "⭐ نظام النقاط\nسيتم إعداد النقاط هنا.",
        "bank": "🏦 نظام البنك\nسيتم إعداد البنك هنا.",
        "jobs": "👮 نظام الوظائف والقطاعات.",
        "trips": "✈️ نظام الرحلات.",
        "announcements": "📢 نظام التعاميم.",
        "setup": "⚙️ **التسطيب**\nاختر النظام الذي تريد تسطيبه."
    }

    if cid in messages:
        await interaction.response.send_message(
            messages[cid],
            ephemeral=True
        )


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN غير موجود في Environment Variables")

bot.run(TOKEN)
