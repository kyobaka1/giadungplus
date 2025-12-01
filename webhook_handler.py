#!/usr/bin/env python3
"""
GitHub Webhook Handler cho tự động deploy
Chạy server Flask đơn giản để nhận webhook từ GitHub và trigger deploy.sh

Cài đặt:
    pip install flask

Chạy:
    python webhook_handler.py

Hoặc với systemd service (xem DEPLOYMENT_GUIDE.md)
"""

import os
import subprocess
import hmac
import hashlib
import json
from flask import Flask, request, jsonify
from pathlib import Path

app = Flask(__name__)

# Cấu hình
PROJECT_DIR = os.environ.get('PROJECT_DIR', '/var/www/giadungplus')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your-secret-key-change-this')
DEPLOY_SCRIPT = os.path.join(PROJECT_DIR, 'deploy.sh')
LOG_FILE = os.path.join(PROJECT_DIR, 'logs', 'webhook.log')

# Tạo thư mục logs nếu chưa có
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def log_message(message):
    """Ghi log vào file"""
    with open(LOG_FILE, 'a') as f:
        f.write(f"{message}\n")
    print(message)


def verify_signature(payload_body, signature_header):
    """Xác thực signature từ GitHub"""
    if not signature_header:
        return False
    
    hash_object = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)


@app.route('/webhook', methods=['POST'])
def webhook():
    """Xử lý webhook từ GitHub"""
    try:
        # Lấy payload
        payload_body = request.get_data()
        signature = request.headers.get('X-Hub-Signature-256', '')
        
        # Xác thực signature (nếu có secret)
        if WEBHOOK_SECRET != 'your-secret-key-change-this':
            if not verify_signature(payload_body, signature):
                log_message("❌ Invalid signature")
                return jsonify({'error': 'Invalid signature'}), 401
        
        # Parse JSON
        payload = json.loads(payload_body)
        event_type = request.headers.get('X-GitHub-Event', '')
        
        log_message(f"📥 Received {event_type} event")
        
        # Chỉ xử lý push event
        if event_type == 'push':
            ref = payload.get('ref', '')
            branch = ref.split('/')[-1] if '/' in ref else ref
            
            # Chỉ deploy khi push vào main/master branch
            if branch in ['main', 'master']:
                log_message(f"🚀 Triggering deploy for branch: {branch}")
                
                # Chạy deploy script trong background
                try:
                    process = subprocess.Popen(
                        ['bash', DEPLOY_SCRIPT],
                        cwd=PROJECT_DIR,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=dict(os.environ, PATH=os.environ.get('PATH', ''))
                    )
                    
                    # Không đợi process hoàn thành (chạy async)
                    log_message(f"✅ Deploy script started (PID: {process.pid})")
                    return jsonify({
                        'status': 'success',
                        'message': 'Deploy started',
                        'branch': branch,
                        'pid': process.pid
                    }), 200
                except Exception as e:
                    log_message(f"❌ Error starting deploy: {str(e)}")
                    return jsonify({'error': str(e)}), 500
            else:
                log_message(f"⏭️  Ignoring push to branch: {branch}")
                return jsonify({
                    'status': 'ignored',
                    'message': f'Branch {branch} is not main/master'
                }), 200
        else:
            log_message(f"⏭️  Ignoring event type: {event_type}")
            return jsonify({
                'status': 'ignored',
                'message': f'Event type {event_type} is not handled'
            }), 200
            
    except Exception as e:
        log_message(f"❌ Error processing webhook: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/webhook', methods=['GET'])
def webhook_get():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'GitHub Webhook Handler',
        'project_dir': PROJECT_DIR
    }), 200


@app.route('/deploy', methods=['POST'])
def manual_deploy():
    """Endpoint để trigger deploy thủ công (cần authentication)"""
    # Có thể thêm authentication token ở đây
    auth_token = request.headers.get('Authorization', '')
    expected_token = os.environ.get('DEPLOY_TOKEN', '')
    
    if expected_token and auth_token != f'Bearer {expected_token}':
        return jsonify({'error': 'Unauthorized'}), 401
    
    log_message("🚀 Manual deploy triggered")
    
    try:
        process = subprocess.Popen(
            ['bash', DEPLOY_SCRIPT],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        log_message(f"✅ Deploy script started (PID: {process.pid})")
        return jsonify({
            'status': 'success',
            'message': 'Deploy started',
            'pid': process.pid
        }), 200
    except Exception as e:
        log_message(f"❌ Error starting deploy: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('WEBHOOK_PORT', 9000))
    host = os.environ.get('WEBHOOK_HOST', '0.0.0.0')
    
    log_message(f"🚀 Starting webhook handler on {host}:{port}")
    log_message(f"📁 Project directory: {PROJECT_DIR}")
    log_message(f"🔐 Webhook secret: {'***' if WEBHOOK_SECRET != 'your-secret-key-change-this' else 'NOT SET'}")
    
    app.run(host=host, port=port, debug=False)

