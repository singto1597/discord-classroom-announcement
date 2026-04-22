import discord

import datetime
from datetime import timezone, timedelta

THAI_TZ = timezone(timedelta(hours=7))

class AddNoteModal(discord.ui.Modal, title='📝 เพิ่มโน้ตใหม่'):
    def __init__(self, db):
        super().__init__()
        self.db = db

        tomorrow_str = (datetime.datetime.now(THAI_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

        self.target_date = discord.ui.TextInput(
            label='วันที่ต้องการเพิ่ม (YYYY-MM-DD)',
            default=tomorrow_str,
            required=True
        )
        self.bring_items = discord.ui.TextInput(
            label='ของที่ต้องนำมา',
            style=discord.TextStyle.paragraph, 
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
        self.add_item(self.bring_items)
        self.add_item(self.announcement)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_date = datetime.datetime.strptime(self.target_date.value, "%Y-%m-%d").date()
        except ValueError:
            return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD นะ", ephemeral=True)

        bring_items = self.bring_items.value if self.bring_items.value.strip() else "-"
        announcement = self.announcement.value if self.announcement.value.strip() else "-"

        success = await self.db.add_daily_note(interaction.guild_id, target_date, bring_items, announcement)

        if success:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Add Note", f"โน้ตของวันที่ {target_date}")
            await interaction.response.send_message(f"📌 **บันทึกโน้ตวันที่ {target_date}**\n🎒 ให้เตรียม: {bring_items}\n📢 โน้ต: {announcement}")
        else:
            await interaction.response.send_message("❌ ผิดพลาด", ephemeral=True)