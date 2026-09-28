"""
module2_model/models.py - 动漫角色识别模型定义
实现：
    - ResNet-50 基线模型（带embedding层）
    - MobileNetV2 轻量级模型
    - 通用 AnimeRecognitionModel 接口
"""
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    NUM_CLASSES, EMBEDDING_SIZE, MODEL_BACKBONE,
    DROPOUT_RATE, IMAGE_SIZE
)


class AnimeRecognitionModel(nn.Module):
    """
    动漫角色识别模型基类
    
    结构：
        Backbone（ResNet-50/MobileNetV2）
        → Global Average Pooling
        → Embedding Layer (512维)
        → L2归一化
        → （训练时接损失头，推理时直接用embedding计算相似度）
    """
    
    def __init__(
        self,
        backbone: str = MODEL_BACKBONE,
        num_classes: int = NUM_CLASSES,
        embedding_size: int = EMBEDDING_SIZE,
        dropout_rate: float = DROPOUT_RATE,
        pretrained: bool = True,
    ):
        super().__init__()
        self.backbone_name = backbone
        self.num_classes = num_classes
        self.embedding_size = embedding_size

        # ===== 骨干网络 =====
        if backbone == "resnet50":
            base_model = models.resnet50(
                weights=models.ResNet50_Weights.DEFAULT if pretrained else None
            )
            # 去掉最后的全连接层，保留特征提取部分
            self.backbone = nn.Sequential(*list(base_model.children())[:-1])
            backbone_out_dim = 2048
            
        elif backbone == "mobilenet_v2":
            base_model = models.mobilenet_v2(
                weights=models.MobileNet_V2_Weights.DEFAULT if pretrained else None
            )
            self.backbone = base_model.features
            backbone_out_dim = 1280
            
        else:
            raise ValueError(f"不支持的骨干网络: {backbone}，请选择 resnet50 或 mobilenet_v2")

        # ===== Embedding头 =====
        self.embedding_head = nn.Sequential(
            nn.Dropout(p=dropout_rate),
            nn.Linear(backbone_out_dim, embedding_size),
            nn.BatchNorm1d(embedding_size),
        )

        # ===== 分类头（Softmax损失使用）=====
        self.classifier = nn.Linear(embedding_size, num_classes)

        self._init_weights()

    def _init_weights(self):
        """初始化embedding和分类头权重"""
        for m in self.embedding_head.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
        
        nn.init.xavier_normal_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)

    def extract_features(self, x: torch.Tensor) -> torch.Tensor:
        """
        提取图像特征向量（L2归一化的embedding）
        
        Args:
            x: 输入图像张量 (B, C, H, W)
        
        Returns:
            torch.Tensor: L2归一化特征向量 (B, embedding_size)
        """
        # 骨干网络提取特征
        if self.backbone_name == "resnet50":
            feat = self.backbone(x)          # (B, 2048, 1, 1)
            feat = feat.view(feat.size(0), -1)  # (B, 2048)
        else:
            feat = self.backbone(x)          # (B, 1280, 7, 7)
            feat = F.adaptive_avg_pool2d(feat, (1, 1))
            feat = feat.view(feat.size(0), -1)  # (B, 1280)

        # Embedding
        embedding = self.embedding_head(feat)  # (B, embedding_size)
        
        # L2归一化（对ArcFace/CosFace很重要）
        embedding = F.normalize(embedding, p=2, dim=1)
        return embedding

    def forward(self, x: torch.Tensor) -> tuple:
        """
        前向传播
        
        Args:
            x: 输入图像 (B, C, H, W)
        
        Returns:
            tuple: (embedding, logits)
                   embedding: L2归一化特征 (B, embedding_size)
                   logits: 分类logits (B, num_classes)，用于Softmax损失
        """
        embedding = self.extract_features(x)
        logits = self.classifier(embedding)
        return embedding, logits

    def get_backbone_parameters(self):
        """获取骨干网络参数（用于分层学习率）"""
        return self.backbone.parameters()

    def get_head_parameters(self):
        """获取头部参数（embedding + 分类，用于分层学习率）"""
        params = list(self.embedding_head.parameters())
        params += list(self.classifier.parameters())
        return params

    def count_parameters(self) -> dict:
        """统计模型参数量"""
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        backbone = sum(p.numel() for p in self.backbone.parameters())
        head = sum(p.numel() for p in self.embedding_head.parameters())
        
        return {
            "total": total,
            "trainable": trainable,
            "backbone": backbone,
            "head": head,
            "total_M": total / 1e6,
        }

    def freeze_backbone(self):
        """冻结骨干网络（仅训练头部）"""
        for param in self.backbone.parameters():
            param.requires_grad = False
        print(f"骨干网络已冻结（{self.backbone_name}）")

    def unfreeze_backbone(self):
        """解冻骨干网络"""
        for param in self.backbone.parameters():
            param.requires_grad = True
        print(f"骨干网络已解冻（{self.backbone_name}）")

    def save(self, path: str, extra_info: dict = None):
        """保存模型"""
        checkpoint = {
            "model_state_dict": self.state_dict(),
            "backbone": self.backbone_name,
            "num_classes": self.num_classes,
            "embedding_size": self.embedding_size,
        }
        if extra_info:
            checkpoint.update(extra_info)
        torch.save(checkpoint, path)
        print(f"模型已保存: {path}")

    @classmethod
    def load(cls, path: str, device: str = "cpu") -> "AnimeRecognitionModel":
        """加载模型"""
        checkpoint = torch.load(path, map_location=device)
        model = cls(
            backbone=checkpoint["backbone"],
            num_classes=checkpoint["num_classes"],
            embedding_size=checkpoint["embedding_size"],
            pretrained=False,
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        return model


def build_model(
    backbone: str = MODEL_BACKBONE,
    num_classes: int = NUM_CLASSES,
    embedding_size: int = EMBEDDING_SIZE,
    pretrained: bool = True,
    freeze_backbone: bool = False,
) -> AnimeRecognitionModel:
    """
    便捷模型构建函数
    
    Args:
        backbone: 骨干网络类型
        num_classes: 分类数
        embedding_size: 特征维度
        pretrained: 是否使用预训练权重
        freeze_backbone: 是否冻结骨干（适合训练初期）
    
    Returns:
        AnimeRecognitionModel 实例
    """
    model = AnimeRecognitionModel(
        backbone=backbone,
        num_classes=num_classes,
        embedding_size=embedding_size,
        pretrained=pretrained,
    )
    
    if freeze_backbone:
        model.freeze_backbone()
    
    # 打印模型信息
    params = model.count_parameters()
    print(f"\n模型初始化完成:")
    print(f"  骨干网络: {backbone}")
    print(f"  分类数: {num_classes}")
    print(f"  特征维度: {embedding_size}")
    print(f"  总参数量: {params['total_M']:.2f}M")
    print(f"  可训练参数: {params['trainable']:,}")
    
    return model


if __name__ == "__main__":
    # 测试模型
    print("测试 ResNet-50 模型...")
    model_r50 = build_model(backbone="resnet50")
    x = torch.randn(2, 3, IMAGE_SIZE, IMAGE_SIZE)
    embedding, logits = model_r50(x)
    print(f"  输入形状: {x.shape}")
    print(f"  Embedding形状: {embedding.shape}")
    print(f"  Logits形状: {logits.shape}")
    
    print("\n测试 MobileNetV2 模型...")
    model_mv2 = build_model(backbone="mobilenet_v2")
    embedding2, logits2 = model_mv2(x)
    print(f"  Embedding形状: {embedding2.shape}")
    print(f"  Logits形状: {logits2.shape}")
