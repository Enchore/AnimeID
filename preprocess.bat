@echo off
chcp 65001 >nul
title 数据预处理 - 动漫角色识别

cd /d "%~dp0"

echo ==========================================
echo    动漫图像数据预处理
echo ==========================================
echo.
echo 步骤1：下载示例图像
python module1_data/crawler.py --count 20

echo.
echo 步骤2：图像预处理
python module1_data/preprocessor.py --split

echo.
echo 步骤3：生成数据标注
python module1_data/annotator.py

echo.
echo 预处理完成！
pause
