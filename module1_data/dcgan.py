"""
module1_data/dcgan.py - DCGAN数据增强模块
基于深度卷积生成对抗网络（DCGAN）生成多样本动漫角色图像
用于扩充稀有角色数据

参考：Radford et al., "Unsupervised Representation Learning with Deep 
Convolutional Generative Adversarial Networks" (2015)

架构说明：
    - Generator: 从随机噪声生成64×64动漫图像
    - Discriminator: 判断图像真实性
    - 训练策略: 交替训练G和D，学习率2e-4，Beta1=0.5
"""
import os
import sys
import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from torchvision.utils import save_image
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    GAN_LATENT_DIM, GAN_IMAGE_SIZE, GAN_EPOCHS,
    GAN_LR, GAN_BETA1, AUGMENTED_DIR, PROCESSED_DIR,
    ANIME_CHARACTERS
)


# =====================
# 生成器 (Generator)
# =====================
class Generator(nn.Module):
    """
    DCGAN生成器
    输入: 随机噪声向量 (batch, latent_dim, 1, 1)
    输出: 生成图像 (batch, 3, 64, 64)
    """
    def __init__(self, latent_dim: int = GAN_LATENT_DIM, image_size: int = GAN_IMAGE_SIZE):
        super().__init__()
        self.latent_dim = latent_dim
        
        # 计算特征图大小
        ngf = 64  # 生成器特征图基础数量

        self.main = nn.Sequential(
            # 输入: latent_dim × 1 × 1
            nn.ConvTranspose2d(latent_dim, ngf * 8, 4, 1, 0, bias=False),
            nn.BatchNorm2d(ngf * 8),
            nn.ReLU(True),
            # 状态大小: (ngf*8) × 4 × 4

            nn.ConvTranspose2d(ngf * 8, ngf * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 4),
            nn.ReLU(True),
            # 状态大小: (ngf*4) × 8 × 8

            nn.ConvTranspose2d(ngf * 4, ngf * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 2),
            nn.ReLU(True),
            # 状态大小: (ngf*2) × 16 × 16

            nn.ConvTranspose2d(ngf * 2, ngf, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf),
            nn.ReLU(True),
            # 状态大小: (ngf) × 32 × 32

            nn.ConvTranspose2d(ngf, 3, 4, 2, 1, bias=False),
            nn.Tanh()
            # 输出大小: 3 × 64 × 64
        )

    def forward(self, z):
        return self.main(z)


# ========================
# 判别器 (Discriminator)
# ========================
class Discriminator(nn.Module):
    """
    DCGAN判别器
    输入: 图像 (batch, 3, 64, 64)
    输出: 真实概率标量 (batch, 1)
    """
    def __init__(self, image_size: int = GAN_IMAGE_SIZE):
        super().__init__()
        ndf = 64  # 判别器特征图基础数量

        self.main = nn.Sequential(
            # 输入: 3 × 64 × 64
            nn.Conv2d(3, ndf, 4, 2, 1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            # 状态大小: (ndf) × 32 × 32

            nn.Conv2d(ndf, ndf * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            # 状态大小: (ndf*2) × 16 × 16

            nn.Conv2d(ndf * 2, ndf * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 4),
            nn.LeakyReLU(0.2, inplace=True),
            # 状态大小: (ndf*4) × 8 × 8

            nn.Conv2d(ndf * 4, ndf * 8, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 8),
            nn.LeakyReLU(0.2, inplace=True),
            # 状态大小: (ndf*8) × 4 × 4

            nn.Conv2d(ndf * 8, 1, 4, 1, 0, bias=False),
            nn.Sigmoid()
            # 输出大小: 1 × 1 × 1
        )

    def forward(self, x):
        return self.main(x).view(-1, 1).squeeze(1)


# ========================
# 数据集
# ========================
class SingleCharacterDataset(Dataset):
    """单个动漫角色的图像数据集（用于GAN训练）"""

    def __init__(self, char_dir: str, image_size: int = GAN_IMAGE_SIZE):
        self.char_dir = Path(char_dir)
        self.transform = transforms.Compose([
            transforms.Resize(image_size),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
        ])
        
        self.image_paths = []
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
            self.image_paths.extend(self.char_dir.glob(ext))
        self.image_paths.sort()

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img = Image.open(self.image_paths[idx]).convert('RGB')
        return self.transform(img)


# ========================
# 权重初始化
# ========================
def weights_init(m):
    """DCGAN论文中推荐的权重初始化方法"""
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        nn.init.normal_(m.weight.data, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)


# ========================
# DCGAN训练器
# ========================
class DCGANTrainer:
    """DCGAN训练器"""

    def __init__(
        self,
        character_key: str,
        data_dir: str = None,
        output_dir: str = AUGMENTED_DIR,
        latent_dim: int = GAN_LATENT_DIM,
        image_size: int = GAN_IMAGE_SIZE,
        lr: float = GAN_LR,
        beta1: float = GAN_BETA1,
        batch_size: int = 64,
        epochs: int = GAN_EPOCHS,
        device: str = None,
    ):
        self.character_key = character_key
        self.data_dir = Path(data_dir) if data_dir else Path(PROCESSED_DIR)
        self.output_dir = Path(output_dir) / character_key
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.latent_dim = latent_dim
        self.image_size = image_size
        self.batch_size = batch_size
        self.epochs = epochs
        
        # 自动选择设备
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        print(f"使用设备: {self.device}")

        # 初始化网络
        self.netG = Generator(latent_dim, image_size).to(self.device)
        self.netD = Discriminator(image_size).to(self.device)
        self.netG.apply(weights_init)
        self.netD.apply(weights_init)

        # 损失函数和优化器
        self.criterion = nn.BCELoss()
        self.optimG = optim.Adam(self.netG.parameters(), lr=lr, betas=(beta1, 0.999))
        self.optimD = optim.Adam(self.netD.parameters(), lr=lr, betas=(beta1, 0.999))

        # 固定噪声（用于可视化训练进度）
        self.fixed_noise = torch.randn(64, latent_dim, 1, 1, device=self.device)

        # 记录训练历史
        self.history = {"g_loss": [], "d_loss": [], "d_real": [], "d_fake": []}

    def train(self):
        """执行DCGAN训练"""
        char_dir = self.data_dir / self.character_key
        dataset = SingleCharacterDataset(str(char_dir), self.image_size)
        
        if len(dataset) == 0:
            print(f"[错误] 角色 {self.character_key} 没有训练图像，跳过GAN训练")
            return

        print(f"\n开始训练DCGAN - 角色: {ANIME_CHARACTERS.get(self.character_key, {}).get('name', self.character_key)}")
        print(f"训练图像: {len(dataset)} 张 | 批次大小: {self.batch_size} | Epoch: {self.epochs}")

        dataloader = DataLoader(
            dataset, batch_size=self.batch_size,
            shuffle=True, num_workers=0, drop_last=True
        )

        real_label = 1.0
        fake_label = 0.0

        for epoch in range(self.epochs):
            epoch_g_loss = 0.0
            epoch_d_loss = 0.0
            epoch_d_real = 0.0
            epoch_d_fake = 0.0

            for i, real_imgs in enumerate(dataloader):
                real_imgs = real_imgs.to(self.device)
                batch_size = real_imgs.size(0)
                label_real = torch.full((batch_size,), real_label,
                                        dtype=torch.float, device=self.device)
                label_fake = torch.full((batch_size,), fake_label,
                                        dtype=torch.float, device=self.device)

                # =====================
                # 训练判别器D
                # =====================
                self.netD.zero_grad()
                
                # 真实图像
                output_real = self.netD(real_imgs)
                d_loss_real = self.criterion(output_real, label_real)
                d_loss_real.backward()
                d_real_mean = output_real.mean().item()

                # 生成假图像
                noise = torch.randn(batch_size, self.latent_dim, 1, 1, device=self.device)
                fake_imgs = self.netG(noise)
                output_fake = self.netD(fake_imgs.detach())
                d_loss_fake = self.criterion(output_fake, label_fake)
                d_loss_fake.backward()
                d_fake_mean_before = output_fake.mean().item()
                
                d_loss = d_loss_real + d_loss_fake
                self.optimD.step()

                # =====================
                # 训练生成器G
                # =====================
                self.netG.zero_grad()
                
                # 生成器希望判别器把假图判断为真
                output_fake2 = self.netD(fake_imgs)
                g_loss = self.criterion(output_fake2, label_real)
                g_loss.backward()
                self.optimG.step()

                epoch_d_loss += d_loss.item()
                epoch_g_loss += g_loss.item()
                epoch_d_real += d_real_mean
                epoch_d_fake += output_fake2.mean().item()

            n_batches = len(dataloader)
            avg_d = epoch_d_loss / n_batches
            avg_g = epoch_g_loss / n_batches
            avg_dr = epoch_d_real / n_batches
            avg_df = epoch_d_fake / n_batches

            self.history["d_loss"].append(avg_d)
            self.history["g_loss"].append(avg_g)
            self.history["d_real"].append(avg_dr)
            self.history["d_fake"].append(avg_df)

            if (epoch + 1) % 10 == 0 or epoch == 0:
                print(
                    f"  Epoch [{epoch+1:3d}/{self.epochs}] "
                    f"D_loss: {avg_d:.4f} | G_loss: {avg_g:.4f} | "
                    f"D(real): {avg_dr:.4f} | D(fake): {avg_df:.4f}"
                )
                # 保存生成样本
                sample_path = self.output_dir / f"samples_epoch{epoch+1:03d}.png"
                with torch.no_grad():
                    fake_sample = self.netG(self.fixed_noise)
                save_image(fake_sample[:16], str(sample_path),
                          nrow=4, normalize=True)

        print(f"\n训练完成！")
        self.save_checkpoint()

    def save_checkpoint(self):
        """保存模型权重"""
        checkpoint_path = self.output_dir / f"dcgan_{self.character_key}.pth"
        torch.save({
            "generator_state_dict": self.netG.state_dict(),
            "discriminator_state_dict": self.netD.state_dict(),
            "history": self.history,
            "config": {
                "character_key": self.character_key,
                "latent_dim": self.latent_dim,
                "image_size": self.image_size,
                "epochs": self.epochs,
            }
        }, checkpoint_path)
        print(f"模型已保存: {checkpoint_path}")

    def generate_images(self, num_images: int = 100, checkpoint_path: str = None):
        """
        使用训练好的生成器生成新图像
        
        Args:
            num_images: 生成图像数量
            checkpoint_path: 权重文件路径（None则使用当前网络）
        """
        if checkpoint_path:
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            self.netG.load_state_dict(checkpoint["generator_state_dict"])

        self.netG.eval()
        generated_dir = self.output_dir / "generated"
        generated_dir.mkdir(exist_ok=True)

        print(f"\n生成图像: {num_images} 张 -> {generated_dir}")
        
        with torch.no_grad():
            for i in range(0, num_images, 64):
                batch_size = min(64, num_images - i)
                noise = torch.randn(batch_size, self.latent_dim, 1, 1, device=self.device)
                fake_imgs = self.netG(noise)
                
                # 反归一化 [-1,1] -> [0,1]
                fake_imgs = (fake_imgs + 1) / 2
                
                for j, img_tensor in enumerate(fake_imgs):
                    img_array = (img_tensor.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                    img = Image.fromarray(img_array)
                    img_path = generated_dir / f"gen_{self.character_key}_{i+j:04d}.jpg"
                    img.save(str(img_path))
        
        print(f"图像生成完成！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DCGAN数据增强训练")
    parser.add_argument("--character", "-c", type=str, required=True,
                        help="目标角色key")
    parser.add_argument("--epochs", "-e", type=int, default=GAN_EPOCHS,
                        help=f"训练轮数（默认{GAN_EPOCHS}）")
    parser.add_argument("--generate", "-g", type=int, default=0,
                        help="生成额外图像数量（需要已有checkpoint）")
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="已有权重文件路径")
    args = parser.parse_args()

    trainer = DCGANTrainer(
        character_key=args.character,
        epochs=args.epochs,
    )

    if args.generate > 0:
        trainer.generate_images(args.generate, args.checkpoint)
    else:
        trainer.train()
        trainer.generate_images(num_images=100)
