// 選了一份歌詞時，空白的歌名、歌手用那份歌詞上的補上（就不會出現「未知歌手」）
//   不是空白的一律不動：你自己打的字、YouTube 自動讀到填在欄位裡的，都不會被換掉
//
//   fillNames(歌名, 歌手, 那份歌詞) → { title, artist }（補好的）
//   changedNames(歌曲, 那份歌詞)    → 要改的 { title, artist }（只放有變的）；都不用改回傳 null

export function fillNames(title, artist, item) {
  const result = { title: title, artist: artist };
  if (!item) {
    return result;
  }
  if (title.trim() === '' && item.title) {
    result.title = item.title;
  }
  if (artist.trim() === '' && item.artist) {
    result.artist = item.artist;
  }
  return result;
}

export function changedNames(song, item) {
  const title = song.title || '';
  const artist = song.artist || '';
  const names = fillNames(title, artist, item);
  const changes = {};
  let count = 0;
  if (names.title !== title) {
    changes.title = names.title;
    count++;
  }
  if (names.artist !== artist) {
    changes.artist = names.artist;
    count++;
  }
  if (count === 0) {
    return null;
  }
  return changes;
}
