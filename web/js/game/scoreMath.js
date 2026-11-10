// 評分會用到的小計算：平均、標準差、移動平均、中位數…
// 總分（finalScore.js）和技巧偵測（techniques.js）都會用到，所以放在一起。

// 限制在 0~1 之間
export function clamp(value) {
  return Math.max(0, Math.min(1, value));
}

// 平均
export function average(values) {
  if (values.length === 0) {
    return 0;
  }
  let sum = 0;
  for (const value of values) {
    sum += value;
  }
  return sum / values.length;
}

// 標準差：數字們離平均有多遠（越大 = 越不整齊）
export function standardDeviation(values) {
  const mean = average(values);
  let sum = 0;
  for (const value of values) {
    sum += (value - mean) * (value - mean);
  }
  return Math.sqrt(sum / Math.max(1, values.length));
}

// 移動平均：每個數字換成「它前後 radius 個」的平均，把快速的抖動抹平
export function movingAverage(values, radius) {
  const result = [];
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let count = 0;
    for (let k = i - radius; k <= i + radius; k++) {
      if (k >= 0 && k < values.length) {
        sum += values[k];
        count++;
      }
    }
    result.push(sum / count);
  }
  return result;
}

// 中位數：排好之後中間那一個（不會被一兩個怪數字影響）
export function median(values) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = values.slice().sort(function (a, b) {
    return a - b;
  });
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middle];
  }
  return (sorted[middle - 1] + sorted[middle]) / 2;
}
