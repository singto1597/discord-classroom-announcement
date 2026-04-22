import discord

import datetime
from datetime import timezone, timedelta

THAI_TZ = timezone(timedelta(hours=7))

class SetOverrideModal(discord.ui.Modal, title='🚨 ตั้งค่าข้อยกเว้นฉุกเฉิน'):
    def __init__(self, db, server_id):
        super().__init__()
        self.db = db
        self.server_id = server_id

        tomorrow_str = (datetime.datetime.now(THAI_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

        self.target_date = discord.ui.TextInput(
            label='วันที่ต้องการแก้ (YYYY-MM-DD)',
            default=tomorrow_str,
            required=True
        )
        self.new_attire = discord.ui.TextInput(
            label='ชุดที่ให้ใส่',
            style=discord.TextStyle.short, 
            default="-",
            required=False
        )
        self.announcement = discord.ui.TextInput(
            label='โน้ตที่อยากแจ้งให้ทราบ',
            style=discord.TextStyle.paragraph, 
            default="-",
            required=False
        )


        self.add_item(self.target_date)
        self.add_item(self.new_attire)
        self.add_item(self.announcement)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_date = datetime.datetime.strptime(self.target_date.value, "%Y-%m-%d").date()
        except ValueError:
            return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD นะ", ephemeral=True)

        new_attire = self.new_attire.value if self.new_attire.value.strip() else "-"
        announcement = self.announcement.value if self.announcement.value.strip() else "-"

        success = await self.db.set_override(self.server_id, target_date, new_attire, announcement)
        if success:
            await self.db.log_action(self.server_id, interaction.user.name, "Set Override", f"วันที่ {target_date} ใส่ชุด {new_attire}")
            await interaction.response.send_message(f"🚨 **ตั้งค่าข้อยกเว้นวันที่ {target_date}**\n👕 ใส่ชุด: {new_attire}\n📝 หมายเหตุ: {announcement}")
        else:
            await interaction.response.send_message("❌ ผิดพลาด", ephemeral=True)