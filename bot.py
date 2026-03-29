import asyncio
import json
import logging
import random
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8358223962:AAEKipanjjX_UfX7MaXMqJFDrSbLLoOWVEo"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class QuizStates(StatesGroup):
    choosing_quiz = State()
    playing = State()
    finished = State()


QUIZZES_DIR = Path("quizzes")


def validate_quiz_data(quiz_id: str, quiz_data: dict[str, Any]) -> bool:
    """Проверяет структуру квиза."""
    if not isinstance(quiz_data, dict):
        logger.warning("Квиз %s пропущен: корень JSON не объект", quiz_id)
        return False

    required_top_fields = ["name", "questions"]
    for field in required_top_fields:
        if field not in quiz_data:
            logger.warning("Квиз %s пропущен: нет поля '%s'", quiz_id, field)
            return False

    if not isinstance(quiz_data["questions"], list) or not quiz_data["questions"]:
        logger.warning("Квиз %s пропущен: questions пустой или не список", quiz_id)
        return False

    for i, question in enumerate(quiz_data["questions"], start=1):
        if not isinstance(question, dict):
            logger.warning("Квиз %s, вопрос %s пропущен: не объект", quiz_id, i)
            return False

        for field in ["question", "options", "answer"]:
            if field not in question:
                logger.warning("Квиз %s, вопрос %s пропущен: нет поля '%s'", quiz_id, i, field)
                return False

        if not isinstance(question["options"], list) or len(question["options"]) < 2:
            logger.warning("Квиз %s, вопрос %s: options должен содержать минимум 2 варианта", quiz_id, i)
            return False

        if question["answer"] not in question["options"]:
            logger.warning("Квиз %s, вопрос %s: answer должен быть одним из options", quiz_id, i)
            return False

    return True


def load_all_quizzes() -> dict[str, dict[str, Any]]:
    """Загружает все валидные квизы из папки quizzes."""
    quizzes: dict[str, dict[str, Any]] = {}
    QUIZZES_DIR.mkdir(exist_ok=True)

    for quiz_file in QUIZZES_DIR.glob("*.json"):
        if quiz_file.name.startswith("_"):
            continue

        try:
            with open(quiz_file, "r", encoding="utf-8") as f:
                quiz_data = json.load(f)

            quiz_id = quiz_file.stem

            if validate_quiz_data(quiz_id, quiz_data):
                quizzes[quiz_id] = quiz_data
                logger.info("Загружен квиз: %s", quiz_id)

        except json.JSONDecodeError as e:
            logger.error("Ошибка JSON в %s: %s", quiz_file.name, e)
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
                callback_data=f"quiz:{quiz_id}"
            )
        ])

    if quizzes:
        keyboard.append([
            InlineKeyboardButton(
                text="🎲 Случайный квиз",
                callback_data="quiz:random"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_start_quiz_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать квиз", callback_data="quiz:start")]
        ]
    )


def build_finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="quiz:restart")],
            [InlineKeyboardButton(text="📚 Другие квизы", callback_data="quiz:menu")],
        ]
    )


def build_answers_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    for idx, option in enumerate(options):
        keyboard.append([
            InlineKeyboardButton(
                text=option,
                callback_data=f"answer:{idx}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def prepare_questions(quiz_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Готовит вопросы к прохождению:
    - копирует список
    - перемешивает вопросы
    - перемешивает варианты
    - сохраняет correct_index
    """
    prepared = []

    for q in quiz_data["questions"]:
        options = q["options"].copy()
        random.shuffle(options)

        prepared.append({
            "question": q["question"],
            "options": options,
            "correct_index": options.index(q["answer"]),
            "explanation": q.get("explanation", "")
        })

    random.shuffle(prepared)
    return prepared


async def show_quiz_menu(target: types.Message | CallbackQuery, text: str | None = None):
    """Показывает меню квизов."""
    message_text = text or "📚 <b>Выберите тему квиза:</b>"

    if not quizzes:
        no_quizzes_text = (
            "😔 <b>Квизы пока не загружены.</b>\n"
            "Добавьте JSON-файлы в папку <code>quizzes/</code>."
        )
        if isinstance(target, CallbackQuery):
            await target.message.answer(no_quizzes_text, parse_mode="HTML")
        else:
            await target.answer(no_quizzes_text, parse_mode="HTML")
        return

    markup = build_quiz_menu()

    if isinstance(target, CallbackQuery):
        await target.message.answer(message_text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.answer(message_text, reply_markup=markup, parse_mode="HTML")


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    welcome_text = (
        "🎮 <b>Добро пожаловать в Квиз-бот!</b>\n\n"
        "Здесь можно проходить квизы по разным темам.\n"
        "Выберите один из доступных вариантов ниже."
    )
    await message.answer(welcome_text, parse_mode="HTML")
    await show_quiz_menu(message)


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await show_quiz_menu(message)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 <b>Как пользоваться ботом</b>\n\n"
        "• /start или /menu — показать список квизов\n"
        "• выбрать тему\n"
        "• нажимать на ответы кнопками\n"
        "• посмотреть результат в конце\n\n"
        "Чтобы добавить новый квиз, положите JSON-файл в папку <code>quizzes/</code>."
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.callback_query(F.data.startswith("quiz:"))
async def process_quiz_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]

    if action == "random":
        if not quizzes:
            await callback.answer("Нет доступных квизов", show_alert=True)
            return
        quiz_id = random.choice(list(quizzes.keys()))
        await start_selected_quiz(callback, state, quiz_id)
        return

    if action == "start":
        await state.set_state(QuizStates.playing)
        await send_next_question(callback.message, state)
        await callback.answer()
        return

    if action == "restart":
        data = await state.get_data()
        quiz_data = data.get("quiz_data")

        if not quiz_data:
            await callback.answer("Не удалось перезапустить квиз", show_alert=True)
            return

        prepared_questions = prepare_questions(quiz_data)
        await state.update_data(
            questions=prepared_questions,
            current_question=0,
            correct_answers=0,
            total_questions=len(prepared_questions),
            current_question_data=None
        )

        await callback.message.answer("🔄 <b>Начинаем заново!</b>", parse_mode="HTML")
        await state.set_state(QuizStates.playing)
        await send_next_question(callback.message, state)
        await callback.answer()
        return

    if action == "menu":
        await state.clear()
        await callback.message.answer("Возвращаемся в меню.")
        await show_quiz_menu(callback)
        await callback.answer()
        return

    # Выбран конкретный quiz_id
    quiz_id = action
    if quiz_id not in quizzes:
        await callback.answer("Квиз не найден", show_alert=True)
        return

    await start_selected_quiz(callback, state, quiz_id)


async def start_selected_quiz(callback: CallbackQuery, state: FSMContext, quiz_id: str):
    quiz_data = quizzes[quiz_id]
    prepared_questions = prepare_questions(quiz_data)

    await state.update_data(
        quiz_id=quiz_id,
        quiz_data=quiz_data,
        questions=prepared_questions,
        current_question=0,
        correct_answers=0,
        total_questions=len(prepared_questions),
        current_question_data=None
    )
    await state.set_state(QuizStates.choosing_quiz)

    title = escape(quiz_data.get("name", quiz_id))
    description = escape(quiz_data.get("description", ""))

    text = (
        f"📋 <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"Количество вопросов: <b>{len(prepared_questions)}</b>\n"
        f"Готовы начать?"
    )

    await callback.message.answer(
        text,
        reply_markup=build_start_quiz_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


async def send_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()

    current = data.get("current_question", 0)
    questions = data.get("questions", [])
    total = data.get("total_questions", 0)

    if current >= total:
        await finish_quiz(message, state)
        return

    question_data = questions[current]
    await state.update_data(current_question_data=question_data)

    question_text = escape(question_data["question"])
    options = question_data["options"]

    await message.answer(
        f"❓ <b>Вопрос {current + 1}/{total}</b>\n\n{question_text}",
        reply_markup=build_answers_keyboard(options),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("answer:"))
async def process_answer(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != QuizStates.playing.state:
        await callback.answer("Сейчас квиз не запущен", show_alert=True)
        return

    try:
        selected_index = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный ответ", show_alert=True)
        return

    data = await state.get_data()
    question_data = data.get("current_question_data")

    if not question_data:
        await callback.answer("Вопрос не найден", show_alert=True)
        return

    options = question_data["options"]
    correct_index = question_data["correct_index"]
    explanation = question_data.get("explanation", "")

    if not (0 <= selected_index < len(options)):
        await callback.answer("Некорректный вариант", show_alert=True)
        return

    is_correct = selected_index == correct_index
    correct_answer = options[correct_index]

    if is_correct:
        await state.update_data(correct_answers=data.get("correct_answers", 0) + 1)
        response_text = "✅ <b>Правильно!</b>"
    else:
        response_text = (
            "❌ <b>Неправильно!</b>\n"
            f"Правильный ответ: <b>{escape(correct_answer)}</b>"
        )

    if explanation:
        response_text += f"\n\n📝 <b>Пояснение:</b> {escape(explanation)}"

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(response_text, parse_mode="HTML")

    await state.update_data(current_question=data.get("current_question", 0) + 1)

    await callback.answer()
    await asyncio.sleep(1)
    await send_next_question(callback.message, state)


async def finish_quiz(message: types.Message, state: FSMContext):
    data = await state.get_data()

    correct = data.get("correct_answers", 0)
    total = data.get("total_questions", 0)
    percentage = (correct / total * 100) if total else 0

    if percentage == 100:
        result_label = "🏆 ГЕНИЙ!"
    elif percentage >= 80:
        result_label = "🌟 Отлично!"
    elif percentage >= 60:
        result_label = "👍 Хорошо"
    elif percentage >= 40:
        result_label = "📚 Можно лучше"
    else:
        result_label = "💪 Попробуйте ещё раз"

    result_text = (
        "🎯 <b>Квиз завершён!</b>\n\n"
        f"{result_label}\n\n"
        f"📊 <b>Результат:</b> {correct} из {total}\n"
        f"📈 <b>Точность:</b> {percentage:.1f}%"
    )

    await message.answer(
        result_text,
        reply_markup=build_finish_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(QuizStates.finished)


async def main():
    logger.info("Бот запущен")
    logger.info("Загружено квизов: %s", len(quizzes))
    for quiz_id, quiz_data in quizzes.items():
        logger.info("• %s (%s)", quiz_data.get("name", quiz_id), quiz_id)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())