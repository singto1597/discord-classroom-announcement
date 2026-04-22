import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
from datetime import timezone, timedelta
import re

THAI_TZ = timezone(timedelta(hours=7))

@app_commands.guild_only()
class BotCommands(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.daily_notification.start()
    
    def cog_unload(self):
        self.daily_notification.cancel()

    def parse_date(self, date_str: str):
        try:
            return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    def get_thai_day(self, date_obj):
        days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
        return days[date_obj.weekday()]

    # ==========================================
    # ระบบ Autocomplete พิมพ์แล้วโชว์ลิสต์งานอัตโนมัติ!
    # ==========================================
    async def task_autocomplete(self, interaction: discord.Interaction, current: str):
        server_id = interaction.guild_id
        tasks = await self.db.get_tasks(server_id)
        
        choices = []
        for t in tasks:
            if current.lower() in t['task_name'].lower():
                display_name = f"{t['task_name']} (ส่ง {t['due_date']})"
                if len(display_name) > 100:
                    display_name = display_name[:95] + "..."
                
                choices.append(app_commands.Choice(name=display_name, value=t['id']))
        return choices[:25]
    
    # ==========================================
    # ระบบ Loop แจ้งเตือนอัตโนมัติ
    # ==========================================
    @tasks.loop(minutes=1)
    async def daily_notification(self):
        """ฟังก์ชันนี้จะรันเช็คตัวเองทุกๆ 1 นาที"""
        # ดึงเวลาปัจจุบันของไทย ให้อยู่ในรูป "HH:MM"
        now = datetime.datetime.now(THAI_TZ)
        current_time_str = now.strftime("%H:%M")


        rooms_to_notify = await self.db.get_rooms_to_notify(current_time_str)
        if not rooms_to_notify: 
            return

        target_date = now.date() + timedelta(days=1)

        for room in rooms_to_notify:
            server_id = room['server_id']
            channel_id = room['announcement_channel_id']
            
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    data = await self.fetch_daily_summary(server_id, target_date)
                    if data:
                        embed = self.build_summary_embed("🌙 แจ้งเตือนอัตโนมัติ: เตรียมตัวสำหรับวันพรุ่งนี้!", data)
                        await channel.send(content="📢 @everyone สรุปตารางเรียนและงานของวันพรุ่งนี้", embed=embed)
            except Exception as e:
                print(f"⚠️ [Loop Warning] ส่งข้อความไป server {server_id} ไม่ได้: {e}")
    
    @daily_notification.before_loop
    async def before_daily_notification(self):
        await self.bot.wait_until_ready()


    @app_commands.command(name="help", description="ดูคู่มือและคำสั่งทั้งหมดของบอท")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="คู่มือการใช้งาน Classroom-Sync",
            description="บอทผู้ช่วยประจำห้อง พิมพ์ `/` แล้วตามด้วยคำสั่งพวกนี้ได้เลย:",
            color=discord.Color.blue()
        )

        # หมวดหมู่ 1: ดึงดูข้อมูล 
        embed.add_field(name="📅 หมวดเช็คตาราง", value=
            "`/today` - ดูตารางเรียนและงานของวันนี้\n"
            "`/tomorrow` - ดูตารางเรียนและงานของวันพรุ่งนี้\n"
            "`/list_tasks` - เช็คงานค้างทั้งหมดของห้อง", inline=False)

        # หมวดหมู่ 2: จัดการงาน
        embed.add_field(name="📝 หมวดจัดการงาน", value=
            "`/add_task` - เพิ่มงาน/การบ้านใหม่\n"
            "`/edit_task` - แก้ไขชื่องานหรือวันส่ง\n"
            "`/mark_done` - ติ๊กส่งงาน (จะได้เลิกเตือน)\n"
            "`/delete_task` - ลบงานทิ้งไปเลย", inline=False)

        # หมวดหมู่ 3: จัดการโน้ตและตารางพิเศษ
        embed.add_field(name="📌 หมวดโน้ตและข้อยกเว้น", value=
            "`/add_note` - โน้ตของที่ต้องเอามา/ประกาศพิเศษ\n"
            "`/delete_note` - ลบโน้ตรายวัน\n"
            "`/set_override` - ตั้งข้อยกเว้นชุดหรือกิจกรรมรายวัน", inline=False)

        # หมวดหมู่ 4: ตั้งค่า
        embed.add_field(name="⚙️ หมวดตั้งค่าระบบ (แอดมิน)", value=
            "`/setup_room` - ลงทะเบียนห้อง (ทำครั้งแรก)\n"
            "`/set_channel` - เลือกห้องแชทให้บอทส่งแจ้งเตือน\n"
            "`/set_schedule` - ตั้งตารางเรียนยืนพื้นจันทร์-ศุกร์\n"
            "`/set_time` - ตั้งเวลาแจ้งเตือนรายวันอัตโนมัติ", inline=False)


        embed.set_footer(text="💡 ทริค: หลายคำสั่งมีเมนูให้กดเลือก ไม่ต้องพิมพ์เองทั้งหมดนะ")


        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # คำสั่งให้แอดมินเปลี่ยนเวลาได้
    # ==========================================
    @app_commands.command(name="set_time", description="ตั้งเวลาแจ้งเตือนรายวัน (ค่าเริ่มต้น 19:00)")
    @app_commands.describe(time_str="ระบุเวลาแบบ 24 ชั่วโมง เช่น 19:00, 20:30")
    async def set_time(self, interaction: discord.Interaction, time_str: str):
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", time_str):
            return await interaction.response.send_message("❌ รูปแบบเวลาผิด ต้องเป็น HH:MM เช่น 19:00, 20:30", ephemeral=True)
            
        success = await self.db.set_notify_time(interaction.guild_id, time_str)
        if success:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Set Time", f"เปลี่ยนเวลาเตือนเป็น {time_str}")
            await interaction.response.send_message(f"⏰ เปลี่ยนเวลาแจ้งเตือนอัตโนมัติเป็น **{time_str} น.** เรียบร้อยแล้ว!")
        else:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากด /setup_room ก่อน", ephemeral=True)

    # ==========================================
    # หมวด 1: จัดการห้อง
    # ==========================================
    @app_commands.command(name="setup_room", description="ตั้งค่าบอทและกำหนดชื่อห้องเรียน")
    async def setup_room(self, interaction: discord.Interaction, room_name: str):
        server_id = interaction.guild_id
        success = await self.db.setup_room(server_id, room_name)
        if success:
            await self.db.log_action(server_id, interaction.user.name, "Setup Room", f"ตั้งชื่อห้องเป็น {room_name}")
            await interaction.response.send_message(f"✅ ลงทะเบียนห้อง **{room_name}** สำเร็จ!\n👉 กด `/set_channel` ด้วยนะ")
        else:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด!", ephemeral=True)

    @app_commands.command(name="set_channel", description="กำหนดห้องแชทที่จะให้บอทแจ้งเตือน")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        server_id = interaction.guild_id
        success = await self.db.set_announcement_channel(server_id, channel.id)
        if success:
            await self.db.log_action(server_id, interaction.user.name, "Set Channel", f"ตั้งค่าไปที่ห้อง {channel.name}")
            await interaction.response.send_message(f"📢 ตั้งค่าสำเร็จ! บอทจะแจ้งเตือนที่ห้อง {channel.mention}")
        else:
            await interaction.response.send_message("❌ กรุณากด `/setup_room` ก่อน", ephemeral=True)

    # ==========================================
    # หมวด 2: ตารางเรียนและข้อยกเว้น
    # ==========================================
    @app_commands.command(name="set_schedule", description="ตั้งตารางเรียนยืนพื้น")
    @app_commands.choices(day=[app_commands.Choice(name=d, value=d) for d in ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]])
    async def set_schedule(self, interaction: discord.Interaction, day: app_commands.Choice[str], attire: str, subjects: str):
        server_id = interaction.guild_id
        success = await self.db.set_default_schedule(server_id, day.value, attire, subjects)
        if success:
            await self.db.log_action(server_id, interaction.user.name, "Set Schedule", f"แก้วัน{day.value} เป็นชุด {attire}")
            await interaction.response.send_message(f"✅ บันทึกตารางวัน**{day.value}**\n👕 ชุด: {attire}\n📚 วิชา: {subjects}")
        else:
            await interaction.response.send_message("❌ ผิดพลาด", ephemeral=True)

    @app_commands.command(name="set_override", description="ตั้งค่าข้อยกเว้นฉุกเฉิน")
    async def set_override(self, interaction: discord.Interaction, date_str: str, new_attire: str, note: str = "-"):
        server_id = interaction.guild_id
        target_date = self.parse_date(date_str)
        if not target_date: return await interaction.response.send_message("❌ รูปแบบวันที่ผิด YYYY-MM-DD", ephemeral=True)

        success = await self.db.set_override(server_id, target_date, new_attire, note)
        if success:
            await self.db.log_action(server_id, interaction.user.name, "Set Override", f"วันที่ {target_date} ใส่ชุด {new_attire}")
            await interaction.response.send_message(f"🚨 **ตั้งค่าข้อยกเว้นวันที่ {target_date}**\n👕 ใส่ชุด: {new_attire}\n📝 หมายเหตุ: {note}")
        else:
            await interaction.response.send_message("❌ ผิดพลาด", ephemeral=True)

    # ==========================================
    # หมวด 3: จัดการงาน 
    # ==========================================
    @app_commands.command(name="add_task", description="เพิ่มงานใหม่")
    async def add_task(self, interaction: discord.Interaction, task_name: str, due_date: str):
        server_id = interaction.guild_id
        target_date = self.parse_date(due_date)
        if not target_date: return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD", ephemeral=True)

        success = await self.db.add_task(server_id, task_name, target_date)
        if success:
            await self.db.log_action(server_id, interaction.user.name, "Add Task", f"เพิ่มงาน {task_name}")
            await interaction.response.send_message(f"📝 **เพิ่มงานใหม่:** {task_name}\n⏳ **กำหนดส่ง:** {target_date}")
        else:
            await interaction.response.send_message("❌ เพิ่มงานไม่สำเร็จ", ephemeral=True)


    @app_commands.command(name="mark_done", description="ติ๊กงานว่าเสร็จแล้ว (มีเมนูให้เลือก)")
    @app_commands.autocomplete(task_id=task_autocomplete)
    async def mark_done(self, interaction: discord.Interaction, task_id: int):
        task_name = await self.db.mark_done_returning(task_id)
        if task_name:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Mark Done", f"ส่งงาน {task_name} แล้ว")
            await interaction.response.send_message(f"✅ ทำสัญลักษณ์ว่างาน **{task_name}** เสร็จ เรียบร้อยแล้ว!")
        else:
            await interaction.response.send_message(f"❌ ไม่พบงานนี้ หรืออาจจะถูกลบไปแล้ว", ephemeral=True)


    @app_commands.command(name="delete_task", description="ลบงานทิ้ง (มีเมนูให้เลือก)")
    @app_commands.autocomplete(task_id=task_autocomplete)
    async def delete_task(self, interaction: discord.Interaction, task_id: int):
        deleted_task_name = await self.db.delete_task_returning(task_id)
        if deleted_task_name:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Delete Task", f"ลบงาน {deleted_task_name}")
            await interaction.response.send_message(f"🗑️ ลบงาน **{deleted_task_name}** ทิ้งแล้ว")
        else:
            await interaction.response.send_message("❌ ลบไม่สำเร็จ", ephemeral=True)

    @app_commands.command(name="list_tasks", description="ดูลิสต์งานทั้งหมดที่ยังไม่เสร็จ")
    async def list_tasks(self, interaction: discord.Interaction):
        tasks = await self.db.get_tasks(interaction.guild_id)
        if not tasks: return await interaction.response.send_message("🎉 ไม่มีงานเลยจ้าา")

        embed = discord.Embed(title="📋 รายการงานที่ยังไม่เสร็จ", color=discord.Color.blue())
        for task in tasks:

            created_str = task['created_at'].strftime("%Y-%m-%d") if task['created_at'] else "ไม่ระบุ"
            embed.add_field(name=f"📌 {task['task_name']}", value=f"📅 กำหนดส่ง: {task['due_date']} \n(บันทึกเมื่อ: {created_str})", inline=False)
        await interaction.response.send_message(embed=embed)
    

    @app_commands.command(name="edit_task", description="แก้ไขชื่องาน หรือ วันกำหนดส่ง (มีเมนูให้เลือก)")
    @app_commands.autocomplete(task_id=task_autocomplete)
    async def edit_task(self, interaction: discord.Interaction, task_id: int, new_task_name: str, new_due_date: str):
        target_date = self.parse_date(new_due_date)
        if not target_date: return await interaction.response.send_message("❌ วันที่ผิด YYYY-MM-DD", ephemeral=True)

        success = await self.db.edit_task(task_id, new_task_name, target_date)
        if success:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Edit Task", f"แก้งาน ID {task_id} เป็น {new_task_name}")
            await interaction.response.send_message(f"✏️ **อัปเดตงานสำเร็จ!**\nชื่องาน: {new_task_name}\nส่งวันที่: {target_date}")
        else:
            await interaction.response.send_message("❌ แก้ไขไม่สำเร็จ", ephemeral=True)

    # ==========================================
    # หมวด 4: โน้ตรายวัน
    # ==========================================
    @app_commands.command(name="add_note", description="เพิ่มโน้ตรายวัน")
    async def add_note(self, interaction: discord.Interaction, date_str: str, bring_items: str = "-", announcement: str = "-"):
        target_date = self.parse_date(date_str)
        if not target_date: return await interaction.response.send_message("❌ วันที่ผิด", ephemeral=True)

        success = await self.db.add_daily_note(interaction.guild_id, target_date, bring_items, announcement)
        if success:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Add Note", f"โน้ตของวันที่ {target_date}")
            await interaction.response.send_message(f"📌 **บันทึกโน้ตวันที่ {target_date}**\n🎒 ให้เตรียม: {bring_items}\n📢 โน้ต: {announcement}")
        else:
            await interaction.response.send_message("❌ ผิดพลาด", ephemeral=True)

    @app_commands.command(name="delete_note", description="ลบโน้ตรายวัน")
    async def delete_note(self, interaction: discord.Interaction, date_str: str):
        target_date = self.parse_date(date_str)
        if not target_date: return await interaction.response.send_message("❌ วันที่ผิด", ephemeral=True)

        deleted_data = await self.db.delete_daily_note_returning(interaction.guild_id, target_date)
        if deleted_data:
            await self.db.log_action(interaction.guild_id, interaction.user.name, "Delete Note", f"ลบโน้ตวันที่ {target_date}")
            await interaction.response.send_message(f"🗑️ **ลบโน้ตวันที่ {target_date} แล้ว!**\nสิ่งที่ลบไป:\n🎒 {deleted_data['bring_items']}\n📢 {deleted_data['announcement']}")
        else:
            await interaction.response.send_message("❌ ไม่มีโน้ตในวันนั้นให้ลบ", ephemeral=True)

    # ==========================================
    # หมวด 5: เรียกดูข้อมูลแบบทันใจ
    # ==========================================
    async def fetch_daily_summary(self, server_id, target_date):
        room_id = await self.db.get_room_id(server_id)
        if not room_id: return None

        day_name = self.get_thai_day(target_date)
        data = {"date": target_date, "day": day_name, "attire": "-", "subjects": "-", "bring": "-", "note": "-", "tasks_due": []}

        async with self.db.pool.acquire() as conn:
            default = await conn.fetchrow("SELECT attire, subjects FROM default_schedules WHERE room_id = $1 AND day_of_week = $2", room_id, day_name)
            if default:
                data["attire"] = default["attire"]
                data["subjects"] = default["subjects"]
            
            override = await conn.fetchrow("SELECT new_attire, note FROM schedule_overrides WHERE room_id = $1 AND target_date = $2", room_id, target_date)
            if override:
                data["attire"] = f"🚨 {override['new_attire']} (กรณีพิเศษ)"
                data["note"] = override['note']
            
            note_data = await conn.fetchrow("SELECT bring_items, announcement FROM daily_notes WHERE room_id = $1 AND target_date = $2", room_id, target_date)
            if note_data:
                data["bring"] = note_data["bring_items"]
                if not override: data["note"] = note_data["announcement"]
            
            today = datetime.datetime.now(THAI_TZ).date()
            tasks = await conn.fetch("SELECT task_name, due_date FROM tasks WHERE room_id = $1 AND status = 'pending' ORDER BY due_date ASC", room_id)
            
            tasks_formatted = []
            for t in tasks:
                days_left = (t['due_date'] - today).days
                if days_left < 0:
                    status = f"🔴 **(เลยกำหนดมา {-days_left} วัน!)**"
                elif days_left == 0:
                    status = f"🔥 **(ส่งวันนี้!)**"
                elif days_left == 1:
                    status = f"⚠️ **(ส่งพรุ่งนี้!)**"
                else:
                    status = f"🟢 (เหลืออีก {days_left} วัน)"
                tasks_formatted.append(f"• {t['task_name']} {status}")
            
            data["tasks_due"] = tasks_formatted

        return data

    def build_summary_embed(self, title, data):
        embed = discord.Embed(title=title, description=f"📅 **วัน{data['day']}ที่ {data['date']}**", color=discord.Color.green())
        embed.add_field(name="👕 ชุดที่ต้องใส่", value=data['attire'], inline=True)
        embed.add_field(name="📚 วิชาเรียน", value=data['subjects'], inline=True)
        
        if data['bring'] != "-": embed.add_field(name="🎒 สิ่งที่ต้องเตรียม", value=data['bring'], inline=False)
        if data['note'] != "-": embed.add_field(name="📢 ประกาศ/หมายเหตุ", value=data['note'], inline=False)
            
        if data['tasks_due']:
            task_list = "\n".join(data['tasks_due'])
            if len(task_list) > 1024:
                task_list = task_list[:1000] + "...\n*(และงานอื่นๆ อีกเพียบ ไปเคลียร์ด้วย!)*"
            embed.add_field(name="⚠️ ลิสต์งานค้างทั้งหมด!", value=task_list, inline=False)
        else:
            embed.add_field(name="✅ ลิสต์งานค้างทั้งหมด!", value="ไม่มีงานจ้า", inline=False)
            
        return embed

    @app_commands.command(name="today", description="สรุปข้อมูลทั้งหมดของวันนี้")
    async def today(self, interaction: discord.Interaction):
        target = datetime.datetime.now(THAI_TZ).date()
        data = await self.fetch_daily_summary(interaction.guild_id, target)
        if not data: return await interaction.response.send_message("❌ ยังไม่ได้ตั้งค่าห้อง กด /setup_room ก่อน", ephemeral=True)
        await interaction.response.send_message(embed=self.build_summary_embed("☀️ สรุปตารางวันนี้", data))

    @app_commands.command(name="tomorrow", description="สรุปข้อมูลทั้งหมดของวันพรุ่งนี้")
    async def tomorrow(self, interaction: discord.Interaction):
        target = datetime.datetime.now(THAI_TZ).date() + timedelta(days=1)
        data = await self.fetch_daily_summary(interaction.guild_id, target)
        if not data: return await interaction.response.send_message("❌ ยังไม่ได้ตั้งค่าห้อง กด /setup_room ก่อน", ephemeral=True)
        await interaction.response.send_message(embed=self.build_summary_embed("🌙 เตรียมตัวสำหรับวันพรุ่งนี้", data))

async def setup(bot, db):
    await bot.add_cog(BotCommands(bot, db))