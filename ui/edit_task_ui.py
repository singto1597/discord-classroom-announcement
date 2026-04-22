import discord

import datetime

class EditTaskModal(discord.ui.Modal, title='✏️ แก้ไขรายละเอียดงาน'):
    def __init__(self, db, task_id: int, old_name: str, old_detail: str, old_date: str):
        super().__init__()
        self.db = db
        self.task_id = task_id

        self.task_name = discord.ui.TextInput(
            label='ชื่องาน',
            default=old_name,
            required=True
        )
        self.task_detail = discord.ui.TextInput(
            label='รายละเอียดเพิ่มเติม',
            style=discord.TextStyle.paragraph, 
            default=old_detail if old_detail != "-" else "",
            required=False
        )

        self.due_date = discord.ui.TextInput(
            label='กำหนดส่ง (YYYY-MM-DD)',
            default=str(old_date),
            required=True
        )

        self.add_item(self.task_name)
        self.add_item(self.task_detail)
        self.add_item(self.due_date)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_date = datetime.datetime.strptime(self.due_date.value, "%Y-%m-%d").date()
        except ValueError:
            return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD นะเว้ย", ephemeral=True)

        detail_val = self.task_detail.value if self.task_detail.value else "-"

        success = await self.db.edit_task(self.task_id, self.task_name.value, detail_val, target_date)
        if success:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Edit Task", f"แก้งาน ID {self.task_id}")
            await interaction.response.send_message(f"✅ **อัปเดตงานสำเร็จ!**\n📌 ชื่องาน: {self.task_name.value}\nℹ️ รายละเอียด: {detail_val}\n⏳ ส่งวันที่: {target_date}")
        else:
            await interaction.response.send_message("❌ แก้ไขไม่สำเร็จ เซิร์ฟเวอร์มีปัญหา", ephemeral=True)