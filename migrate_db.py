# ✅ Импортируем функцию подключения напрямую
from db import Database, get_db_connection

print("🔄 Миграция базы данных...")

with get_db_connection() as conn:
    cursor = conn.cursor()
    
    # Добавляем новые поля если их нет
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN current_task_text TEXT")
        print("✓ Добавлено: current_task_text")
    except Exception as e:
        print(f"⚠️ current_task_text уже существует: {e}")
    
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN current_task_title TEXT")
        print("✓ Добавлено: current_task_title")
    except Exception as e:
        print(f"⚠️ current_task_title уже существует: {e}")
    
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN current_task_context TEXT")
        print("✓ Добавлено: current_task_context")
    except Exception as e:
        print(f"⚠️ current_task_context уже существует: {e}")
    
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN current_task_type TEXT")
        print("✓ Добавлено: current_task_type")
    except Exception as e:
        print(f"⚠️ current_task_type уже существует: {e}")
    
    conn.commit()

print("✅ Миграция завершена!")
