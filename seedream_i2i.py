import base64
import os
import requests
from openai import OpenAI

API_KEY = "ark-7a76c904-4252-43c7-b7b7-f88c347103aa-a6b06"
IMAGE_PATH = "/HARD-DATA/ZZQ/PSI/AgentVideo/Data/girl.jpg"
OUTPUT_DIR = "/HARD-DATA/ZZQ/PSI/AgentVideo/Output"
OUTPUT_FILE = "result_i2i.png"

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=API_KEY,
)


def image_to_data_url(image_path):
    with open(image_path, "rb") as image_file:
        b64_img = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_img}"


image_url = image_to_data_url(IMAGE_PATH)

# 图生图
imagesResponse = client.images.generate(
    model="doubao-seedream-5-0-260128",
    prompt="神情忧郁的女子在划船",
    size="2K",
    response_format="url",
    extra_body={
        "image": image_url,
        "watermark": False,
    },
)

# 获取 URL
generated_image_url = imagesResponse.data[0].url
print("Image URL:", generated_image_url)

# ===== 下载并保存 =====
os.makedirs(OUTPUT_DIR, exist_ok=True)
file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

response = requests.get(generated_image_url)

if response.status_code == 200:
    with open(file_path, "wb") as f:
        f.write(response.content)
    print(f"Image saved to: {file_path}")
else:
    print("Failed to download image:", response.status_code)
