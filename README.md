# QA → Fizzy

A tool that turns voice recordings from QA sessions into Fizzy tickets automatically.

## What it does

Instead of manually writing tickets after a QA session, you record yourself talking through everything that's wrong in staging. The tool then:

1. **Transcribes** your voice recording into text (using Whisper, which runs locally on your Mac for free)
2. **Reads the transcript** and breaks it into individual tickets, writing a clear title and description for each one (using Claude AI)
3. **Shows you the tickets** so you can review and edit anything before they go out
4. **Creates the tickets in Fizzy** and assigns them to the right person automatically

The whole process takes about the same time as your recording, plus ~30 seconds for processing.

## Requirements

Before running for the first time, make sure you have these installed on your Mac:

**1. Python 3**
Check if you have it by opening Terminal and running `python3 --version`. If you get a number back, you're good. If not, download it from python.org.

**2. Homebrew**
Homebrew is a tool for installing software on Mac. Check if you have it by running `brew --version` in Terminal. If not, install it by running:
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**3. ffmpeg**
ffmpeg is needed to process audio files. Once you have Homebrew, install it by running:
```
brew install ffmpeg
```

Everything else (Python packages, AI models) installs automatically the first time you run the app.

## How to run it

**Every time you want to use it:**

1. Open Terminal
2. Run:
   ```
   git clone https://github.com/Tobias-0/qa-tool.git
   cd qa-tool
   ./run.sh
   ```
3. Go to **http://127.0.0.1:8080** in your browser

The terminal needs to stay open while you're using the tool. When you're done, press **Ctrl+C** in the terminal to stop it.

**Your settings are saved** — you only need to fill in Settings once.

## First time setup

Click **⚙ Settings** in the top right and fill in:

- **Anthropic API Key** — from console.anthropic.com → API Keys
- **Fizzy Base URL** — your Fizzy host, e.g. `https://fizzy.example.com`
- **Fizzy Personal Access Token** — from your Fizzy profile → API → Personal access tokens (Read + Write)
- **Board ID** — the ID in your Fizzy board's URL
- **Features & Assignees** — map each feature to the person who owns it (find their user ID in their Fizzy profile URL)

Settings start empty. They are saved to `config.json` on your machine only — that file is gitignored and should never be committed.

## Files

- `app.py` — the backend that handles transcription, AI, and Fizzy API calls
- `templates/index.html` — the UI
- `config.example.json` — empty settings template
- `config.json` — your saved settings (created automatically, do not share this file — it contains your API keys)
- `uploads/` — temporary storage for recordings and screenshots
