import os
import json
import re
import hashlib
import base64
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import anthropic
import whisper
import requests

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

UPLOAD_DIR = Path('uploads')
UPLOAD_DIR.mkdir(exist_ok=True)
CONFIG_FILE = Path('config.json')


def _default_feature_entry():
    return {'name': '', 'assignee_name': '', 'assignee_id': '', 'board_id': ''}


def load_config():
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text())
    else:
        data = {
            'fizzy_base_url': '',
            'fizzy_token': '',
            'fizzy_account_slug': '',
            'anthropic_api_key': '',
            'features': [_default_feature_entry()],
        }
    if not data.get('features'):
        data['features'] = [_default_feature_entry()]

    legacy_board = str(data.get('fizzy_board_id') or '').strip()
    for f in data['features']:
        if not isinstance(f, dict):
            continue
        f.setdefault('name', '')
        f.setdefault('assignee_name', '')
        f.setdefault('assignee_id', '')
        if 'board_id' not in f:
            f['board_id'] = legacy_board
        else:
            f['board_id'] = str(f.get('board_id') or '').strip()

    return data


def save_config(data):
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def fizzy_url(cfg, path):
    base = (cfg.get('fizzy_base_url') or '').rstrip('/')
    account = cfg.get('fizzy_account_slug', '').strip('/')
    prefix = f'/{account}' if account else ''
    return f'{base}{prefix}/{path.lstrip("/")}'


def upload_screenshot_to_fizzy(file_path, cfg):
    """Upload screenshot via Fizzy direct upload. Returns signed_id or None."""
    token = cfg['fizzy_token']

    file_bytes = Path(file_path).read_bytes()
    checksum = base64.b64encode(hashlib.md5(file_bytes).digest()).decode()
    filename = Path(file_path).name
    ext = Path(filename).suffix.lower().lstrip('.')
    content_type = {
        'png': 'image/png', 'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'
    }.get(ext, 'image/png')

    resp = requests.post(
        fizzy_url(cfg, 'rails/active_storage/direct_uploads'),
        json={'blob': {
            'filename': filename,
            'byte_size': len(file_bytes),
            'checksum': checksum,
            'content_type': content_type
        }},
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'QA-Tool/1.0'}
    )
    if resp.status_code not in (200, 201):
        return None

    data = resp.json()
    put_resp = requests.put(
        data['direct_upload']['url'],
        data=file_bytes,
        headers=data['direct_upload']['headers']
    )
    if put_resp.status_code not in (200, 201, 204):
        return None

    return data['signed_id']


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        save_config(request.json)
        return jsonify({'ok': True})
    return jsonify(load_config())


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route('/api/process', methods=['POST'])
def process():
    cfg = load_config()

    if not cfg.get('anthropic_api_key'):
        return jsonify({'error': 'Anthropic API key not set — open Settings to add it.'}), 400

    audio_file = request.files.get('audio')
    screenshots = request.files.getlist('screenshots')
    feature = request.form.get('feature', '').strip()

    audio_path = None
    screenshot_info = []

    if audio_file and audio_file.filename:
        fname = secure_filename(audio_file.filename)
        audio_path = UPLOAD_DIR / fname
        audio_file.save(audio_path)

    for i, ss in enumerate(screenshots):
        if ss.filename:
            fname = secure_filename(ss.filename)
            path = UPLOAD_DIR / fname
            ss.save(path)
            screenshot_info.append({'index': i + 1, 'filename': fname})

    if not audio_path:
        return jsonify({'error': 'No audio file provided.'}), 400

    # Transcribe locally with Whisper
    model = whisper.load_model('base')
    result = model.transcribe(str(audio_path))
    transcript = result['text']

    if not transcript.strip():
        return jsonify({'error': 'Could not transcribe audio — check your recording.'}), 400

    # Build prompt
    ss_context = ''
    if screenshot_info:
        ss_list = ', '.join(f"screenshot_{s['index']} (filename: {s['filename']})" for s in screenshot_info)
        ss_context = (
            f'\n\nThe designer uploaded {len(screenshot_info)} screenshots in order: {ss_list}. '
            'For each ticket, include the filename of the most relevant screenshot in the "screenshot" field, or null if none applies.'
        )

    feature_context = f'\n\nThis QA session is for the feature: "{feature}".' if feature else ''

    prompt = f"""You are a QA assistant helping a designer create bug tickets from voice notes.

Parse the transcript into individual, discrete tickets. Each ticket = one actionable issue.

Return a JSON array. Each item must have:
- "title": Short, clear title (under 60 chars)
- "description": What's wrong and what it should look like instead (2-4 sentences)
- "screenshot": Exact filename of the most relevant screenshot, or null
- "severity": "bug" | "visual" | "copy"
{feature_context}{ss_context}

Transcript:
{transcript}

Return only valid JSON array, no markdown fences."""

    ai = anthropic.Anthropic(api_key=cfg['anthropic_api_key'])
    msg = ai.messages.create(
        model='claude-opus-4-6',
        max_tokens=4096,
        messages=[{'role': 'user', 'content': prompt}]
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    tickets = json.loads(raw)

    assignee = next((f for f in cfg.get('features', []) if f['name'] == feature), {})
    fallback_board = str(cfg.get('fizzy_board_id') or '').strip()
    for t in tickets:
        t['assignee_id'] = assignee.get('assignee_id', '')
        t['assignee_name'] = assignee.get('assignee_name', '')
        t['board_id'] = str(assignee.get('board_id') or '').strip() or fallback_board

    return jsonify({'tickets': tickets, 'transcript': transcript})


@app.route('/api/create', methods=['POST'])
def create_tickets():
    cfg = load_config()
    tickets = request.json.get('tickets', [])

    fallback_board = str(cfg.get('fizzy_board_id') or '').strip()
    token = cfg['fizzy_token']
    auth = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'User-Agent': 'QA-Tool/1.0',
    }

    results = []
    for ticket in tickets:
        if ticket.get('skip'):
            results.append({'title': ticket['title'], 'skipped': True})
            continue

        board = str(ticket.get('board_id') or '').strip() or fallback_board
        if not board:
            results.append({
                'title': ticket['title'],
                'ok': False,
                'error': 'Board ID missing — set it for this feature in Settings → Features.',
            })
            continue

        # Upload screenshot and embed in description
        description = ticket['description']
        ss_file = ticket.get('screenshot')
        if ss_file:
            ss_path = UPLOAD_DIR / ss_file
            if ss_path.exists():
                signed_id = upload_screenshot_to_fizzy(ss_path, cfg)
                if signed_id:
                    description += f'\n\n<action-text-attachment sgid="{signed_id}"></action-text-attachment>'

        # Create card
        resp = requests.post(
            fizzy_url(cfg, f'boards/{board}/cards'),
            json={'card': {'title': ticket['title'], 'description': description}},
            headers={**auth, 'Content-Type': 'application/json'}
        )

        if resp.status_code != 201:
            print(f'Fizzy error {resp.status_code}: {resp.text}')
            results.append({'title': ticket['title'], 'ok': False, 'error': f'HTTP {resp.status_code}: {resp.text[:300]}'})
            continue

        location = resp.headers.get('Location', '')
        card_number = location.rstrip('/').split('/')[-1].replace('.json', '')

        if ticket.get('assignee_id'):
            requests.post(
                fizzy_url(cfg, f'cards/{card_number}/assignments'),
                json={'assignee_id': ticket['assignee_id']},
                headers={**auth, 'Content-Type': 'application/json'}
            )

        results.append({'title': ticket['title'], 'ok': True, 'card_number': card_number})

    return jsonify({'results': results})


if __name__ == '__main__':
    print('\n  QA Tool → http://127.0.0.1:8080\n')
    app.run(port=8080, debug=True)
