from flask import Blueprint, request, jsonify
import os
import requests
import logging

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/send', methods=['POST'])
def send_chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        user_image = data.get('image', None)
        history = data.get('history', [])

        # 校验：必须有消息或图片
        if not user_message and not user_image:
            return jsonify({"error": "Message cannot be empty"}), 400

        api_key = os.environ.get('MOONSHOT_API_KEY')
        base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")

        if not api_key:
            return jsonify({"error": "后端未配置 MOONSHOT_API_KEY"}), 500

        # -------------------------------------------------------------
        # 1. 动态选择模型
        # 如果包含图片，必须使用 vision 模型；否则使用普通 8k 模型以节省成本/提高速度
        # -------------------------------------------------------------
        if user_image:
            current_model = "moonshot-v1-8k-vision-preview"
        else:
            current_model = "moonshot-v1-8k"

        # 2. 构造 System Prompt
        messages = [
            {"role": "system", "content": "你是 ProjectSOA 的智能助手。如果用户发送图片，请仔细分析图片内容并回答问题。"}
        ]

        # 3. 处理历史记录
        # 即使历史为空，这段代码也是安全的，不会定义 msg 给后面用
        for history_item in history[-10:]:
            if history_item.get('role') in ['user', 'assistant'] and history_item.get('content'):
                content = history_item['content']
                if isinstance(content, list):
                    # 如果历史消息是列表（之前发过图），只提取其中的 text 部分，避免上下文过大
                    text_content = next((item['text'] for item in content if item.get('type') == 'text'), "")
                    messages.append({"role": history_item['role'], "content": text_content})
                else:
                    # 普通文本消息
                    messages.append({"role": history_item['role'], "content": content})

        # 4. 构造当前用户消息
        if user_image:
            # --- 视觉模型请求格式 ---
            current_content = [
                {"type": "text", "text": user_message},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": user_image  # 前端传来的 data:image/jpeg;base64,...
                    }
                }
            ]
            messages.append({"role": "user", "content": current_content})
        else:
            # --- 纯文本模型请求格式 ---
            # [修复点] 这里之前错误使用了 msg 变量，现在直接写死 "user"
            messages.append({"role": "user", "content": user_message})

        # 5. 发送请求
        payload = {
            "model": current_model,
            "messages": messages,
            "temperature": 0.3
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        # 错误处理
        if response.status_code != 200:
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get('error', {}).get('message', error_detail)
            except:
                pass
            logging.error(f"Moonshot API Error: {response.status_code} - {response.text}")
            return jsonify({"error": f"AI 服务异常: {error_detail}"}), response.status_code

        result = response.json()
        reply = result['choices'][0]['message']['content']

        return jsonify({"reply": reply})

    except requests.exceptions.RequestException as e:
        logging.error(f"API Request Error: {str(e)}")
        return jsonify({"error": "AI 服务连接失败"}), 502
    except Exception as e:
        logging.error(f"Chat Internal Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "服务器内部错误"}), 500