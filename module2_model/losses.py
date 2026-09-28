"""
module2_model/losses.py - 损失函数模块
实现：
    - ArcFace (Additive Angular Margin Loss)
    - CosFace (Large Margin Cosine Loss)
    - Label Smoothing Cross Entropy（防过拟合）
    - 组合损失

参考论文：
    ArcFace: Deng et al., "ArcFace: Additive Angular Margin Loss for Deep Face Recognition" (2019)
    CosFace: Wang et al., "CosFace: Large Margin Cosine Loss for Deep Face Recognition" (2018)
"""
import sys
import math
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    NUM_CLASSES, EMBEDDING_SIZE, LOSS_TYPE,
    ARCFACE_SCALE, ARCFACE_MARGIN,
    COSFACE_SCALE, COSFACE_MARGIN,
    LABEL_SMOOTHING
)


class ArcFaceLoss(nn.Module):
    """
    ArcFace: Additive Angular Margin Loss
    
    相比普通Softmax，ArcFace在角度空间增加margin，
    使同类特征更紧密，异类特征更分散。
    
    数学原理：
        L = -log [ e^(s·cos(θ+m)) / (e^(s·cos(θ+m)) + Σe^(s·cos(θj))) ]
    
    Args:
        embedding_size: 特征向量维度
        num_classes: 分类数（动漫角色数）
        scale: 缩放因子s（默认64）
        margin: 角度margin m（默认0.5，单位：弧度）
        easy_margin: 是否使用简单margin
    """

    def __init__(
        self,
        embedding_size: int = EMBEDDING_SIZE,
        num_classes: int = NUM_CLASSES,
        scale: float = ARCFACE_SCALE,
        margin: float = ARCFACE_MARGIN,
        easy_margin: bool = False,
    ):
        super().__init__()
        self.embedding_size = embedding_size
        self.num_classes = num_classes
        self.scale = scale
        self.margin = margin
        self.easy_margin = easy_margin

        # 权重矩阵（代表每个类的原型向量）
        self.weight = nn.Parameter(
            torch.FloatTensor(num_classes, embedding_size)
        )
        nn.init.xavier_uniform_(self.weight)

        # 预计算角度变换
        self.cos_m = math.cos(margin)
        self.sin_m = math.sin(margin)
        self.th = math.cos(math.pi - margin)  # 简单margin阈值
        self.mm = math.sin(math.pi - margin) * margin

    def forward(self, embedding: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Args:
            embedding: L2归一化特征向量 (B, embedding_size)
            labels: 类别标签 (B,)
        
        Returns:
            torch.Tensor: ArcFace损失值（标量）
        """
        # 对权重也进行L2归一化
        weight_norm = F.normalize(self.weight, p=2, dim=1)
        
        # 计算cosine相似度
        cosine = F.linear(embedding, weight_norm)   # (B, num_classes)
        cosine = cosine.clamp(-1 + 1e-7, 1 - 1e-7)  # 数值稳定

        # 计算sin
        sine = torch.sqrt(1.0 - cosine.pow(2))

        # cos(θ + m) = cosθ·cosm - sinθ·sinm
        phi = cosine * self.cos_m - sine * self.sin_m

        if self.easy_margin:
            # 简单margin：若cosθ > 0 才应用margin
            phi = torch.where(cosine > 0, phi, cosine)
        else:
            # 标准margin
            phi = torch.where(cosine > self.th, phi, cosine - self.mm)

        # 将ground truth类别替换为加margin后的值
        one_hot = torch.zeros_like(cosine)
        one_hot.scatter_(1, labels.view(-1, 1).long(), 1)

        output = (one_hot * phi) + ((1.0 - one_hot) * cosine)
        output *= self.scale

        return F.cross_entropy(output, labels)


class CosFaceLoss(nn.Module):
    """
    CosFace: Large Margin Cosine Loss
    
    在余弦空间增加margin，计算更简单，效果与ArcFace接近。
    
    数学原理：
        L = -log [ e^(s·(cos(θ)-m)) / (e^(s·(cos(θ)-m)) + Σe^(s·cos(θj))) ]
    
    Args:
        embedding_size: 特征向量维度
        num_classes: 分类数
        scale: 缩放因子s（默认64）
        margin: 余弦margin m（默认0.35）
    """

    def __init__(
        self,
        embedding_size: int = EMBEDDING_SIZE,
        num_classes: int = NUM_CLASSES,
        scale: float = COSFACE_SCALE,
        margin: float = COSFACE_MARGIN,
    ):
        super().__init__()
        self.embedding_size = embedding_size
        self.num_classes = num_classes
        self.scale = scale
        self.margin = margin

        self.weight = nn.Parameter(
            torch.FloatTensor(num_classes, embedding_size)
        )
        nn.init.xavier_uniform_(self.weight)

    def forward(self, embedding: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Args:
            embedding: L2归一化特征向量 (B, embedding_size)
            labels: 类别标签 (B,)
        
        Returns:
            torch.Tensor: CosFace损失值（标量）
        """
        # 权重归一化
        weight_norm = F.normalize(self.weight, p=2, dim=1)
        
        # 余弦相似度
        cosine = F.linear(embedding, weight_norm)   # (B, num_classes)
        cosine = cosine.clamp(-1 + 1e-7, 1 - 1e-7)

        # cos(θ) - m（只对目标类减去margin）
        one_hot = torch.zeros_like(cosine)
        one_hot.scatter_(1, labels.view(-1, 1).long(), 1)

        output = cosine - one_hot * self.margin
        output *= self.scale

        return F.cross_entropy(output, labels)


class LabelSmoothingCrossEntropy(nn.Module):
    """
    Label Smoothing Cross Entropy Loss
    将硬标签 [0,0,1,0,...] 平滑为 [ε/K, ε/K, 1-ε, ε/K, ...]
    减少过拟合，提升模型泛化性
    
    Args:
        smoothing: 平滑系数ε（默认0.1，任务书要求）
        reduction: 聚合方式（mean/sum）
    """

    def __init__(self, smoothing: float = LABEL_SMOOTHING, reduction: str = "mean"):
        super().__init__()
        assert 0 <= smoothing < 1, "平滑系数必须在 [0, 1) 范围内"
        self.smoothing = smoothing
        self.reduction = reduction

    def forward(self, logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Args:
            logits: 模型输出 (B, num_classes)
            labels: 真实标签 (B,)
        
        Returns:
            torch.Tensor: 平滑后的交叉熵损失
        """
        n_classes = logits.size(-1)
        log_probs = F.log_softmax(logits, dim=-1)

        # 平滑标签分布
        with torch.no_grad():
            smooth_labels = torch.full_like(log_probs, self.smoothing / n_classes)
            smooth_labels.scatter_(1, labels.unsqueeze(1), 1 - self.smoothing + self.smoothing / n_classes)

        loss = -(smooth_labels * log_probs).sum(dim=-1)

        if self.reduction == "mean":
            return loss.mean()
        elif self.reduction == "sum":
            return loss.sum()
        return loss


class CombinedLoss(nn.Module):
    """
    组合损失函数
    = ArcFace/CosFace (metric loss) + α * LabelSmoothing (auxiliary loss)
    
    metric loss帮助特征空间更有区分性
    auxiliary loss直接监督分类准确率
    """

    def __init__(
        self,
        loss_type: str = LOSS_TYPE,
        embedding_size: int = EMBEDDING_SIZE,
        num_classes: int = NUM_CLASSES,
        alpha: float = 0.1,   # auxiliary loss权重
        smoothing: float = LABEL_SMOOTHING,
    ):
        super().__init__()
        self.alpha = alpha
        self.loss_type = loss_type

        # 主损失（metric learning）
        if loss_type == "arcface":
            self.metric_loss = ArcFaceLoss(embedding_size, num_classes)
        elif loss_type == "cosface":
            self.metric_loss = CosFaceLoss(embedding_size, num_classes)
        elif loss_type == "softmax":
            self.metric_loss = None
        else:
            raise ValueError(f"不支持的损失类型: {loss_type}")

        # 辅助损失（Label Smoothing）
        self.aux_loss = LabelSmoothingCrossEntropy(smoothing=smoothing)

    def forward(
        self,
        embedding: torch.Tensor,
        logits: torch.Tensor,
        labels: torch.Tensor,
    ) -> tuple:
        """
        Args:
            embedding: L2归一化特征 (B, embedding_size)
            logits: 分类logits (B, num_classes)
            labels: 真实标签 (B,)
        
        Returns:
            tuple: (total_loss, metric_loss, aux_loss)
        """
        # 辅助分类损失
        aux = self.aux_loss(logits, labels)

        if self.metric_loss is not None:
            # metric learning损失
            metric = self.metric_loss(embedding, labels)
            total = metric + self.alpha * aux
            return total, metric, aux
        else:
            # 仅用softmax
            return aux, aux, aux


def build_loss(
    loss_type: str = LOSS_TYPE,
    embedding_size: int = EMBEDDING_SIZE,
    num_classes: int = NUM_CLASSES,
) -> CombinedLoss:
    """
    便捷损失函数构建
    
    Args:
        loss_type: 损失类型 (arcface/cosface/softmax)
        embedding_size: 特征维度
        num_classes: 分类数
    
    Returns:
        CombinedLoss 实例
    """
    loss_fn = CombinedLoss(
        loss_type=loss_type,
        embedding_size=embedding_size,
        num_classes=num_classes,
    )
    print(f"\n损失函数: {loss_type.upper()} + Label Smoothing(ε={LABEL_SMOOTHING})")
    return loss_fn


if __name__ == "__main__":
    # 测试损失函数
    B, E, C = 4, 512, NUM_CLASSES
    embedding = F.normalize(torch.randn(B, E), p=2, dim=1)
    logits = torch.randn(B, C)
    labels = torch.randint(0, C, (B,))

    print("测试 ArcFace 损失...")
    arcface = ArcFaceLoss()
    loss = arcface(embedding, labels)
    print(f"  ArcFace Loss: {loss.item():.4f}")

    print("\n测试 CosFace 损失...")
    cosface = CosFaceLoss()
    loss = cosface(embedding, labels)
    print(f"  CosFace Loss: {loss.item():.4f}")

    print("\n测试 Label Smoothing CE 损失...")
    ls_ce = LabelSmoothingCrossEntropy()
    loss = ls_ce(logits, labels)
    print(f"  LS-CE Loss: {loss.item():.4f}")

    print("\n测试 组合损失...")
    combined = build_loss("arcface")
    total, metric, aux = combined(embedding, logits, labels)
    print(f"  Total: {total.item():.4f} | Metric: {metric.item():.4f} | Aux: {aux.item():.4f}")
