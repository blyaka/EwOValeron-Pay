# bot/main.py
import os, django, logging, asyncio, re
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from decimal import Decimal
from asgiref.sync import sync_to_async
from django.db import transaction
from accounts.models import TelegramLinkToken, TelegramAccount

import aiohttp  # <— нужен в requirements

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAIN_APP_URL = os.getenv("MAIN_APP_URL", "http://web:8000")
BOT_INTERNAL_TOKEN = os.getenv("BOT_INTERNAL_TOKEN", "")  # <— секрет для Django эндпоинта

MIN_BY_METHOD = {36: Decimal("50.00"), 35: Decimal("50.00"), 44: Decimal("10.00")}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@sync_to_async
def _link_user_by_token(tok: str, tg_id: int, username: str, first_name: str):
    try:
        t = TelegramLinkToken.objects.select_related('user').get(token=tok)
    except TelegramLinkToken.DoesNotExist:
        return ("not_found", None)

    if not t.is_active():
        return ("inactive", None)

    with transaction.atomic():
        t.mark_used()
        TelegramAccount.objects.filter(telegram_id=tg_id).delete()
        TelegramAccount.objects.filter(user=t.user).delete()
        TelegramAccount.objects.create(
            user=t.user,
            telegram_id=tg_id,
            username=username or '',
            first_name=first_name or ''
        )
        uname = t.user.username
    return ("ok", uname)

class CreateLinkSG(StatesGroup):
    amount = State()
    email = State()

def _valid_amount(text: str) -> Decimal | None:
    try:
        v = Decimal(text.replace(",", "."))
        if v <= 0:
            return None
        return v.quantize(Decimal("0.01"))
    except Exception:
        return None

def _valid_email(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", s))

@dp.message(Command("newlink"))
async def cmd_newlink(m: Message, state: FSMContext):
    await state.set_state(CreateLinkSG.amount)
    await m.answer("Введи сумму заказа (₽). Минимум для СБП — 10.00")

@dp.message(CreateLinkSG.amount)
async def ask_email(m: Message, state: FSMContext):
    amt = _valid_amount(m.text or "")
    if not amt or amt < MIN_BY_METHOD[44]:
        await m.answer("Некорректная сумма. Минимум для СБП — 10.00 ₽. Введи заново.")
        return
    await state.update_data(amount=str(amt))
    await state.set_state(CreateLinkSG.email)
    await m.answer("Введи почту клиента:")

@dp.message(CreateLinkSG.email)
async def create_link(m: Message, state: FSMContext):
    email = (m.text or "").strip()
    if not _valid_email(email):
        await m.answer("Почта некорректна. Введи email ещё раз.")
        return

    data = await state.get_data()
    amount = data["amount"]

    payload = {
        "amount": float(amount),
        "email": email,  # TTL=24ч и method=СБП задаются на стороне Django
    }

    headers = {
        "X-Bot-Token": BOT_INTERNAL_TOKEN,       # <— правильный секрет
        "X-Telegram-Id": str(m.from_user.id),
        "Content-Type": "application/json",
    }

    url = f"{MAIN_APP_URL}/payments/api/bot/create_link/"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            async with sess.post(url, json=payload, headers=headers) as r:
                if r.status != 200:
                    text = await r.text()
                    await m.answer(f"Ошибка {r.status}: {text[:300]}")
                    await state.clear()
                    return
                j = await r.json()
    except Exception as e:
        await m.answer(f"Ошибка соединения: {e}")
        await state.clear()
        return

    if not j.get("ok"):
        await m.answer(f"Не удалось создать ссылку: {j.get('errors') or j.get('error')}")
    else:
        pub = j["public_url"]
        oid = j["order_id"]
        await m.answer(f"Готово!\nЗаказ <b>{oid}</b>\nСсылка для клиента:\n{pub}")

    await state.clear()

@dp.message(CommandStart())
async def start(m: Message):
    payload = m.text.split(maxsplit=1)
    tok = payload[1].strip() if len(payload) > 1 else ''
    if not tok:
        await m.answer("Привет! Зайди в личный кабинет и нажми «Подключить Telegram».")
        return

    status, _ = await _link_user_by_token(
        tok, m.from_user.id, m.from_user.username or '', m.from_user.first_name or ''
    )

    if status == "ok":
        await m.answer("Готово! Телеграм привязан к твоему аккаунту.")
    elif status == "inactive":
        await m.answer("Токен истёк или уже использован. Сгенерируй новый в личном кабинете.")
    else:
        await m.answer("Токен не найден.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
