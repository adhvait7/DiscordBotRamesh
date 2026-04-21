import discord
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

def log_expense(amount, category, notes="", user_id=None):
    conn = psycopg2.connect(
                host=os.getenv('DB_HOST'),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                sslmode='require'
            )
    cursor=conn.cursor()
    cursor.execute(
        "INSERT INTO expenses (amount, category, notes, user_id) VALUES (%s, %s, %s, %s)",
        (amount, category, notes if notes else None, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
class Client(discord.Client):
    async def on_ready(self):
        print("Hello, World!")
        print(f"Logged on as {self.user}!")
         
    async def on_message(self, message):
        if message.author == self.user:
            return
        elif message.content.lower() == "hi":
            await message.channel.send(f'hola {message.author.mention} :)')
        elif message.content == '!clear':
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST'),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                sslmode='require'
            )
            cursor = conn.cursor()
            cursor.execute("DELETE FROM expenses WHERE user_id = %s", (str(message.author.id),))
            conn.commit()
            cursor.close()
            conn.close()
            await message.channel.send("All your expenses have been cleared.")
        elif message.content.startswith('!t '):
            parts = message.content[3:].split(' ',1)
            
            if len(parts) < 2:
                await message.channel.send("Format: `!t 50 upi` or `!t 100 food groceries`")
                return
            
            try:
                amount = float(parts[0])
                rest = parts[1].split(' ', 1)
                category = rest[0]
                notes = rest[1] if len(rest) > 1 else ""
                
                log_expense(amount, category, notes, user_id=str(message.author.id))
                await message.channel.send(f'✓ Logged ₹{amount} ({category})')
            except ValueError:
                await message.channel.send("Amount must be a number!")
        elif message.content == '!view':
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST'),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                sslmode='require'
            )
            cursor = conn.cursor()
            cursor.execute("SELECT id, amount, category, notes, date FROM expenses WHERE user_id = %s ORDER BY date ASC",
            (str(message.author.id),))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Format as table with better spacing
            table = "```\n"
            table += "S.No │ Amount  │ Category   │ Notes      │ Date\n"
            table += "─" * 70 + "\n"
            for i, row in enumerate(rows, start=1):
                id, amount, category, notes, date = row
                date_str = date.strftime('%Y-%m-%d %H:%M')
                notes_str = (notes[:15] + '...') if notes and len(notes) > 15 else (notes or '-')
                category_str = category[:10]
                table += f"{i:2} │ ₹{amount:7.2f} │ {category_str:10} │ {notes_str:10} │ {date_str}\n"
                
            total = sum([row[1] for row in rows])
            table += "-" * 70 + "\n"
            table += f"{'TOTAL':2} | ₹{total:7.2f} │ {' ':10} │ {' ':10} │ {' ':15}\n"
            
                
            table += "```"
            
            await message.channel.send(table)
intents = discord.Intents.default()
intents.message_content = True

client = Client(intents=intents)
token = os.getenv('DISCORD_TOKEN')
client.run(token)

