// 裁切範圍：這首歌要從第幾秒唱到第幾秒（唱歌頁、編輯歌詞頁共用）
//   歌曲資料裡的 trim_start（0 = 從頭）、trim_end（0 = 到最後）

export function trimStart(song) {
  return Number(song.trim_start) || 0;
}

// 唱到第幾秒（沒有裁結尾 = 歌曲長度）
export function trimEnd(song, duration) {
  const end = Number(song.trim_end) || 0;
  if (end > 0 && end < duration) {
    return end;
  }
  return duration;
}

// 只留下在範圍裡的音符（一半以上在範圍裡才算）
export function notesInRange(notes, start, end) {
  const result = [];
  for (const note of notes) {
    const inside = Math.min(note.e, end) - Math.max(note.s, start);
    if (inside >= (note.e - note.s) * 0.5) {
      result.push(note);
    }
  }
  return result;
}

// 只留下在範圍裡的歌詞句子（整句都在範圍外的拿掉）
export function lyricsInRange(lyrics, start, end) {
  if (!lyrics || !lyrics.lines) {
    return lyrics;
  }
  const lines = [];
  for (const line of lyrics.lines) {
    if (line.end === undefined || (line.end > start && line.start < end)) {
      lines.push(line);
    }
  }
  return { synced: lyrics.synced, lang: lyrics.lang, lines: lines };
}
