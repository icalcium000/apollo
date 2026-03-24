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
TG_TOKEN = os.getenv("TG_TOKEN")
GIGA_CREDENTIALS = os.getenv("GIGA_CREDENTIALS")
ALLOWED_CHAT_ID_STR = os.getenv("ALLOWED_CHAT_ID")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!Аполлон подскажи")
SYSTEM_INSTRUCTION = os.getenv("SYSTEM_INSTRUCTION", "\n\n(Инструкция: ответь коротко и лаконично. В стиле божества Аполлона, аля slay дивы)")

# Валидация критических данных
if not TG_TOKEN:
    logger.critical("Переменная TG_TOKEN не задана!")
    sys.exit(1)
if not GIGA_CREDENTIALS:
    logger.critical("Переменная GIGA_CREDENTIALS не задана!")
    sys.exit(1)
if not ALLOWED_CHAT_ID_STR:
    logger.critical("Переменная ALLOWED_CHAT_ID не задана!")
    sys.exit(1)

try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID_STR)
except ValueError:
    logger.critical(f"Ошибка: ALLOWED_CHAT_ID должен быть числом, получено: {ALLOWED_CHAT_ID_STR}")
    sys.exit(1)

# --- РАБОТА С ПУТЯМИ ---
# Если работаем в Docker (обычно Linux), используем /app/data, иначе локальную папку data
if os.name == 'posix':  # Linux/Mac
    DATA_DIR = Path("/app/data")
else:  # Windows и прочие
    DATA_DIR = Path(__file__).parent / "data"

# Создаем папку, если её нет
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot_database.db"
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
        # Показываем статус "печатает"
        await bot.send_chat_action(message.chat.id, "typing")
        
        full_prompt = f"{user_prompt}{SYSTEM_INSTRUCTION}"
        
        # Контекстный менеджер для GigaChat
        # verify_ssl_certs=False часто нужен для работы GigaChat из РФ без доп. настроек
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
        logger.warning(f"Попытка вызова из чужого чата! ID: {message.chat.id}, User: @{message.from_user.username}")

# --- ФОНОВЫЕ ЗАДАЧИ ---
async def background_monitor():
    """Пример фоновой задачи."""
    while True:
        # Здесь может быть проверка БД или рассылка
        await asyncio.sleep(3600) # Раз в час

# --- ЗАПУСК ---
async def main():
    logger.info(f"Аполлон запущен! Слушаю чат: {ALLOWED_CHAT_ID}")
    
    # Запуск фоновой задачи
    asyncio.create_task(background_monitor())

    try:
        # Очищаем очередь обновлений, которые пришли пока бот был оффлайн
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
    finally:
        # Graceful Shutdown
        logger.info("Завершение работы... Закрываю сессии.")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")