"""
Mel-Band RoFormer 分人聲 AI 的「網路結構」（只有結構，權重在模型檔裡）。

來源（照抄，算法一模一樣）：
  模型作者 Kimberley Jensen 的 GitHub：https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model
  （commit 25f44ffb55ee3c301281bba21b2d6d311cb69ae2 的 models/mel_band_roformer/mel_band_roformer.py、attend.py）
  這份程式原本是 lucidrains 寫的：https://github.com/lucidrains/BS-RoFormer （MIT 授權）
  論文：Wang, Lu, Won（ByteDance）"Mel-Band RoFormer for Music Source Separation"，https://arxiv.org/abs/2310.01809
  授權聲明全文（lucidrains 的 MIT、librosa 的 ISC）見專案最上層的「第三方授權.md」。

跟原本不一樣的地方（不影響結果）：
  1. 拿掉 beartype：它只是在檢查參數型別，不參與計算（少裝一個套件）
  2. 梅爾濾波器自己算（mel_filter_bank），照抄 librosa 1.0 的 filters.mel：
     librosa 會連帶載入 numba，Windows「智慧型應用程式控制」有時會擋 numba（CREPE 也是這樣處理，見 crepe_runner.py）
  3. 拿掉訓練用的部分（算 loss），只留分人聲用的
  4. 注意力（Attend）直接用 PyTorch 內建的 scaled_dot_product_attention（原本也是用它）

需要的套件：torch、einops、rotary-embedding-torch 0.3.5（作者指定的版本）
"""
from functools import partial

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from einops import rearrange, pack, unpack, reduce, repeat
from rotary_embedding_torch import RotaryEmbedding


# ---------- 梅爾濾波器（照抄 librosa 1.0：filters.mel、hz_to_mel、mel_to_hz，Slaney 版本） ----------

def hz_to_mel(frequencies):
    """赫茲 → 梅爾（1000Hz 以下是直線，以上是對數）"""
    frequencies = np.asanyarray(frequencies, dtype=np.float64)
    f_sp = 200.0 / 3
    mels = frequencies / f_sp
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    if mels.ndim == 0:
        if frequencies >= min_log_hz:
            mels = min_log_mel + np.log(frequencies / min_log_hz) / logstep
        return mels
    high = frequencies >= min_log_hz
    mels[high] = min_log_mel + np.log(frequencies[high] / min_log_hz) / logstep
    return mels


def mel_to_hz(mels):
    """梅爾 → 赫茲"""
    mels = np.asanyarray(mels, dtype=np.float64)
    f_sp = 200.0 / 3
    freqs = f_sp * mels
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    high = mels >= min_log_mel
    freqs[high] = min_log_hz * np.exp(logstep * (mels[high] - min_log_mel))
    return freqs


def mel_filter_bank(sample_rate, n_fft, n_mels):
    """回傳 (n_mels, 1 + n_fft // 2) 的梅爾濾波器（float32），跟 librosa.filters.mel 預設一樣"""
    fmax = float(sample_rate) / 2
    weights = np.zeros((n_mels, 1 + n_fft // 2), dtype=np.float32)
    fft_freqs = np.fft.rfftfreq(n=n_fft, d=1.0 / sample_rate)
    mel_points = np.linspace(hz_to_mel(0.0), hz_to_mel(fmax), n_mels + 2)
    mel_f = mel_to_hz(mel_points)
    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fft_freqs)
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))
    enorm = 2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels])
    weights *= enorm[:, np.newaxis]
    return weights


# ---------- 小工具 ----------

def pack_one(t, pattern):
    return pack([t], pattern)


def unpack_one(t, ps, pattern):
    return unpack(t, ps, pattern)[0]


# ---------- 網路的零件 ----------

class RMSNorm(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.scale = dim ** 0.5
        self.gamma = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        return F.normalize(x, dim=-1) * self.scale * self.gamma


class FeedForward(nn.Module):
    def __init__(self, dim, mult=4, dropout=0.):
        super().__init__()
        dim_inner = int(dim * mult)
        self.net = nn.Sequential(
            RMSNorm(dim),
            nn.Linear(dim, dim_inner),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_inner, dim),
            nn.Dropout(dropout)
        )

    def forward(self, x):
        return self.net(x)


class Attend(nn.Module):
    """注意力的計算（沒有權重）"""
    def __init__(self, dropout=0.):
        super().__init__()
        self.dropout = dropout

    def forward(self, q, k, v):
        dropout = 0.
        if self.training:
            dropout = self.dropout
        return F.scaled_dot_product_attention(q, k, v, dropout_p=dropout)


class Attention(nn.Module):
    def __init__(self, dim, heads=8, dim_head=64, dropout=0., rotary_embed=None):
        super().__init__()
        self.heads = heads
        dim_inner = heads * dim_head
        self.rotary_embed = rotary_embed
        self.attend = Attend(dropout=dropout)
        self.norm = RMSNorm(dim)
        self.to_qkv = nn.Linear(dim, dim_inner * 3, bias=False)
        self.to_gates = nn.Linear(dim, heads)
        self.to_out = nn.Sequential(
            nn.Linear(dim_inner, dim, bias=False),
            nn.Dropout(dropout)
        )

    def forward(self, x):
        x = self.norm(x)
        q, k, v = rearrange(self.to_qkv(x), 'b n (qkv h d) -> qkv b h n d', qkv=3, h=self.heads)
        if self.rotary_embed is not None:
            q = self.rotary_embed.rotate_queries_or_keys(q)
            k = self.rotary_embed.rotate_queries_or_keys(k)
        out = self.attend(q, k, v)
        gates = self.to_gates(x)
        out = out * rearrange(gates, 'b n h -> b h n 1').sigmoid()
        out = rearrange(out, 'b h n d -> b n (h d)')
        return self.to_out(out)


class Transformer(nn.Module):
    def __init__(self, *, dim, depth, dim_head=64, heads=8, attn_dropout=0., ff_dropout=0., ff_mult=4,
                 norm_output=True, rotary_embed=None):
        super().__init__()
        self.layers = nn.ModuleList([])
        for _ in range(depth):
            self.layers.append(nn.ModuleList([
                Attention(dim=dim, dim_head=dim_head, heads=heads, dropout=attn_dropout, rotary_embed=rotary_embed),
                FeedForward(dim=dim, mult=ff_mult, dropout=ff_dropout)
            ]))
        if norm_output:
            self.norm = RMSNorm(dim)
        else:
            self.norm = nn.Identity()

    def forward(self, x):
        for attn, ff in self.layers:
            x = attn(x) + x
            x = ff(x) + x
        return self.norm(x)


class BandSplit(nn.Module):
    """把每個頻帶變成同樣長度的特徵"""
    def __init__(self, dim, dim_inputs):
        super().__init__()
        self.dim_inputs = dim_inputs
        self.to_features = nn.ModuleList([])
        for dim_in in dim_inputs:
            net = nn.Sequential(
                RMSNorm(dim_in),
                nn.Linear(dim_in, dim)
            )
            self.to_features.append(net)

    def forward(self, x):
        x = x.split(self.dim_inputs, dim=-1)
        outs = []
        for split_input, to_feature in zip(x, self.to_features):
            outs.append(to_feature(split_input))
        return torch.stack(outs, dim=-2)


def MLP(dim_in, dim_out, dim_hidden=None, depth=1, activation=nn.Tanh):
    if dim_hidden is None:
        dim_hidden = dim_in
    net = []
    dims = (dim_in, *((dim_hidden,) * depth), dim_out)
    for ind, (layer_dim_in, layer_dim_out) in enumerate(zip(dims[:-1], dims[1:])):
        is_last = ind == (len(dims) - 2)
        net.append(nn.Linear(layer_dim_in, layer_dim_out))
        if is_last:
            continue
        net.append(activation())
    return nn.Sequential(*net)


class MaskEstimator(nn.Module):
    """算出每個頻帶「哪些是人聲」的遮罩"""
    def __init__(self, dim, dim_inputs, depth, mlp_expansion_factor=4):
        super().__init__()
        self.dim_inputs = dim_inputs
        self.to_freqs = nn.ModuleList([])
        dim_hidden = dim * mlp_expansion_factor
        for dim_in in dim_inputs:
            mlp = nn.Sequential(
                MLP(dim, dim_in * 2, dim_hidden=dim_hidden, depth=depth),
                nn.GLU(dim=-1)
            )
            self.to_freqs.append(mlp)

    def forward(self, x):
        x = x.unbind(dim=-2)
        outs = []
        for band_features, mlp in zip(x, self.to_freqs):
            outs.append(mlp(band_features))
        return torch.cat(outs, dim=-1)


# ---------- 整個網路 ----------

class MelBandRoformer(nn.Module):
    def __init__(self, dim, *, depth, stereo=False, num_stems=1, time_transformer_depth=2,
                 freq_transformer_depth=2, num_bands=60, dim_head=64, heads=8, attn_dropout=0.1,
                 ff_dropout=0.1, dim_freqs_in=1025, sample_rate=44100, stft_n_fft=2048,
                 stft_hop_length=512, stft_win_length=2048, stft_normalized=False, mask_estimator_depth=1):
        super().__init__()
        self.stereo = stereo
        if stereo:
            self.audio_channels = 2
        else:
            self.audio_channels = 1
        self.num_stems = num_stems
        self.layers = nn.ModuleList([])

        transformer_kwargs = dict(dim=dim, heads=heads, dim_head=dim_head,
                                  attn_dropout=attn_dropout, ff_dropout=ff_dropout)
        time_rotary_embed = RotaryEmbedding(dim=dim_head)
        freq_rotary_embed = RotaryEmbedding(dim=dim_head)
        for _ in range(depth):
            self.layers.append(nn.ModuleList([
                Transformer(depth=time_transformer_depth, rotary_embed=time_rotary_embed, **transformer_kwargs),
                Transformer(depth=freq_transformer_depth, rotary_embed=freq_rotary_embed, **transformer_kwargs)
            ]))

        self.stft_window_fn = partial(torch.hann_window, stft_win_length)
        self.stft_kwargs = dict(n_fft=stft_n_fft, hop_length=stft_hop_length,
                                win_length=stft_win_length, normalized=stft_normalized)
        freqs = stft_n_fft // 2 + 1

        # 梅爾濾波器：每個頻帶包含哪些頻率（論文第 2 節）
        mel_bank = torch.from_numpy(mel_filter_bank(sample_rate, stft_n_fft, num_bands))
        # 原作者的註解：第一個頻率、最後一個位置強制給值（不然有的電腦會是 0）
        mel_bank[0][0] = 1.
        mel_bank[-1, -1] = 1.
        freqs_per_band = mel_bank > 0
        assert freqs_per_band.any(dim=0).all(), '每個頻率都要被至少一個頻帶包到'

        repeated_freq_indices = repeat(torch.arange(freqs), 'f -> b f', b=num_bands)
        freq_indices = repeated_freq_indices[freqs_per_band]
        if stereo:
            freq_indices = repeat(freq_indices, 'f -> f s', s=2)
            freq_indices = freq_indices * 2 + torch.arange(2)
            freq_indices = rearrange(freq_indices, 'f s -> (f s)')

        self.register_buffer('freq_indices', freq_indices, persistent=False)
        self.register_buffer('freqs_per_band', freqs_per_band, persistent=False)
        num_freqs_per_band = reduce(freqs_per_band, 'b f -> b', 'sum')
        num_bands_per_freq = reduce(freqs_per_band, 'b f -> f', 'sum')
        self.register_buffer('num_freqs_per_band', num_freqs_per_band, persistent=False)
        self.register_buffer('num_bands_per_freq', num_bands_per_freq, persistent=False)

        freqs_per_bands_with_complex = tuple(2 * f * self.audio_channels for f in num_freqs_per_band.tolist())
        self.band_split = BandSplit(dim=dim, dim_inputs=freqs_per_bands_with_complex)
        self.mask_estimators = nn.ModuleList([])
        for _ in range(num_stems):
            self.mask_estimators.append(MaskEstimator(dim=dim, dim_inputs=freqs_per_bands_with_complex,
                                                      depth=mask_estimator_depth))

    def forward(self, raw_audio):
        """raw_audio：(批次, 聲道, 取樣點) → 分出來的人聲，形狀一樣"""
        device = raw_audio.device
        if raw_audio.ndim == 2:
            raw_audio = rearrange(raw_audio, 'b t -> b 1 t')
        batch, channels, raw_audio_length = raw_audio.shape

        # 轉成頻譜
        raw_audio, packed_shape = pack_one(raw_audio, '* t')
        stft_window = self.stft_window_fn(device=device)
        stft_repr = torch.stft(raw_audio, **self.stft_kwargs, window=stft_window, return_complex=True)
        stft_repr = torch.view_as_real(stft_repr)
        stft_repr = unpack_one(stft_repr, packed_shape, '* f t c')
        stft_repr = rearrange(stft_repr, 'b s f t c -> b (f s) t c')

        # 取出每個頻帶的頻率
        batch_arange = torch.arange(batch, device=device)[..., None]
        x = stft_repr[batch_arange, self.freq_indices]
        x = rearrange(x, 'b f t c -> b t (f c)')
        x = self.band_split(x)

        # 時間、頻率輪流做注意力
        for time_transformer, freq_transformer in self.layers:
            x = rearrange(x, 'b t f d -> b f t d')
            x, ps = pack([x], '* t d')
            x = time_transformer(x)
            x, = unpack(x, ps, '* t d')
            x = rearrange(x, 'b f t d -> b t f d')
            x, ps = pack([x], '* f d')
            x = freq_transformer(x)
            x, = unpack(x, ps, '* f d')

        num_stems = len(self.mask_estimators)
        masks = torch.stack([fn(x) for fn in self.mask_estimators], dim=1)
        masks = rearrange(masks, 'b n t (f c) -> b n f t c', c=2)

        # 頻譜乘上遮罩（複數相乘）
        stft_repr = rearrange(stft_repr, 'b f t c -> b 1 f t c')
        stft_repr = torch.view_as_complex(stft_repr)
        masks = torch.view_as_complex(masks)
        masks = masks.type(stft_repr.dtype)

        # 同一個頻率被好幾個頻帶包到：遮罩取平均
        scatter_indices = repeat(self.freq_indices, 'f -> b n f t', b=batch, n=num_stems, t=stft_repr.shape[-1])
        stft_repr_expanded_stems = repeat(stft_repr, 'b 1 ... -> b n ...', n=num_stems)
        masks_summed = torch.zeros_like(stft_repr_expanded_stems).scatter_add_(2, scatter_indices, masks)
        denom = repeat(self.num_bands_per_freq, 'f -> (f r) 1', r=channels)
        masks_averaged = masks_summed / denom.clamp(min=1e-8)
        stft_repr = stft_repr * masks_averaged

        # 轉回聲音
        stft_repr = rearrange(stft_repr, 'b n (f s) t -> (b n s) f t', s=self.audio_channels)
        recon_audio = torch.istft(stft_repr, **self.stft_kwargs, window=stft_window, return_complex=False)
        recon_audio = rearrange(recon_audio, '(b n s) t -> b n s t', b=batch, s=self.audio_channels, n=num_stems)
        if num_stems == 1:
            recon_audio = rearrange(recon_audio, 'b 1 s t -> b s t')
        return recon_audio
