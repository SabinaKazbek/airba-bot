import os
import json
import logging
from datetime import datetime, timedelta, time
import pytz
from aiohttp import web

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ChatMemberHandler, ContextTypes
)

TOKEN = os.environ.get('BOT_TOKEN')
DATA_FILE = os.environ.get('DATA_FILE', '/tmp/feedback_data.json')
CHATS_FILE = os.environ.get('CHATS_FILE', '/tmp/chats.json')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')

ALMATY_TZ = pytz.timezone('Asia/Almaty')
DAILY_REPORT_HOUR = int(os.environ.get('REPORT_HOUR', '20'))
DAILY_REPORT_MINUTE = int(os.environ.get('REPORT_MINUTE', '0'))


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f'load_data error: {e}')
    return []


def load_chats():
    try:
        if os.path.exists(CHATS_FILE):
            with open(CHATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f'load_chats error: {e}')
    return []


def save_chats(chats):
    try:
        with open(CHATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(chats, f)
    except Exception as e:
        logging.error(f'save_chats error: {e}')


def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f'save_data error: {e}')


# ── Formatting helpers ────────────────────────────────────────────────────────

def get_stats_text(records, label='всё время'):
    total = len(records)
    if not total:
        return f'📭 За {label} отзывов нет.'

    avg = sum(r.get('score', 0) for r in records) / total
    pos = len([r for r in records if r.get('score', 0) >= 4])
    neg = len([r for r in records if r.get('score', 0) <= 2])
    pos_pct = round(pos / total * 100)

    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in records:
        s = r.get('score', 3)
        if s in counts:
            counts[s] += 1

    def bar(n):
        return '▓' * min(n, 10) if n > 0 else '░'

    tag_count = {}
    for r in records:
        if r.get('tags'):
            for t in r['tags'].split(', '):
                t = t.strip()
                if t:
                    tag_count[t] = tag_count.get(t, 0) + 1

    top_tags = sorted(tag_count.items(), key=lambda x: -x[1])[:5]
    tags_text = '\n'.join(f'  • {k} ({v})' for k, v in top_tags)

    text = (
        f'📊 Статистика — {label}\n'
        f'━━━━━━━━━━━━━━━\n'
        f'📝 Отзывов: {total}\n'
        f'⭐ Средняя оценка: {avg:.1f}/5\n'
        f'😊 Позитивных (≥4⭐): {pos_pct}% ({pos})\n'
        f'😞 Негативных (≤2⭐): {neg}\n\n'
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


def format_new_review(r):
    score = r.get('score', 0)
    stars = '⭐' * score
    emoji = r.get('emoji', '')
    text = f'🔔 Новый отзыв! {emoji} {stars}\n'
    if r.get('tags'):
        text += f'🏷 {r["tags"]}\n'
    if r.get('comment'):
        text += f'💬 {r["comment"]}\n'
    text += f'🕐 {r.get("date", "")}'
    return text


# ── Command handlers ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '👋 Привет! Я бот Airba Express Feedback.\n\n'
        '📊 /stats — вся статистика\n'
        '📅 /today — статистика за сегодня\n'
        '📅 /week — статистика за неделю\n'
        '📅 /month — статистика за месяц\n'
        '💬 /reviews — последние 10 отзывов\n'
        '📋 /report — ежедневный отчет прямо сейчас\n'
        '✅ /register — подписаться на уведомления\n'
        '❌ /unregister — отписаться от уведомлений'
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_stats_text(load_data(), 'всё время'))


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now(ALMATY_TZ).strftime('%d.%m.%Y')
    filtered = [r for r in load_data() if r.get('date', '').startswith(today_str)]
    await update.message.reply_text(get_stats_text(filtered, f'сегодня ({today_str})'))


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    week_ago = datetime.now(ALMATY_TZ).replace(tzinfo=None) - timedelta(days=7)
    filtered = []
    for r in load_data():
        try:
            iso = r.get('dateISO', '').replace('Z', '')
            if datetime.fromisoformat(iso) >= week_ago:
                filtered.append(r)
        except Exception:
            pass
    await update.message.reply_text(get_stats_text(filtered, 'эту неделю'))


async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month_ago = datetime.now(ALMATY_TZ).replace(tzinfo=None) - timedelta(days=30)
    filtered = []
    for r in load_data():
        try:
            iso = r.get('dateISO', '').replace('Z', '')
            if datetime.fromisoformat(iso) >= month_ago:
                filtered.append(r)
        except Exception:
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
        text += f'\n{i}. {r.get("emoji", "")} {stars}\n'
        if r.get('tags'):
            text += f'🏷 {r["tags"]}\n'
        if r.get('comment'):
            text += f'💬 {r["comment"]}\n'
        text += f'🕐 {r.get("date", "")}\n'
    await update.message.reply_text(text)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = _build_daily_report()
    await update.message.reply_text(text)


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chats = load_chats()
    if chat_id not in chats:
        chats.append(chat_id)
        save_chats(chats)
        await update.message.reply_text(
            '✅ Чат подписан!\n'
            f'Буду присылать уведомления о новых отзывах и ежедневный отчет в {DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d} (Алматы).'
        )
    else:
        await update.message.reply_text('ℹ️ Этот чат уже подписан.')


async def unregister(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chats = load_chats()
    if chat_id in chats:
        chats.remove(chat_id)
        save_chats(chats)
        await update.message.reply_text('❌ Чат отписан от уведомлений.')
    else:
        await update.message.reply_text('ℹ️ Этот чат не был подписан.')


# ── Auto-register when bot is added to a group ────────────────────────────────

async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    new_status = result.new_chat_member.status
    chat_id = result.chat.id

    if new_status in ('member', 'administrator'):
        chats = load_chats()
        if chat_id not in chats:
            chats.append(chat_id)
            save_chats(chats)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                '👋 Привет! Я бот Airba Express Feedback.\n\n'
                'Буду присылать сюда уведомления о новых отзывах\n'
                f'и ежедневный отчет в {DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d} (Алматы).\n\n'
                '📊 /stats — вся статистика\n'
                '📅 /today — за сегодня\n'
                '📅 /week — за неделю\n'
                '📅 /month — за месяц\n'
                '💬 /reviews — последние 10 отзывов\n'
                '📋 /report — отчет прямо сейчас\n'
                '❌ /unregister — отписаться'
            )
        )
    elif new_status in ('left', 'kicked'):
        chats = load_chats()
        if chat_id in chats:
            chats.remove(chat_id)
            save_chats(chats)


# ── Scheduled jobs ────────────────────────────────────────────────────────────

def _build_daily_report():
    data = load_data()
    now = datetime.now(ALMATY_TZ)
    today_str = now.strftime('%d.%m.%Y')
    records = [r for r in data if r.get('date', '').startswith(today_str)]

    total = len(records)
    lines = [f'📅 Ежедневный отчет — {today_str}', '━━━━━━━━━━━━━━━']

    if not total:
        lines.append('📭 Сегодня отзывов нет.')
        return '\n'.join(lines)

    # 1. Количество отзывов
    lines.append(f'📝 Всего отзывов: {total}')

    # 2. Количество по каждой оценке
    counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for r in records:
        s = r.get('score', 3)
        if s in counts:
            counts[s] += 1

    lines.append('')
    lines.append('⭐ Оценки:')
    lines.append(f'  🤩 5 звезд — {counts[5]}')
    lines.append(f'  😊 4 звезды — {counts[4]}')
    lines.append(f'  😐 3 звезды — {counts[3]}')
    lines.append(f'  😕 2 звезды — {counts[2]}')
    lines.append(f'  😞 1 звезда  — {counts[1]}')

    avg = sum(r.get('score', 0) for r in records) / total
    lines.append(f'  Средняя: {avg:.1f}/5')

    # 3. Частые комментарии клиентов
    # Сначала теги (категории жалоб/похвал)
    tag_count: dict[str, int] = {}
    for r in records:
        if r.get('tags'):
            for t in r['tags'].split(', '):
                t = t.strip()
                if t:
                    tag_count[t] = tag_count.get(t, 0) + 1

    if tag_count:
        lines.append('')
        lines.append('🏷 Частые причины:')
        for tag, cnt in sorted(tag_count.items(), key=lambda x: -x[1])[:7]:
            lines.append(f'  • {tag} — {cnt}x')

    # Текстовые комментарии клиентов (уникальные, непустые)
    comments = [r['comment'].strip() for r in records if r.get('comment', '').strip()]
    if comments:
        lines.append('')
        lines.append(f'💬 Комментарии клиентов ({len(comments)}):')
        for c in comments[-8:]:
            short = c if len(c) <= 120 else c[:117] + '...'
            lines.append(f'  — {short}')

    return '\n'.join(lines)


async def send_daily_report(context):
    text = _build_daily_report()
    chats = load_chats()
    for chat_id in chats:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logging.error(f'Daily report failed for {chat_id}: {e}')


# ── Webhook HTTP server (receives reviews from the website) ───────────────────

async def handle_review_webhook(request: web.Request) -> web.Response:
    if WEBHOOK_SECRET:
        if request.headers.get('X-Webhook-Secret', '') != WEBHOOK_SECRET:
            return web.Response(status=403, text='forbidden')

    try:
        review = await request.json()
    except Exception:
        return web.Response(status=400, text='invalid json')

    # Save to data file (deduplicate by dateISO)
    data = load_data()
    known = {r.get('dateISO') for r in data}
    if review.get('dateISO') not in known:
        data.append(review)
        save_data(data)

        tg_app: Application = request.app['tg_app']
        text = format_new_review(review)
        for chat_id in load_chats():
            try:
                await tg_app.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logging.error(f'Forward failed for {chat_id}: {e}')

    return web.Response(text='ok')


async def start_web_server(tg_app: Application) -> None:
    http_app = web.Application()
    http_app['tg_app'] = tg_app
    http_app.router.add_post('/webhook/review', handle_review_webhook)
    http_app.router.add_get('/health', lambda _: web.Response(text='ok'))

    runner = web.AppRunner(http_app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    logging.info(f'Webhook server listening on port {port}')


async def on_startup(tg_app: Application) -> None:
    await start_web_server(tg_app)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        raise RuntimeError('BOT_TOKEN env var is not set')

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', start))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('today', today))
    app.add_handler(CommandHandler('week', week))
    app.add_handler(CommandHandler('month', month))
    app.add_handler(CommandHandler('reviews', reviews))
    app.add_handler(CommandHandler('report', report))
    app.add_handler(CommandHandler('register', register))
    app.add_handler(CommandHandler('unregister', unregister))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    jq = app.job_queue
    jq.run_daily(
        send_daily_report,
        time=time(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, tzinfo=ALMATY_TZ),
    )

    logging.info(f'Bot started. Daily report at {DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d} Almaty.')
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
