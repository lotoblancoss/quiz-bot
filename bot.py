import asyncio
import os
import json
import logging
import random
import time
import sqlite3
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    BotCommand,
)

from database import init_db, save_result, get_rank

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

QUIZ_TIME = 30
ANSWER_PAUSE = 5

QUIZZES_DIR = Path("quizzes")


class QuizStates(StatesGroup):
    choosing_quiz = State()
    playing = State()
    finished = State()


def validate_quiz_data(quiz_id: str, quiz_data: dict[str, Any]) -> bool:
    if not isinstance(quiz_data, dict):
        logger.warning("Квиз %s пропущен: корень JSON не объект", quiz_id)
        return False

    if "questions" not in quiz_data:
        logger.warning("Квиз %s пропущен: отсутствует questions", quiz_id)
        return False

    if not isinstance(quiz_data["questions"], list) or not quiz_data["questions"]:
        logger.warning("Квиз %s пропущен: questions пустой или не список", quiz_id)
        return False

    for i, q in enumerate(quiz_data["questions"], start=1):
        if not isinstance(q, dict):
            logger.warning("Квиз %s, вопрос %s: не объект", quiz_id, i)
            return False

        for field in ["question", "options", "answer"]:
            if field not in q:
                logger.warning("Квиз %s, вопрос %s: нет поля %s", quiz_id, i, field)
                return False

        if not isinstance(q["options"], list) or len(q["options"]) < 2:
            logger.warning(
                "Квиз %s, вопрос %s: options пустой или слишком короткий",
                quiz_id,
                i,
            )
            return False

        if q["answer"] not in q["options"]:
            logger.warning(
                "Квиз %s, вопрос %s: answer отсутствует в options",
                quiz_id,
                i,
            )
            return False

    return True


def load_all_quizzes() -> dict[str, dict[str, Any]]:
    quizzes: dict[str, dict[str, Any]] = {}
    QUIZZES_DIR.mkdir(exist_ok=True)

    for quiz_file in QUIZZES_DIR.glob("*.json"):
        if quiz_file.name.startswith("_"):
            continue

        try:
            with open(quiz_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if validate_quiz_data(quiz_file.stem, data):
                quizzes[quiz_file.stem] = data
            else:
                logger.warning("Пропущен невалидный квиз: %s", quiz_file.name)

        except Exception as e:
            logger.exception("Ошибка загрузки %s: %s", quiz_file.name, e)

    return quizzes


quizzes = load_all_quizzes()


def build_quiz_menu() -> InlineKeyboardMarkup:
    keyboard = []

    for quiz_id, quiz_data in quizzes.items():
        keyboard.append([
            InlineKeyboardButton(
                text=quiz_data.get("name", quiz_id),
                callback_data=f"quiz:{quiz_id}",
            )
        ])

    if quizzes:
        keyboard.append([
            InlineKeyboardButton(
                text="🎲 Случайный квиз",
                callback_data="quiz:random",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_answers_keyboard(options: list[str], question_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=option, callback_data=f"answer:{question_index}:{i}")]
            for i, option in enumerate(options)
        ]
    )


def prepare_questions(quiz_data: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = []

    for q in quiz_data["questions"]:
        options = q["options"].copy()
        random.shuffle(options)

        prepared.append({
            "question": q["question"],
            "options": options,
            "correct_index": options.index(q["answer"]),
            "explanation": q.get("explanation", ""),
            "image": q.get("image"),
            "answer_image": q.get("answer_image"),
        })

    random.shuffle(prepared)
    return prepared


@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()

    if not quizzes:
        await message.answer("😔 Квизы пока не загружены.")
        return

    await message.answer("📚 Выберите квиз:", reply_markup=build_quiz_menu())


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📚 <b>Как пользоваться ботом</b>\n\n"
        "• Нажмите /start, чтобы открыть список квизов\n"
        "• Выберите тему и отвечайте на вопросы кнопками\n"
        "• На каждый вопрос даётся 30 секунд\n"
        "• После ответа показывается пояснение\n"
        "• В рейтинг идёт только первое прохождение",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("quiz:"))
async def choose_quiz(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]

    if action == "random":
        if not quizzes:
            await callback.answer("Нет доступных квизов", show_alert=True)
            return
        quiz_id = random.choice(list(quizzes.keys()))
    else:
        quiz_id = action

    if quiz_id not in quizzes:
        await callback.answer("Квиз не найден", show_alert=True)
        return

    quiz_data = quizzes[quiz_id]
    questions = prepare_questions(quiz_data)

    await state.set_state(QuizStates.playing)
    await state.update_data(
        quiz_id=quiz_id,
        questions=questions,
        current_question=0,
        correct_answers=0,
        answered_questions=0,
        total_questions=len(questions),
        start_time=time.time(),
    )

    description = quiz_data.get("description", "")
    text = (
        f"🐉 <b>{escape(quiz_data.get('name', quiz_id))}</b>\n\n"
        f"{escape(description)}\n\n"
        f"⏳ 30 секунд на вопрос\n\n"
        f"Готовы?"
    )

    await callback.message.answer(text, parse_mode="HTML")
    await send_next_question(callback.message, state)
    await callback.answer()


async def send_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()

    current = data["current_question"]
    questions = data["questions"]

    if current >= len(questions):
        await finish_quiz(message, state)
        return

    q = questions[current]
    await state.update_data(current_question_data=q)

    options = q.get("options", [])
    if not options:
        await message.answer("❌ Ошибка: у вопроса нет вариантов ответа.")
        await state.clear()
        return

    text = (
        f"❓ <b>Вопрос {current + 1}/{len(questions)}</b>\n"
        f"⏳ <b>30 секунд</b>\n\n"
        f"{escape(q['question'])}"
    )

    if q.get("image"):
        photo = FSInputFile(q["image"])
        msg = await message.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=build_answers_keyboard(options, current),
            parse_mode="HTML",
        )
    else:
        msg = await message.answer(
            text,
            reply_markup=build_answers_keyboard(options, current),
            parse_mode="HTML",
        )

    asyncio.create_task(question_timer(msg, state, current))


async def question_timer(message: types.Message, state: FSMContext, index: int):
    for t in range(QUIZ_TIME, 0, -1):
        await asyncio.sleep(1)

        data = await state.get_data()

        if data.get("current_question") != index:
            return

        try:
            if getattr(message, "photo", None):
                await message.edit_caption(
                    caption=(
                        f"❓ <b>Вопрос {index + 1}/{data['total_questions']}</b>\n"
                        f"⏳ Осталось: <b>{t} сек</b>\n\n"
                        f"{escape(data['current_question_data']['question'])}"
                    ),
                    parse_mode="HTML",
                    reply_markup=build_answers_keyboard(
                        data["current_question_data"]["options"],
                        index,
                    ),
                )
            else:
                await message.edit_text(
                    f"❓ <b>Вопрос {index + 1}/{data['total_questions']}</b>\n"
                    f"⏳ Осталось: <b>{t} сек</b>\n\n"
                    f"{escape(data['current_question_data']['question'])}",
                    parse_mode="HTML",
                    reply_markup=build_answers_keyboard(
                        data["current_question_data"]["options"],
                        index,
                    ),
                )
        except Exception:
            pass

    data = await state.get_data()

    if data.get("current_question") == index:
        q = data.get("current_question_data", {})
        explanation = q.get("explanation", "")

        text = "⏰ <b>Время вышло!</b>"
        if explanation:
            text += f"\n\n📝 <b>Пояснение:</b> {escape(explanation)}"

        await message.answer(text, parse_mode="HTML")

        await state.update_data(current_question=index + 1)
        await asyncio.sleep(ANSWER_PAUSE)
        await send_next_question(message, state)


@dp.callback_query(F.data.startswith("answer:"))
async def answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректный ответ", show_alert=True)
        return

    try:
        question_index = int(parts[1])
        selected = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный ответ", show_alert=True)
        return

    current_index = data.get("current_question")
    if question_index != current_index:
        await callback.answer("Этот вопрос уже завершён", show_alert=True)
        return

    q = data.get("current_question_data")
    if not q:
        await callback.answer("Вопрос не найден", show_alert=True)
        return

    options = q.get("options", [])
    if not (0 <= selected < len(options)):
        await callback.answer("Некорректный вариант", show_alert=True)
        return

    chosen = options[selected]
    correct = options[q["correct_index"]]
    explanation = q.get("explanation", "")

    await state.update_data(
        answered_questions=data["answered_questions"] + 1
    )

    if chosen == correct:
        await state.update_data(correct_answers=data["correct_answers"] + 1)
        text = "✅ <b>Правильно!</b>"
    else:
        text = f"❌ <b>Неправильно!</b>\nПравильный ответ: <b>{escape(correct)}</b>"

    if explanation:
        text += f"\n\n📝 <b>Пояснение:</b> {escape(explanation)}"

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(text, parse_mode="HTML")

    if q.get("answer_image"):
        photo = FSInputFile(q["answer_image"])
        await callback.message.answer_photo(
            photo=photo,
            caption=f"Правильный ответ: <b>{escape(correct)}</b>",
            parse_mode="HTML",
        )

    await state.update_data(current_question=current_index + 1)

    await callback.answer()
    await asyncio.sleep(ANSWER_PAUSE)
    await send_next_question(callback.message, state)


async def finish_quiz(message: types.Message, state: FSMContext):
    data = await state.get_data()

    correct = data["correct_answers"]
    total = data["total_questions"]
    answered = data["answered_questions"]

    skipped = total - answered
    wrong = answered - correct

    time_taken = time.time() - data["start_time"]

    user = message.from_user

    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT score, time_taken FROM results
        WHERE user_id = ? AND quiz_id = ?
    """, (user.id, data["quiz_id"]))

    existing_result = cur.fetchone()

    if existing_result is None:
        save_result(
            user_id=user.id,
            name=user.full_name,
            quiz_id=data["quiz_id"],
            score=correct,
            total=total,
            time_taken=time_taken,
        )
        rating_score = correct
        rating_time = time_taken
        record_text = "🏆 <b>Результат добавлен в рейтинг!</b>"
    else:
        rating_score, rating_time = existing_result
        record_text = "ℹ️ <b>В рейтинг засчитывается только первое прохождение</b>"

    rank = get_rank(data["quiz_id"], rating_score, rating_time)

    cur.execute(
        "SELECT COUNT(*) FROM results WHERE quiz_id = ?",
        (data["quiz_id"],),
    )
    total_players = cur.fetchone()[0]

    conn.close()

    better_percent = int((1 - (rank / total_players)) * 100) if total_players else 0

    text = (
        "🐉 <b>ИСПЫТАНИЕ ЗАВЕРШЕНО</b>\n\n"
        f"⚔ Верно: <b>{correct}</b>\n"
        f"💀 Ошибки: <b>{wrong}</b>\n"
        f"🌫 Пропущено: <b>{skipped}</b>\n\n"
        f"⏱ Время: <b>{int(time_taken)} сек</b>\n\n"
        f"🏆 Место в рейтинге: <b>{rank}</b> из <b>{total_players}</b>\n"
        f"🔥 Лучше чем <b>{better_percent}%</b> игроков\n\n"
    )

    if better_percent >= 90:
        text += "👑 Легенда Вестероса!\n\n"
    elif better_percent >= 70:
        text += "⚔️ Отличный результат!\n\n"
    elif better_percent >= 50:
        text += "🛡 Неплохо, но можно лучше\n\n"
    else:
        text += "🐺 Зима близко… попробуйте снова\n\n"

    text += record_text

    await message.answer(text, parse_mode="HTML")
    await state.clear()


async def set_main_menu():
    commands = [
        BotCommand(command="start", description="Открыть список квизов"),
        BotCommand(command="help", description="Как пользоваться ботом"),
    ]
    await bot.set_my_commands(commands)


async def main():
    init_db()
    await set_main_menu()
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
