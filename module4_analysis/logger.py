"""
module4_analysis/logger.py - 用户行为日志记录工具
提供独立的日志分析和写入功能（不依赖Flask上下文）
"""
import os
import sys
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BASE_DIR, LOGS_DIR

DB_PATH = os.path.join(BASE_DIR, "anime_system.db")

# 文件日志（不依赖数据库）
file_logger = logging.getLogger("anime.behavior")
file_logger.setLevel(logging.INFO)

log_file = os.path.join(LOGS_DIR, "behavior.log")
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
handler = logging.FileHandler(log_file, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s\t%(levelname)s\t%(message)s"))
file_logger.addHandler(handler)


class BehaviorLogger:
    """
    行为日志记录器
    同时写入：数据库（structured）+ 文件（flat）
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _db_execute(self, sql: str, params=()):
        """执行数据库写入"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(sql, params)
            conn.commit()
            conn.close()
        except Exception as e:
            file_logger.error(f"数据库写入失败: {e} | SQL: {sql[:100]}")

    def log_upload(self, image_filename: str, client_ip: str = None):
        """记录图像上传行为"""
        detail = json.dumps({"filename": image_filename}, ensure_ascii=False)
        self._db_execute(
            """INSERT INTO user_action_logs 
               (action_type, detail, client_ip, created_at) 
               VALUES (?, ?, ?, ?)""",
            ("upload", detail, client_ip, datetime.utcnow().isoformat())
        )
        file_logger.info(f"UPLOAD\t{client_ip}\t{image_filename}")

    def log_recognition(
        self,
        record_id: int,
        character_key: str,
        confidence: float,
        client_ip: str = None
    ):
        """记录角色识别行为"""
        detail = json.dumps(
            {"record_id": record_id, "confidence": confidence},
            ensure_ascii=False
        )
        self._db_execute(
            """INSERT INTO user_action_logs 
               (action_type, record_id, character_key, detail, client_ip, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("recognize", record_id, character_key, detail, client_ip,
             datetime.utcnow().isoformat())
        )
        file_logger.info(f"RECOGNIZE\t{client_ip}\t{character_key}\t{confidence:.1f}%")

    def log_like(self, record_id: int, client_ip: str = None):
        """记录点赞行为"""
        self._db_execute(
            """INSERT INTO user_action_logs 
               (action_type, record_id, client_ip, created_at) 
               VALUES (?, ?, ?, ?)""",
            ("like", record_id, client_ip, datetime.utcnow().isoformat())
        )
        file_logger.info(f"LIKE\t{client_ip}\trecord#{record_id}")

    def log_correction(
        self,
        record_id: int,
        original_name: str,
        corrected_name: str,
        client_ip: str = None
    ):
        """记录纠错行为"""
        detail = json.dumps(
            {"original": original_name, "corrected": corrected_name},
            ensure_ascii=False
        )
        self._db_execute(
            """INSERT INTO user_action_logs 
               (action_type, record_id, detail, client_ip, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            ("correction", record_id, detail, client_ip, datetime.utcnow().isoformat())
        )
        file_logger.info(f"CORRECT\t{client_ip}\trecord#{record_id}\t{original_name}->{corrected_name}")

    def export_to_csv(self, output_path: str = None) -> str:
        """将行为日志导出为CSV"""
        import csv
        if output_path is None:
            output_path = os.path.join(
                LOGS_DIR,
                f"behavior_export_{datetime.now().strftime('%Y%m%d')}.csv"
            )
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, action_type, record_id, character_key, 
                          detail, client_ip, created_at 
                   FROM user_action_logs 
                   ORDER BY created_at DESC"""
            ).fetchall()
            conn.close()

            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'id', 'action_type', 'record_id', 'character_key',
                    'detail', 'client_ip', 'created_at'
                ])
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))

            print(f"行为日志已导出: {output_path} ({len(rows)} 条记录)")
            return output_path
        
        except Exception as e:
            print(f"导出失败: {e}")
            return ""


# 全局单例
_logger_instance = None

def get_logger() -> BehaviorLogger:
    """获取全局行为日志记录器（单例）"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = BehaviorLogger()
    return _logger_instance


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="行为日志工具")
    parser.add_argument("--export", "-e", action="store_true", help="导出日志CSV")
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()

    logger = get_logger()
    if args.export:
        logger.export_to_csv(args.output)
