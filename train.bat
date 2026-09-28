@echo off
chcp 65001 >nul
title 模型训练 - 动漫角色识别

cd /d "%~dp0"

echo ==========================================
echo    动漫角色识别模型训练
echo ==========================================
echo.
echo 可用参数：
echo   --backbone resnet50        使用ResNet-50（默认）
echo   --backbone mobilenet_v2    使用MobileNetV2（更快）
echo   --loss arcface             使用ArcFace损失（默认）
echo   --loss cosface             使用CosFace损失
echo   --epochs 50                训练轮数（默认50）
echo.

python module2_model/trainer.py %*

pause
