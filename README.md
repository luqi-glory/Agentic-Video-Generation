# AgentVideo

AgentVideo 是一个基于大模型与视频生成 API 的短片自动生成工作流项目。项目将用户的一句话创意提示词逐步扩写为剧本、导演分镜、角色参考图、首帧图片、视频片段，并最终使用 `ffmpeg` 拼接成完整视频。

当前项目主要面向中文短片生成场景，示例主题为：`神情忧郁的女子在湖泊上划船`。

## 功能概览

项目按“编剧 → 导演 → 演员/生成器 → 剪辑”的流程组织：

1. **Scriptwriter 编剧**
   - 将用户原始提示词扩写为完整短片剧本资料。
   - 输出故事、背景、角色设定等结构化 JSON。

2. **Director 导演**
   - 读取编剧生成的剧本资料。
   - 将故事拆分为约 5 秒一个的视频片段。
   - 区分“长镜头”和“分镜”，并生成可供视频生成使用的导演分镜 JSON。

3. **Actor 视频生成**
   - 根据角色设定生成角色参考图。
   - 为每个镜头生成首帧图片。
   - 调用 Seedance 图生视频接口生成每个视频片段。
   - 对长镜头组按顺序延续上一片段最后一帧，以提升连续性。

4. **Editor 剪辑**
   - 读取导演分镜顺序。
   - 找到所有生成的视频片段。
   - 使用 `ffmpeg` 将片段拼接为最终视频。

## 项目结构

```text
AgentVideo/
├── scriptwriter.py          # 编剧模块：提示词扩写为剧本 JSON
├── director.py              # 导演模块：剧本拆分为镜头脚本 JSON
├── actor.py                 # 视频生成主模块：参考图、首帧、视频片段生成
├── editor.py                # 剪辑模块：拼接视频片段为最终成片
├── memory.py                # 全局记忆池：保存 story/background/characters
├── reference.py             # 角色参考图生成模块
├── seedream_t2i.py          # Seedream 文生图测试脚本
├── seedream_i2i.py          # Seedream 图生图测试脚本
├── seedance.py              # Seedance 图生视频测试脚本
├── doubao.py                # 豆包文本模型调用测试脚本
├── zimage.py                # 本地 Z-Image-Turbo 生成测试脚本
└── Output/
    ├── video_scripts.json   # 编剧阶段输出
    ├── video_director.json  # 导演阶段输出
    ├── reference.png        # actor.py 生成的人物一致性参考图
    ├── *_first_frame.png    # 每个视频片段的首帧图片
    ├── *.mp4                # 每个镜头片段视频
    ├── concat_list.txt      # ffmpeg 拼接列表
    └── final_results.mp4    # 最终拼接成片
```

## 环境要求

- Python 3.10+
- `ffmpeg`
- 可访问火山方舟 / Ark API 的网络环境
- 有效的 `ARK_API_KEY`

Python 依赖主要包括：

```bash
pip install openai requests
```

如果需要运行 `zimage.py`，还需要额外安装深度学习相关依赖，例如：

```bash
pip install torch diffusers
```

并确保机器具备可用 CUDA 环境。

## 配置 API Key

推荐通过环境变量配置 API Key：

```bash
export ARK_API_KEY="你的 Ark API Key"
```

项目中的主流程类默认会读取 `ARK_API_KEY`。部分测试脚本中目前存在硬编码 API Key，实际使用或提交代码前建议改为统一读取环境变量，避免密钥泄露。

## 快速开始

### 1. 生成剧本资料

运行：

```bash
python scriptwriter.py
```

默认会使用脚本中的提示词：

```text
神情忧郁的女子在湖泊上划船
```

输出文件：

```text
Output/video_scripts.json
```

该文件包含：

- `story`：故事标题、类型、梗概、主题、情绪基调等
- `background`：时间、地点、氛围、视觉风格、光线等
- `characters`：角色外貌、性格、动机、情绪弧线等
- `metadata`：用户原始提示词、生成时间、模型信息等

### 2. 生成导演分镜

运行：

```bash
python director.py
```

输入文件：

```text
Output/video_scripts.json
```

输出文件：

```text
Output/video_director.json
```

每个镜头片段包含：

- `镜头序号`
- `镜头模式`：`长镜头` 或 `分镜`
- `镜头组序号`
- `组内片段序号`
- `是否需要拼接`
- `具体故事`
- `景别`：`远景`、`中景`、`特写`

### 3. 生成视频片段

运行：

```bash
python actor.py
```

该步骤会：

1. 读取 `Output/video_scripts.json` 中的人物设定。
2. 生成人物参考图 `Output/reference.png`。
3. 读取 `Output/video_director.json` 中的镜头列表。
4. 为每个镜头生成首帧图片。
5. 调用 Seedance 生成对应视频片段。
6. 将视频片段保存到 `Output/`。

视频片段命名格式：

```text
group_组号_part_组内片段号_shot_镜头号.mp4
```

例如：

```text
Output/group_003_part_001_shot_005.mp4
```

对应首帧图片：

```text
Output/group_003_part_001_shot_005_first_frame.png
```

### 4. 拼接最终视频

运行：

```bash
python editor.py
```

该步骤会根据 `Output/video_director.json` 中的全局镜头顺序生成拼接列表，并输出最终视频：

```text
Output/final_results.mp4
```

如果直接无损拼接失败，`editor.py` 会自动尝试重新编码拼接。

## 推荐完整流程

```bash
export ARK_API_KEY="你的 Ark API Key"

python scriptwriter.py
python director.py
python actor.py
python editor.py
```

最终结果位于：

```text
Output/final_results.mp4
```

## 核心模块说明

### `scriptwriter.py`

负责将用户输入扩展为完整短片剧本资料。它只生成核心叙事信息，不生成镜头列表。

主要输出字段：

- `story`
- `background`
- `characters`

主要函数：

- `generate_script()`
- `generate_script_and_memory()`
- `save_script_json()`

### `memory.py`

提供轻量级全局记忆池 `MemoryPool`，用于保存编剧阶段生成的故事、背景、角色和元信息。

主要功能：

- 注入剧本信息
- 按角色名查找角色设定
- 输出完整上下文供后续模块使用

### `director.py`

负责将 `video_scripts.json` 转换为视频生成所需的镜头脚本。它会校验输出 JSON 的结构，确保镜头序号、镜头模式、镜头组和景别合法。

主要输出：

```text
Output/video_director.json
```

### `actor.py`

项目中最核心的视频生成模块。它负责：

- 生成人物一致性参考图
- 生成每个镜头的首帧图
- 创建 Seedance 视频生成任务
- 轮询任务状态
- 下载视频片段
- 对长镜头组进行顺序连续生成

默认配置：

```python
SEEDREAM_MODEL = "doubao-seedream-5-0-260128"
SEEDANCE_MODEL = "doubao-seedance-1-5-pro-251215"
DURATION = 5
GROUP_WORKERS = 3
```

### `editor.py`

负责使用 `ffmpeg` 拼接所有生成的视频片段。它会先尝试直接拷贝流拼接：

```bash
ffmpeg -f concat -safe 0 -i Output/concat_list.txt -c copy Output/final_results.mp4
```

如果失败，会自动改用重新编码方式拼接。

### `reference.py`

独立的角色参考图生成模块，会读取 `Output/video_scripts.json` 并输出：

```text
Output/character.png
```

当前 `actor.py` 内部也包含参考图生成逻辑，并默认输出：

```text
Output/reference.png
```

### 测试脚本

以下脚本主要用于单独测试不同能力：

- `doubao.py`：测试豆包文本模型调用。
- `seedream_t2i.py`：测试 Seedream 文生图。
- `seedream_i2i.py`：测试 Seedream 图生图。
- `seedance.py`：测试 Seedance 图生视频。
- `zimage.py`：测试本地 `Tongyi-MAI/Z-Image-Turbo` 图像生成。

## 输出文件说明

| 文件 | 说明 |
| --- | --- |
| `Output/video_scripts.json` | 编剧阶段生成的剧本与角色资料 |
| `Output/video_director.json` | 导演阶段生成的镜头列表 |
| `Output/reference.png` | 角色一致性参考图 |
| `Output/*_first_frame.png` | 每个镜头片段的起始帧 |
| `Output/group_*.mp4` | 每个镜头片段生成的视频 |
| `Output/concat_list.txt` | ffmpeg concat 输入列表 |
| `Output/final_results.mp4` | 最终成片 |

## 注意事项

1. **API Key 安全**
   - 建议移除脚本中的硬编码密钥，统一使用 `ARK_API_KEY` 环境变量。

2. **视频生成耗时**
   - Seedance 视频生成是异步任务，`actor.py` 会轮询任务状态。
   - 镜头越多，总耗时越长。

3. **长镜头连续性**
   - 同一个镜头组内，后续片段会使用上一段视频的最后一帧作为首帧，以增强连续感。

4. **ffmpeg 必须可用**
   - `actor.py` 需要用 `ffmpeg` 抽取上一片段最后一帧。
   - `editor.py` 需要用 `ffmpeg` 拼接最终视频。

5. **输出目录**
   - 默认所有中间产物与最终视频都会写入 `Output/`。

## 常见问题

### 报错：`请先设置环境变量 ARK_API_KEY`

请先执行：

```bash
export ARK_API_KEY="你的 Ark API Key"
```

然后重新运行脚本。

### 报错：`未找到 ffmpeg，请先安装 ffmpeg`

需要安装 `ffmpeg`。

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install ffmpeg
```

macOS：

```bash
brew install ffmpeg
```

### 拼接失败怎么办？

`editor.py` 会先尝试无损拼接，如果失败会自动切换到重新编码拼接。若仍然失败，请检查：

- `Output/video_director.json` 中的镜头顺序是否连续。
- `Output/` 中是否缺少对应 `group_*.mp4` 文件。
- 每个视频片段是否可以正常播放。

## 后续改进建议

- 将所有硬编码 API Key 改为环境变量读取。
- 增加统一入口脚本，例如 `main.py`，一键执行完整流程。
- 增加 `requirements.txt` 或 `pyproject.toml` 管理依赖。
- 增加命令行参数，支持自定义提示词、输出目录、模型、并发数和视频时长。
- 增加日志系统，替代直接 `print`。
- 对失败的视频生成任务增加重试机制。
- 将中间文件与最终文件分目录保存，便于管理。
