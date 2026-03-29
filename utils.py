import json
from pathlib import Path


def create_quiz_template():
    return {
        "name": "Название квиза",
        "description": "Короткое описание квиза",
        "questions": [
            {
                "question": "Первый вопрос?",

                # Картинка вопроса (необязательно)
                "image": "images/question.jpg",

                "options": [
                    "Вариант 1",
                    "Вариант 2",
                    "Вариант 3",
                    "Вариант 4"
                ],

                "answer": "Вариант 1",

                # Картинка ответа (оригинал)
                "answer_image": "images/answer.jpg",

                "explanation": "Пояснение к ответу"
            }
        ]
    }


def save_quiz_template():
    quizzes_dir = Path("quizzes")
    quizzes_dir.mkdir(exist_ok=True)

    template_file = quizzes_dir / "_template.json"

    # ⚠️ не перезаписывать существующий шаблон
    if template_file.exists():
        print(f"⚠️ Шаблон уже существует: {template_file}")
        return

    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(create_quiz_template(), f, ensure_ascii=False, indent=2)

    print(f"✅ Шаблон создан: {template_file}")


if __name__ == "__main__":
    save_quiz_template()