import sqlite3
from pathlib import Path

db_path = Path(".localforge/localforge.db")
if db_path.is_file():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET status = 'READY'")
    cur.execute("UPDATE runs SET status = 'FAILED'")
    cur.execute("DELETE FROM task_runs")
    cur.execute("DELETE FROM worktree_attempt_manifests")
    try:
        cur.execute("UPDATE runner_pool_states SET active_tasks_count = 0")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print("Database tasks, runs, task_runs, worktree manifests, and runner pool states reset cleanly.")
