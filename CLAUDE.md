# CLAUDE.md — 公考小工具 (CivilServantsTools)

> 面向公务员考试备考者的桌面工具箱。将第三方刷题 App 导出的 PDF 试卷转换为标准真题格式，并提供计时练习、答题卡生成、PDF 拼合与 OCR 文字识别功能。

## 项目概况

- **运行平台**: Windows 10/11 (64 位)
- **Python**: 3.10+, <3.13 (OCR 场景依赖限制)
- **打包方式**: PyInstaller 单文件 exe (`main.spec`)
- **版本管理**: Gitee 上的 `version.json` 远端拉取做自动更新检查
- **UI 语言**: 中文（繁体/简体混用，用户界面以简体中文为主）

## 技术栈

| 组件 | 库 | 用途 |
|------|-----|------|
| UI 框架 | PyQt6 ≥ 6.6 | 主窗口、工具栏、预览面板、设置面板等 |
| PDF 解析 | PyMuPDF (fitz) ≥ 1.24 | PDF 文字提取、页面渲染、图片导出 |
| OCR 引擎 | PaddleOCR 2.x + PaddlePaddle | 扫描版 PDF 文字识别、图片文字识别 |
| PDF 生成 | ReportLab ≥ 4.2 | 转换后 PDF 排版输出 |
| 图像处理 | Pillow ≥ 10.0 | 图片加载与预处理 |
| 数据校验 | Pydantic ≥ 2.0 | 配置/数据模型校验 |
| 设计系统 | Slate + Indigo | 全局 QSS 样式 `resources/styles/app.qss` |

## 项目结构

```
CivilServantsTools/
├── main.py                          # 程序入口，创建 QApplication + MainWindow
├── app_paths.py                     # 路径解析工具（区分源码运行 vs PyInstaller 打包）
├── version.json                     # 版本号、更新 URL、更新日志
├── main.spec                        # PyInstaller 打包配置
├── setup.bat / run.bat / setup_runner.ps1  # 安装/启动脚本
├── user_config.json                 # 用户本地配置（如跳过的更新版本）
│
├── ui/                              # 主程序 UI
│   ├── main_window.py               # MainWindow：首页路由、工具栏信号连接、转换流程
│   └── dialogs.py                   # 通用对话框（show_info, show_success）
│
├── tools/
│   ├── ocr_engine/                  # ⭐ 共享 OCR 引擎（pdf_converter + ocr_recognizer 共用）
│   │   ├── base.py                  # BaseRecognizer 抽象基类 + OCRRegion 数据类
│   │   └── paddle_recognizer.py     # PaddleOCR 2.x 实现，GPU 检测与回退
│   │
│   ├── pdf_converter/               # ⭐ 核心工具：PDF 真题排版转换器（最复杂的模块）
│   │   ├── config/
│   │   │   ├── settings.py          # 模板加载器（load_template / load_default_config）
│   │   │   ├── templates/           # JSON 驱动排版模板（40+ 可配置参数）
│   │   │   │   ├── xingce_template.json   # 行测模板
│   │   │   │   └── shenlun_template.json  # 申论模板
│   │   │   └── xingce_section_instructions.json  # 行测五大模块识别指令
│   │   │
│   │   ├── core/
│   │   │   ├── models.py            # 数据模型：TextBlock → ParsedDocument → Question → CleanedDocument → PageElement → LaidOutDocument
│   │   │   ├── pipeline.py          # ConversionPipeline：解析→清洗→排版→生成的完整流水线
│   │   │   ├── parser/
│   │   │   │   ├── base.py          # BaseParser 抽象基类
│   │   │   │   ├── text_parser.py   # TextParser：PyMuPDF 文字型 PDF 解析
│   │   │   │   └── ocr_parser.py    # OCRParser：PaddleOCR 图片型 PDF 解析
│   │   │   ├── cleaner/
│   │   │   │   ├── xingce_cleaner.py   # 行测清洗：去水印/广告/二维码、题号识别、选项提取、五大模块归类
│   │   │   │   └── shenlun_cleaner.py  # 申论清洗：材料分离、作答要求提取、双栏排版识别
│   │   │   ├── layout/
│   │   │   │   └── engine.py        # LayoutEngine：文本排版计算（换行、分页、图片定位）
│   │   │   └── generator/
│   │   │       ├── font_manager.py  # FontManager：Windows 系统字体注册
│   │   │       └── pdf_generator.py # PDFGenerator：ReportLab 输出最终 PDF
│   │   │
│   │   └── ui/                      # pdf_converter 专属 UI
│   │       ├── preview_panel.py     # 双栏预览（左：原始 PDF / 右：转换结果）
│   │       ├── settings_panel.py    # 右侧设置面板（字体、字号、页边距等40+参数）
│   │       ├── toolbar.py           # 工具栏（主页/打开/批量/保存/转换按钮）
│   │       ├── batch_dialog.py      # 批量转换对话框
│   │       ├── progress_dialog.py   # 转换进度对话框
│   │       └── worker.py            # ConversionWorker：后台线程执行转换
│   │
│   ├── exam_timer/                  # 考试计时器
│   │   ├── core/
│   │   │   ├── models.py            # 计时数据模型
│   │   │   └── timer_engine.py      # QTimer 100ms 精度计时引擎
│   │   └── ui/timer_widget.py       # 计时器界面
│   │
│   ├── answer_sheet/                # 申论答题卡生成器
│   │   ├── core/generator.py        # AnswerSheetGenerator：ReportLab 生成答题卡 PDF
│   │   └── ui/widget.py            # 答题卡 UI（页数/题目模式切换）
│   │
│   ├── pdf_merger/                  # PDF 拼合工具
│   │   ├── core/merger.py           # 使用 PyMuPDF 合并
│   │   └── ui/widget.py            # 拖拽排序 + 预览界面
│   │
│   └── ocr_recognizer/             # OCR 文字识别工具
│       ├── core/preprocessing.py    # 图像预处理（对比度增强/锐化/去噪）
│       └── ui/
│           ├── recognizer_widget.py # 识别界面（拖放 + 结果展示）
│           └── worker.py            # 后台识别线程
│
└── resources/
    ├── styles/app.qss               # 全局样式表（Slate + Indigo 设计系统）
    ├── toolsIco.ico                 # 应用图标
    └── author-support-poster.png    # 打赏海报
```

## 核心架构：PDF 转换流水线

PDF 格式转换是项目最核心、最复杂的模块，遵循 **解析 → 清洗 → 排版 → 生成** 四阶段流水线：

### 数据流模型 (models.py)

```
ParsedDocument (原始解析结果)
  └─ ParsedPage[]  (每页的文本块 + 图片块)
       └─ TextBlock[]   (text, bbox, font_name, font_size, is_bold)
       └─ ImageBlock[]  (image_bytes, bbox, 尺寸)

           ↓ [cleaner 清洗]

CleanedDocument (结构化题目)
  ├─ exam_type: "xingce" | "shenlun"
  ├─ questions: Question[]        (行测：题号 + 题干 + Option[ABCD])
  ├─ materials: MaterialBlock[]   (申论：给定资料段落)
  └─ shenlun_questions: ShenlunQuestion[] (申论：作答要求)

           ↓ [layout engine 排版]

LaidOutDocument (页面元素带精确坐标)
  └─ LaidOutPage[]
       └─ PageElement[]  (type, text, x_mm, y_mm, font, size, 图片数据)

           ↓ [pdf_generator 生成]

bytes (最终 PDF 二进制)
```

### 流水线阶段 (pipeline.py: ConversionPipeline.run)

1. **解析 (0-20%)** — 自动检测 PDF 类型：
   - 文字型 PDF → `TextParser` (PyMuPDF 文本提取)
   - 扫描型 PDF → `OCRParser` (PaddleOCR 图像识别)
   - OCR 首次使用会下载模型（约 100MB），需提示用户

2. **清洗 (20-30%)** — 按题型分离：
   - 行测 → `XingceCleaner`: 去水印/广告/二维码，题号+A/B/C/D选项识别，五大模块归类
   - 申论 → `ShenlunCleaner`: 给定材料提取，作答要求分离，跳过答题卡页

3. **排版 (30-70%)** — `LayoutEngine` 计算文本渲染位置：
   - 从 JSON 模板加载 `LayoutConfig`（页边距/字体/字号/间距/选项排列等40+参数）
   - 处理换行、分页、图片嵌入
   - OCR 结果质量差时自动切换到「扫描件保真模式」（页面截图方式渲染）

4. **生成 (70-100%)** — `PDFGenerator` (ReportLab) 输出最终 PDF
   - 可选：追加源 PDF 最后一页（保留对答案二维码）

### 容错机制

- OCR 提取失败（0 题目/选项异常比例≥25%/题号标签不均衡）→ 自动回退到 `_generate_image_preserved_pdf`（将每页渲染为图片居中嵌入）
- OCR 依赖缺失 → 弹出安装引导（调用 `setup.bat`）
- cuDNN 运行时缺失 → 弹出 NVIDIA 下载页
- GPU 不兼容（RTX 50 系列 Blackwell 架构）→ 自动回退 CPU

## UI 架构

`MainWindow` 使用 `QStackedWidget` 做页面路由：

| 索引 | 页面 | 显示条件 |
|------|------|----------|
| 0 | 首页（工具卡片） | 默认 |
| 1 | PDF 格式转换 | 打开 PDF 或点击卡片 |
| 2 | 考试计时器 | 点击卡片 |
| 3 | 申论答题纸 | 点击卡片 |
| 4 | PDF 拼合 | 点击卡片 |
| 5 | OCR 文字识别 | 点击卡片 |

- 只有 PDF 转换页显示顶部 `MainToolbar`
- 其他工具页有独立返回按钮 (`back_requested` 信号)
- 状态栏显示当前工具提示和作者信息

## 关键设计决策与约束

### 1. 打包路径处理 (app_paths.py)
- **源码运行**: `app_root()` 返回 `__file__` 所在目录
- **PyInstaller 打包**: 资源在 `sys._MEIPASS` 临时目录；用户配置在 `%APPDATA%/CivilServantsTools/user_config.json`
- 所有资源路径必须通过 `resource_path()` 构建

### 2. OCR 引擎共享
- `tools/ocr_engine/` 是共享模块，`pdf_converter` 和 `ocr_recognizer` 都通过它访问 PaddleOCR
- `BaseRecognizer` 抽象基类定义了统一接口：`recognize()`, `recognize_batch()`, `warm_up()`
- `PaddleRecognizer` 封装 PaddleOCR 2.x，包含 GPU 兼容性检测

### 3. 中文术语约定
项目中有一些术语专用映射（常见于代码中）：
- 行测 (xingce) = 行政职业能力测验
- 申论 (shenlun) = 申论考试
- 粉笔 = Fenbi App (主流刷题软件)
- 华图 = Huatu App (另一个刷题软件)
- 给定资料 = 申论阅读材料
- 作答要求 = 申论写作题目
- 资料分析 = 行测中的数据分析模块（含图表）
- 五大模块 = 政治理论/常识判断、言语理解与表达、数量关系、判断推理、资料分析

### 4. JSON 模板驱动配置
排版参数全部通过 JSON 模板文件配置（`xingce_template.json` / `shenlun_template.json`），包含 40+ 可调参数：
- 纸张尺寸、页边距
- 各级字体（页眉/题号/题干/选项/页码）的 family + size + bold
- 行距倍数、段落间距、题间间距
- 选项排列方式（竖排/双栏）
- 答题横线、页码显示等开关

UI 设置面板 (`settings_panel.py`) 可覆盖模板默认值，通过 `config_overrides` 字典传入流水线。

## 常见开发任务

### 运行程序
```bash
# 源码运行
pip install -r requirements.txt   # 需要手动确认依赖
python main.py

# 或使用一键脚本
setup.bat   # 安装依赖
run.bat     # 启动
```

### 打包
```bash
pyinstaller main.spec
# 输出: dist/公考小工具.exe (约 600MB+)
```

### 添加新工具
1. 在 `tools/` 下新建子目录（如 `tools/new_tool/`），包含 `core/` 和 `ui/`
2. 在 `ui/main_window.py` 中 import 并添加到 `QStackedWidget`
3. 在首页 `active_tools` 列表中添加卡片入口

### 修改排版参数
直接编辑 `tools/pdf_converter/config/templates/*.json`，无需改代码。UI 设置面板会覆盖这些默认值。

### 调试 PDF 转换
- 关注 `pipeline.py` 中 `progress` 回调的百分比和阶段名
- 转换失败时检查 `CleanedDocument` 的 `filtered_out` 和 `ignored_pages`
- OCR 质量不好时检查 `_ocr_structure_is_poor()` 的判断条件

## 注意事项 / 坑

1. **PaddlePaddle 版本锁定**: 当前使用 PaddlePaddle 2.6.2（因为 3.x 在 Windows 上 GPU 包未发布，且有 PIR/OneDNN 崩溃 bug）。RTX 50 系列 GPU 不支持 GPU 加速。
2. **PyMuPDF 性能**: 粉笔 App 使用 Skia/Chromium PDF 引擎导出，PyMuPDF 文字提取可能较慢。
3. **系统字体依赖**: 排版依赖 Windows 系统字体（SimSun/SimHei/KaiTi/FangSong），非 Windows 平台不支持。
4. **Python 版本上限**: 必须 < 3.13，因为 PaddleOCR/PaddlePaddle 兼容性限制。
5. **exe 体积**: 打包后约 600MB+，因为包含了 PaddleOCR/PaddlePaddle 运行库。
6. **中文注释**: 代码中大量使用中文注释和变量名（如 `_u(0x8D44, 0x6599, 0x5206, 0x6790)` = "资料分析"），需要用 Unicode 码点来避免编码问题。
7. **更新检查**: 从 Gitee 拉取 `version.json`，不是 GitHub。启动时静默检查，菜单栏可手动检查。

## Git 工作流

- **主分支**: `develop` (当前工作分支)
- **发布分支**: `main`
- **提交信息格式**: 中文描述，如 `feat(pdf内容格式转换): ...` / `fix(pdf拼合): ...`
- **用户**: pmy
