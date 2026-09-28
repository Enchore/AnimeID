"""
module4_analysis/visualizer.py - 数据可视化模块
实现：
    1. Matplotlib静态图表（PNG）
       - 热门角色识别频率柱状图
       - 识别准确率趋势折线图
       - 置信度分布饼图
       - 活跃时段热力图

    2. ECharts数据接口（为Web端动态图表提供JSON数据）
       - 角色识别热度图
       - 每日趋势图
       - 纠错率排行
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LOGS_DIR, BASE_DIR

# 尝试导入Matplotlib（可选依赖）
try:
    import matplotlib
    matplotlib.use('Agg')   # 无头模式（服务器环境）
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[警告] 未安装 matplotlib，跳过静态图表生成")


# ==============================
# Matplotlib 静态图表
# ==============================
class StaticChartGenerator:
    """Matplotlib静态图表生成器"""

    # 配色方案（参考系统主题）
    COLORS = {
        "primary": "#6C63FF",
        "accent": "#FF6584",
        "success": "#00D68F",
        "warning": "#FFB700",
        "bg": "#1A1A2E",
        "bg_card": "#16213E",
        "text": "#E8E8F0",
        "muted": "#8888AA",
    }

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or os.path.join(LOGS_DIR, "charts"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if HAS_MATPLOTLIB:
            self._setup_style()

    def _setup_style(self):
        """设置全局图表样式"""
        plt.rcParams.update({
            "figure.facecolor": self.COLORS["bg"],
            "axes.facecolor": self.COLORS["bg_card"],
            "axes.edgecolor": self.COLORS["muted"],
            "axes.labelcolor": self.COLORS["text"],
            "axes.titlecolor": self.COLORS["text"],
            "xtick.color": self.COLORS["muted"],
            "ytick.color": self.COLORS["muted"],
            "text.color": self.COLORS["text"],
            "grid.color": self.COLORS["muted"],
            "grid.alpha": 0.15,
            "grid.linestyle": "--",
            "figure.dpi": 150,
            "savefig.bbox": "tight",
            "savefig.facecolor": self.COLORS["bg"],
        })
        
        # 设置中文字体（Windows/Linux兼容）
        import platform
        if platform.system() == "Windows":
            plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        else:
            plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "Noto Sans CJK SC", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

    def plot_popular_characters(self, data: list, top_n: int = 15) -> str:
        """
        热门角色识别频率柱状图
        
        Args:
            data: analyzer.get_popular_characters() 的返回值
            top_n: 展示前N个角色
        
        Returns:
            str: 图表保存路径
        """
        if not HAS_MATPLOTLIB or not data:
            return ""

        data = data[:top_n]
        names = [d.get("name", "未知") for d in data]
        counts = [d.get("count", 0) for d in data]
        avg_confs = [d.get("avg_confidence", 0) for d in data]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
        fig.suptitle("热门动漫角色识别统计", fontsize=16, fontweight="bold",
                     color=self.COLORS["text"], y=0.98)

        # 左图：识别次数柱状图
        bars = ax1.barh(range(len(names)), counts[::-1],
                        color=self.COLORS["primary"], alpha=0.85, height=0.7)
        ax1.set_yticks(range(len(names)))
        ax1.set_yticklabels(names[::-1], fontsize=9)
        ax1.set_xlabel("识别次数")
        ax1.set_title("识别频率 Top-15")
        ax1.grid(axis="x")
        
        # 数值标注
        for i, (bar, count) in enumerate(zip(bars, counts[::-1])):
            ax1.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height()/2,
                     f"{count}", va="center", fontsize=8, color=self.COLORS["text"])

        # 右图：平均置信度柱状图
        colors = [self.COLORS["success"] if c >= 80 else
                  self.COLORS["warning"] if c >= 60 else
                  self.COLORS["accent"] for c in avg_confs]
        bars2 = ax2.barh(range(len(names)), avg_confs[::-1],
                         color=list(reversed(colors)), alpha=0.85, height=0.7)
        ax2.set_yticks(range(len(names)))
        ax2.set_yticklabels(names[::-1], fontsize=9)
        ax2.set_xlabel("平均置信度 (%)")
        ax2.set_title("识别置信度排行")
        ax2.set_xlim(0, 100)
        ax2.grid(axis="x")
        ax2.axvline(x=80, color=self.COLORS["success"], linestyle="--", alpha=0.5, label="80%基准线")
        ax2.legend(fontsize=8)

        plt.tight_layout()
        save_path = str(self.output_dir / "popular_characters.png")
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"已保存: {save_path}")
        return save_path

    def plot_daily_trend(self, data: list) -> str:
        """
        每日识别趋势折线图 + 置信度趋势
        
        Args:
            data: analyzer.get_daily_trend() 的返回值
        
        Returns:
            str: 图表保存路径
        """
        if not HAS_MATPLOTLIB or not data:
            return ""

        dates = [d["date"] for d in data]
        counts = [d["count"] for d in data]
        avg_confs = [d["avg_confidence"] or 0 for d in data]
        total_likes = [d.get("total_likes") or 0 for d in data]

        # 缩短日期显示
        short_dates = [d[5:] for d in dates]  # MM-DD

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
        fig.suptitle("系统运行趋势（最近30天）", fontsize=15, fontweight="bold",
                     color=self.COLORS["text"])

        # 上图：识别次数 + 点赞数
        ax1.fill_between(range(len(dates)), counts, alpha=0.2, color=self.COLORS["primary"])
        ax1.plot(range(len(dates)), counts, 'o-', color=self.COLORS["primary"],
                 linewidth=2, markersize=5, label="识别次数")
        ax1.fill_between(range(len(dates)), total_likes, alpha=0.15, color=self.COLORS["accent"])
        ax1.plot(range(len(dates)), total_likes, 's--', color=self.COLORS["accent"],
                 linewidth=1.5, markersize=4, label="当日点赞")
        ax1.set_ylabel("数量")
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(True)

        # 下图：平均置信度趋势
        ax2.fill_between(range(len(dates)), avg_confs, alpha=0.2, color=self.COLORS["success"])
        ax2.plot(range(len(dates)), avg_confs, 'D-', color=self.COLORS["success"],
                 linewidth=2, markersize=5, label="平均置信度")
        ax2.axhline(y=80, color=self.COLORS["warning"], linestyle="--",
                    alpha=0.7, label="80%基准线")
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("置信度 (%)")
        ax2.set_xlabel("日期")
        ax2.legend(loc="upper left", fontsize=9)
        ax2.grid(True)

        # X轴刻度：每5天显示一个
        step = max(1, len(dates) // 8)
        ticks = list(range(0, len(dates), step))
        ax2.set_xticks(ticks)
        ax2.set_xticklabels([short_dates[i] for i in ticks], rotation=30, ha='right', fontsize=8)

        plt.tight_layout()
        save_path = str(self.output_dir / "daily_trend.png")
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"已保存: {save_path}")
        return save_path

    def plot_confidence_distribution(self, data: dict) -> str:
        """
        置信度分布饼图
        
        Args:
            data: analyzer.get_confidence_distribution() 的返回值
        
        Returns:
            str: 图表保存路径
        """
        if not HAS_MATPLOTLIB or not data:
            return ""

        labels = list(data.keys())
        values = list(data.values())
        
        # 过滤0值
        filtered = [(l, v) for l, v in zip(labels, values) if v > 0]
        if not filtered:
            return ""
        labels, values = zip(*filtered)

        colors = [
            "#00D68F", "#4CAF50", "#6C63FF", "#FFB700", "#FF9800", "#FF6584"
        ][:len(labels)]

        fig, ax = plt.subplots(1, 1, figsize=(8, 6))
        fig.patch.set_facecolor(self.COLORS["bg"])
        ax.set_facecolor(self.COLORS["bg"])

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            pctdistance=0.75,
            wedgeprops=dict(width=0.6, edgecolor=self.COLORS["bg"], linewidth=2),
        )
        
        for text in texts:
            text.set_color(self.COLORS["text"])
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_color("#fff")
            autotext.set_fontweight("bold")
            autotext.set_fontsize(9)

        ax.set_title("识别置信度分布", color=self.COLORS["text"],
                     fontsize=13, fontweight="bold", pad=15)
        
        # 中心注解
        total = sum(values)
        ax.text(0, 0, f"共\n{total}次", ha="center", va="center",
                fontsize=11, fontweight="bold", color=self.COLORS["text"])

        plt.tight_layout()
        save_path = str(self.output_dir / "confidence_distribution.png")
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"已保存: {save_path}")
        return save_path

    def plot_hourly_heatmap(self, data: list) -> str:
        """
        活跃时段热力图（24小时分布）
        
        Args:
            data: analyzer.get_hourly_distribution() 的返回值
        
        Returns:
            str: 图表保存路径
        """
        if not HAS_MATPLOTLIB or not data:
            return ""

        hours = [d["hour"] for d in data]
        counts = [d["count"] for d in data]

        fig, ax = plt.subplots(figsize=(14, 3.5))
        fig.patch.set_facecolor(self.COLORS["bg"])
        ax.set_facecolor(self.COLORS["bg_card"])

        # 重塑为4行×6列的热力图
        counts_arr = np.array(counts).reshape(1, 24)
        
        im = ax.imshow(counts_arr, aspect="auto", cmap="YlOrRd",
                       interpolation="nearest")
        
        ax.set_xticks(range(24))
        ax.set_xticklabels([f"{h:02d}:00" for h in range(24)],
                           rotation=45, ha="right", fontsize=7.5, color=self.COLORS["muted"])
        ax.set_yticks([])
        
        # 在格子上标注数量
        for j, count in enumerate(counts):
            color = "white" if count > max(counts) * 0.5 else self.COLORS["muted"]
            ax.text(j, 0, str(count), ha="center", va="center",
                    fontsize=8, fontweight="bold" if count > 0 else "normal", color=color)
        
        # 颜色条
        cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                             fraction=0.04, pad=0.25, aspect=60)
        cbar.ax.tick_params(colors=self.COLORS["muted"], labelsize=8)
        cbar.set_label("识别次数", color=self.COLORS["muted"], fontsize=9)
        
        ax.set_title("用户活跃时段分布（24小时）",
                     color=self.COLORS["text"], fontsize=13, fontweight="bold")

        plt.tight_layout()
        save_path = str(self.output_dir / "hourly_heatmap.png")
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"已保存: {save_path}")
        return save_path

    def generate_all_charts(self, analyzer) -> dict:
        """生成所有图表"""
        print("\n生成可视化图表...")
        saved_paths = {}

        try:
            saved_paths["popular"] = self.plot_popular_characters(
                analyzer.get_popular_characters(15)
            )
        except Exception as e:
            print(f"  热门角色图表生成失败: {e}")

        try:
            saved_paths["trend"] = self.plot_daily_trend(
                analyzer.get_daily_trend(30)
            )
        except Exception as e:
            print(f"  趋势图表生成失败: {e}")

        try:
            saved_paths["confidence"] = self.plot_confidence_distribution(
                analyzer.get_confidence_distribution()
            )
        except Exception as e:
            print(f"  置信度分布图表生成失败: {e}")

        try:
            saved_paths["hourly"] = self.plot_hourly_heatmap(
                analyzer.get_hourly_distribution()
            )
        except Exception as e:
            print(f"  时段热力图生成失败: {e}")

        return saved_paths


# ==============================
# ECharts 数据接口
# ==============================
class EChartsDataBuilder:
    """
    为Web端ECharts提供JSON格式的图表数据
    这些数据将由 Flask API 返回给前端渲染
    """

    @staticmethod
    def build_popular_bar(data: list, top_n: int = 10) -> dict:
        """
        热门角色识别频率柱状图配置（ECharts option格式）
        """
        data = data[:top_n]
        names = [d.get("name", "未知") for d in reversed(data)]
        counts = [d.get("count", 0) for d in reversed(data)]

        return {
            "title": {"text": "角色识别热度 Top-10", "textStyle": {"color": "#E8E8F0"}},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "20%", "right": "10%"},
            "xAxis": {"type": "value", "axisLabel": {"color": "#8888AA"}},
            "yAxis": {
                "type": "category",
                "data": names,
                "axisLabel": {"color": "#E8E8F0", "fontSize": 12},
            },
            "series": [{
                "type": "bar",
                "data": counts,
                "itemStyle": {
                    "color": {
                        "type": "linear",
                        "x": 0, "y": 0, "x2": 1, "y2": 0,
                        "colorStops": [
                            {"offset": 0, "color": "#6C63FF"},
                            {"offset": 1, "color": "#FF6584"},
                        ]
                    }
                },
                "barMaxWidth": 30,
                "label": {"show": True, "position": "right", "color": "#E8E8F0"},
            }],
            "backgroundColor": "#1A1A2E",
        }

    @staticmethod
    def build_trend_line(data: list) -> dict:
        """
        每日趋势折线图配置
        """
        dates = [d["date"] for d in data]
        counts = [d["count"] for d in data]
        avg_confs = [d.get("avg_confidence") or 0 for d in data]

        return {
            "title": {"text": "识别趋势（近30天）", "textStyle": {"color": "#E8E8F0"}},
            "tooltip": {"trigger": "axis"},
            "legend": {
                "data": ["识别次数", "平均置信度(%)"],
                "textStyle": {"color": "#8888AA"},
            },
            "grid": {"left": "3%", "right": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": "#8888AA", "rotate": 30},
            },
            "yAxis": [
                {"type": "value", "name": "次数", "nameTextStyle": {"color": "#8888AA"}},
                {
                    "type": "value", "name": "置信度(%)",
                    "min": 0, "max": 100,
                    "nameTextStyle": {"color": "#8888AA"},
                },
            ],
            "series": [
                {
                    "name": "识别次数",
                    "type": "line",
                    "data": counts,
                    "smooth": True,
                    "areaStyle": {"opacity": 0.15, "color": "#6C63FF"},
                    "lineStyle": {"color": "#6C63FF"},
                    "itemStyle": {"color": "#6C63FF"},
                },
                {
                    "name": "平均置信度(%)",
                    "type": "line",
                    "yAxisIndex": 1,
                    "data": avg_confs,
                    "smooth": True,
                    "lineStyle": {"color": "#00D68F", "type": "dashed"},
                    "itemStyle": {"color": "#00D68F"},
                },
            ],
            "backgroundColor": "#1A1A2E",
        }

    @staticmethod
    def build_confidence_pie(data: dict) -> dict:
        """置信度分布饼图配置"""
        pie_data = [{"name": k, "value": v} for k, v in data.items() if v > 0]
        
        return {
            "title": {"text": "置信度分布", "textStyle": {"color": "#E8E8F0"}, "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}次 ({d}%)"},
            "legend": {
                "orient": "vertical", "left": "left",
                "textStyle": {"color": "#8888AA"},
            },
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": pie_data,
                "emphasis": {
                    "itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0,0,0,0.5)"}
                },
                "label": {"color": "#E8E8F0"},
            }],
            "backgroundColor": "#1A1A2E",
            "color": ["#00D68F", "#4CAF50", "#6C63FF", "#FFB700", "#FF9800", "#FF6584"],
        }

    @staticmethod
    def build_hourly_heatmap(data: list) -> dict:
        """活跃时段热力图配置"""
        # ECharts热力图格式：[[小时, 0, 值], ...]（y轴固定为0）
        heatmap_data = [[d["hour"], 0, d["count"]] for d in data]
        max_count = max(d["count"] for d in data) if data else 1

        return {
            "title": {"text": "用户活跃时段分布", "textStyle": {"color": "#E8E8F0"}},
            "tooltip": {
                "formatter": lambda p: f"{p['data'][0]}:00  识别次数: {p['data'][2]}"
            },
            "visualMap": {
                "min": 0, "max": max_count,
                "calculable": True,
                "orient": "horizontal",
                "left": "center", "bottom": "3%",
                "textStyle": {"color": "#8888AA"},
                "inRange": {"color": ["#1A1A2E", "#6C63FF", "#FF6584"]},
            },
            "grid": {"height": "50%", "top": "15%"},
            "xAxis": {
                "type": "category",
                "data": [f"{h:02d}:00" for h in range(24)],
                "splitArea": {"show": True},
                "axisLabel": {"color": "#8888AA"},
            },
            "yAxis": {
                "type": "category",
                "data": [""],
                "splitArea": {"show": True},
            },
            "series": [{
                "type": "heatmap",
                "data": heatmap_data,
                "label": {"show": True, "color": "#fff"},
                "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.5)"}},
            }],
            "backgroundColor": "#1A1A2E",
        }

    @classmethod
    def build_all(cls, analyzer) -> dict:
        """生成所有ECharts配置数据"""
        return {
            "popular_bar": cls.build_popular_bar(analyzer.get_popular_characters(10)),
            "trend_line": cls.build_trend_line(analyzer.get_daily_trend(30)),
            "confidence_pie": cls.build_confidence_pie(analyzer.get_confidence_distribution()),
            "hourly_heatmap": cls.build_hourly_heatmap(analyzer.get_hourly_distribution()),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据可视化工具")
    parser.add_argument("--type", "-t",
                        choices=["matplotlib", "echarts", "all"],
                        default="all", help="生成图表类型")
    parser.add_argument("--output-dir", "-o", type=str, default=None)
    args = parser.parse_args()

    try:
        from module4_analysis.analyzer import BehaviorAnalyzer
        analyzer = BehaviorAnalyzer()

        if args.type in ("matplotlib", "all"):
            generator = StaticChartGenerator(args.output_dir)
            paths = generator.generate_all_charts(analyzer)
            print(f"\n已生成 {sum(1 for p in paths.values() if p)} 个静态图表")

        if args.type in ("echarts", "all"):
            echarts_data = EChartsDataBuilder.build_all(analyzer)
            output_path = os.path.join(
                args.output_dir or LOGS_DIR,
                "echarts_data.json"
            )
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(echarts_data, f, ensure_ascii=False, indent=2)
            print(f"\nECharts数据已保存: {output_path}")

    except Exception as e:
        print(f"可视化失败: {e}")
        raise
