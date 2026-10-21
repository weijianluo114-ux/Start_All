# -*- coding: utf-8 -*-
"""
LaunchForge 多语言层（v1.14.0 起）。

设计约定
--------
· 语言代码用 BCP 47：`zh-Hans` / `zh-Hant` / `en` / `ja`；简体中文是源语言。
· 键名点分层级（`main.add_program`），一眼能看出归属，避免同名字符串串味。
· 任何键缺译文都回落到简体中文，再回落到键名本身——缺一条译文不会让界面崩，
  只会露出中文（可接受的降级），因此新增文案时可以先只写中文。
· 只有**界面文案**进这张表；日志与注册表值名不进（日志是排障用的开发者信息，
  翻译它反而让搜索报错变难）。

用法
----
    from lf_i18n import Lang, t
    Lang.set('en')              # 只改语言码，界面刷新由调用方负责
    label.setText(t('main.log'))
    label.setText(t('msg.path_missing', path=p))
"""

# ------------------------- 语言清单 -------------------------
#
# `name` 一律用**该语言自己的写法**（English 而不是"英语"）：
# 语言选择器里让用户找到母语，靠的是母语写法，不是当前界面的语言。

LANGUAGES = (
    {'code': 'zh-Hans', 'name': '简体中文', 'short': '简'},
    {'code': 'en', 'name': 'English', 'short': 'EN'},
    {'code': 'ja', 'name': '日本語', 'short': 'あ'},
    {'code': 'zh-Hant', 'name': '繁體中文', 'short': '繁'},
)

LANGUAGE_CODES = tuple(item['code'] for item in LANGUAGES)
DEFAULT_LANGUAGE = 'zh-Hans'


def language_name(code):
    for item in LANGUAGES:
        if item['code'] == code:
            return item['name']
    return LANGUAGES[0]['name']


# ------------------------- 文案表 -------------------------
#
# 结构：键 → {语言码: 文案}。示例：
#   'main.log': {'zh-Hans': '日志', 'en': 'Logs', 'ja': 'ログ', 'zh-Hant': '日誌'}
#
# 占位符统一用 `{}` + 关键字，走 str.format；文案里出现的 `%USERPROFILE%`
# 这类百分号只是普通字符，不会被当成格式符。

STRINGS = {
    # ---- 通用 / 标题 ----
    'app.title': {
        'zh-Hans': '一键多启', 'en': 'LaunchForge',
        'ja': 'LaunchForge', 'zh-Hant': '一鍵多啟',
    },
    'app.settings_title': {
        'zh-Hans': '一键多启 · 设置', 'en': 'LaunchForge · Settings',
        'ja': 'LaunchForge · 設定', 'zh-Hant': '一鍵多啟 · 設定',
    },

    # ---- 设置面板 ----
    'settings.title': {
        'zh-Hans': '设置', 'en': 'Settings',
        'ja': '設定', 'zh-Hant': '設定',
    },
    'settings.language': {
        'zh-Hans': '界面语言', 'en': 'Language',
        'ja': '表示言語', 'zh-Hant': '介面語言',
    },
    'settings.language_tip': {
        'zh-Hans': '切换后立即生效，并记住到下次启动',
        'en': 'Applies immediately and is remembered next time',
        'ja': '切り替えるとすぐ反映され、次回起動時も保持されます',
        'zh-Hant': '切換後立即生效，並記住到下次啟動',
    },
    'settings.font_family': {
        'zh-Hans': '字体搭配', 'en': 'Font family',
        'ja': 'フォント', 'zh-Hant': '字型搭配',
    },
    'settings.font_size': {
        'zh-Hans': '字号', 'en': 'Text size',
        'ja': '文字サイズ', 'zh-Hant': '字級',
    },
    'settings.preview': {
        'zh-Hans': '一键多启 · LaunchForge 2026', 'en': 'LaunchForge 2026',
        'ja': 'LaunchForge 2026', 'zh-Hant': '一鍵多啟 · LaunchForge 2026',
    },
    'settings.close': {
        'zh-Hans': '关闭', 'en': 'Close',
        'ja': '閉じる', 'zh-Hant': '關閉',
    },
    'settings.autostart_title': {
        'zh-Hans': '开机自启动', 'en': 'Launch at sign-in',
        'ja': 'スタートアップに登録', 'zh-Hant': '開機時自動啟動',
    },
    'settings.autostart_desc': {
        'zh-Hans': '登录 Windows 后自动打开启动器。\n不会自动启动列表内的条目。',
        'en': 'Open the launcher after you sign in to Windows.\nItems in the list are not started automatically.',
        'ja': 'Windows にサインインしたらランチャーを開きます。\nリスト内の項目は自動起動しません。',
        'zh-Hant': '登入 Windows 後自動開啟啟動器。\n不會自動啟動清單內的項目。',
    },
    'settings.font_available': {
        'zh-Hans': '· 本机可用', 'en': '· available on this PC',
        'ja': '· この PC で使用可能', 'zh-Hant': '· 本機可用',
    },
    'settings.font_missing': {
        'zh-Hans': '· 未安装，回退到 {name}', 'en': '· not installed, falls back to {name}',
        'ja': '· 未インストール、{name} で代替', 'zh-Hant': '· 未安裝，回退到 {name}',
    },
    'settings.hint_legacy': {
        'zh-Hans': '注册表指向旧路径，下次启动会自动改写',
        'en': 'The registry entry points to an old path and will be fixed on next launch',
        'ja': 'レジストリが古いパスを指しています。次回起動時に自動で書き換えます',
        'zh-Hant': '登錄檔指向舊路徑，下次啟動會自動改寫',
    },
    'settings.hint_enabled': {
        'zh-Hans': '已启用 · 登录后运行 {name}', 'en': 'On · runs {name} after sign-in',
        'ja': '有効 · サインイン後に {name} を実行', 'zh-Hant': '已啟用 · 登入後執行 {name}',
    },
    'settings.hint_disabled': {
        'zh-Hans': '未启用 · 开启后随 Windows 登录启动',
        'en': 'Off · turn on to start with Windows',
        'ja': '無効 · オンにすると Windows と同時に起動します',
        'zh-Hant': '未啟用 · 開啟後隨 Windows 登入啟動',
    },
    'settings.command_tip': {
        'zh-Hans': '启动命令：\n{}', 'en': 'Launch command:\n{}',
        'ja': '起動コマンド：\n{}', 'zh-Hant': '啟動命令：\n{}',
    },
    'settings.failed_title': {
        'zh-Hans': '设置未生效', 'en': 'Setting not applied',
        'ja': '設定が反映されませんでした', 'zh-Hant': '設定未生效',
    },
    'settings.failed_body': {
        'zh-Hans': '无法{action}开机自启动：\n\n{error}\n\n'
                   '常见原因：注册表被安全软件拦截、或用户没有当前账户的写入权限。',
        'en': 'Could not turn launch-at-sign-in {action}:\n\n{error}\n\n'
              'Common causes: security software blocking registry writes, '
              'or your account lacking write permission.',
        'ja': 'スタートアップ登録を{action}できませんでした：\n\n{error}\n\n'
              'よくある原因：セキュリティソフトによるレジストリ書き込みの遮断、'
              'または現在のアカウントに書き込み権限がない。',
        'zh-Hant': '無法{action}開機時自動啟動：\n\n{error}\n\n'
                   '常見原因：登錄檔被安全軟體攔截、或使用者沒有目前帳戶的寫入權限。',
    },
    'settings.failed_on': {
        'zh-Hans': '开启', 'en': 'on', 'ja': '有効に', 'zh-Hant': '開啟',
    },
    'settings.failed_off': {
        'zh-Hans': '关闭', 'en': 'off', 'ja': '無効に', 'zh-Hant': '關閉',
    },
    'settings.language_changed': {
        'zh-Hans': '界面语言已切换为 {name}',
        'en': 'Interface language switched to {name}',
        'ja': '表示言語を {name} に切り替えました',
        'zh-Hant': '介面語言已切換為 {name}',
    },

    'settings.size_tip': {
        'zh-Hans': '界面字号 {}–{} px', 'en': 'Interface text size {}–{} px',
        'ja': '画面の文字サイズ {}–{} px', 'zh-Hant': '介面字級 {}–{} px',
    },
    'settings.no_registry': {
        'zh-Hans': '当前系统不支持注册表自启动项',
        'en': 'This system does not support registry startup entries',
        'ja': 'このシステムはレジストリのスタートアップ項目に対応していません',
        'zh-Hant': '目前系統不支援登錄檔開機啟動項目',
    },

    # ---- 窗口标识（关闭确认里用） ----
    'window.label_more': {
        'zh-Hans': ' 等', 'en': ' etc.', 'ja': ' ほか', 'zh-Hant': ' 等',
    },
    'window.label_tabs': {
        'zh-Hans': '（{count} 个标签）', 'en': ' ({count} tabs)',
        'ja': '（{count} タブ）', 'zh-Hant': '（{count} 個分頁）',
    },
    'window.label_unnamed': {
        'zh-Hans': '窗口 {hwnd}', 'en': 'Window {hwnd}',
        'ja': 'ウィンドウ {hwnd}', 'zh-Hant': '視窗 {hwnd}',
    },

    # ---- 字体搭配 ----
    'font.classic.name': {
        'zh-Hans': '雅黑 × 思源', 'en': 'YaHei × Noto',
        'ja': '雅黑 × Noto', 'zh-Hant': '雅黑 × 思源',
    },
    'font.classic.note': {
        'zh-Hans': '标题思源、正文雅黑 · 当前默认观感',
        'en': 'Noto Sans headings, YaHei body · the default look',
        'ja': '見出しは Noto Sans、本文は雅黑 · 既定の見た目',
        'zh-Hant': '標題思源、正文雅黑 · 目前預設外觀',
    },
    'font.yahei.name': {
        'zh-Hans': '雅黑经典', 'en': 'YaHei classic',
        'ja': '雅黑クラシック', 'zh-Hant': '雅黑經典',
    },
    'font.yahei.note': {
        'zh-Hans': '只用系统自带雅黑 · 最稳妥，不依赖额外安装',
        'en': 'System YaHei only · safest, installs nothing',
        'ja': 'システム標準の雅黑のみ · 追加インストール不要で最も安全',
        'zh-Hant': '只用系統內建雅黑 · 最穩定，不需額外安裝',
    },
    'font.dengxian.name': {
        'zh-Hans': '等线清朗', 'en': 'DengXian light',
        'ja': '等線', 'zh-Hant': '等線清朗',
    },
    'font.dengxian.note': {
        'zh-Hans': '字形偏瘦、字面更高 · 同字号下更透气',
        'en': 'Slim strokes, taller glyphs · more airy at the same size',
        'ja': '線が細く字面が高い · 同じサイズでもゆったり見えます',
        'zh-Hant': '字形偏瘦、字面較高 · 同字級下更透氣',
    },
    'font.split.name': {
        'zh-Hans': '中英分排', 'en': 'Latin + CJK split',
        'ja': '欧文と中国語を分ける', 'zh-Hant': '中英分排',
    },
    'font.split.note': {
        'zh-Hans': '西文数字用 Segoe UI，中文回落雅黑 · 数字更精神',
        'en': 'Segoe UI for Latin letters and digits, YaHei for Chinese · crisper numbers',
        'ja': '欧文と数字は Segoe UI、中国語は雅黑 · 数字が引き締まります',
        'zh-Hant': '西文數字用 Segoe UI，中文回落雅黑 · 數字更精神',
    },
    'font.serif.name': {
        'zh-Hans': '书卷衬线', 'en': 'Bookish serif',
        'ja': '書籍風セリフ', 'zh-Hant': '書卷襯線',
    },
    'font.serif.note': {
        'zh-Hans': '标题衬线、正文雅黑 · 气质更文气',
        'en': 'Serif headings, YaHei body · a more literary feel',
        'ja': '見出しはセリフ、本文は雅黑 · 文語的な雰囲気',
        'zh-Hant': '標題襯線、正文雅黑 · 氣質更文氣',
    },

    # ---- 主界面 ----
    'main.preset': {
        'zh-Hans': '预设方案', 'en': 'Preset',
        'ja': 'プリセット', 'zh-Hant': '預設方案',
    },
    'main.new': {
        'zh-Hans': '新建', 'en': 'New', 'ja': '新規', 'zh-Hant': '新增',
    },
    'main.delete': {
        'zh-Hans': '删除', 'en': 'Delete', 'ja': '削除', 'zh-Hant': '刪除',
    },
    'main.add_program': {
        'zh-Hans': '添加程序', 'en': 'Add program',
        'ja': 'プログラムを追加', 'zh-Hant': '新增程式',
    },
    'main.add_folder': {
        'zh-Hans': '添加文件夹', 'en': 'Add folder',
        'ja': 'フォルダーを追加', 'zh-Hant': '新增資料夾',
    },
    'main.add_path': {
        'zh-Hans': '输入路径', 'en': 'Enter path',
        'ja': 'パスを入力', 'zh-Hant': '輸入路徑',
    },
    'main.remove_selected': {
        'zh-Hans': '删除选中', 'en': 'Remove selected',
        'ja': '選択を削除', 'zh-Hant': '刪除選取',
    },
    'main.log': {
        'zh-Hans': '日志', 'en': 'Logs', 'ja': 'ログ', 'zh-Hant': '日誌',
    },
    'main.settings': {
        'zh-Hans': '设置', 'en': 'Settings', 'ja': '設定', 'zh-Hant': '設定',
    },
    'main.taiji_tip': {
        'zh-Hans': '左（绿）：一键启动当前预设　|　右（红）：关闭列表内的程序与文件夹窗口',
        'en': 'Left (green): start everything in this preset  |  '
              'Right (red): close the programs and folder windows in the list',
        'ja': '左（緑）：このプリセットを一括起動　|　'
              '右（赤）：リスト内のプログラムとフォルダーウィンドウを閉じる',
        'zh-Hant': '左（綠）：一鍵啟動目前預設　|　右（紅）：關閉清單內的程式與資料夾視窗',
    },
    'main.taiji_run': {
        'zh-Hans': '启动', 'en': 'START', 'ja': '起動', 'zh-Hant': '啟動',
    },
    'main.taiji_close': {
        'zh-Hans': '关闭', 'en': 'CLOSE', 'ja': '終了', 'zh-Hant': '關閉',
    },
    'main.default_preset': {
        'zh-Hans': '默认方案', 'en': 'Default', 'ja': '既定', 'zh-Hant': '預設方案',
    },

    # ---- 列表 ----
    'list.kind_dir': {
        'zh-Hans': '文件夹', 'en': 'Folder', 'ja': 'フォルダー', 'zh-Hant': '資料夾',
    },
    'list.kind_file': {
        'zh-Hans': '文件', 'en': 'File', 'ja': 'ファイル', 'zh-Hant': '檔案',
    },
    'list.kind_missing': {
        'zh-Hans': '路径不存在，启动时将被跳过',
        'en': 'Path not found — skipped when launching',
        'ja': 'パスが存在しません（起動時にスキップ）',
        'zh-Hant': '路徑不存在，啟動時將被略過',
    },

    # ---- 通用消息 ----
    'msg.ok': {'zh-Hans': '确定', 'en': 'OK', 'ja': 'OK', 'zh-Hant': '確定'},
    'msg.error': {'zh-Hans': '错误', 'en': 'Error', 'ja': 'エラー', 'zh-Hant': '錯誤'},
    'msg.notice': {'zh-Hans': '提示', 'en': 'Notice', 'ja': 'お知らせ', 'zh-Hant': '提示'},
    'msg.yes': {'zh-Hans': '是', 'en': 'Yes', 'ja': 'はい', 'zh-Hant': '是'},
    'msg.no': {'zh-Hans': '否', 'en': 'No', 'ja': 'いいえ', 'zh-Hant': '否'},

    # ---- 主界面消息 ----
    'msg.open_failed': {
        'zh-Hans': '无法打开', 'en': 'Cannot open', 'ja': '開けません', 'zh-Hant': '無法開啟',
    },
    'msg.path_missing': {
        'zh-Hans': '该路径已不存在：\n{path}', 'en': 'This path no longer exists:\n{path}',
        'ja': 'このパスは存在しません：\n{path}', 'zh-Hant': '該路徑已不存在：\n{path}',
    },
    'msg.launch_failed': {
        'zh-Hans': '启动失败', 'en': 'Launch failed', 'ja': '起動に失敗', 'zh-Hant': '啟動失敗',
    },
    'msg.new_preset_title': {
        'zh-Hans': '新建预设', 'en': 'New preset', 'ja': 'プリセットの新規作成',
        'zh-Hant': '新增預設',
    },
    'msg.new_preset_prompt': {
        'zh-Hans': '请输入预设名称：', 'en': 'Preset name:', 'ja': 'プリセット名を入力：',
        'zh-Hant': '請輸入預設名稱：',
    },
    'msg.preset_exists': {
        'zh-Hans': '预设名称已存在！', 'en': 'That preset name already exists.',
        'ja': '同じ名前のプリセットがすでにあります。',
        'zh-Hant': '預設名稱已存在！',
    },
    'msg.keep_one_preset': {
        'zh-Hans': '至少保留一个预设方案。', 'en': 'Keep at least one preset.',
        'ja': 'プリセットは最低 1 つ必要です。', 'zh-Hant': '至少保留一個預設方案。',
    },
    'msg.delete_preset_title': {
        'zh-Hans': '删除预设', 'en': 'Delete preset', 'ja': 'プリセットの削除',
        'zh-Hant': '刪除預設',
    },
    'msg.delete_preset_ask': {
        'zh-Hans': '确定要删除预设“{name}”吗？',
        'en': 'Delete the preset “{name}”?',
        'ja': 'プリセット「{name}」を削除しますか？',
        'zh-Hant': '確定要刪除預設「{name}」嗎？',
    },
    'msg.choose_program': {
        'zh-Hans': '选择要添加的程序或文件', 'en': 'Choose programs or files to add',
        'ja': '追加するプログラムまたはファイルを選択', 'zh-Hant': '選擇要新增的程式或檔案',
    },
    'msg.program_filter': {
        'zh-Hans': '程序 (*.exe *.lnk *.bat *.cmd);;所有文件 (*)',
        'en': 'Programs (*.exe *.lnk *.bat *.cmd);;All files (*)',
        'ja': 'プログラム (*.exe *.lnk *.bat *.cmd);;すべてのファイル (*)',
        'zh-Hant': '程式 (*.exe *.lnk *.bat *.cmd);;所有檔案 (*)',
    },
    'msg.choose_folder': {
        'zh-Hans': '选择要添加的文件夹', 'en': 'Choose a folder to add',
        'ja': '追加するフォルダーを選択', 'zh-Hant': '選擇要新增的資料夾',
    },
    'msg.cannot_add': {
        'zh-Hans': '无法添加', 'en': 'Cannot add', 'ja': '追加できません', 'zh-Hant': '無法新增',
    },
    'msg.folder_invalid': {
        'zh-Hans': '所选目录不存在或不可访问：\n{folder}',
        'en': 'That folder does not exist or is not accessible:\n{folder}',
        'ja': '選択したフォルダーが存在しないか、アクセスできません：\n{folder}',
        'zh-Hant': '所選目錄不存在或無法存取：\n{folder}',
    },
    'msg.folder_exists': {
        'zh-Hans': '该文件夹已在列表中。', 'en': 'That folder is already in the list.',
        'ja': 'そのフォルダーはすでに一覧にあります。', 'zh-Hant': '該資料夾已在清單中。',
    },
    'msg.path_input_title': {
        'zh-Hans': '输入路径', 'en': 'Enter path', 'ja': 'パスを入力', 'zh-Hant': '輸入路徑',
    },
    'msg.path_input_prompt': {
        'zh-Hans': '程序 / 文件 / 文件夹的完整路径（支持 %USERPROFILE% 等环境变量）：',
        'en': 'Full path to a program, file or folder '
              '(%USERPROFILE% and other environment variables are supported):',
        'ja': 'プログラム / ファイル / フォルダーのフルパス'
              '（%USERPROFILE% などの環境変数に対応）：',
        'zh-Hant': '程式 / 檔案 / 資料夾的完整路徑（支援 %USERPROFILE% 等環境變數）：',
    },
    'msg.path_invalid': {
        'zh-Hans': '路径无效', 'en': 'Invalid path', 'ja': '無効なパス', 'zh-Hant': '路徑無效',
    },
    'msg.path_not_exist': {
        'zh-Hans': '该路径不存在：\n{path}', 'en': 'This path does not exist:\n{path}',
        'ja': 'このパスは存在しません：\n{path}', 'zh-Hant': '該路徑不存在：\n{path}',
    },
    'msg.path_exists': {
        'zh-Hans': '该路径已在列表中。', 'en': 'That path is already in the list.',
        'ja': 'そのパスはすでに一覧にあります。', 'zh-Hant': '該路徑已在清單中。',
    },
    'msg.launching': {
        'zh-Hans': '正在启动中，请稍候...', 'en': 'Launching, please wait…',
        'ja': '起動中です。しばらくお待ちください…', 'zh-Hant': '正在啟動中，請稍候…',
    },
    'msg.empty_list': {
        'zh-Hans': '列表为空，没有需要关闭的程序。',
        'en': 'The list is empty — nothing to close.',
        'ja': '一覧が空です。閉じるものはありません。',
        'zh-Hant': '清單為空，沒有需要關閉的程式。',
    },
    'msg.save_failed': {
        'zh-Hans': '保存失败', 'en': 'Save failed', 'ja': '保存に失敗', 'zh-Hant': '儲存失敗',
    },
    'msg.save_failed_body': {
        'zh-Hans': '无法写入配置文件：\n{error}',
        'en': 'Could not write the settings file:\n{error}',
        'ja': '設定ファイルに書き込めませんでした：\n{error}',
        'zh-Hant': '無法寫入設定檔：\n{error}',
    },
    'msg.load_failed': {
        'zh-Hans': '加载失败', 'en': 'Load failed', 'ja': '読み込みに失敗', 'zh-Hant': '載入失敗',
    },
    'msg.load_failed_body': {
        'zh-Hans': '配置文件读取失败：\n{error}\n将使用默认设置。',
        'en': 'Could not read the settings file:\n{error}\nDefaults will be used.',
        'ja': '設定ファイルを読み込めませんでした：\n{error}\n既定の設定を使用します。',
        'zh-Hant': '設定檔讀取失敗：\n{error}\n將使用預設設定。',
    },
    'msg.open_dir_failed': {
        'zh-Hans': '无法打开目录', 'en': 'Cannot open folder',
        'ja': 'フォルダーを開けません', 'zh-Hant': '無法開啟目錄',
    },

    # ---- 关闭确认与结果 ----
    'close.title': {
        'zh-Hans': '确认关闭', 'en': 'Confirm close',
        'ja': '終了の確認', 'zh-Hant': '確認關閉',
    },
    'close.nothing_title': {
        'zh-Hans': '无需关闭', 'en': 'Nothing to close',
        'ja': '閉じるものはありません', 'zh-Hant': '無需關閉',
    },
    'close.nothing_body': {
        'zh-Hans': '列表中的程序当前都没有在运行，也没有找到对应的文件夹窗口，已全部跳过。\n\n'
                   '共检查 {programs} 个程序、{folders} 个文件夹。',
        'en': 'Nothing in the list is running right now and no matching folder windows were '
              'found, so everything was skipped.\n\n'
              'Checked {programs} program(s) and {folders} folder(s).',
        'ja': 'リスト内のプログラムはどれも実行されておらず、対応するフォルダーウィンドウも'
              '見つかりませんでした。すべてスキップします。\n\n'
              'プログラム {programs} 件、フォルダー {folders} 件を確認しました。',
        'zh-Hant': '清單中的程式目前都沒有在執行，也沒有找到對應的資料夾視窗，已全部略過。\n\n'
                   '共檢查 {programs} 個程式、{folders} 個資料夾。',
    },
    'close.ask_header': {
        'zh-Hans': '以下内容将被关闭：', 'en': 'The following will be closed:',
        'ja': '以下を終了します：', 'zh-Hant': '以下內容將被關閉：',
    },
    'close.section_programs': {
        'zh-Hans': '程序 {count} 个（正在运行）：\n{detail}',
        'en': 'Programs ({count}) currently running:\n{detail}',
        'ja': 'プログラム {count} 件（実行中）：\n{detail}',
        'zh-Hant': '程式 {count} 個（正在執行）：\n{detail}',
    },
    'close.section_folders': {
        'zh-Hans': '文件夹窗口 {count} 个（整窗关闭）：\n{detail}',
        'en': 'Folder windows ({count}) to close entirely:\n{detail}',
        'ja': 'フォルダーウィンドウ {count} 件（ウィンドウごと閉じる）：\n{detail}',
        'zh-Hant': '資料夾視窗 {count} 個（整窗關閉）：\n{detail}',
    },
    'close.more_items': {
        'zh-Hans': '· …等共 {count} 个', 'en': '· …and {count} in total',
        'ja': '· …ほか全 {count} 件', 'zh-Hant': '· …等共 {count} 個',
    },
    'close.more_windows': {
        'zh-Hans': '· …等共 {count} 个窗口', 'en': '· …and {count} windows in total',
        'ja': '· …ほか全 {count} ウィンドウ', 'zh-Hant': '· …等共 {count} 個視窗',
    },
    'close.mixed_hint': {
        'zh-Hans': '\n\n另有 {count} 个文件夹窗口混有列表外的标签，稍后单独询问。',
        'en': '\n\n{count} folder window(s) also contain tabs that are not in the list — '
              'you will be asked separately.',
        'ja': '\n\nリスト外のタブを含むフォルダーウィンドウが {count} 件あります。'
              '後で個別に確認します。',
        'zh-Hant': '\n\n另有 {count} 個資料夾視窗混有清單外的分頁，稍後單獨詢問。',
    },
    'close.skipped_hint': {
        'zh-Hans': '\n\n另有 {count} 项未运行或无法判定，将自动跳过。',
        'en': '\n\n{count} item(s) are not running or could not be identified and will be skipped.',
        'ja': '\n\n実行していない、または判定できない項目が {count} 件あり、スキップします。',
        'zh-Hant': '\n\n另有 {count} 項未執行或無法判定，將自動略過。',
    },
    'close.unopened_hint': {
        'zh-Hans': '\n其中 {count} 个文件夹当前没有打开的窗口，自然跳过。',
        'en': '\n{count} of the folders have no open window right now and are skipped.',
        'ja': '\nうち {count} 件のフォルダーは開いているウィンドウがないためスキップします。',
        'zh-Hant': '\n其中 {count} 個資料夾目前沒有開啟的視窗，自然略過。',
    },
    'close.doc_hint': {
        'zh-Hans': '\n\n注：标记了程序名的条目本身是文档（如 .drawio），没有独立进程，'
                   '只能按"打开它的程序"关闭，因此会同时关闭该程序的其他窗口。',
        'en': '\n\nNote: entries with a program name are documents (e.g. .drawio) without a '
              'process of their own, so they can only be closed through the program that '
              'opens them — other windows of that program will be closed too.',
        'ja': '\n\n注：プログラム名が付いた項目は文書（例：.drawio）で、独自のプロセスがないため'
              '「開いているプログラム」経由でしか閉じられません。'
              'そのプログラムの他のウィンドウも同時に閉じます。',
        'zh-Hant': '\n\n註：標記了程式名的項目本身是文件（如 .drawio），沒有獨立程序，'
                   '只能按「開啟它的程式」關閉，因此會同時關閉該程式的其他視窗。',
    },
    'close.warning': {
        'zh-Hans': '\n\n关闭后不可恢复，请确认已保存工作。',
        'en': '\n\nThis cannot be undone — make sure your work is saved.',
        'ja': '\n\n終了後は元に戻せません。作業内容を保存したか確認してください。',
        'zh-Hant': '\n\n關閉後無法復原，請確認已儲存工作。',
    },
    'close.instances_suffix': {
        'zh-Hans': '（将关闭 {name} 的全部实例）',
        'en': ' (all {name} windows will be closed)',
        'ja': '（{name} のすべてのインスタンスを閉じます）',
        'zh-Hant': '（將關閉 {name} 的全部執行個體）',
    },
    'close.mixed_title': {
        'zh-Hans': '窗口含其他标签', 'en': 'Windows contain other tabs',
        'ja': 'ほかのタブを含むウィンドウ', 'zh-Hant': '視窗含其他分頁',
    },
    'close.mixed_body': {
        'zh-Hans': '以下 {count} 个文件夹窗口里还有不属于本列表的标签：\n\n{lines}\n\n'
                   '整窗关闭会把这些标签一起关掉（它们的文件不会被删除）。\n'
                   '是否一并关闭？\n\n'
                   '「是」= 整窗关闭；「否」= 跳过这些窗口，其余内容照常关闭。',
        'en': '{count} folder window(s) also contain tabs that are not in this list:\n\n{lines}\n\n'
              'Closing the whole window closes those tabs too (their files are not deleted).\n'
              'Close them as well?\n\n'
              '“Yes” = close the whole window; “No” = skip these windows and close the rest.',
        'ja': '次の {count} 件のフォルダーウィンドウには、このリストにないタブが含まれています：\n\n'
              '{lines}\n\n'
              'ウィンドウごと閉じるとそれらのタブも閉じます（ファイルは削除されません）。\n'
              'まとめて閉じますか？\n\n'
              '「はい」= ウィンドウごと閉じる；「いいえ」= これらのウィンドウをスキップし、'
              'ほかは通常どおり閉じます。',
        'zh-Hant': '以下 {count} 個資料夾視窗裡還有不屬於本清單的分頁：\n\n{lines}\n\n'
                   '整窗關閉會把這些分頁一起關掉（它們的檔案不會被刪除）。\n'
                   '是否一併關閉？\n\n'
                   '「是」= 整窗關閉；「否」= 略過這些視窗，其餘內容照常關閉。',
    },
    'close.mixed_line': {
        'zh-Hans': '· {title}，另有 {count} 个标签：{names}',
        'en': '· {title} — {count} other tab(s): {names}',
        'ja': '· {title}（ほか {count} タブ：{names}）',
        'zh-Hant': '· {title}，另有 {count} 個分頁：{names}',
    },
    'close.denied_title': {
        'zh-Hans': '需要管理员权限', 'en': 'Administrator rights required',
        'ja': '管理者権限が必要です', 'zh-Hant': '需要系統管理員權限',
    },
    'close.denied_body': {
        'zh-Hans': '{count} 个程序拒绝访问，通常是它们以管理员身份运行。\n'
                   '是否以管理员身份重试关闭？\n（系统会弹出 UAC 确认）',
        'en': '{count} program(s) denied access — usually because they run as administrator.\n'
              'Retry closing them as administrator?\n(A UAC prompt will appear.)',
        'ja': '{count} 件のプログラムがアクセスを拒否しました。多くは管理者として実行されています。\n'
              '管理者として再試行しますか？\n（UAC の確認が表示されます）',
        'zh-Hant': '{count} 個程式拒絕存取，通常是它們以系統管理員身分執行。\n'
                   '是否以系統管理員身分重試關閉？\n（系統會跳出 UAC 確認）',
    },
    'close.result_title': {
        'zh-Hans': '关闭结果', 'en': 'Close results', 'ja': '終了結果', 'zh-Hant': '關閉結果',
    },
    'close.result_programs': {
        'zh-Hans': '已关闭 {count} 个程序。', 'en': 'Closed {count} program(s).',
        'ja': 'プログラム {count} 件を終了しました。', 'zh-Hant': '已關閉 {count} 個程式。',
    },
    'close.result_folders': {
        'zh-Hans': '已关闭 {count} 个文件夹窗口。', 'en': 'Closed {count} folder window(s).',
        'ja': 'フォルダーウィンドウ {count} 件を閉じました。',
        'zh-Hant': '已關閉 {count} 個資料夾視窗。',
    },
    'close.result_none': {
        'zh-Hans': '没有内容被关闭。', 'en': 'Nothing was closed.',
        'ja': '何も終了しませんでした。', 'zh-Hant': '沒有內容被關閉。',
    },
    'close.result_skipped': {
        'zh-Hans': '跳过 {count} 项（未运行 / 未打开窗口 / 无法判定 / 按你的选择跳过）。',
        'en': 'Skipped {count} item(s) (not running / no window / could not identify / '
              'skipped by your choice).',
        'ja': '{count} 件をスキップしました（未実行 / ウィンドウなし / 判定不可 / 選択による）。',
        'zh-Hant': '略過 {count} 項（未執行 / 未開啟視窗 / 無法判定 / 依你的選擇略過）。',
    },
    'close.result_failed': {
        'zh-Hans': '关闭失败 {count} 项：\n{detail}',
        'en': 'Failed to close {count} item(s):\n{detail}',
        'ja': '{count} 件を終了できませんでした：\n{detail}',
        'zh-Hant': '關閉失敗 {count} 項：\n{detail}',
    },
    'close.result_log': {
        'zh-Hans': '详细命令与返回码已写入日志：\n{path}',
        'en': 'Commands and exit codes were written to the log:\n{path}',
        'ja': '詳細なコマンドと戻り値はログに記録しました：\n{path}',
        'zh-Hant': '詳細命令與傳回碼已寫入日誌：\n{path}',
    },
    'close.result_log_hint': {
        'zh-Hans': '（可点击主界面「日志」打开所在目录）',
        'en': '(Use “Logs” on the main window to open that folder.)',
        'ja': '（メイン画面の「ログ」でフォルダーを開けます）',
        'zh-Hant': '（可點擊主介面「日誌」開啟所在目錄）',
    },
    'close.reason_denied': {
        'zh-Hans': '权限不足（需管理员）', 'en': 'Access denied (needs administrator)',
        'ja': '権限不足（管理者が必要）', 'zh-Hant': '權限不足（需系統管理員）',
    },
    'close.reason_still_running': {
        'zh-Hans': '进程仍在运行（可能被后台服务重启）',
        'en': 'Still running (a background service may have restarted it)',
        'ja': 'プロセスが残っています（バックグラウンドサービスが再起動した可能性）',
        'zh-Hant': '程序仍在執行（可能被背景服務重新啟動）',
    },
    'close.mixed_skipped': {
        'zh-Hans': '含列表外标签，按你的选择跳过',
        'en': 'Contains tabs outside the list — skipped as you chose',
        'ja': 'リスト外のタブを含むため、選択どおりスキップ',
        'zh-Hant': '含清單外分頁，依你的選擇略過',
    },
    'close.window_failed': {
        'zh-Hans': '窗口未关闭（可能被拦截或无响应）',
        'en': 'Window not closed (blocked or not responding)',
        'ja': 'ウィンドウが閉じませんでした（ブロックまたは応答なし）',
        'zh-Hant': '視窗未關閉（可能被攔截或無回應）',
    },
}


# ------------------------- 当前语言 -------------------------

class Lang:
    """当前界面语言的唯一状态源（与 FontPrefs 同构，便于测试直接改）。"""

    CODE = DEFAULT_LANGUAGE

    @staticmethod
    def set(code):
        """写入语言码：非法值收敛到默认语言，绝不抛错（配置可能被手改坏）。"""
        Lang.CODE = code if code in LANGUAGE_CODES else DEFAULT_LANGUAGE
        return Lang.CODE

    @staticmethod
    def name(code=None):
        return language_name(code or Lang.CODE)

    @staticmethod
    def index(code=None):
        """在语言清单里的序号，供下拉框定位。"""
        code = code or Lang.CODE
        return LANGUAGE_CODES.index(code) if code in LANGUAGE_CODES else 0

    @staticmethod
    def is_cjk(code=None):
        """中文/日文用竖排两字；英文这类拉丁文字必须横排（竖排五个字母会顶出盘沿）。"""
        return (code or Lang.CODE) in ('zh-Hans', 'zh-Hant', 'ja')


def t(key, **kwargs):
    """
    取一条译文。缺失时依次回落：当前语言 → 简体中文 → 键名。

    回落而不是抛错：新增文案漏翻一条，界面最多露出中文，不会白屏。
    """
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(Lang.CODE) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            # 占位符与调用不一致时返回原文，比抛异常更适合用在绘制/对话框里
            return text
    return text


def all_variants(key):
    """
    同一条文案在所有语言下的写法集合。

    用途只有一个：认出"我们自己起的名字"。「默认方案 / Default / 既定 / 預設方案」
    四个写法都算同一个东西，用户自己建的名字不在其中——换语言时不能动用户的命名。
    """
    return frozenset((STRINGS.get(key) or {}).values())


DEFAULT_PRESET_NAMES = all_variants('main.default_preset')


def missing_keys(code):
    """某语言缺哪些键（测试用：保证四种语言覆盖同一套文案）。"""
    return sorted(k for k, v in STRINGS.items() if not v.get(code))
