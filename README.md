# Philips Hue Voice Control

A Docker-containerized Python application that allows you to control your Philips Hue lights in your living room using voice commands.

## Features

- Voice command recognition using Google's Speech Recognition API
- Control Philips Hue lights with simple voice commands
- Automatically finds and controls lights in your living room
- Docker containerized for easy deployment

## Voice Commands

The application recognizes the following voice commands for your living room lights:

### Basic Controls
- "Turn on lights" or "Lights on" or "Switch on" - Turns on living room lights
- "Turn off lights" or "Lights off" or "Switch off" - Turns off living room lights

### Brightness Controls
- "Dim lights" or "Lower lights" or "Darker" - Reduces brightness
- "Dim lights a little" - Slightly reduces brightness
- "Dim lights a lot" - Significantly reduces brightness
- "Brighten lights" or "Increase lights" or "More light" - Increases brightness
- "Brighten lights a little" - Slightly increases brightness
- "Brighten lights a lot" - Significantly increases brightness
- "Maximum brightness" or "Brightest" or "Full" - Sets lights to maximum brightness
- "Minimum brightness" or "Dimmest" - Sets lights to minimum brightness
- "Set lights to 50 percent" - Sets brightness to specific percentage (any number works)

### Color Controls
- "Blue lights" - Changes the light color to blue
- "Red lights" - Changes the light color to red
- "Green lights" - Changes the light color to green
- "Yellow lights" - Changes the light color to yellow
- "Purple lights" or "Violet lights" - Changes the light color to purple
- "Pink lights" - Changes the light color to pink
- "Orange lights" - Changes the light color to orange
- "White lights" or "Normal lights" or "Reset color" - Changes the light color to white
- "Warm white" - Sets a warm white tone
- "Cool white" or "Cold white" - Sets a cool white tone

### Scene Presets
- "Reading mode" or "Read mode" - Bright neutral light for reading
- "Movie mode" or "Cinema mode" or "Film mode" - Dim, warm light for watching movies
- "Romantic mode" - Dim, purplish-pink light for a romantic atmosphere
- "Relax mode" or "Chill mode" - Medium brightness, warm light for relaxing

## Requirements

- Docker
- Philips Hue Bridge connected to your network
- Microphone connected to your computer

## Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/hue-voice-control.git
   cd hue-voice-control
   ```

2. Create a `.env` file with your Philips Hue Bridge IP address:
   ```
   cp .env.example .env
   ```
   
   Edit the `.env` file and replace the placeholder IP with your Hue Bridge IP.
   You can find your bridge IP in the Philips Hue app or by visiting https://discovery.meethue.com/

3. Build the Docker image:
   ```
   docker build -t hue-voice-control .
   ```

## Running the Application

Run the Docker container with access to your microphone:

```bash
docker run -it --rm \
  --device /dev/snd \
  -v $(pwd):/app \
  -e PULSE_SERVER=unix:${XDG_RUNTIME_DIR}/pulse/native \
  -v ${XDG_RUNTIME_DIR}/pulse/native:${XDG_RUNTIME_DIR}/pulse/native \
  -v ~/.config/pulse/cookie:/root/.config/pulse/cookie \
  --group-add $(getent group audio | cut -d: -f3) \
  hue-voice-control
```

### First Run

When you run the application for the first time, you'll need to press the link button on your Philips Hue Bridge when prompted. This creates a secure connection between the application and your Bridge.

## Troubleshooting

### Audio Issues

If you encounter audio issues, try running the container with different audio configurations:

#### For MacOS:
```bash
docker run -it --rm \
  --device /dev/snd \
  -v $(pwd):/app \
  --env ALSA_CARD=PCH \
  hue-voice-control
```

#### For Linux with PulseAudio:
```bash
docker run -it --rm \
  -v $(pwd):/app \
  -v /run/user/$(id -u)/pulse:/run/user/1000/pulse \
  --env PULSE_SERVER=unix:/run/user/1000/pulse/native \
  hue-voice-control
```

### Bridge Connection Issues

- Make sure your Hue Bridge is on the same network as your computer
- Verify the IP address in the `.env` file is correct
- Check that you've pressed the link button when prompted during first run

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change. 

source venv/bin/activate
python hue_voice_control.py 