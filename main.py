import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user.name}")

# أمر الآي دي (ID System)
@bot.command(name="id")
async def show_id(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    embed = discord.Embed(
        title="• WoLf System - ID •",
        color=discord.Color.dark_red()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="اسم العضو:", value=member.mention, inline=True)
    embed.add_field(name="الآي دي (ID):", value=str(member.id), inline=True)
    embed.add_field(name="تاريخ الانضمام:", value=member.joined_at.strftime("%Y-%m-%d"), inline=False)
    embed.set_footer(text="صُنع لخدمة الأعضاء.", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    
    await ctx.send(embed=embed)

# نظام التسطيب (طلب تسطيب قراند / مودات / سيرفرات)
@bot.command(name="تسطيب")
async def install_system(ctx, *, details: str = None):
    if not details:
        await ctx.send("يرجى كتابة تفاصيل الطلب بجانب الأمر. مثال: `!تسطيب تركيب مودات VRP`")
        return

    embed = discord.Embed(
        title="📥 طلب تسطيب جديد",
        description="تم استلام طلب التسطيب بنجاح.",
        color=discord.Color.red()
    )
    embed.add_field(name="صاحب الطلب:", value=ctx.author.mention, inline=False)
    embed.add_field(name="التفاصيل:", value=details, inline=False)
    embed.set_footer(text="جاري معالجة الطلب من قبل الإدارة...")

    await ctx.send(embed=embed)

bot.run("YOUR_BOT_TOKEN")
