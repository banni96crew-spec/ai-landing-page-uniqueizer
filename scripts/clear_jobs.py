import sys
import os

# Заставляем Python смотреть на папку выше (в корень проекта)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import get_connection

conn = get_connection()
try:
    # 1. Удаляем абсолютно все задачи
    conn.execute("DELETE FROM jobs")

    # 2. Очищаем логи, связанные с этими задачами (чтобы не было мусора)
    conn.execute("DELETE FROM logs")

    # 3. Сбрасываем автоинкремент (счетчик ID), чтобы всё началось с 1
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('jobs', 'logs')")

    conn.commit()
    print("🧹 МАГИЯ УБОРКИ: Все задачи и логи успешно удалены!")
    print("✨ База кристально чиста. Следующая задача будет иметь ID 1.")
except Exception as e:
    print(f"❌ Ошибка при очистке: {e}")
finally:
    conn.close()