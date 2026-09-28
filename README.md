# 基于深度学习的动漫角色图像识别系统

[![CI](https://github.com/Enchore/AnimeID/actions/workflows/ci.yml/badge.svg)](https://github.com/Enchore/AnimeID/actions/workflows/ci.yml)


> 开发语言：Python | 框架：PyTorch + Flask | 数据库：SQLite

---

## 项目结构

```
anime-recognition-system/
├── module1_data/           # 模块1：数据收集与预处理
│   ├── crawler.py          # 图像爬取脚本
│   ├── preprocessor.py     # 图像预处理（裁剪/去水印/标准化）
│   ├── annotator.py        # 数据标注工具
│   └── dcgan.py            # DCGAN数据增强
├── module2_model/          # 模块2：模型构建与训练
│   ├── models.py           # ResNet-50 / MobileNetV2 定义
│   ├── losses.py           # ArcFace / CosFace 损失函数
│   ├── trainer.py          # 训练器（迁移学习 + 分层LR）
│   └── evaluator.py        # 评估（Top-1/Top-5/mAP）
├── module3_web/            # 模块3：Web应用（Flask）
│   ├── app.py              # Flask主应用
│   ├── api.py              # 识别API蓝图
│   ├── templates/          # HTML模板
│   └── static/             # 前端资源（CSS/JS/图片）
├── module4_analysis/       # 模块4：行为分析与可视化
│   ├── logger.py           # 行为日志记录
│   ├── analyzer.py         # 统计分析脚本
│   └── visualizer.py       # ECharts数据生成 + Matplotlib图表
├── data/
│   ├── raw/                # 原始图像
│   ├── processed/          # 预处理后图像
│   └── augmented/          # GAN增强图像
├── models/                 # 训练好的模型权重
├── logs/                   # 运行日志
├── config.py               # 全局配置
├── requirements.txt        # 依赖清单
└── README.md
```

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
python module3_web/app.py --init-db

# 3. 启动Web服务
python module3_web/app.py

# 4. 浏览器访问
http://localhost:5000
```

## 环境变量配置

本仓库是公开仓库，所有密钥一律通过环境变量注入，代码中不含任何明文凭据。
先复制模板再填写：

```bash
cp .env.example .env   # Windows 用 copy .env.example .env
```

| 变量 | 用途 | 不设置会怎样 |
|------|------|--------------|
| `DASHSCOPE_API_KEY` | 通义千问 VL 的图像识别与多语言补全 | 识别功能不可用，其余模块正常 |
| `FLASK_SECRET_KEY` | 签名 Flask session cookie | 每次启动随机生成（重启后需重新登录） |
| `ADMIN_PASSWORD` | 管理后台登录密码 | 管理登录一律拒绝，不会退化成空密码放行 |

> `FLASK_SECRET_KEY` 泄露等同于管理员身份可被伪造，请务必用
> `python -c "import secrets; print(secrets.token_hex(32))"` 生成，且不要复用。

## 模块说明

| 模块 | 功能 | 核心技术 |
|------|------|----------|
| 模块1 | 数据收集、标注、预处理、GAN增强 | OpenCV、DCGAN |
| 模块2 | 模型训练与评估 | ResNet-50、ArcFace、迁移学习 |
| 模块3 | Web API + 社交前端 | Flask、Bootstrap 5 |
| 模块4 | 行为分析与可视化 | ECharts、Matplotlib |

## 参考文献

1. 李航. 机器学习方法（第2版）. 清华大学出版社, 2025.
2. 奥雷利安·杰龙. 机器学习实战. 机械工业出版社, 2024.
3. 李沐等. 动手学深度学习（PyTorch版）. 人民邮电出版社, 2023.
4. 言有三. 深度学习之图像识别：核心算法与实战案例. 清华大学出版社, 2023.
