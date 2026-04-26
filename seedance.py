import base64
import os
import time
import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
API_KEY = "ark-7a76c904-4252-43c7-b7b7-f88c347103aa-a6b06"
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "Data", "girl.jpg")

if not API_KEY:
    raise ValueError("请先设置环境变量 ARK_API_KEY")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

def image_to_data_url(image_path):
    with open(image_path, "rb") as image_file:
        b64_img = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_img}"


def create_task():
    image_data_url = image_to_data_url(IMAGE_PATH)

    payload = {
        "model": "doubao-seedance-1-5-pro-251215",
        "content": [
            {
                "type": "text",
                "text": "神情忧郁的女子在湖泊上划船 --duration 5 --camerafixed false --watermark false"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url
                }
            }
        ]
    }

    response = requests.post(BASE_URL, headers=HEADERS, json=payload)
    response.raise_for_status()

    data = response.json()
    task_id = data.get("id")

    if not task_id:
        raise ValueError(f"创建任务失败: {data}")

    print(f"任务创建成功，ID: {task_id}")
    return task_id


def get_task(task_id):
    url = f"{BASE_URL}/{task_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def poll_task(task_id, interval=5):
    while True:
        result = get_task(task_id)
        status = result.get("status")

        print(f"当前状态: {status}")

        if status == "succeeded":
            return result
        elif status == "failed":
            raise RuntimeError(f"任务失败: {result}")

        time.sleep(interval)


def download_video(video_url, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"开始下载视频: {video_url}")

    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    print(f"视频已保存到: {output_path}")


def extract_video_url(result):
    video_url = result.get("content", {}).get("video_url")
    if not video_url:
        raise ValueError(f"没有找到 video_url: {result}")
    return video_url


if __name__ == "__main__":
    try:
        task_id = create_task()
        result = poll_task(task_id)

        print("任务完成，解析视频地址...")

        video_url = extract_video_url(result)

        output_file = "./Output/result.mp4"
        download_video(video_url, output_file)

    except Exception as e:
        print(f"发生错误: {e}")