import os
import requests
from openai import OpenAI

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key = "yours", 
)

# 生成图片
imagesResponse = client.images.generate(
    model="doubao-seedream-5-0-260128",
    prompt="星际穿越，黑洞，黑洞里冲出一辆快支离破碎的复古列车...",
    size="2K",
    response_format="url",
    extra_body={
        "watermark": False,
    },
)

# 获取 URL
image_url = imagesResponse.data[0].url
print("Image URL:", image_url)

# ===== 下载并保存 =====
output_dir = "/HARD-DATA/ZZQ/PSI/AgentVideo/Output"
os.makedirs(output_dir, exist_ok=True)

file_path = os.path.join(output_dir, "result.png")

response = requests.get(image_url)

if response.status_code == 200:
    with open(file_path, "wb") as f:
        f.write(response.content)
    print(f"Image saved to: {file_path}")
else:
    print("Failed to download image:", response.status_code)