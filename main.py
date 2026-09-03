@bot.tree.command(
    name="gamepanel",
    description="لوحة تحكم سعودي تايم"
)
async def gamepanel(interaction: discord.Interaction):

    try:
        # يثبت لديسكورد أن البوت استجاب
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="🇸🇦 Saudi Time",
            description="مرحباً بك في لوحة تحكم السيرفر",
            color=discord.Color.green()
        )

        embed.add_field(
            name="🎫 التذاكر",
            value="إدارة التذاكر",
            inline=False
        )

        embed.add_field(
            name="👮 الإدارة",
            value="إدارة أعضاء السيرفر",
            inline=False
        )

        embed.add_field(
            name="💼 الوظائف",
            value="إدارة الوظائف والرتب",
            inline=False
        )

        embed.set_footer(
            text=f"طلب بواسطة {interaction.user}"
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    except Exception as e:
        print("GAMEPANEL ERROR:", e)

        if interaction.response.is_done():
            await interaction.followup.send(
                f"❌ صار خطأ:\n`{e}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ صار خطأ:\n`{e}`",
                ephemeral=True
            )
        @bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ تم تسجيل {len(synced)} أمر")
    except Exception as e:
        print(f"❌ خطأ في تسجيل الأوامر: {e}")

    print(f"🟢 البوت شغال: {bot.user}")    
