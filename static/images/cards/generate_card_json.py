import json
import os

# 指定圖片所在的目錄
image_dir = r"C:\Users\odess\Desktop\hpma_guess_who\static\images\cards"

# 創建卡牌列表
cards = []

# 遍歷目錄中的所有 png 文件
for filename in sorted(os.listdir(image_dir)):
    if filename.endswith('.png'):
        card_id = int(filename.split('.')[0])
        cards.append({
            "id": card_id,
            "image": filename
        })

# 將卡牌列表寫入 JSON 文件
with open('cards.json', 'w', encoding='utf-8') as f:
    json.dump(cards, f, ensure_ascii=False, indent=2)

print(f"已生成包含 {len(cards)} 張卡牌信息的 cards.json 文件")