# WMCaption 培训考核自动化系统

WMCaption-Exam-System 是一个基于题库的智能组题与自动评分工具，当前项目核心文件包括：

- `generate_exam.py`：从题库生成试卷并导出飞书 / 问卷星兼容格式
- `grading_system_v2.py`：读取问卷星导出答案并批量评分，支持 Ollama 主观题评分
- `data/test/WMCaption_题库_v2.json`：题库 JSON 数据
- `data/test/WMCaption_题库_v2.md`：题库 Markdown 源文件（参考）
- `exam_history.json`：试卷历史记录，用于避免短期重复出题

## 📁 当前目录结构

```
WMCaption-Exam-System/
├── data/
│   ├── answer/              # 答案文件目录
│   ├── exer/                # 生成试卷 JSON 输出目录
│   ├── outputbyollama/      # 评分结果输出目录
│   └── test/                # 题库源数据目录
│       ├── WMCaption_题库_v2.json
│       └── WMCaption_题库_v2.md
├── exam_history.json
├── generate_exam.py
├── grading_system_v2.py
└── README.md
```

## 🚀 快速使用

### 1. 生成试卷

当前项目已包含 `data/test/WMCaption_题库_v2.json`。直接运行：

```bash
python generate_exam.py
```

脚本会：

- 读取题库 JSON
- 按题型、难度、章节权重智能抽题
- 生成试卷 JSON
- 导出飞书多维表格兼容 CSV
- 导出问卷星 / 腾讯问卷兼容 CSV/Excel（可选）
- 保存试卷 JSON 到 `data/exer/`

生成完成后，你会看到：

- `data/exer/<试卷名>.json`
- `data/exer/<试卷名>_试卷.csv`
- `data/exer/<试卷名>_答案.csv`
- `data/exer/<试卷名>_问卷星导入.csv` 或 `.xlsx`

### 2. 准备学员答题数据

如果你使用问卷星/腾讯问卷，请将导出结果保存到：

- `data/answer/`

当前脚本默认读取：

- `data/answer/367793615_按文本_WM内部评估_2_2.xlsx`

如果你的文件名或路径不同，请修改 `grading_system_v2.py` 中的 `ANSWER_EXCEL_PATH`。

### 3. 批量评分

```bash
python grading_system_v2.py
```

脚本会：

- 加载试卷 JSON（默认 `data/exer/WMCaption考试_20260609_135613.json`）
- 读取问卷星导出的 Excel 答案
- 自动评分客观题
- 使用 Ollama 评分主观题（若可用）
- 生成汇总 CSV 到 `data/outputbyollama/`

## 🧩 依赖说明

`grading_system_v2.py` 读取 Excel 需要：

```bash
pip install pandas openpyxl requests
```

如果要使用 Ollama 主观题评分，还需本机启动 Ollama 服务：

```bash
ollama serve
```

默认地址：`http://localhost:11434`

## 🔧 配置说明

### 题库路径

`generate_exam.py` 默认使用：

- `data/test/WMCaption_题库_v2.json`

如果你想使用其他题库，请修改脚本中的 `DEFAULT_BANK_PATH` 或通过命令行参数指定。

### 输出目录

`generate_exam.py` 默认输出到：

- `data/exer/`

### 组题策略

在 `generate_exam.py` 中，`DEFAULT_CONFIG` 控制：

- `total_questions`：试卷总题量
- `difficulty_ratio`：难度配比
- `type_ratio`：题型配比
- `chapter_weights`：章节权重

### Ollama 设置

在 `grading_system_v2.py` 中，可修改：

```python
self.ollama_url = "http://localhost:11434"
self.model = "qwen3:8b"
```

如果本地没有 Ollama，可将 `DISABLE_OLLAMA = True`。

## 📌 注意事项

- `exam_history.json` 用于记录生成试卷和已用题目，避免短期重复出题。
- `grading_system_v2.py` 当前通过脚本内部路径读取答案文件和试卷文件，若文件名不同请修改对应变量。
- 若你希望从 `data/test/WMCaption_题库_v2.md` 生成 JSON，可自行补充题库解析脚本。

## ✅ 推荐流程

1. 确认 `data/test/WMCaption_题库_v2.json` 存在且格式正确
2. 运行 `python generate_exam.py`
3. 导出学员答案 Excel 到 `data/answer/`
4. 运行 `python grading_system_v2.py`
5. 查看评分结果：`data/outputbyollama/`

## 📄 说明

本项目当前聚焦于从现有题库生成试卷并使用问卷星/Excel答案进行自动评分。
