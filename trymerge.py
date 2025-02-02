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

# GPIO setup for motor drivers
# Motor Driver 1
IN1 = 17  # Motor A1 control
IN2 = 18  # Motor A1 control
ENA = 22  # Enable pin for Motor A1
IN3 = 23  # Motor B1 control
IN4 = 24  # Motor B1 control
ENB = 25  # Enable pin for Motor B1

# Motor Driver 2
IN5 = 5   # Motor A2 control
IN6 = 6   # Motor A2 control
ENA2 = 12 # Enable pin for Motor A2
IN7 = 13  # Motor B2 control
IN8 = 19  # Motor B2 control
ENB2 = 26 # Enable pin for Motor B2

GPIO.setmode(GPIO.BCM)

# Setup for Motor Driver 1
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(ENA, GPIO.OUT)
GPIO.setup(IN3, GPIO.OUT)
GPIO.setup(IN4, GPIO.OUT)
GPIO.setup(ENB, GPIO.OUT)

# Setup for Motor Driver 2
GPIO.setup(IN5, GPIO.OUT)
GPIO.setup(IN6, GPIO.OUT)
GPIO.setup(ENA2, GPIO.OUT)
GPIO.setup(IN7, GPIO.OUT)
GPIO.setup(IN8, GPIO.OUT)
GPIO.setup(ENB2, GPIO.OUT)

# PWM setup for speed control
pwm_a = GPIO.PWM(ENA, 1000)
pwm_b = GPIO.PWM(ENB, 1000)
pwm_a2 = GPIO.PWM(ENA2, 1000)
pwm_b2 = GPIO.PWM(ENB2, 1000)

pwm_a.start(100)
pwm_b.start(100)
pwm_a2.start(100)
pwm_b2.start(100)

# Functions to control the motors
def motors_forward():
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH)
    GPIO.output(IN4, GPIO.LOW)
    GPIO.output(IN5, GPIO.HIGH)
    GPIO.output(IN6, GPIO.LOW)
    GPIO.output(IN7, GPIO.HIGH)
    GPIO.output(IN8, GPIO.LOW)

def motors_backward():
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.HIGH)
    GPIO.output(IN5, GPIO.LOW)
    GPIO.output(IN6, GPIO.HIGH)
    GPIO.output(IN7, GPIO.LOW)
    GPIO.output(IN8, GPIO.HIGH)

def motors_stop():
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.LOW)
    GPIO.output(IN5, GPIO.LOW)
    GPIO.output(IN6, GPIO.LOW)
    GPIO.output(IN7, GPIO.LOW)
    GPIO.output(IN8, GPIO.LOW)

def set_speed(duty_cycle):
    pwm_a.ChangeDutyCycle(duty_cycle)
    pwm_b.ChangeDutyCycle(duty_cycle)
    pwm_a2.ChangeDutyCycle(duty_cycle)
    pwm_b2.ChangeDutyCycle(duty_cycle)

# HTML page for motor control and camera stream
PAGE = """\
<html>
<head>
<title>Motor Control and Camera Stream</title>
</head>
<body>
<h1>Motor Control</h1>
<button onclick="fetch('/?command=forward')">Forward</button>
<button onclick="fetch('/?command=backward')">Backward</button>
<button onclick="fetch('/?command=stop')">Stop</button>
<input type="range" min="0" max="100" value="100" id="speed" onchange="fetch('/?command=speed&value=' + this.value)"> Speed
<h1>Camera Stream</h1>
<img src="stream.mjpg" width="640" height="480" />
</body>
</html>
"""

# Class to handle MJPEG streaming
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

# Class to handle HTTP requests
class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
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
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        elif self.path.startswith("/?command="):
            command = self.path.split("=")[-1]
            if command == "forward":
                motors_forward()
            elif command == "backward":
                motors_backward()
            elif command == "stop":
                motors_stop()
            elif "speed" in command:
                value = int(self.path.split("value=")[-1])
                set_speed(value)
            
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE.encode("utf-8"))
        else:
            self.send_error(404)
            self.end_headers()

# Create Picamera2 instance and configure it
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))

# Get Raspberry Pi's local IP address
hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)

# Set up the server to handle both motor control and streaming
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

with StreamingServer(('', 8000), StreamingHandler) as httpd:
    print(f"Serving at http://{ip_address}:8000")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        picam2.stop_recording()
        pwm_a.stop()
        pwm_b.stop()
        pwm_a2.stop()
        pwm_b2.stop()
        GPIO.cleanup()

