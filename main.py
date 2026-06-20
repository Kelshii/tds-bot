import asyncio
import json
import os
from pathlib import Path

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    p = Path(".token")
    if p.exists():
        BOT_TOKEN = p.read_text().strip()
BOT_PROXY = os.getenv("BOT_PROXY")

session = AiohttpSession(proxy=BOT_PROXY) if BOT_PROXY else None
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

DATA_DIR = Path("data")
PROMOCODES_FILE = DATA_DIR / "promocodes.json"
PIN_CODES_FILE = DATA_DIR / "pin_codes.json"


def load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path: Path, data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


promocodes = load_json(PROMOCODES_FILE)
pin_codes = load_json(PIN_CODES_FILE)

ADMIN_PIN = "TDSS26"


def main_menu():
    kb = [
        [KeyboardButton(text="Промокоды🎁")],
        [KeyboardButton(text="Купить пин-код для админа.")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в <b>TDS Bot</b>!\n\n"
        "🎁 <b>Промокоды</b> — актуальные промокоды для игры\n"
        "🔑 <b>Пин-код для админа</b> — купить доступ за 2 ⭐",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "Промокоды🎁")
async def show_promocodes(message: Message):
    if not promocodes:
        await message.answer(
            "😔 Пока нет активных промокодов.", reply_markup=main_menu()
        )
        return

    text = "🎁 <b>Актуальные промокоды:</b>\n\n"
    for i, code in enumerate(promocodes[:10], 1):
        text += f"{i}. <code>{code}</code>\n"
    await message.answer(text, reply_markup=main_menu())


@dp.message(F.text == "Купить пин-код для админа.")
async def buy_pin(message: Message):
    user_id = str(message.from_user.id)
    existing = next((p for p in pin_codes if p["user_id"] == user_id), None)
    if existing:
        await message.answer(
            f"🔑 У вас уже есть пин-код: <code>{existing['pin_code']}</code>\n\n"
            "Используйте его для входа в админ-панель.",
            reply_markup=main_menu(),
        )
        return

    prices = [LabeledPrice(label="Пин-код администратора", amount=2)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Пин-код администратора",
        description="Доступ к админ-панели игры TDS",
        payload="admin_pin",
        provider_token="",
        currency="XTR",
        prices=prices,
    )


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    user_id = str(message.from_user.id)
    pin_codes.append({"user_id": user_id, "pin_code": ADMIN_PIN})
    save_json(PIN_CODES_FILE, pin_codes)

    await message.answer(
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"🔑 Ваш пин-код: <code>{ADMIN_PIN}</code>\n\n"
        "Сохраните его, он понадобится для входа в админ-панель.",
        reply_markup=main_menu(),
    )


async def run_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await asyncio.Event().wait()


async def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не задан! Создай файл .env и укажи токен.")
        return
    mode = os.getenv("BOT_MODE", "polling")
    if mode == "webhook":
        port = int(os.getenv("PORT", 8080))
        domain = os.getenv("BOT_DOMAIN", "")
        if domain:
            await bot.set_webhook(url=f"{domain}/webhook")
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="OK"))
        app.router.add_get("/health", lambda r: web.Response(text="OK"))
        app.router.add_post("/webhook", handle_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"✅ Webhook mode on port {port}")
        await asyncio.Event().wait()
    else:
        print("✅ Бот запущен (polling)!")
        await asyncio.gather(dp.start_polling(bot), run_web())

async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response(text="OK")


if __name__ == "__main__":
    asyncio.run(main())
