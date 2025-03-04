# Enhanced Philips Hue Voice Control

A Python application that allows you to control your Philips Hue lights using voice commands. The enhanced version features improved performance and reliability with a multithreaded design.

## Key Features

- **Wake word activation** - Say "philips" to start voice recognition
- **Fallback mode** - Run without wake word detection if needed
- **Voice command recognition** - Natural language processing for light control
- **Voice feedback** - System reads back commands and actions using text-to-speech
- **Multithreaded design** - Responsive and efficient performance
- **Command chaining** - Issue multiple commands at once (e.g., "turn on lights and set to 50 percent")
- **Brightness control** - Adjust light intensity with voice commands
- **Audio feedback** - Different sounds for wake word detection, command recognition, and execution
- **Undo functionality** - Revert the last action by saying "undo" or "revert"
- **Timer support** - Schedule actions (e.g., "in 5 minutes turn off lights")
- **Desktop notifications** - Visual feedback when commands are recognized

## Voice Commands

The application recognizes the following types of commands after the wake word "philips":

### Basic Controls
- "Turn on (the lights)"
- "Turn off (the lights)"
- "Undo" or "Revert" (restores previous state)

### Brightness Controls
- "Set brightness to X percent" (where X is 1-100)
- "Brighten" or "Increase brightness"
- "Dim" or "Decrease brightness"
- "Maximum brightness" or "Full brightness"
- "Minimum brightness" or "Low light"

### Timer Commands
- "In X minutes turn off lights"
- "In X seconds turn on lights"
- "After X minutes dim the lights"

## Requirements

- Python 3.9+
- Philips Hue Bridge
- Microphone for voice input
- Speakers for audio feedback
- For Windows: pyttsx3 (optional, for text-to-speech)

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install requirements:
   ```
   pip install -r requirements.txt
   ```
4. On Windows, for voice feedback, install the optional TTS package:
   ```
   pip install pyttsx3
   ```
5. Configure your Hue Bridge IP in an `.env` file:
   ```
   HUE_BRIDGE_IP=192.168.1.x
   WAKE_WORD_SENSITIVITY=0.5
   ```

## Running the Application

### Standard Mode (with wake word detection):
```
python hue_voice_control_enhanced.py
```

### Fallback Mode (without wake word detection):
If you experience issues with wake word detection, use the fallback mode:
```
python hue_voice_control_enhanced.py --fallback
```

In fallback mode, the application continuously listens for commands without requiring the wake word.

## Using the Application

1. Start the application
2. Say the wake word "philips" followed by your command
   - Example: "philips turn on the lights"
3. Listen for voice feedback:
   - The system will read back what it heard: "I heard: turn on the lights"
   - Then it will announce the action: "Turning the lights on"
4. The lights will respond according to your command

## Audio Feedback

The application provides both sound effects and voice feedback:

### Sound Effects
- **Wake word detected**: Tink sound
- **Command recognized**: Morse sound
- **Command executed**: Bottle sound
- **Error or command not recognized**: Basso sound
- **Timer expired**: Glass sound

### Voice Feedback
- Reads back the recognized command: "I heard: [your command]"
- Announces the action being taken: "Turning the lights on"
- Provides status updates: "Timer expired"
- Gives error information: "Sorry, I couldn't understand the command"

## Troubleshooting

- **Application crashes on startup**: Try using fallback mode with `--fallback` flag
- **Voice commands not recognized**: Speak clearly and ensure your microphone is working
- **"No module named 'pyobjus'"**: This is normal on macOS and won't affect functionality
- **No sound feedback**: Ensure your system volume is turned up and sound is not muted
- **No voice feedback on Windows**: Install pyttsx3 package with `pip install pyttsx3`
- **Issues connecting to bridge**: Verify your bridge IP address is correct in the `.env` file

## License

This project is licensed under the MIT License - see the LICENSE file for details. 