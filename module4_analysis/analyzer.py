"""
module4_analysis/analyzer.py - 用户行为统计分析
功能：
    - 热门角色识别频率统计
    - 用户纠错分布分析
    - 识别准确率趋势
    - 活跃时段分析
    - 生成统计报表（JSON/CSV）
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BASE_DIR, LOGS_DIR

# 数据库路径
DB_PATH = os.path.join(BASE_DIR, "anime_system.db")


def get_db_connection():
    """获取数据库连接"""
    import sqlite3
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"数据库文件不存在: {DB_PATH}\n"
            "请先运行 Web 应用（module3_web/app.py）以创建数据库"
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class BehaviorAnalyzer:
    """用户行为统计分析器"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _query(self, sql: str, params=()) -> list:
        """执行SQL查询"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def _query_one(self, sql: str, params=()) -> dict:
        """执行SQL查询（返回单行）"""
        results = self._query(sql, params)
        return results[0] if results else {}

    # ===========================
    # 基础统计
    # ===========================
    def get_overview(self) -> dict:
        """获取系统概览数据"""
        overview = {}

        total = self._query_one("SELECT COUNT(*) as cnt FROM recognition_records")
        overview["total_recognitions"] = total.get("cnt", 0)

        total_likes = self._query_one(
            "SELECT SUM(likes) as total FROM recognition_records"
        )
        overview["total_likes"] = int(total_likes.get("total") or 0)

        total_corrections = self._query_one(
            "SELECT SUM(corrections) as total FROM recognition_records"
        )
        overview["total_corrections"] = int(total_corrections.get("total") or 0)

        # 平均置信度
        avg_conf = self._query_one(
            "SELECT AVG(top1_confidence) as avg FROM recognition_records WHERE top1_confidence IS NOT NULL"
        )
        overview["avg_confidence"] = round(avg_conf.get("avg") or 0, 2)

        # 今日识别数
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = self._query_one(
            f"SELECT COUNT(*) as cnt FROM recognition_records WHERE date(created_at) = ?",
            (today,)
        )
        overview["today_recognitions"] = today_count.get("cnt", 0)

        return overview

    # ===========================
    # 热门角色分析
    # ===========================
    def get_popular_characters(self, top_n: int = 20) -> list:
        """
        统计热门角色识别频率
        
        Returns:
            list: [{"name": ..., "anime": ..., "count": ..., "avg_confidence": ..., "likes": ...}]
        """
        results = self._query(
            """
            SELECT 
                top1_character_name as name,
                top1_anime as anime,
                top1_character_key as character_key,
                COUNT(*) as count,
                ROUND(AVG(top1_confidence), 2) as avg_confidence,
                SUM(likes) as total_likes
            FROM recognition_records
            WHERE top1_character_name IS NOT NULL
            GROUP BY top1_character_key
            ORDER BY count DESC
            LIMIT ?
            """,
            (top_n,)
        )
        return results

    # ===========================
    # 纠错分布分析
    # ===========================
    def get_correction_distribution(self) -> list:
        """
        分析纠错分布（哪些角色被纠错最多）
        
        Returns:
            list: [{"original_name": ..., "corrections": ..., "correction_rate": ...}]
        """
        results = self._query(
            """
            SELECT 
                top1_character_name as original_name,
                top1_anime as anime,
                COUNT(*) as total_count,
                SUM(corrections) as correction_count,
                ROUND(CAST(SUM(corrections) AS FLOAT) / COUNT(*) * 100, 2) as correction_rate,
                user_corrected_name as common_correction
            FROM recognition_records
            WHERE top1_character_name IS NOT NULL
            GROUP BY top1_character_key
            HAVING correction_count > 0
            ORDER BY correction_count DESC
            """
        )
        return results

    # ===========================
    # 时间趋势分析
    # ===========================
    def get_daily_trend(self, days: int = 30) -> list:
        """
        最近N天的每日识别趋势
        
        Returns:
            list: [{"date": "2024-01-01", "count": 42, "avg_confidence": 87.5}]
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        results = self._query(
            """
            SELECT 
                date(created_at) as date,
                COUNT(*) as count,
                ROUND(AVG(top1_confidence), 2) as avg_confidence,
                SUM(likes) as total_likes
            FROM recognition_records
            WHERE date(created_at) >= ?
            GROUP BY date(created_at)
            ORDER BY date
            """,
            (start_date,)
        )
        return results

    def get_hourly_distribution(self) -> list:
        """
        全天24小时的识别分布（活跃时段）
        
        Returns:
            list: [{"hour": 0, "count": 5}, {"hour": 1, "count": 2}, ...]
        """
        results = self._query(
            """
            SELECT 
                CAST(strftime('%H', created_at) AS INTEGER) as hour,
                COUNT(*) as count
            FROM recognition_records
            GROUP BY hour
            ORDER BY hour
            """
        )
        # 补全0-23小时
        hour_map = {r["hour"]: r["count"] for r in results}
        return [{"hour": h, "count": hour_map.get(h, 0)} for h in range(24)]

    # ===========================
    # 置信度分布
    # ===========================
    def get_confidence_distribution(self) -> dict:
        """
        识别置信度区间分布
        
        Returns:
            dict: {"90-100": 150, "80-90": 87, ...}
        """
        ranges = [
            ("90-100%", 90, 100),
            ("80-90%", 80, 90),
            ("70-80%", 70, 80),
            ("60-70%", 60, 70),
            ("50-60%", 50, 60),
            ("<50%", 0, 50),
        ]
        distribution = {}
        for label, low, high in ranges:
            count = self._query_one(
                """
                SELECT COUNT(*) as cnt FROM recognition_records 
                WHERE top1_confidence >= ? AND top1_confidence < ?
                """,
                (low, high)
            )
            distribution[label] = count.get("cnt", 0)
        return distribution

    # ===========================
    # 综合报表
    # ===========================
    def generate_report(self) -> dict:
        """生成完整统计报表"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "overview": self.get_overview(),
            "popular_characters": self.get_popular_characters(20),
            "correction_distribution": self.get_correction_distribution(),
            "daily_trend": self.get_daily_trend(30),
            "hourly_distribution": self.get_hourly_distribution(),
            "confidence_distribution": self.get_confidence_distribution(),
        }
        return report

    def save_report(self, output_path: str = None) -> str:
        """保存报表到JSON文件"""
        if output_path is None:
            output_path = os.path.join(
                LOGS_DIR,
                f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
        
        report = self.generate_report()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"报表已保存: {output_path}")
        return output_path

    def print_summary(self):
        """打印摘要报表"""
        overview = self.get_overview()
        popular = self.get_popular_characters(10)
        corrections = self.get_correction_distribution()

        print("\n" + "="*65)
        print("系统统计报表摘要")
        print("="*65)
        print(f"总识别次数:    {overview['total_recognitions']:>10,}")
        print(f"累计点赞:      {overview['total_likes']:>10,}")
        print(f"累计纠错:      {overview['total_corrections']:>10,}")
        print(f"平均置信度:    {overview['avg_confidence']:>9.2f}%")
        print(f"今日识别:      {overview['today_recognitions']:>10,}")

        print("\n热门角色 Top-10")
        print("-"*65)
        print(f"{'角色名':<20} {'作品':<15} {'次数':>8} {'平均置信度':>10}")
        print("-"*65)
        for char in popular:
            print(
                f"{char.get('name',''):<20} {char.get('anime',''):<15} "
                f"{char.get('count',0):>8} {char.get('avg_confidence',0):>9.1f}%"
            )

        if corrections:
            print("\n纠错频率较高的角色")
            print("-"*65)
            for corr in corrections[:5]:
                print(
                    f"  {corr['original_name']}: "
                    f"纠错 {corr['correction_count']} 次 "
                    f"(纠错率 {corr['correction_rate']:.1f}%)"
                )
        
        print("="*65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="用户行为分析工具")
    parser.add_argument("--report", "-r", action="store_true", help="生成并保存完整报表")
    parser.add_argument("--output", "-o", type=str, default=None, help="报表输出路径")
    parser.add_argument("--summary", "-s", action="store_true", help="打印摘要")
    args = parser.parse_args()

    try:
        analyzer = BehaviorAnalyzer()
        
        if args.report:
            analyzer.save_report(args.output)
        
        analyzer.print_summary()
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
    except Exception as e:
        print(f"分析出错: {e}")
        raise
