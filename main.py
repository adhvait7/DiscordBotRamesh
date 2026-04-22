import discord
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        sslmode='require'
    )


def log_expense(amount, category, notes="", user_id=None):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO expenses (amount, category, notes, user_id) VALUES (%s, %s, %s, %s)",
                (amount, category, notes if notes else None, user_id)
            )


def get_monthly_total(user_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM expenses
                WHERE user_id = %s
                  AND DATE_TRUNC('month', date) = DATE_TRUNC('month', NOW())
                """,
                (user_id,)
            )
            return float(cursor.fetchone()[0])


def get_budget(user_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT budget FROM budgets WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            return float(row[0]) if row else None


def set_budget(user_id, amount):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO budgets (user_id, budget)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET budget = EXCLUDED.budget
                """,
                (user_id, amount)
            )


# ── Bot ───────────────────────────────────────────────────────────────────────

class Client(discord.Client):

    async def on_ready(self):
        print(f"Logged on as {self.user}!")

    async def on_message(self, message):
        if message.author == self.user:
            return

        uid = str(message.author.id)
        content = message.content

        # !hi
        if content.lower() == "hi":
            await message.channel.send(f'hola {message.author.mention} :)')

        # !clear — wipe all expenses for user
        elif content == '!clear':
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM expenses WHERE user_id = %s", (uid,))
            await message.channel.send("All your expenses have been cleared.")

        # !t <amount> <category> [notes] — log an expense
        elif content.startswith('!t '):
            parts = content[3:].split(' ', 1)
            if len(parts) < 2:
                await message.channel.send("Format: `!t 50 upi` or `!t 100 food groceries`")
                return

            try:
                amount = float(parts[0])
                rest = parts[1].split(' ', 1)
                category = rest[0]
                notes = rest[1] if len(rest) > 1 else ""

                log_expense(amount, category, notes, user_id=uid)

                # Budget check
                budget = get_budget(uid)
                monthly_total = get_monthly_total(uid)
                response = f'✓ Logged ₹{amount} ({category})'

                if budget:
                    remaining = budget - monthly_total
                    percent_used = (monthly_total / budget) * 100

                    if monthly_total > budget:
                        response += f'\n⚠️ **Budget exceeded!** You\'ve spent ₹{monthly_total:.2f} of your ₹{budget:.2f} budget (over by ₹{abs(remaining):.2f})'
                    elif percent_used >= 80:
                        response += f'\n🔶 **Warning:** {percent_used:.0f}% of monthly budget used (₹{remaining:.2f} left)'

                await message.channel.send(response)

            except ValueError:
                await message.channel.send("Amount must be a number!")

        # !view — show all expenses as a table
        elif content == '!view':
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, amount, category, notes, date FROM expenses WHERE user_id = %s ORDER BY date ASC",
                        (uid,)
                    )
                    rows = cursor.fetchall()

            table = "```\n"
            table += "S.No │ Amount  │ Category   │ Notes           │ Date\n"
            table += "─" * 70 + "\n"
            for i, row in enumerate(rows, start=1):
                _, amount, category, notes, date = row
                date_str = date.strftime('%Y-%m-%d %H:%M')
                notes_str = (notes[:15] + '...') if notes and len(notes) > 15 else (notes or '-')
                category_str = category[:10]
                table += f"{i:2} │ ₹{amount:7.2f} │ {category_str:10} │ {notes_str:15} │ {date_str}\n"

            total = sum(row[1] for row in rows)
            table += "─" * 70 + "\n"
            table += f"{'TOTAL':>4} │ ₹{total:7.2f}\n"
            table += "```"

            # Append budget status if set
            budget = get_budget(uid)
            if budget:
                monthly_total = get_monthly_total(uid)
                percent_used = (monthly_total / budget) * 100
                remaining = budget - monthly_total
                table += f"\n📊 Monthly budget: ₹{budget:.2f} | Spent this month: ₹{monthly_total:.2f} | Remaining: ₹{remaining:.2f} ({percent_used:.0f}% used)"

            await message.channel.send(table)

        # !summary — spend by category this month
        elif content == '!summary':
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT category, SUM(amount) as total
                        FROM expenses
                        WHERE user_id = %s
                          AND DATE_TRUNC('month', date) = DATE_TRUNC('month', NOW())
                        GROUP BY category
                        ORDER BY total DESC
                        """,
                        (uid,)
                    )
                    rows = cursor.fetchall()

            if not rows:
                await message.channel.send("No expenses this month yet.")
                return

            table = "```\n"
            table += "Category     │ Amount\n"
            table += "─" * 30 + "\n"
            for category, total in rows:
                table += f"{category:12} │ ₹{total:8.2f}\n"
            table += "─" * 30 + "\n"
            table += f"{'TOTAL':12} │ ₹{sum(r[1] for r in rows):8.2f}\n"
            table += "```"
            await message.channel.send(table)

        # !budget <amount> — set monthly budget
        elif content.startswith('!budget '):
            try:
                amount = float(content[8:])
                set_budget(uid, amount)
                await message.channel.send(f'✓ Monthly budget set to ₹{amount:.2f}')
            except ValueError:
                await message.channel.send("Format: `!budget 5000`")

        # !help — show all commands
        elif content == '!help':
            help_text = """```
!t <amount> <category> [notes]  → Log an expense
!view                            → View all expenses
!summary                         → Monthly spend by category
!budget <amount>                 → Set monthly budget
!clear                           → Clear all your expenses
!help                            → Show this message
```"""
            await message.channel.send(help_text)


# ── Run ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

client = Client(intents=intents)
client.run(os.getenv('DISCORD_TOKEN'))