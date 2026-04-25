import asyncio
import logging
from typing import Any

from backend.config import JOB_TIMEOUT_SECONDS, WORKER_POLL_INTERVAL
from backend.database import get_connection
from backend.state import JOB_QUEUES
from backend.worker.pipeline import log_job_message, mark_job_failed, run_pipeline

logger = logging.getLogger(__name__)

MODULE_DONE_MARKERS = {
    "MODULE_SCRAPER_DONE",
    "MODULE_DOM_MUTATOR_DONE",
    "MODULE_AI_REWRITER_DONE",
    "MODULE_MEDIA_UNIQUEIZER_DONE",
    "MODULE_PACKER_DONE",
}


def _claim_next_pending_job_sync() -> dict[str, Any] | None:
    conn = get_connection()
    try:
        # 1. Берем ВООБЩЕ ВСЕ задачи, которые есть в базе
        all_rows = conn.execute("SELECT * FROM jobs").fetchall()

        # 2. Ищем нужную задачу перебором в Python (так мы обойдем глюки SQL WHERE)
        target_row = None
        for row in all_rows:
            # Очищаем статус от пробелов и приводим к нижнему регистру
            status = str(row["status"]).strip().lower()
            if status == "pending":
                target_row = row
                break

        if target_row is None:
            return None

        job_id = target_row["id"]

        # 3. Обновляем статус, используя только ID (самый надежный способ)
        conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))

        # В режиме isolation_level=None (autocommit) изменения сохраняются сразу,
        # но для страховки вернем словарь
        return dict(target_row)
    except Exception as e:
        print(f"⚠️ Ошибка внутри _claim_next_pending_job_sync: {e}")
        return None
    finally:
        conn.close()


async def claim_next_pending_job() -> dict[str, Any] | None:
    return await asyncio.to_thread(_claim_next_pending_job_sync)


async def worker_loop() -> None:
    while True:
        try:
            job = await claim_next_pending_job()

            if job is None:
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue

            job_id = int(job["id"])
            target_url = str(job["target_url"])
            JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

            try:
                await asyncio.wait_for(
                    run_pipeline(job_id, target_url),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                error_message = f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s"
                await log_job_message(job_id, "error", error_message)
                await mark_job_failed(job_id, error_message)
            except asyncio.CancelledError:
             raise
        except Exception as e:
            # ЖЕСТКИЙ ВЫВОД ОШИБКИ В КОНСОЛЬ
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ВОРКЕРА: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(WORKER_POLL_INTERVAL)


async def poll_loop() -> None:
    await worker_loop()
if __name__ == "__main__":
    # Эта строка — тот самый «сигнал жизни», о котором мы говорили
    print("\n🚀 --- WORKER IS ALIVE AND POLLING ---")
    print("Ожидаю задачи со статусом 'pending' в базе данных...\n")

    try:
        asyncio.run(poll_loop())
    except KeyboardInterrupt:
        print("\n🛑 Воркер остановлен пользователем.")