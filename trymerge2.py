import io
import logging
import socket
import socketserver
from http import server
from threading import Condition
import RPi.GPIO as GPIO
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import time
import Adafruit_DHT

file_path = "/home/hossam/proj2/dht_data.txt"

# GPIO motor drivers
# driver 1
IN1, IN2, ENA = 17, 18, 22
IN3, IN4, ENB = 23, 24, 25
# Servo Motors
SERVO_PAN, SERVO_TILT = 20, 21
RELAY_PUMP = 27
RELAY_BUZZER = 16
RELAY_LIGHT = 26
# DHT Sensor
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 7
GPIO.setmode(GPIO.BCM)
#soil moist
SOIL_MOIST = 4
# Setup for motors
for pin in [IN1, IN2, ENA, IN3, IN4, ENB]:
    GPIO.setup(pin, GPIO.OUT)

for pin in [RELAY_PUMP, RELAY_BUZZER, RELAY_LIGHT]:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)
# Setup for servos
SERVO_UP1, SERVO_UP2 = 5, 6  # Change pins if needed

GPIO.setup(SERVO_UP1, GPIO.OUT)
GPIO.setup(SERVO_UP2, GPIO.OUT)

servo_up1 = GPIO.PWM(SERVO_UP1, 50)  # 50Hz for standard servos
servo_up2 = GPIO.PWM(SERVO_UP2, 50)

servo_up1.start(0)
servo_up2.start(0)
GPIO.setup(SERVO_PAN, GPIO.OUT)
GPIO.setup(SERVO_TILT, GPIO.OUT)
servo_pan = GPIO.PWM(SERVO_PAN, 50)
servo_tilt = GPIO.PWM(SERVO_TILT, 50)
servo_pan.start(0)
servo_tilt.start(0)
GPIO.setup(SOIL_MOIST, GPIO.IN)
# PWM setup for motor speed control (might not be working idk)
pwm_a, pwm_b= [GPIO.PWM(pin, 1000) for pin in [ENA, ENB]]
for pwm in [pwm_a, pwm_b]:
    pwm.start(100)

tilt_up_count = 0
tilt_down_count = 0
pan_left_count = 0
pan_right_count = 0

# Read digital soil moisture sensor (returns "Moist" or "Dry")
def read_soil_moisture_digital():
    return "Dry" if GPIO.input(SOIL_MOIST) else "Moist"

def motors_left():
    pwm_a.ChangeDutyCycle(50)  # Reduce left motor speed
    pwm_b.ChangeDutyCycle(100)
def motors_right():
    pwm_a.ChangeDutyCycle(100)  # Keep left motor at full speed
    pwm_b.ChangeDutyCycle(50)  # Red
def motors_forward():
    pwm_a.ChangeDutyCycle(100)
    pwm_b.ChangeDutyCycle(100)
    GPIO.output([IN1, IN3], GPIO.HIGH)
    GPIO.output([IN2, IN4], GPIO.LOW)

def motors_backward():
    GPIO.output([IN1, IN3], GPIO.LOW)
    GPIO.output([IN2, IN4], GPIO.HIGH)
    pwm_a.ChangeDutyCycle(0)
    pwm_b.ChangeDutyCycle(0)
def motors_stop():
    GPIO.output([IN1, IN2, IN3, IN4], GPIO.LOW)

def set_speed(duty_cycle):
    for pwm in [pwm_a, pwm_b, pwm_a2, pwm_b2]:
        pwm.ChangeDutyCycle(duty_cycle)

def move_servo(servo, angle):
    duty = 2.5 + (angle / 18)
    servo.ChangeDutyCycle(duty)
    time.sleep(0.3)
    servo.ChangeDutyCycle(0)
# Store the last successful readings
last_temperature = None
last_humidity = None

def read_dht_sensor():
    global last_temperature, last_humidity  # Use stored values

    try:
        with open(file_path, "r") as f:
            data = f.read().strip()

        if "Error" in data:
            print("DHT Sensor Error:", data)
            return last_temperature, last_humidity  # Return last known good values
        else:
            temp, hum = data.split(",")
            last_temperature, last_humidity = float(temp), float(hum)  # Update stored values
            return last_temperature, last_humidity  # Return latest valid readings

    except Exception as e:
        print(f"Error reading sensor file: {e}")
        return last_temperature, last_humidity  # Return last known good values

PAGE = """
<!DOCTYPE html>
<html lang="en">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Car Control</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            text-align: center;
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            width: 90%;
            max-width: 800px;
        }
        h1 {
            margin-bottom: 20px;
            color: #333;
        }
        .video-stream {
            margin-bottom: 20px;
        }
        .video-stream img {
            max-width: 100%;
            border-radius: 5px;
        }
        .control-panel {
            display: grid;
            grid-template-areas:
                ". forward ."
                "left stop right"
                ". backward .";
            gap: 10px;
            margin-bottom: 20px;
        }
        .control-button {
            padding: 10px 25px;
            font-size: 18px;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            background-color: #007bff;
            color: white;
            transition: background-color 0.3s;
        }
        .control-button:active {
            background-color: #0056b3;
        }
        .control-button#forward { grid-area: forward; }
        .control-button#backward { grid-area: backward; }
        .control-button#left { grid-area: left; }
        .control-button#right { grid-area: right; }
        .control-button#stop { grid-area: stop; background-color: #dc3545; }
        .control-button#stop:active { background-color: #a71d2a; }
        .servo-control {
            margin-bottom: 20px;
        }
        .servo-control button {
            padding: 10px 20px;
            font-size: 16px;
            border-radius: 5px;
            margin: 5px;
        }
        .status-button {
            padding: 10px 20px;
            font-size: 16px;
            border-radius: 5px;
            margin: 5px;
            cursor: pointer;
        }
        .status-button.on {
            background-color: #28a745;
            color: white;
        }
        .status-button.off {
            background-color: #dc3545;
            color: white;
        }
        .status-button:active {
            opacity: 0.8;
        }
        .sensor-data {
            margin-top: 20px;
            font-size: 18px;
            background-color: #f1f1f1;
            padding: 10px;
            border-radius: 5px;
            display: inline-block;
            width: 50%;
            text-align: left;
        }
    </style>

 <script>
        // Toggle status for pump, buzzer, and light
        function toggleStatus(device) {
            const button = document.getElementById(device);
            let command = '';

            if (button.classList.contains('off')) {
                command = device + '_on';
                button.classList.remove('off');
                button.classList.add('on');
                button.innerText = device.charAt(0).toUpperCase() + device.slice(1) + ' ON';
            } else {
                command = device + '_off';
                button.classList.remove('on');
                button.classList.add('off');
                button.innerText = device.charAt(0).toUpperCase() + device.slice(1) + ' OFF';
            }

            // Send the command to the server
            fetch('/?command=' + command)
                .then(response => response.text())
                .then(data => {
                    console.log(data);
                });
        }

    </script>

</head>
<body>
    <div class="container">
        <h1>Car Control</h1>

        <!-- Video Stream -->
        <div class="video-stream">
            <img src="/stream.mjpg" alt="Live Stream">
        </div>

        <!-- Car Control Panel -->
        <div class="control-panel">
            <button class="control-button" id="forward" onmousedown="fetch('/?command=forward')" onmouseup="fetch('/?command=stop')">Forward</button>
            <button class="control-button" id="backward" onmousedown="fetch('/?command=backward')" onmouseup="fetch('/?command=stop')">Backward</button>
            <button class="control-button" id="left" onmousedown="fetch('/?command=left')" onmouseup="fetch('/?command=stop')">Left</button>
            <button class="control-button" id="right" onmousedown="fetch('/?command=right')" onmouseup="fetch('/?command=stop')">Right</button>
            <button class="control-button" id="stop" onclick="fetch('/?command=stop')">Stop</button>
        </div>

        <!-- Servo Control -->
        <div class="servo-control">
            <button class="control-button" onclick="fetch('/?command=pan_left')">Pan Left</button>
            <button class="control-button" onclick="fetch('/?command=tilt_up')">Tilt Up</button>
            <button class="control-button" onclick="fetch('/?command=pan_right')">Pan Right</button>
            <button class="control-button" onclick="fetch('/?command=tilt_down')">Tilt Down</button>
        </div>
        <div class="servo-control">
            <!-- Servo 1 (Up/Down) -->
<button onclick="fetch('/?command=up1')">Servo 1 Up</button>
<button onclick="fetch('/?command=down1')">Servo 1 Down</button>
        </div>
        <div class="servo-control">
<!-- Servo 2 (Up/Down) -->
<button onclick="fetch('/?command=up2')">Servo 2 Up</button>
<button onclick="fetch('/?command=down2')">Servo 2 Down</button>
        </div>
        <!-- Pump, Buzzer, and Light Control -->
        <div>
            <button class="status-button off" id="pump" onclick=handleClick(1)>Pump OFF</button>
            <button class="status-button off" id="buzzer" onclick=handleClick(2)>Buzzer OFF</button>
            <button class="status-button off" id="light" onclick=handleClick(3)>Light OFF</button>

<script>
  let clickCounts = { 1: 0, 2: 0, 3: 0 };

  // Button 1 functions
  function button1FirstClick() {
    console.log('Button 1 - First Click Action');
    fetch('/?command=pump_on')
      toggleStatus('pump')
  }
  function button1SecondClick() {
    fetch('/?command=pump_off')
      toggleStatus('pump')
  }

  // Button 2 functions
  function button2FirstClick() {
    fetch('/?command=buzzer_on')
      toggleStatus('buzzer')
  }
  function button2SecondClick() {
    fetch('/?command=buzzer_off')
      toggleStatus('buzzer')
  }

  // Button 3 functions
  function button3FirstClick() {
    fetch('/?command=light_on')
      toggleStatus('light')
  }
  function button3SecondClick() {
   fetch('/?command=light_off')
      toggleStatus('light')
  }

  // Handle clicks
  function handleClick(buttonNumber) {
    clickCounts[buttonNumber]++;

    if (clickCounts[buttonNumber] === 1) {
      if (buttonNumber === 1) button1FirstClick();
      else if (buttonNumber === 2) button2FirstClick();
      else if (buttonNumber === 3) button3FirstClick();
    } else if (clickCounts[buttonNumber] === 2) {
      if (buttonNumber === 1) button1SecondClick();
      else if (buttonNumber === 2) button2SecondClick();
      else if (buttonNumber === 3) button3SecondClick();
      clickCounts[buttonNumber] = 0;
    }
  }
</script>

        </div>
 <div class="sensor-data">
<script>
function fetchSensorData() {
    fetch('/?command=sensor_data')
        .then(response => response.json())
        .then(data => {
            document.getElementById("moisture").innerText = data.moisture;
            document.getElementById("temp").innerText = data.temperature;
            document.getElementById("humidity").innerText = data.humidity;
        })
        .catch(error => console.error('Error fetching sensor data:', error));
}

// Fetch data every 2 seconds
setInterval(fetchSensorData, 2000);
</script>
            <p>Soil Moisture: <span id="moisture">--</span></p>
            <p>Temperature: <span id="temp">--</span> °C</p>
            <p>Humidity: <span id="humidity">--</span> %</p>
        </div>

    </div>

    <script>
        function toggleStatus(device) {
            const button = document.getElementById(device);
            const isOn = button.classList.contains('on');
            const newStatus = isOn ? 'off' : 'on';
            button.classList.remove(isOn ? 'on' : 'off');
            button.classList.add(newStatus);
            button.textContent = `${device.charAt(0).toUpperCase() + device.slice(1)} ${newStatus.toUpperCase()}`;

            // Send status change to server (for pump, buzzer, light)
            fetch(`/?${device}=${newStatus}`);
        }
    </script>
</body>
</html>

"""

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()
    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class RequestHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        global pan_left_count, pan_right_count , tilt_up_count , tilt_down_count
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(PAGE))
            self.end_headers()
            self.wfile.write(PAGE.encode('utf-8'))
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except:
                pass
        elif self.path.startswith('/?command=sensor_data'):
            temperature, humidity = read_dht_sensor()
            moisture_value = read_soil_moisture_digital()

            response = {
        "temperature": f"{temperature:.1f}°C" if temperature else "--",
        "humidity": f"{humidity:.1f}%" if humidity else "--",
        "moisture": moisture_value
    }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(str(response).replace("'", '"').encode())  # Ensure proper JSON format

        elif self.path.startswith('/?command='):
            command = self.path.split('=')[-1]
            if command == 'forward': 
                motors_forward()
            elif command == 'backward': 
                motors_backward()
            elif command == 'left':
                motors_left()
            elif command == 'right':
                motors_right()
            elif command == 'stop': 
                motors_stop()
            elif command == 'pan_left' and pan_left_count < 2: 
                move_servo(servo_pan, 70)
                pan_left_count += 1
            elif command == 'pan_right' and pan_right_count < 2: 
                move_servo(servo_pan, 95)
                pan_right_count += 1
            elif command == 'tilt_up' and tilt_up_count < 3: 
                move_servo(servo_tilt, 45)
                tilt_up_count += 1
            elif command == 'tilt_down' and tilt_down_count < 3: 
                move_servo(servo_tilt, 120)
                tilt_down_count += 1
            elif command == 'up1':
                move_servo(servo_up1, 90)  # Adjust angle as needed
            elif command == 'down1':
                move_servo(servo_up1, 0)   # Move back to original position
            elif command == 'up2':
                move_servo(servo_up2, 90)
            elif command == 'down2':
                move_servo(servo_up2, 0)
            elif command == 'pump_on': 
                GPIO.output(27, GPIO.HIGH)
            elif command == 'pump_off': 
                GPIO.output(27, GPIO.LOW)
            elif command == 'buzzer_on': 
                GPIO.output(RELAY_BUZZER, GPIO.HIGH)
            elif command == 'buzzer_off': 
                GPIO.output(RELAY_BUZZER, GPIO.LOW)
            elif command == 'light_on': 
                GPIO.output(RELAY_LIGHT, GPIO.HIGH)
            elif command == 'light_off': 
                GPIO.output(RELAY_LIGHT, GPIO.LOW)

	    # If tilt up count is 3 , disable tilt up until tilt down is pressed
            if tilt_up_count == 3 and command == 'tilt_up':
                self.send_response(403)
                self.end_headers()
	    # if tilt down count is 3 , disable tilt down until tilt up is pressed
            if tilt_down_count == 3 and command == 'tilt_down':
                self.send_response(403)
                self.end_headers()
            # If pan left count is 2, disable pan left until pan right is pressed
            if pan_left_count == 2 and command == 'pan_left':
                self.send_response(403)  # Forbidden
                self.end_headers()

            # If pan right count is 2, disable pan right until pan left is pressed
            if pan_right_count == 2 and command == 'pan_right':
                self.send_response(403)  # Forbidden
                self.end_headers()
            if command == 'tilt_up' and tilt_down_count == 3 or command == 'tilt_up' and tilt_down_count == 2 or command == 'tilt_up' and tilt_down_count == 1:
                tilt_down_count -= 1
            if command == 'tilt_down' and tilt_up_count == 3 or command == 'tilt_down' and tilt_up_count == 2 or command == 'tilt_down' and tilt_up_count == 1:
                tilt_up_count -= 1
            # Decrease pan_left_count by 1 when pan_right is pressed
            if command == 'pan_right' and pan_left_count == 2 or command == 'pan_right' and pan_left_count == 1:
                pan_left_count -= 1

            # Decrease pan_right_count by 1 when pan_left is pressed
            if command == 'pan_left' and pan_right_count == 2 or command == 'pan_left' and pan_right_count == 1:
                pan_right_count -= 1

            self.send_response(200)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))

hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)

try:
    address = ('', 8000)
    server = StreamingServer(address, RequestHandler)
    print(f"Server running at http://{ip_address}:8000")
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    picam2.stop_recording()
    for pwm in [pwm_a, pwm_b]:
        pwm.stop()
    servo_pan.stop()
    servo_tilt.stop()
    GPIO.cleanup()
