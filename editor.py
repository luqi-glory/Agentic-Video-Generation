"""Editor agent for concatenating generated shot videos.

This module reads Output/video_director.json, resolves the video filenames
created by actor.py, and concatenates them in global shot order into
Output/final_results.mp4.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

DIRECTOR_PATH = "./Output/video_director.json"
OUTPUT_DIR = "./Output"
FINAL_OUTPUT_PATH = "./Output/final_results.mp4"
CONCAT_LIST_PATH = "./Output/concat_list.txt"


class EditorError(RuntimeError):
    """Raised when video editing fails."""


@dataclass(frozen=True)
class VideoSegment:
    """A generated video segment resolved from director JSON."""

    shot_id: int
    group_id: int
    segment_id: int
    path: str


def load_segments(director_path: str = DIRECTOR_PATH, output_dir: str = OUTPUT_DIR) -> List[VideoSegment]:
    """Load shot order from director JSON and resolve generated video paths."""

    with open(director_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise EditorError("video_director.json 中缺少非空 shots 数组")

    segments: List[VideoSegment] = []
    for expected_id, shot in enumerate(shots, start=1):
        shot_id = shot.get("镜头序号")
        group_id = shot.get("镜头组序号")
        segment_id = shot.get("组内片段序号")
        if shot_id != expected_id:
            raise EditorError(f"第 {expected_id} 个镜头序号不连续")
        if not isinstance(group_id, int) or group_id < 1:
            raise EditorError(f"第 {expected_id} 个镜头组序号无效")
        if not isinstance(segment_id, int) or segment_id < 1:
            raise EditorError(f"第 {expected_id} 个组内片段序号无效")

        filename = f"group_{group_id:03d}_part_{segment_id:03d}_shot_{shot_id:03d}.mp4"
        path = os.path.join(output_dir, filename)
        if not os.path.exists(path):
            raise EditorError(f"缺少镜头视频文件: {path}")
        segments.append(
            VideoSegment(
                shot_id=shot_id,
                group_id=group_id,
                segment_id=segment_id,
                path=path,
            )
        )

    return sorted(segments, key=lambda segment: segment.shot_id)


def write_concat_list(segments: List[VideoSegment], list_path: str = CONCAT_LIST_PATH) -> str:
    """Write an ffmpeg concat demuxer file list."""

    os.makedirs(os.path.dirname(list_path), exist_ok=True)
    with open(list_path, "w", encoding="utf-8") as file:
        for segment in segments:
            absolute_path = os.path.abspath(segment.path)
            escaped_path = absolute_path.replace("'", "'\\''")
            file.write(f"file '{escaped_path}'\n")
    return list_path


def concat_videos(
    concat_list_path: str = CONCAT_LIST_PATH,
    output_path: str = FINAL_OUTPUT_PATH,
    *,
    reencode: bool = False,
) -> str:
    """Concatenate videos with ffmpeg."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path]
    if reencode:
        command.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
            ]
        )
    else:
        command.extend(["-c", "copy"])
    command.append(output_path)

    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise EditorError("未找到 ffmpeg，请先安装 ffmpeg") from exc
    except subprocess.CalledProcessError as exc:
        if not reencode:
            print("直接拼接失败，尝试重新编码拼接...")
            return concat_videos(concat_list_path, output_path, reencode=True)
        error_text = exc.stderr.decode("utf-8", errors="ignore")
        raise EditorError(f"视频拼接失败: {error_text}") from exc

    return output_path


def edit_final_video(
    director_path: str = DIRECTOR_PATH,
    output_dir: str = OUTPUT_DIR,
    output_path: str = FINAL_OUTPUT_PATH,
) -> str:
    """Concatenate all actor-generated videos into final_results.mp4."""

    segments = load_segments(director_path=director_path, output_dir=output_dir)
    concat_list_path = write_concat_list(segments)
    final_path = concat_videos(concat_list_path=concat_list_path, output_path=output_path)
    return final_path


if __name__ == "__main__":
    final_video = edit_final_video()
    print(f"最终视频已保存到: {final_video}")
