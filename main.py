import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")
⁠await bot.tree.sync
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
