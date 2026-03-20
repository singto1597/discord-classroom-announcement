import asyncpg
import logging
from datetime import date

# ตั้งค่า Logging ไว้ดู Error ใน Terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB")

class Database:
    def __init__(self, pool):
        self.pool = pool
    
    @classmethod
    async def create(cls, dsn):
        """สร้าง Connection Pool"""
        pool = await asyncpg.create_pool(dsn)
        return cls(pool)

    async def init_db(self):
        """สร้างตารางทั้งหมดถ้ายังไม่มี"""
        query = """
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY,
            server_id BIGINT UNIQUE NOT NULL,
            room_name TEXT NOT NULL,
            announcement_channel_id BIGINT,
            notify_time VARCHAR(5) DEFAULT '19:00'
        );
        CREATE TABLE IF NOT EXISTS default_schedules (
            id SERIAL PRIMARY KEY,
            room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
            day_of_week TEXT NOT NULL,
            attire TEXT,
            subjects TEXT
        );
        CREATE TABLE IF NOT EXISTS schedule_overrides (
            id SERIAL PRIMARY KEY,
            room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
            target_date DATE NOT NULL,
            new_attire TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
            task_name TEXT NOT NULL,
            due_date DATE NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS daily_notes (
            id SERIAL PRIMARY KEY,
            room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
            target_date DATE NOT NULL,
            bring_items TEXT,
            announcement TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
            user_name TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query)
            logger.info("✅ Database Tables Initialized Successfully!")
        except Exception as e:
            logger.error(f"❌ Failed to init DB: {e}")

    # ==========================================
    # หมวด: จัดการห้อง (Rooms)
    # ==========================================
    async def get_room_id(self, server_id: int):
        """ดึง Primary Key ของห้องจาก Discord Server ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT id FROM rooms WHERE server_id = $1", server_id)
                return row['id'] if row else None
        except Exception as e:
            logger.error(f"Error in get_room_id: {e}")
            return None
    async def set_notify_time(self, server_id: int, time_str: str):
        """เปลี่ยนเวลาแจ้งเตือนรายวัน (รูปแบบ HH:MM)"""
        try:
            async with self.pool.acquire() as conn:
                res = await conn.execute("UPDATE rooms SET notify_time = $1 WHERE server_id = $2", time_str, server_id)
                return res == "UPDATE 1"
        except Exception as e:
            logger.error(f"Error in set_notify_time: {e}")
            return False

    async def get_rooms_to_notify(self, current_time: str):
        """หาว่าเวลานี้ (current_time) มีห้องไหนต้องแจ้งเตือนบ้าง"""
        try:
            async with self.pool.acquire() as conn:
                # ดึงเฉพาะห้องที่ตั้งเวลาตรงกับตอนนี้ และมีการตั้ง channel ไว้แล้ว
                return await conn.fetch(
                    "SELECT server_id, announcement_channel_id FROM rooms WHERE notify_time = $1 AND announcement_channel_id IS NOT NULL", 
                    current_time
                )
        except Exception as e:
            logger.error(f"Error in get_rooms_to_notify: {e}")
            return []


    # ==========================================
    # หมวด: Audit Logs
    # ==========================================
    async def log_action(self, server_id: int, user_name: str, action: str, detail: str):
        """บันทึกประวัติว่าใครทำอะไรลงใน Database"""
        room_id = await self.get_room_id(server_id)
        if not room_id: return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO audit_logs (room_id, user_name, action, detail) VALUES ($1, $2, $3, $4)",
                    room_id, user_name, action, detail
                )
        except Exception as e:
            logger.error(f"Error in log_action: {e}")


    async def setup_room(self, server_id: int, room_name: str):
        """ลงทะเบียนห้องใหม่ หรืออัปเดตชื่อห้องถ้ามีอยู่แล้ว"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO rooms (server_id, room_name) 
                       VALUES ($1, $2) 
                       ON CONFLICT (server_id) 
                       DO UPDATE SET room_name = EXCLUDED.room_name""",
                    server_id, room_name
                )
                return True
        except Exception as e:
            logger.error(f"Error in setup_room: {e}")
            return False
    async def set_announcement_channel(self, server_id: int, channel_id: int):
        """บันทึก ID ของห้องแชทที่จะให้บอทส่งแจ้งเตือนอัตโนมัติ"""
        try:
            async with self.pool.acquire() as conn:
                # อัปเดตข้อมูลลงไปในห้องที่มี server_id ตรงกัน
                res = await conn.execute(
                    "UPDATE rooms SET announcement_channel_id = $1 WHERE server_id = $2",
                    channel_id, server_id
                )
                return res == "UPDATE 1" # จะ Return True ถ้าอัปเดตสำเร็จ 1 แถว
        except Exception as e:
            logger.error(f"Error in set_announcement_channel: {e}")
            return False

    # ==========================================
    # หมวด: ตารางเรียน & ข้อยกเว้น (Schedules)
    # ==========================================
    async def set_default_schedule(self, server_id: int, day_of_week: str, attire: str, subjects: str):
        room_id = await self.get_room_id(server_id)
        if not room_id: return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM default_schedules WHERE room_id = $1 AND day_of_week = $2", room_id, day_of_week)
                await conn.execute(
                    "INSERT INTO default_schedules (room_id, day_of_week, attire, subjects) VALUES ($1, $2, $3, $4)",
                    room_id, day_of_week, attire, subjects
                )
            return True
        except Exception as e:
            logger.error(f"Error in set_default_schedule: {e}")
            return False

    async def set_override(self, server_id: int, target_date: date, new_attire: str, note: str):
        room_id = await self.get_room_id(server_id)
        if not room_id: return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM schedule_overrides WHERE room_id = $1 AND target_date = $2", room_id, target_date)
                await conn.execute(
                    "INSERT INTO schedule_overrides (room_id, target_date, new_attire, note) VALUES ($1, $2, $3, $4)",
                    room_id, target_date, new_attire, note
                )
            return True
        except Exception as e:
            logger.error(f"Error in set_override: {e}")
            return False

    async def clear_override(self, server_id: int, target_date: date):
        room_id = await self.get_room_id(server_id)
        if not room_id: return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM schedule_overrides WHERE room_id = $1 AND target_date = $2", room_id, target_date)
            return True
        except Exception as e:
            logger.error(f"Error in clear_override: {e}")
            return False

    # ==========================================
    # หมวด: งานและการบ้าน (Tasks)
    # ==========================================
    async def add_task(self, server_id: int, task_name: str, due_date: date):
        room_id = await self.get_room_id(server_id)
        if not room_id: return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO tasks (room_id, task_name, due_date) VALUES ($1, $2, $3)",
                    room_id, task_name, due_date
                )
            return True
        except Exception as e:
            logger.error(f"Error in add_task: {e}")
            return False

    async def get_tasks(self, server_id: int, status: str = 'pending'):
        """ดึงรายการงานที่ยังไม่เสร็จของห้องนั้นๆ"""
        room_id = await self.get_room_id(server_id)
        if not room_id: return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, task_name, due_date, created_at FROM tasks WHERE room_id = $1 AND status = $2 ORDER BY due_date ASC",
                    room_id, status
                )
                return rows
        except Exception as e:
            logger.error(f"Error in get_tasks: {e}")
            return []

    async def edit_task(self, task_id: int, new_task_name: str, new_due_date: date):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tasks SET task_name = $1, due_date = $2 WHERE id = $3",
                    new_task_name, new_due_date, task_id
                )
            return True
        except Exception as e:
            logger.error(f"Error in edit_task: {e}")
            return False

    async def delete_task_returning(self, task_id: int):
        """ลบงานแล้วพ่นข้อมูลกลับมาด้วย"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("DELETE FROM tasks WHERE id = $1 RETURNING task_name", task_id)
                return row['task_name'] if row else None
        except Exception:
            return None
        
    async def mark_done_returning(self, task_id: int):
        """อัปเดตงานว่าเสร็จแล้ว และคืนค่าชื่องานกลับมา"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("UPDATE tasks SET status = 'done' WHERE id = $1 RETURNING task_name", task_id)
                return row['task_name'] if row else None
        except Exception:
            return None

    # ==========================================
    # หมวด: โน้ตรายวันและของที่ต้องเตรียม (Daily Notes)
    # ==========================================
    async def add_daily_note(self, server_id: int, target_date: date, bring_items: str, announcement: str):
        room_id = await self.get_room_id(server_id)
        if not room_id: return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM daily_notes WHERE room_id = $1 AND target_date = $2", room_id, target_date)
                await conn.execute(
                    "INSERT INTO daily_notes (room_id, target_date, bring_items, announcement) VALUES ($1, $2, $3, $4)",
                    room_id, target_date, bring_items, announcement
                )
            return True
        except Exception as e:
            logger.error(f"Error in add_daily_note: {e}")
            return False
    
    async def delete_daily_note_returning(self, server_id: int, target_date: date):
        """ลบโน้ตแล้วพ่นข้อมูลกลับมา"""
        room_id = await self.get_room_id(server_id)
        if not room_id: return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "DELETE FROM daily_notes WHERE room_id = $1 AND target_date = $2 RETURNING bring_items, announcement",
                    room_id, target_date
                )
                return row
        except Exception:
            return None