"""Reference image generator for character consistency.

This module reads Output/video_scripts.json, extracts character settings, and
uses Seedream to generate Output/character.png as the visual reference for later
video generation.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests
from openai import OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_INPUT_PATH = "./Output/video_scripts.json"
DEFAULT_OUTPUT_PATH = "./Output/character.png"
DEFAULT_SIZE = "2K"


class ReferenceImageError(RuntimeError):
    """Raised when reference image generation fails."""


class ReferenceImageGenerator:
    """Generate a character reference image from script characters."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = ARK_BASE_URL,
        api_key: str | None = None,
        size: str = DEFAULT_SIZE,
    ) -> None:
        self.model = model
        self.size = size
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or os.getenv("ARK_API_KEY"),
        )

    def generate_from_file(
        self,
        input_path: str = DEFAULT_INPUT_PATH,
        output_path: str = DEFAULT_OUTPUT_PATH,
    ) -> str:
        """Read script JSON, generate reference image, and save it."""

        script_data = load_json(input_path)
        characters = self._extract_characters(script_data)
        prompt = build_reference_prompt(characters, script_data.get("background", {}))
        image_url = self.generate_image_url(prompt)
        download_image(image_url, output_path)
        return output_path

    def generate_image_url(self, prompt: str) -> str:
        """Call Seedream and return the generated image URL."""

        response = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=self.size,
            response_format="url",
            extra_body={"watermark": False},
        )
        if not response.data or not response.data[0].url:
            raise ReferenceImageError("Seedream 没有返回有效图片 URL")
        return response.data[0].url

    @staticmethod
    def _extract_characters(script_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        characters = script_data.get("characters")
        if not isinstance(characters, list) or not characters:
            raise ReferenceImageError("video_scripts.json 中缺少非空 characters 数组")
        return characters


def build_reference_prompt(characters: List[Dict[str, Any]], background: Dict[str, Any]) -> str:
    """Build a Seedream prompt for character reference image generation."""

    character_blocks = []
    for index, character in enumerate(characters, start=1):
        character_blocks.append(
            "\n".join(
                [
                    f"角色 {index}：{character.get('name', '未命名角色')}",
                    f"身份：{character.get('role', '')}",
                    f"年龄：{character.get('age', '')}",
                    f"外貌与服装：{character.get('appearance', '')}",
                    f"性格气质：{character.get('personality', '')}",
                    f"情绪弧线：{character.get('emotional_arc', '')}",
                ]
            )
        )

    visual_style = background.get("visual_style", "电影感写实风格")
    lighting = background.get("lighting", "柔和自然光")
    atmosphere = background.get("atmosphere", "具有叙事感的安静氛围")

    return f"""根据以下人物设定生成一张电影级角色参考图，用于后续视频生成保持角色一致。

人物设定：
{chr(10).join(character_blocks)}

画面要求：
- 生成角色设定参考图，不要生成剧情分镜。
- 如果只有一个角色，生成单人半身或三分之二身参考图。
- 如果有多个角色，将主要角色放在画面中心，其余角色作为辅助参考，但不要拥挤。
- 角色面部、发型、服装、身形、气质要清晰稳定，便于后续视频生成复用。
- 背景保持简洁，可以带有轻微环境暗示，但不要抢占角色主体。
- 风格：{visual_style}。
- 光线：{lighting}。
- 氛围：{atmosphere}。
- 高质量电影剧照质感，真实细腻，构图干净，主体清晰。
- 不要文字，不要水印，不要 logo，不要边框，不要多余肢体，不要畸形面部。
""".strip()


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON from file."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def download_image(image_url: str, output_path: str) -> str:
    """Download image URL to output path."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    response = requests.get(image_url, timeout=120)
    response.raise_for_status()
    with open(output_path, "wb") as file:
        file.write(response.content)
    return output_path


def generate_character_reference(
    input_path: str = DEFAULT_INPUT_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> str:
    """Convenience function for generating Output/character.png."""

    return ReferenceImageGenerator().generate_from_file(
        input_path=input_path,
        output_path=output_path,
    )


if __name__ == "__main__":
    ARK_API_KEY = "yours"
    generator = ReferenceImageGenerator(api_key=ARK_API_KEY)
    saved_path = generator.generate_from_file()
    print(f"角色参考图已保存到: {saved_path}")
