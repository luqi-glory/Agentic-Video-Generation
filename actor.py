"""Group-aware actor: generate videos from Output/video_director.json."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from openai import OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
SEEDANCE_TASK_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
SEEDREAM_MODEL = "doubao-seedream-5-0-260128"
SEEDANCE_MODEL = "doubao-seedance-1-5-pro-251215"
DIRECTOR_PATH = "./Output/video_director.json"
SCRIPT_PATH = "./Output/video_scripts.json"
OUTPUT_DIR = "./Output"
REFERENCE_PATH = "./Output/reference.png"
DURATION = 5
GROUP_WORKERS = 3
SHOT_SIZES = {"远景", "中景", "特写"}


class ActorError(RuntimeError):
    """Actor generation error."""


@dataclass(frozen=True)
class Shot:
    shot_id: int
    mode: str
    group_id: int
    segment_id: int
    need_stitch: bool
    story: str
    shot_size: str

    @property
    def stem(self) -> str:
        return f"group_{self.group_id:03d}_part_{self.segment_id:03d}_shot_{self.shot_id:03d}"


class Actor:
    """Generate groups concurrently while keeping each group linear."""

    def __init__(
        self,
        api_key: str | None = None,
        duration: int = DURATION,
        group_workers: int = GROUP_WORKERS,
        poll_interval: int = 5,
    ) -> None:
        self.api_key = api_key or os.getenv("ARK_API_KEY")
        if not self.api_key:
            raise ActorError("请先设置环境变量 ARK_API_KEY")
        self.duration = duration
        self.group_workers = group_workers
        self.poll_interval = poll_interval
        self.seedream_client = OpenAI(base_url=ARK_BASE_URL, api_key=self.api_key)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def generate_from_file(
        self,
        director_path: str = DIRECTOR_PATH,
        script_path: str = SCRIPT_PATH,
        output_dir: str = OUTPUT_DIR,
        reference_path: str = REFERENCE_PATH,
    ) -> List[Dict[str, Any]]:
        shots = load_shots(director_path)
        groups = group_shots(shots)
        os.makedirs(output_dir, exist_ok=True)
        self.generate_reference_image(script_path, reference_path)
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=self.group_workers) as executor:
            futures = {
                executor.submit(self.generate_group, group_id, group, output_dir, reference_path): group_id
                for group_id, group in groups.items()
            }
            for future in as_completed(futures):
                group_id = futures[future]
                try:
                    results.extend(future.result())
                except Exception as exc:
                    raise ActorError(f"镜头组 {group_id} 生成失败: {exc}") from exc
        return sorted(results, key=lambda item: item["镜头序号"])

    def generate_group(self, group_id: int, group: List[Shot], output_dir: str, reference_path: str) -> List[Dict[str, Any]]:
        print(f"开始生成镜头组 {group_id}，共 {len(group)} 个片段")
        results: List[Dict[str, Any]] = []
        first_frame_path = ""

        for shot in group:
            first_frame_path = os.path.join(output_dir, f"{shot.stem}_first_frame.png")
            if shot.segment_id == 1:
                self.generate_first_frame_i2i(shot, reference_path, first_frame_path)
            else:
                extract_last_frame(results[-1]["video_path"], first_frame_path)

            video_path = os.path.join(output_dir, f"{shot.stem}.mp4")
            task_id = self.create_seedance_task(shot, first_frame_path)
            video_url = extract_video_url(self.poll_task(task_id))
            download_video(video_url, video_path)
            results.append(
                {
                    "镜头序号": shot.shot_id,
                    "镜头模式": shot.mode,
                    "镜头组序号": shot.group_id,
                    "组内片段序号": shot.segment_id,
                    "是否需要拼接": shot.need_stitch,
                    "景别": shot.shot_size,
                    "具体故事": shot.story,
                    "first_frame_path": first_frame_path,
                    "video_path": video_path,
                    "seedance_task_id": task_id,
                }
            )
        print(f"镜头组 {group_id} 生成完成")
        return results

    def generate_reference_image(self, script_path: str, output_path: str) -> str:
        characters = load_characters(script_path)
        response = self.seedream_client.images.generate(
            model=SEEDREAM_MODEL,
            prompt=reference_prompt(characters),
            size="2K",
            response_format="url",
            extra_body={"watermark": False},
        )
        if not response.data or not response.data[0].url:
            raise ActorError("Seedream 没有返回人物参考图 URL")
        return download_binary(response.data[0].url, output_path, "人物参考图")

    def generate_first_frame_i2i(self, shot: Shot, reference_path: str, output_path: str) -> str:
        response = self.seedream_client.images.generate(
            model=SEEDREAM_MODEL,
            prompt=seedream_prompt(shot),
            size="2K",
            response_format="url",
            extra_body={"image": image_to_data_url(reference_path), "watermark": False},
        )
        if not response.data or not response.data[0].url:
            raise ActorError(f"镜头 {shot.shot_id} 的 Seedream i2i 没有返回图片 URL")
        return download_binary(response.data[0].url, output_path, "首帧图片")

    def create_seedance_task(self, shot: Shot, image_path: str) -> str:
        payload = {
            "model": SEEDANCE_MODEL,
            "content": [
                {"type": "text", "text": self.seedance_prompt(shot)},
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
            ],
        }
        response = requests.post(SEEDANCE_TASK_URL, headers=self.headers, json=payload, timeout=120)
        response.raise_for_status()
        task_id = response.json().get("id")
        if not task_id:
            raise ActorError(f"镜头 {shot.shot_id} 创建 Seedance 任务失败: {response.json()}")
        print(f"镜头 {shot.shot_id:03d} Seedance 任务创建成功: {task_id}")
        return task_id

    def poll_task(self, task_id: str) -> Dict[str, Any]:
        while True:
            response = requests.get(f"{SEEDANCE_TASK_URL}/{task_id}", headers=self.headers, timeout=120)
            response.raise_for_status()
            result = response.json()
            status = result.get("status")
            print(f"任务 {task_id} 当前状态: {status}")
            if status == "succeeded":
                return result
            if status == "failed":
                raise ActorError(f"Seedance 任务失败: {result}")
            time.sleep(self.poll_interval)

    def seedance_prompt(self, shot: Shot) -> str:
        continuity = "与输入首帧自然衔接，保持角色、服装、发型、环境光线一致。"
        if shot.segment_id > 1:
            continuity = "严格延续输入首帧的姿态、位置、光线和环境，作为同一镜头组的连续片段。"
        return (
            f"{shot.story}\n景别：{shot.shot_size}。{continuity}"
            "统一生成 4:3 横向画幅，所有视频片段保持相同 4:3 构图比例。"
            "电影级画面，真实自然运动，情绪连贯，避免人物变形，避免文字和水印。"
            f" --duration {self.duration} --camerafixed false --watermark false"
        )


def reference_prompt(characters: List[Dict[str, Any]]) -> str:
    character_text = json.dumps(characters, ensure_ascii=False, indent=2)
    return (
        "根据以下 characters 人物设定生成一张人物一致性参考图。\n"
        f"characters:\n{character_text}\n"
        "画面必须是单人或主要角色的正面全身照，人物自然站立，动作极少，姿态稳定。"
        "脸部细节必须清晰，五官明确，发型、服装、身形、气质必须稳定可识别。"
        "如果 characters 中有多个角色，只生成最主要角色，避免多人同框。"
        "背景使用简洁纯净或轻微环境暗示，不要出现复杂剧情动作，不要划船，不要奔跑，不要夸张姿势。"
        "画面比例必须统一为 4:3 横向画幅，人物居中，完整身体入画，头顶和脚底保留适度空间。"
        "电影级写实质感，柔和自然光，主体居中，完整身体入画，适合作为后续 image-to-image 的角色参考图。"
        "不要文字，不要水印，不要 logo，不要边框，不要多余肢体，不要畸形面部。"
    )


def seedream_prompt(shot: Shot) -> str:
    return (
        f"基于输入的人物参考图生成该视频镜头组的首帧：{shot.story}\n景别：{shot.shot_size}。"
        "必须保持参考图中的人物身份、脸部特征、发型、服装、身形和气质一致。"
        "只生成一张电影级首帧画面，不要分镜图，不要拼贴。"
        "画面比例必须统一为 4:3 横向画幅，并与后续视频保持相同 4:3 构图比例。"
        "画面适合作为 image-to-video 起始帧，主体清晰，构图稳定，动作处在镜头开始状态。"
        "真实电影剧照质感，光线自然，无文字，无水印，无 logo，无边框。"
    )


def load_characters(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as file:
        characters = json.load(file).get("characters")
    if not isinstance(characters, list) or not characters:
        raise ActorError("video_scripts.json 中缺少非空 characters 数组")
    return characters


def load_shots(path: str) -> List[Shot]:
    with open(path, "r", encoding="utf-8") as file:
        raw_shots = json.load(file).get("shots")
    if not isinstance(raw_shots, list) or not raw_shots:
        raise ActorError("video_director.json 中缺少非空 shots 数组")

    shots: List[Shot] = []
    for index, item in enumerate(raw_shots, start=1):
        shot = Shot(
            shot_id=item.get("镜头序号"),
            mode=item.get("镜头模式"),
            group_id=item.get("镜头组序号"),
            segment_id=item.get("组内片段序号"),
            need_stitch=item.get("是否需要拼接"),
            story=item.get("具体故事"),
            shot_size=item.get("景别"),
        )
        validate_shot(shot, index)
        shots.append(shot)
    return shots


def validate_shot(shot: Shot, expected_id: int) -> None:
    if shot.shot_id != expected_id:
        raise ActorError(f"第 {expected_id} 个镜头序号不连续")
    if shot.mode not in {"长镜头", "分镜"}:
        raise ActorError(f"第 {expected_id} 个镜头模式必须是长镜头/分镜")
    if not isinstance(shot.group_id, int) or shot.group_id < 1:
        raise ActorError(f"第 {expected_id} 个镜头组序号必须是正整数")
    if not isinstance(shot.segment_id, int) or shot.segment_id < 1:
        raise ActorError(f"第 {expected_id} 个组内片段序号必须是正整数")
    if not isinstance(shot.need_stitch, bool):
        raise ActorError(f"第 {expected_id} 个是否需要拼接必须是布尔值")
    if not isinstance(shot.story, str) or not shot.story.strip():
        raise ActorError(f"第 {expected_id} 个具体故事不能为空")
    if shot.shot_size not in SHOT_SIZES:
        raise ActorError(f"第 {expected_id} 个景别必须是远景/中景/特写")


def group_shots(shots: List[Shot]) -> Dict[int, List[Shot]]:
    groups: Dict[int, List[Shot]] = {}
    for shot in shots:
        groups.setdefault(shot.group_id, []).append(shot)
    for group_id, group in groups.items():
        group.sort(key=lambda shot: shot.segment_id)
        for expected_segment_id, shot in enumerate(group, start=1):
            if shot.segment_id != expected_segment_id:
                raise ActorError(f"镜头组 {group_id} 的组内片段序号不连续")
            if shot.mode == "分镜" and len(group) != 1:
                raise ActorError(f"分镜镜头组 {group_id} 只能包含一个片段")
    return dict(sorted(groups.items()))


def image_to_data_url(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        b64_img = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:image/png;base64,{b64_img}"


def download_binary(url: str, output_path: str, label: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    with open(output_path, "wb") as file:
        file.write(response.content)
    print(f"{label}已保存到: {output_path}")
    return output_path


def extract_last_frame(video_path: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    command = ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path, "-frames:v", "1", output_path]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise ActorError("未找到 ffmpeg，请先安装 ffmpeg") from exc
    except subprocess.CalledProcessError as exc:
        raise ActorError(exc.stderr.decode("utf-8", errors="ignore")) from exc
    print(f"上一片段最后一帧已保存到: {output_path}")
    return output_path


def extract_video_url(result: Dict[str, Any]) -> str:
    video_url = result.get("content", {}).get("video_url")
    if not video_url:
        raise ActorError(f"没有找到 video_url: {result}")
    return video_url


def download_video(video_url: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print(f"开始下载视频: {output_path}")
    with requests.get(video_url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(output_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
    print(f"视频已保存到: {output_path}")
    return output_path


def generate_actor_videos(
    director_path: str = DIRECTOR_PATH,
    script_path: str = SCRIPT_PATH,
    output_dir: str = OUTPUT_DIR,
    reference_path: str = REFERENCE_PATH,
) -> List[Dict[str, Any]]:
    return Actor().generate_from_file(
        director_path=director_path,
        script_path=script_path,
        output_dir=output_dir,
        reference_path=reference_path,
    )


if __name__ == "__main__":
    ARK_API_KEY = "yours"
    actor = Actor(api_key=ARK_API_KEY)
    outputs = actor.generate_from_file()
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
