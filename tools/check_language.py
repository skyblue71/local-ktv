"""
檢查介面的英文有沒有漏翻。

程式裡的字用 t('中文') 包起來（web\\js\\i18n.js），英文放在 web\\js\\lang\\en\\ 的對照表。
這個工具會列出：
  1. 漏翻：程式裡有 t('…')，對照表裡沒有
  2. 沒用到：對照表裡有，程式裡沒有（伺服器的字 server.js 不算，那是伺服器傳來的）
  3. 代入的名字對不上：中文有 {title}，英文沒有（或相反）
  4. 同一個中文在兩個檔案裡翻得不一樣
  5. 可能沒包到的字：程式裡有中文字串，但那一行沒有 t( 或 tServer(（只是提醒，要自己看）

執行方式（在專案資料夾底下；只讀檔案，不改任何東西）：
  .venv\\Scripts\\python -X utf8 tools\\check_language.py
  .venv\\Scripts\\python -X utf8 tools\\check_language.py lyricsPage.js chartPage.js   ← 只看這幾個檔案
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, "web", "js")
LANG_DIR = os.path.join(JS_DIR, "lang")
TABLE_DIR = os.path.join(LANG_DIR, "en")

# 單引號的字串：'…'（裡面可以有 \' 這種跳脫）
STRING = r"'((?:[^'\\\n]|\\.)*)'"
T_CALL = re.compile(r"\bt\(\s*" + STRING)
ENTRY = re.compile(r"^\s*" + STRING + r"\s*:\s*" + STRING + r"\s*,?\s*$")
ANY_STRING = re.compile(STRING)
# 這一行有沒有用到 t( 或 tServer(（前面要是字的開頭，encodeURIComponent( 這種不算）
WRAPPED = re.compile(r"\bt\(|\btServer\(")
CHINESE = re.compile(r"[一-鿿]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# 這個檔案裡的中文不是給使用者看的字，不用包
SKIP_FILES = ["i18n.js"]


def unescape(text):
    """把程式裡寫的 \\n、\\' 變回真正的字"""
    result = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following == "n":
                result += "\n"
            else:
                result += following
            index += 2
        else:
            result += char
            index += 1
    return result


def strip_comment(line):
    """把一行後面的 // 註解拿掉（字串裡的 // 不算，例如網址）"""
    in_string = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\":
            index += 2
            continue
        if char == "'":
            in_string = not in_string
        if not in_string and line[index:index + 2] == "//":
            return line[:index]
        index += 1
    return line


def read_lines(path):
    with open(path, encoding="utf8") as file:
        return file.read().split("\n")


def load_tables():
    """讀全部對照表：{檔名: {中文: 英文}}"""
    tables = {}
    for name in sorted(os.listdir(TABLE_DIR)):
        if not name.endswith(".js"):
            continue
        entries = {}
        for line in read_lines(os.path.join(TABLE_DIR, name)):
            match = ENTRY.match(strip_comment(line))
            if match:
                entries[unescape(match.group(1))] = unescape(match.group(2))
        tables[name] = entries
    return tables


def source_files(only):
    """要檢查的程式檔（不含對照表）"""
    files = []
    for folder, _, names in os.walk(JS_DIR):
        if folder.startswith(LANG_DIR):
            continue
        for name in sorted(names):
            if not name.endswith(".js") or name in SKIP_FILES:
                continue
            if only and name not in only:
                continue
            files.append(os.path.join(folder, name))
    return files


def main():
    only = sys.argv[1:]
    tables = load_tables()

    merged = {}
    conflicts = []
    for name, entries in tables.items():
        for key, value in entries.items():
            if key in merged and merged[key][1] != value:
                conflicts.append((key, merged[key][0], name))
            merged[key] = (name, value)

    used = set()
    missing = []
    unwrapped = []
    for path in source_files(only):
        short = os.path.relpath(path, JS_DIR)
        in_block_comment = False
        for number, raw in enumerate(read_lines(path), 1):
            line = raw
            if in_block_comment:
                if "*/" in line:
                    in_block_comment = False
                continue
            if line.strip().startswith("/*") and "*/" not in line:
                in_block_comment = True
                continue
            line = strip_comment(line)
            for match in T_CALL.finditer(line):
                key = unescape(match.group(1))
                used.add(key)
                if key not in merged:
                    missing.append((short, number, key))
            if not WRAPPED.search(line):
                for match in ANY_STRING.finditer(line):
                    if CHINESE.search(match.group(1)):
                        unwrapped.append((short, number, match.group(1)))

    bad_names = []
    for key, (name, value) in merged.items():
        if sorted(PLACEHOLDER.findall(key)) != sorted(PLACEHOLDER.findall(value)):
            bad_names.append((name, key, value))

    unused = []
    if not only:
        for key, (name, _) in merged.items():
            if key not in used and name != "server.js":
                unused.append((name, key))

    def show(title, items, format_item):
        print("\n%s：%d" % (title, len(items)))
        for item in items:
            print("  " + format_item(item))

    def one_line(text):
        return text.replace("\n", "\\n")

    print("對照表共 %d 筆，程式裡用到 %d 筆" % (len(merged), len(used)))
    show("1. 漏翻", missing, lambda item: "%s:%d  %s" % (item[0], item[1], one_line(item[2])))
    show("2. 沒用到", unused, lambda item: "%s  %s" % (item[0], one_line(item[1])))
    show("3. 代入的名字對不上", bad_names, lambda item: "%s  %s → %s" % (item[0], one_line(item[1]), one_line(item[2])))
    show("4. 兩個檔案翻得不一樣", conflicts, lambda item: "%s（%s 和 %s）" % (one_line(item[0]), item[1], item[2]))
    show("5. 可能沒包到的字（提醒）", unwrapped, lambda item: "%s:%d  %s" % (item[0], item[1], one_line(item[2])))

    if missing or bad_names or conflicts:
        sys.exit(1)


main()
