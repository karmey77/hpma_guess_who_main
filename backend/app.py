from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_socketio import join_room as flask_join_room
import os
from dotenv import load_dotenv
import random
import json
import string

load_dotenv()

PORT = int(os.getenv('PORT', 5000))
API_URL = os.getenv('API_URL')

print(f"Server will run on port {PORT}")
print(f"API URL is set to: {API_URL}")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# 使用字典來存儲房間信息
rooms = {}

# 載入卡牌數據
with open('./static/images/cards/cards.json', 'r', encoding='utf-8') as f:
    all_cards = json.load(f)

def generate_room_code():
    """生成一個唯一的6位房間代碼"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in rooms:
            return code

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.get_json()
    player_name = data.get('player_name')
    room_code = generate_room_code()
    rooms[room_code] = {
        'players': [player_name],
        'ready': set(),  # 初始化為空集合
        'game_started': False,
        'guesses_left': {},
        'current_turn': None,
        'player_cards': {}
    }
    print(f"房間已創建：{room_code}，創建者：{player_name}")
    return jsonify({"message": "Room created", "room_code": room_code}), 200

@app.route('/join_room', methods=['POST'])
def join_room():
    data = request.get_json()
    room_code = data.get('room_code')
    player_name = data.get('player_name')
    
    if room_code not in rooms:
        return jsonify({"error": "Room not found"}), 404
    
    room = rooms[room_code]
    if len(room['players']) >= 2:
        return jsonify({"error": "Room is full"}), 400
    
    room['players'].append(player_name)
    room['guesses_left'][player_name] = 3
    socketio.emit('player_joined', {"player": player_name, "players": room['players']}, room=room_code)
    
    print(f"Player {player_name} joined room: {room_code}")
    return jsonify({"message": "Joined room successfully", "players": room['players']}), 200

@socketio.on('player_ready')
def on_player_ready(data):
    room_code = data['room_code']
    player_name = data['player_name']
    is_ready = data['is_ready']
    room = rooms.get(room_code)
    if room:
        if is_ready:
            room['ready'].add(player_name)
        else:
            room['ready'].discard(player_name)
        socketio.emit('player_ready', {"player": player_name, "isReady": is_ready}, room=room_code)
        if len(room['ready']) == 2:
            socketio.emit('all_players_ready', room=room_code)
        print(f"玩家 {player_name} 在房間 {room_code} 中的準備狀態已更改為 {'準備' if is_ready else '未準備'}")

@socketio.on('start_game')
def on_start_game(data):
    room_code = data['room_code']
    room = rooms.get(room_code)
    if room and len(room['ready']) == 2 and len(room['players']) == 2:
        room['game_started'] = True
        room['common_cards'] = random.sample(all_cards, 25)
        for player in room['players']:
            room['player_cards'][player] = random.choice(room['common_cards'])
        room['current_turn'] = room['players'][0]
        socketio.emit('game_started', {
            "players": room['players'],
            "current_turn": room['current_turn'],
            "common_cards": [card['id'] for card in room['common_cards']]
        }, room=room_code)
        print(f"Game started in room: {room_code}")
    else:
        print(f"Failed to start game in room: {room_code}")

@socketio.on('join')
def on_join(data):
    room = data['room']
    player = data['player']
    flask_join_room(room)
    if room not in rooms:
        rooms[room] = {
            'players': [],
            'ready': set(),  # 初始化為空集合
            'game_started': False,
            'guesses_left': {},
            'current_turn': None,
            'player_cards': {}
        }
    rooms[room]['players'] = list(set(rooms[room]['players'] + [player]))
    socketio.emit('player_joined', {"players": rooms[room]['players']}, room=room)
    print(f"玩家 {player} 加入房間：{room}")

@socketio.on('ask_question')
def handle_question(data):
    room_code = data['room_code']
    player = data['player']
    question = data['question']

    room = rooms[room_code]

    if player != room['current_turn']:
        return {"error": "Not your turn"}

    # 在這裡，我們只是將問題廣播給房間中的所有玩家
    # 實際的回答和卡牌過濾將由玩家在前端完成
    socketio.emit('new_question', {
        "player": player,
        "question": question
    }, room=room_code)

    # 切換到下一個玩家的回合
    room['current_turn'] = [p for p in room['players'] if p != player][0]
    socketio.emit('turn_change', {"current_turn": room['current_turn']}, room=room_code)

@socketio.on('make_guess')
def handle_guess(data):
    room_code = data['room_code']
    player = data['player']
    guessed_card = data['guessed_card']

    room = rooms[room_code]

    if player != room['current_turn']:
        return {"error": "Not your turn"}

    if room['guesses_left'][player] <= 0:
        return {"error": "No guesses left"}

    room['guesses_left'][player] -= 1

    opponent = [p for p in room['players'] if p != player][0]
    correct_card = room['player_cards'][opponent]

    if guessed_card == correct_card['id']:
        # 玩家猜對了
        socketio.emit('game_over', {
            "winner": player,
            "correct_card": correct_card
        }, room=room_code)
    else:
        # 玩家猜錯了
        socketio.emit('guess_result', {
            "player": player,
            "guessed_card": guessed_card,
            "correct": False,
            "guesses_left": room['guesses_left'][player]
        }, room=room_code)

        if room['guesses_left'][player] == 0:
            # 如果玩家用完了所有猜測機會
            socketio.emit('game_over', {
                "winner": opponent,
                "correct_card": correct_card
            }, room=room_code)
        else:
            # 切換到下一個玩家的回合
            room['current_turn'] = opponent
            socketio.emit('turn_change', {"current_turn": room['current_turn']}, room=room_code)

@app.route('/card_image/<int:card_id>')
def card_image(card_id):
    return send_from_directory('static/images/cards', f'{card_id:02d}.png')

@app.route('/card_back')
def card_back():
    return send_from_directory('static/images/cards', 'card_back.png')

if __name__ == '__main__':
    print("Starting the server...")
    port = int(os.getenv('PORT', 5000))
    print(f"Server will run on port {port}")
    socketio.run(app, debug=True, host='0.0.0.0', port=port)