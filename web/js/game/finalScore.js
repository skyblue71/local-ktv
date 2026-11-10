// 唱完之後的「總分」計算。
// 五個項目（0~100），再按比例加起來：
//   音準   55%  每個音符唱對的比例
//   節奏   15%  開口的時間準不準
//   穩定   10%  長音有沒有飄
//   表現力 10%  顫音、音量起伏
//   完成度 10%  有唱到的音符比例
// 最後再加上「技巧加分」（滑音、轉音、尾音下滑，最多 +3 分），總分最高 100。

import { average, clamp, movingAverage, standardDeviation } from './scoreMath.js';
import { countTechniques, techniqueBonus } from './techniques.js';

// 偵測顫音：音高有規律地上下襬動，每秒 4~8.5 次
function hasVibrato(note) {
  if (note.samples.length < 40) {
    return false;
  }
  const values = [];
  for (const sample of note.samples) {
    values.push(sample.d);
  }
  const slow = movingAverage(values, 15);
  const wave = [];
  for (let i = 0; i < values.length; i++) {
    wave.push(values[i] - slow[i]);
  }
  // 數穿過 0 的次數
  let crossings = 0;
  let lastSign = 0;
  for (const value of wave) {
    if (Math.abs(value) < 0.03) {
      continue;
    }
    const sign = value > 0 ? 1 : -1;
    if (lastSign !== 0 && sign !== lastSign) {
      crossings++;
    }
    lastSign = sign;
  }
  const seconds = note.samples[note.samples.length - 1].t - note.samples[0].t;
  if (seconds <= 0) {
    return false;
  }
  const rate = crossings / 2 / seconds;
  const depth = standardDeviation(wave) * 1.41;
  return rate >= 4 && rate <= 8.5 && depth >= 0.1 && depth <= 1.2;
}

// 穩定度只看「長音」：0.4 秒以上、至少 20 筆音高
const STABLE_MIN_DURATION = 0.4;
const STABLE_MIN_SAMPLES = 20;
// 跟原唱（或音符）差超過 1.5 個半音的瞬間，多半是偵測器聽錯了，穩定度不算它
// （這些瞬間在「音準」那一項已經扣過分了，不用再扣一次）
const STABLE_ERROR_LIMIT = 1.5;

// 一個長音的穩定度（0~1）；太短的音符回傳 null，代表不算
//   有原唱曲線的話看「你跟原唱的差距」（r），原唱本來就有的滑音、轉音不扣分；沒有的話看「你跟音符的差距」（d）
//   先用移動平均抹掉顫音，再看剩下的起伏有多大：起伏越大 = 越不穩
function noteStability(note) {
  if (note.e - note.s < STABLE_MIN_DURATION) {
    return null;
  }
  const values = [];
  for (const sample of note.samples) {
    let value = sample.d;
    if (sample.r !== null && sample.r !== undefined) {
      value = sample.r;
    }
    if (Math.abs(value) <= STABLE_ERROR_LIMIT) {
      values.push(value);
    }
  }
  if (values.length < STABLE_MIN_SAMPLES) {
    return null;
  }
  const drift = standardDeviation(movingAverage(values, 7));
  // 起伏 0.1 半音以內滿分，0.6 半音以上零分
  return clamp(1 - (drift - 0.1) / 0.5);
}

export function calculateFinalScore(scorer) {
  const notes = [];
  for (const note of scorer.notes) {
    if (!note.skipped) {
      notes.push(note);
    }
  }

  const counts = { PERFECT: 0, GREAT: 0, GOOD: 0, MISS: 0 };
  let totalDuration = 0;
  let earned = 0;
  let completed = 0;
  const rhythmScores = [];
  const stabilityScores = [];
  const loudnessList = [];
  let longNotes = 0;
  let vibratoCount = 0;

  let hasLongNote = false;   // 這首歌有沒有「長音」（穩定度要用）

  for (const note of notes) {
    const duration = note.e - note.s;
    const isHit = note.grade !== 'MISS';   // 這個音符有沒有唱對（PERFECT、GREAT、GOOD）
    if (counts[note.grade] !== undefined) {
      counts[note.grade]++;
    }
    totalDuration += duration;
    earned += note.ratio * duration;

    // 完成度：有唱對、而且至少唱了 30% 的時間
    //（只算唱對的：一直出聲但音都不對，不算「唱完」）
    if (isHit && note.sung >= duration * 0.3) {
      completed++;
    }

    // 節奏：第一次唱對的時間，跟音符開始的時間差多少
    if (note.firstHit !== null) {
      const delay = Math.abs(note.firstHit - note.s);
      rhythmScores.push(clamp(1 - (delay - 0.06) / 0.3));
    } else {
      rhythmScores.push(0);
    }

    // 穩定度：唱對的長音有沒有飄
    //（只算唱對的：一直哼同一個音很「穩」，但音不對，不算穩定）
    if (duration >= STABLE_MIN_DURATION) {
      hasLongNote = true;
    }
    if (isHit) {
      const stability = noteStability(note);
      if (stability !== null) {
        stabilityScores.push(stability);
      }
    }

    // 顫音：0.6 秒以上的長音
    if (duration >= 0.6) {
      longNotes++;
      if (hasVibrato(note)) {
        vibratoCount++;
      }
    }

    // 音量起伏：每個音符的平均音量（dB）
    if (note.samples.length > 0) {
      const meanLoudness = note.loudness / note.samples.length;
      loudnessList.push(20 * Math.log10(meanLoudness + 1e-6));
    }
  }

  const pitch = totalDuration > 0 ? earned / totalDuration * 100 : 0;
  const rhythm = average(rhythmScores) * 100;
  // 穩定度：唱對的長音平均；有長音卻一個都沒唱對 → 0；整首歌沒有長音 → 給 80（沒辦法評）
  let stability = 80;
  if (stabilityScores.length > 0) {
    stability = average(stabilityScores) * 100;
  } else if (hasLongNote) {
    stability = 0;
  }
  const vibratoScore = clamp(vibratoCount / Math.max(2, longNotes * 0.4));
  // 音量起伏：每個音符音量的差異（dB），差 0.5 以下算平淡，4.5 以上算很有起伏
  const dynamicsScore = clamp((standardDeviation(loudnessList) - 0.5) / 4);
  const expression = (0.2 + 0.5 * vibratoScore + 0.3 * dynamicsScore) * 100;
  const completion = notes.length > 0 ? completed / notes.length * 100 : 0;

  const raw = pitch * 0.55 + rhythm * 0.15 + stability * 0.1 + expression * 0.1 + completion * 0.1;
  // 稍微調整曲線，讓分數感覺比較自然（唱得不錯的人大約 80~90 分）
  const baseTotal = 100 * Math.pow(raw / 100, 0.8);

  // 技巧加分（只算唱對的音符），總分最高 100
  const techniques = countTechniques(scorer.notes);
  const bonus = techniqueBonus(techniques);
  const total = Math.min(100, baseTotal + bonus);

  const result = {
    total: Math.round(total * 1000) / 1000,
    techniques: techniques,
    bonus: Math.round(bonus * 10) / 10,
    pitch: Math.round(pitch * 10) / 10,
    rhythm: Math.round(rhythm * 10) / 10,
    stability: Math.round(stability * 10) / 10,
    expression: Math.round(expression * 10) / 10,
    completion: Math.round(completion * 10) / 10,
    counts: counts,
    maxCombo: scorer.maxCombo,
    vibratoCount: vibratoCount,
    vibratoScore: vibratoScore,
    dynamicsScore: dynamicsScore,
    noteCount: notes.length,
  };
  result.rank = getRank(result.total);
  result.comment = makeComment(result);
  return result;
}

// 表現力的建議：看是「顫音」還是「音量起伏」比較不夠
function expressionTip(result) {
  if (result.vibratoScore < result.dynamicsScore) {
    return '試著在長音的尾巴加一點顫音，表現力會加分。';
  }
  return '試著讓音量有強有弱（副歌大聲、主歌輕柔），表現力會加分。';
}

function getRank(total) {
  if (total >= 95) return 'SSS';
  if (total >= 90) return 'SS';
  if (total >= 85) return 'S';
  if (total >= 80) return 'A';
  if (total >= 70) return 'B';
  if (total >= 60) return 'C';
  return 'D';
}

function makeComment(result) {
  let first = '';
  if (result.total >= 95) {
    first = '完美！簡直就是原唱本人！';
  } else if (result.total >= 90) {
    first = '太厲害了！音準非常穩。';
  } else if (result.total >= 80) {
    first = '唱得很好！';
  } else if (result.total >= 70) {
    first = '不錯哦，再多練幾次會更好。';
  } else if (result.total >= 60) {
    first = '及格了！';
  } else {
    first = '加油！先多聽幾次原唱熟悉旋律吧。';
  }

  // 找出最弱的項目給建議
  const items = [
    { value: result.pitch, tip: '音準還能更好：可以把「導唱」音量調大，跟著原唱練習。' },
    { value: result.rhythm, tip: '開口的時間有點偏：如果一直被判慢，可以在設定裡調大「延遲補償」。' },
    { value: result.stability, tip: '長音試著穩住，不要飄。' },
    { value: result.expression, tip: expressionTip(result) },
    { value: result.completion, tip: '有些地方沒唱到，試著每一句都開口唱。' },
  ];
  let weakest = items[0];
  for (const item of items) {
    if (item.value < weakest.value) {
      weakest = item;
    }
  }
  if (weakest.value >= 90) {
    return first;
  }
  return first + weakest.tip;
}
