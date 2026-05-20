import os
import json
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN', '8872327007:AAHaH8gonK4Kw12r7Ju1qVn6wVruQR1MSdw')
DATA_FILE = '/tmp/feedback_data.json'

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f'load error: {e}')
    return []

def get_stats_text(records, label='всё время'):
    total = len(records)
    if not total:
        return f'📭 За {label} отзывов нет.'
    avg = sum(r.get('score', 0) for r in records) / total
    pos = len([r for r in records if r.get('score', 0) >= 4])
    pos_pct = round(pos / total * 100)
    counts = {1:0, 2:0, 3:0, 4:0, 5:0}
    for r in records:
        s = r.get('score', 3)
        counts[s] = counts.get(s, 0) + 1
    def bar(n):
        return '▓' * min(n, 10) if n > 0 else '░'
    tag_count = {}
    for r in records:
        if r.get('tags'):
            for t in r['tags'].split(', '):
                if t.strip():
                    tag_count[t.strip()] = tag_count.get(t.strip(), 0) + 1
    top_tags = sorted(tag_count.items(), key=lambda x: -x[1])[:3]
    tags_text = '\n'.join(f'  • {k} ({v})' for k, v in top_tags)
    text = (
        f'📊 Статистика — {label}\n'
        f'━━━━━━━━━━━━━━━\n'
        f'📝 Отзывов: {total}\n'
        f'⭐ Средняя оценка: {avg:.1f}/5\n'
        f'😊 Позитивных (≥4): {pos_pct}%\n\n'
        f'Распределение:\n'
        f'🤩 5 — {counts[5]} {bar(counts[5])}\n'
        f'😊 4 — {counts[4]} {bar(counts[4])}\n'
        f'😐 3 — {counts[3]} {bar(counts[3])}\n'
        f'😕 2 — {counts[2]} {bar(counts[2])}\n'
        f'😞 1 — {counts[1]} {bar(counts[1])}'
    )
    if tags_text:
        text += f'\n\n🏷 Топ причины:\n{tags_text}'
    return text

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '👋 Привет! Я бот Airba Express Feedback.\n\n'
        '📊 /stats — вся статистика\n'
        '📅 /today — статистика за сегодня\n'
        '📅 /week — статистика за неделю\n'
        '📅 /month — статистика за месяц\n'
        '💬 /reviews — последние 10 отзывов'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_stats_text(load_data(), 'всё время'))

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now().strftime('%d.%m.%Y')
    filtered = [r for r in load_data() if r.get('date', '').startswith(today_str)]
    await update.message.reply_text(get_stats_text(filtered, 'сегодня'))

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    week_ago = datetime.now() - timedelta(days=7)
    filtered = []
    for r in load_data():
        try:
            iso = r.get('dateISO', '').replace('Z', '')
            if datetime.fromisoformat(iso) >= week_ago:
                filtered.append(r)
        except:
            pass
    await update.message.reply_text(get_stats_text(filtered, 'эту неделю'))

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month_ago = datetime.now() - timedelta(days=30)
    filtered = []
    for r in load_data():
        try:
            iso = r.get('dateISO', '').replace('Z', '')
            if datetime.fromisoformat(iso) >= month_ago:
                filtered.append(r)
        except:
            pass
    await update.message.reply_text(get_stats_text(filtered, 'этот месяц'))

async def reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text('📭 Отзывов пока нет.')
        return
    last10 = data[-10:][::-1]
    text = '💬 Последние отзывы:\n━━━━━━━━━━━━━━━\n'
    for i, r in enumerate(last10, 1):
        stars = '⭐' * r.get('score', 0)
        text += f"\n{i}. {r.get('emoji', '')} {stars}\n"
        if r.get('tags'):
            text += f"🏷 {r['tags']}\n"
        if r.get('comment'):
            text += f"💬 {r['comment']}\n"
        text += f"🕐 {r.get('date', '')}\n"
    await update.message.reply_text(text)

def main():
    logging.info('Starting bot...')
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', start))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('today', today))
    app.add_handler(CommandHandler('week', week))
    app.add_handler(CommandHandler('month', month))
    app.add_handler(CommandHandler('reviews', reviews))
    logging.info('Bot is running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
