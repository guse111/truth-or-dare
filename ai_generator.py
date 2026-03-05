from openai import OpenAI
import json
import re

client = OpenAI(
    api_key="sk-rslLztN0IfYSOZUlLcDUxSLf8M8yGMHz",
    base_url="https://api.proxyapi.ru/openai/v1"
)

# Системные промпты с учётом новых требований
SYSTEM_PROMPTS = {
    'dare': '''Ты — ведущий игры «Правда или Действие». Генерируй ЗАДАНИЯ (действия).

ПРАВИЛА:
- Для сложности "easy": задания ТОЛЬКО внутри компании игроков. Никаких звонков незнакомцам, публичных действий, взаимодействия с посторонними.
- Для сложности "medium": можно чуть больше креатива, но всё ещё безопасно.
- Никакого насилия, незаконных действий, оскорблений, унизительных заданий.
- Задания должны быть выполнимы здесь и сейчас, без специального реквизита.
- Избегай повторений: если видишь список использованных названий — предложи что-то новое.

ФОРМАТ ОТВЕТА (строго JSON):
{
    "title": "Короткое название, 2-3 слова",
    "context": "Одно предложение: где/как выполнять",
    "task": "Текст задания на русском, 1-2 предложения"
}

Примеры title: "Танец робота", "Комплимент кругу", "Гримаса дня"
Примеры context: "Выполняется сидя на месте", "Требует участия всех игроков", "Можно сделать стоя у стола"
''',
    
    'truth': '''Ты — ведущий игры «Правда или Действие». Генерируй ВОПРОСЫ («Правда»).

ПРАВИЛА:
- Вопросы должны быть искренними, но не травмирующими.
- Для "easy": лёгкие, необязывающие вопросы о предпочтениях, привычках.
- Для "medium": можно чуть более личные, с элементом рефлексии.
- Никаких вопросов про травмы, насилие, незаконное, финансовые детали.
- Избегай повторений: если видишь список использованных названий — предложи что-то новое.

ФОРМАТ ОТВЕТА (строго JSON):
{
    "title": "Короткое название, 2-3 слова",
    "context": "Одно предложение: о чём вопрос",
    "question": "Текст вопроса на русском, 1 предложение"
}

Примеры title: "Детская мечта", "Странный страх", "Любимый запах"
Примеры context: "Вопрос о детских воспоминаниях", "Касается личных предпочтений", "О текущем настроении"
'''
}

def generate_content(content_type: str, difficulty: str, context: str, 
                     used_titles: list = None, model: str = "gpt-4o-mini") -> dict:
    """
    Генерирует задание или вопрос через AI.
    
    Args:
        content_type: 'dare' или 'truth'
        difficulty: 'easy' или 'medium' или 'hardcore'
        context: описание обстоятельств от пользователя
        used_titles: список уже использованных названий (для избежания повторов)
        model: название модели
    
    Returns:
        dict с полями title, context, text или None при ошибке
    """
    if difficulty == 'hardcore':
        return None  # Hardcore обрабатывается через БД
    
    system_prompt = SYSTEM_PROMPTS.get(content_type, SYSTEM_PROMPTS['dare'])
    
    difficulty_ru = "простое и безопасное" if difficulty == 'easy' else "креативное, но безопасное"
    type_ru = "задание (действие)" if content_type == 'dare' else "вопрос"
    context_ru = context if context != 'general' else "обычная домашняя вечеринка"
    
    # Формируем блок с историей названий
    history_block = ""
    if used_titles and len(used_titles) > 0:
        # Берём последние 10 названий, чтобы не перегружать промпт
        recent_titles = used_titles[-10:]
        history_block = f"\n\nУЖЕ ИСПОЛЬЗОВАННЫЕ НАЗВАНИЯ (не повторяй их):\n" + \
                       "\n".join(f"- {t}" for t in recent_titles)
    
    user_prompt = f"""
Сгенерируй {difficulty_ru} {type_ru} для игры «Правда или Действие».

Контекст игры: {context_ru}

Важно:
- Ответ должен быть на русском языке
- Название: 2-3 слова, ёмкое и понятное
- Контекст: одно короткое предложение о том, где/как выполнять
- Текст: краткий, готовый к зачитыванию вслух{history_block}
"""
    
    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0.5,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=12
        )
        
        response_text = completion.choices[0].message.content.strip()
        result = parse_ai_response(response_text, content_type)
        
        if result and validate_response(result, content_type):
            return result
        
        print(f"⚠️ AI response invalid: {response_text[:100]}")
        return None
        
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return None

def parse_ai_response(text: str, content_type: str) -> dict:
    """Пытается распарсить JSON из ответа AI"""
    # Ищем JSON-объект в тексте
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        return None
    
    try:
        data = json.loads(json_match.group())
        
        # Определяем ключ для основного текста
        text_key = 'task' if content_type == 'dare' else 'question'
        
        if all(k in data for k in ['title', 'context', text_key]):
            return {
                'title': str(data['title']).strip()[:30],  # Ограничиваем длину
                'context': str(data['context']).strip()[:100],
                'text': str(data[text_key]).strip()
            }
    except json.JSONDecodeError:
        pass
    
    return None

def validate_response(data: dict, content_type: str) -> bool:
    """Проверяет, что ответ соответствует требованиям"""
    if not all(k in data for k in ['title', 'context', 'text']):
        return False
    if len(data['title']) < 2 or len(data['title']) > 30:
        return False
    if len(data['text']) < 5:
        return False
    # Для easy проверяем, нет ли упоминаний посторонних
    if content_type == 'dare':
        forbidden = ['незнакомец', 'прохожий', 'официант', 'продавец', 'позвони', 'напиши кому-то']
        if any(word in data['text'].lower() for word in forbidden):
            return False
    return True

def get_fallback_content(content_type: str, difficulty: str) -> dict:
    """Запасные варианты на случай сбоя AI"""
    fallbacks = {
        'dare': {
            'easy': [
                {"title": "Танец робота", "context": "Стоя на месте", "text": "Изобрази робота в течение 15 секунд"},
                {"title": "Комплимент кругу", "context": "Смотря на игроков", "text": "Скажи искренний комплимент каждому игроку"},
                {"title": "Гримаса дня", "context": "Перед всеми", "text": "Покажи свою самую смешную гримасу и держи 5 секунд"},
                {"title": "Детский стишок", "context": "С выражением", "text": "Расскажи детский стишок с театральной интонацией"},
                {"title": "Зеркало", "context": "Повторяя за игроком", "text": "Повторяй движения игрока справа как зеркало 10 секунд"}
            ],
            'medium': [
                {"title": "История за 30с", "context": "Перед группой", "text": "Расскажи смешную историю из жизни за 30 секунд"},
                {"title": "Эмоция в звуке", "context": "Без слов", "text": "Изобрази эмоцию только звуками, чтобы угадали"},
                {"title": "Поза статуи", "context": "Замирая на месте", "text": "Замри в необычной позе на 20 секунд, не двигайся"},
                {"title": "Шёпот тайны", "context": "На ухо соседу", "text": "Прошепчи игроку слева выдуманную тайну с серьёзным лицом"},
                {"title": "Реклама предмета", "context": "С энтузиазмом", "text": "Прорекламируй любой предмет в комнате как лучший товар"}
            ]
        },
        'truth': {
            'easy': [
                {"title": "Любимый звук", "context": "О предпочтениях", "text": "Какой звук тебя успокаивает больше всего?"},
                {"title": "Детская еда", "context": "О вкусах", "text": "Какое блюдо из детства ты любишь до сих пор?"},
                {"title": "Идеальный вечер", "context": "О мечтах", "text": "Опиши свой идеальный вечер в трёх словах"},
                {"title": "Смешной случай", "context": "О воспоминаниях", "text": "Что самое смешное случалось с тобой на этой неделе?"},
                {"title": "Суперсила", "context": "О желаниях", "text": "Какую бесполезную суперсилу ты бы хотел иметь?"}
            ],
            'medium': [
                {"title": "Неудобный момент", "context": "О честности", "text": "Какой самый неловкий момент ты помнишь за последний год?"},
                {"title": "Секретная привычка", "context": "О себе", "text": "Какая у тебя есть странная привычка, о которой мало кто знает?"},
                {"title": "Совет себе", "context": "О рефлексии", "text": "Какой совет ты бы дал себе год назад?"},
                {"title": "Вдохновение", "context": "О людях", "text": "Какое качество в других людях тебя восхищает больше всего?"},
                {"title": "Страх и шаг", "context": "О смелости", "text": "Чего ты боишься, но очень хочешь попробовать?"}
            ]
        }
    }
    
    import random
    options = fallbacks.get(content_type, {}).get(difficulty, fallbacks['dare']['easy'])
    return random.choice(options)
