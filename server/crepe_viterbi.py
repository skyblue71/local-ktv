"""
Viterbi 解碼：從「每一幀 360 格音高的機率」找出一條最合理、不會亂跳的音高路線。

算法照 librosa.sequence.viterbi（torchcrepe 原本就是用它），自己寫一份，
因為 librosa 要靠 numba，numba 有時會被 Windows「智慧型應用程式控制」擋。
用 torch 算：有顯示卡就用顯示卡，很快。
librosa 是 ISC 授權，聲明全文見專案最上層的「第三方授權.md」。
"""
import math

import numpy as np
import torch

from server.crepe_model import PITCH_BINS

# 相鄰兩幀，音高最多跳 11 格（220 音分）；跳越近越容易（跟 torchcrepe 一樣）
JUMP_WIDTH = 12
# 很小的數，避免 log(0)（跟 librosa 一樣用 float32 能表示的最小正數）
TINY = float(np.finfo(np.float32).tiny)


def make_log_transition(device):
    """跳格機率表取 log：第 k 列第 j 欄 = 從第 k 格跳到第 j 格的機率"""
    index = np.arange(PITCH_BINS)
    distance = np.abs(index[None, :] - index[:, None])
    transition = np.maximum(JUMP_WIDTH - distance, 0).astype(np.float64)
    transition = transition / transition.sum(axis=1, keepdims=True)
    log_transition = np.log(transition + TINY)
    return torch.tensor(log_transition, dtype=torch.float64, device=device)


def viterbi_bins(chances):
    """chances：(360, 幀數) 的 torch 張量，每一幀 360 格加起來是 1。
    回傳每一幀選第幾格（numpy 整數陣列）"""
    device = chances.device
    frame_count = chances.shape[1]
    log_chance = torch.log(chances + TINY).double().T      # (幀數, 360)
    log_transition = make_log_transition(device)
    log_start = math.log(1.0 / PITCH_BINS + TINY)          # 一開始每一格機會一樣

    # 往前走：記住「走到這一格最好的分數」和「是從哪一格來的」
    score = log_chance[0] + log_start
    came_from = torch.zeros((frame_count, PITCH_BINS), dtype=torch.int64, device=device)
    for t in range(1, frame_count):
        # cost[k, j]：上一幀在 k、這一幀到 j 的總分
        cost = score[:, None] + log_transition
        best_cost, best_from = torch.max(cost, dim=0)
        came_from[t] = best_from
        score = log_chance[t] + best_cost

    # 從最後一幀往回走，找出整條路線
    came_from = came_from.cpu().numpy()
    path = np.zeros(frame_count, dtype=np.int64)
    path[-1] = int(torch.argmax(score))
    for t in range(frame_count - 2, -1, -1):
        path[t] = came_from[t + 1, path[t + 1]]
    return path
