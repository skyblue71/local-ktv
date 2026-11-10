// 音高編號 ↔ 音名、頻率 的換算

const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

// 頻率(Hz) → 音高編號（69 = A4 = 440Hz）
export function frequencyToMidi(frequency) {
  return 69 + 12 * Math.log2(frequency / 440);
}

// 音高編號 → 音名，例如 60 → "C4"
export function midiToName(midi) {
  const rounded = Math.round(midi);
  const name = NAMES[((rounded % 12) + 12) % 12];
  const octave = Math.floor(rounded / 12) - 1;
  return name + octave;
}
