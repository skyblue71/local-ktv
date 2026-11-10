"""
CREPE（AI 音高辨識）的模型長相：一層一層的神經網路。

照抄 torchcrepe 0.0.24 的 model.py（MIT 授權，作者 Max Morrison，
https://github.com/maxrmorrison/torchcrepe ），只留我們用的 "full" 大小。
授權聲明全文見專案最上層的「第三方授權.md」。

為什麼要抄一份：torchcrepe 一載入就會連帶載入 numba，
Windows 的「智慧型應用程式控制」會擋 numba 的檔案。
模型學好的數字（權重）還是用 torchcrepe 套件附的 full.pth，沒有另外下載。
"""
import functools

import torch
import torch.nn.functional as F

PITCH_BINS = 360        # 把音高分成 360 格，每格 20 音分
IN_FEATURES = 2048      # 最後一層前的數字個數

# 每一層的設定（跟 torchcrepe 的 full 一樣）
IN_CHANNELS = [1, 1024, 128, 128, 128, 256]
OUT_CHANNELS = [1024, 128, 128, 128, 256, 512]
KERNEL_SIZES = [(512, 1), (64, 1), (64, 1), (64, 1), (64, 1), (64, 1)]
STRIDES = [(4, 1), (1, 1), (1, 1), (1, 1), (1, 1), (1, 1)]

# 批次正規化的參數（MMdnn 轉檔時留下的數字，要跟原本一樣）
make_batch_norm = functools.partial(torch.nn.BatchNorm2d,
                                    eps=0.0010000000474974513,
                                    momentum=0.0)


def make_conv(index):
    """第 index 層的捲積層"""
    return torch.nn.Conv2d(in_channels=IN_CHANNELS[index],
                           out_channels=OUT_CHANNELS[index],
                           kernel_size=KERNEL_SIZES[index],
                           stride=STRIDES[index])


class CrepeModel(torch.nn.Module):
    """輸入：一幀一幀的聲音 (幀數, 1024)；輸出：每一幀 360 格音高的機率 (幀數, 360)"""

    def __init__(self):
        super().__init__()
        # 名字要跟權重檔一樣（conv1、conv1_BN…），權重才放得進去
        self.conv1 = make_conv(0)
        self.conv1_BN = make_batch_norm(num_features=OUT_CHANNELS[0])
        self.conv2 = make_conv(1)
        self.conv2_BN = make_batch_norm(num_features=OUT_CHANNELS[1])
        self.conv3 = make_conv(2)
        self.conv3_BN = make_batch_norm(num_features=OUT_CHANNELS[2])
        self.conv4 = make_conv(3)
        self.conv4_BN = make_batch_norm(num_features=OUT_CHANNELS[3])
        self.conv5 = make_conv(4)
        self.conv5_BN = make_batch_norm(num_features=OUT_CHANNELS[4])
        self.conv6 = make_conv(5)
        self.conv6_BN = make_batch_norm(num_features=OUT_CHANNELS[5])
        self.classifier = torch.nn.Linear(in_features=IN_FEATURES,
                                          out_features=PITCH_BINS)

    def forward(self, frames):
        # 形狀變成 (幀數, 1, 1024, 1)
        x = frames[:, None, :, None]
        x = self.layer(x, self.conv1, self.conv1_BN, (0, 0, 254, 254))
        x = self.layer(x, self.conv2, self.conv2_BN)
        x = self.layer(x, self.conv3, self.conv3_BN)
        x = self.layer(x, self.conv4, self.conv4_BN)
        x = self.layer(x, self.conv5, self.conv5_BN)
        x = self.layer(x, self.conv6, self.conv6_BN)
        x = x.permute(0, 2, 1, 3).reshape(-1, IN_FEATURES)
        return torch.sigmoid(self.classifier(x))

    def layer(self, x, conv, batch_norm, padding=(0, 0, 31, 32)):
        """一層：補邊 → 捲積 → ReLU → 批次正規化 → 縮小一半"""
        x = F.pad(x, padding)
        x = conv(x)
        x = F.relu(x)
        x = batch_norm(x)
        return F.max_pool2d(x, (2, 1), (2, 1))
