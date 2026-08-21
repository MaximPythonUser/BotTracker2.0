import os
import asyncio
from datetime import datetime
from sys import prefix
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import aiosqlite
from aiogram.fsm.state import State, StatesGroup
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder


class EditState(StatesGroup):
    waiting_for_date = State()
    waiting_for_name = State()
    waiting_for_time = State()


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "training.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS one_off_trainings
                         (
                             id
                             INTEGER
                             PRIMARY
                             KEY
                             AUTOINCREMENT,
                             user_id
                             INTEGER
                             NOT
                             NULL,
                             date
                             TEXT
                             NOT
                             NULL,
                             training_name
                             TEXT
                             NOT
                             NULL,
                             start_time
                             TEXT
                             NOT
                             NULL
                         )
                         """)
        await db.commit()
    print("✅База данных готова")


async def add_one_off_training(user_id: int, date: str, name: str, time: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO one_off_trainings (user_id, date, training_name, start_time)
               VALUES (?, ?, ?, ?)""", (user_id, date, name, time)
        )

        await db.commit()  # commit - Сохранить изменения. Без этого запись не появится в базе.


@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    args = message.text.split(maxsplit=3)

    # split(maxsplit=3) разбивает строку на части. 3 - разделить на первые 3 раза.

    if len(args) < 4:
        await message.answer(
            "❌ Неверный формат.\n"
            "Используй: /add ГГГГ-ММ-ДД Название_тренировки Время\n"
            "Пример: /add 2026-08-25 Силовая 19:00"
        )
        return
    # Проверка формата даты и времени через datetime.strptime
    _, date, name, time = args

    try:
        datetime.strptime(date, "%Y-%m-%d")
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await message.answer("❌ Дата должна быть в формате ГГГГ-ММ-ДД, время — ЧЧ:ММ (24 часа).")
        return

    user_id = message.from_user.id
    await add_one_off_training(user_id, date, name, time)

    await message.answer(f"✅ Тренировка сохранена: {name} на {date} в {time}")


@dp.message(Command("my_trainings"))
async def cmd_my_trainings(message: types.Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row  # Теперь можно обращаться к колонкам по имени, а не по индексу
        cursor = await db.execute(
            "SELECT id, date, training_name, start_time FROM one_off_trainings WHERE user_id = ? ORDER BY id",
            (user_id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("У тебя пока нет запланированных тренировок")
        return

    text = "🗓 Твои тренировки:\n\n"
    for i, row in enumerate(rows, start=1):
        # enumerate(rows, start=1) - нумерация списка. берет каждую строку из базы данных и дает ей номер: 1, 2, 3
        # i - непосредственно номер.

        text += f"№{i}. 📅 {row['date']} | 🏋️ {row['training_name']} | ⏰ {row['start_time']}\n"
    await message.answer(text)


@dp.message(Command("edit"))
async def cmd_edit_start(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id,date, training_name, start_time FROM one_off_trainings WHERE user_id = ? ORDER BY id",
            (user_id,))
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("У тебя нет тренировок для редактирования.")
        return
    text = "🗓 Выбери тренировку для редактирования:\n\n"

    builder = InlineKeyboardBuilder()

    for i, row in enumerate(rows, 1) \
            :
        text += (
            f"🏋️ <b>{row['training_name']}</b>\n"
            f"📅 {row['date']} | ⏰ {row['start_time']}\n"
            f"--------------------------\n")
        prefix = f"edit_{row['id']}_"

        builder.button(text="📅 Изменить дату", callback_data=prefix + "date")
        builder.button(text="📝 Переименовать", callback_data=prefix + "name")
        builder.button(text="⏰ Сменить время", callback_data=prefix + "time")

        builder.adjust(3)

    text = "🗓 <b>Выбери тренировку для редактирования:</b>\n\n"
    builder = InlineKeyboardBuilder()

    for i, row in enumerate(rows, 1):
        text += (
            f"{i}. <b>{row['training_name']}</b>\n"
            f"   📅 {row['date']} • ⏰ {row['start_time']}\n\n"
        )

        prefix = f"edit_{row['id']}_"

        builder.button(text="📅 Дата", callback_data=prefix + "date")
        builder.button(text="📝 Название", callback_data=prefix + "name")
        builder.button(text="⏰ Время", callback_data=prefix + "time")

        builder.adjust(3)

        # ✅ ПРАВИЛЬНО: используем builder для отправки
    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_choice(callback: types.CallbackQuery, state: FSMContext):
    # Распарсим callback_data: edit_105_date -> target_id=105,action=date
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка обработки кнопки", show_alert=True)
        return
    # parts[0] = "edit", parts[1] = id, parts[2] = action
    target_id = int(parts[1])
    action = parts[2]
    print(f"🔧 Пользователь редактирует: id={target_id}, поле={action}")
    # Сохраняем в состояние ID тренировки и тип действия
    await state.update_data(target_id=target_id, field=action)

    prompts = {
        "date": "📅 Напиши новую дату в формате ГГГГ-ММ-ДД (например, 2026-09-01):",
        "name": "📝 Напиши новое название тренировки (можно с пробелами):",
        "time": "⏰ Напиши новое время в формате ЧЧ:ММ (24 часа, например, 21:30):"
    }

    # Меняем сообщение на запросе ввода

    if action == "date":
        await state.set_state(EditState.waiting_for_date)
    elif action == "name":
        await state.set_state(EditState.waiting_for_name)
    elif action == "time":
        await state.set_state(EditState.waiting_for_time)

    await callback.message.edit_text(prompts[action])
    await callback.answer()


@dp.message(EditState.waiting_for_date)
async def process_edit_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data["target_id"]
    new_date = message.text.strip()

    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ГГГГ-ММ-ДД, например: 2026-09-01")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE one_off_trainings SET date = ? WHERE id = ?", (new_date, target_id))
        await db.commit()

    await state.clear()
    await message.answer(f"✅ <b>Готово!</b>\n"
                         f"📅 Дата тренировки успешно изменена на <b>{new_date}</b>.\n"
                         f"Хочешь посмотреть обновленный список? Напиши /my_trainings",
                         parse_mode="HTML")


@dp.message(EditState.waiting_for_name)
async def process_edit_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data["target_id"]
    new_name = message.text.strip()

    if not new_name:
        await message.answer("❌ Название не может быть пустым.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE one_off_trainings SET training_name = ? WHERE id = ?", (new_name, target_id))
        await db.commit()

    await state.clear()
    await message.answer(f"✅ Название обновлено: {new_name}")


@dp.message(EditState.waiting_for_time)
async def process_edit_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data["target_id"]
    new_time = message.text.strip()

    try:
        datetime.strptime(new_time, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверное время. Используй формат ЧЧ:ММ, например: 21:30")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE one_off_trainings SET start_time = ? WHERE id = ?", (new_time, target_id))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Время обновлено на {new_time}!")


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}! Я твой трекер тренировок.\n\n"
        "Вот что я умею:\n\n"
        "📅 /my_trainings — посмотреть список своих тренировок.\n"
        "➕ /add ГГГГ-ММ-ДД Название Время — добавить новую тренировку.\n"
        "🗑️ /delete <номер> — удалить тренировку по номеру из списка.\n"
        "✏️ /edit — выбрать тренировку и отредактировать её через кнопки (дата, название, время).\n\n"  
        "💡 Подсказка: формат даты — 2026-08-25, время — 19:00 (24 часа)."
    )
    await message.answer(welcome_text)


@dp.message(Command("delete"))
async def cmd_delete(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Используй: /delete <номер>\n Номер смотри в списке /my_trainings")
        return

    try:
        idx = int(args[1])
    except ValueError:
        await message.answer("❌ Номер должен быть числом, например: /delete 1")
        return
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id FROM one_off_trainings WHERE user_id = ? ORDER BY id", (user_id,)
                                  )
        rows = await cursor.fetchall()

        if not rows:
            await message.answer("У тебя нет тренировок, нечего удалять.")
            return
        if idx < 1 or idx > len(rows):
            await message.answer(f"❌ Такого номера нет. Найдено тренировок: {len(rows)}")
            return
        target_id = rows[idx - 1]["id"]
        await db.execute("DELETE FROM one_off_trainings WHERE id = ?", (target_id,))
        await db.commit()
    await message.answer(f"✅ Тренировка №{idx} успешно удалена!")


async def main():
    print("Bot Started...")
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


