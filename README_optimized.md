# Optimized Philips Hue Voice Control

A highly responsive, multithreaded Python application for controlling Philips Hue lights with voice commands. This version is optimized for non-color Philips Hue lights.

## Features

- **Wake word activation** - only responds to commands that start with "philips"
- Multithreaded design for improved responsiveness
- Voice command recognition using Google's Speech Recognition API
- Command debouncing to prevent duplicate commands
- Confidence filtering to only process high-confidence commands
- Caching to reduce API calls to the Hue Bridge
- Automatic recovery from connection issues
- Optimized for non-color Philips Hue lights

## Voice Commands

All commands must start with the wake word "philips". The application then recognizes the following voice commands:

### Basic Controls
- "philips turn on lights" or "philips lights on" - Turns on living room lights
- "philips turn off lights" or "philips lights off" - Turns off living room lights

### Brightness Controls
- "philips dim lights" or "philips lower lights" - Reduces brightness
- "philips dim lights a little" - Slightly reduces brightness
- "philips dim lights a lot" - Significantly reduces brightness
- "philips brighten lights" or "philips increase lights" - Increases brightness
- "philips brighten lights a little" - Slightly increases brightness
- "philips brighten lights a lot" - Significantly increases brightness
- "philips maximum brightness" or "philips brightest" - Sets lights to maximum brightness
- "philips minimum brightness" or "philips dimmest" - Sets lights to minimum brightness
- "philips set lights to 50 percent" - Sets brightness to specific percentage (any number works)

## Requirements

- Python 3.9+
- Philips Hue Bridge connected to your network
- Microphone connected to your computer

## Setup

1. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements_optimized.txt
   ```

3. Set your Hue Bridge IP in the `.env` file:
   ```
   HUE_BRIDGE_IP=192.168.1.X
   ```

## Running the Application

```bash
python hue_voice_control_optimized.py
```

When you run the application for the first time, you'll need to press the link button on your Philips Hue Bridge when prompted.

## Customizing the Wake Word

If you want to change the wake word from "philips" to something else:

1. Open `hue_voice_control_optimized.py` in a text editor
2. Find the line `WAKE_WORD = "philips"` near the top of the file
3. Change "philips" to your preferred wake word (use lowercase)
4. Save the file and restart the application

## Troubleshooting

### Speech Recognition Issues
- Make sure FLAC is installed: `brew install flac` (macOS) or `apt-get install flac` (Linux)
- Speak clearly and at a normal pace
- Be in a quiet environment when possible
- Position yourself not too far from your computer's microphone
- **Remember to start each command with "philips"**

### Bridge Connection Issues
- Make sure your Hue Bridge is on the same network as your computer
- Verify the IP address in the `.env` file is correct
- Check that you've pressed the link button when prompted during first run

## License

MIT 