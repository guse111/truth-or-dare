from db import Database

db = Database()

# Пример добавления карточек для Hardcore
cards = [
    # Действия
    ("Сними один предмет одежды", "dare", "hardcore", '["party", "home"]'),
    ("Поцелуй в щёку игрока слева", "dare", "hardcore", '["party", "couple"]'),
    ("Расскажи о своём самом неловком свидании", "dare", "hardcore", '["party"]'),
    
    # Вопросы
    ("Какой твой самый странный фетиш?", "truth", "hardcore", '["party", "couple"]'),
    ("Что тебя больше всего заводит в партнёре?", "truth", "hardcore", '["couple"]'),
    ("Опиши свой идеальный поцелуй", "truth", "hardcore", '["couple", "date"]'),
]

for text, ctype, diff, tags in cards:
    db.add_card(
        text=text,
        card_type=ctype,
        difficulty=diff,
        tags=tags,
        source='manual',
        is_verified=1  # Сразу верифицируем
    )
    print(f"✓ Добавлено: {text[:30]}...")

print("✅ Карточки добавлены!")
