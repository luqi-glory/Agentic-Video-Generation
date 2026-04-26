"""Scriptwriter agent for expanding a user prompt into core script memory."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from openai import OpenAI

from memory import MemoryPool, inject_script_to_global_memory

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-character-251128"
DEFAULT_USER_PROMPT = "神情忧郁的女子在湖泊上划船"


SYSTEM_PROMPT = """你是电影级视频生成工作流中的 scriptwriter。
你的职责只有一个：把用户输入的任意文本提示词，扩写成供后续 director 使用的核心剧本资料。
你只负责创作 story、background、characters，不负责分镜、不负责镜头序号、不负责景别、不负责每段时长、不负责字幕。
输出必须是严格 JSON 对象，不要输出 Markdown，不要解释，不要添加 JSON 以外的任何文字。"""


USER_PROMPT_TEMPLATE = """请将下面的用户原始提示词扩写为完整短片剧本资料。

用户原始提示词：{user_prompt}

工作流上下文：
- scriptwriter 只负责生成剧本核心记忆。
- director 会在下一步从 memory pool 读取 story、background、characters。
- director 会把剧本拆成约每段 5 秒的镜头，并决定镜头序号、镜头内容、景别。
- 因此你不要输出镜头列表、分镜表、shot、scene、duration、camera size 等导演字段。

泛化创作要求：
- 用户提示词可能是人物、事件、地点、风格、动作、概念、世界观或复杂剧情，请根据输入自行补全缺失信息。
- 必须保留用户提示词中的核心主体、动作、情绪、地点、风格或限制。
- 如果用户提示词很短，请扩写为适合 1 分钟及以上视频的完整故事。
- 如果用户提示词已经很复杂，请梳理并强化其剧情逻辑、背景规则和人物动机。
- 故事要具有电影感、可视化细节、情绪变化和明确的起承转合。
- 不要过度增加无关角色或无关设定。

输出格式要求：
必须输出合法 JSON，且顶层只能包含以下三个字段：
{{
  "story": {{
    "title": "短片片名",
    "genre": "类型，例如剧情/科幻/悬疑/奇幻/纪录感等",
    "logline": "一句话故事梗概",
    "theme": "主题表达",
    "tone": "整体情绪与影调",
    "duration_target": "建议总时长，例如 60-90 秒或 90-120 秒",
    "synopsis": "完整剧情梗概，包含起因、发展、转折、高潮、结尾",
    "narrative_arc": {{
      "beginning": "开端",
      "development": "发展",
      "turning_point": "转折",
      "climax": "高潮",
      "ending": "结尾"
    }}
  }},
  "background": {{
    "time": "时间设定",
    "location": "主要地点与空间关系",
    "world_setting": "现实/幻想/科幻等世界设定，以及必要规则",
    "atmosphere": "环境氛围",
    "visual_style": "摄影、美术、色彩、质感",
    "lighting": "主要光线设计",
    "soundscape": "环境声与音乐方向",
    "key_objects": [
      {{
        "name": "关键物件或视觉元素",
        "description": "外观与作用",
        "symbolic_meaning": "如无象征意义可写为空字符串"
      }}
    ]
  }},
  "characters": [
    {{
      "name": "人物姓名或称谓",
      "role": "人物在故事中的功能",
      "age": "年龄段，可为未知",
      "appearance": "稳定外貌、服装、姿态等视觉连续性信息",
      "personality": "性格特征",
      "backstory": "与剧情有关的前史",
      "motivation": "当前目标或内在驱动力",
      "conflict": "内在或外在冲突",
      "emotional_arc": "从开端到结尾的情绪变化"
    }}
  ]
}}

硬性限制：
- 顶层只能有 story、background、characters。
- characters 必须是数组，即使只有一个人物。
- 不要输出 notes。
- 不要输出 director_hint、actor_hint。
- 不要输出镜头拆分、镜头序号、景别、每镜头 5 秒等字段。
- 不要把字段名翻译成中文，保持上述英文字段名。
"""


class ScriptwriterError(RuntimeError):
    """Raised when script generation or parsing fails."""


class Scriptwriter:
    """Expand user text into story, background, and character memory."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = ARK_BASE_URL,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or os.getenv("ARK_API_KEY"),
        )

    def write_script(self, user_prompt: str) -> Dict[str, Any]:
        """Call the external API and return parsed script data."""

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(user_prompt=user_prompt),
                },
            ],
            temperature=0.8,
        )
        content = completion.choices[0].message.content
        if not content:
            raise ScriptwriterError("外部 API 返回内容为空")
        return self._parse_script_json(content)

    def write_and_inject(self, user_prompt: str) -> MemoryPool:
        """Generate script data and inject it into the global memory pool."""

        script = self.write_script(user_prompt)
        return inject_script_to_global_memory(
            user_prompt=user_prompt,
            story=script["story"],
            background=script["background"],
            characters=script["characters"],
            metadata={"scriptwriter_model": self.model},
        )

    @staticmethod
    def _parse_script_json(content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ScriptwriterError(f"无法解析剧本 JSON: {exc}\n原始返回: {content}") from exc

        Scriptwriter._validate_script(data)
        return data

    @staticmethod
    def _validate_script(data: Dict[str, Any]) -> None:
        allowed = {"story", "background", "characters"}
        missing = [field for field in allowed if field not in data]
        extra = [field for field in data if field not in allowed]
        if missing:
            raise ScriptwriterError(f"剧本缺少必要字段: {', '.join(missing)}")
        if extra:
            raise ScriptwriterError(f"剧本包含 scriptwriter 不应输出的字段: {', '.join(extra)}")
        if not isinstance(data["story"], dict):
            raise ScriptwriterError("story 字段必须是对象")
        if not isinstance(data["background"], dict):
            raise ScriptwriterError("background 字段必须是对象")
        if not isinstance(data["characters"], list):
            raise ScriptwriterError("characters 字段必须是数组")


def generate_script(user_prompt: str = DEFAULT_USER_PROMPT) -> Dict[str, Any]:
    """Generate structured script data only."""

    return Scriptwriter().write_script(user_prompt)


def generate_script_and_memory(user_prompt: str = DEFAULT_USER_PROMPT) -> MemoryPool:
    """Generate script data and fill global memory."""

    return Scriptwriter().write_and_inject(user_prompt)


def print_script(script: Dict[str, Any]) -> None:
    """Pretty-print generated script data."""

    print(json.dumps(script, ensure_ascii=False, indent=2))


def save_script_json(memory: MemoryPool, output_path: str = "./Output/video_scripts.json") -> str:
    """Save generated memory context as a JSON file."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(memory.to_dict(), file, ensure_ascii=False, indent=2)
    return output_path


if __name__ == "__main__":
    prompt = DEFAULT_USER_PROMPT
    ARK_API_KEY = "yours"
    scriptwriter = Scriptwriter(api_key=ARK_API_KEY)
    memory = scriptwriter.write_and_inject(prompt)
    output_file = save_script_json(memory)
    print(json.dumps(memory.to_dict(), ensure_ascii=False, indent=2))
    print(f"\n剧本 JSON 已保存到: {output_file}")
