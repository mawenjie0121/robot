import json
import os

DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def set_bugtrack(tag, content):
    data = load_data()
    if tag in data:
        return False  # 已存在
    data[tag] = content
    save_data(data)
    return True

def get_bugtrack(tag):
    data = load_data()
    return data.get(tag)

def update_bugtrack(tag, content):
    data = load_data()
    if tag not in data:
        return False  # 不存在
    data[tag] = content
    save_data(data)
    return True

def delete_bugtrack(tag):
    data = load_data()
    if tag not in data:
        return False  # 不存在
    del data[tag]
    save_data(data)
    return True