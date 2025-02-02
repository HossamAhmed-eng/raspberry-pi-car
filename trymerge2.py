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

# GPIO motor drivers
# driver 1
IN1, IN2, ENA = 17, 18, 22
IN3, IN4, ENB = 23, 24, 25
# driver 2
IN5, IN6, ENA2 = 5, 6, 12
IN7, IN8, ENB2 = 13, 19, 26
# Servo Motors
SERVO_PAN, SERVO_TILT = 20, 21

GPIO.setmode(GPIO.BCM)

# Setup for motors
for pin in [IN1, IN2, ENA, IN3, IN4, ENB, IN5, IN6, ENA2, IN7, IN8, ENB2]:
    GPIO.setup(pin, GPIO.OUT)

# Setup for servos
GPIO.setup(SERVO_PAN, GPIO.OUT)
GPIO.setup(SERVO_TILT, GPIO.OUT)
servo_pan = GPIO.PWM(SERVO_PAN, 50)
servo_tilt = GPIO.PWM(SERVO_TILT, 50)
servo_pan.start(0)
servo_tilt.start(0)

# PWM setup for motor speed control (might not be working idk)
pwm_a, pwm_b, pwm_a2, pwm_b2 = [GPIO.PWM(pin, 1000) for pin in [ENA, ENB, ENA2, ENB2]]
for pwm in [pwm_a, pwm_b, pwm_a2, pwm_b2]:
    pwm.start(100)

tilt_up_count = 0
tilt_down_count = 0
pan_left_count = 0
pan_right_count = 0

def motors_forward():
    GPIO.output([IN1, IN3, IN5, IN7], GPIO.HIGH)
    GPIO.output([IN2, IN4, IN6, IN8], GPIO.LOW)

def motors_backward():
    GPIO.output([IN1, IN3, IN5, IN7], GPIO.LOW)
    GPIO.output([IN2, IN4, IN6, IN8], GPIO.HIGH)

def motors_stop():
    GPIO.output([IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8], GPIO.LOW)

def set_speed(duty_cycle):
    for pwm in [pwm_a, pwm_b, pwm_a2, pwm_b2]:
        pwm.ChangeDutyCycle(duty_cycle)

def move_servo(servo, angle):
    duty = 2.5 + (angle / 18)
    servo.ChangeDutyCycle(duty)
    time.sleep(0.3)
    servo.ChangeDutyCycle(0)

PAGE = """
<html>
<head><title>Car Control</title></head>
<body>
<h1>Motor & Camera Control</h1>
<img src="/stream.mjpg" width="640" height="480" />
<button onclick="fetch('/?command=forward')">Forward</button>
<button onclick="fetch('/?command=backward')">Backward</button>
<button onclick="fetch('/?command=stop')">Stop</button>
<input type="range" min="0" max="100" value="100" id="speed" onchange="fetch('/?command=speed&value=' + this.value)"> Speed
<br>
<button onclick="fetch('/?command=pan_left')">Pan Left</button>
<button onclick="fetch('/?command=pan_right')">Pan Right</button>
<button onclick="fetch('/?command=tilt_up')">Tilt Up</button>
<button onclick="fetch('/?command=tilt_down')">Tilt Down</button>
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
        elif self.path.startswith('/?command='):
            command = self.path.split('=')[-1]
            if command == 'forward': 
                motors_forward()
            elif command == 'backward': 
                motors_backward()
            elif command == 'stop': 
                motors_stop()
            elif 'speed' in command:
                set_speed(int(self.path.split('value=')[-1]))
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
    for pwm in [pwm_a, pwm_b, pwm_a2, pwm_b2]:
        pwm.stop()
    servo_pan.stop()
    servo_tilt.stop()
    GPIO.cleanup()
