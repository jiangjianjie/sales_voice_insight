# Voice Insight — 营销场景语音智能分析平台

基于多模态大模型的销售会话智能处理系统，面向汽车4S店、燃气安检等行业，提供从原始录音到结构化洞察的全链路能力。

---

## 业务背景

销售团队每天产生大量客户录音（单次会话可达6小时），人工复盘效率极低。本平台通过以下能力解决核心痛点：

| 业务问题 | 解决方案 |
|---|---|
| ASR转写错误率高，专业术语识别差 | 多模态ASR文本增强（音频+文本联合纠错） |
| 长录音无法直接送入大模型 | 智能长会话切分（保留时间戳，按句边界切割） |
| 无法快速了解客户需求 | 客户标签与购买意向提取 |
| 服务质量难以量化考核 | 员工服务质检与能力评估 |
| 销售复盘耗时 | 销售会话结构化总结 |

---

## 功能模块

### 1. ASR 文本增强（核心）

**接口：** `POST /api/v1/multimodal/infer/asr`

结合原始音频与ASR文本，通过多模态大模型（Gemini）进行逐字级纠错：

- 同音字/错别字修正
- 汽车行业专业术语纠正（4S店交车/销售场景）
- 角色识别纠正（销售/客户）
- 断句优化（基于音频停顿）
- 严格保留原始时间戳，禁止新增/删除内容

**处理流程：**
```
音频URL + ASR文本列表
    ↓
智能切分（>1小时自动分段，最多6段）
    ↓
并发多模态推理（每段独立处理）
    ↓
合并结果 + 还原全局时间戳
    ↓
返回纠错后的 speech_list
```

### 2. 长会话智能切分

超长录音（>1小时）自动按小时切分，切分点优先选择句子边界（。！？等），避免在句中截断，保证每段语义完整。

### 3. 客户标签提取

**接口：** `POST /api/v1/nlp/agent_conversation_summary`

基于客户发言分析：
- **购买意向**：强 / 中 / 弱 / 无意向
- **购买关注点**：价格、性能、售后、品牌等
- **购买异议点**：价格偏高、信任不足、功能不符等

同时支持客户画像识别（姓名、地址、消费能力标签）及产品推荐话术生成（燃气安检场景）。

### 4. 销售会话总结

**接口：** `POST /api/v1/sales/dialogue/generate`

对完整销售对话生成结构化分析报告，辅助销售复盘与管理层质检。

---

## 技术架构

```
┌─────────────────────────────────────────────┐
│              Tornado HTTP Server             │
│                  Port 8898                   │
├──────────────┬──────────────┬────────────────┤
│  ASR增强接口  │  会话总结接口  │  话术生成接口   │
└──────┬───────┴──────┬───────┴────────────────┘
       │              │
       ▼              ▼
┌─────────────┐  ┌──────────────┐
│ 音频切分模块  │  │  LLM调用模块  │
│  (pydub)    │  │  (aiohttp)   │
└─────────────┘  └──────────────┘
       │              │
       ▼              ▼
┌─────────────────────────────────────────────┐
│           多模态大模型 (Gemini)               │
│           文本大模型 (DeepSeek / GPT-4o)     │
└─────────────────────────────────────────────┘
```

**技术栈：**
- Web框架：Tornado 6.5
- 异步HTTP：aiohttp 3.11
- 音频处理：pydub + ffmpeg
- 大模型：Gemini（多模态）、DeepSeek-V3、GPT-4o（Azure）
- 并发控制：asyncio.Semaphore（最大10并发）

---

## 项目结构

```
marketing_saas_platform/
├── app.py                  # 服务入口，路由注册
├── config.py               # 环境配置、API密钥、系统提示词
├── base_handler.py         # 请求基类，日志、请求追踪
├── analyze_asr_text.py     # ASR增强核心逻辑
├── audio_text_splitter.py  # 长音频/文本切分
├── audio_utils.py          # 时间戳格式转换工具
├── tools.py                # LLM接口封装（Gemini/DeepSeek/GPT）
├── requirements.txt        # 依赖列表
├── server.sh               # Linux守护进程启动脚本
├── test.py                 # 批量接口压测脚本
├── test_asr_enhancer.py    # ASR增强集成测试
├── test_real_case.py       # 音频切分功能测试
└── project_logs/           # 运行日志（自动生成）
```

---

## 快速开始

### 环境要求

- Python 3.9+
- ffmpeg（系统级安装，pydub依赖）

### 安装依赖

```bash
pip install -r marketing_saas_platform/requirements.txt
```

### 配置

编辑 `config.py`，设置运行环境和API密钥：

```python
ENV = "test"   # test / online / dev
```

各环境对应不同的API endpoint和密钥，在 `config.py` 中分别配置。

### 启动服务

**开发环境：**
```bash
cd marketing_saas_platform
python app.py
```

**生产环境（Linux守护进程）：**
```bash
bash server.sh start    # 启动
bash server.sh stop     # 停止
bash server.sh restart  # 重启
```

服务默认监听 `0.0.0.0:8898`。

---

## API 文档

### ASR 文本增强

```
POST /api/v1/multimodal/infer/asr
Content-Type: application/json
```

**请求体：**
```json
{
  "audio_url": "https://example.com/audio.mp3",
  "speech_list": [
    {
      "beginTime": 0,
      "endTime": 3500,
      "role": "销售",
      "text": "您好欢迎来到我们4s店"
    }
  ]
}
```

**响应：**
```json
{
  "code": 200,
  "speech_list": [
    {
      "beginTime": 0,
      "endTime": 3500,
      "role": "销售",
      "text": "您好，欢迎来到我们4S店。"
    }
  ],
  "input_tokens": 12500,
  "output_tokens": 11800
}
```

**speech_list 字段说明：**

| 字段 | 类型 | 说明 |
|---|---|---|
| beginTime | int | 片段开始时间（毫秒） |
| endTime | int | 片段结束时间（毫秒） |
| role | string | 说话角色：`销售` 或 `客户` |
| text | string | ASR转写文本 |

---

### 销售会话总结

```
POST /api/v1/nlp/agent_conversation_summary
Content-Type: application/json
```

分析完整对话，返回客户购买意向、关注点、异议点及判断依据。

---

### 销售话术生成

```
POST /api/v1/sales/dialogue/generate
Content-Type: application/json
```

根据客户画像、商机信息、安全隐患，生成个性化销售话术（燃气安检场景）。

---

## 核心设计决策

**为什么用多模态而不是纯文本纠错？**
纯文本纠错无法区分同音字（如"的/地/得"、"在/再"），也无法判断角色归属。音频提供了声纹、语气、停顿等信息，显著提升纠错准确率。

**为什么按句边界切分而不是固定时间点？**
固定时间点切分会在句子中间截断，导致上下文丢失，影响模型理解。按句边界切分保证每段语义完整。

**并发控制策略**
`asyncio.Semaphore(10)` 限制同时进行的模型调用数，防止触发API限流，同时保证多段音频并发处理的效率。

---

## 日志与追踪

每个请求自动生成 `request_id`（UUID前缀），贯穿整个处理链路，便于问题排查。

日志文件位于 `project_logs/`，按API分类，单文件最大15MB，保留5个备份。

---

## 测试

```bash
# ASR增强集成测试
python marketing_saas_platform/test_asr_enhancer.py

# 音频切分功能测试
python marketing_saas_platform/test_real_case.py

# 批量接口压测（需配置Excel文件路径）
python marketing_saas_platform/test.py
```
