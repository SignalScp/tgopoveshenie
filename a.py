import os
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response
import aiohttp_cors

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем конфигурацию из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.environ.get('PORT', 5000))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Файл для сохранения данных
DATA_FILE = "countdown_data.json"

# Состояния для FSM
class CountdownStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_description = State()

# Глобальное хранилище данных
countdown_data: Dict[int, Dict[str, Any]] = {}

def load_data():
    """Загружает данные из файла"""
    global countdown_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                countdown_data = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            countdown_data = {}
    else:
        countdown_data = {}

def save_data():
    """Сохраняет данные в файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(countdown_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "Привет! 👋\n\n"
        "Я бот для отсчета дней до важных событий.\n"
        "zov\n\n"
        "Доступные команды:\n"
        "/setdate - Установить дату события\n"
        "/status - Показать текущий отсчет\n"
        "/remove - Удалить текущее событие\n"
        "/help - Показать помощь"
        "by AppleElol",
        parse_mode='HTML'
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📅 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Используйте /setdate чтобы установить дату события\n"
        "2️⃣ Введите дату в формате ДД.ММ.ГГГГ (например: 31.12.2024)\n"
        "3️⃣ Укажите описание события\n"
        "4️⃣ Бот будет показывать отсчет по команде /status\n\n"
        "📌 <b>Команды:</b>\n"
        "/setdate - Установить новую дату\n"
        "/status - Показать текущий отсчет\n"
        "/remove - Удалить текущее событие\n",
        parse_mode='HTML'
    )

@dp.message(Command("setdate"))
async def cmd_setdate(message: Message, state: FSMContext):
    """Начинает процесс установки даты"""
    await message.answer(
        "📅 Введите дату события в формате <b>ДД.ММ.ГГГГ</b>\n"
        "Например: 14.88.1941",
        parse_mode='HTML'
    )
    await state.set_state(CountdownStates.waiting_for_date)

@dp.message(Command("remove"))
async def cmd_remove(message: Message):
    """Удаляет текущее событие"""
    chat_id = message.chat.id
    if chat_id in countdown_data:
        event_description = countdown_data[chat_id]['description']
        del countdown_data[chat_id]
        save_data()
        await message.answer(
            f"🗑 Событие <b>{event_description}</b> удалено",
            parse_mode='HTML'
        )
    else:
        await message.answer(
            "❌ Для этого чата не установлено событие.\n"
            "Используйте /setdate чтобы создать новое событие",
            parse_mode='HTML'
        )

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Показывает текущий статус отсчета"""
    chat_id = message.chat.id
    if chat_id not in countdown_data:
        await message.answer(
            "❌ Дата события не установлена. Используйте /setdate",
            parse_mode='HTML'
        )
        return

    data = countdown_data[chat_id]
    target_date = datetime.strptime(data['date'], '%Y-%m-%d')
    description = data['description']

    today = datetime.now().date()
    target = target_date.date()

    days_left = (target - today).days

    if days_left > 0:
        await message.answer(
            f"📅 <b>{description}</b>\n"
            f"🗓 Дата: {target.strftime('%d.%m.%Y')}\n"
            f"⏳ Осталось: <b>{days_left} дн.</b>\n\n",
            parse_mode='HTML'
        )
    elif days_left == 0:
        await message.answer(
            f"🎉 <b>{description}</b>\n"
            f"📅 Сегодня тот самый день! 🎊",
            parse_mode='HTML'
        )
    else:
        await message.answer(
            f"📅 <b>{description}</b>\n"
            f"🗓 Дата: {target.strftime('%d.%m.%Y')}\n"
            f"⚠️ Это событие было {abs(days_left)} дн. назад",
            parse_mode='HTML'
        )

@dp.message(CountdownStates.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    """Обрабатывает введенную дату"""
    try:
        date_str = message.text.strip()
        target_date = datetime.strptime(date_str, '%d.%m.%Y')

        await state.update_data(date=target_date.strftime('%Y-%m-%d'))
        await message.answer(
            f"✅ Дата установлена: <b>{target_date.strftime('%d.%m.%Y')}</b>\n\n"
            "📝 Теперь введите описание события:",
            parse_mode='HTML'
        )
        await state.set_state(CountdownStates.waiting_for_description)

    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Используйте формат <b>ДД.ММ.ГГГГ</b> (например: 31.12.2024)\n\n"
            "Попробуйте еще раз:",
            parse_mode='HTML'
        )

@dp.message(CountdownStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    """Обрабатывает описание события"""
    description = message.text.strip()
    if not description:
        await message.answer("❌ Описание не может быть пустым. Попробуйте еще раз:")
        return

    data = await state.get_data()
    date_str = data['date']

    chat_id = message.chat.id
    countdown_data[chat_id] = {
        'date': date_str,
        'description': description,
        'chat_id': chat_id
    }

    save_data()

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    days_left = (target_date.date() - datetime.now().date()).days

    await message.answer(
        f"✅ <b>Событие успешно установлено!</b>\n\n"
        f"📅 <b>{description}</b>\n"
        f"🗓 Дата: {target_date.strftime('%d.%m.%Y')}\n"
        f"⏳ Осталось: <b>{days_left} дн.</b>\n\n",
        parse_mode='HTML'
    )

    await state.clear()

@dp.message()
async def handle_other_messages(message: Message):
    """Обрабатывает все остальные сообщения"""
    await message.answer(
        "❓ Я не понял эту команду.\n"
        "Используйте /help для просмотра доступных команд"
    )

# Создание веб-приложения
async def create_app():
    """Создает aiohttp приложение"""
    app = web.Application()

    # Настраиваем CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })

    # Webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Health check endpoint для Render
    async def health_check(request: Request) -> Response:
        return web.Response(text="OK", status=200)

    # Корневая страница
    async def index(request: Request) -> Response:
        active_events = len(countdown_data)
        return web.Response(
            text=f"🤖 Telegram Countdown Bot is running!\n"
                 f"📊 Active events: {active_events}\n"
                 f"🌐 Webhook URL: {WEBHOOK_URL}\n",
            status=200,
            content_type='text/plain; charset=utf-8'
        )

    # Статус бота в JSON
    async def bot_status(request: Request) -> Response:
        me = await bot.get_me()
        return web.json_response({
            "bot_info": {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name
            },
            "active_events": len(countdown_data),
            "webhook_url": WEBHOOK_URL,
            "status": "running"
        })

    # Добавляем маршруты
    app.router.add_get('/', index)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', bot_status)

    # Добавляем CORS ко всем маршрутам
    for route in list(app.router.routes()):
        cors.add(route)

    return app

async def on_startup():
    """Выполняется при запуске"""
    load_data()

    # Устанавливаем webhook
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
        logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    else:
        logger.info(f"Webhook уже установлен: {WEBHOOK_URL}")

async def on_shutdown():
    """Выполняется при остановке"""
    await bot.session.close()

async def main():
    """Главная функция"""
    # Запуск
    await on_startup()

    # Создаем приложение
    app = await create_app()

    # Настраиваем cleanup
    app.on_cleanup.append(lambda app: on_shutdown())

    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    logger.info(f"Бот запущен на {WEBAPP_HOST}:{WEBAPP_PORT}")
    logger.info(f"Webhook: {WEBHOOK_URL}")

    # Держим сервер запущенным
    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
    finally:
        await runner.cleanup()
        await on_shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
