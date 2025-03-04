# Philips Hue Voice Control - Simple Version

A Python application that allows you to control your Philips Hue lights using voice commands. This simplified version is designed specifically for non-dimmable, non-color lights, providing basic on/off functionality.

## Features

- Voice command recognition for controlling lights
- **Wake word activation** - only responds to commands that start with "philips"
- Multithreaded design for responsive performance
- Automatic detection of living room lights
- Fallback to all lights if living room lights are not found
- Caching to reduce API calls to the Hue Bridge

## Voice Commands

All commands must start with the wake word "philips", for example:
- "philips turn on the lights"
- "philips turn off"

| Command | Action |
|---------|--------|
| "philips turn on", "philips lights on", etc. | Turn lights on |
| "philips turn off", "philips lights off", etc. | Turn lights off |

## Requirements

- Python 3.9+
- Philips Hue Bridge
- Microphone
- Philips Hue lights (non-color)

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/hue-voice-control.git
   cd hue-voice-control
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your Hue Bridge IP:
   ```
   HUE_BRIDGE_IP=192.168.1.x  # Replace with your Hue Bridge IP
   ```

## Running the Application

1. Ensure your virtual environment is activated.

2. Run the application:
   ```
   python hue_voice_control_simple.py
   ```

3. If running for the first time, press the link button on your Hue Bridge when prompted.

4. Speak commands clearly into your microphone, always starting with the wake word "philips" (e.g., "philips turn on the lights" or "philips turn off").

## Customizing the Wake Word

If you want to change the wake word from "philips" to something else:

1. Open `hue_voice_control_simple.py` in a text editor
2. Find the line `WAKE_WORD = "philips"` near the top of the file
3. Change "philips" to your preferred wake word (use lowercase)
4. Save the file and restart the application

## Troubleshooting

- **Bridge Connection Issues**: Ensure your Hue Bridge IP is correct in the `.env` file.
- **Microphone Not Working**: Check your system's microphone settings and permissions.
- **Commands Not Recognized**: Remember to start each command with "philips" and speak clearly in a quiet environment.
- **Wake Word Not Detected**: Ensure you're saying "philips" clearly before your command.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 