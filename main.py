import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from db import Database
import commands as bot_cmds # นำเข้าไฟล์ commands.py

# โหลดตัวแปร
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_DSN = os.getenv('DB_DSN') # ต้องเพิ่ม DSN ของ Postgres ใน .env ด้วย

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.db = None

    async def setup_hook(self):
        # 1. เริ่มต้น Database Connection
        print("Connecting to Database...")
        self.db = await Database.create(DB_DSN)
        
        # 2. สร้างตารางทั้งหมด
        await self.db.init_db()
        
        # 3. โหลดคำสั่งจากไฟล์ commands.py 
        await bot_cmds.setup(self, self.db)
        
        # 4. ซิงค์ Slash Commands เข้า Discord
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} command(s)")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'✅ บอท {bot.user} พร้อมทำงานแล้ว!')

# รันตัวบอท
if __name__ == '__main__':
    bot.run(TOKEN)