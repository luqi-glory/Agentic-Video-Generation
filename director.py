"""Director agent for converting script memory into shot-level video prompts."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-character-251128"
DEFAULT_INPUT_PATH = "./Output/video_scripts.json"
DEFAULT_OUTPUT_PATH = "./Output/video_director.json"
ALLOWED_SHOT_SIZES = {"远景", "中景", "特写"}

SYSTEM_PROMPT = """你是电影级视频生成工作流中的 director。
你的职责是读取 scriptwriter 生成的 story、background、characters，将其转录为可供 video_generator 使用的导演拍摄脚本。
你需要区分两种组织方式：长镜头与分镜。
长镜头表示叙事上是一个连续镜头，但因为单段视频约 5 秒，需要拆成多个可拼接片段。
分镜表示每个 5 秒片段就是独立镜头，下一个片段进入新的场景、构图或动作单元。
至少拆出2个及以上的分镜头。
只输出严格 JSON，不要输出 Markdown，不要解释。"""

USER_PROMPT_TEMPLATE = """请根据以下剧本资料生成导演拍摄脚本。

剧本资料：
{script_context}

核心概念：
1. 长镜头：
   - 叙事上属于同一个连续镜头，例如一个约 10 秒或 15 秒的连续动作。
   - 但 video_generator 单段最多约 5 秒，所以需要拆成多个 5 秒片段。
   - 这些片段后续会由 editor 拼接成一个完整长镜头。
   - 同一长镜头的多个片段必须使用相同的 "镜头组序号"，并用 "组内片段序号" 标注顺序。
2. 分镜：
   - 每个片段就是一个独立镜头，长度最多约 5 秒。
   - 下一个片段应该进入新的场景、构图、动作重点或情绪阶段。
   - 分镜片段不需要与其他片段拼接成长镜头。

输出要求：
1. 输出必须是合法 JSON 对象。
2. 顶层只能包含 shots 字段。
3. shots 必须是数组。
4. 每个镜头对象只能包含以下字段：
   - "镜头序号"：从 1 开始递增的全局片段序号。
   - "镜头模式"：只能是 "长镜头" 或 "分镜"。
   - "镜头组序号"：用于标注叙事镜头组。同一长镜头拆出的多个片段使用相同组号；独立分镜使用自己的组号。
   - "组内片段序号"：同一镜头组内从 1 开始递增；独立分镜固定为 1。
   - "是否需要拼接"：长镜头片段为 true，独立分镜为 false。
   - "具体故事"：该 5 秒片段的具体画面与动作描述，后续会直接作为 video_generator 的提示词主体。
   - "景别"：只能从 "远景"、"中景"、"特写" 中选择一个。
5. 每个输出对象仍然代表一个约 5 秒视频生成片段。
6. 若某个动作或情绪需要 10 秒以上连续呈现，应使用长镜头模式拆成多个片段。
7. 若叙事需要跳转视角、切换构图、切换环境重点，应使用分镜模式。
8. 镜头之间要形成连续叙事，不能重复描述。
9. 具体故事必须融合人物外貌、动作、环境、光线、情绪和关键物件。
10. 不要输出字幕、旁白、音乐字段、镜头运动字段、时长字段或其他额外字段。

JSON 示例：
{{
  "shots": [
    {{
      "镜头序号": 1,
      "镜头模式": "长镜头",
      "镜头组序号": 1,
      "组内片段序号": 1,
      "是否需要拼接": true,
      "具体故事": "黄昏的湖泊被冷色薄雾笼罩，远处树影环绕水面，穿深色长裙的女子站在岸边凝视湖面，木船停在她身旁，整体氛围安静而忧伤。",
      "景别": "远景"
    }},
    {{
      "镜头序号": 2,
      "镜头模式": "长镜头",
      "镜头组序号": 1,
      "组内片段序号": 2,
      "是否需要拼接": true,
      "具体故事": "延续同一湖岸画面，女子缓慢走向木船并扶住船沿，黄昏侧光掠过她忧郁的脸，动作与上一片段自然衔接。",
      "景别": "远景"
    }},
    {{
      "镜头序号": 3,
      "镜头模式": "分镜",
      "镜头组序号": 2,
      "组内片段序号": 1,
      "是否需要拼接": false,
      "具体故事": "切换到女子坐进小船的中景，她解开绳索，低头握住船桨，湖水在船边轻轻晃动。",
      "景别": "中景"
    }}
  ]
}}
"""


class DirectorError(RuntimeError):
    """Raised when director generation or parsing fails."""


class Director:
    """Convert scriptwriter output into shot-level director JSON."""

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

    def generate_director_script(self, script_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Call the external API and return parsed director script data."""

        script_context = json.dumps(
            {
                "story": script_data.get("story", {}),
                "background": script_data.get("background", {}),
                "characters": script_data.get("characters", []),
            },
            ensure_ascii=False,
            indent=2,
        )
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(script_context=script_context),
                },
            ],
            temperature=0.7,
        )
        content = completion.choices[0].message.content
        if not content:
            raise DirectorError("外部 API 返回内容为空")
        return self._parse_director_json(content)

    def generate_from_file(
        self,
        input_path: str = DEFAULT_INPUT_PATH,
        output_path: str = DEFAULT_OUTPUT_PATH,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Read video_scripts.json, generate shots, and save video_director.json."""

        script_data = load_json(input_path)
        self._validate_script_input(script_data)
        director_data = self.generate_director_script(script_data)
        save_json(director_data, output_path)
        return director_data

    @staticmethod
    def _parse_director_json(content: str) -> Dict[str, List[Dict[str, Any]]]:
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise DirectorError(f"无法解析导演脚本 JSON: {exc}\n原始返回: {content}") from exc

        Director._validate_director_output(data)
        return data

    @staticmethod
    def _validate_script_input(data: Dict[str, Any]) -> None:
        missing = [field for field in ("story", "background", "characters") if field not in data]
        if missing:
            raise DirectorError(f"输入剧本缺少字段: {', '.join(missing)}")
        if not isinstance(data["story"], dict):
            raise DirectorError("输入字段 story 必须是对象")
        if not isinstance(data["background"], dict):
            raise DirectorError("输入字段 background 必须是对象")
        if not isinstance(data["characters"], list):
            raise DirectorError("输入字段 characters 必须是数组")

    @staticmethod
    def _validate_director_output(data: Dict[str, Any]) -> None:
        if set(data.keys()) != {"shots"}:
            raise DirectorError("导演脚本顶层只能包含 shots 字段")
        if not isinstance(data["shots"], list) or not data["shots"]:
            raise DirectorError("shots 必须是非空数组")

        required = {"镜头序号", "镜头模式", "镜头组序号", "组内片段序号", "是否需要拼接", "具体故事", "景别"}
        group_segment_counter: Dict[int, int] = {}
        for index, shot in enumerate(data["shots"], start=1):
            if set(shot.keys()) != required:
                raise DirectorError(f"第 {index} 个镜头字段必须且只能是: {', '.join(required)}")
            if shot["镜头序号"] != index:
                raise DirectorError(f"第 {index} 个镜头的镜头序号应为 {index}")
            if shot["镜头模式"] not in {"长镜头", "分镜"}:
                raise DirectorError(f"第 {index} 个镜头的镜头模式必须是长镜头/分镜")
            if not isinstance(shot["镜头组序号"], int) or shot["镜头组序号"] < 1:
                raise DirectorError(f"第 {index} 个镜头的镜头组序号必须是正整数")
            if not isinstance(shot["组内片段序号"], int) or shot["组内片段序号"] < 1:
                raise DirectorError(f"第 {index} 个镜头的组内片段序号必须是正整数")
            if not isinstance(shot["是否需要拼接"], bool):
                raise DirectorError(f"第 {index} 个镜头的是否需要拼接必须是布尔值")
            if shot["镜头模式"] == "长镜头" and not shot["是否需要拼接"]:
                raise DirectorError(f"第 {index} 个长镜头片段必须标注是否需要拼接为 true")
            if shot["镜头模式"] == "分镜" and shot["是否需要拼接"]:
                raise DirectorError(f"第 {index} 个分镜片段必须标注是否需要拼接为 false")
            if shot["镜头模式"] == "分镜" and shot["组内片段序号"] != 1:
                raise DirectorError(f"第 {index} 个分镜片段的组内片段序号必须为 1")

            group_id = shot["镜头组序号"]
            expected_segment_id = group_segment_counter.get(group_id, 0) + 1
            if shot["组内片段序号"] != expected_segment_id:
                raise DirectorError(
                    f"第 {index} 个镜头的组内片段序号应为 {expected_segment_id}"
                )
            group_segment_counter[group_id] = expected_segment_id

            if not isinstance(shot["具体故事"], str) or not shot["具体故事"].strip():
                raise DirectorError(f"第 {index} 个镜头的具体故事不能为空")
            if shot["景别"] not in ALLOWED_SHOT_SIZES:
                raise DirectorError(f"第 {index} 个镜头的景别必须是远景/中景/特写")


def load_json(path: str) -> Dict[str, Any]:
    """Load a JSON file."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data: Dict[str, Any], path: str) -> str:
    """Save data as formatted JSON."""

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def generate_video_director_json(
    input_path: str = DEFAULT_INPUT_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> Dict[str, List[Dict[str, Any]]]:
    """Convenience function for generating Output/video_director.json."""

    return Director().generate_from_file(input_path=input_path, output_path=output_path)


if __name__ == "__main__":
    ARK_API_KEY = "yours"
    director = Director(api_key=ARK_API_KEY)
    result = director.generate_from_file()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n导演分镜 JSON 已保存到: {DEFAULT_OUTPUT_PATH}")
