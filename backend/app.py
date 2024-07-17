import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room as flask_join_room
from dotenv import load_dotenv
import random
import json
import string

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}
all_cards = [f"{i:02d}" for i in range(1, 82)]  # 01 到 81 的卡牌

def generate_room_code():
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
        'host': player_name,
        'ready': set(),
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
    
    if player_name not in room['players']:
        room['players'].append(player_name)
    room['guesses_left'][player_name] = 3
    
    socketio.emit('player_joined', {
        "player": player_name, 
        "players": room['players'],
        "host": room['host']
    }, room=room_code)
    
    print(f"Player {player_name} joined room: {room_code}")
    return jsonify({"message": "Joined room successfully", "players": room['players'], "host": room['host']}), 200

@socketio.on('join')
def on_join(data):
    room = data['room']
    player = data['player']
    flask_join_room(room)
    if room in rooms:
        if player not in rooms[room]['players']:
            rooms[room]['players'].append(player)
        socketio.emit('player_joined', {
            "player": player,
            "players": rooms[room]['players'],
            "host": rooms[room]['host']
        }, room=room)
    print(f"玩家 {player} 加入房間：{room}")

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
        room['common_cards'] = random.sample(all_cards, 25)
        for player in room['players']:
            room['player_cards'][player] = random.choice(room['common_cards'])
        room['game_started'] = True
        room['current_turn'] = room['players'][0]
        socketio.emit('game_started', {
            "players": room['players'],
            "current_turn": room['current_turn'],
            "common_cards": room['common_cards'],
            "your_secret_card": {player: room['player_cards'][player] for player in room['players']}
        }, room=room_code)
        print(f"Game started in room: {room_code}")
    else:
        print(f"Failed to start game in room: {room_code}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"Server will run on port {port}")
    socketio.run(app, debug=True, host='0.0.0.0', port=port)