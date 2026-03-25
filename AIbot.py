import asyncio
import logging
import os
import sys
import subprocess
from pathlib import Path

# --- АВТОМАТИЧЕСКАЯ УСТАНОВКА ЗАВИСИМОСТЕЙ ---
def install_dependencies():
    """Проверяет наличие библиотек и устанавливает их при необходимости."""
    required = {"aiogram", "gigachat", "python-dotenv"}
    try:
        import aiogram
        import gigachat
        import dotenv
    except ImportError:
        logging.info("Установка недостающих библиотек...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *required])
            logging.info("Библиотеки успешно установлены.")
        except Exception as e:
            logging.critical(f"Не удалось установить зависимости: {e}")
            sys.exit(1)

# --- ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ApolloBot")

# Сначала ставим зависимости, потом импортируем остальное
install_dependencies()

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from gigachat import GigaChat
from dotenv import load_dotenv

# Загружаем переменные из .env файла, если он существует
load_dotenv()

# --- КОНФИГУРАЦИЯ ---
TG_TOKEN = os.getenv("TOKEN")
GIGA_CREDENTIALS = os.getenv("GIGA_CREDENTIALS")
ALLOWED_CHAT_ID_STR = os.getenv("ALLOWED_CHAT_ID")
SUPER_ADMIN_ID_STR = os.getenv("SUPER_ADMIN_ID") # Новый параметр для уведомлений
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!Аполлон подскажи")
SYSTEM_INSTRUCTION = os.getenv("SYSTEM_INSTRUCTION", "\n\n(Инструкция: ответь коротко и лаконично. В стиле божества Аполлона, аля slay дивы)")

# Валидация критических данных
if not TG_TOKEN or not GIGA_CREDENTIALS or not ALLOWED_CHAT_ID_STR:
    logger.critical("Критические переменные окружения не заданы!")
    sys.exit(1)

try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID_STR)
    # SUPER_ADMIN_ID опционален, но важен для уведомлений
    SUPER_ADMIN_ID = int(SUPER_ADMIN_ID_STR) if SUPER_ADMIN_ID_STR else None
except ValueError:
    logger.critical("Ошибка: ALLOWED_CHAT_ID или SUPER_ADMIN_ID должны быть числами!")
    sys.exit(1)

# --- РАБОТА С ПУТЯМИ ---
if os.name == 'posix':
    DATA_DIR = Path("/app/data")
else:
    DATA_DIR = Path(__file__).parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Директория данных: {DATA_DIR}")

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
bot = Bot(
    token=TG_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# --- ОБРАБОТЧИКИ ---

@dp.message(F.chat.id == ALLOWED_CHAT_ID, F.text.startswith(COMMAND_PREFIX))
async def handle_apollo(message: types.Message):
    """Обработка команд в разрешенном чате."""
    user_prompt = message.text[len(COMMAND_PREFIX):].strip()
    
    if not user_prompt:
        await message.reply("Я слушаю, золотце! О чем мне подсказать? ✨")
        return

    try:
        await bot.send_chat_action(message.chat.id, "typing")
        full_prompt = f"{user_prompt}{SYSTEM_INSTRUCTION}"
        
        with GigaChat(credentials=GIGA_CREDENTIALS, verify_ssl_certs=False) as giga:
            response = giga.chat(full_prompt)
            answer = response.choices[0].message.content
            await message.reply(answer)
            
    except Exception as e:
        logger.error(f"Ошибка GigaChat: {e}")
        await message.reply("⚠️ Ой, божественные силы временно покинули чат. Попробуй позже, дорогуша.")

@dp.message(F.text.startswith(COMMAND_PREFIX))
async def log_wrong_chat(message: types.Message):
    """Логирование попыток доступа из других чатов."""
    if message.chat.id != ALLOWED_CHAT_ID:
        logger.warning(f"Попытка вызова из чужого чата! ID: {message.chat.id}")

# --- ФОНОВЫЕ ЗАДАЧИ ---
async def hourly_status_report(bot_instance: Bot):
    """Каждый час отправляет отчет супер-админу."""
    if not SUPER_ADMIN_ID:
        logger.warning("SUPER_ADMIN_ID не задан. Фоновые отчеты отключены.")
        return

    logger.info(f"Запущена задача ежечасных отчетов для админа {SUPER_ADMIN_ID}")
    while True:
        try:
            # Сначала ждем час (3600 секунд)
            await asyncio.sleep(3600)
            await bot_instance.send_message(SUPER_ADMIN_ID, "Работаю")
            logger.info("Отправлен статус 'Работаю' супер-админу.")
        except Exception as e:
            logger.error(f"Ошибка при отправке статуса админу: {e}")
            # Если ошибка (например, бот заблокирован), подождем немного дольше перед повтором
            await asyncio.sleep(60)

# --- ЗАПУСК ---
async def main():
    logger.info(f"Аполлон запущен! Слушаю чат: {ALLOWED_CHAT_ID}")
    
    # Запуск фоновой задачи отчетов
    asyncio.create_task(hourly_status_report(bot))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
    finally:
        logger.info("Завершение работы... Закрываю сессии.")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")