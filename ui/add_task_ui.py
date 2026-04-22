import discord

import datetime
from datetime import timezone, timedelta

THAI_TZ = timezone(timedelta(hours=7))

class AddTaskModal(discord.ui.Modal, title='📝 เพิ่มงาน/การบ้านใหม่'):
    def __init__(self, db, server_id):
        super().__init__()
        self.db = db
        self.server_id = server_id

        tomorrow_str = (datetime.datetime.now(THAI_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

        self.task_name = discord.ui.TextInput(
            label='ชื่องาน',
            required=True
        )
        self.task_detail = discord.ui.TextInput(
            label='รายละเอียดเพิ่มเติม',
            style=discord.TextStyle.paragraph, 
            default="-",
            required=False
        )

        self.due_date = discord.ui.TextInput(
            label='กำหนดส่ง (YYYY-MM-DD)',
            default=tomorrow_str,
            required=True
        )

        self.add_item(self.task_name)
        self.add_item(self.task_detail)
        self.add_item(self.due_date)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_date = datetime.datetime.strptime(self.due_date.value, "%Y-%m-%d").date()
        except ValueError:
            return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD นะ", ephemeral=True)

        detail_val = self.task_detail.value if self.task_detail.value else "-"

        success = await self.db.add_task(self.server_id, self.task_name.value, detail_val, target_date)
        if success:
            await self.db.log_action(self.server_id, interaction.user.name, "Add Task", f"เพิ่มงาน {self.task_name.value}")
            await interaction.response.send_message(
                f"📝 **เพิ่มงานใหม่:** {self.task_name.value}\n"
                f"ℹ️ **รายละเอียด:** {detail_val}\n"
                f"⏳ **กำหนดส่ง:** {target_date}"
            )
        else:
            await interaction.response.send_message("❌ เพิ่มงานไม่สำเร็จ", ephemeral=True)